"""Tests for CDJ model detection and format-recommendation logic."""

import pytest

from models import CDJ_MODELS, get_recommended_format_for_cdj


class TestCDJModelDetection:
    """The recommend logic is a pure function on the CDJ_MODELS table."""

    def test_cdj_3000_recommends_flac(self):
        fmt, reason = get_recommended_format_for_cdj("CDJ-3000")
        assert fmt == "flac"
        assert "96kHz/24-bit" in reason
        assert "lossless" in reason.lower()

    def test_cdj_2000nxs2_recommends_flac(self):
        fmt, reason = get_recommended_format_for_cdj("CDJ-2000NXS2")
        assert fmt == "flac"
        assert "96kHz/24-bit" in reason

    def test_opus_quad_recommends_flac(self):
        fmt, reason = get_recommended_format_for_cdj("OPUS-QUAD")
        assert fmt == "flac"
        assert "96kHz/24-bit" in reason

    def test_xdj_rx3_recommends_flac(self):
        fmt, reason = get_recommended_format_for_cdj("XDJ-RX3")
        assert fmt == "flac"
        assert "48kHz/24-bit" in reason

    def test_xdj_1000mk2_recommends_flac(self):
        fmt, reason = get_recommended_format_for_cdj("XDJ-1000MK2")
        assert fmt == "flac"
        assert "48kHz/24-bit" in reason

    def test_xdj_rx2_recommends_mp3(self):
        fmt, reason = get_recommended_format_for_cdj("XDJ-RX2")
        assert fmt == "mp3"
        assert "320kbps" in reason
        assert "compatibility" in reason.lower()

    def test_xdj_rr_recommends_mp3(self):
        fmt, reason = get_recommended_format_for_cdj("XDJ-RR")
        assert fmt == "mp3"
        assert "320kbps" in reason

    def test_cdj_2000nxs_recommends_mp3(self):
        # CDJ-2000NXS carries a `notes` field about WAV/AIFF -- should surface.
        fmt, reason = get_recommended_format_for_cdj("CDJ-2000NXS")
        assert fmt == "mp3"
        assert "320kbps" in reason
        assert "Note:" in reason or "compatibility" in reason.lower()

    def test_cdj_900_recommends_mp3(self):
        fmt, reason = get_recommended_format_for_cdj("CDJ-900")
        assert fmt == "mp3"
        assert "320kbps" in reason

    def test_xdj_1000_recommends_mp3(self):
        fmt, reason = get_recommended_format_for_cdj("XDJ-1000")
        assert fmt == "mp3"
        assert "320kbps" in reason

    def test_case_insensitive_model_name(self):
        # The function uppercases internally; any casing should resolve.
        fmt1, _ = get_recommended_format_for_cdj("cdj-3000")
        fmt2, _ = get_recommended_format_for_cdj("CDJ-3000")
        fmt3, _ = get_recommended_format_for_cdj("CdJ-3000")
        assert fmt1 == fmt2 == fmt3 == "flac"

    def test_invalid_model_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown CDJ model"):
            get_recommended_format_for_cdj("INVALID-MODEL")

    def test_invalid_model_lists_available_models(self):
        with pytest.raises(ValueError, match="Available models"):
            get_recommended_format_for_cdj("XDJ-9999")

    def test_xdj_xz_has_flac_support(self):
        fmt, reason = get_recommended_format_for_cdj("XDJ-XZ")
        assert fmt == "flac"
        assert "48kHz/24-bit" in reason

    def test_all_models_return_valid_format(self):
        # Sanity: every entry in the database produces something we can encode.
        valid_formats = {"mp3", "flac", "aiff"}
        for model in CDJ_MODELS:
            fmt, reason = get_recommended_format_for_cdj(model)
            assert fmt in valid_formats
            assert isinstance(reason, str)
            assert len(reason) > 0
