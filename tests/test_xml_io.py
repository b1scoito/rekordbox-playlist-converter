"""Tests for `load_xml`, `list_playlists`, `_collect_playlists`, `url_to_path`.

Uses a tiny inline rekordbox-shaped XML fixture so we don't depend on a real
rekordbox export. Recursive folder/playlist discovery is the only non-trivial
bit -- the rest is straightforward XPath against ET trees.
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from converter import RekordboxPlaylistConverter

# Minimal rekordbox-XML-shaped fixture covering the cases the code paths
# actually touch: COLLECTION with TrackIDs, PLAYLISTS with a nested folder.
FIXTURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.0.0" Company="Pioneer DJ"/>
  <COLLECTION Entries="3">
    <TRACK TrackID="1" Name="Track One" Artist="A" Location="file://localhost/music/one.flac"/>
    <TRACK TrackID="2" Name="Track Two" Artist="B" Location="file://localhost/music/two.flac"/>
    <TRACK TrackID="3" Name="Track Three" Artist="C" Location="file://localhost/music/three.mp3"/>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="2">
      <NODE Type="1" Name="Top Level Playlist" KeyType="0" Entries="2">
        <TRACK Key="1"/>
        <TRACK Key="2"/>
      </NODE>
      <NODE Type="0" Name="Folder" Count="1">
        <NODE Type="1" Name="Nested Playlist" KeyType="0" Entries="1">
          <TRACK Key="3"/>
        </NODE>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""


@pytest.fixture
def xml_path() -> Iterator[Path]:
    """Write the fixture to a temp file and yield its path; clean up after."""
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as tmp:
        tmp.write(FIXTURE_XML)
        path = Path(tmp.name)
    yield path
    path.unlink(missing_ok=True)


class TestLoadXML:
    """`load_xml` populates `tracks_map` keyed by TrackID."""

    def test_populates_tracks_map(self, xml_path):
        converter = RekordboxPlaylistConverter(str(xml_path), "mp3")
        converter.load_xml()
        assert set(converter.tracks_map.keys()) == {"1", "2", "3"}

    def test_track_attributes_preserved(self, xml_path):
        converter = RekordboxPlaylistConverter(str(xml_path), "mp3")
        converter.load_xml()
        track1 = converter.tracks_map["1"]
        assert track1.get("Name") == "Track One"
        assert track1.get("Artist") == "A"
        assert track1.get("Location") == "file://localhost/music/one.flac"


class TestListPlaylists:
    """`list_playlists` walks the PLAYLISTS tree and yields (path, node, entries)."""

    def test_discovers_top_level_playlist(self, xml_path):
        converter = RekordboxPlaylistConverter(str(xml_path), "mp3")
        converter.load_xml()
        paths = [p for p, _node, _entries in converter.list_playlists()]
        assert "ROOT/Top Level Playlist" in paths

    def test_discovers_nested_playlist(self, xml_path):
        # The recursive descent into folders is the only logic that's easy
        # to get wrong; this nails the happy path.
        converter = RekordboxPlaylistConverter(str(xml_path), "mp3")
        converter.load_xml()
        paths = [p for p, _node, _entries in converter.list_playlists()]
        assert "ROOT/Folder/Nested Playlist" in paths

    def test_entries_count_reflects_xml_attribute(self, xml_path):
        converter = RekordboxPlaylistConverter(str(xml_path), "mp3")
        converter.load_xml()
        playlists = dict((p, e) for p, _n, e in converter.list_playlists())
        assert playlists["ROOT/Top Level Playlist"] == 2
        assert playlists["ROOT/Folder/Nested Playlist"] == 1

    def test_folder_nodes_are_not_in_playlist_list(self, xml_path):
        # Type="0" nodes are folders; only Type="1" should appear as playlists.
        converter = RekordboxPlaylistConverter(str(xml_path), "mp3")
        converter.load_xml()
        paths = [p for p, _node, _entries in converter.list_playlists()]
        assert "ROOT/Folder" not in paths

    def test_playlist_node_has_track_references(self, xml_path):
        converter = RekordboxPlaylistConverter(str(xml_path), "mp3")
        converter.load_xml()
        nodes = {p: n for p, n, _e in converter.list_playlists()}
        keys = [t.get("Key") for t in nodes["ROOT/Top Level Playlist"].findall("TRACK")]
        assert keys == ["1", "2"]


class TestEmptyXML:
    """A rekordbox export without playlists / collection shouldn't crash."""

    def test_load_xml_handles_no_collection(self):
        empty = '<?xml version="1.0"?><DJ_PLAYLISTS Version="1.0.0"></DJ_PLAYLISTS>'
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as tmp:
            tmp.write(empty)
            path = Path(tmp.name)
        try:
            converter = RekordboxPlaylistConverter(str(path), "mp3")
            converter.load_xml()
            assert converter.tracks_map == {}
            assert converter.list_playlists() == []
        finally:
            path.unlink(missing_ok=True)
