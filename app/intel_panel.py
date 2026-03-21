"""
Intelligence Panel — Tab 2 of HoloIntel.

Rich HoloViz charts for:
  • Energy Markets   — Brent / WTI / Henry Hub trend (area chart)
  • Market Watch     — major indices % change (horizontal bar)
  • Nuclear Monitor  — Safecast CPM by site (bar + severity colors)
  • Macro Risk       — VIX + yield curve normalised (area overlay)
  • Space Activity   — active satellite counts (bar)
  • Sanctions        — OFAC SDN stat card
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import holoviews as hv
import panel as pn
import hvplot.pandas  # noqa: F401 — registers .hvplot accessor

from data.context import (
    load_macro,
    load_market_sample,
    load_safecast_sample,
    load_ofac_sample,
    load_space_sample,
)

# ── Palette / style constants ─────────────────────────────────────────────────
_BG      = "#0a0f1e"
_CARD_BG = "#0c1524"
_BORDER  = "#1e3a5f"
_ACCENT  = "#7dd3fc"
_MUTED   = "#475569"
_TEXT    = "#e2e8f0"
_SUB     = "#94a3b8"

_HDR_CSS = (
    "font-size:10px;font-weight:bold;color:{a};"
    "letter-spacing:2px;text-transform:uppercase;"
    "margin-bottom:10px;font-family:'Courier New',monospace;"
).format(a=_ACCENT)

_CARD_STYLE = {
    "background":    _CARD_BG,
    "border":        f"1px solid {_BORDER}",
    "border-radius": "6px",
    "padding":       "16px 18px",
}

# Common hvplot kwargs forwarded to Bokeh
_PLOT_KW = dict(
    responsive=True,
    height=230,
    grid=True,
    fontscale=0.85,
)

_ENERGY_COLORS = ["#f97316", "#ef4444", "#38bdf8", "#a78bfa", "#22d3ee"]
_MACRO_COLORS  = ["#f43f5e", "#7dd3fc"]


# ── Layout helpers ────────────────────────────────────────────────────────────
def _section(label: str) -> pn.pane.HTML:
    return pn.pane.HTML(
        f'<div style="{_HDR_CSS}">{label}</div>',
        sizing_mode="stretch_width", height=28,
    )


def _card(title: str, *content) -> pn.Column:
    return pn.Column(
        _section(title),
        *content,
        sizing_mode="stretch_both",
        styles=_CARD_STYLE,
        min_height=290,
    )


def _no_data(msg: str = "No data available") -> pn.pane.HTML:
    return pn.pane.HTML(
        f'<div style="color:{_MUTED};font-size:12px;padding:36px 0;'
        f'text-align:center;font-family:\'Courier New\',monospace;">{msg}</div>',
        sizing_mode="stretch_width",
    )


def _hv_panel(chart: hv.core.ViewableElement) -> pn.pane.HoloViews:
    return pn.pane.HoloViews(chart, sizing_mode="stretch_both", min_height=230)


# ── Chart builders ────────────────────────────────────────────────────────────
def _energy_chart() -> pn.viewable.Viewable:
    try:
        macro = load_macro()
        # Accept both live (Brent/WTI/HenryHub) and fallback (Brent Crude/Gold/USD)
        energy = macro[~macro["metric"].isin(["VIX", "T10Y2Y", "TotalDebtTrillion"])].copy()
        if energy.empty:
            return _no_data("EIA / FRED energy data unavailable")

        # Shorten names: "Brent Crude (USD/bbl)" → "Brent Crude"
        energy["label"] = (
            energy["metric"]
            .str.replace(r"\s*\(.*?\)", "", regex=True)
            .str.strip()
        )
        energy = energy.sort_values("date")

        chart = energy.hvplot.area(
            x="date", y="value", by="label",
            alpha=0.3, line_width=2,
            color=_ENERGY_COLORS,
            ylabel="USD", xlabel="",
            legend="top_left",
            **_PLOT_KW,
        )
        return _hv_panel(chart)
    except Exception:
        return _no_data("Energy data load failed")


def _market_chart() -> pn.viewable.Viewable:
    try:
        market = load_market_sample()
        if market.empty:
            return _no_data("Market data unavailable")
        market = market.sort_values("change_pct").copy()

        # Symmetric clim so RdYlGn is anchored at 0
        clim = max(abs(float(market["change_pct"].min())),
                   abs(float(market["change_pct"].max())), 0.01)

        chart = market.hvplot.barh(
            x="symbol", y="change_pct",
            c="change_pct", cmap="RdYlGn",
            clim=(-clim, clim),
            colorbar=False,
            xlabel="Δ% (1 day)", ylabel="",
            **_PLOT_KW,
        )
        return _hv_panel(chart)
    except Exception:
        return _no_data("Market data load failed")


def _radiation_chart() -> pn.viewable.Viewable:
    try:
        rad = load_safecast_sample()
        if rad.empty:
            return _no_data("Safecast data unavailable")

        latest = (
            rad.sort_values("date")
               .groupby("site", as_index=False)
               .last()
        )
        if latest.empty:
            return _no_data("No radiation readings found")

        clim = (0.0, max(float(latest["cpm"].max()), 1.0))
        chart = latest.hvplot.bar(
            x="site", y="cpm",
            c="cpm", cmap="RdYlGn_r",
            clim=clim,
            colorbar=False,
            xlabel="", ylabel="CPM (counts per min)",
            rot=20,
            **_PLOT_KW,
        )
        return _hv_panel(chart)
    except Exception:
        return _no_data("Radiation data load failed")


def _macro_chart() -> pn.viewable.Viewable:
    try:
        macro = load_macro()
        risk = macro[macro["metric"].isin(["VIX", "T10Y2Y"])].copy()
        if risk.empty:
            return _no_data("FRED key required — set FRED_API_KEY for VIX / yield curve")

        risk = risk.sort_values("date")
        # Normalise each series to 0–100 so both fit on one axis
        normalised: list[pd.DataFrame] = []
        for m, grp in risk.groupby("metric"):
            g = grp.copy()
            mn, mx = g["value"].min(), g["value"].max()
            g["norm"] = (g["value"] - mn) / (mx - mn) * 100 if mx > mn else 50.0
            g["label"] = m
            normalised.append(g)
        risk = pd.concat(normalised, ignore_index=True)

        chart = risk.hvplot.area(
            x="date", y="norm", by="label",
            alpha=0.35, line_width=2,
            color=_MACRO_COLORS,
            ylabel="Normalised (0–100)", xlabel="",
            legend="top_right",
            **_PLOT_KW,
        )
        return _hv_panel(chart)
    except Exception:
        return _no_data("Macro risk data load failed")


def _space_chart() -> pn.viewable.Viewable:
    try:
        space = load_space_sample()
        if space.empty:
            return _no_data("Celestrak data unavailable")

        chart = space.hvplot.bar(
            x="constellation", y="active",
            c="active", cmap="Blues",
            colorbar=False,
            xlabel="", ylabel="Active Satellites",
            **_PLOT_KW,
        )
        return _hv_panel(chart)
    except Exception:
        return _no_data("Space data load failed")


def _sanctions_card() -> pn.viewable.Viewable:
    try:
        ofac = load_ofac_sample()
        row = ofac.iloc[0]
        updated  = row.get("updated",          "N/A")
        program  = row.get("program",          "SDN")
        new_ent  = int(row.get("new_entities", 0))
        country  = row.get("high_risk_country","Mixed")

        html = f"""
        <div style="font-family:'Courier New',monospace;font-size:12px;
                    line-height:2.4;color:{_TEXT};padding:8px 0;">
          <div>
            <span style="color:{_MUTED};">Program&nbsp;&nbsp;&nbsp;&nbsp;</span>
            <span style="color:#f97316;font-weight:bold;">{program}</span>
          </div>
          <div>
            <span style="color:{_MUTED};">Updated&nbsp;&nbsp;&nbsp;&nbsp;</span>
            <span style="color:{_ACCENT};">{updated}</span>
          </div>
          <div style="margin-top:12px;">
            <span style="color:{_MUTED};font-size:11px;">NEW DESIGNATIONS</span><br>
            <span style="font-size:44px;font-weight:bold;color:#f43f5e;
                         line-height:1.1;">{new_ent}</span>
          </div>
          <div style="margin-top:12px;">
            <span style="color:{_MUTED};">High-Risk &nbsp;&nbsp;&nbsp;</span>
            <span style="color:#facc15;">{country}</span>
          </div>
        </div>
        """
        return pn.pane.HTML(html, sizing_mode="stretch_width")
    except Exception:
        return _no_data("OFAC data unavailable")


# ── Ticker strip (energy + market prices as a single-line HTML bar) ───────────
def _price_ticker() -> pn.pane.HTML:
    """A compact live-price strip that sits below the tab header."""
    try:
        market = load_market_sample()
        macro  = load_macro()

        items: list[str] = []

        # Energy spot prices
        for metric in ["Brent", "WTI", "HenryHub", "Brent Crude (USD/bbl)"]:
            sub = macro[macro["metric"].str.startswith(metric.split()[0])]
            if sub.empty:
                continue
            val = sub.sort_values("date").iloc[-1]["value"]
            short = "Brent" if "Brent" in metric else "WTI" if "WTI" in metric else "Gas"
            items.append(
                f'<span style="color:{_MUTED};">{short}&nbsp;</span>'
                f'<span style="color:{_ACCENT};font-weight:bold;">${val:.1f}</span>'
            )

        # Market % changes
        for _, row in market.iterrows():
            sym = row["symbol"]
            pct = row["change_pct"]
            color = "#22c55e" if pct >= 0 else "#f43f5e"
            arrow = "▲" if pct >= 0 else "▼"
            items.append(
                f'<span style="color:{_MUTED};">{sym}&nbsp;</span>'
                f'<span style="color:{color};">{arrow}{abs(pct):.2f}%</span>'
            )

        strip = '&nbsp;&nbsp;|&nbsp;&nbsp;'.join(items)
        return pn.pane.HTML(
            f'<div style="background:#070d1a;border-bottom:1px solid {_BORDER};'
            f'padding:6px 20px;font-family:\'Courier New\',monospace;font-size:11px;'
            f'white-space:nowrap;overflow:hidden;">{strip}</div>',
            sizing_mode="stretch_width", height=32,
        )
    except Exception:
        return pn.pane.HTML("", height=0)


# ── Main panel builder ────────────────────────────────────────────────────────
def build_intel_tab() -> pn.Column:
    """Assemble the Intelligence tab with HoloViz charts."""

    ticker = _price_ticker()

    # Row 1: Energy Markets full-width
    row1 = pn.Row(
        _card("Energy Markets — Brent / WTI / Henry Hub", _energy_chart()),
        sizing_mode="stretch_width",
        min_height=300,
    )

    # Row 2: Market Watch | Nuclear Monitoring
    row2 = pn.Row(
        _card("Market Watch — 1-Day Change %", _market_chart()),
        _card("Nuclear Site Radiation — Safecast CPM", _radiation_chart()),
        sizing_mode="stretch_width",
        min_height=300,
    )

    # Row 3: Macro Risk | Satellite Activity
    row3 = pn.Row(
        _card("Macro Risk — VIX / Yield Curve (Normalised)", _macro_chart()),
        _card("Active Satellite Constellations", _space_chart()),
        sizing_mode="stretch_width",
        min_height=300,
    )

    # Row 4: OFAC Sanctions (half-width card)
    row4 = pn.Row(
        _card("OFAC Sanctions Intelligence", _sanctions_card()),
        pn.Spacer(sizing_mode="stretch_width"),
        sizing_mode="stretch_width",
        min_height=260,
    )

    return pn.Column(
        ticker,
        row1, row2, row3, row4,
        sizing_mode="stretch_both",
        scroll=True,
        styles={
            "background": _BG,
            "padding": "0 16px 16px 16px",
            "gap": "14px",
        },
    )
