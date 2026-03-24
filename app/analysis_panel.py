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
    "font-size:10px;font-weight:bold;color:{a};"
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
        bins=5,
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

    def _filter_df(sel_expr):
        """Apply link_selections expression to raw df; fall back to full df."""
        if sel_expr is None:
            return df
        try:
            hv_ds = hv.Dataset(df, kdims=["lon", "lat"],
                               vdims=["source", "severity", "region"])
            mask = sel_expr.apply(hv_ds, expanded=False, flat=True)
            return df[mask]
        except Exception:
            return df

    # ── Severity by source — colored BoxWhisker ───────────────────────────
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
    src_box = None
    for _src, _color in _SRC_COLORS.items():
        _sdf = df[df["source"] == _src]
        if _sdf.empty:
            continue
        _b = hv.BoxWhisker(_sdf, kdims=["source"], vdims=["severity"]).opts(
            box_color=_color,
            whisker_color=_color,
            outlier_color=_color,
            **_box_opts,
        )
        src_box = _b if src_box is None else src_box * _b

    # ── Top active regions bar chart (reactive) ───────────────────────────
    @pn.depends(ls.param.selection_expr)
    def _region_bars(sel_expr=None):
        fdf = _filter_df(sel_expr)
        top = (
            fdf.groupby("region").size()
               .reset_index(name="count")
               .sort_values("count", ascending=False)
               .head(10)
        )
        return hv.Bars(top, kdims=["region"], vdims=["count"]).opts(
            color=_ACCENT,
            alpha=0.85,
            line_color=None,
            height=220,
            xlabel="",
            ylabel="Events",
            xrotation=30,
            **_CHART_OPTS,
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

    # ── Right chart column ────────────────────────────────────────────────
    charts = pn.Column(
        hint,
        _hdr("Severity distribution"),
        pn.pane.HoloViews(linked_sev, sizing_mode="stretch_width", margin=0),
        _hdr("Severity by source"),
        pn.pane.HoloViews(src_box, sizing_mode="stretch_width", margin=0),
        _hdr("Top active regions"),
        _region_bars,
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
