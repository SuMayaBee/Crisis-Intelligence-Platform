"""Tests for data/context.py loaders — fallback behaviour and data shape."""
import math
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


# ── load_fx_live ──────────────────────────────────────────────────────────────

def test_load_fx_live_fallback_on_request_error():
    """When HTTP requests fail, load_fx_live must return a non-empty fallback DataFrame."""
    with patch("data.context._safe_get_json", side_effect=Exception("network error")):
        from data.context import load_fx_live
        df = load_fx_live()
    assert not df.empty
    assert {"pair", "rate", "change_pct"}.issubset(df.columns)
    assert (df["rate"] > 0).all()


def test_load_fx_live_fallback_on_api_failure():
    """When the API returns success=False, should use the fallback."""
    with patch("data.context._safe_get_json", return_value={"success": False}):
        from data.context import load_fx_live
        df = load_fx_live()
    assert not df.empty
    assert "pair" in df.columns


def test_load_fx_live_parses_live_response():
    """When the API returns valid data, parse it correctly."""
    live_resp = {
        "success": True,
        "quotes": {"USDEUR": 0.924, "USDGBP": 0.785},
    }
    prev_resp = {
        "success": True,
        "quotes": {"USDEUR": 0.920, "USDGBP": 0.780},
    }
    responses = [live_resp, prev_resp]
    with patch("data.context._safe_get_json", side_effect=responses):
        from data.context import load_fx_live
        df = load_fx_live(currencies=["EUR", "GBP"])
    assert len(df) == 2
    eur = df[df["pair"] == "USD/EUR"].iloc[0]
    assert eur["rate"] == pytest.approx(0.924)
    expected_pct = ((0.924 - 0.920) / 0.920) * 100
    assert eur["change_pct"] == pytest.approx(expected_pct, abs=0.01)


# ── load_fx_history ───────────────────────────────────────────────────────────

def test_load_fx_history_fallback():
    """When API fails, returns synthetic fallback rows for the date range."""
    with patch("data.context._safe_get_json", side_effect=Exception("error")):
        from data.context import load_fx_history
        df = load_fx_history("2025-01-01", "2025-01-10", currencies=["EUR", "GBP"])
    assert not df.empty
    assert {"date", "currency", "rate"}.issubset(df.columns)
    assert (df["rate"] > 0).all()


# ── load_commodities_history ──────────────────────────────────────────────────

def test_load_commodities_history_fallback():
    """When Yahoo Finance is unreachable, fallback provides synthetic history."""
    with patch("data.context._safe_get_json", side_effect=Exception("timeout")):
        from data.context import load_commodities_history
        # Clear pn.cache if present — call the underlying function directly
        fn = load_commodities_history
        if hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        df = fn()
    assert not df.empty
    assert {"date", "commodity", "price"}.issubset(df.columns)
    # Prices should be positive
    assert (df["price"] > 0).all()


def test_load_commodities_history_shape():
    """Fallback data should cover at least 8 commodities and 50+ rows."""
    with patch("data.context._safe_get_json", side_effect=Exception("timeout")):
        from data.context import load_commodities_history
        fn = load_commodities_history
        if hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        df = fn()
    assert df["commodity"].nunique() >= 8
    assert len(df) >= 50


# ── load_currency_rates ───────────────────────────────────────────────────────

def test_load_currency_rates_fallback():
    """When Yahoo Finance is down, returns a well-formed fallback."""
    with patch("data.context._safe_get_json", side_effect=Exception("error")):
        from data.context import load_currency_rates
        df = load_currency_rates()
    assert not df.empty
    assert {"pair", "rate", "change_pct"}.issubset(df.columns)
    assert len(df) >= 5


# ── load_ticker_search ────────────────────────────────────────────────────────

def test_load_ticker_search_returns_list():
    mock_resp = {
        "quotes": [
            {"symbol": "AAPL", "shortname": "Apple Inc.", "quoteType": "EQUITY"},
            {"symbol": "AAPL.L", "shortname": "Apple London", "quoteType": "EQUITY"},
        ]
    }
    with patch("data.context._safe_get_json", return_value=mock_resp):
        from data.context import load_ticker_search
        results = load_ticker_search("apple")
    assert isinstance(results, list)
    assert any("AAPL" in r for r in results)


def test_load_ticker_search_empty_on_error():
    with patch("data.context._safe_get_json", side_effect=Exception("error")):
        from data.context import load_ticker_search
        results = load_ticker_search("anything")
    assert results == []
