"""
AI Chat tab — custom Panel ChatInterface with DuckDB + Gemini + hvPlot.

Features:
  • SQL queries via DuckDB
  • Live ticker fetch via Yahoo Finance
  • Google Search grounding (streaming)
  • GeoViews geographic maps for lat/lon data
  • Multi-chart grid layouts for overview queries
  • HoloViz code display after every chart
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading

import duckdb
import geoviews as gv
import holoviews as hv
import hvplot.pandas  # noqa: F401
import pandas as pd
import panel as pn
from cartopy import crs
from google import genai

from data.context import (
    FX_REGION_GROUPS,
    load_commodities_history,
    load_fx_live,
    load_market_sample,
    load_ohlcv,
)
from data.events import load_events

gv.extension("bokeh")

# ── Style constants ───────────────────────────────────────────────────────────
_BG      = "#0a0f1e"
_BORDER  = "#1e3a5f"
_ACCENT  = "#7dd3fc"
_MUTED   = "#475569"
_PLOT_KW = dict(responsive=True, height=420, grid=True, fontscale=0.85)

# ── Gemini client ─────────────────────────────────────────────────────────────
_client: genai.Client | None = None
_runtime_api_key: str = ""   # set from the sidebar widget at runtime


def _get_client() -> genai.Client:
    global _client, _runtime_api_key
    key = _runtime_api_key or os.getenv("GEMINI_API_KEY", os.getenv("LLM_API_KEY", ""))
    # Rebuild client when the key changes
    if _client is None or getattr(_client, "_api_key_used", None) != key:
        _client = genai.Client(api_key=key)
        _client._api_key_used = key  # type: ignore[attr-defined]
    return _client


def _get_model() -> str:
    return os.getenv("LLM_MODEL", "gemini-2.5-flash")


# ── DuckDB ────────────────────────────────────────────────────────────────────
_con: duckdb.DuckDBPyConnection | None = None
_SCHEMA_CACHE: str = ""


def _init_db() -> duckdb.DuckDBPyConnection:
    global _con, _SCHEMA_CACHE
    if _con is not None:
        return _con

    _con = duckdb.connect(":memory:")

    all_fx = list({c for codes in FX_REGION_GROUPS.values() for c in codes})
    events_df     = load_events()
    commodities_df = load_commodities_history()
    fx_df         = load_fx_live(all_fx)
    market_df     = load_market_sample()

    _con.execute("CREATE TABLE risk_events  AS SELECT * FROM events_df")
    _con.execute("CREATE TABLE commodities  AS SELECT * FROM commodities_df")
    _con.execute("CREATE TABLE currency_fx  AS SELECT * FROM fx_df")
    _con.execute("CREATE TABLE market       AS SELECT * FROM market_df")

    parts = []
    for table in ["risk_events", "commodities", "currency_fx", "market"]:
        cols   = _con.execute(f"DESCRIBE {table}").fetchdf()
        col_desc = ", ".join(f"{r['column_name']} ({r['column_type']})" for _, r in cols.iterrows())
        sample = _con.execute(f"SELECT * FROM {table} LIMIT 3").fetchdf().to_string(index=False)
        parts.append(f"TABLE: {table}\n  Columns: {col_desc}\n  Sample:\n{sample}")
    _SCHEMA_CACHE = "\n\n".join(parts)
    return _con


# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are HoloIntel AI, an analyst for a global risk intelligence platform.
You have access to a DuckDB database with these tables:

{schema}

When the user asks a question:
1. Decide whether it needs SQL, a live ticker fetch, a web search, charts, or just text.
2. Respond with a JSON object (no markdown fences) with these fields:
   - "answer": string — short natural-language commentary
   - "sql": string | null — DuckDB SQL query (LIMIT 1000 max)
   - "tickers": list[string] | null — Yahoo Finance tickers for live stock/crypto data
     (e.g. ["TSLA"], ["AAPL","MSFT"]). Data columns: date, open, high, low, close, volume, symbol.
   - "search": bool — true for real-time news/events not in the tables
   - "search_query": string | null — optimised Google search query when search=true
   - "charts": list of chart specs | null — one OR more charts to display:
       Each chart spec has:
       - "kind": "line"|"bar"|"barh"|"scatter"|"area"|"hist"|"box"|"heatmap"|"step"|"map"
         Use "map" when data has lat/lon columns and geographic context makes sense.
       - "x": column for x-axis
       - "y": column for y-axis (string or list)
       - "by": column to color-group by (optional)
       - "title": chart title
   - "show_table": bool — whether to show raw data table

Rules:
- SQL must be valid DuckDB SQL with single-quoted strings.
- For overview/summary queries (e.g. "give me a risk overview"), return 2-3 charts in "charts".
- Use kind="map" when data has lat and lon columns.
- For bar charts with string x-axis prefer "barh".
- "by" only when grouping adds value.
- For tickers: default line chart with x="date", y="close", by="symbol" if multiple.
- Use "search" for news, policy, sanctions, geopolitical updates.
- Respond ONLY with the JSON object, nothing else.
"""


# ── Google Search (streaming) ─────────────────────────────────────────────────
def _search_web_stream(query: str):
    client = _get_client()
    stream = client.models.generate_content_stream(
        model=_get_model(),
        contents=f"Answer in 3-5 concise sentences. Be brief and factual.\n\nQuestion: {query}",
        config=genai.types.GenerateContentConfig(
            tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
            temperature=0.1,
        ),
    )
    for chunk in stream:
        if chunk.text:
            yield chunk.text


# ── LLM decision call ─────────────────────────────────────────────────────────
def _ask_llm(user_msg: str, history: list[dict]) -> dict:
    client  = _get_client()
    system  = _SYSTEM_PROMPT.format(schema=_SCHEMA_CACHE)
    contents = []
    for h in history[-10:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append(genai.types.Content(role=role, parts=[genai.types.Part(text=h["text"])]))
    contents.append(genai.types.Content(role="user", parts=[genai.types.Part(text=user_msg)]))

    response = client.models.generate_content(
        model=_get_model(),
        contents=contents,
        config=genai.types.GenerateContentConfig(system_instruction=system, temperature=0.1),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return json.loads(text)


# ── Chart builders ────────────────────────────────────────────────────────────
def _hvplot_code(df_name: str, kind: str, kwargs: dict) -> str:
    """Generate the hvPlot code string for display."""
    kw_parts = []
    for k, v in kwargs.items():
        if k in ("responsive", "grid"):
            kw_parts.append(f"{k}={v}")
        else:
            kw_parts.append(f'{k}={v!r}')
    kw_str = ", ".join(kw_parts)
    return f"import hvplot.pandas\n\n{df_name}.hvplot.{kind}({kw_str})"


def _make_geo_map(df: pd.DataFrame, spec: dict) -> pn.viewable.Viewable:
    """GeoViews point map for DataFrames with lat/lon columns."""
    title  = spec.get("title", "Geographic Events")
    by     = spec.get("by")
    color  = by if by and by in df.columns else "severity" if "severity" in df.columns else None
    hover_cols = [c for c in ["title", "category", "severity", "source", "region"] if c in df.columns]

    points = gv.Points(
        df, kdims=["lon", "lat"],
        vdims=[c for c in (([color] if color else []) + hover_cols) if c in df.columns],
    ).opts(
        color=color or "steelblue",
        cmap="RdYlGn_r" if color == "severity" else "Category10",
        size=6, alpha=0.7,
        tools=["hover"], title=title,
        width=700, height=420,
        bgcolor="#0a0f1e",
        xaxis=None, yaxis=None,
    )
    tiles = gv.tile_sources.CartoDark()
    chart = (tiles * points).opts(projection=crs.GOOGLE_MERCATOR)
    code  = (
        "import geoviews as gv\n"
        "from cartopy import crs\n\n"
        f"points = gv.Points(df, kdims=['lon','lat'], vdims={[color]+hover_cols!r})\n"
        "tiles  = gv.tile_sources.CartoDark()\n"
        "map_   = (tiles * points).opts(projection=crs.GOOGLE_MERCATOR)"
    )
    return _wrap_with_code(pn.pane.HoloViews(chart, sizing_mode="stretch_both", min_height=420), code)


def _make_chart(df: pd.DataFrame, spec: dict) -> pn.viewable.Viewable:
    """Build an hvPlot chart + collapsible code block."""
    kind  = spec.get("kind", "line")
    title = spec.get("title", "")
    x     = spec.get("x")
    y     = spec.get("y")
    by    = spec.get("by")

    # Route geographic data to GeoViews
    if kind == "map" or ({"lat", "lon"}.issubset(df.columns) and kind in ("scatter", "points", "map")):
        return _make_geo_map(df, spec)

    # Coerce column types to avoid int/str comparison errors in hvPlot
    df = df.copy()
    if x and x in df.columns and kind in ("bar", "barh"):
        df[x] = df[x].astype(str)
    if y and y in df.columns:
        df[y] = pd.to_numeric(df[y], errors="coerce")

    kwargs: dict = {**_PLOT_KW, "title": title}
    if x:               kwargs["x"]  = x
    if y:               kwargs["y"]  = y
    if by and by in df.columns:
        kwargs["by"] = by

    plot_fn = getattr(df.hvplot, kind, df.hvplot.line)
    chart   = plot_fn(**kwargs)
    code    = _hvplot_code("df", kind, kwargs)
    return _wrap_with_code(pn.pane.HoloViews(chart, sizing_mode="stretch_both", min_height=400), code)


def _wrap_with_code(chart_pane: pn.viewable.Viewable, code: str) -> pn.viewable.Viewable:
    """Wrap a chart with a collapsible HoloViz code block beneath it."""
    code_block = pn.pane.Markdown(
        f"```python\n{code}\n```",
        sizing_mode="stretch_width",
    )
    accordion = pn.Accordion(
        ("📋 View HoloViz Code", code_block),
        sizing_mode="stretch_width",
        styles={"border": f"1px solid {_BORDER}", "border-radius": "4px"},
    )
    return pn.Column(chart_pane, accordion, sizing_mode="stretch_both")


def _make_multi_chart(df: pd.DataFrame, specs: list[dict]) -> pn.viewable.Viewable:
    """Render multiple charts in a 2-column grid."""
    panels = []
    for spec in specs:
        try:
            panels.append(_make_chart(df, spec))
        except Exception:
            pass
    if not panels:
        return pn.pane.Markdown("*Could not render charts.*")
    if len(panels) == 1:
        return panels[0]
    return pn.GridBox(*panels, ncols=2, sizing_mode="stretch_both")


def _make_table(df: pd.DataFrame) -> pn.widgets.Tabulator:
    clean = df.copy()
    for col in clean.columns:
        if clean[col].dtype == "object":
            clean[col] = clean[col].astype(str)
    return pn.widgets.Tabulator(
        clean.reset_index(drop=True),
        sizing_mode="stretch_both",
        height=350,
        theme="midnight",
        page_size=20,
        show_index=False,
    )


# ── Chat callback ─────────────────────────────────────────────────────────────
_history: list[dict] = []


async def _chat_callback(contents: str, user: str, instance: pn.chat.ChatInterface):
    con = _init_db()
    _history.append({"role": "user", "text": contents})

    try:
        result = _ask_llm(contents, _history)
    except json.JSONDecodeError:
        yield "I had trouble parsing the response. Could you rephrase your question?"
        return
    except Exception as e:
        yield f"**Error contacting AI:** {e}"
        return

    answer      = result.get("answer", "")
    sql         = result.get("sql")
    tickers     = result.get("tickers") or ([result["ticker"]] if result.get("ticker") else None)
    do_search   = result.get("search", False)
    search_query = result.get("search_query") or contents
    chart_specs = result.get("charts") or ([result["chart"]] if result.get("chart") else None)
    show_table  = result.get("show_table", False)

    _history.append({"role": "assistant", "text": answer})

    if answer:
        yield pn.pane.Markdown(answer)

    # ── Google Search (streamed) ──────────────────────────────────────────────
    if do_search:
        try:
            q: queue.Queue = queue.Queue()

            def _run():
                try:
                    for chunk in _search_web_stream(search_query):
                        q.put(chunk)
                finally:
                    q.put(None)

            threading.Thread(target=_run, daemon=True).start()
            accumulated = ""
            while True:
                chunk = await asyncio.get_event_loop().run_in_executor(None, q.get)
                if chunk is None:
                    break
                accumulated += chunk
                yield accumulated
        except Exception as e:
            yield f"**Search Error:** {e}"
        return

    # ── Live ticker fetch ─────────────────────────────────────────────────────
    df = None
    if tickers:
        end   = pd.Timestamp.now().strftime("%Y-%m-%d")
        start = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime("%Y-%m-%d")
        frames = []
        for t in tickers:
            tdf = load_ohlcv(t, start, end)
            if not tdf.empty:
                tdf["symbol"] = t
                frames.append(tdf)
        if not frames:
            yield pn.pane.Markdown(f"*Could not fetch `{', '.join(tickers)}`.*")
            return
        df = pd.concat(frames, ignore_index=True)
        if not chart_specs:
            multi = len(tickers) > 1
            chart_specs = [{
                "kind": "line", "x": "date", "y": "close",
                "by": "symbol" if multi else None,
                "title": " vs ".join(tickers) + " — Closing Price",
            }]

    # ── SQL query ─────────────────────────────────────────────────────────────
    elif sql:
        try:
            df = con.execute(sql).fetchdf()
        except Exception as e:
            yield pn.pane.Markdown(f"**SQL Error:** `{e}`\n\n```sql\n{sql}\n```")
            return

    # ── Render charts ─────────────────────────────────────────────────────────
    if df is not None and not df.empty:
        if chart_specs:
            try:
                if len(chart_specs) > 1:
                    yield _make_multi_chart(df, chart_specs)
                else:
                    yield _make_chart(df, chart_specs[0])
            except Exception as e:
                yield pn.pane.Markdown(f"**Chart Error:** {e}")

        if show_table or not chart_specs:
            try:
                yield _make_table(df)
            except Exception as e:
                yield pn.pane.Markdown(f"**Table Error:** {e}")

    elif df is not None and df.empty:
        yield pn.pane.Markdown("*No data found for that query.*")


# ── Suggestions ───────────────────────────────────────────────────────────────
_SUGGESTIONS = [
    "Give me a risk overview of Asia",
    "Plot gold vs oil price over time",
    "Show conflict events in the Middle East on a map",
    "Which currencies dropped the most today?",
    "Show the top 10 most recent critical events",
    "Plot Apple vs Microsoft",
    "What's the latest news on oil prices?",
    "Which market is up the most today?",
]


# ── Sidebar ───────────────────────────────────────────────────────────────────
def _build_sidebar() -> pn.Column:
    """API key sidebar shown to every user."""
    global _runtime_api_key

    def _label(text: str) -> pn.pane.HTML:
        return pn.pane.HTML(
            f'<div style="font-size:10px;font-weight:bold;color:{_ACCENT};'
            f'letter-spacing:2px;text-transform:uppercase;'
            f'font-family:\'Courier New\',monospace;margin-bottom:4px;">{text}</div>',
            sizing_mode="stretch_width",
        )

    def _hint(text: str) -> pn.pane.HTML:
        return pn.pane.HTML(
            f'<div style="font-size:10px;color:{_MUTED};line-height:1.5;margin-top:4px;">{text}</div>',
            sizing_mode="stretch_width",
        )

    def _divider() -> pn.pane.HTML:
        return pn.pane.HTML(
            f'<hr style="border:none;border-top:1px solid {_BORDER};margin:14px 0;">',
            sizing_mode="stretch_width",
        )

    api_input = pn.widgets.PasswordInput(
        placeholder="AIza...",
        sizing_mode="stretch_width",
    )
    status = pn.pane.HTML(
        '<div style="font-size:11px;color:#475569;margin-top:6px;">No key set — using server default</div>',
        sizing_mode="stretch_width",
    )

    def _on_key(event):
        global _runtime_api_key, _client
        key = (event.new or "").strip()
        _runtime_api_key = key
        _client = None  # force rebuild on next call
        if key:
            status.object = (
                '<div style="font-size:11px;color:#4ade80;margin-top:6px;">✓ API key set</div>'
            )
        else:
            status.object = (
                '<div style="font-size:11px;color:#475569;margin-top:6px;">No key set — using server default</div>'
            )

    api_input.param.watch(_on_key, "value")

    model_select = pn.widgets.Select(
        options=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
        value=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        sizing_mode="stretch_width",
    )

    def _on_model(event):
        os.environ["LLM_MODEL"] = event.new

    model_select.param.watch(_on_model, "value")

    capabilities = pn.pane.HTML(
        f"""
        <div style="font-size:11px;color:#94a3b8;line-height:1.8;">
          <b style="color:{_ACCENT};">Data sources:</b><br>
          • Risk events (ACLED, FIRMS…)<br>
          • Commodities history<br>
          • Currency FX rates<br>
          • Market prices<br>
          • Live stocks via Yahoo Finance<br>
          • Web search via Google<br><br>
          <b style="color:{_ACCENT};">Chart types:</b><br>
          • Line, bar, scatter, area<br>
          • GeoViews maps (lat/lon data)<br>
          • Multi-chart grid layouts<br><br>
          <b style="color:{_ACCENT};">HoloViz code:</b><br>
          Every chart shows the code<br>
          that generated it.
        </div>
        """,
        sizing_mode="stretch_width",
    )

    get_key_link = pn.pane.HTML(
        f'<a href="https://aistudio.google.com/apikey" target="_blank" '
        f'style="font-size:10px;color:{_ACCENT};text-decoration:none;">'
        f'→ Get a free Gemini API key</a>',
        sizing_mode="stretch_width",
    )

    return pn.Column(
        _label("Gemini API Key"),
        api_input,
        status,
        get_key_link,
        _divider(),
        _label("Model"),
        model_select,
        _divider(),
        _label("Capabilities"),
        capabilities,
        pn.Spacer(),
        width=220,
        sizing_mode="stretch_height",
        styles={
            "background":   "#0c1524",
            "border-right": f"1px solid {_BORDER}",
            "padding":      "16px 14px",
            "overflow-y":   "auto",
        },
    )


# ── Build tab ─────────────────────────────────────────────────────────────────
def build_ai_tab() -> pn.viewable.Viewable:
    _init_db()

    chat = pn.chat.ChatInterface(
        callback=_chat_callback,
        callback_user="HoloIntel AI",
        show_rerun=False,
        show_undo=True,
        show_clear=True,
        placeholder_text="Ask about risk events, commodities, stocks, or world news...",
        sizing_mode="stretch_both",
        min_height=600,
        callback_exception="verbose",
    )

    chat.send(
        pn.pane.Markdown(
            "**Welcome to HoloIntel AI**\n\n"
            "I can query risk events, commodities, currencies, live stocks, and search the web. "
            "Charts include the HoloViz code that generated them.\n\n"
            + "\n".join(f"- *{s}*" for s in _SUGGESTIONS),
        ),
        user="HoloIntel AI",
        respond=False,
    )

    return pn.Row(
        _build_sidebar(),
        pn.Column(
            chat,
            sizing_mode="stretch_both",
            min_height=600,
            styles={"background": _BG},
        ),
        sizing_mode="stretch_both",
        styles={"background": _BG},
    )
