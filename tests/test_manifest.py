"""Tests for `write_manifest` -- JSON manifest of a conversion run.

The manifest is what makes runs diffable: source vs target rate/depth,
output bitrate, duration, action verb. A schema regression here would
silently break gig-prep auditing, so we round-trip the JSON and assert
on the structure.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

from converter import Action, ConversionResult, OutputFormat, RekordboxPlaylistConverter


def _result(action: Action = Action.ENCODED, **overrides: Any) -> ConversionResult:
    """Convenience: build a representative ConversionResult for the manifest."""
    base: dict[str, Any] = dict(
        source_path=Path("/src/song.flac"),
        output_path=Path("/out/song.flac"),
        output_format=OutputFormat.FLAC,
        action=action,
        source_sample_rate=96000,
        source_bit_depth=24,
        target_sample_rate=48000,
        target_bit_depth=24,
        output_bitrate_kbps=2304,
        output_size_bytes=12_000_000,
        duration_seconds=240.5,
    )
    base.update(overrides)
    return ConversionResult(**base)


class TestManifestSchema:
    """Top-level keys and per-track shape are stable, since downstream
    tooling (and future humans) consume them."""

    def test_top_level_keys(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "flac", cdj_model="CDJ-3000")
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            converter.write_manifest(path, "My Set", [_result()])
            payload = json.loads(path.read_text())
            assert payload["playlist"] == "My Set"
            assert payload["cdj_model"] == "CDJ-3000"
            assert payload["output_format"] == "flac"
            assert isinstance(payload["tracks"], list)
        finally:
            path.unlink(missing_ok=True)

    def test_track_entries_carry_quality_fields(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            converter.write_manifest(path, "Set", [_result()])
            track = json.loads(path.read_text())["tracks"][0]
            assert track["source_sample_rate"] == 96000
            assert track["source_bit_depth"] == 24
            assert track["target_sample_rate"] == 48000
            assert track["target_bit_depth"] == 24
            assert track["output_bitrate_kbps"] == 2304
            assert track["duration_seconds"] == 240.5
        finally:
            path.unlink(missing_ok=True)

    def test_paths_serialize_as_strings(self):
        # ConversionResult.source_path / output_path are pathlib.Path; JSON
        # needs strings. The writer explicitly converts.
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            converter.write_manifest(path, "Set", [_result()])
            track = json.loads(path.read_text())["tracks"][0]
            assert track["source_path"] == "/src/song.flac"
            assert track["output_path"] == "/out/song.flac"
        finally:
            path.unlink(missing_ok=True)

    def test_action_serializes_as_string(self):
        # Action is StrEnum -- json.dumps default=str renders the value.
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            converter.write_manifest(
                path,
                "Set",
                [
                    _result(action=Action.ENCODED),
                    _result(action=Action.PASSTHROUGH),
                    _result(action=Action.SKIPPED),
                ],
            )
            actions = [t["action"] for t in json.loads(path.read_text())["tracks"]]
            assert actions == ["encoded", "passthrough", "skipped"]
        finally:
            path.unlink(missing_ok=True)


class TestEmptyManifest:
    """Empty results still produces a valid (if uninteresting) manifest."""

    def test_no_tracks_still_writes_structure(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tmp:
            path = Path(tmp.name)
        try:
            converter.write_manifest(path, "Empty", [])
            payload = json.loads(path.read_text())
            assert payload["tracks"] == []
            assert payload["playlist"] == "Empty"
        finally:
            path.unlink(missing_ok=True)
