# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Rekordbox playlist converter that converts tracks from Rekordbox playlists to various formats (MP3, FLAC, AIFF) optimized for Pioneer DJ CDJ/XDJ equipment. The tool creates a **standalone, importable XML file** that doesn't modify the user's original Rekordbox database.

## Core Architecture

### Module Layout

The codebase is split into small, single-purpose modules. Each leans on the next in a clean dependency line: `quality` and `models` are pure; `converter` builds on them; `cli` builds on `converter`; `main.py` is just the entry point.

- `_console.py` — Shared `rich.console.Console` instance imported wherever output is printed.
- `models.py` — `CDJ_MODELS` data + `get_recommended_format_for_cdj` (pure, no I/O, no Rich).
- `quality.py` — Pure quality-decision functions and the ffprobe wrapper: `parse_max_quality`, `plan_conversion`, `can_passthrough`, `existing_matches_plan`, `probe`. Safety-critical; isolated so it can be tested without touching the rest of the system.
- `converter.py` — `RekordboxPlaylistConverter` class plus `OutputFormat`/`Action` StrEnums, `FormatSettings` and `ConversionResult` dataclasses, and the `FORMAT_SETTINGS` registry. Orchestrates ffmpeg, XML I/O, and the JSON manifest.
- `cli.py` — Typer commands (`models`, `list`, `convert`) and the model-table renderer.
- `main.py` — Thin shim: `from cli import app; if __name__ == "__main__": app()`. Exists only to satisfy `[project.scripts] rekordbox-converter = "main:app"` in pyproject.

### Critical Design Principles

1. **Standalone XML Generation**: Never modify the original Rekordbox XML. Always create a new, independent XML file with:
   - Unique track IDs starting from 1,000,000 (configurable via `starting_track_id`)
   - Only converted tracks (not the entire collection)
   - Valid Rekordbox XML structure: `DJ_PLAYLISTS` → `PRODUCT` → `COLLECTION` → `PLAYLISTS`

2. **Quality follows source, capped to deck**: The conversion never upsamples. Source rate/bit depth is probed via ffprobe; the planner steps quality down only when the deck cap or codec ceiling demands it. See `quality.plan_conversion`. This is the project's safety-critical invariant.

3. **Atomic writes**: ffmpeg writes to a sibling `.<name>.part.<ext>` temp file and only renames into place on success. Real extension stays last so ffmpeg can infer the muxer. Interrupted runs never leave truncated outputs that look complete.

4. **Stale-output reuse**: When the output file already exists, we probe it and reuse only if its rate/depth matches what we'd produce now (`quality.existing_matches_plan`). Changing the deck or format between runs forces a re-encode.

5. **Same-format passthrough**: When the source codec matches the output format and quality fits the caps (`quality.can_passthrough`), ffmpeg uses `-c:a copy` instead of full re-encode. No quality loss, much faster.

6. **Cover-art passthrough**: MP3/FLAC carry the source's attached picture via `-map 0:v? -c:v copy -disposition:v attached_pic`. AIFF can't embed pictures, so it stays audio-only.

7. **Honest XML metadata**: `_create_track_element` writes `BitRate`/`SampleRate`/`Size` based on probing the *encoded* output, not hardcoded values. Manifest JSON does the same.

## Development Commands

### Setup
```bash
uv sync                       # Install dependencies
uv run pre-commit install     # Install git hooks
```

### Linting and Type Checking
```bash
uv run ruff check .           # Lint
uv run ruff format .          # Format
uv run pyright .              # Type check
```

### Testing
```bash
# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_quality_capping.py -v

# Run a specific test
uv run pytest tests/test_cdj_detection.py::TestCDJModelDetection::test_cdj_3000_recommends_flac -v

# Coverage
uv run pytest tests/ --cov=. --cov-report=term-missing
```

### Running the Tool (Development)
```bash
# Using uv (recommended during development)
uv run python main.py models
uv run python main.py list rekordbox.xml
uv run python main.py convert rekordbox.xml -p "Playlist" -o ./output --cdj-model XDJ-RX2

# Plan-only (no files written, prints conversion plan table)
uv run python main.py convert rekordbox.xml -p "Playlist" -o ./out --cdj-model CDJ-3000 --dry-run

# Tune parallelism (default: cpu_count; 1 disables threads)
uv run python main.py convert rekordbox.xml -p "Playlist" -o ./out -j 4

# After installation (production)
rekordbox-converter convert rekordbox.xml -p "Playlist" -o ./output --cdj-model CDJ-3000
```

