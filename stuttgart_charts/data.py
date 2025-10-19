"""Data loading helpers for Börse Stuttgart instruments.

Prefers parsing HTML pages (Nuxt payload) and includes an HTML snapshot
fallback (via a read-only relay) for times when JSON APIs are unavailable or
no candles are served outside trading hours.
"""
from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.parse import urljoin

import pandas as pd
import pytz
import requests

# Configurable constants for HTML content matching
QUOTE_BLOCK_STRINGS = [
    "QuoteBlock",
    "Kursdaten",
    "LETZTER PREIS",
]


def _resolve_bundle_path(relative: str) -> Path:
    """Return a path that works both in development and PyInstaller bundles."""

    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    if not isinstance(base_path, Path):
        base_path = Path(base_path)
    return base_path / relative


WATCHLIST_PATH = _resolve_bundle_path("data/watchlist.csv")
BASE_URL = "https://www.boerse-stuttgart.de"
SEARCH_ROUTE = "/de-de/suche/"
TIMEZONE_EUROPE_BERLIN = pytz.timezone("Europe/Berlin")

# Headers for HTML requests
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StockChartingBot/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Also expose API endpoint constants for external callers/imports
BOERSE_SEARCH_ENDPOINT = "https://www.boerse-stuttgart.de/api/data/instruments/search"
BOERSE_INTRADAY_ENDPOINT = "https://www.boerse-stuttgart.de/api/data/pricehistory/intraday"
BOERSE_HISTORY_ENDPOINT = "https://www.boerse-stuttgart.de/api/data/pricehistory/history"

RANGE_WINDOWS: Dict[str, object] = {
    "1 Tag": timedelta(days=1),
    "5 Tage": timedelta(days=5),
    "1 Monat": pd.DateOffset(months=1),
    "3 Monate": pd.DateOffset(months=3),
    "6 Monate": pd.DateOffset(months=6),
    "1 Jahr": pd.DateOffset(years=1),
    "3 Jahre": pd.DateOffset(years=3),
    "5 Jahre": pd.DateOffset(years=5),
}

# UI mapping retained for dropdowns; not used for fetching in this module
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


@dataclass
class InstrumentMatch:
    name: str
    url: str
    isin: Optional[str] = None
    wkn: Optional[str] = None


def _fetch_html(url: str, params: Optional[Dict[str, str]] = None) -> str:
    response = requests.get(
        url,
        params=params,
        headers=REQUEST_HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    return response.text


def _iter_json_nodes(node) -> Iterator:
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _iter_json_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_nodes(item)


def _extract_balanced_payload(source: str, marker: str) -> Optional[str]:
    idx = source.find(marker)
    if idx == -1:
        return None
    idx += len(marker)
    length = len(source)
    while idx < length and source[idx].isspace():
        idx += 1
    if idx >= length or source[idx] not in "[{":
        return None
    opening = source[idx]
    closing = "}" if opening == "{" else "]"
    depth = 0
    for pos in range(idx, length):
        char = source[pos]
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return source[idx : pos + 1]
    return None


def _parse_nuxt_payload(html_text: str):
    script_regexes = [
        r'id="__NUXT_DATA__"[^>]*>(.*?)</script>',
    ]
    for pattern in script_regexes:
        match = re.search(pattern, html_text, re.S)
        if not match:
            continue
        raw = html.unescape(match.group(1))
        cleaned = raw.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            temp = (
                cleaned.replace("undefined", "null")
                .replace("NaN", "null")
                .replace("Infinity", "null")
            )
            temp = re.sub(r"new Date\((.*?)\)", r"\1", temp)
            try:
                return json.loads(temp)
            except json.JSONDecodeError:
                continue

    balanced = _extract_balanced_payload(html_text, "window.__NUXT__=")
    if balanced:
        cleaned = html.unescape(balanced)
        temp = (
            cleaned.replace("undefined", "null")
            .replace("NaN", "null")
            .replace("Infinity", "null")
        )
        temp = re.sub(r"new Date\((.*?)\)", r"\1", temp)
        return json.loads(temp)
    raise ValueError("Konnte Nuxt-Zustand aus HTML nicht extrahieren")


def _extract_price_frames(state) -> List[pd.DataFrame]:
    frames: List[pd.DataFrame] = []
    for node in _iter_json_nodes(state):
        if isinstance(node, dict):
            candidates = [node] + list(node.values())
        elif isinstance(node, list):
            candidates = [node] + list(node)
        else:
            continue
        for candidate in candidates:
            if isinstance(candidate, (dict, list)):
                try:
                    df = _normalise_records(candidate)
                except Exception:
                    continue
                if not df.empty:
                    frames.append(df)
    return frames


def _choose_best_frame(frames: List[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()

    def score(df: pd.DataFrame) -> Tuple[int, float]:
        if df.empty:
            return (0, float("inf"))
        diffs = df["timestamp"].diff().dropna()
        if diffs.empty:
            median = float("inf")
        else:
            median = diffs.median().total_seconds()
        return (len(df), median)

    frames_sorted = sorted(frames, key=score, reverse=True)
    return frames_sorted[0]


def _filter_range(df: pd.DataFrame, range_key: str) -> pd.DataFrame:
    if df.empty or range_key not in RANGE_WINDOWS:
        return df
    window = RANGE_WINDOWS[range_key]
    end_ts = df["timestamp"].max()
    if pd.isna(end_ts):
        return df
    if isinstance(window, timedelta):
        start_ts = end_ts - window
    else:
        start_ts = end_ts - window
    return df[df["timestamp"] >= start_ts]


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


def _resolve_identifier_url(identifier: str) -> InstrumentMatch:
    identifier = identifier.strip()
    identifier_upper = identifier.upper()
    if identifier.startswith("http://") or identifier.startswith("https://"):
        return InstrumentMatch(name=identifier, url=identifier)

    watchlist = load_watchlist()
    search_hint = identifier
    if not watchlist.empty and "Identifier" in watchlist.columns:
        watch_match = watchlist[
            watchlist["Identifier"].astype(str).str.upper() == identifier_upper
        ]
        if not watch_match.empty:
            name = watch_match.iloc[0]["Name"]
            search_hint = f"{identifier} {name}".strip()

    search_df = search_instruments(search_hint, limit=20)
    if search_df.empty:
        raise ValueError(f"Keine Börse-Stuttgart-Treffer für '{identifier}' gefunden")

    for _, row in search_df.iterrows():
        isin = str(row.get("isin") or "").upper()
        wkn = str(row.get("wkn") or "").upper()
        url_value = row.get("url")
        if url_value and identifier_upper in {isin, wkn}:
            return InstrumentMatch(
                name=row.get("name") or identifier,
                url=url_value,
                isin=isin or None,
                wkn=wkn or None,
            )

    first = search_df.iloc[0]
    url_value = first.get("url")
    if not url_value:
        raise ValueError("Suchergebnis enthält keine Detail-URL")
    return InstrumentMatch(
        name=first.get("name") or identifier,
        url=url_value,
        isin=first.get("isin"),
        wkn=first.get("wkn"),
    )


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
    Fetch the HTML content of a Boerse Stuttgart instrument page using a read-only
    relay service to bypass Cloudflare restrictions.
    """
    if not wkn:
        return None
    candidates = [
        f"https://r.jina.ai/https://www.boerse-stuttgart.de/en/products/equities/stuttgart/{wkn}",
    ]
    for url in candidates:
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200:
                text = resp.text
                pattern = "|".join(re.escape(s) for s in QUOTE_BLOCK_STRINGS)
                if re.search(pattern, text, re.IGNORECASE):
                    return text
        except Exception:
            continue
    return None


def _extract_block_json(html_text: str, block_name: str) -> Optional[Dict]:
    """Extract escaped JSON for a block (e.g., QuoteBlock) from Nuxt payload."""
    if not html_text:
        return None
    pattern = rf"\"{re.escape(block_name)}\"\s*,\s*\"[0-9a-f\-]+\"\s*,\s*\"(\{{.*?\}})\""
    m = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    raw = m.group(1)
    try:
        obj = json.loads(raw.encode("utf-8").decode("unicode_escape"))
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return None


def _parse_quote_snapshot_from_html(html_text: str) -> Optional[pd.DataFrame]:
    """Build a single-row OHLCV DataFrame from QuoteBlock in HTML."""
    # 1) Prefer structured Nuxt block if present
    block = _extract_block_json(html_text, "QuoteBlock")
    if block:
        payload = {
            "price": block.get("price"),
            "quoteDateTime": block.get("quoteDateTime"),
            "latestTradingVolume": block.get("latestTradingVolume", 0),
        }
    else:
        # 2) Fallback: parse r.jina.ai Markdown text (Kursdaten table)
        text = html_text

        def _parse_de_number(s: str) -> Optional[float]:
            s = s.strip()
            s = s.replace(".", "").replace("\xa0", " ")
            s = s.replace(",", ".")
            try:
                return float(s)
            except Exception:
                return None

        price_match = re.search(r"LETZTER\s+PREIS\s+([0-9\.,]+)", text, re.IGNORECASE)
        time_match = re.search(
            r"KURSZEIT\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*/\s*[0-9]{2}:[0-9]{2}:[0-9]{2})",
            text,
            re.IGNORECASE,
        )
        vol_match = re.search(r"TAGESVOLUMEN.*?([0-9\.,]+)", text, re.IGNORECASE)
        price = _parse_de_number(price_match.group(1)) if price_match else None
        volume = _parse_de_number(vol_match.group(1)) if vol_match else 0
        quote_dt = None
        if time_match:
            dt_str = time_match.group(1)
            try:
                quote_dt = pd.to_datetime(dt_str, format="%d.%m.%Y / %H:%M:%S", utc=True)
            except (ValueError, TypeError):
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
    """Fetch historical/intraday data with HTML-first strategy and fallback."""
    if range_key not in RANGE_WINDOWS:
        raise KeyError(f"Unbekannte Range-Auswahl: {range_key}")

    try:
        instrument = _resolve_identifier_url(identifier)
        if not instrument.url:
            raise ValueError(f"Keine Detail-URL für '{identifier}' ermittelt")
        html_text = _fetch_html(instrument.url)
        state = _parse_nuxt_payload(html_text)
        frames = _extract_price_frames(state)
        df = _choose_best_frame(frames)
        if not df.empty:
            filtered = _filter_range(df, range_key)
            if not filtered.empty:
                return filtered
    except Exception:
        # proceed to HTML snapshot fallback
        pass

    # HTML fallback (snapshot from QuoteBlock via relay)
    wkn = _derive_wkn_from_isin(identifier)
    html_text = _fetch_instrument_html_via_relay(wkn) if wkn else None
    if html_text:
        snap = _parse_quote_snapshot_from_html(html_text)
        if snap is not None and not snap.empty:
            snap.attrs["source"] = "html_snapshot"
            try:
                snap.attrs["last_update"] = pd.to_datetime(snap["timestamp"].iloc[-1], utc=True)
            except (KeyError, IndexError, ValueError, TypeError):
                pass
            return snap

    raise ValueError("Keine Kursdaten verfügbar (außerhalb der Handelszeit oder Zugriff blockiert)")


def search_instruments(query: str, limit: int = 15) -> pd.DataFrame:
    """Search instruments via on-site search page (Nuxt state)."""
    params = {"query": query, "q": query, "searchValue": query}
    url = urljoin(BASE_URL, SEARCH_ROUTE)
    html_text = _fetch_html(url, params=params)
    state = _parse_nuxt_payload(html_text)

    seen: set[Tuple[str, str, str]] = set()
    records: List[Dict[str, Optional[str]]] = []
    for node in _iter_json_nodes(state):
        if not isinstance(node, dict):
            continue
        name = node.get("name") or node.get("title") or node.get("shortName")
        isin = node.get("isin") or node.get("isinCode")
        wkn = node.get("wkn") or node.get("wknCode")
        url_fragment = node.get("url") or node.get("href") or node.get("link")
        if not (name and url_fragment):
            continue
        if not (isin or wkn):
            continue
        absolute_url = urljoin(BASE_URL, url_fragment)
        key = (name, isin or "", wkn or "")
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "name": name,
                "isin": isin,
                "wkn": wkn,
                "url": absolute_url,
            }
        )
        if len(records) >= limit:
            break

    return pd.DataFrame(records)


def enrich_with_timezone(df: pd.DataFrame, tz: pytz.timezone = TIMEZONE_EUROPE_BERLIN) -> pd.DataFrame:
    result = df.copy()
    if result["timestamp"].dt.tz is None:
        result["timestamp"] = result["timestamp"].dt.tz_localize(pytz.UTC)
    result["timestamp_local"] = result["timestamp"].dt.tz_convert(tz)
    return result

