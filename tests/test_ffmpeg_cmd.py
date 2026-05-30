"""Tests for `_build_ffmpeg_cmd` / `_extend_with_audio_args`.

The ffmpeg invocation is the on-the-wire surface where bugs cause silent
quality loss. The command-list is built without invoking ffmpeg, so it's
trivially testable — just assert what flags are (and aren't) present.
"""

from pathlib import Path

import pytest

from converter import RekordboxPlaylistConverter


def _cmd(
    fmt: str,
    *,
    source_sr: int | None = None,
    source_bd: int | None = None,
    target_sr: int | None = None,
    target_bd: int | None = None,
    passthrough: bool = False,
) -> list[str]:
    """Build an ffmpeg command for the given conversion shape."""
    converter = RekordboxPlaylistConverter("dummy.xml", fmt)
    return converter._build_ffmpeg_cmd(
        Path("/in/source"),
        Path("/out/.target.part.ext"),
        source_sr,
        source_bd,
        target_sr,
        target_bd,
        passthrough=passthrough,
    )


def _arg(cmd: list[str], flag: str) -> str | None:
    """Return the value following `flag` in cmd, or None if absent."""
    try:
        return cmd[cmd.index(flag) + 1]
    except ValueError:
        return None


def _all_args(cmd: list[str], flag: str) -> list[str]:
    """Return all values following each occurrence of `flag`."""
    out: list[str] = []
    for i, tok in enumerate(cmd):
        if tok == flag and i + 1 < len(cmd):
            out.append(cmd[i + 1])
    return out


