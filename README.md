# Rekordbox Playlist Converter

Convert Rekordbox playlists with automatic format selection for Pioneer DJ CDJ/XDJ equipment.

[![CI](https://github.com/yourusername/rekordbox-playlist-converter/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/rekordbox-playlist-converter/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)

## Features

- Automatic format selection based on CDJ/XDJ model capabilities
- Standalone XML generation without modifying original Rekordbox library
- MP3 (320kbps), FLAC (lossless), and AIFF conversion via ffmpeg
- Support for 17 Pioneer DJ models (CDJ-900 to CDJ-3000, XDJ-RX to OPUS-QUAD)
- CLI interface with Typer and Rich
- 49 unit tests with full type coverage

## Overview

Pioneer CDJs have different format support capabilities and known compatibility issues with WAV files (WAV_EXTENSIBLE metadata). This tool addresses these issues by:

- Selecting FLAC for models that support it
- Using MP3 320kbps for models with limited format support
- Avoiding WAV/AIFF to prevent metadata compatibility problems
- Preserving all metadata including cue points, BPM, key, and track analysis

## Installation

### From PyPI (Coming Soon)

```bash
pip install rekordbox-playlist-converter
```

### From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/rekordbox-playlist-converter.git
cd rekordbox-playlist-converter

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### System Requirements

- Python 3.11 or higher
- ffmpeg for audio conversion

Install ffmpeg:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
choco install ffmpeg
```

## Usage

### List Supported CDJ Models

```bash
rekordbox-converter models
```

### List Playlists in Rekordbox XML

```bash
rekordbox-converter list rekordbox.xml
```

### Convert a Playlist (Auto-format Selection)

```bash
rekordbox-converter convert rekordbox.xml \
  --playlist "My Playlist" \
  --output ./converted \
  --cdj-model XDJ-RX2
```

### Convert with Manual Format Selection

```bash
rekordbox-converter convert rekordbox.xml \
  --playlist "My Playlist" \
  --output ./converted \
  --format flac
```

### Full Example

```bash
# 1. List all playlists
rekordbox-converter list rekordbox.xml

# 2. Convert for CDJ-3000 (automatically selects FLAC)
rekordbox-converter convert rekordbox.xml \
  -p "Tech House 2024" \
  -o ./converted \
  --cdj-model CDJ-3000

# 3. Import the generated XML into Rekordbox
# File � Import Collection � Select "Tech House 2024 (FLAC).xml"
```

## Format Recommendations by Model

| Model | Recommended | Max Quality | Notes |
|-------|------------|-------------|-------|
| CDJ-3000 | FLAC | 96kHz/24-bit | Highest quality support |
| CDJ-2000NXS2 | FLAC | 96kHz/24-bit | Full lossless support |
| XDJ-RX3 | FLAC | 48kHz/24-bit | FLAC supported |
| XDJ-RX2 | MP3 | 320kbps | No FLAC support |
| CDJ-2000NXS | MP3 | 320kbps | WAV/AIFF compatibility issues |

See full model list with `rekordbox-converter models`

## Development

### Setup

```bash
# Install development dependencies
uv sync

# Install pre-commit hooks
uv run pre-commit install
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=main --cov-report=term-missing

# Run specific test
uv run pytest tests/test_cdj_detection.py -v
```

### Linting and Type Checking

```bash
# Lint and format
uv run ruff check main.py tests/
uv run ruff format main.py tests/

# Type check
uv run pyright main.py tests/
```

### Pre-commit Hooks

Pre-commit hooks run automatically before each commit:
- Trailing whitespace removal
- YAML/JSON/TOML validation
- Ruff linting and formatting
- Type checking should be done manually with `uv run pyright`

## How It Works

1. Reads the Rekordbox XML file to extract playlist information
2. Converts tracks using ffmpeg to the selected format
3. Creates a standalone XML file containing:
   - Only converted tracks from the specified playlist
   - Unique track IDs starting from 1000000 to avoid conflicts
   - All original metadata (cue points, BPM, key, track analysis)
4. Import the generated XML into Rekordbox via File > Import Collection

## FAQ

**Q: Will this modify my original Rekordbox library?**
A: No. The tool creates a new standalone XML file without modifying the original.

**Q: Why not use WAV/AIFF?**
A: CDJs have known issues with WAV_EXTENSIBLE metadata. FLAC provides lossless quality without these compatibility problems.

**Q: Can I use this for USB export?**
A: Yes. Import the generated XML into Rekordbox, then export to USB as normal.

**Q: What if my CDJ model is not supported?**
A: The tool will display an error listing all supported models. Open an issue to request additional model support.

## Contributing

Contributions are welcome. Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests and linters pass
5. Submit a pull request

## License

GNU GPLv3 License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Pioneer DJ for Rekordbox and CDJ/XDJ equipment
- [Typer](https://typer.tiangolo.com/) for CLI framework
- [Rich](https://rich.readthedocs.io/) for terminal output
- DJ community for format compatibility insights


## Support

- [Report bugs](https://github.com/yourusername/rekordbox-playlist-converter/issues)
- [Request features](https://github.com/yourusername/rekordbox-playlist-converter/issues)
