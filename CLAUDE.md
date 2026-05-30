# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Rekordbox playlist converter that converts tracks from Rekordbox playlists to various formats (MP3, FLAC, AIFF) optimized for Pioneer DJ / AlphaTheta CDJ/XDJ equipment (Pioneer DJ rebranded to AlphaTheta in 2024 — newer models like CDJ-3000X and XDJ-AZ ship under the AlphaTheta name). The tool creates a **standalone, importable XML file** that doesn't modify the user's original Rekordbox database.

See [`ROADMAP.md`](ROADMAP.md) for candidate features under consideration — most notably an opt-in `--write-library` mode that would skip the manual Rekordbox import step by writing to `master.db` directly.

## Core Architecture

### Module Layout

The codebase is split into small, single-purpose modules. Each leans on the next in a clean dependency line: `quality` and `models` are pure; `converter` builds on them; `cli` builds on `converter`; `main.py` is just the entry point.

- `_console.py` — Shared `rich.console.Console` instance imported wherever output is printed.
- `models.py` — `CDJ_MODELS` data + `get_recommended_format_for_cdj` (pure, no I/O, no Rich).
- `quality.py` — Pure quality-decision functions and the ffprobe wrapper: `parse_max_quality`, `plan_conversion`, `can_passthrough`, `existing_matches_plan`, `probe`. Safety-critical; isolated so it can be tested without touching the rest of the system.
- `converter.py` — `RekordboxPlaylistConverter` class plus `OutputFormat`/`Action` StrEnums, `FormatSettings` and `ConversionResult` dataclasses, and the `FORMAT_SETTINGS` registry. Orchestrates ffmpeg, XML I/O, and the JSON manifest.
- `cli.py` — Typer commands (`models`, `list`, `convert`) and the model-table renderer.
- `main.py` — Thin shim: `from cli import app; if __name__ == "__main__": app()`. Kept for the `python main.py …` dev workflow; the installed entry point is `[project.scripts] rekordbox-converter = "cli:app"`.

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

8. **Output paths are absolute**: `convert_playlist` resolves `output_dir` to an absolute path before anything else, and `_create_track_element` resolves again defensively. Rekordbox 7 silently refuses to import `file://localhost<rel>` URIs; the resolve calls are load-bearing for the import flow. Do not remove them.

## Beatgrid alignment caveats

`_create_track_element` copies `TEMPO` (beatgrid) and `POSITION_MARK` (cues) verbatim from the source XML — it never rewrites grid timestamps. That's correct for sample-exact conversions, but two paths can introduce timing drift the XML won't reflect:

- **MP3 source → FLAC/AIFF target**: the MP3 decoder strips ~13–26 ms of encoder delay; the converted PCM is shifted earlier than the original timeline the `TEMPO Inizio` values were computed against. Result: beatgrid drifts forward by the encoder delay.
- **FLAC source → MP3 target on older CDJs**: `libmp3lame` writes a LAME header so modern CDJs (CDJ-3000, XDJ-RX2/3, XDJ-XZ) play gapless. Older firmware (CDJ-900, some CDJ-2000) may ignore the header, producing the same ~13–26 ms shift on the deck.

Mitigations the code already takes:
- Same-format passthrough (`-c:a copy`) when source and target codec/quality match. Zero drift on MP3→MP3 and FLAC→FLAC paths.
- AIFF as a fallback for old decks that won't honour LAME's gapless header.

If a future change starts rewriting the grid (e.g. to correct the MP3→lossless drift), it must do so against the *converted* audio's timeline, not the source's, and it must be opt-in — the project's contract with users is "your cues come out untouched."

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
- Pyright runs in **strict mode** (`typeCheckingMode = "strict"` in pyproject). Production code is clean under strict.
- `[tool.pyright.executionEnvironments]` scopes `tests/` and **relaxes** `reportPrivateUsage`, `reportMissingParameterType`, `reportUnknownParameterType`, `reportUnknownArgumentType`, `reportUnknownMemberType`, `reportUnknownVariableType`. Tests can access private members, accept untyped `MagicMock` returns, and omit annotations on test methods / fixtures. **Don't add `# type: ignore` to test files** — adjust the executionEnvironment if a legit error surfaces, or fix the production type that triggered it.
- `extraPaths = ["."]` on the tests environment lets `tests/` resolve flat top-level imports (`from converter import …`).
- All public methods carry return-type annotations.
- `converter.py` uses `from __future__ import annotations` because `ET.ElementTree[Any]` isn't subscriptable at runtime; PEP 563 makes annotations lazy.
- `match` blocks on `OutputFormat` end with `case _: assert_never(self.output_format)` so pyright enforces exhaustiveness.

