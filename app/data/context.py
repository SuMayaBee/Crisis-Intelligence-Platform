from __future__ import annotations

import math
import os
import re
from typing import Any

import pandas as pd
import panel as pn

from data.events import _safe_get_json, _safe_get_text
from data.fallbacks import macro_fallback

# ── exchangerate.host config ──────────────────────────────────────────────────
_EXRATE_KEY = os.getenv("EXCHANGERATE_HOST_KEY", "8714a033883d231f95dedd4270d88619")
_FX_CURRENCIES = ["EUR", "GBP", "JPY", "CNY", "RUB", "TRY", "SAR", "ILS"]
_FX_BASE_RATES: dict[str, float] = {
    "EUR": 0.924, "GBP": 0.785, "JPY": 149.8, "CNY": 7.24,
    "RUB": 91.5,  "TRY": 32.1,  "SAR": 3.75,  "ILS": 3.73,
    "AED": 3.673, "KWD": 0.307, "QAR": 3.641, "OMR": 0.385,
    "BHD": 0.377, "JOD": 0.709, "CHF": 0.899, "NOK": 10.56,
    "SEK": 10.42, "DKK": 6.89,  "PLN": 4.02,  "HUF": 358.0,
    "CZK": 22.8,  "RON": 4.65,  "UAH": 39.1,  "KRW": 1330.0,
    "INR": 83.1,  "SGD": 1.34,  "HKD": 7.82,  "AUD": 1.53,
    "NZD": 1.63,  "THB": 35.1,  "MYR": 4.71,  "CAD": 1.36,
    "BRL": 5.01,  "MXN": 17.1,  "ARS": 870.0, "CLP": 940.0,
    "COP": 3900.0,"ZAR": 18.6,  "NGN": 1550.0,"EGP": 47.5,
}

FX_REGION_GROUPS: dict[str, list[str]] = {
    "Geopolitical":     ["EUR", "GBP", "JPY", "CNY", "RUB", "TRY", "SAR", "ILS"],
    "Middle East":      ["SAR", "AED", "KWD", "QAR", "OMR", "BHD", "JOD", "ILS"],
    "Europe":           ["EUR", "GBP", "CHF", "NOK", "SEK", "DKK", "PLN", "HUF", "CZK", "RON", "UAH", "TRY", "RUB"],
    "Asia Pacific":     ["JPY", "CNY", "KRW", "INR", "SGD", "HKD", "AUD", "NZD", "THB", "MYR"],
    "Americas":         ["CAD", "BRL", "MXN", "ARS", "CLP", "COP"],
    "Emerging Markets": ["ZAR", "NGN", "EGP", "BRL", "INR", "MXN", "KRW", "TRY", "RUB"],
}


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


