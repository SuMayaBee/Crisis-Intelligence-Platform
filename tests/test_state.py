"""Tests for DashboardState.filtered_events."""
import pandas as pd
import pytest


def _make_events(rows):
    return pd.DataFrame(
        [
            {
                "source": src,
                "timestamp": pd.Timestamp(ts, tz="UTC"),
                "severity": sev,
                "region": region,
                "lat": 0.0,
                "lon": 0.0,
                "category": "Fight",
                "title": "Test",
                "details": "",
                "evidence_url": "",
            }
            for src, ts, sev, region in rows
        ]
    )


@pytest.fixture
def sample_events():
    now = pd.Timestamp.now(tz="UTC")
    return _make_events([
        ("GDELT",  str(now - pd.Timedelta(days=1)),  3, "Europe"),
        ("FIRMS",  str(now - pd.Timedelta(days=2)),  2, "Asia"),
        ("GDELT",  str(now - pd.Timedelta(days=3)),  5, "Middle East"),
        ("OpenSky",str(now - pd.Timedelta(days=400)), 1, "Africa"),  # outside lookback window
    ])


def test_filtered_events_default_all(sample_events):
    from state import DashboardState
    state = DashboardState(events=sample_events)
    filtered = state.filtered_events()
    # Lookback window is 10800 hours = 450 days from the max timestamp.
    # All 4 events are within 450 days of the newest event (1 day ago).
    assert len(filtered) == 4


def test_filtered_events_by_severity(sample_events):
    from state import DashboardState
    state = DashboardState(events=sample_events)
    state.min_severity = 4
    filtered = state.filtered_events()
    assert all(filtered["severity"] >= 4)
    assert len(filtered) == 1


def test_filtered_events_by_source(sample_events):
    from state import DashboardState
    state = DashboardState(events=sample_events)
    state.source_filter = ["GDELT"]
    filtered = state.filtered_events()
    assert set(filtered["source"].unique()) == {"GDELT"}


def test_filtered_events_by_region(sample_events):
    from state import DashboardState
    state = DashboardState(events=sample_events)
    state.region_filter = ["Europe", "Asia"]
    filtered = state.filtered_events()
    assert set(filtered["region"].unique()).issubset({"Europe", "Asia"})


def test_filtered_events_empty_df():
    from state import DashboardState
    empty = pd.DataFrame(columns=["source", "timestamp", "severity", "region",
                                   "lat", "lon", "category", "title", "details", "evidence_url"])
    state = DashboardState(events=empty)
    assert state.filtered_events().empty
