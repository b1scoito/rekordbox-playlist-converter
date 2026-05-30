"""Rekordbox playlist converter: orchestrates ffmpeg, XML I/O, and manifest.

Holds the project's only stateful class. Wraps the pure quality helpers
(`quality.py`) with the side-effecting work: reading the rekordbox XML,
running ffmpeg, writing the standalone XML and JSON manifest. Uses Rich for
progress reporting via the shared console (`_console.py`).
"""

# PEP 563: all type annotations are evaluated lazily as strings. Lets us use
# generic forms like `ET.ElementTree[Any]` even though ElementTree isn't
# subscriptable at runtime in the stdlib.
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, assert_never
from urllib.parse import unquote

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from _console import console
from models import CDJ_MODELS
from quality import (
    can_passthrough,
    existing_matches_plan,
    parse_max_quality,
    plan_conversion,
    probe,
)

# ffmpeg wall-clock ceiling. Long 96k/24 sources can take a couple of minutes;
# bound it so one pathological file can't hang the whole playlist.
FFMPEG_TIMEOUT_SECONDS = 600


class OutputFormat(StrEnum):
    """Audio formats we can produce. StrEnum lets us pass these as plain
    strings to ffmpeg / typer without losing type-checker exhaustiveness."""

    MP3 = "mp3"
    FLAC = "flac"
    AIFF = "aiff"


class Action(StrEnum):
    """What `convert_track` did for one source.

    - ENCODED: ran ffmpeg with full decode + encode pipeline.
    - PASSTHROUGH: muxed without re-encoding (same format, within caps).
    - SKIPPED: prior good output was reused unchanged.
    """

    ENCODED = "encoded"
    PASSTHROUGH = "passthrough"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class FormatSettings:
    """Per-format ffmpeg knobs. Frozen + module-level shared so we don't
    rebuild this dict on every converter instance."""

    ext: str
    codec: str
    bitrate: str | None = None
    default_sample_rate: int | None = None
    compression_level: str | None = None


FORMAT_SETTINGS: dict[OutputFormat, FormatSettings] = {
    OutputFormat.MP3: FormatSettings(
        ext="mp3", codec="libmp3lame", bitrate="320k", default_sample_rate=44100
    ),
    OutputFormat.FLAC: FormatSettings(
        ext="flac", codec="flac", default_sample_rate=48000, compression_level="5"
    ),
    OutputFormat.AIFF: FormatSettings(ext="aiff", codec="pcm_s16be", default_sample_rate=44100),
}


@dataclass
class ConversionResult:
    """What `convert_track` learned about one source -> output pairing.

    Captures the inputs to the capping decision (source rate/depth), the
    decision itself (target rate/depth), and observable properties of the
    final file (bitrate, size, duration). Used to (a) write honest XML
    metadata, (b) emit the manifest, and (c) drive --dry-run reporting
    without actually invoking ffmpeg.
    """

    source_path: Path
    output_path: Path
    output_format: OutputFormat
    action: Action
    source_sample_rate: int | None = None
    source_bit_depth: int | None = None
    target_sample_rate: int | None = None
    target_bit_depth: int | None = None
    output_bitrate_kbps: int | None = None
    output_size_bytes: int | None = None
    duration_seconds: float | None = None


class RekordboxPlaylistConverter:
    """Read a rekordbox XML, convert tracks via ffmpeg, emit a standalone XML.

    Never modifies the source XML. Builds a fresh DJ_PLAYLISTS tree containing
    only the converted tracks with new TrackIDs (default starting at 1,000,000)
    so it can be imported alongside the original library without collisions.
    """

    # Declared up-front so pyright sees the attribute even before
    # create_standalone_xml() runs.
    standalone_tree: ET.ElementTree[Any]
    standalone_root: ET.Element

    def __init__(
        self,
        xml_path: str,
        output_format: str | OutputFormat = OutputFormat.MP3,
        starting_track_id: int = 1000000,
        cdj_model: str | None = None,
    ) -> None:
        self.xml_path: Path = Path(xml_path)
        try:
            self.output_format: OutputFormat = OutputFormat(str(output_format).lower())
        except ValueError as e:
            raise ValueError(
                f"Unsupported format: {output_format}. Use 'mp3', 'flac', or 'aiff'"
            ) from e

        # Deck identity + per-format quality caps. An empty caps dict means
        # "no ceiling" -- conversion preserves the source verbatim.
        self.cdj_model: str | None = cdj_model.upper() if cdj_model else None
        self.max_quality_caps: dict[str, tuple[int | None, int | None]] = {}
        if self.cdj_model and self.cdj_model in CDJ_MODELS:
            for fmt, spec in CDJ_MODELS[self.cdj_model].get("max_quality", {}).items():
                self.max_quality_caps[fmt] = parse_max_quality(spec)

        self.tree: ET.ElementTree[Any]
        self.root: ET.Element
        self.tracks_map: dict[str, ET.Element] = {}  # TrackID -> TRACK element
        self.starting_track_id: int = starting_track_id
        self.new_track_id_counter: int = starting_track_id

    @property
    def format_settings(self) -> FormatSettings:
        """Shortcut to the FormatSettings for this converter's output format."""
        return FORMAT_SETTINGS[self.output_format]

    # ----- XML loading + playlist discovery -----

    def load_xml(self) -> None:
        """Load and parse the rekordbox XML file."""
        console.print(f"Loading XML: {self.xml_path}")
        self.tree = ET.parse(self.xml_path)
        root = self.tree.getroot()
        assert root is not None, "XML root element not found"
        self.root = root
        collection = self.root.find("COLLECTION")
        if collection is not None:
            for track in collection.findall("TRACK"):
                track_id = track.get("TrackID")
                if track_id:
                    self.tracks_map[track_id] = track
        console.print(f"Loaded {len(self.tracks_map)} tracks from collection")

    def list_playlists(self) -> list[tuple[str, ET.Element, int]]:
        """Return [(path, node, entries), ...] for every playlist in the XML."""
        playlists: list[tuple[str, ET.Element, int]] = []
        playlists_node = self.root.find("PLAYLISTS")
        if playlists_node is not None:
            self._collect_playlists(playlists_node, "", playlists)
        return playlists

    def _collect_playlists(
        self, node: ET.Element, path: str, playlists: list[tuple[str, ET.Element, int]]
    ) -> None:
        for child in node.findall("NODE"):
            name = child.get("Name", "")
            node_type = child.get("Type", "0")
            current_path = f"{path}/{name}" if path else name
            if node_type == "1":  # playlist
                entries = child.get("Entries", "0")
                playlists.append((current_path, child, int(entries)))
            else:  # folder
                self._collect_playlists(child, current_path, playlists)

    @staticmethod
    def url_to_path(location: str) -> Path | None:
        """Decode a rekordbox `file://localhost/...` URL into a local Path."""
        if not location.startswith("file://localhost"):
            return None
        return Path(unquote(location.replace("file://localhost", "")))

    # ----- Track conversion -----

    def _plan_for_track(
        self, track_element: ET.Element, output_dir: Path
    ) -> tuple[ConversionResult, str | None] | None:
        """Compute the planned conversion for a track without running ffmpeg.

        Returns (planned_result, source_codec) -- codec is internal-only and
        used by `convert_track` to decide passthrough. Result's `action`
        reflects the prediction: SKIPPED if existing output already matches;
        PASSTHROUGH if source can be muxed without re-encoding; ENCODED
        otherwise. None if the source file can't be located.
        """
        location = track_element.get("Location")
        if not location:
            return None
        source_path = self.url_to_path(location)
        if not source_path or not source_path.exists():
            return None

        track_name = track_element.get("Name", "Unknown")
        artist = track_element.get("Artist", "")
        safe_filename = self.sanitize_filename(f"{artist} - {track_name}" if artist else track_name)
        output_path = output_dir / f"{safe_filename}.{self.format_settings.ext}"

        source_sr, source_bd, source_codec, _source_bitrate, source_duration = probe(source_path)
        cap_sr, cap_bd = self.max_quality_caps.get(self.output_format.value, (None, None))
        target_sr, target_bd = plan_conversion(
            self.output_format.value, source_sr, source_bd, cap_sr, cap_bd
        )

        # Existing-output reuse: the prior file is consistent with this plan
        # iff its probed rate/depth matches what we'd produce now. Different
        # deck or format between runs -> mismatch -> re-encode.
        if output_path.exists():
            existing_sr, existing_bd, _ec, existing_bitrate_bps, existing_duration = probe(
                output_path
            )
            if existing_matches_plan(
                self.output_format.value, existing_sr, existing_bd, target_sr, target_bd
            ):
                try:
                    size_bytes: int | None = output_path.stat().st_size
                except OSError:
                    size_bytes = None
                return (
                    ConversionResult(
                        source_path=source_path,
                        output_path=output_path,
                        output_format=self.output_format,
                        action=Action.SKIPPED,
                        source_sample_rate=source_sr,
                        source_bit_depth=source_bd,
                        target_sample_rate=existing_sr,
                        target_bit_depth=existing_bd,
                        output_bitrate_kbps=(
                            round(existing_bitrate_bps / 1000)
                            if existing_bitrate_bps is not None
                            else None
                        ),
                        output_size_bytes=size_bytes,
                        duration_seconds=existing_duration or source_duration,
                    ),
                    source_codec,
                )

        action = (
            Action.PASSTHROUGH
            if can_passthrough(
                self.output_format.value,
                source_codec,
                source_sr,
                source_bd,
                target_sr,
                target_bd,
            )
            else Action.ENCODED
        )
        return (
            ConversionResult(
                source_path=source_path,
                output_path=output_path,
                output_format=self.output_format,
                action=action,
                source_sample_rate=source_sr,
                source_bit_depth=source_bd,
                target_sample_rate=target_sr,
                target_bit_depth=target_bd,
                duration_seconds=source_duration,
            ),
            source_codec,
        )

    def _build_ffmpeg_cmd(
        self,
        source_path: Path,
        temp_path: Path,
        source_sr: int | None,
        source_bd: int | None,
        target_sr: int | None,
        target_bd: int | None,
        passthrough: bool,
    ) -> list[str]:
        """Assemble the ffmpeg invocation for one track.

        Sample rate is only added when stepping DOWN. Bit depth is enforced
        via codec choice for AIFF and `-sample_fmt` for FLAC (only when
        reducing). MP3 carries no PCM depth. Passthrough mode replaces all
        audio codec options with `-c:a copy`. Cover art is carried for
        MP3/FLAC (AIFF can't embed it).
        """
        # Cover art travels for the muxers that accept it.
        carry_art = self.output_format in (OutputFormat.MP3, OutputFormat.FLAC)

        cmd: list[str] = ["ffmpeg", "-i", str(source_path)]
        if carry_art:
            # First audio stream + optional attached picture; '?' makes the
            # art mapping a no-op when the source has none.
            cmd.extend(["-map", "0:a:0", "-map", "0:v?"])
        else:
            cmd.append("-vn")  # AIFF can't hold attached pictures

        if passthrough:
            cmd.extend(["-c:a", "copy"])
        else:
            self._extend_with_audio_args(cmd, source_sr, source_bd, target_sr, target_bd)

        if carry_art:
            cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])

        cmd.extend(["-y", str(temp_path)])
        return cmd

    def _extend_with_audio_args(
        self,
        cmd: list[str],
        source_sr: int | None,
        source_bd: int | None,
        target_sr: int | None,
        target_bd: int | None,
    ) -> None:
        """Append the codec / bitrate / sample-rate args for full encoding.

        Split out of `_build_ffmpeg_cmd` so the format dispatch stays in one
        `match` block and the passthrough branch stays trivially obvious.
        """
        # Sample rate: resample only when stepping DOWN; if probe failed,
        # fall back to the format's safe default rate.
        if target_sr is not None and source_sr is not None and target_sr < source_sr:
            cmd.extend(["-ar", str(target_sr)])
        elif source_sr is None and self.format_settings.default_sample_rate is not None:
            cmd.extend(["-ar", str(self.format_settings.default_sample_rate)])

        bitrate = self.format_settings.bitrate
        if bitrate:
            cmd.extend(["-b:a", bitrate])

        match self.output_format:
            case OutputFormat.AIFF:
                depth = target_bd if target_bd is not None else 16
                codec = "pcm_s24be" if depth >= 24 else "pcm_s16be"
                cmd.extend(["-acodec", codec])
            case OutputFormat.FLAC:
                cmd.extend(["-acodec", "flac"])
                # Force sample_fmt only when reducing >16 -> 16; otherwise
                # let ffmpeg preserve native depth (s16/s32 carry 16/24).
                if (
                    target_bd is not None
                    and target_bd <= 16
                    and (source_bd is None or source_bd > 16)
                ):
                    cmd.extend(["-sample_fmt", "s16"])
                cmd.extend(["-compression_level", self.format_settings.compression_level or "5"])
            case OutputFormat.MP3:
                cmd.extend(["-acodec", self.format_settings.codec])
            case _:  # pragma: no cover - exhaustive
                assert_never(self.output_format)

    def _run_ffmpeg(self, cmd: list[str], temp_path: Path, output_path: Path) -> bool:
        """Execute ffmpeg; atomic-rename temp -> output on success.

        Returns True iff the output was produced. On any failure
        (missing binary, timeout, non-zero exit) the temp file is cleaned up
        so a partial encode never masquerades as a finished one.
        """
        import subprocess  # local import: only needed in the encode path

        try:
            run = subprocess.run(
                cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS
            )
        except FileNotFoundError:
            temp_path.unlink(missing_ok=True)
            return False  # ffmpeg not installed
        except subprocess.TimeoutExpired:
            temp_path.unlink(missing_ok=True)
            return False
        except Exception:
            temp_path.unlink(missing_ok=True)
            return False

        if run.returncode != 0:
            temp_path.unlink(missing_ok=True)
            return False
        temp_path.replace(output_path)  # atomic on the same filesystem
        return True

    def _result_from_encoded_output(self, planned_result: ConversionResult) -> ConversionResult:
        """Probe the freshly-encoded file and return a result reflecting what
        actually shipped (not what we planned). Used to keep XML / manifest
        honest about bitrate / sample rate / size."""
        out_sr, out_bd, _oc, out_bitrate_bps, out_duration = probe(planned_result.output_path)
        try:
            size_bytes: int | None = planned_result.output_path.stat().st_size
        except OSError:
            size_bytes = None
        return ConversionResult(
            source_path=planned_result.source_path,
            output_path=planned_result.output_path,
            output_format=planned_result.output_format,
            action=planned_result.action,
            source_sample_rate=planned_result.source_sample_rate,
            source_bit_depth=planned_result.source_bit_depth,
            target_sample_rate=out_sr if out_sr is not None else planned_result.target_sample_rate,
            target_bit_depth=out_bd if out_bd is not None else planned_result.target_bit_depth,
            output_bitrate_kbps=(
                round(out_bitrate_bps / 1000) if out_bitrate_bps is not None else None
            ),
            output_size_bytes=size_bytes,
            duration_seconds=(
                out_duration if out_duration is not None else planned_result.duration_seconds
            ),
        )

    def convert_track(
        self,
        track_element: ET.Element,
        output_dir: Path,
        *,
        dry_run: bool = False,
    ) -> ConversionResult | None:
        """Convert a single track. Returns a ConversionResult, or None on
        unrecoverable failure (missing source, ffmpeg error)."""
        plan = self._plan_for_track(track_element, output_dir)
        if plan is None:
            return None
        planned_result, _source_codec = plan
        if dry_run or planned_result.action == Action.SKIPPED:
            return planned_result

        # Atomic write: encode to a sibling temp file, rename on success.
        # Real extension stays last so ffmpeg can still infer the muxer.
        output_path = planned_result.output_path
        temp_path = output_path.with_name(f".{output_path.stem}.part{output_path.suffix}")
        cmd = self._build_ffmpeg_cmd(
            planned_result.source_path,
            temp_path,
            planned_result.source_sample_rate,
            planned_result.source_bit_depth,
            planned_result.target_sample_rate,
            planned_result.target_bit_depth,
            passthrough=(planned_result.action == Action.PASSTHROUGH),
        )
        if not self._run_ffmpeg(cmd, temp_path, output_path):
            return None
        return self._result_from_encoded_output(planned_result)

    # ----- XML element building -----

    def _create_track_element(
        self,
        original_track: ET.Element,
        new_track_id: str | None,
        result: ConversionResult,
    ) -> ET.Element:
        """Build a TRACK element for the standalone XML.

        Copies every attribute and child element of the original (so all
        rekordbox metadata, TEMPO beatgrid, and POSITION_MARK cues carry
        across), then overrides Location/Kind/BitRate/SampleRate/Size with
        honest values probed from the encoded output.
        """
        new_track = ET.Element("TRACK", attrib=dict(original_track.attrib))
        if new_track_id:
            new_track.set("TrackID", new_track_id)
        new_track.set("Location", f"file://localhost{result.output_path.as_posix()}")

        match self.output_format:
            case OutputFormat.MP3:
                new_track.set("Kind", "MP3 File")
            case OutputFormat.FLAC:
                new_track.set("Kind", "FLAC File")
            case OutputFormat.AIFF:
                new_track.set("Kind", "AIFF File")
            case _:  # pragma: no cover - exhaustive
                assert_never(self.output_format)

        if result.output_bitrate_kbps is not None:
            new_track.set("BitRate", str(result.output_bitrate_kbps))
        elif result.target_sample_rate and result.target_bit_depth:
            # Lossless without a probed bitrate: rate * depth * 2ch -> kbps.
            derived = result.target_sample_rate * result.target_bit_depth * 2 // 1000
            new_track.set("BitRate", str(derived))
        if result.target_sample_rate is not None:
            new_track.set("SampleRate", str(result.target_sample_rate))
        if result.output_size_bytes is not None:
            new_track.set("Size", str(result.output_size_bytes))

        # Preserve TEMPO / POSITION_MARK / any other child elements.
        for child in original_track:
            new_track.append(child)
        return new_track

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Drop characters that aren't safe across macOS / Windows / Linux."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
        return filename[:200]

    # ----- Playlist-level orchestration -----

    def convert_playlist(
        self,
        playlist_name: str,
        output_dir: str,
        *,
        dry_run: bool = False,
        jobs: int | None = None,
    ) -> tuple[bool, str | None, list[ET.Element], list[ConversionResult]]:
        """Convert every track in a playlist.

        Returns (success, display_name, track_elements, results). `results`
        is the data source for the manifest. dry_run=True only probes/plans
        and writes no files. `jobs` controls ffmpeg parallelism (default:
        cpu_count).
        """
        output_path = Path(output_dir)
        if not dry_run:
            output_path.mkdir(parents=True, exist_ok=True)

        playlists = self.list_playlists()
        target_playlist = next(
            (
                node
                for path, node, _entries in playlists
                if path == playlist_name or node.get("Name") == playlist_name
            ),
            None,
        )
        if target_playlist is None:
            console.print(f"[bold red]Error:[/bold red] Playlist '{playlist_name}' not found")
            return (False, None, [], [])

        console.print(f"\n[bold]Playlist:[/bold] {playlist_name}")
        console.print(f"[bold]Output:[/bold] {output_path}")
        console.print(f"[bold]Format:[/bold] {self.output_format.value.upper()}")
        if self.cdj_model:
            console.print(f"[bold]CDJ model:[/bold] {self.cdj_model}")
        if dry_run:
            console.print("[bold yellow]Mode:[/bold yellow] DRY RUN (no files written)")

        # Pre-assign track IDs in playlist order so parallel workers don't
        # race a shared counter, and the standalone XML preserves ordering
        # regardless of which conversion finishes first.
        track_keys = [t.get("Key") for t in target_playlist.findall("TRACK")]
        work_items: list[tuple[int, ET.Element, str]] = []
        for i, track_key in enumerate(track_keys):
            if track_key is None or track_key not in self.tracks_map:
                console.print(
                    f"  [yellow]warn[/yellow] track {track_key} not in collection, skipping"
                )
                continue
            new_track_id = str(self.new_track_id_counter)
            self.new_track_id_counter += 1
            work_items.append((i, self.tracks_map[track_key], new_track_id))

        if dry_run:
            n_workers = 1  # probe-only; no benefit from parallel
        elif jobs is not None and jobs > 0:
            n_workers = jobs
        else:
            n_workers = os.cpu_count() or 1

        results_by_index: dict[int, tuple[ConversionResult, ET.Element]] = {}

        def process(
            item: tuple[int, ET.Element, str],
        ) -> tuple[int, tuple[ConversionResult, ET.Element] | None]:
            i, original_track, new_id = item
            result = self.convert_track(original_track, output_path, dry_run=dry_run)
            if result is None:
                return (i, None)
            elem = self._create_track_element(original_track, new_id, result)
            return (i, (result, elem))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(
                "Planning" if dry_run else "Converting", total=len(work_items)
            )
            if n_workers <= 1:
                for item in work_items:
                    idx, outcome = process(item)
                    if outcome is not None:
                        results_by_index[idx] = outcome
                    progress.advance(task_id)
            else:
                with ThreadPoolExecutor(max_workers=n_workers) as ex:
                    futures = [ex.submit(process, item) for item in work_items]
                    for fut in as_completed(futures):
                        idx, outcome = fut.result()
                        if outcome is not None:
                            results_by_index[idx] = outcome
                        progress.advance(task_id)

        # Restore original playlist order.
        converted_tracks: list[ET.Element] = []
        all_results: list[ConversionResult] = []
        for i in range(len(track_keys)):
            outcome = results_by_index.get(i)
            if outcome is None:
                continue
            result, elem = outcome
            all_results.append(result)
            converted_tracks.append(elem)

        # Per-action summary so the user sees what really happened
        # (e.g. "30 encoded, 5 passthrough, 12 skipped").
        n_encoded = sum(1 for r in all_results if r.action == Action.ENCODED)
        n_passthrough = sum(1 for r in all_results if r.action == Action.PASSTHROUGH)
        n_skipped = sum(1 for r in all_results if r.action == Action.SKIPPED)
        n_failed = len(work_items) - len(all_results)
        summary_parts = [f"[green]{n_encoded} encoded[/green]"]
        if n_passthrough:
            summary_parts.append(f"[cyan]{n_passthrough} passthrough[/cyan]")
        if n_skipped:
            summary_parts.append(f"[dim]{n_skipped} skipped[/dim]")
        if n_failed:
            summary_parts.append(f"[red]{n_failed} failed[/red]")
        console.print("\n[bold]Done.[/bold] " + ", ".join(summary_parts))

        if dry_run:
            self._print_dry_run_table(all_results)

        fmt_label = self.output_format.value.upper()
        playlist_display_name = f"{target_playlist.get('Name')} ({fmt_label})"
        return (
            len(converted_tracks) > 0,
            playlist_display_name,
            converted_tracks,
            all_results,
        )

    def _print_dry_run_table(self, results: list[ConversionResult]) -> None:
        """Print a Rich table summarizing the planned conversion per track."""
        table = Table(title="\nConversion plan", show_header=True, header_style="bold magenta")
        table.add_column("Track", style="cyan", overflow="fold")
        table.add_column("Source", justify="center")
        table.add_column("Target", justify="center")
        table.add_column("Action", justify="center")
        action_style = {
            Action.ENCODED: "[green]encode[/green]",
            Action.PASSTHROUGH: "[cyan]copy[/cyan]",
            Action.SKIPPED: "[dim]skip[/dim]",
        }
        for r in results:
            src = self._format_quality(r.source_sample_rate, r.source_bit_depth)
            tgt = self._format_quality(r.target_sample_rate, r.target_bit_depth)
            table.add_row(r.output_path.name, src, tgt, action_style.get(r.action, r.action.value))
        console.print(table)

    @staticmethod
    def _format_quality(sample_rate: int | None, bit_depth: int | None) -> str:
        """Render '44.1k/16' style quality summary for the dry-run table."""
        # `:g` trims trailing zeros: 44100/1000 -> 44.1, 48000/1000 -> 48.
        sr_str = "?" if sample_rate is None else f"{sample_rate / 1000:g}k"
        bd_str = f"/{bit_depth}" if bit_depth is not None else ""
        return sr_str + bd_str

    def write_manifest(
        self,
        manifest_path: Path,
        playlist_name: str,
        results: list[ConversionResult],
    ) -> None:
        """Write a JSON manifest of the run for diffability between runs.

        Records per-track source/target rate and depth, output bitrate,
        size, duration, and action. Makes it easy to spot regressions and
        audit gig prep.
        """
        payload = {
            "playlist": playlist_name,
            "cdj_model": self.cdj_model,
            "output_format": self.output_format.value,
            "tracks": [
                {**asdict(r), "source_path": str(r.source_path), "output_path": str(r.output_path)}
                for r in results
            ],
        }
        # default=str handles Path and StrEnum members cleanly.
        manifest_path.write_text(json.dumps(payload, indent=2, default=str))

    # ----- Standalone XML emission -----

    def create_standalone_xml(self, playlist_name: str, converted_tracks: list[ET.Element]) -> None:
        """Build a fresh DJ_PLAYLISTS tree holding only the converted tracks.

        Importing this file in rekordbox adds a parallel playlist without
        touching the original collection -- new TrackIDs (default starting at
        1,000,000) avoid colliding with existing entries.
        """
        new_root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
        ET.SubElement(new_root, "PRODUCT", Name="rekordbox", Version="6.0.0", Company="Pioneer DJ")
        collection = ET.SubElement(new_root, "COLLECTION", Entries=str(len(converted_tracks)))
        for track in converted_tracks:
            collection.append(track)

        playlists_node = ET.SubElement(new_root, "PLAYLISTS")
        root_node = ET.SubElement(playlists_node, "NODE", Type="0", Name="ROOT", Count="1")
        playlist_node = ET.SubElement(
            root_node,
            "NODE",
            Name=playlist_name,
            Type="1",
            KeyType="0",
            Entries=str(len(converted_tracks)),
        )
        for track in converted_tracks:
            track_id = track.get("TrackID")
            if track_id:
                ET.SubElement(playlist_node, "TRACK", Key=track_id)

        self.standalone_tree = ET.ElementTree(new_root)
        self.standalone_root = new_root
        console.print(f"Created standalone XML with {len(converted_tracks)} tracks")

    def save_standalone_xml(self, output_path: str) -> Path:
        """Write the standalone XML to disk (original XML is never touched)."""
        # standalone_tree is class-declared but only bound by create_standalone_xml;
        # hasattr is enough to detect the not-yet-built case.
        if not hasattr(self, "standalone_tree"):
            raise ValueError("No standalone XML created. Call create_standalone_xml() first.")
        output_file = Path(output_path)
        self._indent_xml(self.standalone_root)
        self.standalone_tree.write(str(output_file), encoding="UTF-8", xml_declaration=True)
        console.print(f"Saved standalone XML: {output_file}")
        return output_file

    def _indent_xml(self, elem: ET.Element, level: int = 0) -> None:
        """Pretty-print indentation, in-place. Python <3.9 didn't ship one."""
        indent = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            last_child = None
            for child in elem:
                self._indent_xml(child, level + 1)
                last_child = child
            if last_child is not None and (not last_child.tail or not last_child.tail.strip()):
                last_child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent
