"""
AI Chat tab — custom Panel ChatInterface with DuckDB + Gemini + hvPlot.

Replaces Lumen ExplorerUI entirely.  The LLM generates SQL queries and
chart specs; we execute via DuckDB and render with hvPlot/Tabulator.
"""
from __future__ import annotations

import json
import os
import traceback

import duckdb
import hvplot.pandas  # noqa: F401 — registers .hvplot accessor
import pandas as pd
import panel as pn
from google import genai

from data.context import FX_REGION_GROUPS, load_commodities_history, load_fx_live
from data.events import load_events

# ── Style constants (match dashboard) ────────────────────────────────────────
_BG     = "#0a0f1e"
_PANEL_BG = "#0c1524"
_BORDER = "#1e3a5f"
_ACCENT = "#7dd3fc"
_MUTED  = "#475569"
_PLOT_KW = dict(responsive=True, height=420, grid=True, fontscale=0.85)

# ── Gemini client (lazy init) ────────────────────────────────────────────────
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", os.getenv("LLM_API_KEY", ""))
        _client = genai.Client(api_key=api_key)
    return _client


def _get_model() -> str:
    return os.getenv("LLM_MODEL", "gemini-2.5-flash")


# ── DuckDB connection (module-level, created once) ───────────────────────────
_con: duckdb.DuckDBPyConnection | None = None
_SCHEMA_CACHE: str = ""


def _init_db() -> duckdb.DuckDBPyConnection:
    global _con, _SCHEMA_CACHE
    if _con is not None:
        return _con

    _con = duckdb.connect(":memory:")

    all_fx = list({c for codes in FX_REGION_GROUPS.values() for c in codes})
    events_df = load_events()
    commodities_df = load_commodities_history()
    fx_df = load_fx_live(all_fx)

    _con.execute("CREATE TABLE risk_events AS SELECT * FROM events_df")
    _con.execute("CREATE TABLE commodities AS SELECT * FROM commodities_df")
    _con.execute("CREATE TABLE currency_fx AS SELECT * FROM fx_df")

    # Build schema description for the LLM prompt
    parts = []
    for table in ["risk_events", "commodities", "currency_fx"]:
        cols = _con.execute(f"DESCRIBE {table}").fetchdf()
        col_desc = ", ".join(f"{r['column_name']} ({r['column_type']})" for _, r in cols.iterrows())
        sample = _con.execute(f"SELECT * FROM {table} LIMIT 3").fetchdf().to_string(index=False)
        parts.append(f"TABLE: {table}\n  Columns: {col_desc}\n  Sample:\n{sample}")
    _SCHEMA_CACHE = "\n\n".join(parts)
    return _con


# ── System prompt ────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are HoloIntel AI, an analyst for a global risk intelligence platform.
You have access to a DuckDB database with these tables:

{schema}

When the user asks a question:
1. Decide whether it needs a SQL query, a chart, or just a text answer.
2. Respond with a JSON object (no markdown fences) with these fields:
   - "answer": string — a short natural-language answer or commentary
   - "sql": string | null — a DuckDB SQL query to run (if data is needed)
   - "chart": object | null — chart spec if a visualization is appropriate:
       - "kind": one of "line", "bar", "barh", "scatter", "area", "hist", "box", "heatmap", "step"
       - "x": column name for x-axis (string)
       - "y": column name for y-axis (string or list of strings)
       - "by": column to color-group by (string, optional)
       - "title": chart title (string)
   - "show_table": bool — whether to also show the raw data table

Rules:
- SQL must be valid DuckDB SQL. Use single quotes for strings.
- Always LIMIT results to 1000 rows max unless the user asks for everything.
- If the user asks to "plot" or "show chart", always include a chart spec.
- If the question is conversational (greeting, thanks, etc.), just answer with text.
- For bar charts with string/categorical x-axis, prefer "barh" (horizontal).
- The "by" field should only be used when grouping makes sense for the data.
- Respond ONLY with the JSON object, nothing else.
"""


def _ask_llm(user_msg: str, history: list[dict]) -> dict:
    """Send message to Gemini and parse the JSON response."""
    client = _get_client()
    model = _get_model()

    schema = _SCHEMA_CACHE
    system = _SYSTEM_PROMPT.format(schema=schema)

    # Build conversation history for context
    contents = []
    for h in history[-10:]:  # last 10 messages for context
        role = "user" if h["role"] == "user" else "model"
        contents.append(genai.types.Content(role=role, parts=[genai.types.Part(text=h["text"])]))
    contents.append(genai.types.Content(role="user", parts=[genai.types.Part(text=user_msg)]))

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=genai.types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.1,
        ),
    )

    text = response.text.strip()
    # Strip markdown code fences if the LLM wrapped them
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


# ── Chart builder ────────────────────────────────────────────────────────────
def _make_chart(df: pd.DataFrame, spec: dict) -> pn.pane.HoloViews:
    """Create an hvPlot chart from a DataFrame and chart spec."""
    kind = spec.get("kind", "line")
    x = spec.get("x")
    y = spec.get("y")
    by = spec.get("by")
    title = spec.get("title", "")

    kwargs = {**_PLOT_KW, "title": title}
    if x:
        kwargs["x"] = x
    if y:
        kwargs["y"] = y
    if by and by in df.columns:
        kwargs["by"] = by

    plot_fn = getattr(df.hvplot, kind, df.hvplot.line)
    chart = plot_fn(**kwargs)
    return pn.pane.HoloViews(chart, sizing_mode="stretch_both", min_height=400)


# ── Table builder ────────────────────────────────────────────────────────────
def _make_table(df: pd.DataFrame) -> pn.widgets.Tabulator:
    """Create a styled Tabulator table."""
    # Coerce object columns with mixed types to strings to avoid
    # Tabulator sorting/pagination TypeError on comparisons.
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


# ── Chat callback ────────────────────────────────────────────────────────────
_history: list[dict] = []


async def _chat_callback(contents: str, user: str, instance: pn.chat.ChatInterface):
    """Process user message → LLM → SQL → chart/table → yield responses."""
    con = _init_db()
    _history.append({"role": "user", "text": contents})

    # Call Gemini
    try:
        result = _ask_llm(contents, _history)
    except json.JSONDecodeError:
        yield pn.pane.Markdown(
            "I had trouble understanding the response. Could you rephrase your question?",
        )
        return
    except Exception as e:
        yield pn.pane.Markdown(f"**Error contacting AI:** {e}")
        return

    answer = result.get("answer", "")
    sql = result.get("sql")
    chart_spec = result.get("chart")
    show_table = result.get("show_table", False)

    _history.append({"role": "assistant", "text": answer})

    # 1. Always show the text answer
    if answer:
        yield pn.pane.Markdown(answer)

    # 2. Execute SQL if provided
    df = None
    if sql:
        try:
            df = con.execute(sql).fetchdf()
        except Exception as e:
            yield pn.pane.Markdown(f"**SQL Error:** `{e}`\n\n```sql\n{sql}\n```")
            return

    if df is not None and not df.empty:
        # 3. Show chart if requested
        if chart_spec:
            try:
                yield _make_chart(df, chart_spec)
            except Exception as e:
                yield pn.pane.Markdown(f"**Chart Error:** {e}")

        # 4. Show table if requested (or if no chart)
        if show_table or not chart_spec:
            try:
                yield _make_table(df)
            except Exception as e:
                yield pn.pane.Markdown(f"**Table Error:** {e}")
    elif df is not None and df.empty:
        yield pn.pane.Markdown("*No data found for that query.*")


# ── Suggestions as clickable buttons ─────────────────────────────────────────
_SUGGESTIONS = [
    "Which region has the most conflict events?",
    "Show severity 5 events",
    "Plot gold vs oil price over time",
    "Which currencies dropped the most today?",
    "Show the top 10 most recent critical events",
    "Compare commodity prices this year",
]


# ── Build the AI tab ─────────────────────────────────────────────────────────
def build_ai_tab() -> pn.viewable.Viewable:
    _init_db()  # warm up data + schema

    chat = pn.chat.ChatInterface(
        callback=_chat_callback,
        callback_user="HoloIntel AI",
        show_rerun=False,
        show_undo=True,
        show_clear=True,
        placeholder_text="Ask about risk events, commodities, or currencies...",
        sizing_mode="stretch_both",
        min_height=600,
    )

    # Welcome message
    chat.send(
        pn.pane.Markdown(
            "**Welcome to HoloIntel AI**\n\n"
            "I can query risk events, commodity prices, and currency exchange rates. "
            "Try one of the suggestions below, or ask your own question.\n\n"
            + "\n".join(f"- *{s}*" for s in _SUGGESTIONS),
        ),
        user="HoloIntel AI",
        respond=False,
    )

    return pn.Column(
        chat,
        sizing_mode="stretch_both",
        min_height=600,
        styles={"background": _BG},
    )
