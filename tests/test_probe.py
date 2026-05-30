"""Tests for `quality.probe` -- the ffprobe wrapper.

We don't shell out to a real ffprobe; we patch subprocess.run to return
canned output so the parser can be exercised against every relevant
combination (lossy, lossless, missing fields, ffprobe absent).
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quality import probe, probe_audio_start_seconds


def _stdout(text: str) -> MagicMock:
    """Build a fake subprocess.run result with the given stdout."""
    result = MagicMock()
    result.stdout = text
    result.returncode = 0
    return result


class TestProbeParsing:
    """Happy path: ffprobe stdout -> tuple of typed fields."""

    @patch("quality.subprocess.run")
    def test_parses_full_lossless_output(self, mock_run):
        mock_run.return_value = _stdout(
            "codec_name=flac\n"
            "sample_rate=44100\n"
            "bits_per_raw_sample=16\n"
            "bit_rate=921600\n"
            "duration=180.5\n"
        )
        sr, bd, codec, bitrate, dur = probe(Path("/x.flac"))
        assert sr == 44100
        assert bd == 16
        assert codec == "flac"
        assert bitrate == 921600
        assert dur == 180.5

    @patch("quality.subprocess.run")
    def test_prefers_bits_per_raw_sample_over_bits_per_sample(self, mock_run):
        # FLAC containers report container-level depth (32) and raw depth (24);
        # only the raw value is the true PCM depth.
        mock_run.return_value = _stdout(
            "codec_name=flac\nsample_rate=96000\nbits_per_raw_sample=24\nbits_per_sample=32\n"
        )
        _sr, bd, _codec, _br, _dur = probe(Path("/x.flac"))
        assert bd == 24

    @patch("quality.subprocess.run")
    def test_falls_back_to_bits_per_sample_when_raw_missing(self, mock_run):
        # Some lossless containers only set bits_per_sample.
        mock_run.return_value = _stdout("codec_name=alac\nsample_rate=44100\nbits_per_sample=16\n")
        _sr, bd, _codec, _br, _dur = probe(Path("/x.m4a"))
        assert bd == 16

    @patch("quality.subprocess.run")
    def test_lossy_source_has_no_bit_depth(self, mock_run):
        # MP3 reports sample_rate + bit_rate but no bit depth -- expected None.
        mock_run.return_value = _stdout("codec_name=mp3\nsample_rate=44100\nbit_rate=320000\n")
        _sr, bd, codec, _br, _dur = probe(Path("/x.mp3"))
        assert bd is None
        assert codec == "mp3"

    @patch("quality.subprocess.run")
    def test_ignores_na_values(self, mock_run):
        # ffprobe writes 'N/A' for fields it can't determine; we must not
        # blow up trying to int('N/A').
        mock_run.return_value = _stdout(
            "codec_name=mp3\nsample_rate=44100\nbits_per_raw_sample=N/A\nbit_rate=N/A\n"
        )
        sr, bd, _codec, bitrate, _dur = probe(Path("/x.mp3"))
        assert sr == 44100
        assert bd is None
        assert bitrate is None


class TestProbeFailures:
    """Every probe failure mode returns all-None so callers fall back cleanly."""

    @patch("quality.subprocess.run", side_effect=FileNotFoundError())
    def test_ffprobe_missing_returns_all_none(self, _mock_run):
        # ffprobe isn't installed -> caller falls back to passthrough/defaults.
        result = probe(Path("/x.flac"))
        assert result == (None, None, None, None, None)

    @patch("quality.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 30))
    def test_timeout_returns_all_none(self, _mock_run):
        # Pathological file hanging ffprobe -> bounded wait, no exception out.
        result = probe(Path("/x.flac"))
        assert result == (None, None, None, None, None)

    @patch("quality.subprocess.run", side_effect=OSError("permission denied"))
    def test_oserror_returns_all_none(self, _mock_run):
        result = probe(Path("/x.flac"))
        assert result == (None, None, None, None, None)


class TestProbeAudioStartSeconds:
    """`probe_audio_start_seconds` surfaces libmp3lame's encoder delay so the
    converter can shift the rekordbox grid to match. Returns 0.0 for every
    failure mode (no delay assumed) so callers don't have to handle None."""

    @patch("quality.subprocess.run")
    def test_parses_libmp3lame_encoder_delay(self, mock_run):
        # The exact value the user reported on their FLAC->MP3 output:
        # ~1152-sample libmp3lame delay at 44.1 kHz.
        mock_run.return_value = MagicMock(stdout="0.025057\n", returncode=0)
        assert probe_audio_start_seconds(Path("/x.mp3")) == pytest.approx(0.025057)

    @patch("quality.subprocess.run")
    def test_lossless_format_reports_zero(self, mock_run):
        mock_run.return_value = MagicMock(stdout="0.000000\n", returncode=0)
        assert probe_audio_start_seconds(Path("/x.flac")) == 0.0

    @patch("quality.subprocess.run")
    def test_na_value_returns_zero(self, mock_run):
        mock_run.return_value = MagicMock(stdout="N/A\n", returncode=0)
        assert probe_audio_start_seconds(Path("/x.mp3")) == 0.0

    @patch("quality.subprocess.run")
    def test_empty_output_returns_zero(self, mock_run):
        mock_run.return_value = MagicMock(stdout="\n", returncode=0)
        assert probe_audio_start_seconds(Path("/x.mp3")) == 0.0

    @patch("quality.subprocess.run")
    def test_unparseable_output_returns_zero(self, mock_run):
        # ffprobe returning garbage shouldn't blow up the conversion.
        mock_run.return_value = MagicMock(stdout="not-a-float\n", returncode=0)
        assert probe_audio_start_seconds(Path("/x.mp3")) == 0.0

    @patch("quality.subprocess.run")
    def test_negative_value_clamped_to_zero(self, mock_run):
        # Defensive: a negative PTS shouldn't shift the grid backwards.
        mock_run.return_value = MagicMock(stdout="-0.5\n", returncode=0)
        assert probe_audio_start_seconds(Path("/x.mp3")) == 0.0

    @patch("quality.subprocess.run", side_effect=FileNotFoundError())
    def test_ffprobe_missing_returns_zero(self, _mock_run):
        assert probe_audio_start_seconds(Path("/x.mp3")) == 0.0

    @patch("quality.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 30))
    def test_timeout_returns_zero(self, _mock_run):
        assert probe_audio_start_seconds(Path("/x.mp3")) == 0.0
