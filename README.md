# Crisis Intelligence Platform

A real-time global risk intelligence dashboard built entirely with the **HoloViz ecosystem** — no JavaScript, no separate frontend, no paid data subscriptions. Just Python and free APIs.

**Motivation**: The Iran-Israel conflict, oil prices spiking, currencies crashing overnight — all this information exists but it's scattered across a dozen tools and paywalled platforms. I wanted to bring it all into one place, built entirely in Python with the HoloViz stack, using only free APIs. This is that platform — and a demonstration of how far HoloViz can go on a real-world, data-heavy application.

---

## Tabs

<table>
  <tr>
    <td valign="top" width="35%">
      <h3>🗺 Risk Map</h3>
      Live global event map built with <b>GeoViews</b> on CartoDark tiles. Sources — conflict, fire, earthquake, weather, flight, maritime — each encoded with unique shapes and colors. <b>Datashader</b> rasterizes high-density point clouds server-side. Sidebar filters powered by <b>Param</b>.
    </td>
    <td valign="top" width="65%">
      <img width="100%" alt="Risk Map" src="https://github.com/user-attachments/assets/4cb55ed6-0723-4648-86b8-01a054f70863" />
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>📰 News &amp; Events</h3>
      Cross-filtering via <code>hv.link_selections</code> (<b>HoloViews</b>). Draw a box on the map → severity histogram, box plot, and stats all update instantly. News feed fetches live Google News RSS headlines for the selected region.
    </td>
    <td valign="top">
      <img width="100%" alt="News & Events" src="https://github.com/user-attachments/assets/9d0f7cb1-bed9-44d8-87b0-03749e875dfd" />
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>📈 Global Prices</h3>
      Commodity price history (Gold, Oil, Gas, Wheat, Copper, Silver) from Yahoo Finance rendered with <b>hvPlot</b>. Date range picker updates charts reactively via <code>pn.bind</code>.
    </td>
    <td valign="top">
      <img width="100%" alt="Global Prices" src="https://github.com/user-attachments/assets/65889931-3263-4f73-8db2-bf5d45225d45" />
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>💱 Currency FX</h3>
      1-day % change of currencies vs USD by region. Green = weakened against dollar, red = strengthened. Built with <b>hvPlot</b> + <b>Param</b>. Useful for tracking real-time economic impact of conflicts.
    </td>
    <td valign="top">
      <img width="100%" alt="Currency FX" src="https://github.com/user-attachments/assets/a84bcc31-d2a9-4ce4-b727-8b44c0779a4b" />
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h3>🤖 AI Explorer</h3>
      <b>Panel ChatInterface</b> + <b>Gemini</b> + <b>DuckDB</b>. Ask in natural language — the AI runs SQL, fetches live stock data, or searches the web, then renders an <b>hvPlot</b> or <b>GeoViews</b> chart directly in the chat.
      <br><br>
      <i>"Give me a risk overview of Asia"</i><br>
      <i>"Plot gold vs oil price over time"</i><br>
      <i>"Show me Tesla stock price"</i><br>
      <i>"What's the latest news on the Iran-Israel conflict?"</i>
    </td>
    <td valign="top">
      <table>
        <tr>
          <td><img width="100%" alt="Risk overview of Asia" src="https://github.com/user-attachments/assets/d8014950-d5f8-44dc-a2e1-5bca100cbff4" /></td>
          <td><img width="100%" alt="Gold vs oil price" src="https://github.com/user-attachments/assets/9529bc91-e270-4b52-9c97-261fe81eff10" /></td>
        </tr>
        <tr>
          <td><img width="100%" alt="Tesla stock price" src="https://github.com/user-attachments/assets/7159f4ea-3df8-421e-a995-674b44a5d458" /></td>
          <td><img width="100%" alt="Iran-Israel conflict news" src="https://github.com/user-attachments/assets/3b5a89d3-15b5-4232-845e-90337eb3456d" /></td>
        </tr>
      </table>
    </td>
  </tr>
</table>


---

## HoloViz Ecosystem Usage

