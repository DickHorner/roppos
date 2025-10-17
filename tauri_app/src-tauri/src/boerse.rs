use std::collections::HashMap;

use anyhow::{anyhow, Context, Result};
use chrono::{DateTime, FixedOffset, TimeZone, Utc};
use chrono_tz::Europe::Berlin;
use once_cell::sync::Lazy;
use reqwest::Client;
use serde_json::Value;

use crate::models::{CandleResponse, SearchResult};

const SEARCH_ENDPOINT: &str = "https://www.boerse-stuttgart.de/api/data/instruments/search";
const INTRADAY_ENDPOINT: &str = "https://www.boerse-stuttgart.de/api/data/pricehistory/intraday";
const HISTORY_ENDPOINT: &str = "https://www.boerse-stuttgart.de/api/data/pricehistory/history";

#[derive(Clone, Copy)]
enum Endpoint {
    Intraday,
    History,
}

#[derive(Clone, Copy)]
struct RangeOption {
    range: &'static str,
    interval: &'static str,
    endpoint: Endpoint,
}

static RANGE_OPTIONS: Lazy<HashMap<&'static str, RangeOption>> = Lazy::new(|| {
    let mut map = HashMap::new();
    map.insert(
        "1 Tag",
        RangeOption {
            range: "1d",
            interval: "1m",
            endpoint: Endpoint::Intraday,
        },
    );
    map.insert(
        "5 Tage",
        RangeOption {
            range: "5d",
            interval: "5m",
            endpoint: Endpoint::Intraday,
        },
    );
    map.insert(
        "1 Monat",
        RangeOption {
            range: "1mo",
            interval: "30m",
            endpoint: Endpoint::Intraday,
        },
    );
    map.insert(
        "3 Monate",
        RangeOption {
            range: "3mo",
            interval: "1h",
            endpoint: Endpoint::Intraday,
        },
    );
    map.insert(
        "6 Monate",
        RangeOption {
            range: "6mo",
            interval: "2h",
            endpoint: Endpoint::History,
        },
    );
    map.insert(
        "1 Jahr",
        RangeOption {
            range: "1y",
            interval: "1d",
            endpoint: Endpoint::History,
        },
    );
    map.insert(
        "3 Jahre",
        RangeOption {
            range: "3y",
            interval: "1d",
            endpoint: Endpoint::History,
        },
    );
    map.insert(
        "5 Jahre",
        RangeOption {
            range: "5y",
            interval: "1d",
            endpoint: Endpoint::History,
        },
    );
    map
});

const USER_AGENT: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) TauriApp/1.0";

pub async fn search(client: &Client, query: &str, limit: usize) -> Result<Vec<SearchResult>> {
    let response = client
        .get(SEARCH_ENDPOINT)
        .query(&[("query", query), ("limit", &limit.to_string())])
        .header("User-Agent", USER_AGENT)
        .send()
        .await
        .context("HTTP-Anfrage an Börse Stuttgart fehlgeschlagen")?
        .error_for_status()
        .context("Suche lieferte HTTP-Fehler")?;

    let payload: Value = response
        .json()
        .await
        .context("Antwort der Suche konnte nicht als JSON gelesen werden")?;

    let mut results = Vec::new();
    let candidates = extract_array(payload);
    for candidate in candidates {
        if let Some(result) = parse_search_candidate(candidate) {
            results.push(result);
        }
    }
    Ok(results)
}

fn extract_array(value: Value) -> Vec<Value> {
    match value {
        Value::Array(arr) => arr,
        Value::Object(mut map) => {
            for key in [
                "items", "results", "data", "records", "chart", "values", "candles",
            ] {
                if let Some(inner) = map.remove(key) {
                    return extract_array(inner);
                }
            }
            vec![Value::Object(map)]
        }
        other => vec![other],
    }
}

fn parse_search_candidate(value: Value) -> Option<SearchResult> {
    match value {
        Value::Object(map) => {
            let name = map.get("name").or_else(|| map.get("symbol"))?;
            let identifier = map
                .get("isin")
                .or_else(|| map.get("identifier"))
                .or_else(|| map.get("wkn"))?;
            let market = map
                .get("market")
                .or_else(|| map.get("segment"))
                .and_then(|v| v.as_str().map(|s| s.to_string()));
            Some(SearchResult {
                name: name.as_str()?.to_string(),
                identifier: identifier.as_str()?.to_string(),
                market,
            })
        }
        Value::Array(arr) => {
            if arr.len() >= 2 {
                let name = arr.get(0)?.as_str()?.to_string();
                let identifier = arr.get(1)?.as_str()?.to_string();
                Some(SearchResult {
                    name,
                    identifier,
                    market: None,
                })
            } else {
                None
            }
        }
        _ => None,
    }
}

