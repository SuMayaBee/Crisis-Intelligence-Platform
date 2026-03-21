from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd

from data.events import _safe_get_json, _safe_get_text
from data.fallbacks import macro_fallback


def load_macro() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    eia_key = os.getenv("EIA_API_KEY")
    if eia_key:
        eia_specs = [
            ("WTI", "https://api.eia.gov/v2/petroleum/pri/spt/data/", "RWTC", "daily"),
            ("Brent", "https://api.eia.gov/v2/petroleum/pri/spt/data/", "RBRTE", "daily"),
            ("HenryHub", "https://api.eia.gov/v2/natural-gas/pri/fut/data/", "RNGWHHD", "daily"),
        ]
        for metric, base, series, freq in eia_specs:
            try:
                data = _safe_get_json(
                    base,
                    params={
                        "api_key": eia_key,
                        "frequency": freq,
                        "data[0]": "value",
                        "sort[0][column]": "period",
                        "sort[0][direction]": "desc",
                        "length": "15",
                        "facets[series][]": series,
                    },
                )
                for item in data.get("response", {}).get("data", [])[:10]:
                    rows.append({"date": item.get("period"), "metric": metric, "value": float(item.get("value", 0)), "source": "EIA"})
            except Exception:
                pass

    fred_key = os.getenv("FRED_API_KEY")
    if fred_key:
        fred_series = {"VIX": "VIXCLS", "T10Y2Y": "T10Y2Y"}
        for metric, sid in fred_series.items():
            try:
                data = _safe_get_json(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": sid,
                        "api_key": fred_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": "10",
                    },
                )
                for obs in data.get("observations", []):
                    if obs.get("value") not in {".", None, ""}:
                        rows.append({"date": obs.get("date"), "metric": metric, "value": float(obs.get("value")), "source": "FRED"})
            except Exception:
                pass

    try:
        data = _safe_get_json(
            "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny",
            params={"fields": "record_date,tot_pub_debt_out_amt", "sort": "-record_date", "page[size]": "10"},
        )
        for row in data.get("data", []):
            rows.append(
                {
                    "date": row.get("record_date"),
                    "metric": "TotalDebtTrillion",
                    "value": float(row.get("tot_pub_debt_out_amt", 0)) / 1e12,
                    "source": "Treasury",
                }
            )
    except Exception:
        pass

    if not rows:
        macro = macro_fallback()
    else:
        macro = pd.DataFrame(rows)

    macro["date"] = pd.to_datetime(macro["date"], errors="coerce")
    return macro.dropna(subset=["date"]).copy()


def load_ofac_sample() -> pd.DataFrame:
    try:
        xml = _safe_get_text("https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML")
        publish = re.search(r"<Publish_Date>(.*?)</Publish_Date>", xml)
        count = len(re.findall(r"<sdnEntry>", xml))
        updated = publish.group(1) if publish else pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
        return pd.DataFrame(
            [{"updated": updated, "program": "SDN", "new_entities": min(30, max(1, int(count * 0.001))), "high_risk_country": "Mixed"}]
        )
    except Exception:
        return pd.DataFrame(
            [{"updated": "2026-03-21", "program": "SDN", "new_entities": 14, "high_risk_country": "Iran"}]
        )


def load_safecast_sample() -> pd.DataFrame:
    sites = {"Zaporizhzhia": (47.51, 34.58), "Fukushima": (37.42, 141.03), "Bushehr": (28.83, 50.89)}
    rows: list[dict[str, Any]] = []
    for site, (lat, lon) in sites.items():
        try:
            data = _safe_get_json(
                "https://api.safecast.org/measurements.json",
                params={"latitude": lat, "longitude": lon, "distance": "100000", "limit": "5"},
            )
            if isinstance(data, list):
                for rec in data:
                    value = rec.get("value")
                    captured = rec.get("captured_at")
                    if value is not None and captured:
                        rows.append({"date": captured[:10], "site": site, "cpm": float(value)})
        except Exception:
            continue

    if not rows:
        return pd.DataFrame(
            [
                {"date": "2026-03-21", "site": "Zaporizhzhia", "cpm": 33.4},
                {"date": "2026-03-21", "site": "Fukushima", "cpm": 8.4},
                {"date": "2026-03-21", "site": "Bushehr", "cpm": 9.2},
            ]
        )

    return pd.DataFrame(rows)


def load_space_sample() -> pd.DataFrame:
    specs = {"Starlink": "starlink", "OneWeb": "oneweb", "Military": "military", "Stations": "stations"}
    rows: list[dict[str, Any]] = []
    for label, group in specs.items():
        try:
            data = _safe_get_json(f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json")
            rows.append({"constellation": label, "active": len(data) if isinstance(data, list) else 0})
        except Exception:
            rows.append({"constellation": label, "active": 0})
    return pd.DataFrame(rows)


def load_market_sample() -> pd.DataFrame:
    symbols = ["SPY", "QQQ", "BTC-USD", "CL=F", "^VIX"]
    rows: list[dict[str, Any]] = []
    for sym in symbols:
        try:
            data = _safe_get_json(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"range": "5d", "interval": "1d", "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            if price is None:
                closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
                closes = [c for c in closes if c is not None]
                if closes:
                    price = closes[-1]
                    prev = closes[-2] if len(closes) > 1 else closes[-1]
            if price is not None and prev:
                pct = ((float(price) - float(prev)) / float(prev)) * 100
                rows.append({"symbol": sym, "price": float(price), "change_pct": round(pct, 2)})
        except Exception:
            continue

    if not rows:
        return pd.DataFrame(
            [
                {"symbol": "SPY", "price": 593.72, "change_pct": -0.18},
                {"symbol": "QQQ", "price": 466.11, "change_pct": -0.24},
                {"symbol": "BTC-USD", "price": 70653.2, "change_pct": 1.66},
                {"symbol": "CL=F", "price": 98.71, "change_pct": 1.78},
                {"symbol": "^VIX", "price": 27.2, "change_pct": 4.62},
            ]
        )

    return pd.DataFrame(rows)