## Packaging

Flat module layout (no package directory). pyproject declares `[tool.setuptools] py-modules = ["_console", "models", "quality", "converter", "cli", "main"]` — setuptools' auto-discovery refuses to guess when there's more than one top-level `.py`, so the list is required.

**If you add a new top-level module, you MUST add it to `py-modules` or it will be silently omitted from the wheel.** v0.2.0's release workflow failed for exactly this reason after the modular split; v0.2.1 fixed it. Tests live under `tests/` (no `__init__.py`, no package) and are not part of the distribution.

Build backend: `setuptools.build_meta` (requires `setuptools>=77` for PEP 639 SPDX license expressions, declared in `[build-system]`).

## Release flow

1. **Work on `dev`.** It's the default working branch (per project convention); CI runs on PRs/pushes to `[dev, main]`.
2. **Open PR `dev` → `main`.** `main` is the GitHub default branch (we renamed from `master` in May 2026). CI matrix runs Python 3.11 / 3.12 / 3.13.
3. **Merge with `gh pr merge <N> --merge`** — not `--squash`. The per-commit messages are written deliberately and preserve the rationale chain.
4. **Bump `version` in `pyproject.toml`.** Run `uv sync` so `uv.lock` reflects the new version; commit both. Patch bumps for bug fixes (e.g. 0.2.1 → 0.2.2), minor for features.
5. **Cut the GitHub release**: `gh release create vX.Y.Z --target main --title "vX.Y.Z" --notes "..."`. The `release.yml` workflow triggers on `release: published` and publishes to PyPI via **trusted publishing** — no API tokens involved, just the `id-token: write` permission already in the workflow.
6. **Verify**: `curl -s https://pypi.org/simple/rekordbox-playlist-converter/ | grep <version>` returns a hit when the new version is live. The JSON endpoint (`/json`) lags by a few minutes due to caching; trust `/simple/`.

If a release workflow fails, **don't reuse the version**. Bump forward (0.2.0 → 0.2.1) so the failed release stays as a historical record on GitHub instead of being overwritten.

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
- **tests/test_probe.py** — `quality.probe` with `subprocess.run` patched to canned ffprobe output. Covers parsing including `bits_per_raw_sample` preference, `N/A` handling, and every failure mode (`FileNotFoundError`, `TimeoutExpired`, `OSError`).
- **tests/test_ffmpeg_cmd.py** — `_build_ffmpeg_cmd` / `_extend_with_audio_args` over the full source × target × format × passthrough matrix. Pure command-list assertions; no subprocess.
- **tests/test_xml_io.py** — `load_xml`, `list_playlists`, recursive `_collect_playlists`, empty-XML handling. Inline rekordbox-shaped fixture, no real XML export needed.
- **tests/test_xml_structure.py** — Standalone XML structure + per-track element building. Builds minimal `ConversionResult` fixtures via a local `_result` helper. Includes a regression test for the absolute-path Location URI invariant.
- **tests/test_manifest.py** — `write_manifest` JSON round-trip, schema stability, Path / StrEnum serialization.
- **tests/test_dry_run_render.py** — `_format_quality` parametrized + `_print_dry_run_table` via captured `Console`.
- **tests/test_cli.py** — `typer.testing.CliRunner` against `models` / `list` / `convert`. Argument validation, `--dry-run` side-effect-freeness, ANSI-stripped help-text assertions.
- **tests/test_path_utilities.py** — URL decoding, filename sanitization, track ID management, `FORMAT_SETTINGS` registry.

When adding tests for capping / plan logic, prefer parametrized table tests in `test_quality_capping.py` — that's where future bug-class regressions get caught. When adding tests for ffmpeg command shape, extend `test_ffmpeg_cmd.py`'s matrix rather than adding subprocess mocks.

If you add a CLI assertion that checks for a flag or label in Rich-rendered output, strip ANSI first: `tests/test_cli.py` has a `_plain(text)` helper that does this. Otherwise CI fails on Rich's interleaved color codes even when local runs pass.
