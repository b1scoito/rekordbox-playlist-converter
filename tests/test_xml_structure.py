"""Tests for XML structure generation and validation"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from main import RekordboxPlaylistConverter


class TestStandaloneXMLGeneration:
    """Test standalone XML structure creation"""

    def setup_method(self):
        """Create a converter instance for testing"""
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_create_standalone_xml_structure(self):
        """Standalone XML should have correct root structure"""
        # Create mock converted tracks
        track1 = ET.Element("TRACK", TrackID="1000000", Name="Track 1", Artist="Artist 1")
        track2 = ET.Element("TRACK", TrackID="1000001", Name="Track 2", Artist="Artist 2")
        converted_tracks = [track1, track2]

        self.converter.create_standalone_xml("Test Playlist", converted_tracks)

        # Verify standalone tree was created
        assert hasattr(self.converter, "standalone_tree")
        assert hasattr(self.converter, "standalone_root")
        assert self.converter.standalone_root is not None

    def test_standalone_xml_root_element(self):
        """Root element should be DJ_PLAYLISTS with correct version"""
        track = ET.Element("TRACK", TrackID="1000000", Name="Test")
        self.converter.create_standalone_xml("Test", [track])

        root = self.converter.standalone_root
        assert root.tag == "DJ_PLAYLISTS"
        assert root.get("Version") == "1.0.0"

    def test_standalone_xml_has_product_node(self):
        """XML should contain PRODUCT node with Rekordbox info"""
        track = ET.Element("TRACK", TrackID="1000000", Name="Test")
        self.converter.create_standalone_xml("Test", [track])

        product = self.converter.standalone_root.find("PRODUCT")
        assert product is not None
        assert product.get("Name") == "rekordbox"
        assert product.get("Version") == "6.0.0"
        assert product.get("Company") == "Pioneer DJ"

    def test_standalone_xml_has_collection(self):
        """XML should contain COLLECTION with correct entry count"""
        track1 = ET.Element("TRACK", TrackID="1000000", Name="Track 1")
        track2 = ET.Element("TRACK", TrackID="1000001", Name="Track 2")
        converted_tracks = [track1, track2]

        self.converter.create_standalone_xml("Test", converted_tracks)

        collection = self.converter.standalone_root.find("COLLECTION")
        assert collection is not None
        assert collection.get("Entries") == "2"
        # All tracks should be in collection
        assert len(collection.findall("TRACK")) == 2

    def test_standalone_xml_has_playlists_structure(self):
        """XML should have correct PLAYLISTS → ROOT → NODE structure"""
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
        """Playlist TRACK elements should reference correct TrackIDs"""
        track1 = ET.Element("TRACK", TrackID="1000000")
        track2 = ET.Element("TRACK", TrackID="1000001")
        self.converter.create_standalone_xml("Test", [track1, track2])

        root_node = self.converter.standalone_root.find("PLAYLISTS/NODE[@Name='ROOT']")
        assert root_node is not None
        playlist_node = root_node.find("NODE[@Type='1']")
        assert playlist_node is not None
        track_refs = playlist_node.findall("TRACK")

        assert len(track_refs) == 2
        assert track_refs[0].get("Key") == "1000000"
        assert track_refs[1].get("Key") == "1000001"


class TestTrackElementCreation:
    """Test track element creation and metadata"""

    def setup_method(self):
        """Create a converter instance for testing"""
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_create_track_element_mp3(self):
        """MP3 track element should have correct Kind and BitRate"""
        original_track = ET.Element("TRACK", Name="Test Track", Artist="Artist")
        new_path = Path("/test/output/track.mp3")

        new_track = self.converter._create_track_element(original_track, new_path, "1000000")

        assert new_track.get("TrackID") == "1000000"
        assert new_track.get("Kind") == "MP3 File"
        assert new_track.get("BitRate") == "320"

    def test_create_track_element_flac(self):
        """FLAC track element should have correct Kind and BitRate"""
        converter = RekordboxPlaylistConverter("dummy.xml", "flac")
        original_track = ET.Element("TRACK", Name="Test Track", Artist="Artist")
        new_path = Path("/test/output/track.flac")

        new_track = converter._create_track_element(original_track, new_path, "1000000")

        assert new_track.get("TrackID") == "1000000"
        assert new_track.get("Kind") == "FLAC File"
        assert new_track.get("BitRate") == "1411"

    def test_create_track_element_aiff(self):
        """AIFF track element should have correct Kind and BitRate"""
        converter = RekordboxPlaylistConverter("dummy.xml", "aiff")
        original_track = ET.Element("TRACK", Name="Test Track", Artist="Artist")
        new_path = Path("/test/output/track.aiff")

        new_track = converter._create_track_element(original_track, new_path, "1000000")

        assert new_track.get("TrackID") == "1000000"
        assert new_track.get("Kind") == "AIFF File"
        assert new_track.get("BitRate") == "2116"

    def test_track_element_location_updated(self):
        """Track element should have updated Location attribute"""
        original_track = ET.Element("TRACK", Location="file://localhost/old/path/track.wav")
        new_path = Path("/new/path/track.mp3")

        new_track = self.converter._create_track_element(original_track, new_path)

        assert new_track.get("Location") == "file://localhost/new/path/track.mp3"

    def test_track_element_preserves_attributes(self):
        """Track element should preserve original attributes"""
        original_track = ET.Element(
            "TRACK",
            Name="Test Track",
            Artist="Test Artist",
            Album="Test Album",
            BPM="128.00",
            Genre="House",
        )
        new_path = Path("/output/track.mp3")

        new_track = self.converter._create_track_element(original_track, new_path)

        assert new_track.get("Name") == "Test Track"
        assert new_track.get("Artist") == "Test Artist"
        assert new_track.get("Album") == "Test Album"
        assert new_track.get("BPM") == "128.00"
        assert new_track.get("Genre") == "House"

    def test_track_element_preserves_child_elements(self):
        """Track element should preserve child elements (TEMPO, POSITION_MARK, etc.)"""
        original_track = ET.Element("TRACK", Name="Test")
        ET.SubElement(original_track, "TEMPO", Inizio="0.000", Bpm="128.00")
        ET.SubElement(original_track, "POSITION_MARK", Name="Cue", Start="1.000")

        new_path = Path("/output/track.mp3")
        new_track = self.converter._create_track_element(original_track, new_path)

        # Check child elements were copied
        assert len(new_track) == 2
        tempo_copy = new_track.find("TEMPO")
        position_mark_copy = new_track.find("POSITION_MARK")

        assert tempo_copy is not None
        assert tempo_copy.get("Bpm") == "128.00"
        assert position_mark_copy is not None
        assert position_mark_copy.get("Name") == "Cue"

    def test_track_element_without_track_id(self):
        """Track element without new_track_id should preserve original TrackID"""
        original_track = ET.Element("TRACK", TrackID="12345", Name="Test")
        new_path = Path("/output/track.mp3")

        new_track = self.converter._create_track_element(original_track, new_path)

        # Should preserve original TrackID when new_track_id not provided
        assert new_track.get("TrackID") == "12345"


class TestSaveStandaloneXML:
    """Test saving standalone XML"""

    def setup_method(self):
        """Create a converter instance for testing"""
        self.converter = RekordboxPlaylistConverter("dummy.xml", "mp3")

    def test_save_without_creating_raises_error(self):
        """Saving without creating standalone XML should raise ValueError"""
        with pytest.raises(ValueError, match="No standalone XML created"):
            self.converter.save_standalone_xml("/tmp/test.xml")

    def test_save_returns_path(self):
        """save_standalone_xml should return the output Path"""
        track = ET.Element("TRACK", TrackID="1000000", Name="Test")
        self.converter.create_standalone_xml("Test", [track])

        # Mock save (don't actually write file)
        # We can't test actual file writing without temp files, but we can test the return type
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            result = self.converter.save_standalone_xml(tmp.name)
            assert isinstance(result, Path)
            assert result.name.endswith(".xml")
            # Clean up
            Path(tmp.name).unlink()
