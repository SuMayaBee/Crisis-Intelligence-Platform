"""
Full-page layout: map fills the screen, compact controls on the right.
No template sidebar.

Right panel contains:
  - Severity color indicator (legend)
  - Min-severity slider
  - Region checkboxes  (All + one per region; initially all ticked)
"""
from __future__ import annotations

import math
import threading
import urllib.parse
import urllib.request
import json

import panel as pn

from data.events import load_events
from legend import build_severity_legend, SOURCE_SHAPES
from state import DashboardState


# ── Geocoding helpers ─────────────────────────────────────────────────────────
_DEFAULT_XLIM = (-20000000, 20000000)
_DEFAULT_YLIM = (-10000000, 15000000)

def _lon_to_mercator_x(lon: float) -> float:
    return lon * 20037508.34 / 180.0

def _lat_to_mercator_y(lat: float) -> float:
    lat = max(-89.9, min(89.9, lat))
    return math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180) * 20037508.34 / 180.0

def _geocode_country(name: str):
    """Return (xlim, ylim, geojson_geometry) in Web Mercator for the given country name, or None on failure."""
    try:
        q = urllib.parse.urlencode({
            "q": name, "format": "json", "limit": "1",
            "featuretype": "country", "polygon_geojson": "1",
        })
        url = f"https://nominatim.openstreetmap.org/search?{q}"
        req = urllib.request.Request(url, headers={"User-Agent": "HoloIntel/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            results = json.loads(resp.read())
        if not results:
            return None
        result  = results[0]
        bb      = result.get("boundingbox")   # [south, north, west, east]
        geojson = result.get("geojson")       # GeoJSON geometry dict (Polygon/MultiPolygon)
        if not bb:
            return None
        south, north, west, east = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
        dlon = (east - west) * 0.15
        dlat = (north - south) * 0.15
        x0 = _lon_to_mercator_x(west - dlon)
        x1 = _lon_to_mercator_x(east + dlon)
        y0 = _lat_to_mercator_y(south - dlat)
        y1 = _lat_to_mercator_y(north + dlat)
        return (x0, x1), (y0, y1), geojson
    except Exception:
        return None

# ── Styling ───────────────────────────────────────────────────────────────────
_BG         = "#0a0f1e"
_PANEL_BG   = "#0c1524"
_BORDER     = "#1e3a5f"
_ACCENT     = "#7dd3fc"
_PANEL_W    = 320

_HDR_CSS = (
    "font-size:12px;font-weight:bold;color:{a};"
    "letter-spacing:2px;text-transform:uppercase;"
    "margin-bottom:8px;font-family:'Courier New',monospace;"
).format(a=_ACCENT)

_HINT_CSS = "font-size:12px;color:#7a8fa6;margin-top:4px;line-height:1.4;"

_TAB_CSS = """
:host .bk-header {
    background: #0a0f1e;
    border-bottom: 1px solid #1e3a5f;
    display: flex;
    justify-content: center;
}
:host .bk-header .bk-btn-group {
    display: flex;
    justify-content: center;
    width: 100%;
}
:host .bk-tab {
    background: #0a0f1e; color: #94a3b8;
    border: none; border-bottom: 2px solid transparent;
    font-family: 'Courier New', monospace; font-size: 13px;
    font-weight: bold; letter-spacing: 1px; text-transform: uppercase;
    padding: 10px 20px;
}
:host .bk-tab:hover  { color: #cbd5e1; }
:host .bk-tab.bk-active { color: #7dd3fc; border-bottom: 2px solid #7dd3fc; }
"""

def _divider() -> pn.pane.HTML:
    """Return a fresh divider each call — Bokeh forbids reusing the same model object."""
    return pn.pane.HTML(
        f'<hr style="border:none;border-top:1px solid {_BORDER};margin:10px 0;">',
        sizing_mode="stretch_width",
    )



def _section(label: str) -> pn.pane.HTML:
    return pn.pane.HTML(
        f'<div style="{_HDR_CSS}">{label}</div>',
        sizing_mode="stretch_width",
    )


def _hint(text: str) -> pn.pane.HTML:
    return pn.pane.HTML(
        f'<div style="{_HINT_CSS}">{text}</div>',
        sizing_mode="stretch_width",
    )


def build_dashboard() -> pn.Column:
    state  = DashboardState(events=load_events())
    regions = state.param.region_filter.objects   # sorted list of region strings

    # ── Header ────────────────────────────────────────────────────────────
    header = pn.pane.HTML(
        f"""
        <div style="background:{_BG};padding:13px 20px;
                    border-bottom:3px solid {_ACCENT};
                    box-shadow:0 3px 10px {_ACCENT}66;
                    display:flex;align-items:center;justify-content:center;">
          <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700&display=swap" rel="stylesheet">
          <span style="color:#e2e8f0;font-size:22px;font-weight:700;
                       font-family:'Orbitron',sans-serif;letter-spacing:3px;">
            Crisis Intelligence Platform
          </span>
        </div>
        """,
        sizing_mode="stretch_width",
        height=50,
    )

    # ── Source checkboxes ─────────────────────────────────────────────────
    src_all_cb = pn.widgets.Checkbox(name="All", value=True)

    # One Checkbox per source; glyph rendered large in an adjacent HTML pane
    # Distinct colors and sizes per source icon
    _SRC_ICON_STYLE = {
        "GDELT":     ("#ef4444", "22px"),  # red    — conflict
        "FIRMS":     ("#f97316", "18px"),  # orange — fire
        "NOAA":      ("#fbbf24", "18px"),  # yellow — weather
        "OpenSky":   ("#38bdf8", "18px"),  # blue   — flight tracking
        "Maritime":  ("#10b981", "18px"),  # green  — ships
        "Rocket":    ("#f43f5e", "22px"),  # rose   — rocket alerts
        "Seismic":   ("#a78bfa", "18px"),  # violet — earthquakes
        "Cyber":     ("#34d399", "18px"),  # emerald — cyber
    }

    # Checkbox widgets with blank name — label rendered as HTML beside them
    _src_cbs: dict[str, pn.widgets.Checkbox] = {
        src: pn.widgets.Checkbox(name="", value=True, width=20)
        for src in SOURCE_SHAPES
    }
    src_cb_rows = pn.Column(
        *[
            pn.Row(
                _src_cbs[src],
                pn.pane.HTML(
                    f'<span style="font-size:14px;color:#e2e8f0;font-weight:bold;">{short}</span>'
                    f'&nbsp;<span style="font-size:{_SRC_ICON_STYLE[src][1]};'
                    f'color:{_SRC_ICON_STYLE[src][0]};line-height:1;">{glyph}</span>'
                    f'<span style="font-size:11px;color:#94a3b8;"> — {desc}</span>',
                    sizing_mode="stretch_width",
                    margin=0,
                ),
                sizing_mode="stretch_width",
                align="center",
                margin=(3, 0),
            )
            for src, (glyph, short, desc) in SOURCE_SHAPES.items()
        ],
        margin=0,
        sizing_mode="stretch_width",
    )

    _src_busy = {"v": False}

    def _update_src_state():
        state.source_filter = [s for s, cb in _src_cbs.items() if cb.value]

    def _src_all_toggled(event):
        if _src_busy["v"]:
            return
        _src_busy["v"] = True
        for cb in _src_cbs.values():
            cb.value = event.new
        _update_src_state()
        _src_busy["v"] = False

    def _src_cb_toggled(event):
        if _src_busy["v"]:
            return
        _src_busy["v"] = True
        _update_src_state()
        src_all_cb.value = all(cb.value for cb in _src_cbs.values())
        _src_busy["v"] = False

    src_all_cb.param.watch(_src_all_toggled, "value")
    for _cb in _src_cbs.values():
        _cb.param.watch(_src_cb_toggled, "value")

    # ── Min-severity slider ───────────────────────────────────────────────
    severity_slider = pn.widgets.IntSlider.from_param(
        state.param.min_severity,
        start=1, end=5, step=1,
        bar_color="#0ea5e9",
        sizing_mode="stretch_width",
    )

    # ── Region checkboxes (2-column grid) ────────────────────────────────
    all_cb = pn.widgets.Checkbox(name="All", value=True)
    _reg_cbs: dict[str, pn.widgets.Checkbox] = {
        r: pn.widgets.Checkbox(name=r, value=True) for r in regions
    }
    region_grid = pn.GridBox(
        *_reg_cbs.values(),
        ncols=2,
        sizing_mode="stretch_width",
    )

    _busy = {"v": False}

    def _all_toggled(event):
        if _busy["v"]:
            return
        _busy["v"] = True
        for cb in _reg_cbs.values():
            cb.value = event.new
        state.region_filter = list(regions) if event.new else []
        _busy["v"] = False

    def _reg_cb_toggled(event):
        if _busy["v"]:
            return
        _busy["v"] = True
        state.region_filter = [r for r, cb in _reg_cbs.items() if cb.value]
        all_cb.value = all(cb.value for cb in _reg_cbs.values())
        _busy["v"] = False

    all_cb.param.watch(_all_toggled, "value")
    for _rcb in _reg_cbs.values():
        _rcb.param.watch(_reg_cb_toggled, "value")

    # ── Country search ────────────────────────────────────────────────────
    country_input = pn.widgets.TextInput(
        placeholder="Search country…",
        sizing_mode="stretch_width",
        styles={"font-family": "'Courier New', monospace", "font-size": "12px"},
    )
    search_status = pn.pane.HTML(
        "",
        sizing_mode="stretch_width",
        styles={"font-size": "10px", "color": "#475569", "font-family": "'Courier New', monospace"},
    )

    def _on_country_search(event):
        name = (event.new or "").strip()
        if not name:
            state.param.update(
                map_xlim=_DEFAULT_XLIM,
                map_ylim=_DEFAULT_YLIM,
                map_highlight=None,
            )
            search_status.object = ""
            return
        search_status.object = f'<span style="color:#7dd3fc;">Searching "{name}"…</span>'

        def _fetch():
            result = _geocode_country(name)
            if result:
                xlim, ylim, geojson = result
                # Batch all three param changes → single map rebuild
                state.param.update(map_xlim=xlim, map_ylim=ylim, map_highlight=geojson)
                search_status.object = f'<span style="color:#39ff14;">&#10003; Zoomed to {name}</span>'
            else:
                search_status.object = f'<span style="color:#f87171;">&#10007; Country not found</span>'

        threading.Thread(target=_fetch, daemon=True).start()

    country_input.param.watch(_on_country_search, "value")

    # ── Right control panel ───────────────────────────────────────────────
    controls = pn.Column(
        _section("Map Search"),
        country_input,
        search_status,
        _divider(),
        _section("Sources"),
        src_all_cb,
        pn.pane.HTML(
            f'<hr style="border:none;border-top:1px dashed {_BORDER};margin:5px 0 4px;">',
            sizing_mode="stretch_width",
        ),
        src_cb_rows,
        _divider(),

        _section("Severity"),
        build_severity_legend(),
        _divider(),

        _section("Min Severity"),
        severity_slider,
        _hint("1 = all &nbsp;|&nbsp; 5 = critical only"),
        _divider(),

        _section("Regions"),
        all_cb,
        pn.pane.HTML(
            f'<hr style="border:none;border-top:1px dashed {_BORDER};margin:5px 0 4px;">',
            sizing_mode="stretch_width",
        ),
        region_grid,
        _divider(),

        pn.Card(
            pn.pane.HTML(
                f"""
                <table style="width:100%;border-collapse:collapse;
                              font-family:'Courier New',monospace;font-size:11px;color:#94a3b8;">
                  <tbody>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">GDELT</td>
                        <td style="padding:4px 0;">Conflict &amp; news events</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">NASA FIRMS</td>
                        <td style="padding:4px 0;">Satellite fire hotspots</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">OpenSky</td>
                        <td style="padding:4px 0;">Live flight tracking</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">NOAA</td>
                        <td style="padding:4px 0;">Weather alerts</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">AIS Stream</td>
                        <td style="padding:4px 0;">Maritime tracking</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">USGS</td>
                        <td style="padding:4px 0;">Seismic events</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">AlienVault OTX</td>
                        <td style="padding:4px 0;">Cyber threats</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">Yahoo Finance</td>
                        <td style="padding:4px 0;">Commodities &amp; stocks</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">ExchangeRate.host</td>
                        <td style="padding:4px 0;">Live FX rates</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">Google News RSS</td>
                        <td style="padding:4px 0;">Regional headlines</td></tr>
                    <tr><td style="padding:4px 4px 4px 0;color:#e2e8f0;">Gemini</td>
                        <td style="padding:4px 0;">AI Explorer LLM</td></tr>
                  </tbody>
                </table>
                <div style="margin-top:8px;font-size:10px;color:#475569;font-family:'Courier New',monospace;">
                  All free &amp; open — no paid subscriptions.
                </div>
                """,
                sizing_mode="stretch_width",
            ),
            title="About Data",
            collapsed=True,
            sizing_mode="stretch_width",
            styles={"background": _PANEL_BG},
            header_color=_ACCENT,
            stylesheets=[f"""
                :host .card-header {{
                    background: {_PANEL_BG};
                    border-bottom: 1px solid {_BORDER};
                    font-family: 'Courier New', monospace;
                    font-size: 11px;
                    font-weight: bold;
                    letter-spacing: 1px;
                    text-transform: uppercase;
                    padding: 6px 10px;
                }}
            """],
        ),
        pn.Spacer(),

        sizing_mode="stretch_height",
        width=_PANEL_W,
        styles={
            "background":  _PANEL_BG,
            "border-left": f"1px solid {_BORDER}",
            "padding":     "14px 12px",
            "overflow-y":  "auto",
            "min-height":  "100%",
        },
    )

    from intel_panel import build_commodities_tab, build_currency_tab  # local import avoids circular load
    from ai_panel import build_ai_tab
    from analysis_panel import build_analysis_tab

    map_body = pn.Row(
        state.map_panel,
        controls,
        sizing_mode="stretch_both",
    )

    _tab_news     = pn.Column(build_analysis_tab(state.filtered_events()), sizing_mode="stretch_both", loading=True)
    _tab_prices   = pn.Column(build_commodities_tab(),                     sizing_mode="stretch_both", loading=True)
    _tab_currency = pn.Column(build_currency_tab(),                        sizing_mode="stretch_both", loading=True)
    _tab_ai       = pn.Column(build_ai_tab(),                              sizing_mode="stretch_both", loading=True)

    def _clear_loading():
        _tab_news.loading     = False
        _tab_prices.loading   = False
        _tab_currency.loading = False
        _tab_ai.loading       = False

    pn.state.onload(_clear_loading)

    tabs = pn.Tabs(
        ("🗺  Risk Map",      map_body),
        ("📰  News & Events", _tab_news),
        ("📈  Global Prices", _tab_prices),
        ("💱  Currency FX",   _tab_currency),
        ("🤖  AI Explorer",   _tab_ai),
        dynamic=True,
        sizing_mode="stretch_both",
        stylesheets=[_TAB_CSS],
    )

    return pn.Column(
        header,
        tabs,
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )
