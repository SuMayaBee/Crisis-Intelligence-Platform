import os
from pathlib import Path

import holoviews as hv
import panel as pn
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))


def initialize_runtime() -> None:
    load_dotenv(BASE_DIR / ".env")
    pn.extension(
        "tabulator",
        "deckgl",
        theme="dark",
        sizing_mode="stretch_width",
    )
    hv.extension("bokeh")
