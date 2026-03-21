"""
Legend definitions shared across the map and right control panel.

Visual encoding on the map:
  SHAPE  → which data source  (circle / triangle / diamond / square)
  COLOR  → how severe         (gray → blue → yellow → orange → red)
"""
from __future__ import annotations

import panel as pn

# ── Severity (color) ──────────────────────────────────────────────────────────
# String keys required for GeoViews categorical cmap
SEVERITY_CMAP: dict[str, str] = {
    "1": "#64748b",   # slate  — Minimal
    "2": "#38bdf8",   # blue   — Low
    "3": "#facc15",   # yellow — Moderate
    "4": "#f97316",   # orange — High
    "5": "#f43f5e",   # red    — Critical
}

# Integer keys for mapping DataFrame severity column
SEV_COLOR: dict[int, str] = {int(k): v for k, v in SEVERITY_CMAP.items()}

SEV_LABEL: dict[int, str] = {
    1: "Minimal",
    2: "Low",
    3: "Moderate",
    4: "High",
    5: "Critical",
}

# ── Source (shape + description) ──────────────────────────────────────────────
# shape_char is a Unicode glyph that matches the Bokeh marker used on the map.
SOURCE_SHAPES: dict[str, tuple[str, str, str]] = {
    #               unicode  short label      one-line description
    "GDELT":      ("●",  "Conflict",   "Real-time global conflict events (GDELT)"),
    "FIRMS":      ("▲",  "Fire",       "NASA satellite thermal anomalies"),
    "OpenSky":    ("◆",  "Aviation",   "Live aircraft (ADS-B transponders)"),
    "NOAA":       ("■",  "Weather",    "Active NWS severe weather alerts"),
    "Maritime":   ("▼",  "AIS Ships",  "Vessel tracking — Hormuz / Red Sea / Gulf"),
    "Rocket":     ("★",  "Rocket",     "Israel Home Front Command alerts"),
    "Seismic":    ("⬡",  "Earthquake", "USGS M≥2.5 earthquakes (7-day)"),
    "Cyber":      ("✚",  "Cyber",      "AlienVault OTX threat intelligence"),
    "Radiation":  ("✳",  "Radiation",  "Safecast nuclear site monitoring"),
}

# Bokeh marker names matched to each source
MARKER_MAP: dict[str, str] = {
    "GDELT":     "circle",
    "FIRMS":     "triangle",
    "OpenSky":   "diamond",
    "NOAA":      "square",
    "Maritime":  "inverted_triangle",
    "Rocket":    "star",
    "Seismic":   "hex",
    "Cyber":     "cross",
    "Radiation": "asterisk",
}


def build_source_legend() -> pn.pane.HTML:
    """One row per source: shape glyph + name + short description."""
    rows = "".join(
        f"""
        <div style="display:flex;align-items:flex-start;margin-bottom:11px;">
          <span style="font-size:13px;color:#94a3b8;flex-shrink:0;
                       margin-right:10px;margin-top:1px;">{glyph}</span>
          <div>
            <span style="font-size:12px;font-weight:bold;color:#e2e8f0;">{src}</span>
            <span style="font-size:11px;color:#475569;"> — {short}</span><br>
            <span style="font-size:10px;color:#334155;">{desc}</span>
          </div>
        </div>"""
        for src, (glyph, short, desc) in SOURCE_SHAPES.items()
    )
    return pn.pane.HTML(rows, sizing_mode="stretch_width")


def build_severity_legend() -> pn.pane.HTML:
    """Two-column grid of severity levels: colored dot + label."""
    items = list(SEVERITY_CMAP.items())
    cells = "".join(
        f"""<div style="display:flex;align-items:center;margin-bottom:5px;">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                       background:{color};flex-shrink:0;
                       box-shadow:0 0 4px {color}88;"></span>
          <span style="margin-left:7px;font-size:11px;color:#cbd5e1;">
            <b style="color:{color};">{k}</b>&nbsp;{SEV_LABEL[int(k)]}
          </span>
        </div>"""
        for k, color in items
    )
    html = f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 6px;">{cells}</div>'
    return pn.pane.HTML(html, sizing_mode="stretch_width")