pub async fn fetch_candles(
    client: &Client,
    identifier: &str,
    range_key: &str,
) -> Result<Vec<CandleResponse>> {
    let option = RANGE_OPTIONS
        .get(range_key)
        .ok_or_else(|| anyhow!("Unbekannte Range-Auswahl: {range_key}"))?;

    let endpoint = match option.endpoint {
        Endpoint::Intraday => INTRADAY_ENDPOINT,
        Endpoint::History => HISTORY_ENDPOINT,
    };

    let response = client
        .get(endpoint)
        .query(&[
            ("isin", identifier),
            ("range", option.range),
            ("interval", option.interval),
        ])
        .header("User-Agent", USER_AGENT)
        .send()
        .await
        .context("HTTP-Anfrage für Kursdaten fehlgeschlagen")?
        .error_for_status()
        .context("Kursdatenlieferung ergab HTTP-Fehler")?;

    let payload: Value = response
        .json()
        .await
        .context("Kursdaten konnten nicht als JSON gelesen werden")?;

    let mut candles = Vec::new();
    for record in extract_array(payload) {
        if let Some(candle) = parse_candle(record) {
            candles.push(candle);
        }
    }

    if candles.is_empty() {
        return Err(anyhow!("Keine Kursdaten vom Server erhalten"));
    }

    candles.sort_by(|a, b| a.timestamp.cmp(&b.timestamp));
    Ok(candles)
}

#[derive(Clone)]
struct RawCandle {
    timestamp: DateTime<Utc>,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: Option<f64>,
}

fn parse_candle(value: Value) -> Option<CandleResponse> {
    match parse_raw_candle(value) {
        Some(raw) => Some(convert_raw_candle(raw)),
        None => None,
    }
}

fn parse_raw_candle(value: Value) -> Option<RawCandle> {
    match value {
        Value::Object(map) => {
            let timestamp_value = map
                .get("timestamp")
                .or_else(|| map.get("time"))
                .or_else(|| map.get("date"))?;
            let timestamp = parse_timestamp(timestamp_value)?;
            let open = map.get("open").or_else(|| map.get("o"))?.as_f64()?;
            let high = map.get("high").or_else(|| map.get("h"))?.as_f64()?;
            let low = map.get("low").or_else(|| map.get("l"))?.as_f64()?;
            let close = map.get("close").or_else(|| map.get("c"))?.as_f64()?;
            let volume = map
                .get("volume")
                .or_else(|| map.get("v"))
                .and_then(|v| v.as_f64());
            Some(RawCandle {
                timestamp,
                open,
                high,
                low,
                close,
                volume,
            })
        }
        Value::Array(arr) => {
            if arr.len() < 5 {
                return None;
            }
            let timestamp = parse_timestamp(&arr[0])?;
            let open = arr.get(1)?.as_f64()?;
            let high = arr.get(2)?.as_f64()?;
            let low = arr.get(3)?.as_f64()?;
            let close = arr.get(4)?.as_f64()?;
            let volume = arr.get(5).and_then(|v| v.as_f64());
            Some(RawCandle {
                timestamp,
                open,
                high,
                low,
                close,
                volume,
            })
        }
        _ => None,
    }
}

fn parse_timestamp(value: &Value) -> Option<DateTime<Utc>> {
    match value {
        Value::String(text) => parse_timestamp_str(text),
        Value::Number(num) => {
            if let Some(n) = num.as_i64() {
                if n > 10_000_000_000 {
                    DateTime::<Utc>::from_timestamp_millis(n)
                } else {
                    DateTime::<Utc>::from_timestamp(n, 0)
                }
            } else if let Some(n) = num.as_f64() {
                let millis = (n * 1000.0).round() as i64;
                DateTime::<Utc>::from_timestamp_millis(millis)
            } else {
                None
            }
        }
        _ => None,
    }
}

fn parse_timestamp_str(text: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(text)
        .map(|dt| dt.with_timezone(&Utc))
        .ok()
        .or_else(|| {
            DateTime::parse_from_str(text, "%Y-%m-%d %H:%M:%S")
                .ok()
                .map(|dt| dt.with_timezone(&Utc))
        })
        .or_else(|| {
            DateTime::parse_from_str(text, "%d.%m.%Y %H:%M:%S")
                .ok()
                .map(|dt| dt.with_timezone(&Utc))
        })
}

fn convert_raw_candle(raw: RawCandle) -> CandleResponse {
    let utc_offset = FixedOffset::east_opt(0).expect("UTC offset available");
    let ts_utc = raw.timestamp.with_timezone(&utc_offset);
    let local_dt = raw.timestamp.with_timezone(&Berlin);
    let ts_local = local_dt.with_timezone(&local_dt.offset().fix());
    CandleResponse {
        timestamp: ts_utc,
        timestamp_local: ts_local,
        open: raw.open,
        high: raw.high,
        low: raw.low,
        close: raw.close,
        volume: raw.volume,
    }
}
