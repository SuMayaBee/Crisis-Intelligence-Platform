from settings import initialize_runtime

initialize_runtime()

from dashboard import build_dashboard  # noqa: E402

build_dashboard().servable(title="HoloIntel — Global Risk Map")
