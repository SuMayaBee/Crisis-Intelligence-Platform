"""
Synthetic fallback data — returned when live API calls fail or return empty.

Each function returns a DataFrame whose columns match exactly what
_normalize_events / load_macro expect from the raw API responses,
so callers need no special-casing.
"""
from __future__ import annotations

import pandas as pd

def _ago(days: int) -> str:
    """ISO date string for N days before now (UTC), used to keep fallback
    events always inside the 720-hour lookback window."""
    ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    return ts.strftime("%Y-%m-%d")


def _ago_iso(days: int) -> str:
    """Full ISO-8601 timestamp N days before now, for NOAA 'sent' field."""
    ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ago_dt(days: int) -> str:
    """Datetime string N days before now, for OpenSky 'time' field."""
    ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def gdelt_fallback() -> pd.DataFrame:
    """Pre-normalised GDELT-style conflict fallback rows."""
    rows = [
        (_ago( 1),  15.55,  32.53, "Africa",      "Fight",         5, "Armed group | Khartoum, Sudan",        "CAMEO:190 mentions=12"),
        (_ago( 2),  31.52,  34.47, "Middle East",  "Assault",       4, "Military | Gaza Strip",                "CAMEO:180 mentions=25"),
        (_ago( 3),  48.38,  35.29, "Europe",       "Fight",         3, "Forces | Donetsk, Ukraine",            "CAMEO:190 mentions=8"),
        (_ago( 4),  21.09,  96.88, "Asia",         "Coerce",        3, "Military | Mandalay, Myanmar",         "CAMEO:170 mentions=5"),
        (_ago( 5),  -4.32,  15.32, "Africa",       "Mass Violence", 4, "Armed group | Eastern DRC",            "CAMEO:200 mentions=15"),
        (_ago( 6),  33.34,  44.40, "Middle East",  "Protest",       2, "Civilians | Baghdad, Iraq",            "CAMEO:140 mentions=6"),
        (_ago( 7),  14.10,  -0.36, "Africa",       "Assault",       4, "Jihadist | Burkina Faso",              "CAMEO:180 mentions=10"),
        (_ago( 8),  13.45,   2.10, "Africa",       "Fight",         3, "Military | Niger",                     "CAMEO:190 mentions=7"),
        (_ago( 9),  47.00,  37.50, "Europe",       "Fight",         3, "Forces | Eastern Ukraine",             "CAMEO:190 mentions=9"),
        (_ago(10),  16.90,  33.10, "Africa",       "Mass Violence", 5, "Armed group | Sudan",                  "CAMEO:200 mentions=20"),
    ]
    return pd.DataFrame([
        {
            "source":       "GDELT",
            "timestamp":    pd.Timestamp(f"{date} 00:00:00", tz="UTC"),
            "lat": lat, "lon": lon,
            "region":       region,
            "category":     category,
            "severity":     sev,
            "title":        title,
            "details":      details,
            "evidence_url": "https://www.gdeltproject.org",
        }
        for date, lat, lon, region, category, sev, title, details in rows
    ])


def firms_fallback() -> pd.DataFrame:
    return pd.DataFrame([
        {"acq_date": _ago( 1), "acq_time": "1430", "latitude":  -9.20, "longitude": -62.80, "daynight": "D", "frp": 18.5, "confidence": 85},
        {"acq_date": _ago( 2), "acq_time": "0600", "latitude":  -7.10, "longitude": -63.40, "daynight": "N", "frp": 22.1, "confidence": 90},
        {"acq_date": _ago( 4), "acq_time": "1200", "latitude": -32.50, "longitude": 148.20, "daynight": "D", "frp": 14.0, "confidence": 78},
        {"acq_date": _ago( 6), "acq_time": "0900", "latitude":  60.80, "longitude": 107.50, "daynight": "D", "frp": 11.3, "confidence": 72},
        {"acq_date": _ago( 8), "acq_time": "1800", "latitude":  38.40, "longitude":-121.50, "daynight": "N", "frp": 16.8, "confidence": 88},
        {"acq_date": _ago(10), "acq_time": "1100", "latitude":  -1.60, "longitude": 112.50, "daynight": "D", "frp": 19.0, "confidence": 83},
        {"acq_date": _ago(12), "acq_time": "1500", "latitude": -14.80, "longitude":  30.20, "daynight": "D", "frp":  8.4, "confidence": 65},
        {"acq_date": _ago(14), "acq_time": "0730", "latitude":  -6.30, "longitude": -72.10, "daynight": "D", "frp": 25.0, "confidence": 92},
    ])


