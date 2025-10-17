"""Data loading helpers for Börse Stuttgart instruments."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import pandas as pd
import pytz
import requests


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
        "date": "timestamp",
        "time": "timestamp",
        "t": "timestamp",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    missing_price_cols = [col for col in ["open", "high", "low", "close"] if col not in df.columns]
    if missing_price_cols:
        raise ValueError("Preisfelder in der Antwort fehlen: " + ", ".join(missing_price_cols))

    if "volume" not in df.columns:
        df["volume"] = pd.NA

    ts_candidates = ["timestamp", "datetime", "time", "date"]
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


def fetch_boerse_history(identifier: str, range_key: str) -> pd.DataFrame:
    if range_key not in RANGE_OPTIONS:
        raise KeyError(f"Unbekannte Range-Auswahl: {range_key}")

    selection = RANGE_OPTIONS[range_key]
    params = {
        "isin": identifier,
        "range": selection["range"],
        "interval": selection["interval"],
    }
    endpoint = (
        BOERSE_INTRADAY_ENDPOINT
        if selection["endpoint"] == "intraday"
        else BOERSE_HISTORY_ENDPOINT
    )
    response = requests.get(endpoint, params=params, headers=REQUEST_HEADERS, timeout=15)
    response.raise_for_status()
    payload = response.json()
    df = _normalise_records(payload)
    if df.empty:
        raise ValueError("Keine Kursdaten verfügbar")
    return df


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
