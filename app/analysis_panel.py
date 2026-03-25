"""
Risk Analysis tab — linked cross-filtering with hv.link_selections.

Box-select any region on the map → time scatter, severity histogram, and
source strip all filter instantly to show only those events.

Full HoloViz stack showcase:
  geoviews    — tile map + geographic points
  holoviews   — link_selections, Scatter, Histogram
  datashader  — (available via the main Risk Map tab)
  panel       — layout, panes, responsive sizing
  param       — reactive state
"""
from __future__ import annotations

import threading
import urllib.parse
import urllib.request

import pandas as pd
import holoviews as hv
import geoviews as gv
import panel as pn
from holoviews.operation import histogram as hv_histogram

from data.events import load_events
from legend import SEV_COLOR

_BG       = "#0a0f1e"
_PANEL_BG = "#0c1524"
_BORDER   = "#1e3a5f"
_ACCENT   = "#7dd3fc"
_MUTED    = "#475569"

_HDR_CSS = (
    "font-size:13px;font-weight:bold;color:{a};"
    "letter-spacing:2px;text-transform:uppercase;"
    "font-family:'Courier New',monospace;padding:6px 0 2px;"
).format(a=_ACCENT)

_CHART_OPTS = dict(
    bgcolor=_PANEL_BG,
    show_grid=True,
    toolbar="above",
    responsive=True,
)


def _hdr(text: str) -> pn.pane.HTML:
    return pn.pane.HTML(
        f'<div style="{_HDR_CSS}">{text}</div>',
        sizing_mode="stretch_width",
        height=26,
        margin=0,
    )


def build_analysis_tab(df: pd.DataFrame | None = None) -> pn.viewable.Viewable:
    if df is None:
        df = load_events()

    if df.empty:
        return pn.pane.Markdown(
            "### No event data available",
            styles={"color": "#94a3b8", "padding": "40px"},
            sizing_mode="stretch_both",
        )

    df = df.copy()
    df["sev_color"] = df["severity"].map(SEV_COLOR).fillna("#64748b")
    # tz-naive so Bokeh datetime axis works cleanly
    df["ts"] = df["timestamp"].dt.tz_localize(None)

    # ── hv.link_selections — the core of this tab ─────────────────────────
    # One instance links ALL elements: select on any → all filter.
    ls = hv.link_selections.instance()

    # ── Map (gv.Points) ───────────────────────────────────────────────────
    # Apply ls() ONLY to the Points layer — not the tile source.
    # WMTS (tile) objects don't support _transforms and will crash if wrapped.
    map_pts = gv.Points(
        df, kdims=["lon", "lat"],
        vdims=["severity", "source", "region", "sev_color"],
    ).opts(
        color="sev_color",
        size=5,
        alpha=0.8,
        nonselection_alpha=0.15,
        show_legend=False,
    )

    linked_pts = ls(map_pts)

    map_overlay = (gv.tile_sources.CartoDark * linked_pts).opts(
        responsive=True,
        min_height=500,
        xaxis=None,
        yaxis=None,
        bgcolor=_BG,
        xlim=(-20000000, 20000000),
        ylim=(-10000000, 15000000),
        tools=["box_select", "wheel_zoom", "pan", "reset"],
        active_tools=["box_select", "wheel_zoom"],
    )

    # ── Severity histogram ────────────────────────────────────────────────
    # hv_histogram on a Dataset is natively supported by link_selections:
    # selecting on the map recomputes the histogram for filtered rows.
    sev_hist = hv_histogram(
        hv.Dataset(df, kdims=["severity"], vdims=["lon", "lat"]),
        dimension="severity",
        num_bins=5,
        normed=False,
    ).opts(
        color=_ACCENT,
        alpha=0.85,
        line_color=None,
        height=185,
        xlabel="Severity",
        ylabel="Count",
        **_CHART_OPTS,
    )
    linked_sev = ls(sev_hist)

    import re
    _BOUNDS_RE = re.compile(
        r"dim\('lon'\)\s*>=\s*([-\d.eE+]+).*?"
        r"dim\('lon'\)\s*<=\s*([-\d.eE+]+).*?"
        r"dim\('lat'\)\s*>=\s*([-\d.eE+]+).*?"
        r"dim\('lat'\)\s*<=\s*([-\d.eE+]+)",
        re.DOTALL,
    )

    def _filter_df(sel_expr):
        """Parse lon/lat bounds from selection expression, filter with pandas."""
        if sel_expr is None:
            print("[DEBUG] _filter_df: no selection")
            return df
        expr_str = repr(sel_expr)
        print(f"[DEBUG] _filter_df: sel_expr = {expr_str}")
        m = _BOUNDS_RE.search(expr_str)
        if not m:
            print("[DEBUG] _filter_df: could not parse bounds from expression")
            return df
        lon0, lon1 = float(m.group(1)), float(m.group(2))
        lat0, lat1 = float(m.group(3)), float(m.group(4))
        print(f"[DEBUG] _filter_df: parsed bounds lon=[{lon0:.2f},{lon1:.2f}] lat=[{lat0:.2f},{lat1:.2f}]")
        fdf = df[
            df["lon"].between(lon0, lon1) &
            df["lat"].between(lat0, lat1)
        ]
        print(f"[DEBUG] _filter_df: OK — {len(fdf)} / {len(df)} rows selected")
        return fdf

    _SRC_COLORS = {
        "GDELT":    "#ef4444",
        "FIRMS":    "#f97316",
        "OpenSky":  "#38bdf8",
        "NOAA":     "#22d3ee",
        "Maritime": "#0ea5e9",
        "Rocket":   "#f43f5e",
        "Seismic":  "#a78bfa",
        "Cyber":    "#34d399",
    }
    _box_opts = dict(
        box_alpha=0.8, outlier_alpha=0.5,
        height=220, xlabel="", ylabel="Severity",
        ylim=(0, 5.5), xrotation=30, **_CHART_OPTS,
    )

    # Stream that fires whenever ls.selection_expr changes — this is
    # HoloViews' own mechanism and is guaranteed to work in server mode.
    _sel_stream = hv.streams.Params(ls, ["selection_expr"])

    # ── Severity by source — reactive colored BoxWhisker ─────────────────
    def _build_box_overlay(selection_expr=None):
        fdf = _filter_df(selection_expr)
        box = None
        for _src, _color in _SRC_COLORS.items():
            _sdf = fdf[fdf["source"] == _src]
            if _sdf.empty:
                continue
            _b = hv.BoxWhisker(
                _sdf, kdims=["source"], vdims=["severity"],
            ).opts(
                box_color=_color, whisker_color=_color,
                outlier_color=_color, **_box_opts,
            )
            box = _b if box is None else box * _b
        if box is None:
            box = hv.BoxWhisker(
                pd.DataFrame({"source": pd.Series([], dtype=str),
                              "severity": pd.Series([], dtype=float)}),
                kdims=["source"], vdims=["severity"],
            ).opts(**_box_opts)
        return box

    dmap_box = hv.DynamicMap(_build_box_overlay, streams=[_sel_stream])

    # ── Summary stats cards — reactive ───────────────────────────────────
    _card_css = (
        "display:inline-flex;flex-direction:column;align-items:center;"
        f"justify-content:center;background:{_PANEL_BG};"
        f"border:1px solid {_BORDER};border-radius:8px;"
        "padding:12px 8px;width:calc(50% - 6px);box-sizing:border-box;"
    )
    _num_css = f"font-size:22px;font-weight:bold;color:{_ACCENT};font-family:'Courier New',monospace;"
    _lbl_css = "font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:#475569;margin-top:4px;font-family:'Courier New',monospace;"

    def _make_stats_html(fdf):
        if fdf.empty:
            total, avg_sev, top_src, top_reg = 0, 0.0, "—", "—"
        else:
            total   = len(fdf)
            avg_sev = fdf["severity"].mean()
            top_src = fdf["source"].value_counts().index[0]
            top_reg = fdf["region"].value_counts().index[0]
        return f"""
        <div style="display:flex;flex-wrap:wrap;gap:6px;padding:4px 0 10px;">
          <div style="{_card_css}">
            <span style="{_num_css}">{total:,}</span>
            <span style="{_lbl_css}">Total Events</span>
          </div>
          <div style="{_card_css}">
            <span style="{_num_css}">{avg_sev:.1f}</span>
            <span style="{_lbl_css}">Avg Severity</span>
          </div>
          <div style="{_card_css}">
            <span style="{_num_css};font-size:16px;">{top_src}</span>
            <span style="{_lbl_css}">Top Source</span>
          </div>
          <div style="{_card_css}">
            <span style="{_num_css};font-size:13px;text-align:center;">{top_reg}</span>
            <span style="{_lbl_css}">Top Region</span>
          </div>
        </div>
        """

    stats_pane = pn.pane.HTML(
        _make_stats_html(df), sizing_mode="stretch_width", margin=0,
    )

    # ── Instruction hint + clear button ──────────────────────────────────
    clear_btn = pn.widgets.Button(
        name="✕  Clear Selection",
        button_type="light",
        sizing_mode="stretch_width",
        height=28,
        styles={
            "font-family": "'Courier New', monospace",
            "font-size": "10px",
            "background": "#0c1524",
            "color": "#7dd3fc",
            "border": f"1px solid {_BORDER}",
            "cursor": "pointer",
        },
    )

    def _clear(event):
        ls.selection_expr = None
        feed_pane.object = _PLACEHOLDER

    clear_btn.on_click(_clear)

    hint = pn.Column(
        pn.pane.HTML(
            f'<div style="font-size:10px;color:{_MUTED};font-family:Courier New,monospace;'
            f'padding:4px 0 8px;">'
            f'&#x25A1;&nbsp; Box-select on the map &mdash; all charts filter instantly</div>',
            sizing_mode="stretch_width",
            margin=0,
        ),
        clear_btn,
        pn.pane.HTML(
            f'<hr style="border:none;border-top:1px solid {_BORDER};margin:8px 0;">',
            sizing_mode="stretch_width",
            margin=0,
        ),
        sizing_mode="stretch_width",
        margin=0,
    )

    # ── Google News RSS feed (reactive) ──────────────────────────────────
    import xml.etree.ElementTree as ET

    _GNEWS_BASE = "https://news.google.com/rss/search"

    def _fetch_google_news(region: str, max_results: int = 20) -> list[dict]:
        """Single Google News RSS call — searches directly by region keyword."""
        q = urllib.parse.quote(region)
        url = f"{_GNEWS_BASE}?q={q}&gl=US&hl=en&ceid=US:en"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 HoloIntel/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = ET.parse(resp)
        articles = []
        for item in tree.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            src_el = item.find("source")
            source = (src_el.text or "Google News").strip() if src_el is not None else "Google News"
            if title:
                articles.append({
                    "source": source,
                    "title":  title,
                    "url":    link,
                    "date":   pub,
                })
        return articles[:max_results]

    def _make_news_html(articles: list[dict], region: str) -> str:
        if not articles:
            return (
                f'<div style="color:#475569;font-size:11px;'
                f'font-family:Courier New,monospace;padding:20px 0;">'
                f'No news found for <em>{region}</em>.</div>'
            )
        items = []
        for art in articles:
            title = art["title"]
            if len(title) > 100:
                title = title[:97] + "…"
            try:
                date_str = pd.Timestamp(art["date"]).strftime("%b %d")
            except Exception:
                date_str = ""
            items.append(f"""
            <div style="border-bottom:1px solid {_BORDER};padding:8px 0;">
              <div style="color:#475569;font-size:9px;font-family:'Courier New',monospace;
                          margin-bottom:3px;">{art['source']} &nbsp;·&nbsp; {date_str}</div>
              <a href="{art['url']}" target="_blank"
                 style="color:#e2e8f0;font-size:11px;font-family:'Courier New',monospace;
                        text-decoration:none;line-height:1.5;">{title}</a>
            </div>""")
        return (
            f'<div style="font-size:9px;color:{_ACCENT};font-family:Courier New,monospace;'
            f'padding-bottom:6px;">Google News &nbsp;|&nbsp; '
            f'region: <em>{region}</em></div>'
            + "".join(items)
        )

    _PLACEHOLDER = (
        f'<div style="color:#475569;font-size:11px;font-family:Courier New,monospace;'
        f'padding:20px 0;">Box-select a region on the map to load latest news.</div>'
    )

    feed_pane = pn.pane.HTML(
        _PLACEHOLDER,
        sizing_mode="stretch_width",
        margin=0,
        styles={"overflow-y": "auto", "max-height": "520px"},
    )

    # Single subscriber drives stats + news from the same reliable stream.
    # _sel_stream (Params watching ls.selection_expr) is the only mechanism
    # guaranteed to fire in Bokeh server mode — BoundsXY silently drops
    # calls because it passes x0/y0/x1/y1 as keyword args, not positional.
    def _on_selection(selection_expr=None):
        fdf = _filter_df(selection_expr)
        stats_pane.object = _make_stats_html(fdf)

        if selection_expr is None:
            feed_pane.object = _PLACEHOLDER
            return

        if fdf.empty:
            print("[DEBUG] _on_selection: fdf is empty after filter")
            feed_pane.object = (
                f'<div style="color:#475569;font-size:11px;'
                f'font-family:Courier New,monospace;padding:20px 0;">'
                f'No events in selection.</div>'
            )
            return

        region_counts = fdf["region"].value_counts()
        region = region_counts.index[0]
        print(f"[DEBUG] _on_selection: fdf has {len(fdf)} rows")
        print(f"[DEBUG] _on_selection: region counts =\n{region_counts.head(5)}")
        print(f"[DEBUG] _on_selection: top region = {region!r}")

        q = urllib.parse.quote(region)
        api_url = f"https://news.google.com/rss/search?q={q}&gl=US&hl=en&ceid=US:en"
        print(f"[DEBUG] _on_selection: Google News URL = {api_url}")

        feed_pane.object = (
            f'<div style="color:{_ACCENT};font-size:10px;'
            f'font-family:Courier New,monospace;padding:12px 0;">'
            f'Fetching news for <em>{region}</em>…</div>'
        )

        def _fetch():
            try:
                articles = _fetch_google_news(region)
                print(f"[DEBUG] _fetch: got {len(articles)} articles for {region!r}")
                feed_pane.object = _make_news_html(articles, region)
            except Exception as exc:
                print(f"[DEBUG] _fetch: FAILED — {exc!r}")
                feed_pane.object = (
                    f'<div style="color:#f87171;font-size:10px;'
                    f'font-family:Courier New,monospace;padding:12px 0;">'
                    f'News fetch failed: {exc}</div>'
                )

        threading.Thread(target=_fetch, daemon=True).start()

    _sel_stream.add_subscriber(_on_selection)

    # ── Right chart column ────────────────────────────────────────────────
    charts = pn.Column(
        hint,
        _hdr("Severity distribution"),
        pn.pane.HoloViews(linked_sev, sizing_mode="stretch_width", margin=0),
        _hdr("Latest news (Google News)"),
        feed_pane,
        pn.Spacer(),
        sizing_mode="stretch_height",
        styles={
            "background":  _BG,
            "padding":     "10px 14px",
            "overflow-y":  "auto",
            "border-left": f"1px solid {_BORDER}",
        },
        width=400,
    )

    return pn.Row(
        pn.pane.HoloViews(map_overlay, sizing_mode="stretch_both", margin=0),
        charts,
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )
