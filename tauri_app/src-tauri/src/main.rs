mod boerse;
mod indicators;
mod models;
mod watchlist;

use std::sync::Arc;

use anyhow::Result;
use boerse::{fetch_candles, search};
use indicators::build_chart_response;
use models::{ChartResponse, FetchChartRequest, Instrument, SearchResult};
use reqwest::Client;
use tauri::State;
use tokio::sync::Mutex;
use watchlist::{
    ensure_watchlist_dir, load_default_watchlist, load_user_watchlist, merge_watchlists,
    persist_instrument,
};

struct HttpClientState {
    client: Client,
}

impl HttpClientState {
    fn new() -> Result<Self> {
        let client = Client::builder()
            .user_agent("Mozilla/5.0 (Tauri Desktop App)")
            .gzip(true)
            .brotli(true)
            .deflate(true)
            .build()?;
        Ok(Self { client })
    }
}

type SharedClient = State<'_, Arc<Mutex<HttpClientState>>>;

#[tauri::command]
async fn load_watchlist(app: tauri::AppHandle) -> Result<Vec<Instrument>, String> {
    ensure_watchlist_dir(&app).map_err(|err| err.to_string())?;
    let base = load_default_watchlist().map_err(|err| err.to_string())?;
    let custom = load_user_watchlist(&app).map_err(|err| err.to_string())?;
    Ok(merge_watchlists(base, custom))
}

#[tauri::command]
async fn add_to_watchlist(app: tauri::AppHandle, instrument: Instrument) -> Result<(), String> {
    let cleaned = instrument.normalised();
    persist_instrument(&app, &cleaned).map_err(|err| err.to_string())
}

#[tauri::command]
async fn search_instruments(
    state: SharedClient,
    query: String,
    limit: Option<u32>,
) -> Result<Vec<SearchResult>, String> {
    if query.trim().len() < 2 {
        return Err("Suchbegriff zu kurz".to_string());
    }
    let limit = limit.unwrap_or(15) as usize;
    let guard = state.inner().lock().await;
    search(&guard.client, &query, limit)
        .await
        .map_err(|err| err.to_string())
}

#[tauri::command]
async fn fetch_chart_data(
    state: SharedClient,
    request: FetchChartRequest,
) -> Result<ChartResponse, String> {
    let guard = state.inner().lock().await;
    let candles = fetch_candles(&guard.client, &request.identifier, &request.range_key)
        .await
        .map_err(|err| err.to_string())?;
    build_chart_response(candles, &request.indicators).map_err(|err| err.to_string())
}

fn main() {
    tauri::Builder::default()
        .manage(Arc::new(Mutex::new(
            HttpClientState::new().expect("HTTP-Client initialisierbar"),
        )))
        .invoke_handler(tauri::generate_handler![
            load_watchlist,
            add_to_watchlist,
            search_instruments,
            fetch_chart_data
        ])
        .run(tauri::generate_context!())
        .expect("Tauri-Anwendung konnte nicht gestartet werden");
}