| Library | Role in this project |
| --- | --- |
| **Panel** | App shell, tabs, sidebar, ChatInterface, reactive bindings |
| **HoloViews** | `link_selections` cross-filtering, BoxWhisker, Histogram |
| **hvPlot** | Commodity line charts, FX bar charts, stock plots |
| **GeoViews** | Interactive world map on CartoDark tiles (Mercator projection) |
| **Datashader** | Server-side rasterization of high-density point clouds on the risk map |
| **Param** | `DashboardState` — central reactive state, `param.watch`, `pn.bind` |
| **Bokeh** | Rendering backend for all charts |

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

## Architecture

<table>
  <tr>
    <td colspan="5" align="center"><b>Panel Dashboard</b><br><sub>Reactive Callbacks &nbsp;·&nbsp; Dark Mode &nbsp;·&nbsp; Multi-Source &nbsp;·&nbsp; AI-Powered</sub></td>
  </tr>
  <tr>
    <td align="center"><b>🗺 Risk Map</b><br><sub>GeoViews · Datashader<br>CartoDark Tiles<br>Param Filters</sub></td>
    <td align="center"><b>📰 News & Events</b><br><sub>hv.link_selections<br>Histogram · BoxWhisker<br>Google News RSS</sub></td>
    <td align="center"><b>📈 Global Prices</b><br><sub>hvPlot · Yahoo Finance<br>Date Range Picker<br>pn.bind</sub></td>
    <td align="center"><b>💱 Currency FX</b><br><sub>hvPlot · ExchangeRate<br>Region Filter<br>Param</sub></td>
    <td align="center"><b>🤖 AI Explorer</b><br><sub>ChatInterface · Gemini<br>DuckDB · hvPlot<br>GeoViews</sub></td>
  </tr>
  <tr>
    <td colspan="5" align="center"><b>HoloViz Stack</b><br><sub>Panel &nbsp;·&nbsp; HoloViews &nbsp;·&nbsp; hvPlot &nbsp;·&nbsp; GeoViews &nbsp;·&nbsp; Datashader &nbsp;·&nbsp; Param &nbsp;·&nbsp; Bokeh</sub></td>
  </tr>
  <tr>
    <td align="center"><b>GeoViews</b><br><sub>gv.Points<br>CartoDark Tiles<br>Mercator Projection</sub></td>
    <td align="center"><b>HoloViews</b><br><sub>link_selections<br>BoxWhisker · Histogram<br>hv.Dataset</sub></td>
    <td align="center"><b>hvPlot</b><br><sub>hvplot.line()<br>hvplot.barh()<br>hvplot.scatter()</sub></td>
    <td align="center"><b>Datashader</b><br><sub>Point Rasterization<br>Density Heatmap<br>Server-side Render</sub></td>
    <td align="center"><b>Param</b><br><sub>DashboardState<br>param.Parameterized<br>param.watch · pn.bind</sub></td>
  </tr>
  <tr>
    <td colspan="5" align="center"><b>Data Layer</b><br><sub>pandas &nbsp;·&nbsp; numpy &nbsp;·&nbsp; DuckDB &nbsp;·&nbsp; Python</sub></td>
  </tr>
  <tr>
    <td align="center"><b>GDELT</b><br><sub>Conflict Events<br>Free · No Key</sub></td>
    <td align="center"><b>NASA FIRMS</b><br><sub>Fire Hotspots<br>Free Key</sub></td>
    <td align="center"><b>OpenSky · NOAA</b><br><sub>Flight Tracking<br>Weather Alerts · Free</sub></td>
    <td align="center"><b>Yahoo Finance</b><br><sub>Stocks · Commodities<br>OHLCV · Free</sub></td>
    <td align="center"><b>Google News RSS</b><br><sub>Live Headlines<br>Free · No Key</sub></td>
  </tr>
</table>

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
OTX_API_KEY=your_key

# Optional — enables EIA energy prices and FRED financial indicators
EIA_API_KEY=your_key
FRED_API_KEY=your_key
```

Run the app:

```bash
panel serve app/app.py --autoreload --show --port 5007
```

Open: http://localhost:5007/app

---

## Project Structure

```text
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

## Live Demo

Deployed on Hugging Face Spaces — try it at: [Crisis Intelligence Platform](https://huggingface.co/spaces/maya369/Crisis-Intelligence-Platform)
