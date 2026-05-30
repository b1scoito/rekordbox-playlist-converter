"""Pure quality-decision functions and ffprobe wrapper.

No I/O beyond ffprobe subprocess calls, no Rich, no state. Every function here
is independently testable -- they're the safety-critical core of the
conversion pipeline, and isolating them from the rest of the code keeps that
property visible.
"""

import contextlib
import re
import subprocess
from pathlib import Path

# Wall-clock ceiling on ffprobe. Fast operation; this just guards against
# pathological inputs hanging the playlist.
FFPROBE_TIMEOUT_SECONDS = 30

# Maps internal output_format keys to codec names ffprobe reports on
# already-encoded files. Used by `can_passthrough` to spot "same format,
# already correct" inputs we can stream-copy instead of re-encoding.
PASSTHROUGH_CODECS: dict[str, set[str]] = {
    "mp3": {"mp3"},
    "flac": {"flac"},
    "aiff": {"pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_s8"},
}


def parse_max_quality(spec: str) -> tuple[int | None, int | None]:
    """Parse a capability string like '96kHz/24-bit' -> (96000, 24).

    Either component may be absent; missing parts come back as None. Used to
    translate CDJ_MODELS' `max_quality` entries into numeric caps.
    """
    sample_rate: int | None = None
    bit_depth: int | None = None
    sr_match = re.search(r"([\d.]+)\s*kHz", spec, re.IGNORECASE)
    if sr_match:
        sample_rate = round(float(sr_match.group(1)) * 1000)
    bd_match = re.search(r"(\d+)\s*-?\s*bit", spec, re.IGNORECASE)
    if bd_match:
        bit_depth = int(bd_match.group(1))
    return (sample_rate, bit_depth)


def probe(
    path: Path,
) -> tuple[int | None, int | None, str | None, int | None, float | None]:
    """Probe a media file via ffprobe.

    Returns (sample_rate, bit_depth, codec_name, bitrate_bps, duration_seconds).
    Any field is None when ffprobe can't determine it (or isn't installed).
    Lossy sources (e.g. MP3) carry no meaningful bit depth -> None.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate,bits_per_raw_sample,bits_per_sample,codec_name,bit_rate,duration",
                "-of",
                "default=noprint_wrappers=1:nokey=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return (None, None, None, None, None)

    sample_rate: int | None = None
    bit_depth: int | None = None
    codec_name: str | None = None
    bitrate_bps: int | None = None
    duration: float | None = None
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        if not value or value == "N/A":
            continue
        if key == "codec_name":
            codec_name = value
            continue
        if key == "duration":
            with contextlib.suppress(ValueError):
                duration = float(value)
            continue
        try:
            num = int(value)
        except ValueError:
            continue
        if key == "sample_rate":
            sample_rate = num
        elif key == "bit_rate":
            bitrate_bps = num
        # bits_per_raw_sample is the accurate one for lossless (e.g. 24);
        # bits_per_sample is the container fallback (only when raw is absent).
        elif num > 0 and (
            key == "bits_per_raw_sample" or (key == "bits_per_sample" and bit_depth is None)
        ):
            bit_depth = num
    return (sample_rate, bit_depth, codec_name, bitrate_bps, duration)


def probe_audio_start_seconds(path: Path) -> float:
    """Return the audio stream's presentation start time, in seconds.

    For an MP3 encoded by ffmpeg's libmp3lame, this surfaces the encoder
    delay (~1152 samples / ~25 ms at 44.1 kHz) even though ffmpeg does
    not fill the LAME info-tag delay subfield. Lossless formats report 0.
    Returns 0.0 on any probe failure rather than raising -- callers treat
    "unknown" the same as "no delay" (don't shift the grid).
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=start_time",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return 0.0
    text = result.stdout.strip()
    if not text or text == "N/A":
        return 0.0
    try:
        return max(0.0, float(text))
    except ValueError:
        return 0.0


def plan_conversion(
    output_format: str,
    source_sr: int | None,
    source_bd: int | None,
    cap_sr: int | None,
    cap_bd: int | None,
) -> tuple[int | None, int | None]:
    """Decide (target_sample_rate, target_bit_depth) given source + caps.

    Invariant: never step quality up. We only resample/reduce when the source
    exceeds either the deck cap or the codec's own ceiling (LAME tops out at
    48 kHz; AIFF/FLAC have no codec-side rate cap). Bit depth is
    format-specific: AIFF defaults to 16 when source is unknown (likely lossy
    origin); FLAC preserves source depth unless capped; MP3 carries no PCM
    bit depth.
    """
    codec_max_sr = 48000 if output_format == "mp3" else None
    limits = [c for c in (cap_sr, codec_max_sr) if c is not None]
    effective_cap = min(limits) if limits else None
    target_sr = source_sr
    if target_sr is not None and effective_cap is not None and target_sr > effective_cap:
        target_sr = effective_cap

    target_bd: int | None
    if output_format == "aiff":
        target_bd = source_bd if source_bd is not None else 16
        if cap_bd is not None and target_bd > cap_bd:
            target_bd = cap_bd
    elif output_format == "flac":
        target_bd = source_bd
        if cap_bd is not None and (target_bd is None or target_bd > cap_bd):
            target_bd = cap_bd
    else:  # mp3 carries no PCM bit depth
        target_bd = None
    return target_sr, target_bd


def can_passthrough(
    output_format: str,
    source_codec: str | None,
    source_sr: int | None,
    source_bd: int | None,
    target_sr: int | None,
    target_bd: int | None,
) -> bool:
    """True iff the source is already what we'd produce: same codec family,
    within sample-rate cap, within bit-depth cap. Lets us `-c:a copy`
    instead of re-encoding (no quality loss, much faster)."""
    if source_codec not in PASSTHROUGH_CODECS.get(output_format, set()):
        return False
    # Source rate must not exceed target (resample would be needed otherwise).
    if source_sr is None or target_sr is None or source_sr > target_sr:
        return False
    if output_format == "mp3":
        return True  # MP3 has no PCM depth dimension
    if source_bd is None:
        return False  # need known depth to prove it fits the cap
    # Source depth must be within the target cap (or cap unset = unbounded).
    return target_bd is None or source_bd <= target_bd


def existing_matches_plan(
    output_format: str,
    existing_sr: int | None,
    existing_bd: int | None,
    target_sr: int | None,
    target_bd: int | None,
) -> bool:
    """True if an existing output file is consistent with the current plan.

    Lets us keep prior good output across re-runs. If the deck or format has
    changed since the prior run, the existing file's rate/depth won't match
    the new plan and we'll re-encode. If we can't probe either side, refuse
    to reuse (re-encode to be safe).
    """
    if existing_sr is None or target_sr is None or existing_sr != target_sr:
        return False
    if output_format == "mp3":
        return True  # MP3 has no PCM depth dimension
    if existing_bd is None or target_bd is None:
        return False
    return existing_bd == target_bd
