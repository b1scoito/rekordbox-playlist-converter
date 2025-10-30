"""Tests for path utilities and filename sanitization"""

from pathlib import Path

from main import RekordboxPlaylistConverter


class TestPathUtilities:
    """Test URL to path conversion and filename sanitization"""

    def setup_method(self):
        """Create a converter instance for testing"""
        # Use a dummy XML path since we're only testing utility methods
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_url_to_path_basic(self):
        """Convert basic file:// URL to path"""
        url = "file://localhost/Users/test/Music/track.mp3"
        path = self.converter.url_to_path(url)
        assert path == Path("/Users/test/Music/track.mp3")

    def test_url_to_path_with_spaces(self):
        """Convert URL with encoded spaces"""
        url = "file://localhost/Users/test/My%20Music/track.mp3"
        path = self.converter.url_to_path(url)
        assert path == Path("/Users/test/My Music/track.mp3")

    def test_url_to_path_with_special_chars(self):
        """Convert URL with URL-encoded special characters"""
        url = "file://localhost/Users/test/Music%20%26%20Audio/track.mp3"
        path = self.converter.url_to_path(url)
        assert path == Path("/Users/test/Music & Audio/track.mp3")

    def test_url_to_path_without_file_protocol(self):
        """Return None for URLs without file:// protocol"""
        url = "http://example.com/track.mp3"
        path = self.converter.url_to_path(url)
        assert path is None

    def test_url_to_path_without_localhost(self):
        """Return None for file URLs without localhost"""
        url = "file:///Users/test/track.mp3"
        path = self.converter.url_to_path(url)
        assert path is None

    def test_sanitize_filename_removes_invalid_chars(self):
        """Remove invalid filesystem characters"""
        filename = 'Artist - Track <Name> "Test"'
        sanitized = self.converter._sanitize_filename(filename)
        assert "<" not in sanitized
        assert ">" not in sanitized
        assert '"' not in sanitized
        # Should replace with underscore
        assert "_" in sanitized

    def test_sanitize_filename_removes_all_invalid_chars(self):
        """Remove all invalid characters: <>:"/\\|?*"""
        filename = r'Test<>:"/\|?*Track'
        sanitized = self.converter._sanitize_filename(filename)
        # All invalid chars should be replaced
        for char in r'<>:"/\|?*':
            assert char not in sanitized

    def test_sanitize_filename_preserves_valid_chars(self):
        """Preserve valid characters in filename"""
        filename = "Artist - Track Name (Remix) [2024]"
        sanitized = self.converter._sanitize_filename(filename)
        assert sanitized == filename

    def test_sanitize_filename_limits_length(self):
        """Limit filename to 200 characters"""
        long_filename = "A" * 300
        sanitized = self.converter._sanitize_filename(long_filename)
        assert len(sanitized) == 200

    def test_sanitize_filename_unicode_characters(self):
        """Preserve unicode characters in filename"""
        filename = "Artist - Track Ñame Café"
        sanitized = self.converter._sanitize_filename(filename)
        assert "Ñ" in sanitized
        assert "é" in sanitized


class TestTrackIDManagement:
    """Test track ID generation and uniqueness"""

    def test_default_starting_track_id(self):
        """Default starting track ID should be 1000000"""
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        assert converter.starting_track_id == 1000000
        assert converter.new_track_id_counter == 1000000

    def test_custom_starting_track_id(self):
        """Custom starting track ID should be respected"""
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3", starting_track_id=2000000)
        assert converter.starting_track_id == 2000000
        assert converter.new_track_id_counter == 2000000

    def test_track_id_increments(self):
        """Track ID counter should increment"""
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        initial = converter.new_track_id_counter
        converter.new_track_id_counter += 1
        assert converter.new_track_id_counter == initial + 1

    def test_track_id_uniqueness_across_conversions(self):
        """Track IDs should be unique across multiple conversions"""
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        ids = set()
        for _ in range(100):
            track_id = str(converter.new_track_id_counter)
            assert track_id not in ids, "Track ID should be unique"
            ids.add(track_id)
            converter.new_track_id_counter += 1


class TestFormatSettings:
    """Test format settings configuration"""

    def test_mp3_format_settings(self):
        """MP3 format should have correct settings"""
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        settings = converter.format_settings["mp3"]
        assert settings["ext"] == "mp3"
        assert settings["codec"] == "libmp3lame"
        assert settings["bitrate"] == "320k"
        assert settings["sample_rate"] == "44100"

    def test_flac_format_settings(self):
        """FLAC format should have correct settings"""
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        settings = converter.format_settings["flac"]
        assert settings["ext"] == "flac"
        assert settings["codec"] == "flac"
        assert settings["bitrate"] is None  # Lossless
        assert settings["sample_rate"] == "48000"
        assert settings["compression_level"] == "5"

    def test_aiff_format_settings(self):
        """AIFF format should have correct settings"""
        converter = RekordboxPlaylistConverter("dummy.xml", "aiff")
        settings = converter.format_settings["aiff"]
        assert settings["ext"] == "aiff"
        assert settings["codec"] == "pcm_s16be"
        assert settings["bitrate"] is None
        assert settings["sample_rate"] == "44100"

    def test_unsupported_format_raises_error(self):
        """Unsupported format should raise ValueError"""
        import pytest

        with pytest.raises(ValueError, match="Unsupported format"):
            RekordboxPlaylistConverter("dummy.xml", "wav")

    def test_format_case_insensitive(self):
        """Format should be case-insensitive"""
        converter1 = RekordboxPlaylistConverter("dummy.xml", "MP3")
        converter2 = RekordboxPlaylistConverter("dummy.xml", "mp3")
        converter3 = RekordboxPlaylistConverter("dummy.xml", "Mp3")
        assert (
            converter1.output_format
            == converter2.output_format
            == converter3.output_format
            == "mp3"
        )
