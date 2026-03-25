# Crisis Intelligence Platform

A real-time global risk intelligence dashboard built entirely with the **HoloViz ecosystem** — no JavaScript, no separate frontend, no paid data subscriptions. Just Python and free APIs.

---

## Motivation

The Iran-Israel conflict, oil prices spiking, currencies crashing overnight — all this information exists but it's scattered across a dozen tools and paywalled platforms. I wanted to bring it all into one place, built entirely in Python with the HoloViz stack, using only free APIs. This is that platform — and a demonstration of how far HoloViz can go on a real-world, data-heavy application.
---

## What is HoloViz?

HoloViz is a coordinated set of Python libraries built and maintained by **Anaconda** for data visualization and interactive apps. Each library has a specific role:

| Library | Role |
|---|---|
| **Panel** | Builds and serves the full web app — layout, widgets, tabs, ChatInterface |
| **HoloViews** | Chart abstraction and cross-filtering (`link_selections`, `hv.Points`, `hv.BoxWhisker`) |
| **hvPlot** | One-liner interactive charts directly from pandas DataFrames |
| **GeoViews** | Geographic plots — `gv.Points` on map tiles with coordinate projection |
| **Datashader** | Rasterizes tens of thousands of event points into smooth density layers |
| **Param** | Reactive parameters — powers the `DashboardState` that wires everything together |
| **Bokeh** | Rendering backend — turns all of the above into interactive browser charts |

The entire platform — map, charts, AI chat, cross-filtering — is 100% Python with the HoloViz stack.

---

## Free APIs Used

All data in this platform is sourced from **free, open APIs** — no paywalls, no paid subscriptions.

| Source | Data | API |
|---|---|---|
| **GDELT** | Global conflict and news events | Free, no key required |
| **NASA FIRMS** | Satellite fire hotspots | Free key at firms.modaps.eosdis.nasa.gov |
| **OpenSky Network** | Live flight tracking | Free, no key required |
| **NOAA** | Weather alerts and severe events | Free, no key required |
| **AIS Stream** | Maritime vessel tracking | Free key at aisstream.io |
| **USGS** | Earthquake / seismic events | Free, no key required |
| **Yahoo Finance** | Commodity and stock prices (OHLCV) | Free, no key required |
| **ExchangeRate.host** | Live FX rates vs USD | Free key at exchangerate.host |
| **Google News RSS** | Regional news feed | Free, no key required |
| **Gemini (Google AI)** | AI Explorer LLM | Free key at aistudio.google.com |

---

## Tabs

### 🗺 Risk Map
The main view. Every event on the map is a `gv.Points` layer rendered on a CartoDark tile source via **GeoViews**, with Cartopy handling the Google Mercator projection. Each data source (conflict, fire, earthquake, weather alert, flight, maritime) has its own shape and color encoding. When all sources are active, **Datashader** rasterizes the combined point cloud server-side so the browser receives a smooth density image instead of thousands of individual glyphs. The sidebar filters (source, region, severity) are powered by **Param** — a `DashboardState` class built on `param.Parameterized` that keeps all downstream components reactive.

### 📰 News & Events
Cross-filtering powered by `hv.link_selections` (**HoloViews**). Draw a bounding box on the map and the severity histogram (`hv.operation.histogram`), box plot (`hv.BoxWhisker`), and summary stats all update simultaneously — no manual callbacks. The news feed on the right reacts to the same selection: it parses the bounding coordinates from the `sel_expr`, identifies the dominant region in that box, and fetches live headlines from Google News RSS. Map selection → live regional news in one gesture.

### 📈 Global Prices
Commodity price history — Gold, Oil, Natural Gas, Wheat, Copper, Silver and more — fetched from Yahoo Finance and rendered with `df.hvplot.line()` (**hvPlot**). Date range picker updates the chart reactively via `pn.bind`. The entire tab is pure pandas + hvPlot + **Panel**.

### 💱 Currency FX
1-day percentage change of currencies vs USD, grouped by region (Middle East, Asia-Pacific, Europe, Americas, Geopolitical). Color-coded bars: green = currency weakened against dollar, red = currency strengthened. Built with `df.hvplot.barh()`. Region dropdown updates reactively via **Param**. Useful for tracking economic pressure on countries involved in conflicts in real time.

### 🤖 AI Explorer
A **Panel ChatInterface** backed by **Gemini** with a **DuckDB** in-memory database loaded at startup with all risk events, commodities, FX, and market data. When you ask a question, Gemini decides whether to run SQL against DuckDB, fetch live stock/crypto data from Yahoo Finance, or trigger a Google Search. It returns a JSON spec and the app renders an **hvPlot** chart or **GeoViews** map inline inside the chat bubble. Built on Panel's async generator callback pattern — loading indicator, answer text, and chart all appear progressively in the same message.

---

## Run Locally

```bash
git clone https://github.com/your-repo/holoviz-risk-platform
cd holoviz-risk-platform
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file at the project root:

```env
FIRMS_MAP_KEY=your_key
GEMINI_API_KEY=your_key
EXCHANGERATE_HOST_KEY=your_key
AISSTREAM_API_KEY=your_key
```

Run the app:

```bash
panel serve app/app.py --autoreload --show --port 5007
```

Open: http://localhost:5007/app

---

## Project Structure

```
holoviz-risk-platform/
├── app/
│   ├── app.py              # Entry point
│   ├── dashboard.py        # Main layout, header, tabs
│   ├── map_panel.py        # GeoViews risk map
│   ├── analysis_panel.py   # News & Events tab
│   ├── intel_panel.py      # Global Prices + Currency FX tabs
│   ├── ai_panel.py         # AI Explorer tab
│   ├── legend.py           # Source/severity color and shape mappings
│   ├── state.py            # DashboardState (Param-based reactive state)
│   └── data/
│       ├── events.py       # Multi-source event loader
│       └── context.py      # Commodities, FX, market data loaders
├── requirements.txt
└── README.md
```

---

## Tech Stack

```
pandas DataFrame
    → hvPlot / HoloViews   (charts and cross-filtering)
    → GeoViews             (geographic layers)
    → Datashader           (high-density point rasterization)
    → Panel                (layout, widgets, serving)
    → Bokeh                (browser rendering)
```

---

## Live Demo

Deployed on Hugging Face Spaces — try it at: [Crisis Intelligence Platform](https://huggingface.co/spaces/maya369/Crisis-Intelligence-Platform)
