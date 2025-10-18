# Boerse Stuttgart Charting Tools

Dieses Repository enthaelt zwei Anwendungen, die auf denselben Analysebausteinen aufbauen und interaktive Charts fuer Boerse-Stuttgart-Instrumente bereitstellen.

## Gemeinsamer Kern

Das Paket [`stuttgart_charts`](stuttgart_charts/) stellt das Daten- und Analysefundament dar. Es laedt die kuratierte Watchlist, reichert Kursreihen um Indikatoren an und erzeugt Plotly-Visualisierungen fuer beide Frontends.

## Windows Desktop App

[`windows_app/`](windows_app/) enthaelt die PySide6-basierte Desktop-Oberflaeche.

- Gemeinsame Watchlist mit Cluster- und Trigger-Hinweisen
- Suche nach weiteren Instrumenten, Speicherung in `%USERPROFILE%/.boerse_stuttgart_charts/custom_watchlist.json`
- SMA/EMA-Overlays, Bollinger-Baender, RSI, MACD und ORB-Berechnung konfigurierbar
- Plotly-Charts im eingebetteten WebView

### Start

```bash
pip install -r requirements.txt
python windows_app/main.py
```

### Exe bauen

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
pyinstaller --noconfirm windows_app/boerse_stuttgart_chart.spec
```

Die erzeugte Anwendung liegt anschliessend unter `dist/BoerseStuttgartCharts/BoerseStuttgartCharts.exe`.

## Dash Web App

[`web_app/`](web_app/) liefert das Dash-Frontend, das sich auf Codespaces, Render, Railway und aehnlichen Plattformen deployen laesst.

- Teilt sich die Watchlist mit der Desktop-Version
- Identische Indikator-Optionen
- Plotly-Candlestick inklusive ORB-Markierung

### Start

```bash
pip install -r requirements.txt
python web_app/app.py
```

Standard-Port: `http://127.0.0.1:8050`. Fuer den Produktivbetrieb empfiehlt sich ein WSGI- oder ASGI-Server.

## Datenfluss

Mangels nutzbarer JSON-APIs werden Kursdaten und Suchergebnisse direkt aus dem Boerse-Stuttgart-HTML extrahiert. BeautifulSoup findet die eingebetteten Kursreihen, anschliessend normalisieren wir die Zeitstempel und ordnen sie der angeforderten Range zu. Beim Instrument-Search wird zunaechst die lokale Watchlist durchsucht, erst danach erfolgt bei Bedarf ein HTML-Scrape der Ergebnisliste.

## Tests

```bash
python -m compileall stuttgart_charts windows_app web_app
```

## CLI-Vorschau

```bash
python -m stuttgart_charts --isin DE0007030009 --range \"1 Monat\" --output charts/rheinmetall.html
```

Ohne `--output` oeffnet sich der Chart im Standardbrowser. SMA- und EMA-Perioden sowie Indikator-Toggles lassen sich wie in den Frontends steuern.
