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
    load_ohlcv,
    FX_REGION_GROUPS,
)

# ── Style constants ────────────────────────────────────────────────────────────
_BG     = "#0a0f1e"
_BORDER = "#1e3a5f"
_ACCENT = "#7dd3fc"
_MUTED  = "#475569"

_HDR_CSS = (
    "font-size:10px;font-weight:bold;color:{a};"
    "letter-spacing:2px;text-transform:uppercase;"
    "font-family:'Courier New',monospace;padding:16px 16px 10px;"
).format(a=_ACCENT)

_COMMODITY_COLORS = [
    "#f97316", "#ef4444", "#38bdf8",   # WTI / Brent / Nat Gas
    "#facc15", "#94a3b8", "#c084fc",   # Gold / Silver / Palladium
    "#86efac", "#fb923c",               # Wheat / Copper
]

_PLOT_KW = dict(responsive=True, height=520, grid=True, fontscale=0.9)


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

        chart = normed.hvplot.line(
            x="date", y="indexed", by="commodity",
            line_width=2,
            color=_COMMODITY_COLORS,
            ylabel="Indexed (base 100)", xlabel="",
            legend="top_left",
            **_PLOT_KW,
        )
        return pn.pane.HoloViews(chart, sizing_mode="stretch_both")

    chart_pane = pn.bind(_make_chart, start_picker.param.value, end_picker.param.value)

    return pn.Column(
        _header("Commodities — 30-Day Indexed Performance (Base 100)"),
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
            clim = max(abs(float(fx["change_pct"].min())),
                       abs(float(fx["change_pct"].max())), 0.01)
            h = max(260, len(codes) * 32)
            chart = fx.hvplot.barh(
                x="pair", y="change_pct",
                c="change_pct", cmap="RdYlGn",
                clim=(-clim, clim), colorbar=False,
                xlabel="Δ% (today)", ylabel="",
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
        pn.panel(live_pane, sizing_mode="stretch_both"),
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )


# ── Market Tab ─────────────────────────────────────────────────────────────────
def build_market_tab() -> pn.Column:
    ticker_search = pn.widgets.TextInput(
        name="Ticker", value="AAPL",
        placeholder="e.g. AAPL, TSLA, BTC-USD, 7203.T",
        width=200,
    )
    start_picker = pn.widgets.DatePicker(
        name="From",
        value=(pd.Timestamp.now() - pd.DateOffset(months=6)).date(),
        width=160,
    )
    end_picker = pn.widgets.DatePicker(
        name="To", value=pd.Timestamp.now().date(), width=160,
    )
    interval_select = pn.widgets.Select(
        name="Interval", options=["1d", "1wk", "1mo"], value="1d", width=100,
    )

    def _make_charts(ticker, start_date, end_date, interval):
        t = (ticker or "").strip().upper()
        if not t or start_date is None or end_date is None:
            return _no_data("Enter a ticker symbol and select a date range")

        df = load_ohlcv(t, pd.Timestamp(start_date).strftime("%Y-%m-%d"),
                           pd.Timestamp(end_date).strftime("%Y-%m-%d"), interval)

        if df.empty:
            return _no_data(f'No data found for "{t}" — check the ticker symbol')

        from bokeh.plotting import figure
        from bokeh.models import HoverTool

        # ── Stats strip ───────────────────────────────────────────────────────
        last      = df.iloc[-1]
        chg_pct   = (last["close"] - df.iloc[0]["close"]) / df.iloc[0]["close"] * 100
        chg_color = "#22c55e" if chg_pct >= 0 else "#ef4444"
        arrow     = "▲" if chg_pct >= 0 else "▼"

        stats = pn.pane.HTML(f"""
        <div style="background:#070d1a;border-bottom:1px solid {_BORDER};
                    padding:8px 20px;font-family:'Courier New',monospace;font-size:12px;
                    display:flex;gap:28px;align-items:center;flex-wrap:wrap;">
          <span style="color:{_ACCENT};font-weight:bold;font-size:15px;">{t}</span>
          <span><span style="color:{_MUTED};">O </span>
                <span style="color:#e2e8f0;">{last['open']:.2f}</span></span>
          <span><span style="color:{_MUTED};">H </span>
                <span style="color:#22c55e;">{last['high']:.2f}</span></span>
          <span><span style="color:{_MUTED};">L </span>
                <span style="color:#ef4444;">{last['low']:.2f}</span></span>
          <span><span style="color:{_MUTED};">C </span>
                <span style="color:#e2e8f0;">{last['close']:.2f}</span></span>
          <span><span style="color:{_MUTED};">Vol </span>
                <span style="color:#94a3b8;">{last['volume']:,}</span></span>
          <span style="color:{chg_color};font-weight:bold;">{arrow} {abs(chg_pct):.2f}%</span>
        </div>""", sizing_mode="stretch_width", height=42)

        # ── Helpers ───────────────────────────────────────────────────────────
        inc = df[df["close"] >= df["open"]]
        dec = df[df["close"] <  df["open"]]
        n   = len(df)
        ms  = ((df["date"].max() - df["date"].min()).total_seconds() * 1000 / max(n, 1)) * 0.65

        def _style(p):
            p.background_fill_color = _BG
            p.border_fill_color     = _BG
            p.outline_line_color    = _BORDER
            p.grid.grid_line_color  = _BORDER
            p.grid.grid_line_alpha  = 0.5
            for ax in (p.xaxis, p.yaxis):
                ax.major_label_text_color = "#94a3b8"
                ax.axis_line_color        = _BORDER
                ax.major_tick_line_color  = _BORDER
                ax.minor_tick_line_color  = _BORDER

        # ── Candlestick figure ────────────────────────────────────────────────
        hover = HoverTool(tooltips=[
            ("Date",  "@date{%F}"), ("Open",  "@open{0.2f}"),
            ("High",  "@high{0.2f}"), ("Low", "@low{0.2f}"),
            ("Close", "@close{0.2f}"), ("Vol", "@volume{0,}"),
        ], formatters={"@date": "datetime"})

        cp = figure(x_axis_type="datetime", height=440, sizing_mode="stretch_width",
                    toolbar_location="above", tools=["xpan", "xwheel_zoom", "reset", hover],
                    active_scroll="xwheel_zoom")
        _style(cp)
        cp.segment("date", "high", "date", "low", source=df.to_dict("list"),
                   color="#94a3b8", line_width=1)
        if not inc.empty:
            cp.vbar("date", ms, "open", "close", source=inc.to_dict("list"),
                    fill_color="#22c55e", line_color="#22c55e")
        if not dec.empty:
            cp.vbar("date", ms, "open", "close", source=dec.to_dict("list"),
                    fill_color="#ef4444", line_color="#ef4444")

        # ── Volume figure (linked x-axis) ─────────────────────────────────────
        vp = figure(x_axis_type="datetime", height=150, sizing_mode="stretch_width",
                    x_range=cp.x_range, toolbar_location=None, tools=[])
        _style(vp)
        if not inc.empty:
            vp.vbar("date", ms, 0, "volume", source=inc.to_dict("list"),
                    fill_color="#22c55e", line_color="#22c55e")
        if not dec.empty:
            vp.vbar("date", ms, 0, "volume", source=dec.to_dict("list"),
                    fill_color="#ef4444", line_color="#ef4444")
        vp.yaxis.axis_label = "Volume"
        vp.yaxis.axis_label_text_color = "#94a3b8"

        return pn.Column(
            stats,
            pn.pane.Bokeh(cp, sizing_mode="stretch_both", min_height=420),
            pn.pane.Bokeh(vp, sizing_mode="stretch_width", height=170),
            sizing_mode="stretch_both",
        )

    chart_pane = pn.bind(
        _make_charts,
        ticker_search.param.value,
        start_picker.param.value,
        end_picker.param.value,
        interval_select.param.value,
    )

    return pn.Column(
        _header("Market — OHLCV Candlestick Chart"),
        pn.Row(
            ticker_search, start_picker, end_picker, interval_select,
            align="end",
            styles={"padding": "0 16px 12px"},
        ),
        pn.panel(chart_pane, sizing_mode="stretch_both"),
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )
