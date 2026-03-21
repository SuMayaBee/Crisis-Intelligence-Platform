# HoloIntel MVP

A HoloViz-based Global Early Warning and Risk Intelligence dashboard built from open-data APIs you already validated.

This MVP intentionally **excludes**:

- Scheduled ingestion jobs
- Persistent storage (Parquet + DuckDB)
- LLM narrative layer

It includes:

- Unified event model from sample API outputs (ACLED, FIRMS, OpenSky, NOAA)
- Global map with source layer toggles
- "What changed in last 24h" analytics panel
- Region risk score table with explainable drivers
- Time-series drill-down for event counts and macro indicators
- Alert feed with evidence links

## Project layout

```text
holoviz-risk-platform/
  app/
    app.py
  data/
    acled_sample.csv
    firms_sample.csv
    opensky_sample.csv
    noaa_sample.csv
    macro_sample.csv
  requirements.txt
  README.md
```

## Run locally

```bash
cd /home/sumaiya/Desktop/acled/holoviz-risk-platform
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
panel serve app/app.py --autoreload --show --port 5007
```

Open:

- http://localhost:5007/app

## Environment variables (.env)

Create a `.env` file at project root for live APIs. For ACLED, cookie-based auth is supported.

```env
# ACLED (preferred: session cookie from browser/Postman)
ACLED_COOKIE=SSESS...=...
ACLED_LIMIT=200
ACLED_EVENT_DATE_RANGE=2025-03-01|2026-03-21

# Optional fallback (if cookie not provided)
ACLED_EMAIL=your_email
ACLED_PASSWORD=your_password

# Other APIs
FIRMS_MAP_KEY=...
EIA_API_KEY=...
FRED_API_KEY=...
```

## Next phases (later)

1. Ingestion workers for each API
2. Parquet + DuckDB storage and versioned snapshots
3. LLM-assisted briefings and explainers
