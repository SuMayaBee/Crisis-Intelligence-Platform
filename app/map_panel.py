"""
Combined risk map — multi-source CartoDark tile map with hybrid rendering.

Visual encoding
---------------
  SHAPE  = data source
              ▲  triangle — FIRMS   (fire / thermal) — Datashader density raster
              ●  circle   — GDELT   (conflict events)
              ◆  diamond  — OpenSky (aviation)
              ■  square   — NOAA    (weather alerts)
              ▼  inv-tri  — Maritime (AIS vessels)
              ★  star     — Rocket  (alerts)
              ⬡  hex      — Seismic (earthquakes)
              ✚  cross    — Cyber   (threats)
  COLOR  = severity level
              gray → blue → yellow → orange → red  (1 → 5)
  SIZE   = uniform (all dots the same size)

Rendering strategy
------------------
  FIRMS uses Datashader server-side rasterization (can be 10k–80k points/day).
  All other sources use regular GeoViews Points with per-point hover tooltips.

Hover popup shows: source, category, title, region, severity, time.
"""
from __future__ import annotations

import datashader as ds
import holoviews.operation.datashader as hd
import pandas as pd
import panel as pn
import geoviews as gv
from bokeh.models import HoverTool
import cartopy.crs as ccrs
from shapely.geometry import shape as shapely_shape

from legend import SEVERITY_CMAP, SEV_COLOR, SEV_LABEL, MARKER_MAP

MIN_HEIGHT = 800
DOT_SIZE   = 7   # uniform size — visual weight via color only

# FIRMS fire-severity palette used by the Datashader layer (low → high density)
_FIRMS_CMAP = ["#7c2d12", "#f97316", "#fbbf24", "#fef08a"]

# Bokeh markers that have NO fill area — rendered purely with stroke lines.
# These need line_color set to be visible; fill_color has no effect on them.
_LINE_MARKERS = {"cross", "asterisk", "x", "plus", "dash"}

# ── HTML tooltip template ─────────────────────────────────────────────────────
# @fieldname is replaced by Bokeh with the per-row column value.
_TOOLTIP = """
<div style="
  background:#0d1a2a;
  border:1px solid #1e3a5f;
  border-radius:8px;
  padding:12px 14px;
  font-family:'Courier New',monospace;
  max-width:280px;
  box-shadow:0 6px 20px rgba(0,0,0,0.7);
  line-height:1.5;
">
  <div style="border-bottom:1px solid #1e3a5f;padding-bottom:7px;margin-bottom:8px;">
    <span style="font-size:12px;font-weight:bold;color:@sev_color;">@source</span>
    <span style="font-size:10px;color:#475569;margin-left:8px;">@category</span>
  </div>
  <div style="font-size:12px;color:#e2e8f0;margin-bottom:10px;">@title</div>
  <table style="font-size:11px;border-collapse:collapse;width:100%;">
    <tr>
      <td style="color:#475569;padding:2px 10px 2px 0;white-space:nowrap;">Region</td>
      <td style="color:#94a3b8;">@region</td>
    </tr>
    <tr>
      <td style="color:#475569;padding:2px 10px 2px 0;">Severity</td>
      <td style="color:@sev_color;font-weight:bold;">@sev_label</td>
    </tr>
    <tr>
      <td style="color:#475569;padding:2px 10px 2px 0;">Time</td>
      <td style="color:#94a3b8;">@ts_str</td>
    </tr>
  </table>
</div>
"""


def build_combined_map(
    df: pd.DataFrame,
    xlim: tuple = (-20000000, 20000000),
    ylim: tuple = (-10000000, 15000000),
    highlight_geojson: dict | None = None,
) -> pn.viewable.Viewable:
    if df.empty:
        return pn.pane.Markdown(
            "### No events match the current filters\n\n"
            "Lower the minimum severity or select more regions.",
            sizing_mode="stretch_both",
            styles={"color": "#94a3b8", "padding": "40px"},
        )

    df = df.copy()
    # Categorical severity string for colormap lookup
    df["sev_str"]   = df["severity"].astype(str)
    # Per-row hex color and label so the tooltip can reference them
    df["sev_color"] = df["severity"].map(SEV_COLOR).fillna("#64748b")
    df["sev_label"] = df["severity"].map(SEV_LABEL).fillna("Unknown")
    df["ts_str"]    = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M UTC")

    VDIMS = ["sev_str", "severity", "source", "category",
             "title", "region", "ts_str", "sev_color", "sev_label"]

    plot = gv.tile_sources.CartoDark

    # ── FIRMS: Datashader rasterization ──────────────────────────────────────
    # FIRMS can produce 10k–80k points/day globally (satellite fire detections).
    # Individual hover tooltips are not meaningful at that density, so we
    # rasterize on the server and shade as a density heatmap instead.
    firms_df = df[df["source"] == "FIRMS"]
    if not firms_df.empty:
        firms_pts = gv.Points(
            firms_df[["lon", "lat", "severity"]],
            kdims=["lon", "lat"],
            vdims=["severity"],
        )
        # rasterize aggregates into a pixel grid; dynspread expands isolated
        # pixels so sparse areas remain visible at all zoom levels.
        firms_raster = hd.rasterize(
            firms_pts,
            aggregator=ds.mean("severity"),
            dynamic=True,
        )
        firms_spread = hd.dynspread(
            firms_raster,
            threshold=0.4,
            max_px=4,
        )
        firms_shaded = hd.shade(
            firms_spread,
            cmap=_FIRMS_CMAP,
            alpha=200,
        ).opts(
            show_legend=False,
            tools=["wheel_zoom", "pan", "reset"],
        )
        plot = plot * firms_shaded

    # ── All other sources: regular GeoViews Points with per-point hover ───────
    # These sources produce small enough row counts that Bokeh can render them
    # individually, preserving rich hover tooltips for each event.
    for source, marker_shape in MARKER_MAP.items():
        if source == "FIRMS":
            continue  # already handled above with Datashader
        sdf = df[df["source"] == source]
        if sdf.empty:
            continue

        is_line_marker = marker_shape in _LINE_MARKERS
        pts = gv.Points(
            sdf, kdims=["lon", "lat"], vdims=VDIMS,
        ).opts(
            marker=marker_shape,
            color="sev_str",
            cmap=SEVERITY_CMAP,
            # Line-based markers (cross, asterisk) have no fill — they are
            # drawn entirely with lines, so line_color must follow the cmap.
            # Fill-based markers look cleaner without a visible border.
            line_color="sev_str" if is_line_marker else None,
            line_width=2 if is_line_marker else 1,
            size=DOT_SIZE + 4 if is_line_marker else DOT_SIZE,
            alpha=0.85,
            show_legend=False,
            # Each layer gets its own HoverTool instance (Bokeh requirement).
            tools=[HoverTool(tooltips=_TOOLTIP)],
        )
        plot = plot * pts

    # Country highlight border — rendered on top of event dots
    if highlight_geojson:
        try:
            geom = shapely_shape(highlight_geojson)
            # Input geometry is in WGS84 (lat/lon); GeoViews reprojects to Web Mercator for the tile map.
            highlight = gv.Shape(geom, crs=ccrs.PlateCarree()).opts(
                fill_color="rgba(57,255,20,0.07)",
                line_color="#39ff14",
                line_width=2.5,
                line_dash="solid",
            )
            plot = plot * highlight
        except Exception:
            pass  # never crash the map over a missing highlight

    plot = plot.opts(
        responsive=True,
        min_height=MIN_HEIGHT,
        xaxis=None,
        yaxis=None,
        active_tools=["wheel_zoom"],
        tools=["wheel_zoom", "pan", "reset"],
        bgcolor="#0a0f1e",
        xlim=xlim,
        ylim=ylim,
    )

    return pn.pane.HoloViews(plot, sizing_mode="stretch_both", min_height=MIN_HEIGHT)
