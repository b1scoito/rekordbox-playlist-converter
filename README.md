# Rekordbox Playlist Converter

Convert Rekordbox playlists with automatic format selection for Pioneer DJ CDJ/XDJ equipment.

[![CI](https://github.com/yourusername/rekordbox-playlist-converter/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/rekordbox-playlist-converter/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)

## Features

- <� **Smart Format Selection**: Automatically recommends the best format (FLAC/MP3) for your specific CDJ/XDJ model
- = **Safe**: Creates a standalone XML file - never modifies your original Rekordbox library
- <� **High Quality**: Supports MP3 (320kbps), FLAC (lossless), and AIFF conversion via ffmpeg
- =� **17 CDJ Models Supported**: From CDJ-900 to CDJ-3000 and XDJ-RX to OPUS-QUAD
- ( **Modern CLI**: Beautiful interface powered by Typer and Rich
- >� **Well Tested**: 49 unit tests with 100% type safety

## Why This Tool?

Pioneer CDJs have varying format support capabilities and known issues with WAV files (WAV_EXTENSIBLE metadata problems). This tool:

- **Avoids WAV/AIFF issues** by recommending FLAC or MP3
- **Maximizes quality** by using FLAC for supported models
- **Ensures compatibility** by using MP3 320kbps for older models
- **Preserves metadata** including cue points, BPM, key, and track analysis

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

- **Python 3.11+**
- **ffmpeg** (for audio conversion)
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
| **CDJ-3000** | FLAC | 96kHz/24-bit | Best quality available |
| **CDJ-2000NXS2** | FLAC | 96kHz/24-bit | Excellent lossless support |
| **XDJ-RX3** | FLAC | 48kHz/24-bit | Modern FLAC support |
| **XDJ-RX2** | MP3 | 320kbps | Reliable, no WAV issues |
| **CDJ-2000NXS** | MP3 | 320kbps | WAV/AIFF compatibility issues |

[Full model list](https://github.com/yourusername/rekordbox-playlist-converter#supported-models)

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

1. **Reads** your Rekordbox XML to extract playlist information
2. **Converts** tracks using ffmpeg to the optimal format for your CDJ
3. **Creates** a standalone XML with:
   - Only the converted tracks (not your entire library)
   - Unique track IDs (starting from 1000000) to prevent conflicts
   - All metadata preserved (cue points, BPM, key, etc.)
4. **Safe to import** via Rekordbox: File � Import Collection

## FAQ

**Q: Will this modify my original Rekordbox library?**
A: No! It creates a completely new, standalone XML file. Your original is never touched.

**Q: Why not use WAV/AIFF?**
A: CDJs have known issues with WAV_EXTENSIBLE metadata in WAV files. FLAC provides lossless quality without compatibility issues.

**Q: Can I use this for USB sticks for CDJs?**
A: Yes! After conversion, import the standalone XML into Rekordbox, then export to USB as normal.

**Q: What if my CDJ model isn't listed?**
A: The tool will show an error with all supported models. Please open an issue to request support for your model.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests and linters pass
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Pioneer DJ for Rekordbox and CDJ/XDJ equipment
- [Typer](https://typer.tiangolo.com/) for the excellent CLI framework
- [Rich](https://rich.readthedocs.io/) for beautiful terminal output
- The DJ community for format compatibility insights

## Support

- = [Report bugs](https://github.com/yourusername/rekordbox-playlist-converter/issues)
- =� [Request features](https://github.com/yourusername/rekordbox-playlist-converter/issues)
- =� [Read the docs](https://github.com/yourusername/rekordbox-playlist-converter)
