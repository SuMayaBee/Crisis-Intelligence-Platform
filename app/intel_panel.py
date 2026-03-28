"""
Commodities and Currency FX panels — Tabs 2 & 3.

  • Commodities — 30-day indexed performance with interactive date range selector
  • Currency FX  — 1-day % change vs USD, horizontal bar chart
"""
from __future__ import annotations

import pandas as pd
import panel as pn
import hvplot.pandas  # noqa: F401 — registers .hvplot accessor


from data.context import (
    load_commodities_history,
    load_fx_live,
    FX_REGION_GROUPS,
)

# ── Style constants ────────────────────────────────────────────────────────────
_BG     = "#0a0f1e"
_BORDER = "#1e3a5f"
_ACCENT = "#7dd3fc"
_MUTED  = "#475569"

_HDR_CSS = (
    "font-size:13px;font-weight:bold;color:{a};"
    "letter-spacing:2px;text-transform:uppercase;"
    "font-family:'Courier New',monospace;padding:16px 16px 10px;"
).format(a=_ACCENT)

_COMMODITY_ORDER = [
    "Gold", "Global Oil Price", "US Oil Price",
    "Natural Gas", "Wheat", "Copper", "Silver", "Palladium",
]

_COMMODITY_COLORS = [
    "#facc15", "#ef4444", "#f97316",   # Gold / Global Oil Price / US Oil Price
    "#38bdf8", "#86efac", "#fb923c",   # Natural Gas / Wheat / Copper
    "#94a3b8", "#c084fc",               # Silver / Palladium
]

_PLOT_KW = dict(responsive=True, height=520, grid=True, fontscale=1.2)


def _no_data(msg: str) -> pn.pane.HTML:
    return pn.pane.HTML(
        f'<div style="color:{_MUTED};font-size:13px;padding:80px 0;'
        f'text-align:center;font-family:\'Courier New\',monospace;">{msg}</div>',
        sizing_mode="stretch_both",
    )


def _header(title: str) -> pn.pane.HTML:
    return pn.pane.HTML(
        f'<div style="{_HDR_CSS}">{title}</div>',
        sizing_mode="stretch_width", height=46,
    )


# ── Commodities Tab ────────────────────────────────────────────────────────────
def build_commodities_tab() -> pn.Column:
    df = load_commodities_history()

    if df.empty:
        return pn.Column(
            _header("Commodities — 30-Day Indexed Performance (Base 100)"),
            _no_data("Commodity data unavailable"),
            sizing_mode="stretch_both",
            styles={"background": _BG},
        )

    df = df.sort_values("date")
    today     = pd.Timestamp.now().date()
    one_yr_ago = (pd.Timestamp.now() - pd.DateOffset(years=1)).date()

    start_picker = pn.widgets.DatePicker(
        name="From", value=one_yr_ago, width=160,
    )
    end_picker = pn.widgets.DatePicker(
        name="To", value=today, width=160,
    )
    date_row = pn.Row(
        start_picker, end_picker,
        styles={"padding": "0 16px 8px"},
    )

    def _make_chart(start_date, end_date):
        if start_date is None or end_date is None:
            return _no_data("Select a date range above")
        start = pd.Timestamp(start_date)
        end   = pd.Timestamp(end_date) + pd.Timedelta(days=1)  # inclusive end
        if start >= end:
            return _no_data("Start date must be before end date")
        filtered = df[(df["date"] >= start) & (df["date"] < end)].copy()

        if filtered.empty:
            return _no_data("No data available for selected range")

        # Re-normalise to 100 at the start of the selected window
        frames = []
        for commodity, grp in filtered.groupby("commodity"):
            g = grp.sort_values("date").copy()
            first = g["price"].iloc[0]
            g["indexed"] = (g["price"] / first * 100).round(2) if first else 100.0
            frames.append(g)
        normed = pd.concat(frames, ignore_index=True)

        # Pivot to wide format so column order controls legend order exactly
        wide = normed.pivot(index="date", columns="commodity", values="indexed")
        ordered_cols = [c for c in _COMMODITY_ORDER if c in wide.columns]
        wide = wide[ordered_cols].reset_index()

        chart = wide.hvplot.line(
            x="date", y=ordered_cols,
            line_width=2,
            color=_COMMODITY_COLORS[:len(ordered_cols)],
            ylabel="Indexed (base 100)", xlabel="",
            legend="top_left",
            **_PLOT_KW,
        )
        return pn.pane.HoloViews(chart, sizing_mode="stretch_both")

    chart_pane = pn.bind(_make_chart, start_picker.param.value, end_picker.param.value)

    return pn.Column(
        date_row,
        pn.panel(chart_pane, sizing_mode="stretch_both"),
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )


# ── Currency FX Tab ────────────────────────────────────────────────────────────
def build_currency_tab() -> pn.Column:
    region_select = pn.widgets.Select(
        name="Region",
        options=list(FX_REGION_GROUPS.keys()),
        value="Geopolitical",
        width=200,
    )

    def _live_bar(region):
        try:
            codes = FX_REGION_GROUPS.get(region, [])
            fx = load_fx_live(codes).sort_values("change_pct")
            fx["Change (%)"] = fx["change_pct"].map(lambda x: f"{x:+.3f}%")
            clim = max(abs(float(fx["change_pct"].min())),
                       abs(float(fx["change_pct"].max())), 0.01)
            h = max(260, len(codes) * 32)
            chart = fx.hvplot.barh(
                x="pair", y="change_pct",
                c="change_pct", cmap="RdYlGn",
                clim=(-clim, clim), colorbar=False,
                xlim=(-clim, clim),
                hover_cols=["Change (%)"],
                xlabel="1-day % change vs USD",
                ylabel="",
                responsive=True, height=h, grid=True, fontscale=0.9,
            )
            return pn.pane.HoloViews(chart, sizing_mode="stretch_both", min_height=h)
        except Exception:
            return _no_data("Live FX unavailable")

    live_pane = pn.bind(_live_bar, region_select.param.value)

    return pn.Column(
        _header("Currency FX — 1-Day Change % vs USD"),
        pn.Row(
            region_select,
            pn.pane.HTML(
                f'<div style="font-size:10px;color:{_MUTED};font-family:\'Courier New\',monospace;'
                f'padding:22px 0 0 12px;">Select region to filter currencies</div>',
                sizing_mode="stretch_width",
            ),
            styles={"padding": "0 16px 12px"},
        ),
        pn.pane.HTML(
            f'<div style="font-size:11px;color:{_MUTED};font-family:\'Courier New\',monospace;'
            f'padding:0 16px 8px;">'
            f'🟢 positive = USD strengthened (local currency weakened) &nbsp;·&nbsp; '
            f'🔴 negative = USD weakened (local currency strengthened)'
            f'</div>',
            sizing_mode="stretch_width",
        ),
        pn.panel(live_pane, sizing_mode="stretch_both"),
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )

