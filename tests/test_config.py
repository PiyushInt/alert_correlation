"""Tests for config.py — guards against silent scale mistakes."""

from ace.config import settings


def test_fuzzy_match_threshold_is_on_rapidfuzz_scale() -> None:
    """
    FUZZY_MATCH_THRESHOLD must be on the rapidfuzz 0-100 scale.
    A value < 1 (e.g. 0.85) means 'match everything' because rapidfuzz
    scores are 0-100, and 0.85 out of 100 is effectively zero.
    """
    assert 1 <= settings.FUZZY_MATCH_THRESHOLD <= 100, (
        f"FUZZY_MATCH_THRESHOLD={settings.FUZZY_MATCH_THRESHOLD} is not on the "
        f"rapidfuzz 0-100 scale. A value < 1 silently disables the threshold."
    )
