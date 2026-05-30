"""Tests for the dry-run table renderer and `_format_quality`.

Both surface as user-facing CLI output. Renderer correctness matters
because dry-run is the audit/preview path -- if it misreports the plan,
the user can't trust the actual run that follows.
"""

from pathlib import Path

import pytest
from rich.console import Console

import converter as converter_module
from converter import Action, ConversionResult, OutputFormat, RekordboxPlaylistConverter

fmt_quality = RekordboxPlaylistConverter._format_quality


class TestFormatQuality:
    """`_format_quality(sample_rate, bit_depth)` -> e.g. '44.1k/16'."""

    @pytest.mark.parametrize(
        "sr, bd, expected",
        [
            (44100, 16, "44.1k/16"),
            (48000, 24, "48k/24"),
            (96000, 24, "96k/24"),
            (192000, 32, "192k/32"),
            (22050, 16, "22.05k/16"),  # half-rate is unusual but valid
        ],
    )
    def test_rate_and_depth(self, sr, bd, expected):
        assert fmt_quality(sr, bd) == expected

    def test_rate_only(self):
        # MP3 has no PCM depth axis -- show only the rate.
        assert fmt_quality(48000, None) == "48k"

    def test_unknown_rate(self):
        # ffprobe failed -> we show '?' rather than fabricating a value.
        assert fmt_quality(None, None) == "?"

    def test_unknown_rate_with_depth(self):
        # Shouldn't happen in practice but guards against future bugs.
        assert fmt_quality(None, 24) == "?/24"


class TestDryRunTable:
    """`_print_dry_run_table` renders to console -- we capture and inspect."""

    def _capture(self, results):
        """Run the renderer against a captured console; return the output."""
        # Replace the module-level console with a captured one for this call.
        original = converter_module.console
        captured = Console(record=True)
        converter_module.console = captured
        try:
            conv = RekordboxPlaylistConverter("dummy.xml", "mp3")
            conv._print_dry_run_table(results)
            return captured.export_text()
        finally:
            converter_module.console = original

    def test_empty_results_does_not_crash(self):
        output = self._capture([])
        # Table title still appears; just no rows.
        assert "Conversion plan" in output

    def test_renders_track_name_and_quality(self):
        result = ConversionResult(
            source_path=Path("/src/a.flac"),
            output_path=Path("/out/a.flac"),
            output_format=OutputFormat.FLAC,
            action=Action.ENCODED,
            source_sample_rate=96000,
            source_bit_depth=24,
            target_sample_rate=48000,
            target_bit_depth=24,
        )
        output = self._capture([result])
        assert "a.flac" in output
        assert "96k/24" in output
        assert "48k/24" in output

    def test_renders_action_verb(self):
        # Encode, copy, skip -- each gets its own verb in the table.
        results = [
            ConversionResult(
                source_path=Path("/s"),
                output_path=Path(f"/{name}.flac"),
                output_format=OutputFormat.FLAC,
                action=action,
                source_sample_rate=44100,
                source_bit_depth=16,
                target_sample_rate=44100,
                target_bit_depth=16,
            )
            for name, action in [
                ("encoded_one", Action.ENCODED),
                ("copied_one", Action.PASSTHROUGH),
                ("skipped_one", Action.SKIPPED),
            ]
        ]
        output = self._capture(results)
        assert "encode" in output
        assert "copy" in output
        assert "skip" in output
