"""
AI Chat tab — Lumen AI processing with full ExplorerUI.

ExplorerUI is built internally so Lumen's full agent stack
(Planner → SQLAgent → VegaLiteAgent / DeckGLAgent) is active.
Uses ExplorerUI._page (panel_material_ui.Page) directly for
proper height propagation to charts and tables.
"""
from __future__ import annotations

import os

import lumen.ai as lmai
import panel as pn
from lumen.sources.duckdb import DuckDBSource

from data.context import FX_REGION_GROUPS, load_commodities_history, load_fx_live
from data.events import load_events

_BG = "#0a0f1e"


def build_ai_tab() -> pn.viewable.Viewable:
    # ── Data via DuckDB (proper SQL engine for SQLAgent) ──────────────────────
    all_fx = list({c for codes in FX_REGION_GROUPS.values() for c in codes})

    source = DuckDBSource.from_df(
        tables={
            "risk_events":  load_events(),
            "commodities":  load_commodities_history(),
            "currency_fx":  load_fx_live(all_fx),
        }
    )

    # Pre-warm schema cache with full DISTINCT queries (limit=None).
    for tbl in source.get_tables():
        source.get_schema(tbl)

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm = lmai.llm.Google(
        api_key=os.getenv("GEMINI_API_KEY", os.getenv("LLM_API_KEY", "")),
        model_kwargs={
            "default": {"model": os.getenv("LLM_MODEL", "gemini-2.5-flash")},
        },
    )

    # ── Build ExplorerUI with Page configured for tab embedding ───────────────
    # ExplorerUI.__panel__() returns self._main (a bare material-UI Row) which
    # loses the CSS grid / flex context that Page provides.  Without Page, the
    # nested HSplit → Paper → Tabs → VSplit chain has no concrete parent height,
    # so ALL content (tables, charts) collapses to 0 px.
    #
    # Using _page (panel_material_ui.Page) restores proper height propagation.
    # Page defaults to 100vw × 100vh; we override to 100% × 100% so it fits
    # inside our dashboard tab.  The Page's AppBar (position:fixed) would
    # overlap our dashboard header, so we hide it and its toolbar spacer via
    # MUI sx nested selectors.
    ui = lmai.ExplorerUI(
        data=source,
        llm=llm,
        title="HOLOINTEL AI",
        page_config={
            "sx": {
                "height": "100%",
                "width": "100%",
                # Hide the Page's fixed AppBar and the toolbar spacer inside
                # the main area — our dashboard already has its own header.
                "& .header": {"display": "none"},
                "& .main .MuiToolbar-root": {"display": "none"},
            },
        },
        suggestions=[
            ("bar_chart",        "Which region has the most conflict events?"),
            ("crisis_alert",     "Show severity 5 events"),
            ("show_chart",       "Plot gold vs oil price"),
            ("currency_exchange","Which currencies dropped the most today?"),
        ],
    )

    # Return the full Page wrapper — it has the CSS grid + flex layout that
    # makes HSplit, Paper, Tabs, VSplit, and Vega all get proper height.
    return pn.Column(
        ui._page,
        sizing_mode="stretch_both",
        min_height=600,
        styles={"background": _BG},
    )
