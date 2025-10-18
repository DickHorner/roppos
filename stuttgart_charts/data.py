"""Data loading helpers for Boerse Stuttgart instruments.

This module prefers HTML-based scraping as a fallback when JSON APIs are
unavailable or when no candles are served outside trading hours. It extracts
snapshot quote information (Geld/Brief/Last) from the Nuxt payload embedded in
instrument pages and synthesizes a minimal OHLC row when needed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pytz
import requests
# from bs4 import BeautifulSoup  # noqa: F401  (reserved for future table parsing)

# Configurable constants for HTML content matching
QUOTE_BLOCK_STRINGS = [
    "QuoteBlock",
    "Kursdaten",
    "LETZTER PREIS"
]


def _resolve_bundle_path(relative: str) -> Path:
    """Return a path that works both in development and PyInstaller bundles."""

    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    if not isinstance(base_path, Path):
        base_path = Path(base_path)
    return base_path / relative


WATCHLIST_PATH = _resolve_bundle_path("data/watchlist.csv")
BOERSE_SEARCH_ENDPOINT = "https://www.boerse-stuttgart.de/api/data/instruments/search"
BOERSE_INTRADAY_ENDPOINT = "https://www.boerse-stuttgart.de/api/data/pricehistory/intraday"
BOERSE_HISTORY_ENDPOINT = "https://www.boerse-stuttgart.de/api/data/pricehistory/history"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockChartingBot/1.0)",
    "Accept": "application/json, text/plain, */*",
}
TIMEZONE_EUROPE_BERLIN = pytz.timezone("Europe/Berlin")

RANGE_OPTIONS: Dict[str, Dict[str, str]] = {
    "1 Tag": {"range": "1d", "interval": "1m", "endpoint": "intraday"},
    "5 Tage": {"range": "5d", "interval": "5m", "endpoint": "intraday"},
    "1 Monat": {"range": "1mo", "interval": "30m", "endpoint": "intraday"},
    "3 Monate": {"range": "3mo", "interval": "1h", "endpoint": "intraday"},
    "6 Monate": {"range": "6mo", "interval": "2h", "endpoint": "history"},
    "1 Jahr": {"range": "1y", "interval": "1d", "endpoint": "history"},
    "3 Jahre": {"range": "3y", "interval": "1d", "endpoint": "history"},
    "5 Jahre": {"range": "5y", "interval": "1d", "endpoint": "history"},
}


def load_watchlist(path: Path = WATCHLIST_PATH) -> pd.DataFrame:
    """Load the pre-curated watchlist CSV."""
    if not path.exists():
        raise FileNotFoundError(f"Watchlist-Datei nicht gefunden: {path}")
    return pd.read_csv(path)


def _normalise_records(payload: Dict) -> pd.DataFrame:
    if not payload:
        return pd.DataFrame()

    records = None
    for key in ("candles", "data", "records", "results", "chart", "values"):
        if isinstance(payload, dict) and key in payload:
            candidate = payload[key]
            if isinstance(candidate, dict):
                candidate = list(candidate.values())
            records = candidate
            break

    if records is None:
        records = payload if isinstance(payload, list) else [payload]

    if isinstance(records, dict):
        records = list(records.values())

    df: pd.DataFrame
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, dict):
            df = pd.DataFrame(records)
        else:
            columns = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ][: len(first)]
            df = pd.DataFrame(records, columns=columns)
    else:
        df = pd.DataFrame(records)

    rename_map = {
        "o": "open",
        "h": "high",
        "l": "low",
        "c": "close",
        "v": "volume",
        "value": "close",
        "price": "close",
        "date": "timestamp",
        "time": "timestamp",
        "t": "timestamp",
        "quoteDateTime": "timestamp",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # If only "close" is present (e.g., snapshot), synthesize OHLC
    if not set(["open", "high", "low"]).issubset(df.columns) and "close" in df.columns:
        close_series = df["close"]
        df["open"] = close_series
        df["high"] = close_series
        df["low"] = close_series

    missing_price_cols = [col for col in ["open", "high", "low", "close"] if col not in df.columns]
    if missing_price_cols:
        raise ValueError("Preisfelder in der Antwort fehlen: " + ", ".join(missing_price_cols))

    if "volume" not in df.columns:
        df["volume"] = pd.NA

    ts_candidates = ["timestamp", "datetime", "time", "date", "quoteDateTime"]
    for cand in ts_candidates:
        if cand in df.columns:
            ts = df[cand]
            break
    else:
        raise ValueError("Zeitstempel in der Antwort nicht gefunden")

    parsed_ts = pd.to_datetime(ts, utc=True, errors="coerce")
    if parsed_ts.isna().all():
        parsed_ts = pd.to_datetime(ts, utc=True, errors="coerce", unit="ms")
    if parsed_ts.isna().all():
        parsed_ts = pd.to_datetime(ts, utc=True, errors="coerce", unit="s")

    df["timestamp"] = parsed_ts
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


# ------------------------------ HTML scraping ------------------------------


def _derive_wkn_from_isin(isin: str) -> Optional[str]:
    """Derive WKN for German ISINs. Many German ISINs follow DE000 + WKN + check.

    Example: DE0007030009 -> WKN 703000
    """
    if not isin:
        return None
    isin = isin.strip().upper()
    if len(isin) == 12 and isin.startswith("DE000"):
        return isin[5:11]
    return None


def _fetch_instrument_html_via_relay(wkn: str) -> Optional[str]:
    """
    Fetches the HTML content of a Boerse Stuttgart instrument page using a read-only relay service
    to bypass Cloudflare restrictions.

    Parameters:
        wkn (str): The Wertpapierkennnummer (WKN) identifier of the instrument.

    Returns:
        Optional[str]: The HTML content of the instrument page if successful, otherwise None.
    """
    candidates = [
        f"https://r.jina.ai/https://www.boerse-stuttgart.de/en/products/equities/stuttgart/{wkn}",
    ]
    for url in candidates:
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200:
                text = resp.text
                # Efficient substring search using a single regex pattern
                pattern = "|".join(re.escape(s) for s in QUOTE_BLOCK_STRINGS)
                if re.search(pattern, text, re.IGNORECASE):
                    return text
        except Exception:
            continue
    return None
def _extract_block_json(html: str, block_name: str) -> Optional[Dict]:
    """Extract escaped JSON for a block (e.g., QuoteBlock) from Nuxt payload."""
    if not html:
        return None
    # The regex pattern below matches:
    # - The block name in quotes (e.g., "QuoteBlock")
    # - Followed by a comma and a UUID (hex + dashes) in quotes
    # - Followed by a comma and the JSON object in quotes
    # - Captures the JSON object as group 1
    pattern = rf"\"{re.escape(block_name)}\"\s*,\s*\"[0-9a-f\-]+\"\s*,\s*\"(\{{.*?\}})\""
    m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    raw = m.group(1)
    try:
        # Unescape unicode + quotes
        obj = json.loads(raw.encode("utf-8").decode("unicode_escape"))
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return None


def _parse_quote_snapshot_from_html(html: str) -> Optional[pd.DataFrame]:
    """Build a single-row OHLCV DataFrame from QuoteBlock in HTML."""
    # 1) Prefer structured Nuxt block if present
    block = _extract_block_json(html, "QuoteBlock")
    if block:
        payload = {
            "price": block.get("price"),
            "quoteDateTime": block.get("quoteDateTime"),
            "latestTradingVolume": block.get("latestTradingVolume", 0),
        }
    else:
        # 2) Fallback: parse r.jina.ai Markdown text (Kursdaten table)
        text = html
        # German number parsing helper
        def _parse_de_number(s: str) -> Optional[float]:
            """
            Parse a German-formatted number string to float.
            Removes thousand separators (dots, non-breaking spaces), and converts decimal comma to dot.
            """
            s = s.strip()
            # remove thousand separators
            s = s.replace(".", "").replace("\xa0", " ")
            # decimal comma to dot
            s = s.replace(",", ".")
            try:
                return float(s)
            except Exception:
                return None

        # Extract last price after "LETZTER PREIS" possibly followed by value and qualifier
        price_match = re.search(r"LETZTER\s+PREIS\s+([0-9\.,]+)", text, re.IGNORECASE)
        # Extract Kurszeit like "17.10.2025 / 21:59:01" or "17.10.2025 / 21:59:01 Uhr"
        time_match = re.search(r"KURSZEIT\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*/\s*[0-9]{2}:[0-9]{2}:[0-9]{2})", text, re.IGNORECASE)
        vol_match = re.search(r"TAGESVOLUMEN.*?([0-9\.,]+)", text, re.IGNORECASE)
        price = _parse_de_number(price_match.group(1)) if price_match else None
        volume = _parse_de_number(vol_match.group(1)) if vol_match else 0
        quote_dt = None
        if time_match:
            dt_str = time_match.group(1)
            # Normalize "dd.mm.yyyy / HH:MM:SS"
            try:
                quote_dt = pd.to_datetime(dt_str, format="%d.%m.%Y / %H:%M:%S", utc=True)
            except (ValueError, TypeError):
                # try without explicit format
                quote_dt = pd.to_datetime(dt_str, utc=True, errors="coerce")
        if price is None or quote_dt is None:
            return None
        payload = {"price": price, "quoteDateTime": quote_dt, "latestTradingVolume": volume}
    df = _normalise_records([payload])
    if df.empty:
        return None
    for col in ("open", "high", "low", "close"):
        if col not in df or df[col].isna().values.any():
            df[col] = df["close"].ffill().bfill()
    if "volume" in df.columns and df["volume"].isna().all():
        df["volume"] = payload.get("latestTradingVolume", 0) or 0
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def fetch_boerse_history(identifier: str, range_key: str) -> pd.DataFrame:
    # HTML fallback (snapshot from QuoteBlock)
    wkn = _derive_wkn_from_isin(identifier)
    html = _fetch_instrument_html_via_relay(wkn) if wkn else None
    #     pass

    # HTML fallback (snapshot from QuoteBlock)
    wkn = _derive_wkn_from_isin(identifier)
    html = _fetch_instrument_html_via_relay(wkn) if wkn else None
    if html:
        snap = _parse_quote_snapshot_from_html(html)
        if snap is not None and not snap.empty:
            # mark as snapshot for UI hints
            snap.attrs["source"] = "html_snapshot"
            try:
                # best-effort last update for display
                snap.attrs["last_update"] = pd.to_datetime(snap["timestamp"].iloc[-1], utc=True)
            except (KeyError, IndexError, ValueError, TypeError):
                pass
            return snap

    raise ValueError(
        "Keine Kursdaten verfuegbar (ausserhalb der Handelszeit oder Zugriff blockiert)"
    )


def search_instruments(query: str, limit: int = 15) -> pd.DataFrame:
    params = {"query": query, "limit": limit}
    response = requests.get(
        BOERSE_SEARCH_ENDPOINT, params=params, headers=REQUEST_HEADERS, timeout=10
    )
    response.raise_for_status()
    payload = response.json()

    candidates = None
    if isinstance(payload, dict):
        for key in ("data", "results", "items", "instruments"):
            if key in payload:
                candidates = payload[key]
                break
    if candidates is None:
        candidates = payload
    df = pd.DataFrame(candidates)
    return df


def enrich_with_timezone(df: pd.DataFrame, tz: pytz.timezone = TIMEZONE_EUROPE_BERLIN) -> pd.DataFrame:
    result = df.copy()
    if result["timestamp"].dt.tz is None:
        result["timestamp"] = result["timestamp"].dt.tz_localize(pytz.UTC)
    result["timestamp_local"] = result["timestamp"].dt.tz_convert(tz)
    return result
