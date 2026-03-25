"""Tests for compute_changes and compute_risk_by_region."""
import pandas as pd
import pytest
from data.analytics import compute_changes, compute_risk_by_region


def _make_events(rows):
    """Helper: list of (source, timestamp, severity, region) → DataFrame.
    timestamp may be a tz-aware Timestamp or a date string.
    """
    def _to_ts(ts):
        if isinstance(ts, pd.Timestamp):
            return ts if ts.tzinfo is not None else ts.tz_localize("UTC")
        return pd.Timestamp(ts, tz="UTC")

    return pd.DataFrame(
        [
            {
                "source": src,
                "timestamp": _to_ts(ts),
                "severity": sev,
                "region": region,
            }
            for src, ts, sev, region in rows
        ]
    )


# ── compute_changes ────────────────────────────────────────────────────────────

def test_compute_changes_empty():
    df = compute_changes(pd.DataFrame(columns=["source", "timestamp", "severity", "region"]), window_hours=24)
    assert list(df.columns) == ["source", "current", "previous", "delta"]
    assert len(df) == 0


def test_compute_changes_basic():
    now = pd.Timestamp.now(tz="UTC")
    # end_time = now-1h; start_current = now-25h; start_previous = now-49h
    rows = [
        # current window [now-25h, now-1h]
        ("GDELT", now - pd.Timedelta(hours=1),  3, "Europe"),
        ("GDELT", now - pd.Timedelta(hours=2),  4, "Africa"),
        # previous window [now-49h, now-25h)  — use -26h to be strictly < start_current
        ("GDELT", now - pd.Timedelta(hours=26), 3, "Europe"),
        ("FIRMS", now - pd.Timedelta(hours=30), 2, "Asia"),
    ]
    df = _make_events(rows)
    result = compute_changes(df, window_hours=24)

    gdelt_row = result[result["source"] == "GDELT"].iloc[0]
    assert gdelt_row["current"] == 2
    assert gdelt_row["previous"] == 1
    assert gdelt_row["delta"] == 1

    firms_row = result[result["source"] == "FIRMS"].iloc[0]
    assert firms_row["current"] == 0
    assert firms_row["previous"] == 1
    assert firms_row["delta"] == -1


def test_compute_changes_sorted_descending():
    now = pd.Timestamp.now(tz="UTC")
    rows = [
        ("GDELT", now - pd.Timedelta(hours=1), 3, "Europe"),
        ("GDELT", now - pd.Timedelta(hours=2), 3, "Europe"),
        ("GDELT", now - pd.Timedelta(hours=3), 3, "Europe"),
        ("FIRMS", now - pd.Timedelta(hours=1), 2, "Asia"),
    ]
    df = _make_events(rows)
    result = compute_changes(df, window_hours=24)
    # All events are in current window, none in previous → all delta ≥ 0
    assert (result["delta"] >= 0).all()
    # Sorted descending by delta
    assert result["delta"].is_monotonic_decreasing


# ── compute_risk_by_region ────────────────────────────────────────────────────

def test_compute_risk_empty():
    df = compute_risk_by_region(pd.DataFrame(columns=["source", "timestamp", "severity", "region"]))
    assert list(df.columns) == ["region", "event_count", "avg_severity", "risk_score"]
    assert len(df) == 0


def test_compute_risk_basic():
    now = pd.Timestamp.now(tz="UTC")
    rows = [
        ("GDELT", now, 5, "Middle East"),
        ("GDELT", now, 4, "Middle East"),
        ("FIRMS", now, 2, "Africa"),
    ]
    df = _make_events(rows)
    result = compute_risk_by_region(df)

    me = result[result["region"] == "Middle East"].iloc[0]
    assert me["event_count"] == 2
    assert me["avg_severity"] == pytest.approx(4.5)
    assert me["risk_score"] > 0

    # Middle East has higher severity → should rank above Africa (which has sev=2)
    assert result.iloc[0]["region"] == "Middle East"


def test_compute_risk_score_increases_with_events():
    """More events in the same region → higher risk score."""
    now = pd.Timestamp.now(tz="UTC")
    rows_small = [("GDELT", now, 3, "Europe")]
    rows_large = [("GDELT", now, 3, "Europe")] * 10
    small = compute_risk_by_region(_make_events(rows_small))
    large = compute_risk_by_region(_make_events(rows_large))
    assert large.iloc[0]["risk_score"] > small.iloc[0]["risk_score"]
