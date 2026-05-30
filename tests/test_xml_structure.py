"""Tests for standalone XML generation and track-element construction."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from converter import (
    Action,
    ConversionResult,
    OutputFormat,
    RekordboxPlaylistConverter,
)


def _result(
    fmt: OutputFormat,
    output_path: Path,
    *,
    bitrate_kbps: int | None = None,
    sample_rate: int | None = None,
    bit_depth: int | None = None,
    size_bytes: int | None = None,
) -> ConversionResult:
    """Convenience: build a minimal ConversionResult for XML-building tests."""
    return ConversionResult(
        source_path=Path("/dummy/source"),
        output_path=output_path,
        output_format=fmt,
        action=Action.ENCODED,
        target_sample_rate=sample_rate,
        target_bit_depth=bit_depth,
        output_bitrate_kbps=bitrate_kbps,
        output_size_bytes=size_bytes,
    )


class TestStandaloneXMLGeneration:
    """Whole-tree shape: DJ_PLAYLISTS > PRODUCT, COLLECTION, PLAYLISTS."""

    def setup_method(self):
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_create_standalone_xml_structure(self):
        track1 = ET.Element("TRACK", TrackID="1000000", Name="Track 1", Artist="Artist 1")
        track2 = ET.Element("TRACK", TrackID="1000001", Name="Track 2", Artist="Artist 2")
        self.converter.create_standalone_xml("Test Playlist", [track1, track2])
        assert hasattr(self.converter, "standalone_tree")
        assert hasattr(self.converter, "standalone_root")
        assert self.converter.standalone_root is not None

    def test_standalone_xml_root_element(self):
        track = ET.Element("TRACK", TrackID="1000000", Name="Test")
        self.converter.create_standalone_xml("Test", [track])
        root = self.converter.standalone_root
        assert root.tag == "DJ_PLAYLISTS"
        assert root.get("Version") == "1.0.0"

    def test_standalone_xml_has_product_node(self):
        track = ET.Element("TRACK", TrackID="1000000", Name="Test")
        self.converter.create_standalone_xml("Test", [track])
        product = self.converter.standalone_root.find("PRODUCT")
        assert product is not None
        assert product.get("Name") == "rekordbox"
        assert product.get("Version") == "6.0.0"
        assert product.get("Company") == "Pioneer DJ"

    def test_standalone_xml_has_collection(self):
        track1 = ET.Element("TRACK", TrackID="1000000", Name="Track 1")
        track2 = ET.Element("TRACK", TrackID="1000001", Name="Track 2")
        self.converter.create_standalone_xml("Test", [track1, track2])
        collection = self.converter.standalone_root.find("COLLECTION")
        assert collection is not None
        assert collection.get("Entries") == "2"
        assert len(collection.findall("TRACK")) == 2

    def test_standalone_xml_has_playlists_structure(self):
        track = ET.Element("TRACK", TrackID="1000000", Name="Test")
        self.converter.create_standalone_xml("My Playlist", [track])
        playlists = self.converter.standalone_root.find("PLAYLISTS")
        assert playlists is not None
        root_node = playlists.find("NODE[@Name='ROOT']")
        assert root_node is not None
        assert root_node.get("Type") == "0"
        assert root_node.get("Count") == "1"
        playlist_node = root_node.find("NODE[@Name='My Playlist']")
        assert playlist_node is not None
        assert playlist_node.get("Type") == "1"
        assert playlist_node.get("Entries") == "1"

    def test_playlist_tracks_reference_correct_ids(self):
        track1 = ET.Element("TRACK", TrackID="1000000")
        track2 = ET.Element("TRACK", TrackID="1000001")
        self.converter.create_standalone_xml("Test", [track1, track2])
        root_node = self.converter.standalone_root.find("PLAYLISTS/NODE[@Name='ROOT']")
        assert root_node is not None
        playlist_node = root_node.find("NODE[@Type='1']")
        assert playlist_node is not None
        refs = playlist_node.findall("TRACK")
        assert len(refs) == 2
        assert refs[0].get("Key") == "1000000"
        assert refs[1].get("Key") == "1000001"


class TestTrackElementCreation:
    """Per-track element building: honest metadata from ConversionResult."""

    def setup_method(self):
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_create_track_element_mp3(self):
        original = ET.Element("TRACK", Name="Test", Artist="Artist")
        result = _result(
            OutputFormat.MP3,
            Path("/test/output/track.mp3"),
            bitrate_kbps=320,
            sample_rate=44100,
        )
        new_track = self.converter._create_track_element(original, "1000000", result)
        assert new_track.get("TrackID") == "1000000"
        assert new_track.get("Kind") == "MP3 File"
        assert new_track.get("BitRate") == "320"  # honest, from result
        assert new_track.get("SampleRate") == "44100"

    def test_create_track_element_flac(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        original = ET.Element("TRACK", Name="Test", Artist="Artist")
        # Hi-res FLAC: 96k/24/2ch lossless ~= 4608 kbps -- the honest value.
        result = _result(
            OutputFormat.FLAC,
            Path("/test/output/track.flac"),
            bitrate_kbps=4608,
            sample_rate=96000,
            bit_depth=24,
        )
        new_track = converter._create_track_element(original, "1000000", result)
        assert new_track.get("TrackID") == "1000000"
        assert new_track.get("Kind") == "FLAC File"
        assert new_track.get("BitRate") == "4608"
        assert new_track.get("SampleRate") == "96000"

    def test_create_track_element_flac_derives_bitrate_when_unprobed(self):
        # Probe couldn't read bitrate -> XML derives from rate * depth * 2ch / 1000.
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        original = ET.Element("TRACK", Name="Test")
        result = _result(
            OutputFormat.FLAC,
            Path("/x.flac"),
            bitrate_kbps=None,
            sample_rate=44100,
            bit_depth=16,
        )
        new_track = converter._create_track_element(original, None, result)
        # 44100 * 16 * 2 / 1000 = 1411
        assert new_track.get("BitRate") == "1411"

    def test_create_track_element_aiff(self):
        converter = RekordboxPlaylistConverter("dummy.xml", "aiff")
        original = ET.Element("TRACK", Name="Test", Artist="Artist")
        result = _result(
            OutputFormat.AIFF,
            Path("/test/output/track.aiff"),
            bitrate_kbps=1411,
            sample_rate=44100,
            bit_depth=16,
        )
        new_track = converter._create_track_element(original, "1000000", result)
        assert new_track.get("TrackID") == "1000000"
        assert new_track.get("Kind") == "AIFF File"
        assert new_track.get("BitRate") == "1411"
        assert new_track.get("SampleRate") == "44100"

    def test_track_element_location_updated(self):
        original = ET.Element("TRACK", Location="file://localhost/old/path/track.wav")
        result = _result(OutputFormat.MP3, Path("/new/path/track.mp3"))
        new_track = self.converter._create_track_element(original, None, result)
        assert new_track.get("Location") == "file://localhost/new/path/track.mp3"

    def test_track_element_preserves_attributes(self):
        # Every rekordbox attribute that isn't explicitly overridden carries.
        original = ET.Element(
            "TRACK",
            Name="Test Track",
            Artist="Test Artist",
            Album="Test Album",
            BPM="128.00",
            Genre="House",
        )
        result = _result(OutputFormat.MP3, Path("/output/track.mp3"))
        new_track = self.converter._create_track_element(original, None, result)
        assert new_track.get("Name") == "Test Track"
        assert new_track.get("Artist") == "Test Artist"
        assert new_track.get("Album") == "Test Album"
        assert new_track.get("BPM") == "128.00"
        assert new_track.get("Genre") == "House"

    def test_track_element_preserves_child_elements(self):
        # TEMPO (beatgrid) and POSITION_MARK (cues) must travel unchanged.
        original = ET.Element("TRACK", Name="Test")
        ET.SubElement(original, "TEMPO", Inizio="0.000", Bpm="128.00")
        ET.SubElement(original, "POSITION_MARK", Name="Cue", Start="1.000")
        result = _result(OutputFormat.MP3, Path("/output/track.mp3"))
        new_track = self.converter._create_track_element(original, None, result)
        assert len(new_track) == 2
        tempo_copy = new_track.find("TEMPO")
        position_mark_copy = new_track.find("POSITION_MARK")
        assert tempo_copy is not None
        assert tempo_copy.get("Bpm") == "128.00"
        assert position_mark_copy is not None
        assert position_mark_copy.get("Name") == "Cue"

    def test_track_element_without_track_id_preserves_original(self):
        original = ET.Element("TRACK", TrackID="12345", Name="Test")
        result = _result(OutputFormat.MP3, Path("/output/track.mp3"))
        new_track = self.converter._create_track_element(original, None, result)
        # Passing None means: don't override; keep the original.
        assert new_track.get("TrackID") == "12345"

    def test_track_element_writes_output_size(self):
        original = ET.Element("TRACK", Name="Test")
        result = _result(OutputFormat.MP3, Path("/output/track.mp3"), size_bytes=8_000_000)
        new_track = self.converter._create_track_element(original, None, result)
        assert new_track.get("Size") == "8000000"


class TestSaveStandaloneXML:
    """Persistence: writing the standalone XML to disk."""

    def setup_method(self):
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_save_without_creating_raises_error(self):
        with pytest.raises(ValueError, match="No standalone XML created"):
            self.converter.save_standalone_xml("/tmp/test.xml")

    def test_save_returns_path(self):
        track = ET.Element("TRACK", TrackID="1000000", Name="Test")
        self.converter.create_standalone_xml("Test", [track])
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            result = self.converter.save_standalone_xml(tmp.name)
            assert isinstance(result, Path)
            assert result.name.endswith(".xml")
            Path(tmp.name).unlink()