@pn.cache(ttl=3600)
def load_commodities_history() -> pd.DataFrame:
    """30-day daily closes for oil, metals, and agriculture — Yahoo Finance (no key)."""
    import math
    symbols = {
        "WTI":      "CL=F",
        "Brent":    "BZ=F",
        "Nat Gas":  "NG=F",
        "Gold":     "GC=F",
        "Silver":   "SI=F",
        "Palladium":"PA=F",
        "Wheat":    "ZW=F",
        "Copper":   "HG=F",
    }
    rows: list[dict[str, Any]] = []
    def _fetch(sym: str, range_: str, interval: str) -> list[tuple]:
        try:
            data = _safe_get_json(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"range": range_, "interval": interval, "includePrePost": "false"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            result = data.get("chart", {}).get("result", [{}])[0]
            timestamps = result.get("timestamp", [])
            closes = (result.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
            return [(pd.Timestamp(ts, unit="s").normalize(), round(float(p), 2))
                    for ts, p in zip(timestamps, closes) if p is not None]
        except Exception:
            return []

    for label, sym in symbols.items():
        # Historical weekly data (up to 5 years)
        seen: dict = {}
        for dt, price in _fetch(sym, "5y", "1wk"):
            seen[dt] = price
        # Recent daily data (last 60 days) — fills gaps in most recent weeks
        for dt, price in _fetch(sym, "60d", "1d"):
            seen[dt] = price
        for dt, price in seen.items():
            rows.append({"date": dt, "commodity": label, "price": price})

    if not rows:
        base = {
            "WTI": 76.0, "Brent": 80.5, "Nat Gas": 2.1,
            "Gold": 2300.0, "Silver": 27.0, "Palladium": 1020.0,
            "Wheat": 550.0, "Copper": 4.20,
        }
        today = pd.Timestamp.now().normalize()
        # Two years of weekly fallback data
        for i in range(104):
            d = today - pd.Timedelta(weeks=103 - i)
            for commodity, bp in base.items():
                rows.append({"date": d, "commodity": commodity,
                              "price": round(bp + math.sin(i * 0.15 + hash(commodity) % 6) * bp * 0.08, 2)})

    return pd.DataFrame(rows)


def load_currency_rates() -> pd.DataFrame:
    """Spot FX rates + 1-day % change for geopolitically relevant pairs — Yahoo Finance."""
    pairs = {
        "USD Index": "DX-Y.NYB",
        "EUR/USD":   "EURUSD=X",
        "GBP/USD":   "GBPUSD=X",
        "USD/JPY":   "USDJPY=X",
        "USD/CNY":   "USDCNY=X",
        "USD/RUB":   "USDRUB=X",
        "USD/TRY":   "USDTRY=X",
        "USD/SAR":   "USDSAR=X",
        "USD/ILS":   "USDILS=X",
    }
    rows: list[dict[str, Any]] = []
    for label, sym in pairs.items():
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
                    price, prev = closes[-1], (closes[-2] if len(closes) > 1 else closes[-1])
            if price is not None and prev:
                pct = ((float(price) - float(prev)) / float(prev)) * 100
                rows.append({"pair": label, "rate": round(float(price), 4), "change_pct": round(pct, 3)})
        except Exception:
            continue

    if not rows:
        return pd.DataFrame([
            {"pair": "USD Index", "rate": 104.20, "change_pct":  0.18},
            {"pair": "EUR/USD",   "rate": 1.082,  "change_pct":  0.12},
            {"pair": "GBP/USD",   "rate": 1.265,  "change_pct": -0.08},
            {"pair": "USD/JPY",   "rate": 149.80, "change_pct":  0.21},
            {"pair": "USD/CNY",   "rate": 7.241,  "change_pct": -0.05},
            {"pair": "USD/RUB",   "rate": 91.50,  "change_pct":  0.45},
            {"pair": "USD/TRY",   "rate": 32.10,  "change_pct":  0.31},
            {"pair": "USD/SAR",   "rate": 3.752,  "change_pct":  0.00},
            {"pair": "USD/ILS",   "rate": 3.725,  "change_pct": -0.18},
        ])

    return pd.DataFrame(rows)


@pn.cache(ttl=300)
def load_fx_live(currencies: list[str] | None = None) -> pd.DataFrame:
    """Latest FX rates + 1-day % change — exchangerate.host live + historical."""
    codes   = currencies or _FX_CURRENCIES
    cur_str = ",".join(codes)
    yesterday = (pd.Timestamp.now() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        live = _safe_get_json(
            "https://api.exchangerate.host/live",
            params={"access_key": _EXRATE_KEY, "currencies": cur_str, "source": "USD"},
        )
        prev = _safe_get_json(
            "https://api.exchangerate.host/historical",
            params={"access_key": _EXRATE_KEY, "date": yesterday, "currencies": cur_str, "source": "USD"},
        )
        if live.get("success"):
            live_q = live.get("quotes", {})
            prev_q = prev.get("quotes", {}) if prev.get("success") else {}
            rows: list[dict[str, Any]] = []
            for code in codes:
                rate = live_q.get(f"USD{code}")
                if rate is None:
                    continue
                prev_rate = prev_q.get(f"USD{code}")
                pct = 0.0
                if prev_rate and float(prev_rate) != 0:
                    pct = ((float(rate) - float(prev_rate)) / float(prev_rate)) * 100
                rows.append({"pair": f"USD/{code}", "rate": round(float(rate), 4),
                             "change_pct": round(pct, 3)})
            if rows:
                return pd.DataFrame(rows)
    except Exception:
        pass
    return pd.DataFrame([
        {"pair": f"USD/{c}", "rate": _FX_BASE_RATES.get(c, 1.0),
         "change_pct": round(math.sin(hash(c) % 10) * 0.3, 3)}
        for c in codes
    ])


def load_fx_history(start_date: str, end_date: str,
                    currencies: list[str] | None = None) -> pd.DataFrame:
    """Daily FX rates over a date range — exchangerate.host timeframe endpoint."""
    codes   = currencies or _FX_CURRENCIES
    cur_str = ",".join(codes)
    rows: list[dict[str, Any]] = []
    try:
        data = _safe_get_json(
            "https://api.exchangerate.host/timeframe",
            params={"access_key": _EXRATE_KEY, "start_date": start_date,
                    "end_date": end_date, "source": "USD", "currencies": cur_str},
        )
        if data.get("success"):
            for date_str, rates in data.get("quotes", {}).items():
                for code in codes:
                    rate = rates.get(f"USD{code}")
                    if rate is not None:
                        rows.append({"date": pd.Timestamp(date_str),
                                     "currency": f"USD/{code}",
                                     "rate": round(float(rate), 4)})
    except Exception:
        pass
    if not rows:
        dates = pd.date_range(start=start_date, end=end_date, freq="B")
        for i, d in enumerate(dates):
            for code in codes:
                base = _FX_BASE_RATES.get(code, 1.0)
                rows.append({"date": d, "currency": f"USD/{code}",
                             "rate": round(base * (1 + math.sin(i * 0.08 + hash(code) % 5) * 0.03), 4)})
    return pd.DataFrame(rows)


def load_fx_fluctuation(start_date: str, end_date: str,
                        currencies: list[str] | None = None) -> pd.DataFrame:
    """% change in FX rates over a period — exchangerate.host fluctuation endpoint."""
    codes   = currencies or _FX_CURRENCIES
    cur_str = ",".join(codes)
    rows: list[dict[str, Any]] = []
    try:
        data = _safe_get_json(
            "https://api.exchangerate.host/fluctuation",
            params={"access_key": _EXRATE_KEY, "start_date": start_date,
                    "end_date": end_date, "source": "USD", "currencies": cur_str},
        )
        if data.get("success"):
            for code, info in data.get("rates", {}).items():
                if code in codes:
                    rows.append({"pair": f"USD/{code}",
                                 "change_pct": round(float(info.get("change_pct", 0)), 3),
                                 "start_rate": round(float(info.get("start_rate", 0)), 4),
                                 "end_rate":   round(float(info.get("end_rate",   0)), 4)})
    except Exception:
        pass
    if not rows:
        for code in codes:
            base = _FX_BASE_RATES.get(code, 1.0)
            rows.append({"pair": f"USD/{code}", "change_pct": 0.0,
                         "start_rate": base, "end_rate": base})
    return pd.DataFrame(rows)


def load_ticker_search(query: str) -> list[str]:
    """Search tickers by symbol or company name — Yahoo Finance search API (no key)."""
    try:
        data = _safe_get_json(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": 15, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        allowed = {"EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY", "CURRENCY", "FUTURE"}
        return [
            f"{q['symbol']} — {q.get('shortname') or q.get('longname', '')}"
            for q in data.get("quotes", [])
            if q.get("symbol") and q.get("quoteType") in allowed
        ]
    except Exception:
        return []


@pn.cache(ttl=3600)
def load_ohlcv(ticker: str, start_date: str, end_date: str,
               interval: str = "1d") -> pd.DataFrame:
    """OHLCV candlestick data for any ticker — Yahoo Finance (no key needed)."""
    start_ts = int(pd.Timestamp(start_date).timestamp())
    end_ts   = int((pd.Timestamp(end_date) + pd.Timedelta(days=1)).timestamp())
    try:
        data = _safe_get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"period1": start_ts, "period2": end_ts,
                    "interval": interval, "includePrePost": "false"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        result = data.get("chart", {}).get("result", [{}])[0]
        if not result:
            return pd.DataFrame()
        timestamps = result.get("timestamp", [])
        quote      = (result.get("indicators", {}).get("quote") or [{}])[0]
        opens   = quote.get("open",   [])
        highs   = quote.get("high",   [])
        lows    = quote.get("low",    [])
        closes  = quote.get("close",  [])
        volumes = quote.get("volume", [])
        rows: list[dict[str, Any]] = []
        for i, ts in enumerate(timestamps):
            o = opens[i]   if i < len(opens)   else None
            h = highs[i]   if i < len(highs)   else None
            l = lows[i]    if i < len(lows)    else None
            c = closes[i]  if i < len(closes)  else None
            v = volumes[i] if i < len(volumes) else 0
            if None not in (o, h, l, c):
                rows.append({
                    "date":   pd.Timestamp(ts, unit="s"),
                    "open":   round(float(o), 4),
                    "high":   round(float(h), 4),
                    "low":    round(float(l), 4),
                    "close":  round(float(c), 4),
                    "volume": int(v) if v else 0,
                })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


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
