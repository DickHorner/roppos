const { invoke } = window.__TAURI__;

const instrumentSelect = document.querySelector('#instrument-select');
const rangeSelect = document.querySelector('#range-select');
const searchInput = document.querySelector('#search-input');
const searchButton = document.querySelector('#search-button');
const searchResults = document.querySelector('#search-results');
const addToWatchlistButton = document.querySelector('#add-to-watchlist');
const statusEl = document.querySelector('#status');
const chartTitle = document.querySelector('#chart-title');
const detailsTableBody = document.querySelector('#details-table tbody');

let watchlist = [];
let lastInstrument = null;

function getCheckedValues(selector) {
  return Array.from(document.querySelectorAll(selector))
    .filter((input) => input.checked)
    .map((input) => Number.parseInt(input.value, 10))
    .filter((val) => !Number.isNaN(val));
}

function getIndicatorOptions() {
  return {
    smaPeriods: getCheckedValues('.sma-checkbox'),
    emaPeriods: getCheckedValues('.ema-checkbox'),
    showBollinger: document.querySelector('#bollinger-toggle').checked,
    showRsi: document.querySelector('#rsi-toggle').checked,
    showMacd: document.querySelector('#macd-toggle').checked,
    showVolume: document.querySelector('#volume-toggle').checked,
    orbMinutes: Number.parseInt(document.querySelector('#orb-minutes').value, 10) || 15,
  };
}

function renderWatchlist() {
  instrumentSelect.innerHTML = '';
  watchlist.forEach((item, idx) => {
    const option = document.createElement('option');
    option.value = idx;
    option.textContent = `${item.name} (${item.identifier})`;
    instrumentSelect.appendChild(option);
  });
  if (watchlist.length > 0) {
    instrumentSelect.selectedIndex = 0;
    applyInstrument(watchlist[0]);
  }
}

function updateDetails(instrument) {
  detailsTableBody.innerHTML = '';
  if (!instrument) {
    return;
  }
  const row = document.createElement('tr');
  const cells = [
    instrument.cluster,
    instrument.primary_triggers,
    instrument.entry_setup,
    instrument.stop_rule,
    instrument.tp_management,
    instrument.time_window,
    instrument.notes,
  ];
  cells.forEach((value) => {
    const cell = document.createElement('td');
    cell.textContent = value || '';
    row.appendChild(cell);
  });
  detailsTableBody.appendChild(row);
}

function showStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? '#ff6b6b' : '#94d2ff';
}

function handleSearchResults(results) {
  searchResults.innerHTML = '';
  if (!results || results.length === 0) {
    const empty = document.createElement('li');
    empty.textContent = 'Keine Treffer';
    empty.classList.add('empty');
    searchResults.appendChild(empty);
    return;
  }
  results.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = `${item.name} (${item.identifier}) – ${item.market || ''}`;
    li.addEventListener('click', () => {
      addOrReplaceInstrument(item);
      searchResults.innerHTML = '';
    });
    searchResults.appendChild(li);
  });
}

function addOrReplaceInstrument(instrument) {
  const existingIndex = watchlist.findIndex((item) => item.identifier === instrument.identifier);
  if (existingIndex >= 0) {
    watchlist[existingIndex] = instrument;
    instrumentSelect.selectedIndex = existingIndex;
  } else {
    watchlist.push(instrument);
    renderWatchlist();
    instrumentSelect.selectedIndex = watchlist.length - 1;
  }
  applyInstrument(instrument);
}

async function addInstrumentToWatchlist() {
  if (!lastInstrument) {
    showStatus('Kein Instrument ausgewählt', true);
    return;
  }
  try {
    await invoke('add_to_watchlist', { instrument: lastInstrument });
    showStatus('Instrument dauerhaft gespeichert.');
  } catch (error) {
    console.error(error);
    showStatus('Konnte Watchlist nicht speichern.', true);
  }
}

