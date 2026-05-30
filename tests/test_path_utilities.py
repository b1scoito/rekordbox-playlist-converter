"""Tests for path utilities, filename sanitization, format settings, and IDs."""

from pathlib import Path

import pytest

from converter import FORMAT_SETTINGS, OutputFormat, RekordboxPlaylistConverter


class TestPathUtilities:
    """URL -> Path conversion and filename sanitization."""

    def setup_method(self):
        # Dummy XML path -- we only test utility methods.
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_url_to_path_basic(self):
        url = "file://localhost/Users/test/Music/track.mp3"
        assert self.converter.url_to_path(url) == Path("/Users/test/Music/track.mp3")

    def test_url_to_path_with_spaces(self):
        url = "file://localhost/Users/test/My%20Music/track.mp3"
        assert self.converter.url_to_path(url) == Path("/Users/test/My Music/track.mp3")

    def test_url_to_path_with_special_chars(self):
        url = "file://localhost/Users/test/Music%20%26%20Audio/track.mp3"
        assert self.converter.url_to_path(url) == Path("/Users/test/Music & Audio/track.mp3")

    def test_url_to_path_without_file_protocol(self):
        assert self.converter.url_to_path("http://example.com/track.mp3") is None

    def test_url_to_path_without_localhost(self):
        # rekordbox always emits the `localhost` form; bare `file:///` isn't supported.
        assert self.converter.url_to_path("file:///Users/test/track.mp3") is None

    def test_sanitize_filename_removes_invalid_chars(self):
        sanitized = self.converter._sanitize_filename('Artist - Track <Name> "Test"')
        assert "<" not in sanitized
        assert ">" not in sanitized
        assert '"' not in sanitized
        assert "_" in sanitized

    def test_sanitize_filename_removes_all_invalid_chars(self):
        sanitized = self.converter._sanitize_filename(r'Test<>:"/\|?*Track')
        for char in r'<>:"/\|?*':
            assert char not in sanitized

    def test_sanitize_filename_preserves_valid_chars(self):
        filename = "Artist - Track Name (Remix) [2024]"
        assert self.converter._sanitize_filename(filename) == filename

    def test_sanitize_filename_limits_length(self):
        assert len(self.converter._sanitize_filename("A" * 300)) == 200

    def test_sanitize_filename_unicode_characters(self):
        sanitized = self.converter._sanitize_filename("Artist - Track Ñame Café")
        assert "Ñ" in sanitized
        assert "é" in sanitized


class TestTrackIDManagement:
    """Sequential, monotonically-increasing track IDs that don't collide
    with the user's existing rekordbox library."""

    def test_default_starting_track_id(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        assert converter.starting_track_id == 1000000
        assert converter.new_track_id_counter == 1000000

    def test_custom_starting_track_id(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3", starting_track_id=2000000)
        assert converter.starting_track_id == 2000000
        assert converter.new_track_id_counter == 2000000

    def test_track_id_increments(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        initial = converter.new_track_id_counter
        converter.new_track_id_counter += 1
        assert converter.new_track_id_counter == initial + 1

    def test_track_id_uniqueness_across_conversions(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "mp3")
        seen: set[str] = set()
        for _ in range(100):
            track_id = str(converter.new_track_id_counter)
            assert track_id not in seen
            seen.add(track_id)
            converter.new_track_id_counter += 1


class TestFormatSettings:
    """Per-format ffmpeg defaults are typed and frozen on FORMAT_SETTINGS."""

    def test_mp3_format_settings(self):
        s = FORMAT_SETTINGS[OutputFormat.MP3]
        assert s.ext == "mp3"
        assert s.codec == "libmp3lame"
        assert s.bitrate == "320k"
        assert s.default_sample_rate == 44100

    def test_flac_format_settings(self):
        s = FORMAT_SETTINGS[OutputFormat.FLAC]
        assert s.ext == "flac"
        assert s.codec == "flac"
        assert s.bitrate is None  # lossless
        assert s.default_sample_rate == 48000
        assert s.compression_level == "5"

    def test_aiff_format_settings(self):
        s = FORMAT_SETTINGS[OutputFormat.AIFF]
        assert s.ext == "aiff"
        assert s.codec == "pcm_s16be"
        assert s.bitrate is None
        assert s.default_sample_rate == 44100

    def test_converter_format_settings_property(self):
        # Convenience accessor on the converter instance.
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        assert converter.format_settings is FORMAT_SETTINGS[OutputFormat.FLAC]

    def test_unsupported_format_raises_error(self):
        with pytest.raises(ValueError, match="Unsupported format"):
            RekordboxPlaylistConverter("dummy.xml", "wav")

    def test_format_case_insensitive(self):
        # OutputFormat is a StrEnum, so == "mp3" still holds.
        a = RekordboxPlaylistConverter("dummy.xml", "MP3")
        b = RekordboxPlaylistConverter("dummy.xml", "mp3")
        c = RekordboxPlaylistConverter("dummy.xml", "Mp3")
        assert a.output_format == b.output_format == c.output_format == OutputFormat.MP3
