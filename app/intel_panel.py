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

_COMMODITY_ORDER = [
    "Gold", "Global Oil Price", "US Oil Price",
    "Natural Gas", "Wheat", "Copper", "Silver", "Palladium",
]

_COMMODITY_COLORS = [
    "#facc15", "#ef4444", "#f97316",   # Gold / Global Oil Price / US Oil Price
    "#38bdf8", "#86efac", "#fb923c",   # Natural Gas / Wheat / Copper
    "#94a3b8", "#c084fc",               # Silver / Palladium
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


# ── Ticker Tape ────────────────────────────────────────────────────────────────
_TAPE_SYMBOLS = [
    ("SPY",     "S&P 500"),
    ("QQQ",     "NASDAQ"),
    ("^DJI",    "DOW"),
    ("BTC-USD", "Bitcoin"),
    ("ETH-USD", "Ethereum"),
    ("GC=F",    "Gold"),
    ("CL=F",    "Oil (WTI)"),
    ("BZ=F",    "Oil (Brent)"),
    ("NG=F",    "Nat Gas"),
    ("SI=F",    "Silver"),
    ("AAPL",    "Apple"),
    ("MSFT",    "Microsoft"),
    ("NVDA",    "NVIDIA"),
    ("TSLA",    "Tesla"),
    ("AMZN",    "Amazon"),
]


def _build_ticker_tape() -> pn.pane.HTML:
    """Scrolling Bloomberg-style ticker tape with live prices."""
    try:
        import requests
        items = []
        for sym, label in _TAPE_SYMBOLS:
            try:
                data = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                    params={"range": "2d", "interval": "1d", "includePrePost": "false"},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=6,
                ).json()
                result = data.get("chart", {}).get("result", [{}])[0]
                meta   = result.get("meta", {})
                price  = meta.get("regularMarketPrice")
                prev   = meta.get("previousClose") or meta.get("chartPreviousClose")
                if price and prev:
                    chg     = price - prev
                    chg_pct = chg / prev * 100
                    color   = "#22c55e" if chg >= 0 else "#ef4444"
                    arrow   = "▲" if chg >= 0 else "▼"
                    items.append(
                        f'<span style="margin:0 28px;white-space:nowrap;">'
                        f'<span style="color:#94a3b8;font-size:10px;">{label}&nbsp;</span>'
                        f'<span style="color:#e2e8f0;font-weight:bold;">{price:,.2f}</span>'
                        f'&nbsp;<span style="color:{color};font-size:10px;">'
                        f'{arrow}&nbsp;{abs(chg_pct):.2f}%</span>'
                        f'</span>'
                    )
            except Exception:
                pass
    except Exception:
        items = []

    if not items:
        items = [
            f'<span style="margin:0 28px;color:#475569;font-size:10px;">Market data unavailable</span>'
        ]

    # Duplicate for seamless loop
    content = "".join(items) * 2

    html = f"""
    <style>
      @keyframes ticker-scroll {{
        0%   {{ transform: translateX(0); }}
        100% {{ transform: translateX(-50%); }}
      }}
      .ticker-wrap {{
        width: 100%;
        overflow: hidden;
        background: #070d1a;
        border-bottom: 1px solid {_BORDER};
        border-top: 1px solid {_BORDER};
        height: 36px;
        display: flex;
        align-items: center;
      }}
      .ticker-inner {{
        display: inline-flex;
        animation: ticker-scroll 60s linear infinite;
        font-family: 'Courier New', monospace;
        font-size: 12px;
      }}
      .ticker-inner:hover {{ animation-play-state: paused; }}
    </style>
    <div class="ticker-wrap">
      <div class="ticker-inner">{content}</div>
    </div>
    """
    return pn.pane.HTML(html, sizing_mode="stretch_width", height=36)