async function fetchChart(instrument) {
  if (!instrument) {
    return;
  }
  showStatus('Lade Daten …');
  try {
    const indicators = getIndicatorOptions();
    const data = await invoke('fetch_chart_data', {
      request: {
        identifier: instrument.identifier,
        name: instrument.name,
        rangeKey: rangeSelect.value,
        indicators,
      },
    });
    renderChart(instrument, data, indicators);
    showStatus('Daten aktualisiert');
  } catch (error) {
    console.error(error);
    showStatus('Fehler beim Laden der Kursdaten.', true);
  }
}

function renderChart(instrument, data, indicators) {
  chartTitle.textContent = `${instrument.name} (${instrument.identifier})`;
  lastInstrument = instrument;
  updateDetails(instrument);
  const x = data.candles.map((candle) => candle.timestamp_local);
  const candleTrace = {
    x,
    open: data.candles.map((c) => c.open),
    high: data.candles.map((c) => c.high),
    low: data.candles.map((c) => c.low),
    close: data.candles.map((c) => c.close),
    type: 'candlestick',
    name: 'Preis',
    xaxis: 'x',
    yaxis: 'y',
  };

  const traces = [candleTrace];

  data.sma.forEach((series) => {
    traces.push({
      x,
      y: series.values,
      type: 'scatter',
      mode: 'lines',
      name: series.name,
      xaxis: 'x',
      yaxis: 'y',
    });
  });

  data.ema.forEach((series) => {
    traces.push({
      x,
      y: series.values,
      type: 'scatter',
      mode: 'lines',
      name: series.name,
      line: { dash: 'dash' },
      xaxis: 'x',
      yaxis: 'y',
    });
  });

  if (data.bollinger) {
    traces.push({
      x,
      y: data.bollinger.upper,
      type: 'scatter',
      mode: 'lines',
      name: 'Bollinger Upper',
      line: { color: 'rgba(33,150,243,0.3)' },
      xaxis: 'x',
      yaxis: 'y',
    });
    traces.push({
      x,
      y: data.bollinger.lower,
      type: 'scatter',
      mode: 'lines',
      fill: 'tonexty',
      name: 'Bollinger Lower',
      line: { color: 'rgba(33,150,243,0.3)' },
      xaxis: 'x',
      yaxis: 'y',
    });
  }

  const layout = {
    template: 'plotly_dark',
    xaxis: { rangemode: 'tozero', title: 'Zeit' },
    yaxis: { title: 'Preis' },
    margin: { t: 32, r: 24, b: 48, l: 48 },
    dragmode: 'pan',
    legend: { orientation: 'h' },
    height: indicators.showRsi || indicators.showMacd || indicators.showVolume ? 820 : 640,
  };

  const rows = [1];
  const specs = [[{ type: 'candlestick' }]];
  let currentRow = 1;
  const dataTraces = [...traces];

  if (indicators.showVolume && data.volume) {
    currentRow += 1;
    layout[`xaxis${currentRow}`] = { anchor: `y${currentRow}`, matches: 'x', showgrid: false };
    layout[`yaxis${currentRow}`] = { title: 'Volumen', side: 'right' };
    specs.push([{ type: 'bar' }]);
    rows.push(currentRow);
    data.volumeTrace = {
      x,
      y: data.volume,
      type: 'bar',
      name: 'Volumen',
      xaxis: `x${currentRow}`,
      yaxis: `y${currentRow}`,
      marker: { color: '#4cc9f0' },
      opacity: 0.6,
    };
    dataTraces.push(data.volumeTrace);
  }

  if (indicators.showRsi && data.rsi) {
    currentRow += 1;
    layout[`xaxis${currentRow}`] = { anchor: `y${currentRow}`, matches: 'x', showgrid: false };
    layout[`yaxis${currentRow}`] = { title: 'RSI', range: [0, 100] };
    specs.push([{ type: 'scatter' }]);
    rows.push(currentRow);
    dataTraces.push({
      x,
      y: data.rsi,
      type: 'scatter',
      mode: 'lines',
      name: 'RSI 14',
      xaxis: `x${currentRow}`,
      yaxis: `y${currentRow}`,
    });
  }

  if (indicators.showMacd && data.macd) {
    currentRow += 1;
    layout[`xaxis${currentRow}`] = { anchor: `y${currentRow}`, matches: 'x', showgrid: false };
    layout[`yaxis${currentRow}`] = { title: 'MACD' };
    specs.push([{ type: 'scatter' }]);
    rows.push(currentRow);
    dataTraces.push({
      x,
      y: data.macd.macd,
      type: 'scatter',
      mode: 'lines',
      name: 'MACD',
      xaxis: `x${currentRow}`,
      yaxis: `y${currentRow}`,
    });
    dataTraces.push({
      x,
      y: data.macd.signal,
      type: 'scatter',
      mode: 'lines',
      name: 'Signal',
      xaxis: `x${currentRow}`,
      yaxis: `y${currentRow}`,
      line: { dash: 'dot' },
    });
    dataTraces.push({
      x,
      y: data.macd.histogram,
      type: 'bar',
      name: 'Histogramm',
      xaxis: `x${currentRow}`,
      yaxis: `y${currentRow}`,
      marker: { color: '#f1c40f' },
      opacity: 0.5,
    });
  }

  if (data.orb) {
    const orb = data.orb;
    dataTraces.push({
      x: [orb.start_local, orb.start_local],
      y: [orb.low, orb.high],
      type: 'scatter',
      mode: 'lines',
      name: `ORB (${indicators.orbMinutes}m)`,
      line: { color: '#ff6b6b', width: 2 },
      xaxis: 'x',
      yaxis: 'y',
    });
    dataTraces.push({
      x: [orb.end_local, orb.end_local],
      y: [orb.low, orb.high],
      type: 'scatter',
      mode: 'lines',
      showlegend: false,
      line: { color: '#ff6b6b', width: 2, dash: 'dot' },
      xaxis: 'x',
      yaxis: 'y',
    });
  }

  Plotly.newPlot('chart', dataTraces, layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  });
}

