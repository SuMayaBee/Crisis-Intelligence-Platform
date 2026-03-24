import os
from pathlib import Path

import holoviews as hv
import panel as pn
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "10"))


_VIEWPORT_CSS = """
html, body {
    height: 100%;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
.bk-root, .bk-root > div {
    height: 100% !important;
}
.bk-tab-pane {
    overflow-y: auto !important;
    height: 100% !important;
}
"""


def initialize_runtime() -> None:
    load_dotenv(BASE_DIR / ".env")
    pn.extension(
        "tabulator",
        "deckgl",
        "filedropper",
        "codeeditor",
        theme="dark",
        sizing_mode="stretch_width",
        raw_css=[_VIEWPORT_CSS],
        css_files=["https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css"],
    )
    hv.extension("bokeh")
