from __future__ import annotations

import io
import json
import os
import queue
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
import panel as pn
import requests

from data.fallbacks import (
    gdelt_fallback, firms_fallback, opensky_fallback, noaa_fallback,
    maritime_fallback, rocket_fallback, seismic_fallback,
    cyber_fallback, radiation_fallback,
)
from settings import HTTP_TIMEOUT


def _safe_to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _safe_get_json(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _safe_get_text(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> str:
    r = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.text


def _region_from_latlon(lat: float, lon: float) -> str:
    if np.isnan(lat) or np.isnan(lon):
        return "Unknown"
    if -170 <= lon <= -30 and -60 <= lat <= 72:
        return "North America" if lat >= 15 else "South America"
    if -25 <= lon <= 45 and 35 <= lat <= 72:
        return "Europe"
    if -25 <= lon <= 55 and -35 <= lat <= 37:
        return "Africa"
    if 25 <= lon <= 75 and 12 <= lat <= 42:
        return "Middle East"
    if 45 <= lon <= 180 and -10 <= lat <= 75:
        return "Asia"
    return "Other"


# ── Existing source normaliser (FIRMS / OpenSky / NOAA) ───────────────────────
def _normalize_events(acled: pd.DataFrame, firms: pd.DataFrame, opensky: pd.DataFrame, noaa: pd.DataFrame) -> pd.DataFrame:
    def col(df: pd.DataFrame, name: str, default: Any) -> pd.Series:
        if name in df.columns:
            return df[name]
        return pd.Series([default] * len(df), index=df.index)

    firms_ts = _safe_to_datetime(col(firms, "acq_date", "") + " " + col(firms, "acq_time", "0000").astype(str).str.zfill(4))
    firms_lat = pd.to_numeric(col(firms, "latitude", np.nan), errors="coerce")
    firms_lon = pd.to_numeric(col(firms, "longitude", np.nan), errors="coerce")
    firms_region = [_region_from_latlon(lat, lon) for lat, lon in zip(firms_lat.fillna(np.nan), firms_lon.fillna(np.nan))]
    firms_events = pd.DataFrame(
        {
            "source": "FIRMS",
            "timestamp": firms_ts,
            "lat": firms_lat,
            "lon": firms_lon,
            "region": firms_region,
            "category": np.where(col(firms, "daynight", "D") == "N", "Thermal (night)", "Thermal (day)"),
            "severity": np.select(
                [
                    pd.to_numeric(col(firms, "frp", 0), errors="coerce") >= 15,
                    pd.to_numeric(col(firms, "frp", 0), errors="coerce") >= 10,
                    pd.to_numeric(col(firms, "frp", 0), errors="coerce") >= 6,
                ],
                [5, 4, 3],
                default=2,
            ),
            "title": "Thermal detection | FRP " + col(firms, "frp", "0").astype(str),
            "details": "confidence=" + col(firms, "confidence", "").astype(str),
            "evidence_url": "https://firms.modaps.eosdis.nasa.gov",
        }
    )

    os_lat = pd.to_numeric(col(opensky, "latitude", np.nan), errors="coerce")
    os_lon = pd.to_numeric(col(opensky, "longitude", np.nan), errors="coerce")
    os_region = [_region_from_latlon(lat, lon) for lat, lon in zip(os_lat.fillna(np.nan), os_lon.fillna(np.nan))]
    opensky_events = pd.DataFrame(
        {
            "source": "OpenSky",
            "timestamp": _safe_to_datetime(col(opensky, "time", pd.NaT)),
            "lat": os_lat,
            "lon": os_lon,
            "region": os_region,
            "category": np.where(col(opensky, "on_ground", False), "Aircraft (ground)", "Aircraft (airborne)"),
            "severity": np.select(
                [
                    pd.to_numeric(col(opensky, "velocity", 0), errors="coerce") >= 220,
                    pd.to_numeric(col(opensky, "velocity", 0), errors="coerce") >= 180,
                ],
                [3, 2],
                default=1,
            ),
            "title": "Flight " + col(opensky, "callsign", "").astype(str).str.strip() + " | " + col(opensky, "origin_country", "Unknown").astype(str),
            "details": "velocity=" + pd.to_numeric(col(opensky, "velocity", 0), errors="coerce").round(2).astype(str),
            "evidence_url": "https://opensky-network.org",
        }
    )

    noaa_lat = pd.to_numeric(col(noaa, "latitude", np.nan), errors="coerce")
    noaa_lon = pd.to_numeric(col(noaa, "longitude", np.nan), errors="coerce")
    noaa_sev_map = {"Extreme": 5, "Severe": 4, "Moderate": 3, "Minor": 2}
    noaa_events = pd.DataFrame(
        {
            "source": "NOAA",
            "timestamp": _safe_to_datetime(col(noaa, "sent", pd.NaT)),
            "lat": noaa_lat,
            "lon": noaa_lon,
            "region": "North America",
            "category": col(noaa, "event", "Weather Alert"),
            "severity": col(noaa, "severity", "Minor").map(noaa_sev_map).fillna(2).astype(int),
            "title": col(noaa, "headline", "NWS Alert"),
            "details": col(noaa, "areaDesc", ""),
            "evidence_url": "https://api.weather.gov/alerts/active",
        }
    )

    events = pd.concat([firms_events, opensky_events, noaa_events], ignore_index=True)
    events = events.dropna(subset=["timestamp", "lat", "lon"]).copy()
    events["severity"] = pd.to_numeric(events["severity"], errors="coerce").fillna(1).astype(int)
    return events


# ── GDELT ─────────────────────────────────────────────────────────────────────
_CAMEO_LABELS: dict[str, str] = {
    "13": "Threaten",        "14": "Protest",       "15": "Exhibit Force",
    "16": "Reduce Relations","17": "Coerce",        "18": "Assault",
    "19": "Fight",           "20": "Mass Violence",
}


def _gdelt_severity(goldstein: float) -> int:
    if goldstein <= -8: return 5
    if goldstein <= -5: return 4
    if goldstein <= -2: return 3
    if goldstein <   0: return 2
    return 1


def _load_gdelt_live() -> pd.DataFrame:
    """Fetch the latest GDELT 2.0 conflict events (updates every 15 min)."""
    txt = _safe_get_text("http://data.gdeltproject.org/gdeltv2/lastupdate.txt")
    export_url: str | None = None
    for line in txt.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3 and "export.CSV.zip" in parts[2]:
            export_url = parts[2]
            break
    if not export_url:
        raise RuntimeError("Could not parse GDELT lastupdate.txt")

    r = requests.get(export_url, timeout=30)
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            raw = pd.read_csv(f, sep="\t", header=None, low_memory=False)

    # GDELT 2.0 column indices (verified against live data):
    #   1=SQLDATE  6=Actor1Name  26=EventCode  28=EventRootCode
    #   29=QuadClass  30=GoldsteinScale  31=NumMentions
    #   52=ActionGeo_FullName  56=ActionGeo_Lat  57=ActionGeo_Long  60=SOURCEURL
    C_DATE, C_ACTOR, C_CODE, C_ROOT = 1, 6, 26, 28
    C_QUAD, C_GOLD, C_MENT = 29, 30, 31
    C_LOC, C_LAT, C_LON, C_URL = 52, 56, 57, 60

    raw = raw[raw[C_QUAD].isin([3, 4])].copy()

    lat = pd.to_numeric(raw[C_LAT], errors="coerce")
    lon = pd.to_numeric(raw[C_LON], errors="coerce")
    mask = lat.notna() & lon.notna() & (lat != 0) & (lon != 0)
    raw, lat, lon = raw[mask].copy(), lat[mask], lon[mask]

    # Deduplicate: keep highest-mention row per (date, event-code, location)
    raw["_lat"] = lat.values
    raw["_lon"] = lon.values
    raw = (raw.sort_values(C_MENT, ascending=False)
               .drop_duplicates(subset=[C_DATE, C_CODE, C_LAT, C_LON])
               .copy())
    lat = raw["_lat"]
    lon = raw["_lon"]
    raw = raw.drop(columns=["_lat", "_lon"])

    if raw.empty:
        return pd.DataFrame()

    timestamp = pd.to_datetime(
        raw[C_DATE].astype(str), format="%Y%m%d", errors="coerce"
    ).dt.tz_localize("UTC")

    region   = [_region_from_latlon(la, lo) for la, lo in zip(lat.fillna(np.nan), lon.fillna(np.nan))]
    goldstein = pd.to_numeric(raw[C_GOLD], errors="coerce").fillna(0)
    severity  = goldstein.map(_gdelt_severity)
    category  = raw[C_ROOT].astype(str).map(_CAMEO_LABELS).fillna("Conflict")
    actor     = raw[C_ACTOR].fillna("Unknown").astype(str).str.strip()
    location  = raw[C_LOC].fillna("Unknown").astype(str)
    title     = actor + " | " + location
    details   = ("CAMEO:" + raw[C_CODE].astype(str)
                 + "  mentions=" + pd.to_numeric(raw[C_MENT], errors="coerce").fillna(1).astype(int).astype(str))
    src_url   = raw[C_URL].fillna("https://www.gdeltproject.org").astype(str)

    df = pd.DataFrame({
        "source":       "GDELT",
        "timestamp":    timestamp.values,
        "lat":          lat.values,
        "lon":          lon.values,
        "region":       region,
        "category":     category.values,
        "severity":     severity.astype(int).values,
        "title":        title.values,
        "details":      details.values,
        "evidence_url": src_url.values,
    }).dropna(subset=["timestamp", "lat", "lon"]).copy()

    # Jitter: GDELT geocodes to city centroids so many events share exact
    # coordinates. A small offset (~0.3°, ≈33 km) spreads them so every
    # point is individually hoverable without misleading the viewer.
    rng = np.random.default_rng()
    df["lat"] = df["lat"] + rng.uniform(-0.3, 0.3, size=len(df))
    df["lon"] = df["lon"] + rng.uniform(-0.3, 0.3, size=len(df))
    return df


# ── FIRMS / OpenSky / NOAA live loaders ──────────────────────────────────────
def _load_firms_live() -> pd.DataFrame:
    key = os.getenv("FIRMS_MAP_KEY")
    if not key:
        raise RuntimeError("FIRMS key not found")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/-180,-90,180,90/1"
    txt = _safe_get_text(url)
    return pd.read_csv(StringIO(txt))


def _load_opensky_live() -> pd.DataFrame:
    data = _safe_get_json("https://opensky-network.org/api/states/all")
    states = data.get("states", [])[:700]
    rows = []
    for s in states:
        rows.append(
            {
                "time": pd.to_datetime(s[4], unit="s", utc=True) if s[4] is not None else pd.NaT,
                "callsign": (s[1] or "").strip() if len(s) > 1 else "",
                "origin_country": s[2] if len(s) > 2 else "Unknown",
                "longitude": s[5] if len(s) > 5 else np.nan,
                "latitude": s[6] if len(s) > 6 else np.nan,
                "velocity": s[9] if len(s) > 9 else 0,
                "on_ground": s[8] if len(s) > 8 else False,
            }
        )
    return pd.DataFrame(rows)


def _polygon_centroid(coords: Any) -> tuple[float, float]:
    try:
        ring = coords[0]
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        return float(np.mean(lats)), float(np.mean(lons))
    except Exception:
        return np.nan, np.nan


def _load_noaa_live() -> pd.DataFrame:
    data = _safe_get_json(
        "https://api.weather.gov/alerts/active",
        headers={"Accept": "application/geo+json", "User-Agent": "holointel-mvp"},
    )
    feats = data.get("features", [])[:120]
    rows = []
    for f in feats:
        p = f.get("properties", {})
        lat, lon = np.nan, np.nan
        geom = f.get("geometry")
        if geom and geom.get("type") == "Polygon":
            lat, lon = _polygon_centroid(geom.get("coordinates", []))
        rows.append(
            {
                "sent": p.get("sent"),
                "event": p.get("event"),
                "severity": p.get("severity"),
                "urgency": p.get("urgency"),
                "areaDesc": p.get("areaDesc"),
                "latitude": lat,
                "longitude": lon,
                "headline": p.get("headline"),
            }
        )
    return pd.DataFrame(rows)


# ── AIS Maritime ──────────────────────────────────────────────────────────────
def _load_ais_live() -> pd.DataFrame:
    """Fetch AIS vessel positions via AISStream WebSocket.
    Monitors Strait of Hormuz, Red Sea, and Persian Gulf for ~5 seconds.
    """
    try:
        import websocket  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError("websocket-client not installed")

    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("AISSTREAM_API_KEY not set")

    collected: list[dict] = []
    stop_event = threading.Event()

    subscribe_msg = json.dumps({
        "APIKey": api_key,
        "BoundingBoxes": [
            [[21.0, 55.0], [27.0, 60.0]],   # Strait of Hormuz
            [[12.0, 32.0], [30.0, 43.0]],   # Red Sea
            [[22.0, 47.0], [30.0, 57.0]],   # Persian Gulf
        ],
        "FilterMessageTypes": ["PositionReport"],
    })

    def on_open(ws: Any) -> None:
        if stop_event.is_set():
            return
        try:
            ws.send(subscribe_msg)
        except Exception:
            stop_event.set()

    def on_message(ws: Any, message: str) -> None:
        if stop_event.is_set():
            return          # let the timer close it; don't call ws.close() here
        try:
            data = json.loads(message)
            if data.get("MessageType") == "PositionReport":
                meta = data.get("MetaData", {})
                lat = meta.get("latitude")
                lon = meta.get("longitude")
                if lat is not None and lon is not None:
                    pos = data.get("Message", {}).get("PositionReport", {})
                    collected.append({
                        "mmsi":  str(meta.get("MMSI", "")).strip(),
                        "name":  meta.get("ShipName", "").strip() or str(meta.get("MMSI", "Unknown")),
                        "lat":   float(lat),
                        "lon":   float(lon),
                        "time":  meta.get("time_utc", ""),
                        "speed": float(pos.get("SpeedOverGround", 0) or 0),
                    })
        except Exception:
            pass

    def on_error(ws: Any, error: Any) -> None:
        stop_event.set()

    ws_app = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
    )
    thread = threading.Thread(target=ws_app.run_forever, daemon=True)
    thread.start()

    # Collect for up to 5 seconds then close gracefully
    time.sleep(5)
    stop_event.set()
    try:
        ws_app.close()
    except Exception:
        pass
    thread.join(timeout=2.0)

    if not collected:
        return pd.DataFrame()

    df = pd.DataFrame(collected).drop_duplicates(subset=["mmsi"])
    speed = pd.to_numeric(df["speed"], errors="coerce").fillna(0)
    severity = np.select([speed >= 20, speed >= 12], [3, 2], default=1)
    now = pd.Timestamp.now(tz="UTC")
    region = [_region_from_latlon(r.lat, r.lon) for r in df.itertuples()]

    return pd.DataFrame({
        "source":       "Maritime",
        "timestamp":    now,
        "lat":          df["lat"].values,
        "lon":          df["lon"].values,
        "region":       region,
        "category":     "Vessel",
        "severity":     severity,
        "title":        "Vessel " + df["name"].values,
        "details":      "MMSI=" + df["mmsi"].values + " speed=" + speed.round(1).astype(str).values + "kn",
        "evidence_url": "https://aisstream.io",
    })


# ── Rocket Alerts (oref.org.il) ───────────────────────────────────────────────
# Hebrew area names → (lat, lon)
_OREF_COORDS: dict[str, tuple[float, float]] = {
    "תל אביב": (32.08, 34.78),   "ירושלים": (31.78, 35.22),
    "חיפה":    (32.79, 34.99),   "באר שבע": (31.25, 34.79),
    "אשדוד":   (31.80, 34.65),   "אשקלון":  (31.67, 34.57),
    "נתניה":   (32.33, 34.85),   "ראשון לציון": (31.97, 34.80),
    "פתח תקווה":(32.09, 34.88), "הרצליה":  (32.16, 34.84),
    "שדרות":   (31.52, 34.60),   "כרמיאל":  (32.92, 35.30),
    "עפולה":   (32.60, 35.29),   "טבריה":   (32.79, 35.53),
    "אילת":    (29.56, 34.95),   "מטולה":   (33.27, 35.57),
    "קריית שמונה": (33.21, 35.57), "עכו":   (32.92, 35.08),
    "לוד":     (31.95, 34.90),   "רמלה":    (31.93, 34.87),
    "רחובות":  (31.90, 34.81),   "נהריה":   (33.00, 35.10),
    "צפת":     (32.96, 35.50),   "עיר גן":  (32.05, 34.85),
    "גבעתיים": (32.07, 34.81),   "כפר סבא": (32.18, 34.91),
}
_ISRAEL_CENTER = (31.5, 35.0)


def _load_rocket_live() -> pd.DataFrame:
    """Fetch current and recent rocket alerts from Israel Home Front Command."""
    headers = {
        "Referer": "https://www.oref.org.il/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    }
    rows: list[dict] = []
    now = pd.Timestamp.now(tz="UTC")

    # Active alerts
    try:
        r = requests.get("https://www.oref.org.il/WarningMessages/alert/alerts.json",
                         headers=headers, timeout=HTTP_TIMEOUT)
        if r.ok and r.text.strip() and r.text.strip() != "null":
            data = r.json()
            areas = data.get("data", []) if isinstance(data, dict) else []
            for area in areas:
                lat, lon = _OREF_COORDS.get(area.strip(), _ISRAEL_CENTER)
                rows.append({"area": area, "lat": lat, "lon": lon,
                             "timestamp": now, "severity": 5, "category": "Rocket Alert"})
    except Exception:
        pass

    # Recent history (last 24 h)
    try:
        r = requests.get("https://www.oref.org.il/WarningMessages/History/AlertsHistory.json",
                         headers=headers, timeout=HTTP_TIMEOUT)
        if r.ok:
            history = r.json() if isinstance(r.json(), list) else []
            for item in history[:30]:
                area = item.get("data", item.get("area", ""))
                ts_str = item.get("alertDate", item.get("date", ""))
                try:
                    ts = pd.Timestamp(ts_str, tz="UTC")
                except Exception:
                    ts = now
                lat, lon = _OREF_COORDS.get(str(area).strip(), _ISRAEL_CENTER)
                rows.append({"area": area, "lat": lat, "lon": lon,
                             "timestamp": ts, "severity": 4, "category": "Rocket Alert (History)"})
    except Exception:
        pass

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return pd.DataFrame({
        "source":       "Rocket",
        "timestamp":    df["timestamp"],
        "lat":          df["lat"],
        "lon":          df["lon"],
        "region":       "Middle East",
        "category":     df["category"],
        "severity":     df["severity"],
        "title":        "Rocket Alert | " + df["area"].astype(str),
        "details":      "oref.org.il",
        "evidence_url": "https://www.oref.org.il",
    })


# ── USGS Seismic ──────────────────────────────────────────────────────────────
def _seismic_severity(mag: float) -> int:
    if mag >= 7.0: return 5
    if mag >= 6.0: return 4
    if mag >= 5.0: return 3
    if mag >= 4.0: return 2
    return 1


def _load_seismic_live() -> pd.DataFrame:
    """Fetch M≥2.5 earthquakes from USGS (past 7 days)."""
    data = _safe_get_json(
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson"
    )
    rows: list[dict] = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        coords = (feat.get("geometry") or {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        depth = float(coords[2]) if len(coords) > 2 else 0.0
        mag = props.get("mag")
        if mag is None:
            continue
        mag = float(mag)
        if mag < 2.5:
            continue
        place = props.get("place", "Unknown location")
        ts_ms = props.get("time")
        ts = pd.Timestamp(ts_ms, unit="ms", tz="UTC") if ts_ms else pd.Timestamp.now(tz="UTC")
        rows.append({
            "source":       "Seismic",
            "timestamp":    ts,
            "lat":          float(lat),
            "lon":          float(lon),
            "region":       _region_from_latlon(float(lat), float(lon)),
            "category":     f"M{mag:.1f} Earthquake",
            "severity":     _seismic_severity(mag),
            "title":        f"M{mag:.1f} — {place}",
            "details":      f"mag={mag:.1f} depth={depth:.0f}km",
            "evidence_url": props.get("url", "https://earthquake.usgs.gov"),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Cyber Threats (AlienVault OTX) ────────────────────────────────────────────
_COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "Iran":          (32.0,  53.0),  "Israel":        (31.5,  35.0),
    "Ukraine":       (49.0,  32.0),  "Russia":        (55.0,  37.0),
    "United States": (38.0, -97.0),  "China":         (35.0, 105.0),
    "Lebanon":       (33.9,  35.5),  "Syria":         (34.8,  38.9),
    "Iraq":          (33.3,  44.4),  "Saudi Arabia":  (24.7,  46.7),
    "United Kingdom":(51.5,  -0.1),  "Germany":       (51.2,  10.5),
    "France":        (46.2,   2.2),  "United Arab Emirates": (25.2, 55.3),
    "Pakistan":      (30.4,  69.3),  "India":         (20.6,  78.9),
    "Turkey":        (38.9,  35.2),  "Egypt":         (26.8,  30.8),
    "Yemen":         (15.6,  48.5),  "North Korea":   (40.3, 127.5),
}


def _load_cyber_live() -> pd.DataFrame:
    """Fetch recent cyber threat pulses from AlienVault OTX."""
    api_key = os.getenv("OTX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OTX_API_KEY not set")

    # Search for pulses related to conflict-zone cyber operations
    tags = ["iran", "israel", "hamas", "hezbollah", "ukraine", "critical-infrastructure",
            "ics", "scada", "nuclear", "energy-sector", "ddos", "apt"]
    all_pulses: list[dict] = []

    for tag in tags[:5]:   # cap API calls
        try:
            data = _safe_get_json(
                f"https://otx.alienvault.com/api/v1/pulses/search",
                params={"q": tag, "limit": 10, "page": 1},
                headers={"X-OTX-API-KEY": api_key},
            )
            all_pulses.extend(data.get("results", []))
        except Exception:
            continue

    if not all_pulses:
        return pd.DataFrame()

    seen: set[str] = set()
    rows: list[dict] = []
    for pulse in all_pulses:
        pid = pulse.get("id", "")
        if pid in seen:
            continue
        seen.add(pid)

        name = pulse.get("name", "Unknown Threat")
        tags_list = pulse.get("tags", [])
        countries = pulse.get("targeted_countries", [])
        modified = pulse.get("modified", "")
        tlp = pulse.get("tlp", "white")

        try:
            ts = pd.Timestamp(modified, tz="UTC")
        except Exception:
            ts = pd.Timestamp.now(tz="UTC")

        # Severity from TLP
        sev = {"red": 5, "amber": 4, "green": 3, "white": 2}.get(tlp.lower(), 2)

        # Map pulse to geographic coordinates via targeted_countries
        geo_countries = countries if countries else ["Unknown"]
        for country in geo_countries[:2]:   # at most 2 points per pulse
            lat, lon = _COUNTRY_COORDS.get(str(country).strip(), (None, None))
            if lat is None:
                continue
            rows.append({
                "source":       "Cyber",
                "timestamp":    ts,
                "lat":          lat + np.random.uniform(-1.5, 1.5),
                "lon":          lon + np.random.uniform(-1.5, 1.5),
                "region":       _region_from_latlon(lat, lon),
                "category":     "Cyber Threat",
                "severity":     sev,
                "title":        name[:80],
                "details":      "tags=" + ",".join(str(t) for t in tags_list[:5]),
                "evidence_url": f"https://otx.alienvault.com/pulse/{pid}",
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Safecast Radiation ────────────────────────────────────────────────────────
_NUCLEAR_SITES: dict[str, tuple[float, float]] = {
    "Bushehr (Iran)":      (28.83, 50.89),
    "Fordow (Iran)":       (34.89, 50.47),
    "Natanz (Iran)":       (33.72, 51.73),
    "Dimona (Israel)":     (30.97, 35.15),
    "Zaporizhzhia (UKR)":  (47.51, 34.58),
    "Fukushima (JPN)":     (37.42, 141.03),
}


def _load_radiation_live() -> pd.DataFrame:
    """Query Safecast API near each nuclear facility."""
    rows: list[dict] = []
    for site, (lat, lon) in _NUCLEAR_SITES.items():
        try:
            data = _safe_get_json(
                "https://api.safecast.org/measurements.json",
                params={"latitude": lat, "longitude": lon,
                        "distance": "50000", "limit": "5",
                        "unit": "cpm", "order": "captured_at desc"},
            )
            if not isinstance(data, list) or not data:
                continue
            for rec in data[:3]:
                cpm = rec.get("value")
                captured = rec.get("captured_at", "")
                if cpm is None:
                    continue
                cpm = float(cpm)
                try:
                    ts = pd.Timestamp(captured, tz="UTC")
                except Exception:
                    ts = pd.Timestamp.now(tz="UTC")
                rows.append({
                    "source":       "Radiation",
                    "timestamp":    ts,
                    "lat":          float(rec.get("latitude", lat)),
                    "lon":          float(rec.get("longitude", lon)),
                    "region":       _region_from_latlon(lat, lon),
                    "category":     "Radiation Reading",
                    "severity":     (5 if cpm > 100 else 4 if cpm > 50 else
                                     3 if cpm > 30 else 2 if cpm > 20 else 1),
                    "title":        f"Radiation | {site}",
                    "details":      f"cpm={cpm:.1f}",
                    "evidence_url": "https://api.safecast.org",
                })
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Legacy ACLED helpers (kept for reference) ─────────────────────────────────
def _acled_auth_headers() -> dict[str, str]:
    acled_cookie = os.getenv("ACLED_COOKIE", "").strip()
    if acled_cookie:
        return {"Cookie": acled_cookie, "User-Agent": "holointel/1.0"}
    email    = os.getenv("ACLED_EMAIL", "").strip()
    password = os.getenv("ACLED_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError("ACLED credentials not found")
    errors: list[str] = []
    try:
        r = requests.post(
            "https://acleddata.com/oauth/token",
            data={"username": email, "password": password,
                  "grant_type": "password", "client_id": "acled"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=HTTP_TIMEOUT,
        )
        token = r.json().get("access_token") if r.ok else None
        if token:
            return {"Authorization": f"Bearer {token}", "User-Agent": "holointel/1.0"}
        errors.append(f"OAuth2 HTTP {r.status_code}: {r.text[:120]}")
    except Exception as exc:
        errors.append(f"OAuth2 error: {exc}")
    raise RuntimeError(f"All ACLED auth methods failed: {'; '.join(errors)}")


# ── Main loader ───────────────────────────────────────────────────────────────
def _try_load(loader_fn, fallback_fn, label: str) -> pd.DataFrame:
    """Run a loader, fall back to static data on any error, warn to stderr."""
    try:
        df = loader_fn()
        if not df.empty:
            return df
    except Exception:
        pass
    return fallback_fn()


@pn.cache(ttl=900)
def load_events() -> pd.DataFrame:
    _TASKS = [
        ("GDELT",     _load_gdelt_live,     gdelt_fallback),
        ("FIRMS",     _load_firms_live,     firms_fallback),
        ("OpenSky",   _load_opensky_live,   opensky_fallback),
        ("NOAA",      _load_noaa_live,      noaa_fallback),
        ("Maritime",  _load_ais_live,       maritime_fallback),
        ("Rocket",    _load_rocket_live,    rocket_fallback),
        ("Seismic",   _load_seismic_live,   seismic_fallback),
        ("Cyber",     _load_cyber_live,     cyber_fallback),
        ("Radiation", _load_radiation_live, radiation_fallback),
    ]

    results: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=len(_TASKS)) as executor:
        future_to_label = {
            executor.submit(_try_load, loader, fallback, label): label
            for label, loader, fallback in _TASKS
        }
        for future in as_completed(future_to_label):
            results[future_to_label[future]] = future.result()

    gdelt     = results["GDELT"]
    firms     = results["FIRMS"]
    opensky   = results["OpenSky"]
    noaa      = results["NOAA"]
    maritime  = results["Maritime"]
    rocket    = results["Rocket"]
    seismic   = results["Seismic"]
    cyber     = results["Cyber"]
    radiation = results["Radiation"]

    # FIRMS / OpenSky / NOAA go through the raw normaliser
    normalized = _normalize_events(
        pd.DataFrame(), firms, opensky, noaa,
    )

    events = pd.concat(
        [df for df in [gdelt, normalized, maritime, rocket, seismic, cyber, radiation]
         if not df.empty],
        ignore_index=True,
    )
    events = events.dropna(subset=["timestamp", "lat", "lon"]).copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="coerce")
    events["severity"] = pd.to_numeric(events["severity"], errors="coerce").fillna(1).astype(int)
    events = events.drop_duplicates(
        subset=["source", "lon", "lat", "timestamp"], keep="first"
    ).reset_index(drop=True)
    return events
