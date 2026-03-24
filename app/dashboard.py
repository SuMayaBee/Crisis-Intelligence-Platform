"""
Full-page layout: map fills the screen, compact controls on the right.
No template sidebar.

Right panel contains:
  - Severity color indicator (legend)
  - Min-severity slider
  - Region checkboxes  (All + one per region; initially all ticked)
"""
from __future__ import annotations

import panel as pn

from data.events import load_events
from legend import build_severity_legend, SOURCE_SHAPES
from state import DashboardState

# ── Styling ───────────────────────────────────────────────────────────────────
_BG         = "#0a0f1e"
_PANEL_BG   = "#0c1524"
_BORDER     = "#1e3a5f"
_ACCENT     = "#7dd3fc"
_PANEL_W    = 320

_HDR_CSS = (
    "font-size:10px;font-weight:bold;color:{a};"
    "letter-spacing:2px;text-transform:uppercase;"
    "margin-bottom:8px;font-family:'Courier New',monospace;"
).format(a=_ACCENT)

_HINT_CSS = "font-size:10px;color:#475569;margin-top:4px;line-height:1.4;"

_TAB_CSS = """
:host .bk-header { background: #0a0f1e; border-bottom: 1px solid #1e3a5f; }
:host .bk-tab {
    background: #0a0f1e; color: #475569;
    border: none; border-bottom: 2px solid transparent;
    font-family: 'Courier New', monospace; font-size: 10px;
    letter-spacing: 1.5px; text-transform: uppercase;
    padding: 9px 18px;
}
:host .bk-tab:hover  { color: #94a3b8; }
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
                    border-bottom:1px solid {_BORDER};display:flex;align-items:center;">
          <span style="color:#e2e8f0;font-size:17px;font-weight:bold;
                       font-family:sans-serif;letter-spacing:0.5px;">
            HoloIntel &mdash; Global Risk Map
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
        "OpenSky":   ("#38bdf8", "18px"),  # blue   — aviation
        "NOAA":      ("#22d3ee", "18px"),  # teal   — weather
        "Maritime":  ("#0ea5e9", "18px"),  # sky    — ships
        "Rocket":    ("#f43f5e", "22px"),  # rose   — alerts are critical
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
                    f'<span style="font-size:12px;color:#e2e8f0;">{short}</span>'
                    f'<span style="font-size:11px;color:#475569;"> (Source: {src})</span>'
                    f'&nbsp;<span style="font-size:{_SRC_ICON_STYLE[src][1]};'
                    f'color:{_SRC_ICON_STYLE[src][0]};line-height:1;">{glyph}</span>',
                    sizing_mode="stretch_width",
                    margin=0,
                ),
                sizing_mode="stretch_width",
                align="center",
                margin=(3, 0),
            )
            for src, (glyph, short, _desc) in SOURCE_SHAPES.items()
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

    # ── Right control panel ───────────────────────────────────────────────
    controls = pn.Column(
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

    map_body = pn.Row(
        state.map_panel,
        controls,
        sizing_mode="stretch_both",
    )

    tabs = pn.Tabs(
        ("🗺  Risk Map",    map_body),
        ("📈  Global Prices", build_commodities_tab()),
        ("💱  Currency FX", build_currency_tab()),
        ("🤖  AI Explorer", build_ai_tab()),
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