def opensky_fallback() -> pd.DataFrame:
    return pd.DataFrame([
        {"latitude":  51.47, "longitude":  -0.46, "time": _ago_dt( 1), "on_ground": False, "velocity": 245.0, "callsign": "BAW123 ", "origin_country": "United Kingdom"},
        {"latitude":  40.63, "longitude": -73.78, "time": _ago_dt( 2), "on_ground": False, "velocity": 230.0, "callsign": "AAL456 ", "origin_country": "United States"},
        {"latitude":  48.35, "longitude":  11.79, "time": _ago_dt( 3), "on_ground": False, "velocity": 210.0, "callsign": "DLH789 ", "origin_country": "Germany"},
        {"latitude":  35.55, "longitude": 139.78, "time": _ago_dt( 5), "on_ground": False, "velocity": 260.0, "callsign": "JAL001 ", "origin_country": "Japan"},
        {"latitude":  25.25, "longitude":  55.36, "time": _ago_dt( 7), "on_ground": False, "velocity": 235.0, "callsign": "UAE321 ", "origin_country": "United Arab Emirates"},
        {"latitude": -33.94, "longitude": 151.18, "time": _ago_dt( 9), "on_ground": False, "velocity": 220.0, "callsign": "QFA055 ", "origin_country": "Australia"},
        {"latitude":  19.43, "longitude": -99.07, "time": _ago_dt(11), "on_ground": True,  "velocity":   0.0, "callsign": "AMX800 ", "origin_country": "Mexico"},
        {"latitude":  55.97, "longitude":  37.41, "time": _ago_dt(13), "on_ground": False, "velocity": 195.0, "callsign": "AFL249 ", "origin_country": "Russia"},
    ])


def noaa_fallback() -> pd.DataFrame:
    return pd.DataFrame([
        {"latitude": 35.50, "longitude": -97.50, "sent": _ago_iso( 1), "severity": "Severe",   "event": "Tornado Warning",     "headline": "Tornado Warning in effect for central Oklahoma", "areaDesc": "Oklahoma County, OK"},
        {"latitude": 25.80, "longitude": -80.20, "sent": _ago_iso( 3), "severity": "Extreme",  "event": "Hurricane Warning",   "headline": "Hurricane Warning for South Florida coast",      "areaDesc": "Miami-Dade County, FL"},
        {"latitude": 44.00, "longitude": -88.00, "sent": _ago_iso( 5), "severity": "Moderate", "event": "Winter Storm Warning", "headline": "Heavy snow expected across Wisconsin",           "areaDesc": "Winnebago County, WI"},
        {"latitude": 39.75, "longitude":-104.87, "sent": _ago_iso( 8), "severity": "Severe",   "event": "Blizzard Warning",    "headline": "Blizzard conditions expected in Denver metro",   "areaDesc": "Denver County, CO"},
        {"latitude": 30.30, "longitude": -89.00, "sent": _ago_iso(10), "severity": "Moderate", "event": "Flash Flood Watch",   "headline": "Flash Flood Watch for coastal Mississippi",      "areaDesc": "Harrison County, MS"},
    ])