class TestSampleRateFlag:
    """`-ar` is added only when reducing sample rate, never when matching or
    upsampling. Probe-failure falls back to the format default."""

    def test_mp3_no_resample_when_at_rate(self):
        # 44.1k source, no deck cap. 44.1k <= 48k LAME ceiling -> no -ar.
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        assert "-ar" not in cmd

    def test_mp3_resamples_down_to_48k(self):
        cmd = _cmd("mp3", source_sr=96000, target_sr=48000)
        assert _arg(cmd, "-ar") == "48000"

    def test_mp3_falls_back_to_default_rate_when_probe_failed(self):
        # source_sr=None means probe failed -> use format default (44100).
        cmd = _cmd("mp3", source_sr=None, target_sr=None)
        assert _arg(cmd, "-ar") == "44100"

    def test_flac_falls_back_to_48k_default(self):
        cmd = _cmd("flac", source_sr=None, target_sr=None)
        assert _arg(cmd, "-ar") == "48000"

    def test_flac_preserves_44_1k_when_deck_supports_more(self):
        # Never upsample 44.1k -> 48k just because the deck allows it.
        cmd = _cmd("flac", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        assert "-ar" not in cmd


class TestFlacBitDepth:
    """FLAC: force `-sample_fmt s16` ONLY when reducing >16 -> 16. Otherwise
    let ffmpeg preserve the native depth (the bug this guards against)."""

    def test_no_sample_fmt_when_preserving_24(self):
        # 96k/24 source, deck allows 96k/24: leave depth alone.
        cmd = _cmd("flac", source_sr=96000, source_bd=24, target_sr=96000, target_bd=24)
        assert "-sample_fmt" not in cmd

    def test_no_sample_fmt_when_preserving_16(self):
        # 44.1k/16 source, deck allows more: depth preserved, no flag needed.
        cmd = _cmd("flac", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        assert "-sample_fmt" not in cmd

    def test_sample_fmt_s16_when_reducing_24_to_16(self):
        # 96k/24 source, deck capped to 48k/16: must force 16-bit output.
        cmd = _cmd("flac", source_sr=96000, source_bd=24, target_sr=48000, target_bd=16)
        assert _arg(cmd, "-sample_fmt") == "s16"

    def test_forces_s16_when_source_depth_unknown(self):
        # Source depth None (lossy origin: probe couldn't read PCM depth) is
        # treated defensively: we can't prove the source is already <=16, so
        # force s16 rather than risk shipping a >16 file the deck won't play.
        cmd = _cmd("flac", source_sr=44100, source_bd=None, target_sr=44100, target_bd=16)
        assert _arg(cmd, "-sample_fmt") == "s16"

    def test_flac_always_sets_compression_level(self):
        cmd = _cmd("flac", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        assert _arg(cmd, "-compression_level") == "5"


class TestAiffCodec:
    """AIFF chooses pcm_s24be vs pcm_s16be based on target_bd."""

    def test_24bit_picks_pcm_s24be(self):
        cmd = _cmd("aiff", source_sr=44100, source_bd=24, target_sr=44100, target_bd=24)
        assert _arg(cmd, "-acodec") == "pcm_s24be"

    def test_16bit_picks_pcm_s16be(self):
        cmd = _cmd("aiff", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        assert _arg(cmd, "-acodec") == "pcm_s16be"

    def test_unknown_target_depth_defaults_to_16bit(self):
        # target_bd=None should still pick pcm_s16be (safest default).
        cmd = _cmd("aiff", source_sr=44100, source_bd=None, target_sr=44100, target_bd=None)
        assert _arg(cmd, "-acodec") == "pcm_s16be"


class TestPassthrough:
    """Passthrough replaces all audio codec options with `-c:a copy`."""

    def test_passthrough_uses_c_a_copy(self):
        cmd = _cmd(
            "flac",
            source_sr=44100,
            source_bd=16,
            target_sr=44100,
            target_bd=16,
            passthrough=True,
        )
        assert _arg(cmd, "-c:a") == "copy"

    def test_passthrough_omits_acodec(self):
        # `-acodec` is the full-encode form; passthrough must NOT add it.
        cmd = _cmd(
            "flac",
            source_sr=44100,
            source_bd=16,
            target_sr=44100,
            target_bd=16,
            passthrough=True,
        )
        assert "-acodec" not in cmd

    def test_passthrough_omits_sample_rate_and_bitrate(self):
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100, passthrough=True)
        assert "-ar" not in cmd
        assert "-b:a" not in cmd


class TestCoverArt:
    """MP3/FLAC carry attached pictures; AIFF cannot embed art."""

    def test_mp3_maps_audio_and_optional_art(self):
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        maps = _all_args(cmd, "-map")
        assert "0:a:0" in maps
        assert "0:v?" in maps
        # Picture stream is copied verbatim and tagged as attached_pic.
        assert _arg(cmd, "-c:v") == "copy"
        assert _arg(cmd, "-disposition:v") == "attached_pic"

    def test_flac_maps_audio_and_optional_art(self):
        cmd = _cmd("flac", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        maps = _all_args(cmd, "-map")
        assert "0:a:0" in maps
        assert "0:v?" in maps

    def test_aiff_drops_video_stream(self):
        # AIFF muxer cannot embed an attached picture: -vn instead of -map.
        cmd = _cmd("aiff", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        assert "-vn" in cmd
        assert "-map" not in cmd
        assert "-c:v" not in cmd


class TestCommandStructure:
    """End-to-end shape: input first, output last, every command has -y."""

    def test_input_is_first_after_ffmpeg(self):
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        assert cmd[0] == "ffmpeg"
        assert cmd[1] == "-i"
        assert cmd[2] == "/in/source"

    def test_output_is_last(self):
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        # The temp path is the final positional argument.
        assert cmd[-1] == "/out/.target.part.ext"

    def test_overwrite_flag_present(self):
        # -y so ffmpeg doesn't block on prompt if a leftover exists.
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        assert "-y" in cmd


class TestMp3SpecificFlags:
    """MP3 always uses libmp3lame at strict CBR 320k. We don't ship VBR/ABR."""

    def test_codec_is_libmp3lame(self):
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        assert _arg(cmd, "-acodec") == "libmp3lame"

    def test_bitrate_is_320k(self):
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        assert _arg(cmd, "-b:a") == "320k"

    def test_strict_cbr_flags_present(self):
        # Without these three flags pinned to the target, ffmpeg's libmp3lame
        # underspends via the bit reservoir and tags the file VBR -- we saw
        # 270 kb/s actual on a 320k target. minrate == maxrate == bufsize ==
        # bitrate forces every frame full-size: real CBR 320 kbps.
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100)
        assert _arg(cmd, "-minrate") == "320k"
        assert _arg(cmd, "-maxrate") == "320k"
        assert _arg(cmd, "-bufsize") == "320k"

    def test_strict_cbr_flags_omitted_for_passthrough(self):
        # Passthrough = stream copy, no re-encode. Rate-control flags would
        # be meaningless and might even confuse ffmpeg's mux.
        cmd = _cmd("mp3", source_sr=44100, target_sr=44100, passthrough=True)
        assert "-minrate" not in cmd
        assert "-maxrate" not in cmd
        assert "-bufsize" not in cmd


class TestLosslessFormatsHaveNoRateControl:
    """FLAC and AIFF are lossless: minrate/maxrate would be a category error.
    Only MP3 (a lossy bitrate-targeted codec) gets the CBR enforcement flags."""

    def test_flac_has_no_minrate_maxrate(self):
        cmd = _cmd("flac", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        assert "-minrate" not in cmd
        assert "-maxrate" not in cmd
        assert "-bufsize" not in cmd

    def test_aiff_has_no_minrate_maxrate(self):
        cmd = _cmd("aiff", source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
        assert "-minrate" not in cmd
        assert "-maxrate" not in cmd
        assert "-bufsize" not in cmd


@pytest.mark.parametrize(
    "fmt, expected_codec",
    [
        ("mp3", "libmp3lame"),
        ("flac", "flac"),
        # AIFF codec depends on bit depth - covered in TestAiffCodec.
    ],
)
def test_codec_per_format(fmt, expected_codec):
    cmd = _cmd(fmt, source_sr=44100, source_bd=16, target_sr=44100, target_bd=16)
    assert _arg(cmd, "-acodec") == expected_codec
