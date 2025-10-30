"""Tests for CDJ model detection and format selection logic"""

import pytest

from main import RekordboxPlaylistConverter


class TestCDJModelDetection:
    """Test CDJ/XDJ model detection and format recommendations"""

    def test_cdj_3000_recommends_flac(self):
        """CDJ-3000 should recommend FLAC with 96kHz/24-bit support"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("CDJ-3000")
        assert fmt == "flac"
        assert "96kHz/24-bit" in reason
        assert "lossless" in reason.lower()

    def test_cdj_2000nxs2_recommends_flac(self):
        """CDJ-2000NXS2 should recommend FLAC with 96kHz/24-bit support"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("CDJ-2000NXS2")
        assert fmt == "flac"
        assert "96kHz/24-bit" in reason

    def test_opus_quad_recommends_flac(self):
        """OPUS-QUAD should recommend FLAC with 96kHz/24-bit support"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("OPUS-QUAD")
        assert fmt == "flac"
        assert "96kHz/24-bit" in reason

    def test_xdj_rx3_recommends_flac(self):
        """XDJ-RX3 should recommend FLAC with 48kHz/24-bit support"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("XDJ-RX3")
        assert fmt == "flac"
        assert "48kHz/24-bit" in reason

    def test_xdj_1000mk2_recommends_flac(self):
        """XDJ-1000MK2 should recommend FLAC with 48kHz/24-bit support"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("XDJ-1000MK2")
        assert fmt == "flac"
        assert "48kHz/24-bit" in reason

    def test_xdj_rx2_recommends_mp3(self):
        """XDJ-RX2 should recommend MP3 320kbps (no FLAC support)"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("XDJ-RX2")
        assert fmt == "mp3"
        assert "320kbps" in reason
        assert "compatibility" in reason.lower()

    def test_xdj_rr_recommends_mp3(self):
        """XDJ-RR should recommend MP3 320kbps (no FLAC support)"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("XDJ-RR")
        assert fmt == "mp3"
        assert "320kbps" in reason

    def test_cdj_2000nxs_recommends_mp3(self):
        """CDJ-2000NXS should recommend MP3 due to WAV/AIFF issues"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("CDJ-2000NXS")
        assert fmt == "mp3"
        assert "320kbps" in reason
        # Should mention WAV/AIFF compatibility issues
        assert "Note:" in reason or "compatibility" in reason.lower()

    def test_cdj_900_recommends_mp3(self):
        """CDJ-900 should recommend MP3 320kbps"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("CDJ-900")
        assert fmt == "mp3"
        assert "320kbps" in reason

    def test_xdj_1000_recommends_mp3(self):
        """XDJ-1000 should recommend MP3 320kbps (no FLAC support)"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("XDJ-1000")
        assert fmt == "mp3"
        assert "320kbps" in reason

    def test_case_insensitive_model_name(self):
        """Model names should be case-insensitive"""
        fmt1, _ = RekordboxPlaylistConverter.get_recommended_format_for_cdj("cdj-3000")
        fmt2, _ = RekordboxPlaylistConverter.get_recommended_format_for_cdj("CDJ-3000")
        fmt3, _ = RekordboxPlaylistConverter.get_recommended_format_for_cdj("CdJ-3000")
        assert fmt1 == fmt2 == fmt3 == "flac"

    def test_invalid_model_raises_value_error(self):
        """Unknown CDJ model should raise ValueError"""
        with pytest.raises(ValueError, match="Unknown CDJ model"):
            RekordboxPlaylistConverter.get_recommended_format_for_cdj("INVALID-MODEL")

    def test_invalid_model_lists_available_models(self):
        """Error message should list available models"""
        with pytest.raises(ValueError, match="Available models"):
            RekordboxPlaylistConverter.get_recommended_format_for_cdj("XDJ-9999")

    def test_xdj_xz_has_flac_support(self):
        """XDJ-XZ should recommend FLAC (added in FW update)"""
        fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj("XDJ-XZ")
        assert fmt == "flac"
        assert "48kHz/24-bit" in reason

    def test_all_models_return_valid_format(self):
        """All models in database should return a valid format"""
        from main import CDJ_MODELS

        valid_formats = {"mp3", "flac", "aiff"}
        for model in CDJ_MODELS.keys():
            fmt, reason = RekordboxPlaylistConverter.get_recommended_format_for_cdj(model)
            assert fmt in valid_formats
            assert isinstance(reason, str)
            assert len(reason) > 0
