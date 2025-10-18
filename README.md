# Börse Stuttgart Charting Tools

Dieses Repository enthält zwei eigenständige Anwendungen, die auf den gleichen Analysemodulen aufbauen und umfangreiche, konfigurierbare Charts für Börse-Stuttgart-Instrumente bereitstellen.

## 📦 Gemeinsame Basis

Die Logik zum Laden der Watchlist, Abrufen der Marktdaten, Berechnen von Indikatoren und Erstellen der Plotly-Charts befindet sich im Paket [`stuttgart_charts`](stuttgart_charts/). Beide Frontends greifen darauf zurück, wodurch Erweiterungen an einem zentralen Ort vorgenommen werden können.

## 🖥️ Windows-Desktop-App

Der Ordner [`windows_app/`](windows_app/) enthält eine PySide6-Anwendung, die lokal unter Windows (und auch anderen Desktop-Plattformen) läuft. Funktionen:

- Vor-konfigurierte Watchlist mit Cluster-/Trigger-Informationen
- Suche nach zusätzlichen Instrumenten und Persistieren in `%USERPROFILE%/.boerse_stuttgart_charts/custom_watchlist.json`
- Frei konfigurierbare SMA/EMA-Overlays, Bollinger-Bänder, RSI, MACD sowie ORB-Berechnung
- Interaktive Plotly-Charts im eingebetteten WebView

### Starten der Desktop-App

```bash
pip install -r requirements.txt
python windows_app/main.py
```

### Erstellen einer Windows-Exe

Für eine ausführbare Datei, die ohne lokale Python-Installation funktioniert, steht eine vorbereitete PyInstaller-Spec zur Verfügung:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
pyinstaller --noconfirm windows_app/boerse_stuttgart_chart.spec
```

Die fertige Anwendung liegt anschließend unter `dist/BoerseStuttgartCharts/BoerseStuttgartCharts.exe` und kann direkt weitergegeben werden. Beim ersten Start werden benutzerbezogene Einstellungen (z. B. zusätzliche Watchlist-Einträge) unter `%USERPROFILE%/.boerse_stuttgart_charts/` abgelegt.

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

Die Datei [`data/watchlist.csv`](data/watchlist.csv) enthält die kuratierte Liste an Instrumenten samt Trading-Setup-Metadaten. Ergänzungen über die Frontends werden pro Benutzer in `%USERPROFILE%/.boerse_stuttgart_charts/custom_watchlist.json` persistiert.

## ✅ Tests

Zum schnellen Syntax-Check kann das Projekt kompiliert werden:

```bash
python -m compileall stuttgart_charts windows_app web_app
```

Weitere Tests (Unit- oder Integrationstests) können bei Bedarf ergänzt werden.

## ⚙️ Schnelle Vorschau aus der Konsole

Für eine schnelle Sichtprüfung ohne GUI kann das Kernpaket direkt als Modul
ausgeführt werden. Dabei wird ein Plotly-Chart erzeugt, der entweder im Browser
geöffnet oder als HTML-Datei gespeichert wird:

```bash
python -m stuttgart_charts --isin DE0007030009 --range "1 Monat" --output charts/rheinmetall.html
```

Ohne `--output` öffnet sich der Chart unmittelbar im Standardbrowser. Über
Parameter wie `--sma 10 20 50`, `--ema 12 26`, `--no-rsi`, `--no-macd` oder
`--orb-minutes 30` lassen sich die Indikatoren analog zu den Frontends
konfigurieren.
