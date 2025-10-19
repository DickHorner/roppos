"""Dash web application for Börse Stuttgart charting."""
from __future__ import annotations

from typing import Dict, List
import sys
from pathlib import Path

import dash
from dash import Dash, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

# Ensure the project root is on sys.path so the sibling
# package stuttgart_charts can be imported when this module
# is executed directly.
if not getattr(sys, "frozen", False):
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from stuttgart_charts import (
    IndicatorSelection,
    RANGE_WINDOWS,
    RANGE_OPTIONS,
    build_chart,
    compute_orb,
    enrich_with_timezone,
    fetch_boerse_history,
    load_watchlist,
    prepare_indicators,
    search_instruments,
)
from stuttgart_charts import data as _data


def _initial_watchlist() -> List[Dict]:
    df = load_watchlist()
    df["Source"] = "Kern"
    return df.to_dict("records")


def _parse_periods(text: str) -> List[int]:
    if not text:
        return []
    parts = [part.strip() for part in text.split(",") if part.strip()]
    periods: List[int] = []
    for part in parts:
        try:
            value = int(part)
            if value > 0:
                periods.append(value)
        except ValueError:
            continue
    return periods


def _normalise_entry(entry: Dict) -> Dict:
    identifier = entry.get("Identifier") or entry.get("identifier") or entry.get("isin")
    return {
        "Name": entry.get("Name") or entry.get("name") or identifier or "Unbekannt",
        "Identifier": identifier,
        "Market": entry.get("Market") or entry.get("market") or entry.get("MIC") or "",
        "Source": entry.get("Source") or "Benutzer",
    }


def _error_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False)
    fig.update_layout(template="plotly_dark", xaxis_visible=False, yaxis_visible=False)
    return fig


def _instrument_options(data: List[Dict]) -> List[Dict]:
    options = []
    for entry in data:
        identifier = entry.get("Identifier")
        if not identifier:
            continue
        name = entry.get("Name") or identifier
        market = entry.get("Market") or ""
        label = f"{name} ({identifier})"
        if market:
            label += f" - {market}"
        if entry.get("Source") == "Benutzer":
            label += " *"
        options.append({"label": label, "value": identifier})
    return options


def _find_watchlist_entry(data: List[Dict], identifier: str) -> Dict:
    for entry in data:
        if entry.get("Identifier") == identifier:
            return entry
    return {}


app: Dash = dash.Dash(__name__)
app.title = "Börse Stuttgart Charting"
app.layout = html.Div(
    [
        dcc.Store(id="watchlist-store", data=_initial_watchlist()),
        dcc.Store(id="search-results-store", data=[]),
        html.Div(
            [
                html.H1("Börse Stuttgart Charting Dashboard"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.H2("Watchlist"),
                                dcc.Dropdown(id="instrument-dropdown", placeholder="Instrument auswählen"),
                                html.Div(
                                    [
                                        html.Label("Suche"),
                                        dcc.Input(id="search-input", type="text", placeholder="Name, ISIN oder Symbol", debounce=True),
                                        html.Button("Suchen", id="search-button"),
                                        dcc.Dropdown(id="search-results-dropdown", placeholder="Suchergebnisse"),
                                        html.Button("Zur Watchlist hinzufügen", id="add-button"),
                                    ],
                                    className="search-panel",
                                    style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
                                ),
                                html.H3("Indikatoren"),
                                html.Label("Zeithorizont"),
                                dcc.Dropdown(
                                    id="range-dropdown",
                                    options=[{"label": key, "value": key} for key in RANGE_OPTIONS],
                                    value="1 Tag",
                                ),
                                html.Label("SMA Perioden"),
                                dcc.Input(id="sma-input", type="text", value="20,50"),
                                html.Label("EMA Perioden"),
                                dcc.Input(id="ema-input", type="text", value="21"),
                                dcc.Checklist(
                                    id="indicator-checklist",
                                    options=[
                                        {"label": "Volumen", "value": "volume"},
                                        {"label": "RSI", "value": "rsi"},
                                        {"label": "MACD", "value": "macd"},
                                        {"label": "Bollinger Bänder", "value": "bollinger"},
                                    ],
                                    value=["volume", "rsi", "bollinger"],
                                ),
                                html.Label("Bollinger Periode"),
                                dcc.Input(id="bollinger-period", type="number", value=20, min=5, max=200, step=1),
                                html.Label("Bollinger Std"),
                                dcc.Input(id="bollinger-std", type="number", value=2.0, min=0.5, max=5, step=0.1),
                                html.Label("ORB Minuten"),
                                dcc.Input(id="orb-input", type="number", value=15, min=1, max=120, step=1),
                            ],
                            className="sidebar",
                            style={
                                "flex": "0 0 360px",
                                "display": "flex",
                                "flexDirection": "column",
                                "gap": "0.75rem",
                            },
                        ),
                        html.Div(
                            [dcc.Graph(id="chart", figure=_error_figure("Bitte Instrument wählen."))],
                            className="content",
                            style={"flex": "1 1 auto"},
                        ),
                    ],
                    className="layout",
                    style={"display": "flex", "gap": "2rem", "alignItems": "flex-start"},
                ),
            ],
            className="container",
        ),
    ]
)


