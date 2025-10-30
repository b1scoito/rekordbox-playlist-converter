#!/usr/bin/env python3
"""
Rekordbox Playlist Converter
Converts tracks from a rekordbox playlist to MP3 format and creates a new playlist
"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(
    name="rekordbox-converter",
    help=(
        "Convert Rekordbox playlists with automatic format selection "
        "for Pioneer DJ CDJ/XDJ equipment"
    ),
    add_completion=False,
)

# Pioneer DJ CDJ/XDJ Format Support Database
CDJ_MODELS = {
    # High-end models with full FLAC/ALAC support (96kHz/24-bit)
    "CDJ-3000": {
        "year": 2020,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "CDJ-2000NXS2": {
        "year": 2016,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "CDJ-TOUR1": {
        "year": 2016,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "OPUS-QUAD": {
        "year": 2023,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    # Mid-range models with limited FLAC support (48kHz/24-bit)
    "XDJ-1000MK2": {
        "year": 2016,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "XDJ-XZ": {
        "year": 2019,
        "formats": ["flac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
        "notes": "FLAC support added in 2019 FW update",
    },
    "XDJ-RX3": {
        "year": 2021,
        "formats": ["flac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    # Older models without FLAC support
    "CDJ-2000NXS": {
        "year": 2012,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
        "notes": "MP3 320kbps recommended due to WAV/AIFF compatibility issues",
    },
    "CDJ-900NXS": {
        "year": 2013,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "CDJ-2000": {
        "year": 2009,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "CDJ-900": {
        "year": 2009,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-1000": {
        "year": 2014,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-700": {
        "year": 2015,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-RR": {
        "year": 2018,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-RX2": {
        "year": 2017,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-RX": {
        "year": 2015,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-R1": {
        "year": 2013,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-AERO": {
        "year": 2012,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
}


class RekordboxPlaylistConverter:
    """Convert rekordbox playlists to MP3 format"""

    # Dynamically added attributes (created in create_standalone_xml)
    standalone_tree: ET.ElementTree
    standalone_root: ET.Element

    def __init__(
        self,
        xml_path: str,
        output_format: str = "mp3",
        starting_track_id: int = 1000000,
    ) -> None:
        self.xml_path: Path = Path(xml_path)
        self.output_format: str = output_format.lower()
        self.tree: ET.ElementTree[Any]
        self.root: ET.Element
        self.tracks_map: dict[str, ET.Element] = {}  # TrackID -> TRACK element
        self.starting_track_id: int = starting_track_id
        self.new_track_id_counter: int = starting_track_id

        # Format settings
        self.format_settings: dict[str, dict[str, str | None]] = {
            "mp3": {
                "ext": "mp3",
                "codec": "libmp3lame",
                "bitrate": "320k",
                "sample_rate": "44100",
            },
            "flac": {
                "ext": "flac",
                "codec": "flac",
                "bitrate": None,  # Lossless
                "sample_rate": "48000",  # Safe default for most CDJs
                "compression_level": "5",  # Balanced compression
            },
            "aiff": {
                "ext": "aiff",
                "codec": "pcm_s16be",
                "bitrate": None,
                "sample_rate": "44100",
            },
        }

        if self.output_format not in self.format_settings:
            raise ValueError(f"Unsupported format: {output_format}. Use 'mp3', 'flac', or 'aiff'")

    @staticmethod
    def get_recommended_format_for_cdj(model: str) -> tuple[str, str]:
        """
        Get the recommended format for a specific CDJ/XDJ model.
        Returns: (format, reason)

        Rationale:
        - FLAC is preferred for models that support it (lossless + good tag support + no WAV issues)
        - MP3 320kbps is recommended for older models (universal support + no compatibility issues)
        - WAV/AIFF are avoided due to known compatibility issues with WAV_EXTENSIBLE metadata
        """
        model_upper = model.upper()

        if model_upper not in CDJ_MODELS:
            available_models = ", ".join(sorted(CDJ_MODELS.keys()))
            raise ValueError(f"Unknown CDJ model: {model}. Available models: {available_models}")

        model_info = CDJ_MODELS[model_upper]
        recommended = model_info["recommended"]

        if recommended == "flac":
            quality = model_info["max_quality"].get("flac", "48kHz/24-bit")
            reason = (
                f"FLAC (up to {quality}): Best quality with lossless compression, "
                "excellent tag support, no compatibility issues"
            )
        else:  # mp3
            reason = (
                "MP3 320kbps: Best compatibility, excellent tag support, "
                "no WAV/AIFF compatibility issues"
            )

        notes = model_info.get("notes")
        if notes:
            reason += f" | Note: {notes}"

        return (recommended, reason)

    @staticmethod
    def list_supported_cdj_models() -> None:
        """Print all supported CDJ/XDJ models with their format capabilities using Rich tables"""
        console.print("\n🎛️  [bold cyan]Supported Pioneer DJ CDJ/XDJ Models[/bold cyan]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Model", style="cyan", width=15)
        table.add_column("Year", justify="center", width=6)
        table.add_column("Recommended", style="green", width=12)
        table.add_column("Max Quality", width=15)
        table.add_column("Notes", width=30)

        for model, info in sorted(CDJ_MODELS.items(), key=lambda x: (-x[1]["year"], x[0])):
            recommended = info["recommended"].upper()
            max_qual = info["max_quality"].get(info["recommended"], "320kbps")
            notes = info.get("notes", "")
            table.add_row(model, str(info["year"]), recommended, max_qual, notes)

        console.print(table)

        console.print("\n[bold yellow]💡 Why these recommendations?[/bold yellow]")
        console.print(
            "  • [green]FLAC[/green]: Lossless compression, excellent tag support, "
            "no compatibility issues"
        )
        console.print(
            "  • [green]MP3 320kbps[/green]: Universal support, no WAV/AIFF compatibility issues"
        )
        console.print(
            "  • [red]WAV/AIFF avoided[/red]: Known WAV_EXTENSIBLE metadata issues on CDJs\n"
        )

    def load_xml(self) -> None:
        """Load and parse the rekordbox XML file"""
        print(f"Loading XML file: {self.xml_path}")
        self.tree = ET.parse(self.xml_path)
        root = self.tree.getroot()
        assert root is not None, "XML root element not found"
        self.root = root

        # Build track map for quick lookup
        collection = self.root.find("COLLECTION")
        if collection is not None:
            for track in collection.findall("TRACK"):
                track_id = track.get("TrackID")
                if track_id:
                    self.tracks_map[track_id] = track

        print(f"Loaded {len(self.tracks_map)} tracks from collection")

    def list_playlists(self) -> list[tuple[str, ET.Element, int]]:
        """List all available playlists"""
        playlists: list[tuple[str, ET.Element, int]] = []
        playlists_node = self.root.find("PLAYLISTS")

        if playlists_node is not None:
            self._collect_playlists(playlists_node, "", playlists)

        return playlists

    def _collect_playlists(
        self, node: ET.Element, path: str, playlists: list[tuple[str, ET.Element, int]]
    ) -> None:
        """Recursively collect all playlists"""
        for child in node.findall("NODE"):
            name = child.get("Name", "")
            node_type = child.get("Type", "0")

            current_path = f"{path}/{name}" if path else name

            if node_type == "1":  # It's a playlist
                entries = child.get("Entries", "0")
                playlists.append((current_path, child, int(entries)))
            else:  # It's a folder
                self._collect_playlists(child, current_path, playlists)

    def url_to_path(self, location: str) -> Path | None:
        """Convert file:// URL to local path"""
        if not location.startswith("file://localhost"):
            return None

        # Remove file://localhost prefix and decode URL encoding
        path_str = unquote(location.replace("file://localhost", ""))
        return Path(path_str)

    def convert_track(
        self, track_element: ET.Element, output_dir: Path
    ) -> tuple[Path, ET.Element] | None:
        """
        Convert a single track to the target format
        Returns: (new_path, new_track_element) or None if failed
        """
        location = track_element.get("Location")
        if not location:
            return None

        source_path = self.url_to_path(location)
        if not source_path or not source_path.exists():
            print(f"  ⚠ Source file not found: {source_path}")
            return None

        # Create output filename
        track_name = track_element.get("Name", "Unknown")
        artist = track_element.get("Artist", "")
        safe_filename = self._sanitize_filename(
            f"{artist} - {track_name}" if artist else track_name
        )

        format_settings = self.format_settings[self.output_format]
        output_path = output_dir / f"{safe_filename}.{format_settings['ext']}"

        # Skip if already converted
        if output_path.exists():
            print(f"  ✓ Already exists: {output_path.name}")
            return (output_path, self._create_track_element(track_element, output_path))

        # Convert using ffmpeg
        print(f"  Converting: {source_path.name} -> {output_path.name}")

        try:
            cmd = [
                "ffmpeg",
                "-i",
                str(source_path),
                "-vn",  # No video
                "-ar",
                format_settings["sample_rate"],
            ]

            # Add bitrate for lossy formats
            if format_settings.get("bitrate"):
                cmd.extend(["-b:a", format_settings["bitrate"]])

            # Add codec
            cmd.extend(["-acodec", format_settings["codec"]])

            # Add format-specific parameters
            if self.output_format == "flac":
                # FLAC compression level (0-12, 5 is default, good balance)
                compression_level = format_settings.get("compression_level", "5")
                cmd.extend(["-compression_level", compression_level])

            cmd.extend(["-y", str(output_path)])  # Overwrite output file

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print("  ✓ Converted successfully")
                return (
                    output_path,
                    self._create_track_element(track_element, output_path),
                )
            else:
                print(f"  ✗ Conversion failed: {result.stderr[:200]}")
                return None

        except FileNotFoundError:
            print("  ✗ ffmpeg not found. Please install ffmpeg to convert audio files.")
            return None
        except Exception as e:
            print(f"  ✗ Error during conversion: {e}")
            return None

    def _create_track_element(
        self,
        original_track: ET.Element,
        new_path: Path,
        new_track_id: str | None = None,
    ) -> ET.Element:
        """Create a new TRACK element with updated file location and properties"""
        # Create new track element with all original attributes
        new_track = ET.Element("TRACK", attrib=dict(original_track.attrib))

        # Assign new track ID if provided
        if new_track_id:
            new_track.set("TrackID", new_track_id)

        # Update location
        new_location = f"file://localhost{new_path.as_posix()}"
        new_track.set("Location", new_location)

        # Update Kind based on format
        if self.output_format == "mp3":
            new_track.set("Kind", "MP3 File")
            new_track.set("BitRate", "320")
        elif self.output_format == "flac":
            new_track.set("Kind", "FLAC File")
            # FLAC is lossless, so bitrate varies. Use approximate value for 48kHz/16-bit
            new_track.set("BitRate", "1411")  # Typical for 48kHz/16-bit FLAC
        elif self.output_format == "aiff":
            new_track.set("Kind", "AIFF File")
            new_track.set("BitRate", "2116")

        # Update Size if file exists
        if new_path.exists():
            new_track.set("Size", str(new_path.stat().st_size))

        # Copy all child elements (TEMPO, POSITION_MARK, etc.)
        for child in original_track:
            new_track.append(child)

        return new_track

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename by removing invalid characters"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")
        return filename[:200]  # Limit length

    def convert_playlist(
        self, playlist_name: str, output_dir: str
    ) -> tuple[bool, str | None, list[ET.Element]]:
        """
        Convert all tracks in a playlist and return track data for standalone XML
        Returns: (success, playlist_display_name, converted_tracks_with_new_ids)
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Find the playlist
        playlists = self.list_playlists()
        target_playlist = None

        for plist_path, plist_node, entries in playlists:
            if plist_path == playlist_name or plist_node.get("Name") == playlist_name:
                target_playlist = plist_node
                break

        if target_playlist is None:
            print(f"Playlist '{playlist_name}' not found!")
            return (False, None, [])

        print(f"\nConverting playlist: {playlist_name}")
        print(f"Output directory: {output_path}")
        print(f"Target format: {self.output_format.upper()}")
        print("-" * 60)

        # Get all tracks in the playlist
        track_keys = [track.get("Key") for track in target_playlist.findall("TRACK")]
        print(f"Found {len(track_keys)} tracks in playlist\n")

        # Convert tracks and assign new track IDs
        converted_tracks: list[ET.Element] = []

        for i, track_key in enumerate(track_keys, 1):
            print(f"[{i}/{len(track_keys)}] Processing track...")

            if track_key not in self.tracks_map:
                print(f"  ⚠ Track {track_key} not found in collection")
                continue

            original_track = self.tracks_map[track_key]

            if result := self.convert_track(original_track, output_path):
                new_path, _ = result

                # Assign new unique track ID
                new_track_id = str(self.new_track_id_counter)
                self.new_track_id_counter += 1

                # Create track element with new ID
                new_track_element = self._create_track_element(
                    original_track, new_path, new_track_id
                )
                converted_tracks.append(new_track_element)

        print(f"\n✓ Successfully converted {len(converted_tracks)}/{len(track_keys)} tracks")

        # Generate playlist display name
        playlist_display_name = f"{target_playlist.get('Name')} ({self.output_format.upper()})"

        return (len(converted_tracks) > 0, playlist_display_name, converted_tracks)

    def create_standalone_xml(self, playlist_name: str, converted_tracks: list[ET.Element]) -> None:
        """
        Create a standalone Rekordbox XML with only the converted tracks
        This XML can be safely imported into Rekordbox without modifying the original library
        """
        # Create root element
        new_root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")

        # Add PRODUCT node (Rekordbox version info)
        ET.SubElement(new_root, "PRODUCT", Name="rekordbox", Version="6.0.0", Company="Pioneer DJ")

        # Create COLLECTION with converted tracks
        collection = ET.SubElement(new_root, "COLLECTION", Entries=str(len(converted_tracks)))
        for track in converted_tracks:
            collection.append(track)

        # Create PLAYLISTS structure
        playlists_node = ET.SubElement(new_root, "PLAYLISTS")

        # Create ROOT node
        root_node = ET.SubElement(playlists_node, "NODE", Type="0", Name="ROOT", Count="1")

        # Create the playlist node
        playlist_node = ET.SubElement(
            root_node,
            "NODE",
            Name=playlist_name,
            Type="1",
            KeyType="0",
            Entries=str(len(converted_tracks)),
        )

        # Add track references to playlist
        for track in converted_tracks:
            track_id = track.get("TrackID")
            if track_id:
                ET.SubElement(playlist_node, "TRACK", Key=track_id)

        # Create new tree
        self.standalone_tree = ET.ElementTree(new_root)
        self.standalone_root = new_root

        print(f"✓ Created standalone XML with {len(converted_tracks)} tracks")
        print(f"✓ Playlist: {playlist_name}")

    def save_standalone_xml(self, output_path: str) -> Path:
        """Save the standalone XML file (does not modify original)"""
        if not hasattr(self, "standalone_tree") or self.standalone_tree is None:
            raise ValueError("No standalone XML created. Call create_standalone_xml() first.")

        output_file = Path(output_path)

        # Format and save
        self._indent_xml(self.standalone_root)
        self.standalone_tree.write(str(output_file), encoding="UTF-8", xml_declaration=True)
        print(f"✓ Saved standalone XML file: {output_file}")
        print("  You can now import this file into Rekordbox via: File > Import Collection")
        return output_file

    def _indent_xml(self, elem: ET.Element, level: int = 0) -> None:
        """Add pretty-printing indentation to XML"""
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


@app.command(name="models")
def list_cdj_models():
    """List all supported CDJ/XDJ models with format recommendations"""
    RekordboxPlaylistConverter.list_supported_cdj_models()


@app.command(name="list")
def list_playlists(
    xml_file: Annotated[Path, typer.Argument(help="Path to Rekordbox XML file", exists=True)],
):
    """List all playlists in a Rekordbox XML file"""
    try:
        converter = RekordboxPlaylistConverter(str(xml_file), "mp3")
        converter.load_xml()

        console.print("\n[bold cyan]Available playlists:[/bold cyan]")
        console.print("-" * 60)
        playlists = converter.list_playlists()
        for path, node, entries in playlists:
            console.print(f"  {path} [dim]({entries} tracks)[/dim]")
        console.print()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command(name="convert")
def convert_playlist(
    xml_file: Annotated[Path, typer.Argument(help="Path to Rekordbox XML file", exists=True)],
    playlist: Annotated[str, typer.Option("-p", "--playlist", help="Name of playlist to convert")],
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output directory for converted files")
    ],
    cdj_model: Annotated[
        str | None,
        typer.Option(
            "--cdj-model",
            help=(
                "Your CDJ/XDJ model (e.g., XDJ-RX2, CDJ-3000) - automatically selects best format"
            ),
        ),
    ] = None,
    format: Annotated[
        str | None,
        typer.Option(
            "-f",
            "--format",
            help=(
                "Output format (mp3, flac, aiff). If not specified, "
                "use --cdj-model for auto-selection"
            ),
        ),
    ] = None,
    output_xml: Annotated[
        Path | None,
        typer.Option(
            "--output-xml",
            help="Path for standalone XML file (default: saved in output directory)",
        ),
    ] = None,
):
    """
    Convert a Rekordbox playlist to MP3/FLAC/AIFF format

    Creates a NEW standalone XML file that can be safely imported into Rekordbox
    without modifying your original library. Converted tracks will have unique IDs
    starting from 1000000 to prevent conflicts.
    """
    try:
        # Determine output format
        output_format = "mp3"  # default
        if format:
            if format.lower() not in ["mp3", "flac", "aiff"]:
                console.print(
                    f"[bold red]Error:[/bold red] Invalid format '{format}'. "
                    "Choose from: mp3, flac, aiff"
                )
                raise typer.Exit(code=1)
            output_format = format.lower()
        elif cdj_model:
            # Auto-select format based on CDJ model
            recommended_format, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj(
                cdj_model
            )
            output_format = recommended_format
            console.print(f"\n🎛️  [bold]CDJ Model:[/bold] {cdj_model.upper()}")
            console.print(
                f"📀  [bold]Recommended format:[/bold] [green]{output_format.upper()}[/green]"
            )
            console.print(f"💡  {reason}\n")

        converter = RekordboxPlaylistConverter(str(xml_file), output_format)
        converter.load_xml()

        # Convert playlist and get track data
        success, playlist_name, converted_tracks = converter.convert_playlist(playlist, str(output))

        if success and playlist_name:
            # Create standalone XML with converted tracks
            converter.create_standalone_xml(playlist_name, converted_tracks)

            # Determine output XML path
            if output_xml:
                output_xml_path = output_xml
            else:
                # Default: save in output directory with descriptive name
                safe_name = converter._sanitize_filename(playlist_name)
                output_xml_path = output / f"{safe_name}.xml"

            # Save the standalone XML
            converter.save_standalone_xml(str(output_xml_path))

            console.print("\n" + "=" * 60)
            console.print("[bold green]✓ Conversion complete![/bold green]")
            console.print(f"  [cyan]Converted files:[/cyan] {output}")
            console.print(f"  [cyan]Standalone XML:[/cyan] {output_xml_path}")
            console.print("  [yellow]Original XML:[/yellow] NOT MODIFIED (safe!)")
        else:
            console.print("[bold red]Error:[/bold red] Conversion failed")
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback

        traceback.print_exc()
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
