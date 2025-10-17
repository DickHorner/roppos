# Börse Stuttgart Charting Tools

Dieses Repository enthält zwei eigenständige Anwendungen, die auf den gleichen Analysemodulen aufbauen und umfangreiche, konfigurierbare Charts für Börse-Stuttgart-Instrumente bereitstellen.

## 📦 Gemeinsame Basis

Die Logik zum Laden der Watchlist, Abrufen der Marktdaten, Berechnen von Indikatoren und Erstellen der Plotly-Charts befindet sich im Paket [`stuttgart_charts`](stuttgart_charts/). Beide Frontends greifen darauf zurück, wodurch Erweiterungen an einem zentralen Ort vorgenommen werden können.

## 🖥️ Windows-Desktop-App

Der Ordner [`windows_app/`](windows_app/) enthält eine PySide6-Anwendung, die lokal unter Windows (und auch anderen Desktop-Plattformen) läuft. Funktionen:

- Vor-konfigurierte Watchlist mit Cluster-/Trigger-Informationen
- Suche nach zusätzlichen Instrumenten und Persistieren in einer benutzerspezifischen Datei (z. B. `%APPDATA%/StuttgartCharts/custom_watchlist.json` unter Windows)
- Frei konfigurierbare SMA/EMA-Overlays, Bollinger-Bänder, RSI, MACD sowie ORB-Berechnung
- Interaktive Plotly-Charts im eingebetteten WebView

### Starten der Desktop-App

```bash
pip install -r requirements.txt
python windows_app/main.py
```

### Windows-Installer (.exe) erstellen

Für eine wirklich niederschwellige Installation ohne vorab eingerichtete Python-Umgebung kann aus dem Quellcode ein ausführbares Paket gebaut werden. Dazu wird [`PyInstaller`](https://pyinstaller.org/) benötigt:

```powershell
python -m pip install -r requirements.txt pyinstaller
pyinstaller windows_app/build_exe.spec
```

Der gebaute Ordner `dist/StuttgartCharts/` enthält `StuttgartCharts.exe` inklusive aller Abhängigkeiten. Dieser Ordner kann als ZIP archiviert oder direkt auf andere Windows-Rechner kopiert werden.

## 🌐 Dash-Webanwendung

Im Ordner [`web_app/`](web_app/) befindet sich eine Dash-Anwendung, die sich ohne Streamlit betreiben und beispielsweise auf GitHub Codespaces, Render, Railway oder anderen Hosting-Umgebungen deployen lässt. Highlights:

- Gemeinsame Watchlist mit der Desktop-App, inkl. Möglichkeit zum Ergänzen neuer Werte
- Umfangreiche Indikator-Konfiguration analog zur Desktop-Version
- Plotly-Candlestick-Visualisierung samt ORB-Markierung

### Starten der Web-App

```bash
pip install -r requirements.txt
python web_app/app.py
```

Der Server lauscht standardmäßig auf `http://127.0.0.1:8050` und kann für den Produktionseinsatz über WSGI/ASGI-Wrapper bereitgestellt werden.

## 📊 Datenbasis

Die Datei [`data/watchlist.csv`](data/watchlist.csv) enthält die kuratierte Liste an Instrumenten samt Trading-Setup-Metadaten. Ergänzungen über die Frontends werden benutzerspezifisch abgelegt (unter Windows beispielsweise in `%APPDATA%/StuttgartCharts/custom_watchlist.json`).

## ✅ Tests

Zum schnellen Syntax-Check kann das Projekt kompiliert werden:

```bash
python -m compileall stuttgart_charts windows_app web_app
```

Weitere Tests (Unit- oder Integrationstests) können bei Bedarf ergänzt werden.
