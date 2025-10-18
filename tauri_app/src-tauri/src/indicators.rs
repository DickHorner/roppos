use anyhow::Result;
use chrono::{Duration, NaiveTime};

use crate::models::{
    BollingerSeries, CandleResponse, ChartResponse, IndicatorOptions, IndicatorSeries, MacdSeries,
    OrbLevels,
};

const DEFAULT_BOLLINGER_PERIOD: usize = 20;
const DEFAULT_BOLLINGER_STD: f64 = 2.0;
const RSI_PERIOD: usize = 14;
const MACD_FAST: usize = 12;
const MACD_SLOW: usize = 26;
const MACD_SIGNAL: usize = 9;

pub fn build_chart_response(
    candles: Vec<CandleResponse>,
    options: &IndicatorOptions,
) -> Result<ChartResponse> {
    let closes: Vec<f64> = candles.iter().map(|c| c.close).collect();

    let mut sma_series = Vec::new();
    for &period in &options.sma_periods {
        if period > 1 {
            sma_series.push(IndicatorSeries {
                name: format!("SMA {period}"),
                values: simple_moving_average(&closes, period as usize),
            });
        }
    }

    let mut ema_series = Vec::new();
    for &period in &options.ema_periods {
        if period > 1 {
            ema_series.push(IndicatorSeries {
                name: format!("EMA {period}"),
                values: exponential_moving_average(&closes, period as usize),
            });
        }
    }

    let bollinger = if options.show_bollinger {
        let (upper, lower) =
            bollinger_bands(&closes, DEFAULT_BOLLINGER_PERIOD, DEFAULT_BOLLINGER_STD);
        Some(BollingerSeries { upper, lower })
    } else {
        None
    };

    let rsi = if options.show_rsi {
        Some(relative_strength_index(&closes, RSI_PERIOD))
    } else {
        None
    };

    let macd = if options.show_macd {
        Some(macd(&closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL))
    } else {
        None
    };

    let volume = if options.show_volume {
        Some(candles.iter().map(|c| c.volume).collect::<Vec<_>>())
    } else {
        None
    };

    let orb = compute_opening_range(&candles, options.orb_minutes as i64);

    Ok(ChartResponse {
        candles,
        sma: sma_series,
        ema: ema_series,
        bollinger,
        rsi,
        macd,
        volume,
        orb,
    })
}

fn simple_moving_average(values: &[f64], period: usize) -> Vec<Option<f64>> {
    if period == 0 || period > values.len() {
        return vec![None; values.len()];
    }
    let mut result = vec![None; values.len()];
    let mut sum = 0.0;
    for i in 0..values.len() {
        sum += values[i];
        if i >= period {
            sum -= values[i - period];
        }
        if i + 1 >= period {
            result[i] = Some(sum / period as f64);
        }
    }
    result
}

fn exponential_moving_average(values: &[f64], period: usize) -> Vec<Option<f64>> {
    if period == 0 || values.is_empty() {
        return vec![None; values.len()];
    }
    let mut result = vec![None; values.len()];
    let multiplier = 2.0 / (period as f64 + 1.0);
    let mut ema = values[0];
    for i in 0..values.len() {
        if i == 0 {
            ema = values[0];
        } else {
            ema = (values[i] - ema) * multiplier + ema;
        }
        if i + 1 >= period {
            result[i] = Some(ema);
        }
    }
    result
}

fn bollinger_bands(
    values: &[f64],
    period: usize,
    std_factor: f64,
) -> (Vec<Option<f64>>, Vec<Option<f64>>) {
    if period == 0 || period > values.len() {
        return (vec![None; values.len()], vec![None; values.len()]);
    }
    let mut upper = vec![None; values.len()];
    let mut lower = vec![None; values.len()];
    for i in (period - 1)..values.len() {
        let window = &values[i + 1 - period..=i];
        let mean: f64 = window.iter().sum::<f64>() / period as f64;
        let variance = window
            .iter()
            .map(|price| {
                let diff = price - mean;
                diff * diff
            })
            .sum::<f64>()
            / period as f64;
        let std_dev = variance.sqrt();
        upper[i] = Some(mean + std_factor * std_dev);
        lower[i] = Some(mean - std_factor * std_dev);
    }
    (upper, lower)
}

fn relative_strength_index(values: &[f64], period: usize) -> Vec<Option<f64>> {
    if values.len() < 2 {
        return vec![None; values.len()];
    }
    let mut rsi = vec![None; values.len()];
    let mut gains = 0.0;
    let mut losses = 0.0;
    for i in 1..=period.min(values.len() - 1) {
        let change = values[i] - values[i - 1];
        if change >= 0.0 {
            gains += change;
        } else {
            losses -= change;
        }
    }
    let mut avg_gain = gains / period as f64;
    let mut avg_loss = losses / period as f64;
    for i in period..values.len() {
        if i > period {
            let change = values[i] - values[i - 1];
            if change >= 0.0 {
                avg_gain = (avg_gain * (period as f64 - 1.0) + change) / period as f64;
                avg_loss = (avg_loss * (period as f64 - 1.0)) / period as f64;
            } else {
                avg_gain = (avg_gain * (period as f64 - 1.0)) / period as f64;
                avg_loss = (avg_loss * (period as f64 - 1.0) - change) / period as f64;
            }
        }
        if avg_loss == 0.0 {
            rsi[i] = Some(100.0);
        } else {
            let rs = avg_gain / avg_loss;
            rsi[i] = Some(100.0 - (100.0 / (1.0 + rs)));
        }
    }
    rsi
}

fn macd(values: &[f64], fast: usize, slow: usize, signal_period: usize) -> MacdSeries {
    let fast_ema = exponential_moving_average(values, fast);
    let slow_ema = exponential_moving_average(values, slow);
    let mut macd_line = vec![None; values.len()];
    for i in 0..values.len() {
        if let (Some(fast_val), Some(slow_val)) = (fast_ema[i], slow_ema[i]) {
            macd_line[i] = Some(fast_val - slow_val);
        }
    }
    let macd_values: Vec<f64> = macd_line.iter().map(|value| value.unwrap_or(0.0)).collect();
    let signal_line = exponential_moving_average(&macd_values, signal_period);
    let mut histogram = vec![None; values.len()];
    for i in 0..values.len() {
        if let (Some(macd_val), Some(signal_val)) = (macd_line[i], signal_line[i]) {
            histogram[i] = Some(macd_val - signal_val);
        }
    }
    MacdSeries {
        macd: macd_line,
        signal: signal_line,
        histogram,
    }
}

fn compute_opening_range(candles: &[CandleResponse], minutes: i64) -> Option<OrbLevels> {
    if candles.is_empty() {
        return None;
    }
    let last = candles.last()?;
    let date = last.timestamp_local.date_naive();
    let offset = last.timestamp_local.offset().clone();
    let start_time = NaiveTime::from_hms_opt(9, 0, 0)?;
    let start = offset
        .from_local_datetime(&date.and_time(start_time)?)
        .single()?;
    let end = start + Duration::minutes(minutes);
    let mut high = f64::MIN;
    let mut low = f64::MAX;
    let mut found = false;
    for candle in candles {
        if candle.timestamp_local < start || candle.timestamp_local > end {
            continue;
        }
        high = high.max(candle.high);
        low = low.min(candle.low);
        found = true;
    }
    if !found {
        return None;
    }
    Some(OrbLevels {
        start_local: start,
        end_local: end,
        high,
        low,
    })
}