def maritime_fallback() -> pd.DataFrame:
    """AIS vessel positions in strategic chokepoints."""
    rows = [
        (25.40,  56.60, "Middle East", "Tanker",  2, "DALEEL",    "MMSI=311000123 speed=12.3kn", "Strait of Hormuz"),
        (24.55,  57.10, "Middle East", "Cargo",   1, "GULF STAR", "MMSI=372001456 speed=8.1kn",  "Strait of Hormuz"),
        (15.20,  41.50, "Middle East", "Tanker",  3, "RED QUEEN", "MMSI=636000789 speed=14.0kn", "Bab-el-Mandeb"),
        (20.10,  38.80, "Middle East", "Warship", 4, "HOUTHI Z1", "MMSI=476000001 speed=22.0kn", "Red Sea"),
        (26.70,  49.90, "Middle East", "LNG",     2, "AL KHAFJI", "MMSI=403000222 speed=9.5kn",  "Persian Gulf"),
        (23.90,  57.30, "Middle East", "Cargo",   1, "MALIHA",    "MMSI=620001003 speed=6.2kn",  "Gulf of Oman"),
        (13.40,  42.70, "Middle East", "Tanker",  3, "NIAMA",     "MMSI=677000567 speed=11.0kn", "Red Sea South"),
        (24.20,  56.40, "Middle East", "Cargo",   2, "ATLAS MAX", "MMSI=248000899 speed=7.8kn",  "Strait of Hormuz"),
    ]
    return pd.DataFrame([
        {
            "source": "Maritime", "timestamp": pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=i * 7),
            "lat": lat, "lon": lon, "region": region,
            "category": cat, "severity": sev,
            "title": f"Vessel {name}", "details": details,
            "evidence_url": "https://aisstream.io",
        }
        for i, (lat, lon, region, cat, sev, name, details, _) in enumerate(rows)
    ])


def rocket_fallback() -> pd.DataFrame:
    """Israel Home Front Command rocket/missile alert fallback."""
    # Israeli city coordinates for alert areas
    alerts = [
        (_ago(0),  31.52, 34.60, "Asia", "Rocket",  5, "Alert: Sderot",           "oref area=שדרות"),
        (_ago(0),  31.67, 34.57, "Asia", "Rocket",  5, "Alert: Ashkelon",         "oref area=אשקלון"),
        (_ago(1),  32.08, 34.78, "Asia", "Rocket",  5, "Alert: Tel Aviv",         "oref area=תל אביב"),
        (_ago(1),  31.80, 34.65, "Asia", "Rocket",  4, "Alert: Ashdod",           "oref area=אשדוד"),
        (_ago(2),  33.21, 35.57, "Asia", "Rocket",  4, "Alert: Kiryat Shmona",    "oref area=קריית שמונה"),
        (_ago(3),  32.92, 35.08, "Asia", "Rocket",  3, "Alert: Acre",             "oref area=עכו"),
    ]
    return pd.DataFrame([
        {
            "source": "Rocket", "timestamp": pd.Timestamp(f"{date} 06:00:00", tz="UTC"),
            "lat": lat, "lon": lon, "region": region,
            "category": cat, "severity": sev, "title": title, "details": details,
            "evidence_url": "https://www.oref.org.il",
        }
        for date, lat, lon, region, cat, sev, title, details in alerts
    ])


def seismic_fallback() -> pd.DataFrame:
    """USGS earthquake fallback (M ≥ 2.5)."""
    quakes = [
        (_ago(0),  37.42, 141.03, "Asia",          5.8, 10.0,  "M5.8 Near Fukushima, Japan"),
        (_ago(1),  35.68,  36.10, "Middle East",   4.2, 15.0,  "M4.2 Northern Syria"),
        (_ago(1),  38.11,  46.35, "Middle East",   3.9, 8.0,   "M3.9 Northwest Iran"),
        (_ago(2),  36.52,  71.50, "Asia",          5.1, 220.0, "M5.1 Afghanistan-Tajikistan border"),
        (_ago(3),  32.00,  35.30, "Middle East",   3.1, 12.0,  "M3.1 Dead Sea region"),
        (_ago(4),  47.51,  34.58, "Europe",        3.5, 5.0,   "M3.5 Near Zaporizhzhia"),
        (_ago(5),  33.72,  51.73, "Middle East",   4.0, 18.0,  "M4.0 Natanz, Iran"),
        (_ago(7),  28.83,  50.89, "Middle East",   3.3, 25.0,  "M3.3 Bushehr coastal, Iran"),
    ]
    return pd.DataFrame([
        {
            "source": "Seismic",
            "timestamp": pd.Timestamp(f"{date} 12:00:00", tz="UTC"),
            "lat": lat, "lon": lon,
            "region": region,
            "category": f"M{mag:.1f} Earthquake",
            "severity": (5 if mag >= 7 else 4 if mag >= 6 else 3 if mag >= 5 else 2 if mag >= 4 else 1),
            "title": title,
            "details": f"mag={mag:.1f} depth={depth:.0f}km",
            "evidence_url": "https://earthquake.usgs.gov",
        }
        for date, lat, lon, region, mag, depth, title in quakes
    ])


