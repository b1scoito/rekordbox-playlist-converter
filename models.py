"""Pioneer DJ CDJ/XDJ model database and format recommendations.

Pure data + one pure function. No I/O, no Rich, so this module is cheap to
import and trivial to test in isolation.
"""

from typing import Any

# Each entry records the model's release year, every format the firmware
# accepts, the per-format max quality the deck can actually decode (used by
# the conversion planner as a ceiling), and a sensible default `recommended`
# format. `notes` is optional, free-form, surfaced by the `models` CLI.
CDJ_MODELS: dict[str, dict[str, Any]] = {
    # High-end models with full FLAC/ALAC support (96kHz/24-bit)
    "CDJ-3000X": {
        "year": 2025,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
        "notes": "AlphaTheta-branded successor to CDJ-3000; adds Wi-Fi/streaming/NFC",
    },
    "CDJ-3000": {
        "year": 2020,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "CDJ-2000NXS2": {
        "year": 2016,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "CDJ-TOUR1": {
        "year": 2016,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "OPUS-QUAD": {
        "year": 2023,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "96kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    # Mid-range models with limited FLAC support (48kHz/24-bit)
    "XDJ-AZ": {
        "year": 2024,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
        "notes": "AlphaTheta 4-channel flagship all-in-one; FLAC requires firmware 1.10+",
    },
    "XDJ-1000MK2": {
        "year": 2016,
        "formats": ["flac", "alac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    "XDJ-XZ": {
        "year": 2019,
        "formats": ["flac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
        "notes": "FLAC support added in firmware 1.10 (2020); no ALAC",
    },
    "XDJ-RX3": {
        "year": 2021,
        "formats": ["flac", "aiff", "wav", "aac", "mp3"],
        "max_quality": {"flac": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "flac",
    },
    # Older models without FLAC support
    "CDJ-2000NXS": {
        "year": 2012,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
        "notes": "MP3 320kbps recommended due to WAV/AIFF compatibility issues",
    },
    "CDJ-900NXS": {
        "year": 2013,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "CDJ-2000": {
        "year": 2009,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "CDJ-900": {
        "year": 2009,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-1000": {
        "year": 2014,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-700": {
        "year": 2015,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-RR": {
        "year": 2018,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-RX2": {
        "year": 2017,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-RX": {
        "year": 2015,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-R1": {
        "year": 2013,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
    "XDJ-AERO": {
        "year": 2012,
        "formats": ["aiff", "wav", "aac", "mp3"],
        "max_quality": {"aiff": "48kHz/24-bit", "aac": "48kHz/16-bit"},
        "recommended": "mp3",
    },
}


def get_recommended_format_for_cdj(model: str) -> tuple[str, str]:
    """Return (recommended_format, human-readable reason) for a given model.

    Raises ValueError for unknown models so callers can fail fast on typos
    (the CLI does this before constructing a converter, so a typo can't
    silently drop the quality caps).
    """
    model_upper = model.upper()
    if model_upper not in CDJ_MODELS:
        available = ", ".join(sorted(CDJ_MODELS.keys()))
        raise ValueError(f"Unknown CDJ model: {model}. Available models: {available}")

    info = CDJ_MODELS[model_upper]
    recommended: str = info["recommended"]
    if recommended == "flac":
        quality = info["max_quality"].get("flac", "48kHz/24-bit")
        reason = (
            f"FLAC (up to {quality}): Best quality with lossless compression, "
            "excellent tag support, no compatibility issues"
        )
    else:  # mp3
        reason = (
            "MP3 320kbps: Best compatibility, excellent tag support, "
            "no WAV/AIFF compatibility issues"
        )
    notes = info.get("notes")
    if notes:
        reason += f" | Note: {notes}"
    return (recommended, reason)