function applyInstrument(instrument) {
  if (!instrument) {
    return;
  }
  fetchChart(instrument);
}

instrumentSelect.addEventListener('change', () => {
  const selected = watchlist[Number.parseInt(instrumentSelect.value, 10)];
  if (selected) {
    applyInstrument(selected);
  }
});

rangeSelect.addEventListener('change', () => {
  if (lastInstrument) {
    fetchChart(lastInstrument);
  }
});

for (const checkbox of document.querySelectorAll('.sma-checkbox, .ema-checkbox, #bollinger-toggle, #rsi-toggle, #macd-toggle, #volume-toggle')) {
  checkbox.addEventListener('change', () => {
    if (lastInstrument) {
      fetchChart(lastInstrument);
    }
  });
}

document.querySelector('#orb-minutes').addEventListener('change', () => {
  if (lastInstrument) {
    fetchChart(lastInstrument);
  }
});

searchButton.addEventListener('click', async () => {
  const query = searchInput.value.trim();
  if (query.length < 2) {
    showStatus('Bitte mindestens zwei Zeichen eingeben.', true);
    return;
  }
  showStatus('Suche Instrumente …');
  try {
    const results = await invoke('search_instruments', { query, limit: 15 });
    handleSearchResults(results);
    showStatus(`${results.length} Treffer gefunden.`);
  } catch (error) {
    console.error(error);
    showStatus('Suche fehlgeschlagen.', true);
  }
});

searchInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    searchButton.click();
  }
});

addToWatchlistButton.addEventListener('click', addInstrumentToWatchlist);

async function init() {
  try {
    watchlist = await invoke('load_watchlist');
    renderWatchlist();
    showStatus('Watchlist geladen.');
  } catch (error) {
    console.error(error);
    showStatus('Konnte Watchlist nicht laden.', true);
  }
}

document.addEventListener('DOMContentLoaded', init);