def cyber_fallback() -> pd.DataFrame:
    """AlienVault OTX cyber threat fallback."""
    incidents = [
        (_ago(0),  32.0,  53.0, "Middle East", "ICS/SCADA Attack",   5, "Iran Energy Grid Probe",            "tags=iran,ics,critical-infrastructure"),
        (_ago(1),  31.5,  35.0, "Middle East", "Phishing Campaign",  4, "Israeli Gov Spear-phishing",        "tags=israel,apt,phishing"),
        (_ago(1),  49.0,  32.0, "Europe",      "Malware",            5, "Ukraine Power Grid Malware",        "tags=ukraine,destructive,grid"),
        (_ago(2),  38.0, -97.0, "North America","Ransomware",        4, "US Critical Infrastructure Hit",    "tags=us,ransomware,energy"),
        (_ago(3),  51.5,  10.0, "Europe",      "DDoS",               3, "NATO Alliance DDoS Campaign",       "tags=nato,ddos,russia-nexus"),
        (_ago(4),  33.9,  35.5, "Middle East", "Wiperware",          5, "Lebanon Telecom Wiperware",         "tags=lebanon,wiper,telecom"),
        (_ago(5),  25.2,  55.3, "Middle East", "Supply Chain",       4, "UAE Finance Sector Supply Chain",   "tags=uae,supply-chain,finance"),
    ]
    return pd.DataFrame([
        {
            "source": "Cyber",
            "timestamp": pd.Timestamp(f"{date} 00:00:00", tz="UTC"),
            "lat": lat, "lon": lon, "region": region,
            "category": cat, "severity": sev, "title": title, "details": details,
            "evidence_url": "https://otx.alienvault.com",
        }
        for date, lat, lon, region, cat, sev, title, details in incidents
    ])


def radiation_fallback() -> pd.DataFrame:
    """Safecast radiation readings at nuclear facility sites."""
    sites = [
        (28.83, 50.89, "Middle East", "Bushehr, Iran",         9.2,  _ago(1)),
        (30.97, 35.15, "Middle East", "Dimona, Israel",        11.4, _ago(1)),
        (34.89, 50.47, "Middle East", "Fordow, Iran",          8.8,  _ago(2)),
        (47.51, 34.58, "Europe",      "Zaporizhzhia, Ukraine", 33.4, _ago(1)),
        (33.72, 51.73, "Middle East", "Natanz, Iran",          7.6,  _ago(3)),
        (37.42, 141.03,"Asia",        "Fukushima, Japan",       8.4, _ago(1)),
    ]
    return pd.DataFrame([
        {
            "source": "Radiation",
            "timestamp": pd.Timestamp(f"{date} 00:00:00", tz="UTC"),
            "lat": lat, "lon": lon, "region": region,
            "category": "Radiation Reading",
            "severity": (5 if cpm > 100 else 4 if cpm > 50 else 3 if cpm > 30 else 2 if cpm > 20 else 1),
            "title": f"Radiation | {site}",
            "details": f"cpm={cpm:.1f}",
            "evidence_url": "https://api.safecast.org",
        }
        for lat, lon, region, site, cpm, date in sites
    ])


def macro_fallback() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": _ago(28), "metric": "Brent Crude (USD/bbl)", "value":  82.5, "source": "EIA"},
        {"date": _ago(28), "metric": "Gold (USD/oz)",          "value":2035.0, "source": "LBMA"},
        {"date": _ago(28), "metric": "USD Index",              "value": 104.2, "source": "Fed"},
        {"date": _ago(14), "metric": "Brent Crude (USD/bbl)", "value":  83.1, "source": "EIA"},
        {"date": _ago(14), "metric": "Gold (USD/oz)",          "value":2045.0, "source": "LBMA"},
        {"date": _ago(14), "metric": "USD Index",              "value": 104.8, "source": "Fed"},
        {"date": _ago( 1), "metric": "Brent Crude (USD/bbl)", "value":  81.9, "source": "EIA"},
        {"date": _ago( 1), "metric": "Gold (USD/oz)",          "value":2060.0, "source": "LBMA"},
        {"date": _ago( 1), "metric": "USD Index",              "value": 103.9, "source": "Fed"},
    ])
