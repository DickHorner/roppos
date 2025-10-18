use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Instrument {
    #[serde(rename(deserialize = "Name", serialize = "name"), alias = "name")]
    pub name: String,
    #[serde(
        rename(deserialize = "Identifier", serialize = "identifier"),
        alias = "identifier"
    )]
    pub identifier: String,
    #[serde(
        rename(deserialize = "Market", serialize = "market"),
        alias = "market",
        default
    )]
    pub market: Option<String>,
    #[serde(
        rename(deserialize = "Cluster", serialize = "cluster"),
        alias = "cluster",
        default
    )]
    pub cluster: Option<String>,
    #[serde(
        rename(deserialize = "Primary Triggers", serialize = "primary_triggers"),
        alias = "primary_triggers",
        default
    )]
    pub primary_triggers: Option<String>,
    #[serde(
        rename(deserialize = "Entry Setup", serialize = "entry_setup"),
        alias = "entry_setup",
        default
    )]
    pub entry_setup: Option<String>,
    #[serde(
        rename(deserialize = "Stop Rule", serialize = "stop_rule"),
        alias = "stop_rule",
        default
    )]
    pub stop_rule: Option<String>,
    #[serde(
        rename(deserialize = "TP/Management", serialize = "tp_management"),
        alias = "tp_management",
        default
    )]
    pub tp_management: Option<String>,
    #[serde(
        rename(deserialize = "Time Window (CEST)", serialize = "time_window"),
        alias = "time_window",
        default
    )]
    pub time_window: Option<String>,
    #[serde(
        rename(deserialize = "Notes", serialize = "notes"),
        alias = "notes",
        default
    )]
    pub notes: Option<String>,
}

impl Instrument {
    pub fn normalised(mut self) -> Self {
        self.market = self.market.filter(|v| !v.trim().is_empty());
        self.cluster = self.cluster.filter(|v| !v.trim().is_empty());
        self.primary_triggers = self.primary_triggers.filter(|v| !v.trim().is_empty());
        self.entry_setup = self.entry_setup.filter(|v| !v.trim().is_empty());
        self.stop_rule = self.stop_rule.filter(|v| !v.trim().is_empty());
        self.tp_management = self.tp_management.filter(|v| !v.trim().is_empty());
        self.time_window = self.time_window.filter(|v| !v.trim().is_empty());
        self.notes = self.notes.filter(|v| !v.trim().is_empty());
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IndicatorOptions {
    #[serde(default)]
    pub sma_periods: Vec<u32>,
    #[serde(default)]
    pub ema_periods: Vec<u32>,
    #[serde(default)]
    pub show_bollinger: bool,
    #[serde(default)]
    pub show_rsi: bool,
    #[serde(default)]
    pub show_macd: bool,
    #[serde(default)]
    pub show_volume: bool,
    #[serde(default = "default_orb_minutes")]
    pub orb_minutes: u32,
}

fn default_orb_minutes() -> u32 {
    15
}

#[derive(Debug, Clone, Serialize)]
pub struct CandleResponse {
    pub timestamp: DateTime<FixedOffset>,
    pub timestamp_local: DateTime<FixedOffset>,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct IndicatorSeries {
    pub name: String,
    pub values: Vec<Option<f64>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BollingerSeries {
    pub upper: Vec<Option<f64>>,
    pub lower: Vec<Option<f64>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MacdSeries {
    pub macd: Vec<Option<f64>>,
    pub signal: Vec<Option<f64>>,
    pub histogram: Vec<Option<f64>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrbLevels {
    pub start_local: DateTime<FixedOffset>,
    pub end_local: DateTime<FixedOffset>,
    pub high: f64,
    pub low: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ChartResponse {
    pub candles: Vec<CandleResponse>,
    pub sma: Vec<IndicatorSeries>,
    pub ema: Vec<IndicatorSeries>,
    pub bollinger: Option<BollingerSeries>,
    pub rsi: Option<Vec<Option<f64>>>,
    pub macd: Option<MacdSeries>,
    pub volume: Option<Vec<Option<f64>>>,
    pub orb: Option<OrbLevels>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub name: String,
    pub identifier: String,
    #[serde(default)]
    pub market: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FetchChartRequest {
    pub identifier: String,
    pub name: String,
    #[serde(rename = "rangeKey")]
    pub range_key: String,
    pub indicators: IndicatorOptions,
}
