"""Tests for utility functions in data/events.py."""
import pandas as pd
import pytest
from data.events import _safe_to_datetime, _try_load


# ── _safe_to_datetime ─────────────────────────────────────────────────────────

def test_safe_to_datetime_valid():
    s = pd.Series(["2025-01-01", "2024-06-15"])
    result = _safe_to_datetime(s)
    assert result.notna().all()
    assert str(result.dt.tz) == "UTC"


def test_safe_to_datetime_invalid_becomes_nat():
    s = pd.Series(["not-a-date", "also-bad"])
    result = _safe_to_datetime(s)
    assert result.isna().all()


def test_safe_to_datetime_mixed():
    s = pd.Series(["2025-01-01", "garbage", "2024-12-31"])
    result = _safe_to_datetime(s)
    assert result.notna().sum() == 2
    assert result.isna().sum() == 1


# ── _try_load ─────────────────────────────────────────────────────────────────

def test_try_load_uses_live_data_when_available():
    live_df = pd.DataFrame([{"source": "GDELT", "value": 1}])
    fallback_df = pd.DataFrame([{"source": "fallback", "value": 0}])

    result = _try_load(lambda: live_df, lambda: fallback_df, "GDELT")
    assert result["source"].iloc[0] == "GDELT"


def test_try_load_falls_back_on_exception():
    fallback_df = pd.DataFrame([{"source": "fallback", "value": 0}])

    def boom():
        raise RuntimeError("network error")

    result = _try_load(boom, lambda: fallback_df, "GDELT")
    assert result["source"].iloc[0] == "fallback"


def test_try_load_falls_back_on_empty_df():
    """If the live loader returns an empty DataFrame, fallback is used."""
    fallback_df = pd.DataFrame([{"source": "fallback", "value": 0}])

    result = _try_load(lambda: pd.DataFrame(), lambda: fallback_df, "GDELT")
    assert result["source"].iloc[0] == "fallback"
