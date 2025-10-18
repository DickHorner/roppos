"""Indicator calculations and Plotly chart construction."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, Iterable, List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .data import TIMEZONE_EUROPE_BERLIN
_TZ = TIMEZONE_EUROPE_BERLIN


@dataclass
class IndicatorSelection:
    sma_periods: Iterable[int]
    ema_periods: Iterable[int]
    bollinger_period: Optional[int]
    bollinger_std: float
    show_rsi: bool
    show_macd: bool
    show_volume: bool
    orb_minutes: int


def add_sma(df: pd.DataFrame, period: int) -> None:
    df[f"SMA_{period}"] = df["close"].rolling(window=period).mean()


def add_ema(df: pd.DataFrame, period: int) -> None:
    df[f"EMA_{period}"] = df["close"].ewm(span=period, adjust=False).mean()


def add_bollinger_bands(df: pd.DataFrame, period: int, num_std: float) -> None:
    rolling = df["close"].rolling(window=period)
    mid = rolling.mean()
    std = rolling.std(ddof=0)
    df[f"BOLL_{period}_MID"] = mid
    df[f"BOLL_{period}_UPPER"] = mid + std * num_std
    df[f"BOLL_{period}_LOWER"] = mid - std * num_std


def add_rsi(df: pd.DataFrame, period: int = 14) -> None:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    df[f"RSI_{period}"] = 100 - (100 / (1 + rs))


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_period: int = 9) -> None:
    fast_ema = df["close"].ewm(span=fast, adjust=False).mean()
    slow_ema = df["close"].ewm(span=slow, adjust=False).mean()
    macd = fast_ema - slow_ema
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    df["MACD"] = macd
    df["MACD_SIGNAL"] = signal
    df["MACD_HIST"] = macd - signal


def prepare_indicators(df: pd.DataFrame, selection: IndicatorSelection) -> pd.DataFrame:
    enriched = df.copy()
    for period in selection.sma_periods:
        if period:
            add_sma(enriched, period)
    for period in selection.ema_periods:
        if period:
            add_ema(enriched, period)
    if selection.bollinger_period:
        add_bollinger_bands(enriched, selection.bollinger_period, selection.bollinger_std)
    if selection.show_rsi:
        add_rsi(enriched)
    if selection.show_macd:
        add_macd(enriched)
    return enriched


def compute_orb(
    df: pd.DataFrame,
    minutes: int,
    session_start: time = time(9, 0),
) -> Optional[Dict[str, datetime]]:
    if df.empty:
        return None
    if "timestamp_local" not in df.columns:
        raise KeyError("timestamp_local fehlt für ORB-Berechnung")
    latest_session_day = df["timestamp_local"].dt.date.max()
    if pd.isna(latest_session_day):
        return None

    session_start_dt = TIMEZONE_EUROPE_BERLIN.localize(datetime.combine(latest_session_day, session_start))
    session_end_dt = session_start_dt + timedelta(minutes=minutes)
    mask = (df["timestamp_local"] >= session_start_dt) & (df["timestamp_local"] <= session_end_dt)
    if not mask.any():
        return None

    orb_high = df.loc[mask, "high"].max()
    orb_low = df.loc[mask, "low"].min()
    return {
        "start": session_start_dt,
        "end": session_end_dt,
        "high": orb_high,
        "low": orb_low,
    }


def build_chart(
    df: pd.DataFrame,
    selection: IndicatorSelection,
    orb_levels: Optional[Dict[str, datetime]],
    title: str,
) -> go.Figure:
    panels: List[str] = []
    if selection.show_volume:
        panels.append("volume")
    if selection.show_rsi:
        panels.append("rsi")
    if selection.show_macd:
        panels.append("macd")

    rows = 1 + len(panels)
    row_heights = [0.6] + [0.4 / max(len(panels), 1)] * len(panels)
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )

    fig.add_trace(
        go.Candlestick(
            x=df["timestamp_local"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Preis",
        ),
        row=1,
        col=1,
    )

    for period in selection.sma_periods:
        col = f"SMA_{period}"
        if col in df:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp_local"],
                    y=df[col],
                    name=col,
                    mode="lines",
                ),
                row=1,
                col=1,
            )

    for period in selection.ema_periods:
        col = f"EMA_{period}"
        if col in df:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp_local"],
                    y=df[col],
                    name=col,
                    mode="lines",
                    line=dict(dash="dash"),
                ),
                row=1,
                col=1,
            )

    if selection.bollinger_period:
        mid = f"BOLL_{selection.bollinger_period}_MID"
        upper = f"BOLL_{selection.bollinger_period}_UPPER"
        lower = f"BOLL_{selection.bollinger_period}_LOWER"
        if mid in df and upper in df and lower in df:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp_local"],
                    y=df[upper],
                    name="Bollinger Upper",
                    mode="lines",
                    line=dict(color="rgba(33,150,243,0.3)"),
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp_local"],
                    y=df[lower],
                    name="Bollinger Lower",
                    fill="tonexty",
                    mode="lines",
                    line=dict(color="rgba(33,150,243,0.3)"),
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp_local"],
                    y=df[mid],
                    name="Bollinger Mid",
                    mode="lines",
                    line=dict(color="rgba(33,150,243,0.6)", dash="dot"),
                ),
                row=1,
                col=1,
            )

    if orb_levels:
        fig.add_vrect(
            x0=orb_levels["start"],
            x1=orb_levels["end"],
            fillcolor="rgba(255, 193, 7, 0.2)",
            line_width=0,
            row=1,
            col=1,
            annotation_text="ORB",
            annotation_position="top left",
        )
        fig.add_hline(y=orb_levels["high"], line=dict(color="rgba(244, 67, 54, 0.7)", dash="dash"), row=1, col=1)
        fig.add_hline(y=orb_levels["low"], line=dict(color="rgba(76, 175, 80, 0.7)", dash="dash"), row=1, col=1)

    current_row = 2
    if selection.show_volume:
        fig.add_trace(
            go.Bar(x=df["timestamp_local"], y=df["volume"], name="Volumen", marker_color="rgba(158,158,158,0.7)"),
            row=current_row,
            col=1,
        )
        current_row += 1

    if selection.show_rsi:
        rsi_col = "RSI_14"
        if rsi_col in df:
            fig.add_trace(
                go.Scatter(x=df["timestamp_local"], y=df[rsi_col], name=rsi_col, mode="lines"),
                row=current_row,
                col=1,
            )
            fig.add_hrect(y0=30, y1=70, fillcolor="rgba(33,150,243,0.1)", line_width=0, row=current_row, col=1)
        current_row += 1 if selection.show_macd else 0

    if selection.show_macd:
        if "MACD" in df:
            fig.add_trace(
                go.Scatter(x=df["timestamp_local"], y=df["MACD"], name="MACD", mode="lines"),
                row=current_row,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp_local"],
                    y=df["MACD_SIGNAL"],
                    name="Signal",
                    mode="lines",
                    line=dict(dash="dash"),
                ),
                row=current_row,
                col=1,
            )
            fig.add_trace(
                go.Bar(
                    x=df["timestamp_local"],
                    y=df["MACD_HIST"],
                    name="Histogramm",
                    marker_color="rgba(158, 158, 158, 0.5)",
                ),
                row=current_row,
                col=1,
            )

    fig.update_layout(title=title, xaxis_rangeslider_visible=False, template="plotly_dark")

    # Snapshot banner annotation (outside trading hours)
    try:
        source = getattr(df, "attrs", {}).get("source")
        if source == "html_snapshot":
            ts = df.attrs.get("last_update")
            try:
                if ts is not None and hasattr(ts, "tz_convert"):
                    ts_local = ts.tz_convert(_TZ)
                    note = f"Snapshot (außerhalb Handelszeit) – {ts_local:%d.%m.%Y %H:%M:%S}"
                else:
                    ts_last = df["timestamp_local"] if "timestamp_local" in df.columns else None
                    if ts_last is not None and len(ts_last) > 0:
                        note = f"Snapshot (außerhalb Handelszeit) – {ts_last.iloc[-1]:%d.%m.%Y %H:%M:%S}"
                    else:
                        note = "Snapshot (außerhalb Handelszeit)"
            except Exception:
                note = "Snapshot (außerhalb Handelszeit)"

            fig.add_annotation(
                xref="paper",
                yref="paper",
                x=1.0,
                y=1.08,
                showarrow=False,
                text=note,
                align="right",
                font=dict(color="rgba(255, 193, 7, 1)", size=12),
                bgcolor="rgba(255, 193, 7, 0.15)",
                bordercolor="rgba(255, 193, 7, 0.6)",
            )
    except Exception:
        pass
    return fig