def _fetch_news(ticker: str) -> str:
    """Latest Yahoo Finance headlines for ticker via free RSS feed."""
    try:
        import requests
        import xml.etree.ElementTree as ET
        resp = requests.get(
            f"https://feeds.finance.yahoo.com/rss/2.0/headline"
            f"?s={ticker}&region=US&lang=en-US",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        root  = ET.fromstring(resp.text)
        items = root.findall(".//item")[:6]
        if not items:
            return ""
        rows = ""
        for item in items:
            title   = item.findtext("title",   "").strip()
            link    = item.findtext("link",    "#").strip()
            pubdate = item.findtext("pubDate", "").strip()
            try:
                dt_str = pd.Timestamp(pubdate).strftime("%b %d, %H:%M")
            except Exception:
                dt_str = pubdate[:16]
            rows += (
                f'<div style="padding:7px 0;border-bottom:1px solid {_BORDER};">'
                f'<a href="{link}" target="_blank" style="color:#e2e8f0;font-size:12px;'
                f'text-decoration:none;font-family:\'Courier New\',monospace;'
                f'line-height:1.5;">{title}</a>'
                f'<div style="font-size:10px;color:{_MUTED};margin-top:2px;">'
                f'{dt_str}</div></div>'
            )
        return (
            f'<div style="background:#070d1a;border:1px solid {_BORDER};'
            f'border-radius:6px;padding:12px 18px;margin-top:6px;">'
            f'<div style="font-size:9px;color:{_ACCENT};letter-spacing:2px;'
            f'text-transform:uppercase;margin-bottom:10px;'
            f'font-family:\'Courier New\',monospace;">Latest News — {ticker}</div>'
            f'{rows}</div>'
        )
    except Exception:
        return ""


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

        # Always load 2-year history so panning left reveals older candles.
        history_start = (pd.Timestamp.now() - pd.DateOffset(years=2)).strftime("%Y-%m-%d")
        history_end   = (pd.Timestamp.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        df = load_ohlcv(t, history_start, history_end, interval)

        if df.empty:
            return _no_data(f'No data found for "{t}" — check the ticker symbol')

        from bokeh.plotting import figure
        from bokeh.models import HoverTool, Range1d, Span

        # ── Technical indicators ──────────────────────────────────────────────
        df = df.copy()
        df["ma20"]  = df["close"].rolling(20).mean().round(4)
        df["ma50"]  = df["close"].rolling(50).mean().round(4)
        df["ma200"] = df["close"].rolling(200).mean().round(4)

        def _rsi(series, period=14):
            delta = series.diff()
            gain  = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
            loss  = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
            rs    = gain / loss.replace(0, float("nan"))
            return (100 - 100 / (1 + rs)).round(2)

        df["rsi"] = _rsi(df["close"])

        # ── View window (for stats strip + bar width) ─────────────────────────
        view_mask = (
            (df["date"] >= pd.Timestamp(start_date)) &
            (df["date"] <= pd.Timestamp(end_date) + pd.Timedelta(days=1))
        )
        view_df   = df[view_mask] if view_mask.any() else df
        last      = view_df.iloc[-1]
        chg_pct   = (last["close"] - view_df.iloc[0]["close"]) / view_df.iloc[0]["close"] * 100
        chg_color = "#22c55e" if chg_pct >= 0 else "#ef4444"
        arrow     = "▲" if chg_pct >= 0 else "▼"

        # ── Stats strip ───────────────────────────────────────────────────────
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

        # ── Signal summary ────────────────────────────────────────────────────
        lc        = float(df["close"].iloc[-1])
        ma50_val  = float(df["ma50"].dropna().iloc[-1])  if df["ma50"].notna().any()  else None
        ma200_val = float(df["ma200"].dropna().iloc[-1]) if df["ma200"].notna().any() else None
        rsi_val   = float(df["rsi"].dropna().iloc[-1])   if df["rsi"].notna().any()   else None

        signals: list[tuple[str, str]] = []
        bull = bear = 0

        if ma50_val and ma200_val:
            if ma50_val > ma200_val:
                signals.append(("#22c55e", f"MA50 ({ma50_val:.2f}) > MA200 ({ma200_val:.2f}) — Golden Cross"))
                bull += 1
            else:
                signals.append(("#ef4444", f"MA50 ({ma50_val:.2f}) < MA200 ({ma200_val:.2f}) — Death Cross"))
                bear += 1
        if ma50_val:
            if lc > ma50_val:
                signals.append(("#22c55e", f"Price above MA50 ({ma50_val:.2f}) — Uptrend"))
                bull += 1
            else:
                signals.append(("#ef4444", f"Price below MA50 ({ma50_val:.2f}) — Downtrend"))
                bear += 1
        if ma200_val:
            if lc > ma200_val:
                signals.append(("#22c55e", f"Price above MA200 ({ma200_val:.2f}) — Long-term Uptrend"))
                bull += 1
            else:
                signals.append(("#ef4444", f"Price below MA200 ({ma200_val:.2f}) — Long-term Downtrend"))
                bear += 1
        if rsi_val:
            if rsi_val > 70:
                signals.append(("#facc15", f"RSI {rsi_val:.0f} — Overbought, potential reversal"))
            elif rsi_val < 30:
                signals.append(("#facc15", f"RSI {rsi_val:.0f} — Oversold, potential bounce"))
            else:
                signals.append(("#94a3b8", f"RSI {rsi_val:.0f} — Neutral zone (30–70)"))

        if bull > bear:
            verdict, v_color = "BULLISH", "#22c55e"
        elif bear > bull:
            verdict, v_color = "BEARISH", "#ef4444"
        else:
            verdict, v_color = "NEUTRAL", "#facc15"

        sig_rows = "".join(
            f'<div style="display:flex;align-items:center;margin:3px 0;">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{c};'
            f'flex-shrink:0;display:inline-block;margin-right:8px;'
            f'box-shadow:0 0 4px {c}99;"></span>'
            f'<span style="font-size:11px;color:#cbd5e1;">{msg}</span></div>'
            for c, msg in signals
        )
        signal_pane = pn.pane.HTML(f"""
        <div style="background:#070d1a;border:1px solid {_BORDER};border-radius:6px;
                    padding:12px 20px;font-family:'Courier New',monospace;
                    display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap;">
          <div style="min-width:90px;">
            <div style="font-size:9px;color:{_MUTED};letter-spacing:2px;
                        text-transform:uppercase;margin-bottom:4px;">Signal</div>
            <div style="font-size:22px;font-weight:bold;color:{v_color};
                        text-shadow:0 0 12px {v_color}66;">{verdict}</div>
            <div style="font-size:10px;color:{_MUTED};margin-top:3px;">
              {bull}B / {bear}S</div>
          </div>
          <div style="flex:1;min-width:200px;">{sig_rows}</div>
        </div>""", sizing_mode="stretch_width", min_height=90)

        # ── Helpers ───────────────────────────────────────────────────────────
        inc    = df[df["close"] >= df["open"]]
        dec    = df[df["close"] <  df["open"]]
        view_n = max(len(view_df), 1)
        if view_n > 1:
            ms = ((view_df["date"].max() - view_df["date"].min()).total_seconds()
                  * 1000 / view_n) * 0.7
        else:
            ms = int(0.7 * 24 * 3600 * 1000)

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
        candle_hover = HoverTool(tooltips=[
            ("Date",  "@date{%F}"), ("Open",  "@open{0.2f}"),
            ("High",  "@high{0.2f}"), ("Low",  "@low{0.2f}"),
            ("Close", "@close{0.2f}"), ("Vol", "@volume{0,}"),
        ], formatters={"@date": "datetime"})

        view_start_ms = int(pd.Timestamp(start_date).timestamp() * 1000)
        view_end_ms   = int((pd.Timestamp(end_date) + pd.Timedelta(days=1)).timestamp() * 1000)
        price_min = df["low"].min()
        price_max = df["high"].max()
        price_pad = (price_max - price_min) * 0.05
        y_range   = Range1d(start=price_min - price_pad, end=price_max + price_pad)

        cp = figure(x_axis_type="datetime", height=520, sizing_mode="stretch_width",
                    toolbar_location="above",
                    tools=["xpan", "xwheel_zoom", "reset", candle_hover],
                    active_scroll="xwheel_zoom",
                    x_range=Range1d(start=view_start_ms, end=view_end_ms),
                    y_range=y_range)
        _style(cp)
        seg_r = cp.segment("date", "high", "date", "low", source=df.to_dict("list"),
                            color="#94a3b8", line_width=1)
        inc_r = cp.vbar("date", ms, "open", "close", source=inc.to_dict("list"),
                        fill_color="#22c55e", line_color="#22c55e") if not inc.empty else None
        dec_r = cp.vbar("date", ms, "open", "close", source=dec.to_dict("list"),
                        fill_color="#ef4444", line_color="#ef4444") if not dec.empty else None

        # Restrict candle hover to candle renderers only
        candle_hover.renderers = [r for r in [seg_r, inc_r, dec_r] if r is not None]

        # MA overlays — each gets its own hover showing date + MA value
        for col, color, label in [
            ("ma20",  "#38bdf8", "MA20"),
            ("ma50",  "#f97316", "MA50"),
            ("ma200", "#f43f5e", "MA200"),
        ]:
            ma_df = df[df[col].notna()]
            if not ma_df.empty:
                src  = {"date": ma_df["date"].tolist(), "value": ma_df[col].tolist()}
                ma_r = cp.line("date", "value", source=src,
                               color=color, line_width=1.5,
                               legend_label=label, alpha=0.85)
                cp.add_tools(HoverTool(
                    renderers=[ma_r],
                    tooltips=[(label, "@value{0.2f}"), ("Date", "@date{%F}")],
                    formatters={"@date": "datetime"},
                ))

        cp.legend.background_fill_color = "#0a0f1e"
        cp.legend.background_fill_alpha = 0.8
        cp.legend.label_text_color      = "#94a3b8"
        cp.legend.border_line_color     = _BORDER
        cp.legend.location              = "top_left"
        cp.legend.label_text_font_size  = "10px"
        cp.legend.click_policy          = "hide"

        # ── Volume figure (linked x-axis) ─────────────────────────────────────
        vp = figure(x_axis_type="datetime", height=110, sizing_mode="stretch_width",
                    x_range=cp.x_range, toolbar_location=None, tools=[])
        _style(vp)
        if not inc.empty:
            vp.vbar("date", ms, 0, "volume", source=inc.to_dict("list"),
                    fill_color="#22c55e", line_color="#22c55e", alpha=0.7)
        if not dec.empty:
            vp.vbar("date", ms, 0, "volume", source=dec.to_dict("list"),
                    fill_color="#ef4444", line_color="#ef4444", alpha=0.7)
        vp.yaxis.axis_label            = "Volume"
        vp.yaxis.axis_label_text_color = "#94a3b8"

        # ── RSI figure (linked x-axis) ────────────────────────────────────────
        rsi_clean = df[df["rsi"].notna()]
        rp = figure(x_axis_type="datetime", height=140, sizing_mode="stretch_width",
                    x_range=cp.x_range, toolbar_location=None, tools=[],
                    y_range=Range1d(0, 100))
        _style(rp)
        rp.line(rsi_clean["date"].tolist(), rsi_clean["rsi"].tolist(),
                color="#a78bfa", line_width=1.5)
        rp.add_layout(Span(location=70, dimension="width",
                           line_color="#ef4444", line_dash="dashed",
                           line_width=1, line_alpha=0.6))
        rp.add_layout(Span(location=30, dimension="width",
                           line_color="#22c55e", line_dash="dashed",
                           line_width=1, line_alpha=0.6))
        rp.yaxis.axis_label            = "RSI(14)"
        rp.yaxis.axis_label_text_color = "#94a3b8"

        # ── News ──────────────────────────────────────────────────────────────
        news_html = _fetch_news(t)
        news_pane = pn.pane.HTML(news_html, sizing_mode="stretch_width")

        return pn.Column(
            stats,
            signal_pane,
            pn.pane.Bokeh(cp, sizing_mode="stretch_both", min_height=500),
            pn.pane.Bokeh(vp, sizing_mode="stretch_width", height=130),
            pn.pane.Bokeh(rp, sizing_mode="stretch_width", height=160),
            news_pane,
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
        _build_ticker_tape(),
        pn.Row(
            ticker_search, start_picker, end_picker, interval_select,
            align="end",
            styles={"padding": "10px 16px 8px"},
        ),
        pn.panel(chart_pane, sizing_mode="stretch_both"),
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )
