"""Tests for the Typer CLI entry points (`models`, `list`, `convert`).

Uses `typer.testing.CliRunner` to invoke commands as the shell would. We
don't exercise the ffmpeg pipeline here -- the convert tests use --dry-run
so they probe-and-plan without writing files (or invoking ffmpeg).
"""

import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import app

# Rich's help formatter interleaves ANSI color codes inside flag names
# (e.g. `\x1b[1;36m-\x1b[0m\x1b[1;36m-dry-run\x1b[0m`), so a literal
# substring search for "--dry-run" fails in CI even though the flag is
# present. Strip ANSI before asserting on rendered output.
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _plain(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


runner = CliRunner()


FIXTURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.0.0" Company="Pioneer DJ"/>
  <COLLECTION Entries="1">
    <TRACK TrackID="1" Name="Demo" Artist="A" Location="file://localhost/nonexistent.flac"/>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="1">
      <NODE Type="1" Name="Demo Playlist" KeyType="0" Entries="1">
        <TRACK Key="1"/>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""


@pytest.fixture
def xml_path() -> Iterator[Path]:
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as tmp:
        tmp.write(FIXTURE_XML)
        path = Path(tmp.name)
    yield path
    path.unlink(missing_ok=True)


class TestModelsCommand:
    """`models` prints the table without arguments."""

    def test_models_runs_successfully(self):
        result = runner.invoke(app, ["models"])
        assert result.exit_code == 0

    def test_models_lists_known_decks(self):
        # Spot-check a few names from the database.
        result = runner.invoke(app, ["models"])
        assert "CDJ-3000" in result.stdout
        assert "XDJ-AZ" in result.stdout
        assert "CDJ-2000" in result.stdout


class TestListCommand:
    """`list` enumerates playlists in a rekordbox XML."""

    def test_list_missing_file_errors(self):
        result = runner.invoke(app, ["list", "/no/such/file.xml"])
        # typer's `exists=True` argument check exits with code 2 (usage error).
        assert result.exit_code != 0

    def test_list_shows_playlists(self, xml_path):
        result = runner.invoke(app, ["list", str(xml_path)])
        assert result.exit_code == 0
        assert "Demo Playlist" in _plain(result.stdout)


class TestConvertValidation:
    """Argument-validation paths in `convert` — exit before invoking ffmpeg."""

    def test_unknown_cdj_model_errors_even_with_format(self, xml_path, tmp_path):
        # The original silent-cap-fallback bug: with --format set, the old code
        # never validated --cdj-model. New code fails fast on a typo.
        result = runner.invoke(
            app,
            [
                "convert",
                str(xml_path),
                "-p",
                "Demo Playlist",
                "-o",
                str(tmp_path / "out"),
                "--cdj-model",
                "CDJ-9999",
                "--format",
                "mp3",
            ],
        )
        assert result.exit_code == 1
        assert "Unknown CDJ model" in _plain(result.stdout)

    def test_invalid_format_errors(self, xml_path, tmp_path):
        result = runner.invoke(
            app,
            [
                "convert",
                str(xml_path),
                "-p",
                "Demo Playlist",
                "-o",
                str(tmp_path / "out"),
                "--format",
                "wav",  # not in {mp3, flac, aiff}
            ],
        )
        assert result.exit_code == 1
        assert "Invalid format" in _plain(result.stdout)

    def test_missing_xml_file_errors(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "convert",
                "/no/such/file.xml",
                "-p",
                "Anything",
                "-o",
                str(tmp_path / "out"),
            ],
        )
        # typer's argument exists=True check.
        assert result.exit_code != 0


class TestConvertDryRun:
    """`--dry-run` probes and reports without writing files or running ffmpeg."""

    def test_dry_run_exits_cleanly_even_with_unfindable_sources(self, xml_path, tmp_path):
        # The fixture references file://localhost/nonexistent.flac on purpose.
        # Dry-run reports the plan but doesn't fail just because audio is gone.
        result = runner.invoke(
            app,
            [
                "convert",
                str(xml_path),
                "-p",
                "Demo Playlist",
                "-o",
                str(tmp_path / "out"),
                "--format",
                "mp3",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in _plain(result.stdout)

    def test_dry_run_does_not_create_output_directory(self, xml_path, tmp_path):
        out = tmp_path / "should_not_exist"
        runner.invoke(
            app,
            [
                "convert",
                str(xml_path),
                "-p",
                "Demo Playlist",
                "-o",
                str(out),
                "--format",
                "mp3",
                "--dry-run",
            ],
        )
        # Dry-run skips mkdir; the directory must not have been created.
        assert not out.exists()


class TestHelp:
    """Help text exposes the flags users actually need."""

    def test_convert_help_lists_new_flags(self):
        # If someone removes one of these by accident, the help test catches it.
        result = runner.invoke(app, ["convert", "--help"])
        assert result.exit_code == 0
        stdout = _plain(result.stdout)
        assert "--dry-run" in stdout
        assert "--jobs" in stdout
        assert "--manifest" in stdout
        assert "--cdj-model" in stdout