## Installation Methods

### From Source (Development)
```bash
git clone <repo>
cd rekordbox-playlist-converter
uv sync
```

### As Package (Production)
```bash
pip install rekordbox-playlist-converter
# Then use: rekordbox-converter <command>
```

### System Requirements
- Python 3.11+ (uses `StrEnum`, `assert_never`, `match`/`case`)
- ffmpeg + ffprobe on PATH (system dependency, not in pyproject.toml)

## Type System Requirements

- Python 3.11+ (`list[...]`, `dict[...]`, `X | None`, `StrEnum`, `assert_never`).
- All public methods carry return-type annotations.
- `converter.py` uses `from __future__ import annotations` because `ET.ElementTree[Any]` isn't subscriptable at runtime; PEP 563 makes annotations lazy.
- `match` blocks on `OutputFormat` end with `case _: assert_never(self.output_format)` so pyright enforces exhaustiveness.

## Adding a New CDJ/XDJ Model

Add an entry to `models.CDJ_MODELS`:
- Required: `year`, `formats` (list), `max_quality` (dict mapping format -> `"<kHz>kHz/<bits>-bit"`), `recommended` (`"flac"` or `"mp3"`).
- Optional: `notes` (str) — surfaces in the CLI table and recommendation reason.

Recommended format:
- `"flac"` for models with FLAC support (typically ≥2016).
- `"mp3"` for older models or those with WAV/AIFF compatibility issues.

The `max_quality` strings are parsed by `quality.parse_max_quality` -> `(sample_rate_hz, bit_depth)`. Either component may be absent.

## XML Metadata Handling

`converter._create_track_element` copies the full attribute dict and every child element of the original `TRACK`, so all rekordbox metadata (artist/title/album/genre/key/BPM/rating/colour/comments) plus **all `TEMPO` (beatgrid) and `POSITION_MARK` (hot + memory cues with colors/labels)** carry into the standalone XML unchanged. Do not refactor that copy away.

Attributes overridden after the copy:
- `TrackID` (if a new ID is provided)
- `Location` (rebuilt as `file://localhost<output_path>`)
- `Kind` (per format: "MP3 File" / "FLAC File" / "AIFF File")
- `BitRate`, `SampleRate`, `Size` (from probing the encoded output via `quality.probe`)

## External Dependencies

- **ffmpeg + ffprobe**: Required for probing and conversion (system dependency).
- Codecs: MP3 (libmp3lame), FLAC (flac), AIFF (pcm_s16be / pcm_s24be).
- Tool fails gracefully (returns None / re-encodes) if ffprobe or ffmpeg isn't available.

## Key Public Surface

- `models.get_recommended_format_for_cdj(model)` -> `(format, reason)`. Raises `ValueError` on unknown model so the CLI fails fast on typos.
- `quality.plan_conversion(format, source_sr, source_bd, cap_sr, cap_bd)` -> `(target_sr, target_bd)`. Pure.
- `quality.probe(path)` -> `(sample_rate, bit_depth, codec_name, bitrate_bps, duration_seconds)`. Wraps ffprobe with a timeout.
- `converter.RekordboxPlaylistConverter.convert_playlist(...)` -> `(success, name, track_elements, results)`. The `results` list is the manifest source.
- `converter.RekordboxPlaylistConverter.write_manifest(path, name, results)` — JSON manifest of the run.

## Test Organization

Tests live in `tests/`. Each suite mirrors a module:

- **tests/test_cdj_detection.py** — `models.get_recommended_format_for_cdj` across the model database.
- **tests/test_quality_capping.py** — `quality.parse_max_quality`, `plan_conversion`, `can_passthrough`, `existing_matches_plan`. Pure-function tests; parametrized for the matrix.
- **tests/test_path_utilities.py** — URL decoding, filename sanitization, track ID management, `FORMAT_SETTINGS` registry.
- **tests/test_xml_structure.py** — Standalone XML structure + per-track element building. Builds minimal `ConversionResult` fixtures via a local `_result` helper.

When adding tests for capping / plan logic, prefer parametrized table tests in `test_quality_capping.py` — that's where future bug-class regressions get caught.
