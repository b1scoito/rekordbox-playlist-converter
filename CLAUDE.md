# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Rekordbox playlist converter that converts tracks from Rekordbox playlists to various formats (MP3, FLAC, AIFF) optimized for Pioneer DJ CDJ/XDJ equipment. The tool creates a **standalone, importable XML file** that doesn't modify the user's original Rekordbox database.

## Core Architecture

### Single-File Design
The entire application is contained in `main.py` (~730 lines). This includes:
- `CDJ_MODELS` dictionary (lines 27-140): Database of 17 Pioneer DJ models with format capabilities
- `RekordboxPlaylistConverter` class: Handles XML parsing, track conversion, and standalone XML generation
- **Typer CLI** with 3 commands:
  - `models`: List supported CDJ/XDJ models
  - `list`: List playlists in Rekordbox XML
  - `convert`: Convert playlist with format selection
- **Rich** for beautiful terminal output (tables, colors, formatting)

### Critical Design Principles

1. **Standalone XML Generation**: Never modify the original Rekordbox XML. Always create a new, independent XML file with:
   - Unique track IDs starting from 1000000 (configurable via `starting_track_id`)
   - Only converted tracks (not the entire collection)
   - Valid Rekordbox XML structure: `DJ_PLAYLISTS` → `PRODUCT` → `COLLECTION` → `PLAYLISTS`

2. **Format Selection Logic**:
   - FLAC for models that support it (lossless, no WAV_EXTENSIBLE issues)
   - MP3 320kbps for older models (universal compatibility)
   - Avoid WAV/AIFF due to known WAV_EXTENSIBLE metadata compatibility issues on CDJs

3. **ffmpeg Conversion Pipeline**: `convert_track()` method (lines 287-363)
   - Handles MP3, FLAC, and AIFF conversion
   - FLAC uses compression level 5 (balanced)
   - Sample rates: 48kHz for FLAC, 44.1kHz for MP3/AIFF

## Development Commands

### Setup
```bash
uv sync  # Install dependencies
uv run pre-commit install  # Install git hooks
```

### Linting and Type Checking
```bash
uv run ruff check main.py tests/     # Lint
uv run ruff format main.py tests/    # Format
uv run pyright main.py tests/        # Type check
```

### Testing
```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_cdj_detection.py -v

# Run specific test
uv run pytest tests/test_cdj_detection.py::TestCDJModelDetection::test_cdj_3000_recommends_flac -v

# Run tests with coverage
uv run pytest tests/ --cov=main --cov-report=term-missing
```

### Running the Tool (Development)
```bash
# Using uv (recommended during development)
uv run python main.py models
uv run python main.py list rekordbox.xml
uv run python main.py convert rekordbox.xml -p "Playlist" -o ./output --cdj-model XDJ-RX2

# After installation (production)
rekordbox-converter models
rekordbox-converter list rekordbox.xml
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
- Python 3.11+
- ffmpeg (system dependency, not in pyproject.toml)

## Type System Requirements

- Python 3.11+ (uses modern type hints: `list[...]`, `dict[...]`, `tuple[...]`)
- All methods have return type annotations
- `ET.ElementTree[Any]` used for XML tree (due to invariant generics)
- Use assertions for XML root element checks to satisfy type checker

## CDJ Model Database

When adding new CDJ/XDJ models to `CDJ_MODELS`:
- Include: `year`, `formats` (list), `max_quality` (dict), `recommended` (str)
- Optional: `notes` (str) for firmware updates or special considerations
- Recommended format should be:
  - `"flac"` for models with FLAC support (≥2016 typically)
  - `"mp3"` for older models or those with WAV/AIFF compatibility issues

## XML Metadata Handling

Track elements must preserve:
- All child elements (TEMPO, POSITION_MARK, etc.) via `_create_track_element()`
- Proper `Kind` attribute: "MP3 File", "FLAC File", or "AIFF File"
- BitRate, Size, Location attributes
- TrackID must be unique and sequential

## External Dependencies

- **ffmpeg**: Required for audio conversion (not in pyproject.toml, system dependency)
- Converts formats: MP3 (libmp3lame), FLAC (flac), AIFF (pcm_s16be)
- Tool fails gracefully if ffmpeg not found

## Key Methods

- `get_recommended_format_for_cdj(model: str)`: Static method, returns `(format, reason)` tuple
- `convert_playlist()`: Returns `(success, playlist_name, converted_tracks)` - does NOT modify original XML
- `create_standalone_xml()`: Builds fresh XML structure from scratch
- `save_standalone_xml()`: Saves standalone XML with proper indentation

## Test Organization

Tests are organized in `tests/` directory with 49 comprehensive unit tests:

- **test_cdj_detection.py** (15 tests): CDJ model detection, format recommendations, error handling
- **test_path_utilities.py** (19 tests): URL parsing, filename sanitization, track ID management, format settings
- **test_xml_structure.py** (15 tests): Standalone XML generation, track element creation, metadata preservation

Tests cover:
- All 17 CDJ/XDJ models in the database
- Format selection logic (FLAC vs MP3 recommendations)
- Path utilities (file:// URL decoding, filename sanitization)
- Track ID uniqueness and sequential generation
- XML structure validation (DJ_PLAYLISTS hierarchy)
- Track metadata preservation (attributes and child elements)
