"""PySide6 desktop application for Börse Stuttgart charting."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from stuttgart_charts import (
    IndicatorSelection,
    RANGE_OPTIONS,
    compute_orb,
    enrich_with_timezone,
    fetch_boerse_history,
    load_watchlist,
    prepare_indicators,
    search_instruments,
    build_chart,
)

APP_NAME = "StuttgartCharts"


def _ensure_app_data_dir() -> Path:
    """Return a writable directory for user-specific data."""

    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"

    app_dir = base / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


CUSTOM_WATCHLIST_PATH = _ensure_app_data_dir() / "custom_watchlist.json"


class ChartingWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Börse Stuttgart Charting")
        self.resize(1400, 900)

        self.watchlist_df = self._load_watchlists()
        self._current_identifier: Optional[str] = None

        self.watchlist_widget = QListWidget()
        self.watchlist_widget.currentItemChanged.connect(self._on_watchlist_selection_changed)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Suche nach Name, ISIN oder Symbol…")
        self.search_button = QPushButton("Suchen")
        self.search_button.clicked.connect(self._on_search_clicked)

        self.search_results_widget = QListWidget()
        self.search_results_widget.setSelectionMode(QListWidget.SingleSelection)

        self.add_button = QPushButton("Zur Watchlist hinzufügen")
        self.add_button.clicked.connect(self._add_selected_search_result)

        self.range_combo = QComboBox()
        for key in RANGE_OPTIONS:
            self.range_combo.addItem(key)
        self.range_combo.setCurrentText("1 Tag")

        self.sma_input = QLineEdit("20, 50")
        self.ema_input = QLineEdit("21")

        self.bollinger_toggle = QCheckBox("Bollinger Bänder aktivieren")
        self.bollinger_toggle.setChecked(True)
        self.bollinger_period = QSpinBox()
        self.bollinger_period.setRange(5, 200)
        self.bollinger_period.setValue(20)
        self.bollinger_std = QDoubleSpinBox()
        self.bollinger_std.setRange(0.5, 5.0)
        self.bollinger_std.setSingleStep(0.1)
        self.bollinger_std.setValue(2.0)

        self.volume_checkbox = QCheckBox("Volumen anzeigen")
        self.volume_checkbox.setChecked(True)
        self.rsi_checkbox = QCheckBox("RSI anzeigen")
        self.rsi_checkbox.setChecked(True)
        self.macd_checkbox = QCheckBox("MACD anzeigen")
        self.macd_checkbox.setChecked(False)

        self.orb_minutes = QSpinBox()
        self.orb_minutes.setRange(1, 120)
        self.orb_minutes.setValue(15)

        self.refresh_button = QPushButton("Chart aktualisieren")
        self.refresh_button.clicked.connect(self._refresh_chart)

        self.chart_view = QWebEngineView()

        self._build_layout()
        self._populate_watchlist()

    def _build_layout(self) -> None:
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("Watchlist"))
        left_panel.addWidget(self.watchlist_widget, stretch=1)

        left_panel.addWidget(QLabel("Instrument hinzufügen"))
        left_panel.addWidget(self.search_input)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search_button)
        left_panel.addLayout(search_row)
        left_panel.addWidget(self.search_results_widget, stretch=1)
        left_panel.addWidget(self.add_button)

        left_container = QWidget()
        left_container.setLayout(left_panel)

        settings_layout = QFormLayout()
        settings_layout.addRow("Zeithorizont", self.range_combo)
        settings_layout.addRow("SMA Perioden", self.sma_input)
        settings_layout.addRow("EMA Perioden", self.ema_input)
        settings_layout.addRow(self.bollinger_toggle)
        settings_layout.addRow("Bollinger Periode", self.bollinger_period)
        settings_layout.addRow("Bollinger Std", self.bollinger_std)
        settings_layout.addRow(self.volume_checkbox)
        settings_layout.addRow(self.rsi_checkbox)
        settings_layout.addRow(self.macd_checkbox)
        settings_layout.addRow("ORB Minuten", self.orb_minutes)
        settings_layout.addRow(self.refresh_button)

        settings_widget = QWidget()
        settings_widget.setLayout(settings_layout)

        right_layout = QVBoxLayout()
        right_layout.addWidget(settings_widget)
        right_layout.addWidget(self.chart_view, stretch=1)
        right_container = QWidget()
        right_container.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(1, 1)

        root_layout = QHBoxLayout()
        root_layout.addWidget(splitter)
        self.setLayout(root_layout)

    def _load_watchlists(self) -> pd.DataFrame:
        base_df = load_watchlist().copy()
        base_df["Source"] = "Kern"
        custom_entries: List[dict] = []
        if CUSTOM_WATCHLIST_PATH.exists():
            try:
                custom_entries = json.loads(CUSTOM_WATCHLIST_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                QMessageBox.warning(self, "Warnung", "Benutzerdefinierte Watchlist konnte nicht gelesen werden.")
        else:
            legacy_path = Path("data/custom_watchlist.json")
            if legacy_path.exists():
                try:
                    custom_entries = json.loads(legacy_path.read_text(encoding="utf-8"))
                    CUSTOM_WATCHLIST_PATH.write_text(json.dumps(custom_entries, ensure_ascii=False, indent=2), encoding="utf-8")
                except json.JSONDecodeError:
                    QMessageBox.warning(
                        self,
                        "Warnung",
                        "Benutzerdefinierte Watchlist aus dem Legacy-Pfad konnte nicht gelesen werden.",
                    )
        if custom_entries:
            normalised = [self._normalise_entry(entry) for entry in custom_entries]
            custom_df = pd.DataFrame(normalised)
            custom_df["Source"] = "Benutzer"
            base_df = pd.concat([base_df, custom_df], ignore_index=True)
        return base_df.drop_duplicates(subset=["Identifier"]).reset_index(drop=True)

    def _populate_watchlist(self) -> None:
        self.watchlist_widget.clear()
        self.watchlist_df = (
            self.watchlist_df.dropna(subset=["Identifier"])
            .drop_duplicates(subset=["Identifier"], keep="last")
            .reset_index(drop=True)
        )
        for _, row in self.watchlist_df.iterrows():
            item = QListWidgetItem(self._format_watchlist_entry(row))
            item.setData(Qt.UserRole, row.to_dict())
            self.watchlist_widget.addItem(item)
        if self.watchlist_widget.count() > 0:
            self.watchlist_widget.setCurrentRow(0)

    def _normalise_entry(self, entry: dict) -> dict:
        identifier = entry.get("Identifier") or entry.get("identifier") or entry.get("isin")
        return {
            "Name": entry.get("Name") or entry.get("name") or identifier or "Unbekannt",
            "Identifier": identifier,
            "Market": entry.get("Market") or entry.get("market") or entry.get("MIC") or "",
        }

    def _format_watchlist_entry(self, row: pd.Series) -> str:
        name = row.get("Name") or row.get("name") or "Unbekannt"
        identifier = row.get("Identifier") or row.get("identifier") or row.get("isin")
        market = row.get("Market") or row.get("market") or ""
        label = f"{name} ({identifier})"
        if market:
            label += f" - {market}"
        if row.get("Source") == "Benutzer":
            label += " *"
        return label

    def _on_watchlist_selection_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        data = current.data(Qt.UserRole)
        self._current_identifier = data.get("Identifier") or data.get("identifier") or data.get("isin")
        self._refresh_chart()

    def _parse_periods(self, text: str) -> List[int]:
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

    def _build_selection(self) -> IndicatorSelection:
        sma_periods = self._parse_periods(self.sma_input.text())
        ema_periods = self._parse_periods(self.ema_input.text())
        bollinger_period = self.bollinger_period.value() if self.bollinger_toggle.isChecked() else None
        selection = IndicatorSelection(
            sma_periods=sma_periods,
            ema_periods=ema_periods,
            bollinger_period=bollinger_period,
            bollinger_std=self.bollinger_std.value(),
            show_rsi=self.rsi_checkbox.isChecked(),
            show_macd=self.macd_checkbox.isChecked(),
            show_volume=self.volume_checkbox.isChecked(),
            orb_minutes=self.orb_minutes.value(),
        )
        return selection

    def _refresh_chart(self) -> None:
        if not self._current_identifier:
            return
        selection = self._build_selection()
        identifier = self._current_identifier
        range_choice = self.range_combo.currentText()
        try:
            df = fetch_boerse_history(identifier, range_choice)
            df = enrich_with_timezone(df)
            df = prepare_indicators(df, selection)
            orb_levels = compute_orb(df, selection.orb_minutes)
            title = f"{identifier} - {range_choice}"
            fig = build_chart(df, selection, orb_levels, title)
            html = fig.to_html(include_plotlyjs="cdn", full_html=False)
            self.chart_view.setHtml(html)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Fehler", f"Chart konnte nicht geladen werden: {exc}")

    def _on_search_clicked(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.information(self, "Hinweis", "Bitte einen Suchbegriff eingeben.")
            return
        try:
            df = search_instruments(query)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Fehler", f"Suche fehlgeschlagen: {exc}")
            return
        self.search_results_widget.clear()
        if df.empty:
            self.search_results_widget.addItem("Keine Treffer")
            return
        for _, row in df.iterrows():
            identifier = row.get("isin") or row.get("Identifier") or row.get("identifier")
            if not identifier:
                continue
            name = row.get("name") or row.get("Name") or identifier
            market = row.get("market") or row.get("Market") or row.get("MIC") or ""
            item = QListWidgetItem(f"{name} ({identifier}) {market}")
            item.setData(Qt.UserRole, {"Name": name, "Identifier": identifier, "Market": market})
            self.search_results_widget.addItem(item)

    def _add_selected_search_result(self) -> None:
        item = self.search_results_widget.currentItem()
        if not item:
            QMessageBox.information(self, "Hinweis", "Bitte ein Suchergebnis auswählen.")
            return
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        normalised = self._normalise_entry(data)
        identifier = normalised.get("Identifier")
        if not identifier:
            QMessageBox.warning(self, "Warnung", "Keine gültige ISIN im Suchergebnis gefunden.")
            return
        if identifier in self.watchlist_df["Identifier"].values:
            QMessageBox.information(self, "Hinweis", "Instrument ist bereits in der Watchlist.")
            return
        normalised["Source"] = "Benutzer"
        self.watchlist_df = pd.concat([self.watchlist_df, pd.DataFrame([normalised])], ignore_index=True)
        self._persist_custom_entry(normalised)
        self._populate_watchlist()

    def _persist_custom_entry(self, entry: dict) -> None:
        existing: List[dict] = []
        if CUSTOM_WATCHLIST_PATH.exists():
            try:
                existing = json.loads(CUSTOM_WATCHLIST_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = []
        identifier = entry.get("Identifier")
        if not identifier:
            return
        existing_identifiers = {item.get("Identifier") for item in existing}
        if identifier not in existing_identifiers:
            existing.append(entry)
            CUSTOM_WATCHLIST_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    app = QApplication(sys.argv)
    window = ChartingWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
