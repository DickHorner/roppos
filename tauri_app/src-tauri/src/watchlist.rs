use std::fs;
use std::io::Cursor;
use std::path::PathBuf;

use anyhow::{anyhow, Context, Result};
use csv::ReaderBuilder;
use serde_json::Value;
use tauri::api::path::home_dir;
use tauri::AppHandle;

use crate::models::Instrument;

const DEFAULT_WATCHLIST: &str = include_str!("../../../data/watchlist.csv");
const STATE_DIR_NAME: &str = ".boerse_stuttgart_charts";
const USER_FILENAME: &str = "custom_watchlist.json";

pub fn load_default_watchlist() -> Result<Vec<Instrument>> {
    let cursor = Cursor::new(DEFAULT_WATCHLIST.as_bytes());
    let mut reader = ReaderBuilder::new().has_headers(true).from_reader(cursor);
    let mut instruments = Vec::new();
    for record in reader.deserialize::<Instrument>() {
        let instrument = record.map(|inst| inst.normalised())?;
        instruments.push(instrument);
    }
    Ok(instruments)
}

pub fn ensure_watchlist_dir(_handle: &AppHandle) -> Result<PathBuf> {
    let home = home_dir().ok_or_else(|| anyhow!("Konnte Benutzerverzeichnis nicht bestimmen"))?;
    let watchlist_dir = home.join(STATE_DIR_NAME);
    fs::create_dir_all(&watchlist_dir)
        .with_context(|| format!("Kann Verzeichnis {:?} nicht anlegen", watchlist_dir))?;
    Ok(watchlist_dir)
}

fn user_watchlist_path(handle: &AppHandle) -> Result<PathBuf> {
    Ok(ensure_watchlist_dir(handle)?.join(USER_FILENAME))
}

pub fn load_user_watchlist(handle: &AppHandle) -> Result<Vec<Instrument>> {
    let path = user_watchlist_path(handle)?;
    if !path.exists() {
        return Ok(Vec::new());
    }
    let raw = fs::read_to_string(&path)
        .with_context(|| format!("Kann Watchlist-Datei {:?} nicht lesen", path))?;
    if raw.trim().is_empty() {
        return Ok(Vec::new());
    }
    let parsed: Vec<Value> =
        serde_json::from_str(&raw).with_context(|| format!("Ungültiges JSON in {:?}", path))?;
    let mut instruments = Vec::new();
    for entry in parsed {
        let instrument: Instrument = serde_json::from_value(entry)?;
        instruments.push(instrument.normalised());
    }
    Ok(instruments)
}

pub fn persist_instrument(handle: &AppHandle, instrument: &Instrument) -> Result<()> {
    let path = user_watchlist_path(handle)?;
    let mut existing = load_user_watchlist(handle)?;
    if existing
        .iter()
        .any(|entry| entry.identifier == instrument.identifier)
    {
        return Ok(());
    }
    existing.push(instrument.clone());
    let serialised = serde_json::to_string_pretty(&existing)?;
    fs::write(&path, serialised)
        .with_context(|| format!("Kann Watchlist-Datei {:?} nicht schreiben", path))?;
    Ok(())
}

pub fn merge_watchlists(mut base: Vec<Instrument>, mut custom: Vec<Instrument>) -> Vec<Instrument> {
    base.sort_by(|a, b| a.name.cmp(&b.name));
    custom.sort_by(|a, b| a.name.cmp(&b.name));
    for instrument in custom.into_iter() {
        if base
            .iter()
            .any(|existing| existing.identifier == instrument.identifier)
        {
            continue;
        }
        base.push(instrument);
    }
    base.sort_by(|a, b| a.name.cmp(&b.name));
    base
}
