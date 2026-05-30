"""Tests for quality capping, plan logic, passthrough, and stale detection.

These cover the safety-critical decisions that determine output quality. A bug
here causes silent quality regressions (upsampled, downsampled, truncated bit
depth) that aren't caught by listening at a gig -- the whole point of the
capping fix was to prevent that class of failure, so the decision tree gets
its own dedicated tests.
"""

import pytest

from quality import (
    can_passthrough,
    existing_matches_plan,
    parse_max_quality,
    plan_conversion,
)


class TestParseMaxQuality:
    """`parse_max_quality` extracts (sample_rate_hz, bit_depth) from a
    capability string. Translates CDJ_MODELS strings into numeric caps."""

    @pytest.mark.parametrize(
        "spec, expected",
        [
            ("96kHz/24-bit", (96000, 24)),
            ("48kHz/24-bit", (48000, 24)),
            ("44.1kHz/16-bit", (44100, 16)),
            ("48kHz/16-bit", (48000, 16)),
            ("192kHz/32-bit", (192000, 32)),
        ],
    )
    def test_standard_specs(self, spec, expected):
        assert parse_max_quality(spec) == expected

    @pytest.mark.parametrize(
        "spec, expected",
        [
            ("96 kHz / 24 bit", (96000, 24)),
            ("96kHz / 24bit", (96000, 24)),
            ("48KHZ/16BIT", (48000, 16)),  # case-insensitive
        ],
    )
    def test_whitespace_and_case(self, spec, expected):
        assert parse_max_quality(spec) == expected

    def test_only_rate(self):
        assert parse_max_quality("48kHz") == (48000, None)

    def test_only_depth(self):
        assert parse_max_quality("24-bit") == (None, 24)

    def test_empty(self):
        assert parse_max_quality("") == (None, None)

    def test_garbage(self):
        assert parse_max_quality("just text") == (None, None)


class TestPlanConversionMP3:
    """MP3 has no PCM bit depth axis, but it does have a LAME-imposed 48 kHz
    sample-rate ceiling -- so the codec cap applies even when the deck allows more."""

    def test_44_1k_source_no_cap_stays_44_1k(self):
        # No deck cap; 44.1k <= 48k (LAME ceiling) so no change.
        assert plan_conversion("mp3", 44100, None, None, None) == (44100, None)

    def test_96k_source_capped_by_codec_to_48k(self):
        # No deck cap, but LAME tops out at 48 kHz.
        assert plan_conversion("mp3", 96000, 24, None, None) == (48000, None)

    def test_96k_source_capped_by_deck_to_44_1k(self):
        # Deck cap 44.1k is tighter than the codec ceiling.
        assert plan_conversion("mp3", 96000, 24, 44100, 16) == (44100, None)

    def test_unknown_source_rate(self):
        # Probe failed: caller falls back to format default downstream.
        assert plan_conversion("mp3", None, None, None, None) == (None, None)


class TestPlanConversionFLAC:
    """FLAC preserves source quality unless deck cap requires reduction.
    Bit depth and sample rate: only reduce, never inflate."""

    def test_44_1k_16_passthrough_quality(self):
        # 44.1k/16 to a CDJ-3000-tier deck: no change.
        assert plan_conversion("flac", 44100, 16, 96000, 24) == (44100, 16)

    def test_96k_24_preserved_when_deck_supports(self):
        # 96k/24 to CDJ-3000: stays 96k/24 (the bug this fixes).
        assert plan_conversion("flac", 96000, 24, 96000, 24) == (96000, 24)

    def test_96k_24_capped_to_48k_24_for_older_deck(self):
        # 96k/24 to XDJ-RX3 (48k/24): rate steps down, depth preserved.
        assert plan_conversion("flac", 96000, 24, 48000, 24) == (48000, 24)

    def test_96k_24_capped_to_48k_16_for_oldest_flac_deck(self):
        assert plan_conversion("flac", 96000, 24, 48000, 16) == (48000, 16)

    def test_44_1k_24_preserved(self):
        # Don't upsample 44.1k -> 48k just because the deck allows it.
        assert plan_conversion("flac", 44100, 24, 96000, 24) == (44100, 24)


class TestPlanConversionAIFF:
    """AIFF defaults to 16-bit when source depth is unknown (likely lossy
    origin) and has no codec-side rate ceiling."""

    def test_44_1k_16_passthrough(self):
        assert plan_conversion("aiff", 44100, 16, 48000, 24) == (44100, 16)

    def test_unknown_depth_defaults_to_16(self):
        # Lossy source (MP3) carries no bit depth -> AIFF lands at 16-bit.
        assert plan_conversion("aiff", 44100, None, 48000, 24) == (44100, 16)

    def test_96k_24_capped_to_48k_24(self):
        assert plan_conversion("aiff", 96000, 24, 48000, 24) == (48000, 24)

    def test_24_bit_capped_to_16_bit(self):
        assert plan_conversion("aiff", 44100, 24, 48000, 16) == (44100, 16)


class TestCanPassthrough:
    """Passthrough is allowed only when source is already what we'd produce:
    same codec family, within sample-rate cap, within bit-depth cap."""

    def test_flac_to_flac_same_quality(self):
        assert can_passthrough("flac", "flac", 44100, 16, 44100, 16) is True

    def test_flac_to_flac_source_below_target(self):
        # 44.1k/16 source with deck cap 48k/24: copying the 44.1k/16 is fine.
        assert can_passthrough("flac", "flac", 44100, 16, 48000, 24) is True

    def test_flac_to_flac_source_above_target_refuse(self):
        # 96k source but plan says 48k -> must re-encode.
        assert can_passthrough("flac", "flac", 96000, 24, 48000, 24) is False

    def test_mp3_to_mp3_no_depth_axis(self):
        assert can_passthrough("mp3", "mp3", 44100, None, 44100, None) is True

    def test_mp3_to_flac_refuse(self):
        # Different codec family -- can't just copy bytes.
        assert can_passthrough("flac", "mp3", 44100, None, 44100, 16) is False

    def test_aiff_pcm_24_to_aiff(self):
        assert can_passthrough("aiff", "pcm_s24be", 44100, 24, 44100, 24) is True

    def test_no_source_codec_refuse(self):
        # Probe failed -- we can't prove codec match.
        assert can_passthrough("flac", None, 44100, 16, 44100, 16) is False

    def test_unknown_source_depth_for_lossless_refuse(self):
        # Lossless target needs known source depth to prove it fits the cap.
        assert can_passthrough("flac", "flac", 44100, None, 44100, 16) is False


class TestExistingMatchesPlan:
    """Existing output is reused only if its rate/depth matches the current
    plan. Different deck or format between runs -> re-encode."""

    def test_match_exact(self):
        assert existing_matches_plan("flac", 44100, 16, 44100, 16) is True

    def test_rate_mismatch_re_encode(self):
        assert existing_matches_plan("flac", 48000, 16, 44100, 16) is False

    def test_depth_mismatch_re_encode(self):
        # User changed deck from 16-bit-capped to 24-bit-capped.
        assert existing_matches_plan("flac", 44100, 16, 44100, 24) is False

    def test_mp3_ignores_depth(self):
        assert existing_matches_plan("mp3", 44100, None, 44100, None) is True

    def test_no_existing_probe_re_encode(self):
        # We couldn't probe the existing file (e.g. corrupt).
        assert existing_matches_plan("flac", None, None, 44100, 16) is False

    def test_no_target_re_encode(self):
        # Source probe failed -> we don't know the target -> re-encode.
        assert existing_matches_plan("flac", 44100, 16, None, None) is False
