# Börse Stuttgart Charting Tools

Dieses Repository enthält drei eigenständige Anwendungen, die umfangreiche, konfigurierbare Charts für Börse-Stuttgart-Instrumente bereitstellen. Zwei Frontends greifen auf das gemeinsame Python-Paket `stuttgart_charts` zu, während die neue Rust/Tauri-Anwendung dieselbe Funktionalität nativ implementiert.

## 📦 Gemeinsame Basis

Die Logik zum Laden der Watchlist, Abrufen der Marktdaten, Berechnen von Indikatoren und Erstellen der Plotly-Charts befindet sich für die Python-Frontends im Paket [`stuttgart_charts`](stuttgart_charts/). Der Rust-Client unter [`tauri_app/`](tauri_app/) verfügt über eine äquivalente Implementierung (HTTP-Zugriff, Indikatoren, ORB) in Rust und liefert dieselben Features innerhalb einer nativen Desktop-Shell.

## 🦀 Rust/Tauri-Desktop-App

Der Ordner [`tauri_app/`](tauri_app/) enthält eine auf Rust und Tauri basierende Anwendung, die ohne Python-Laufzeit auskommt. Highlights:

- Vor-konfigurierte Watchlist, Suche nach weiteren Instrumenten, Persistenz kompatibel zu den Python-Frontends (`~/.boerse_stuttgart_charts/custom_watchlist.json`)
- Plotly.js im Tauri-WebView mit SMA/EMA, Bollinger-Bändern, RSI, MACD, Volumen und ORB-Markierung
- Komplett native Backend-Implementierung (Reqwest + Chrono), optimiert für leichte Distribution via Tauri

### Entwicklung & Test

Voraussetzungen: aktuelles Rust-Toolchain sowie `cargo-tauri` (installierbar via `cargo install tauri-cli`). Anschließend kann die App wie folgt gestartet werden:

```bash
cd tauri_app
cargo tauri dev --manifest-path src-tauri/Cargo.toml
```

Für signierte Builds (Windows .msi/.exe, macOS `.app`, Linux `.deb/.AppImage`) genügt:

```bash
cd tauri_app
cargo tauri build --manifest-path src-tauri/Cargo.toml
```

Die gebauten Artefakte landen unter `tauri_app/src-tauri/target/release/bundle/`.

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

Die Datei [`data/watchlist.csv`](data/watchlist.csv) enthält die kuratierte Liste an Instrumenten samt Trading-Setup-Metadaten. Ergänzungen über die Frontends werden pro Benutzer in `%USERPROFILE%/.boerse_stuttgart_charts/custom_watchlist.json` (Linux/macOS: `~/.boerse_stuttgart_charts/custom_watchlist.json`) persistiert und sind zwischen den Python- und der Rust/Tauri-Anwendung austauschbar.

## ✅ Tests

Zum schnellen Syntax-Check können die Python-Komponenten kompiliert werden:

```bash
python -m compileall stuttgart_charts windows_app web_app
```

Für den Rust/Tauri-Part empfiehlt sich zusätzlich:

```bash
cargo fmt --manifest-path tauri_app/src-tauri/Cargo.toml
cargo check --manifest-path tauri_app/src-tauri/Cargo.toml
```

Weitere Tests (Unit- oder Integrationstests) können bei Bedarf ergänzt werden.