@app.callback(
    Output("search-results-store", "data"),
    Output("search-results-dropdown", "options"),
    Output("search-results-dropdown", "value"),
    Input("search-button", "n_clicks"),
    State("search-input", "value"),
    prevent_initial_call=True,
)
def search_callback(n_clicks: int, query: str):
    if not n_clicks or not query:
        raise PreventUpdate
    try:
        df = search_instruments(query)
    except Exception as exc:  # noqa: BLE001
        return [], [], None
    if df.empty:
        return [], [], None
    records = []
    options = []
    for _, row in df.iterrows():
        entry = _normalise_entry(row.to_dict())
        if not entry.get("Identifier"):
            continue
        records.append(entry)
        label = entry["Name"] + f" ({entry['Identifier']})"
        if entry["Market"]:
            label += f" - {entry['Market']}"
        options.append({"label": label, "value": entry["Identifier"]})
    value = options[0]["value"] if options else None
    return records, options, value


@app.callback(
    Output("watchlist-store", "data"),
    Input("add-button", "n_clicks"),
    State("search-results-dropdown", "value"),
    State("search-results-store", "data"),
    State("watchlist-store", "data"),
    prevent_initial_call=True,
)
def add_to_watchlist(n_clicks: int, identifier: str, search_results: List[Dict], watchlist: List[Dict]):
    if not n_clicks or not identifier:
        raise PreventUpdate
    existing_ids = {entry.get("Identifier") for entry in watchlist}
    if identifier in existing_ids:
        raise PreventUpdate
    match = next((entry for entry in search_results if entry.get("Identifier") == identifier), None)
    if not match:
        raise PreventUpdate
    return watchlist + [match]


@app.callback(
    Output("instrument-dropdown", "options"),
    Output("instrument-dropdown", "value"),
    Input("watchlist-store", "data"),
    State("instrument-dropdown", "value"),
)
def update_instrument_options(data: List[Dict], current_value: str):
    options = _instrument_options(data)
    if not options:
        return options, None
    values = {opt["value"] for opt in options}
    if current_value in values:
        return options, current_value
    return options, options[0]["value"]


@app.callback(
    Output("chart", "figure"),
    Input("instrument-dropdown", "value"),
    Input("range-dropdown", "value"),
    Input("sma-input", "value"),
    Input("ema-input", "value"),
    Input("indicator-checklist", "value"),
    Input("bollinger-period", "value"),
    Input("bollinger-std", "value"),
    Input("orb-input", "value"),
    State("watchlist-store", "data"),
)
def update_chart(
    identifier: str,
    range_value: str,
    sma_text: str,
    ema_text: str,
    indicators: List[str],
    bollinger_period: int,
    bollinger_std: float,
    orb_minutes: int,
    watchlist: List[Dict],
):
    if not identifier:
        return _error_figure("Bitte Instrument wählen.")
    selection = IndicatorSelection(
        sma_periods=_parse_periods(sma_text),
        ema_periods=_parse_periods(ema_text),
        bollinger_period=bollinger_period if "bollinger" in indicators else None,
        bollinger_std=bollinger_std or 2.0,
        show_rsi="rsi" in indicators,
        show_macd="macd" in indicators,
        show_volume="volume" in indicators,
        orb_minutes=orb_minutes or 15,
    )
    try:
        df = fetch_boerse_history(identifier, range_value)
        df = enrich_with_timezone(df)
        df = prepare_indicators(df, selection)
        orb_levels = compute_orb(df, selection.orb_minutes)
        entry = _find_watchlist_entry(watchlist, identifier)
        title = f"{entry.get('Name', identifier)} ({identifier})"
        # UI hint: snapshot outside trading hours
        try:
            if getattr(df, "attrs", {}).get("source") == "html_snapshot":
                ts = df.attrs.get("last_update")
                if ts is not None:
                    ts_local = ts.tz_convert(_data.TIMEZONE_EUROPE_BERLIN)
                    title += f" • Snapshot (außerhalb Handelszeit) – {ts_local:%d.%m.%Y %H:%M:%S}"
                else:
                    title += " • Snapshot (außerhalb Handelszeit)"
        except Exception:
            pass
        fig = build_chart(df, selection, orb_levels, title)
        return fig
    except Exception as exc:  # noqa: BLE001
        return _error_figure(str(exc))


server = app.server


if __name__ == "__main__":
    app.run(debug=True)
