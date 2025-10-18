"""Command-line entry point for ad-hoc chart generation."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Optional

from . import data, indicators


def _parse_periods(raw: Optional[Iterable[str]]) -> List[int]:
    if not raw:
        return []
    periods: List[int] = []
    for value in raw:
        try:
            period = int(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - argparse assures strings
            raise argparse.ArgumentTypeError(f"Ungültiger Periodenwert: {value}") from exc
        if period <= 0:
            raise argparse.ArgumentTypeError("Perioden müssen größer 0 sein")
        periods.append(period)
    return periods


def build_indicator_selection(args: argparse.Namespace) -> indicators.IndicatorSelection:
    return indicators.IndicatorSelection(
        sma_periods=_parse_periods(args.sma) or [20, 50],
        ema_periods=_parse_periods(args.ema) or [12, 26],
        bollinger_period=args.bollinger_period,
        bollinger_std=args.bollinger_std,
        show_rsi=not args.no_rsi,
        show_macd=not args.no_macd,
        show_volume=not args.no_volume,
        orb_minutes=args.orb_minutes,
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m stuttgart_charts",
        description="Erzeuge interaktive Börse-Stuttgart-Charts direkt aus der Konsole.",
    )
    parser.add_argument(
        "--isin",
        required=True,
        help="ISIN des Instruments, z. B. DE0007030009",
    )
    parser.add_argument(
        "--range",
        default="5 Tage",
        choices=list(data.RANGE_OPTIONS.keys()),
        help="Zeitraum der Kursdaten (Standard: 5 Tage)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optionaler Pfad für die Ausgabe als HTML-Datei. Ohne Angabe wird der Browser geöffnet.",
    )
    parser.add_argument(
        "--sma",
        nargs="*",
        help="Eine oder mehrere Simple-Moving-Average-Perioden (Standard: 20 50)",
    )
    parser.add_argument(
        "--ema",
        nargs="*",
        help="Eine oder mehrere Exponential-Moving-Average-Perioden (Standard: 12 26)",
    )
    parser.add_argument(
        "--bollinger-period",
        type=int,
        default=20,
        help="Periode für Bollinger-Bänder (Standard: 20). 0 deaktiviert die Bänder.",
    )
    parser.add_argument(
        "--bollinger-std",
        type=float,
        default=2.0,
        help="Standardabweichungs-Faktor für Bollinger-Bänder (Standard: 2.0)",
    )
    parser.add_argument(
        "--no-rsi",
        action="store_true",
        help="RSI-Panel deaktivieren",
    )
    parser.add_argument(
        "--no-macd",
        action="store_true",
        help="MACD-Panel deaktivieren",
    )
    parser.add_argument(
        "--no-volume",
        action="store_true",
        help="Volumen-Panel deaktivieren",
    )
    parser.add_argument(
        "--orb-minutes",
        type=int,
        default=15,
        help="Anzahl Minuten für die Opening-Range-Breakout-Berechnung (Standard: 15)",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = create_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    df = data.fetch_boerse_history(args.isin, args.range)
    df = data.enrich_with_timezone(df)

    if args.bollinger_period and args.bollinger_period <= 0:
        parser.error("--bollinger-period muss größer 0 sein oder weggelassen werden")

    selection = build_indicator_selection(args)
    enriched = indicators.prepare_indicators(df, selection)
    orb = indicators.compute_orb(enriched, selection.orb_minutes)

    title = f"{args.isin} - {args.range}"
    # UI hint if we used HTML snapshot (off-hours)
    try:
        if getattr(df, "attrs", {}).get("source") == "html_snapshot":
            ts = df.attrs.get("last_update")
            if ts is not None:
                ts_local = ts.tz_convert(data.TIMEZONE_EUROPE_BERLIN)
                title += f" • Snapshot (außerhalb Handelszeit) – {ts_local:%d.%m.%Y %H:%M:%S}"
            else:
                title += " • Snapshot (außerhalb Handelszeit)"
    except Exception:
        pass
    figure = indicators.build_chart(enriched, selection, orb, title=title)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        figure.write_html(args.output, include_plotlyjs="cdn", auto_open=False)
        print(f"Chart gespeichert unter {args.output}")
    else:
        figure.show()


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
