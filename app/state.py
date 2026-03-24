"""DashboardState — reactive params for the combined risk map."""
from __future__ import annotations

import pandas as pd
import panel as pn
import param

# All sources the map can show (order matters for legend)
ALL_SOURCES = ["GDELT", "FIRMS", "OpenSky", "NOAA",
               "Maritime", "Rocket", "Seismic", "Cyber"]


class DashboardState(param.Parameterized):
    source_filter = param.ListSelector(default=[], label="Sources")
    min_severity  = param.Integer(default=1, bounds=(1, 5), label="Min Severity")
    region_filter = param.ListSelector(default=[], label="Regions")

    _LOOKBACK_HOURS = 10800  # 450 days — matches ACLED fetch window

    def __init__(self, events: pd.DataFrame, **params):
        super().__init__(**params)
        self.events = events

        self.param.source_filter.objects = ALL_SOURCES
        self.source_filter = list(ALL_SOURCES)

        self.param.region_filter.objects = sorted(
            events["region"].dropna().unique().tolist()
        )
        self.region_filter = list(self.param.region_filter.objects)

    def filtered_events(self) -> pd.DataFrame:
        if self.events.empty:
            return self.events
        ts = pd.to_datetime(self.events["timestamp"], utc=True, errors="coerce")
        end_time   = ts.max()
        start_time = end_time - pd.Timedelta(hours=self._LOOKBACK_HOURS)
        return self.events[
            (ts >= start_time)
            & (ts <= end_time)
            & (self.events["severity"] >= self.min_severity)
            & (self.events["source"].isin(self.source_filter))
            & (self.events["region"].isin(self.region_filter))
        ].copy()

    @pn.depends("source_filter", "min_severity", "region_filter")
    def map_panel(self) -> pn.viewable.Viewable:
        from map_panel import build_combined_map
        return build_combined_map(self.filtered_events())
