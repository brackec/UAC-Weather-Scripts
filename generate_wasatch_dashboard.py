#!/usr/bin/env python3
"""
UAC Weather Dashboard Generator
================================
Fetches weather station data from the Synoptic Data API and writes a
self-contained HTML file.  Run from cron twice daily (6 AM / 6 PM).

Cron example:
  0 6,18 * * * /usr/bin/python3 /path/to/generate_dashboard.py

Outputs:   OUTPUT_PATH (single HTML file, ready to serve)
"""

import argparse
import json
import os
import requests
from datetime import datetime
from typing import List

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION  ← edit here
# ─────────────────────────────────────────────────────────────

# Synoptic Data API token (keep server-side; not exposed in the HTML)
TOKEN = "1643bf6fc1c2450b8ac5b25ff91a1fab"

# UAC forecast region label shown in the page header
REGION = "Wasatch"

# Hours of history to retrieve (48 = last 2 days)
HOURS = 48

# Station list — add Synoptic STIDs for this region
STATIONS = [
    {"id": "PCM01"},
    {"id": "C99"},
    {"id": "MLDU1"},
    {"id": "EY"},
    {"id": "SPC"},
    {"id": "ATH20"},
    {"id": "CLN"},
    {"id": "AMB"},
    {"id": "HDP"},
    {"id": "IFF"},
]

# Where to write the finished HTML file.
# Override via --output CLI arg or DASHBOARD_OUTPUT_PATH env var.
# Example cron: /usr/bin/python3 /home/user/python/scripts/generate_wasatch_dashboard.py \
#               --output /home/user/public_html/Weather/Wasatch-Weather-Stations.html
_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "Wasatch-Weather-Stations.html")
OUTPUT_PATH = os.environ.get("DASHBOARD_OUTPUT_PATH", _DEFAULT_OUTPUT)

# Absolute path to THIS script on the server, used to generate the PHP refresh helper.
# Set via --server-script-path CLI arg. If not set, no PHP file is written.
# Example: /home2/vofgesmy/python/scripts/generate_wasatch_dashboard.py
SERVER_SCRIPT_PATH = None

# ─────────────────────────────────────────────────────────────
#  DATA FETCH
# ─────────────────────────────────────────────────────────────

def fetch_stations() -> List[dict]:
    """Fetch 48 h of data for all configured stations in one API call."""
    stids   = ",".join(s["id"] for s in STATIONS)
    minutes = HOURS * 60
    url = (
        "https://api.synopticdata.com/v2/stations/timeseries"
        f"?stid={stids}"
        f"&token={TOKEN}"
        f"&recent={minutes}"
        "&vars=air_temp,wind_speed,wind_gust,wind_direction,snow_depth"
        "&obtimezone=local"
    )

    print(f"  Fetching {len(STATIONS)} stations ...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "STATION" not in data or not data["STATION"]:
        print("  WARNING: API returned no stations.")
        return []

    return data["STATION"]


def parse_stations(raw_stations: List[dict]) -> List[dict]:
    """Convert raw API results into clean dicts suitable for JSON embedding."""
    # Build a lookup by STID
    by_id = {s["STID"]: s for s in raw_stations}

    result = []
    for cfg in STATIONS:
        raw = by_id.get(cfg["id"])
        if raw is None:
            print(f"  WARNING: No data for {cfg['id']}")
            continue

        obs = raw.get("OBSERVATIONS", {})
        times = obs.get("date_time", [])

        def to_f(vals):
            return [round(c * 9/5 + 32, 2) if c is not None else None
                    for c in vals]

        def to_mph(vals):
            return [round(v * 2.23694, 2) if v is not None else None
                    for v in vals]

        def to_in(vals):
            return [round(v * 0.0393701, 2) if v is not None else None
                    for v in vals]

        raw_temp  = obs.get("air_temp_set_1",       [None]*len(times))
        raw_wind  = obs.get("wind_speed_set_1",      [None]*len(times))
        raw_gust  = obs.get("wind_gust_set_1",       [None]*len(times))
        raw_dir   = obs.get("wind_direction_set_1",  [None]*len(times))
        raw_snow  = obs.get("snow_depth_set_1",      [None]*len(times))

        result.append({
            "id":        raw["STID"],
            "name":      raw.get("NAME", cfg["id"]),
            "elevation": raw.get("ELEVATION"),          # already in feet from API
            "lat":       raw.get("LATITUDE"),
            "lon":       raw.get("LONGITUDE"),
            "times":     times,                          # ISO 8601 strings
            "temp_f":    to_f(raw_temp),
            "wind_mph":  to_mph(raw_wind),
            "gust_mph":  to_mph(raw_gust),
            "wind_dir":  raw_dir,
            "snow_in":   to_in(raw_snow),
        })

        n = len(times)
        temps_valid = sum(1 for v in raw_temp if v is not None)
        snow_valid  = sum(1 for v in raw_snow if v is not None)
        print(f"  {cfg['id']:8s}  {n:4d} obs  "
              f"temp:{temps_valid}  snow:{snow_valid}")

    return result


# ─────────────────────────────────────────────────────────────
#  HTML GENERATION
# ─────────────────────────────────────────────────────────────

def generate_html(station_list: List[dict], generated_at: str, refresh_url: str = "") -> str:
    if refresh_url:
        refresh_button_html = (
            f'<a href="{refresh_url}" class="refresh-btn">'
            '<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/>'
            '<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>'
            'Refresh Data</a>'
        )
    else:
        refresh_button_html = ""

    data_json = json.dumps({
        "region":       REGION,
        "generated_at": generated_at,
        "hours":        HOURS,
        "stations":     station_list,
    }, separators=(",", ":"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{REGION} — Weather Station Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
  <style>
    :root {{
      --blue:      #2563eb;
      --blue-dark: #1e3a5f;
      --red:       #ef4444;
      --green:     #16a34a;
      --bg:        #e8eef4;
      --card:      #ffffff;
      --border:    #cbd5e1;
      --text:      #1e293b;
      --muted:     #64748b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 16px;
    }}

    /* ── Page header ── */
    .page-header {{
      background: var(--blue-dark);
      color: #fff;
      padding: 18px 24px;
      border-radius: 12px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .page-header h1   {{ font-size: 1.45rem; font-weight: 700; }}
    .page-header .meta {{ font-size: 0.82rem; opacity: 0.75; margin-top: 4px; }}
    .refresh-btn {{
      display: inline-flex; align-items: center; gap: 6px;
      background: rgba(255,255,255,0.15);
      color: #fff;
      border: 1px solid rgba(255,255,255,0.35);
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 0.82rem;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      transition: background 0.15s;
      white-space: nowrap;
    }}
    .refresh-btn:hover {{ background: rgba(255,255,255,0.25); }}
    .refresh-btn svg {{ width: 14px; height: 14px; fill: none; stroke: currentColor;
                        stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round;
                        pointer-events: none; }}

    /* ── Station cards ── */
    .station-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 24px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    .card-header {{
      background: var(--blue-dark);
      color: #fff;
      padding: 12px 20px;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .station-name {{ font-size: 1.05rem; font-weight: 700; }}
    .station-id   {{ font-size: 0.78rem; opacity: 0.65; margin-left: 6px; }}
    .station-meta {{ font-size: 0.78rem; opacity: 0.8; }}
    .nws-link {{
      font-size: 1.05rem;
      color: rgba(255,255,255,0.85);
      text-decoration: none;
      margin-left: 10px;
      white-space: nowrap;
    }}
    .nws-link:hover {{ color: #fff; text-decoration: underline; }}

    /* ── Charts layout ── */
    .charts-area {{
      display: grid;
      grid-template-columns: 3fr 2fr;
    }}
    @media (max-width: 800px) {{
      .charts-area {{ grid-template-columns: 1fr; }}
    }}
    .chart-panel {{
      padding: 16px;
      border-right: 1px solid var(--border);
      min-width: 0;
    }}
    @media (max-width: 800px) {{
      .chart-panel {{ border-right: none; border-bottom: 1px solid var(--border); }}
    }}
    .chart-label {{
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      margin-bottom: 6px;
    }}

    /* ── Wind rose panel ── */
    .rose-panel {{
      padding: 14px 12px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }}
    .rose-title {{
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      align-self: flex-start;
    }}
    .rose-canvas {{ display: block; }}

    /* ── Wind rose controls ── */
    .rose-controls {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: center;
    }}
    .rose-step-btn {{
      background: var(--blue-dark);
      color: #fff;
      border: none;
      width: 32px; height: 32px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 1rem;
      display: flex; align-items: center; justify-content: center;
    }}
    .rose-step-btn:disabled {{ background: #94a3b8; cursor: default; }}
    .rose-step-btn:not(:disabled):hover {{ background: var(--blue); }}
    .rose-window-label {{
      min-width: 160px;
      text-align: center;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--text);
      padding: 5px 8px;
      background: #f1f5f9;
      border: 1px solid var(--border);
      border-radius: 6px;
    }}
    .rose-all-btn {{
      background: #f1f5f9;
      color: var(--blue-dark);
      border: 1px solid var(--border);
      padding: 5px 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.73rem;
      font-weight: 600;
    }}
    .rose-all-btn.active,
    .rose-all-btn:hover {{ background: var(--blue-dark); color: #fff; border-color: var(--blue-dark); }}

    /* ── Wind rose legend ── */
    .rose-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 3px 8px;
      justify-content: center;
    }}
    .legend-item {{
      display: flex; align-items: center; gap: 4px;
      font-size: 0.68rem; color: var(--muted);
    }}
    .legend-swatch {{ width: 11px; height: 11px; border-radius: 2px; flex-shrink: 0; }}

    /* ── Stats bar ── */
    .stats-bar {{
      background: #f8fafc;
      border-top: 1px solid var(--border);
      padding: 12px 20px;
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
    }}
    .stat {{ display: flex; flex-direction: column; }}
    .stat-lbl {{ font-size: 0.67rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
    .stat-val {{ font-size: 0.98rem; font-weight: 700; }}
    .stat-val.temp {{ color: var(--red); }}
    .stat-val.wind {{ color: var(--blue); }}
    .stat-val.snow {{ color: var(--green); }}

    .no-data {{ color: var(--muted); font-size: 0.82rem; padding: 20px; text-align: center; }}
  </style>
</head>
<body>

<div class="page-header">
  <div>
    <h1>{REGION} &mdash; Weather Station Dashboard</h1>
    <div class="meta">Generated {generated_at} &nbsp;&bull;&nbsp; Last {HOURS} hours (local time)</div>
  </div>
  {refresh_button_html}
</div>

<div id="stations-container"></div>

<!-- Embedded station data (generated by generate_dashboard.py) -->
<script>
const DASHBOARD_DATA = {data_json};
</script>

<script>
// ── Wind rose constants ──────────────────────────────────────
const N_DIRS     = 16;
const DIR_SIZE   = 360 / N_DIRS;   // 22.5°
const DIR_LABELS = [
  'N','NNE','NE','ENE','E','ESE','SE','SSE',
  'S','SSW','SW','WSW','W','WNW','NW','NNW',
];
const SPEED_BINS   = [0, 5, 10, 15, 20, 25, 30, Infinity];
const SPEED_LABELS = ['0–5','5–10','10–15','15–20','20–25','25–30','30+'];
const SPEED_COLORS = [
  '#3b82f6','#22c55e','#eab308','#f97316','#ef4444','#8b5cf6','#dc2626',
];

// ── App state ────────────────────────────────────────────────
const charts      = {{}};   // id → Chart.js instance
const roseWindow  = {{}};   // id → windowIndex (-1 = all 48h, 0 = newest 4h, …)
const MAX_WINDOW  = DASHBOARD_DATA.hours / 4 - 1;   // 11 for 48 h

// ── Build page from embedded data ───────────────────────────
function init() {{
  const container = document.getElementById('stations-container');

  for (const st of DASHBOARD_DATA.stations) {{
    // Parse ISO timestamps into Date objects
    st._times = st.times.map(t => new Date(t));
    roseWindow[st.id] = -1;

    const card = buildCard(st);
    container.appendChild(card);

    // Defer rendering so DOM is ready
    setTimeout(() => {{
      renderTempChart(st);
      renderWindRose(st, -1);
    }}, 0);
  }}
}}

// ── Build station card DOM ───────────────────────────────────
function buildCard(st) {{
  const elev   = st.elevation
    ? parseInt(st.elevation, 10).toLocaleString() + ' ft'
    : '';
  const coords = (st.lat && st.lon)
    ? parseFloat(st.lat).toFixed(3) + '°N, ' +
      Math.abs(parseFloat(st.lon)).toFixed(3) + '°W'
    : '';
  const meta = [elev, coords].filter(Boolean).join('  |  ');

  const hasSnow = st.snow_in.some(v => v != null);

  const nwsHref = (st.lat && st.lon)
    ? 'https://forecast.weather.gov/MapClick.php?w0=t&w1=td&w2=wc&w3=sfcwind&w3u=1&w4=sky&w5=pop&w6=rh&w7=thunder&w8=rain&w9=snow&w10=fzg&w11=sleet&AheadHour=0&Submit=Submit&FcstType=graphical&textField1='
      + parseFloat(st.lat).toFixed(5) + '&textField2='
      + parseFloat(st.lon).toFixed(5) + '&site=all&unit=0&dd=&bw='
    : '';
  const nwsLink = nwsHref
    ? '<a class="nws-link" href="' + nwsHref + '" target="_blank" rel="noopener noreferrer">NWS Point Forecast</a>'
    : '';

  const card = document.createElement('div');
  card.className = 'station-card';
  card.innerHTML = `
    <div class="card-header">
      <div>
        <span class="station-name">${{st.name}}</span>
        <span class="station-id">${{st.id}}</span>
        ${{nwsLink}}
      </div>
      <div class="station-meta">${{meta}}</div>
    </div>
    <div class="charts-area">
      <div class="chart-panel">
        <div class="chart-label">Temperature${{hasSnow ? ' &amp; Snow Depth' : ''}} — Last {HOURS}h</div>
        <canvas id="chart-${{st.id}}" height="146"></canvas>
      </div>
      <div class="rose-panel">
        <div class="rose-title">Wind Rose</div>
        <canvas id="rose-${{st.id}}" class="rose-canvas" width="420" height="420"></canvas>
        <div class="rose-controls">
          <button class="rose-step-btn" id="prev-${{st.id}}"
                  onclick="stepRose('${{st.id}}',-1)" title="Older 4-hour window">&#8592;</button>
          <span class="rose-window-label" id="rose-lbl-${{st.id}}">Last {HOURS}h</span>
          <button class="rose-step-btn" id="next-${{st.id}}"
                  onclick="stepRose('${{st.id}}',1)" title="Newer 4-hour window">&#8594;</button>
          <button class="rose-all-btn active" id="all-${{st.id}}"
                  onclick="resetRose('${{st.id}}')">All {HOURS}h</button>
        </div>
        <div class="rose-legend" id="legend-${{st.id}}"></div>
      </div>
    </div>
    ${{buildStatsBar(st)}}
  `;
  return card;
}}

function buildStatsBar(st) {{
  const validTemps = st.temp_f.filter(v => v != null);
  const validWinds = st.wind_mph.filter(v => v != null);
  const validGusts = st.gust_mph.filter(v => v != null);
  const validSnow  = st.snow_in.filter(v => v != null);

  const items = [];
  if (validTemps.length) {{
    const cur = validTemps[validTemps.length - 1];
    const mn  = Math.min(...validTemps).toFixed(1);
    const mx  = Math.max(...validTemps).toFixed(1);
    items.push(['Current Temp',      cur.toFixed(1) + '°F',           'temp']);
    items.push(['{HOURS}h Temp Range', mn + '° – ' + mx + '°F',     'temp']);
  }}
  if (validWinds.length) {{
    const cur = validWinds[validWinds.length - 1];
    items.push(['Current Wind', cur.toFixed(1) + ' mph', 'wind']);
    const validDirs = st.wind_dir.filter(v => v != null);
    if (validDirs.length) {{
      const curDir = validDirs[validDirs.length - 1];
      const dirLabel = DIR_LABELS[Math.round(curDir / DIR_SIZE) % N_DIRS];
      items.push(['Current Direction', curDir.toFixed(0) + '° (' + dirLabel + ')', 'wind']);
    }}
    if (validGusts.length) {{
      items.push(['{HOURS}h Max Gust', Math.max(...validGusts).toFixed(1) + ' mph', 'wind']);
    }} else {{
      items.push(['{HOURS}h Max Wind', Math.max(...validWinds).toFixed(1) + ' mph', 'wind']);
    }}
  }}
  if (validSnow.length) {{
    const cur = validSnow[validSnow.length - 1];
    const mn  = Math.min(...validSnow).toFixed(1);
    const mx  = Math.max(...validSnow).toFixed(1);
    items.push(['Snow Depth',    cur.toFixed(1) + '"',         'snow']);
    items.push(['{HOURS}h Range', mn + '" – ' + mx + '"',    'snow']);
  }}

  if (!items.length) return '<div class="no-data">No data available</div>';

  return '<div class="stats-bar">' +
    items.map(([lbl, val, cls]) =>
      `<div class="stat">
        <div class="stat-lbl">${{lbl}}</div>
        <div class="stat-val ${{cls}}">${{val}}</div>
       </div>`
    ).join('') +
    '</div>';
}}

// ── Temperature + Snow chart ─────────────────────────────────
function renderTempChart(st) {{
  const canvas = document.getElementById('chart-' + st.id);
  if (!canvas) return;

  const tempData = [], snowData = [];
  for (let i = 0; i < st._times.length; i++) {{
    const x = st._times[i];
    if (st.temp_f[i] != null) tempData.push({{x, y: st.temp_f[i]}});
    if (st.snow_in[i] != null) snowData.push({{x, y: st.snow_in[i]}});
  }}

  const datasets = [];
  if (tempData.length) {{
    const temps = tempData.map(p => p.y);
    datasets.push({{
      label: 'Temperature (°F)',
      data: tempData,
      borderColor: '#ef4444',
      backgroundColor: 'rgba(239,68,68,0.07)',
      borderWidth: 2, pointRadius: 0, tension: 0.3,
      yAxisID: 'yTemp', fill: true, spanGaps: true,
    }});
  }}
  if (snowData.length) {{
    datasets.push({{
      label: 'Snow Depth (in)',
      data: snowData,
      borderColor: '#16a34a',
      backgroundColor: 'rgba(22,163,74,0.07)',
      borderWidth: 2, pointRadius: 0, tension: 0.3,
      yAxisID: 'ySnow', fill: true, spanGaps: true,
    }});
  }}

  if (!datasets.length) {{
    canvas.parentElement.insertAdjacentHTML('beforeend',
      '<div class="no-data">No data available</div>');
    return;
  }}

  const scales = {{
    x: {{
      type: 'time',
      time: {{
        tooltipFormat: 'MMM d, HH:mm',
        displayFormats: {{ hour: 'HH:mm', day: 'MMM d' }},
      }},
      ticks: {{ maxTicksLimit: 9, font: {{ size: 11 }} }},
      grid: {{ color: '#e2e8f0' }},
    }},
  }};

  if (tempData.length) {{
    const mn = Math.min(...tempData.map(p => p.y));
    const mx = Math.max(...tempData.map(p => p.y));
    scales.yTemp = {{
      position: 'left',
      title: {{ display: true, text: '°F', color: '#ef4444', font: {{ size: 11 }} }},
      min: mn - 5, max: mx + 5,
      ticks: {{ font: {{ size: 11 }}, color: '#ef4444' }},
      grid: {{ color: '#e2e8f0' }},
    }};
  }}
  if (snowData.length) {{
    const mn = Math.min(...snowData.map(p => p.y));
    const mx = Math.max(...snowData.map(p => p.y));
    scales.ySnow = {{
      position: 'right',
      title: {{ display: true, text: 'Snow (in)', color: '#16a34a', font: {{ size: 11 }} }},
      min: Math.max(0, mn - 2), max: mx + 2,
      ticks: {{ font: {{ size: 11 }}, color: '#16a34a' }},
      grid: {{ drawOnChartArea: false }},
    }};
  }}

  if (charts[st.id]) charts[st.id].destroy();
  charts[st.id] = new Chart(canvas, {{
    type: 'line',
    data: {{ datasets }},
    options: {{
      responsive: true, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{ legend: {{ labels: {{ font: {{ size: 11 }} }} }} }},
      scales,
    }},
  }});
}}

// ── Wind rose ────────────────────────────────────────────────
function filterWindObs(st, windowIndex) {{
  const pairs = [];
  for (let i = 0; i < st._times.length; i++) {{
    const d = st.wind_dir[i], s = st.wind_mph[i];
    if (d == null || s == null) continue;
    pairs.push({{ t: st._times[i], dir: d, speed: s }});
  }}
  if (windowIndex === -1) return pairs;

  const lastMs  = st._times.length ? st._times[st._times.length - 1].getTime() : Date.now();
  const endMs   = lastMs - windowIndex * 4 * 3600000;
  const startMs = endMs  - 4 * 3600000;
  return pairs.filter(p => p.t.getTime() >= startMs && p.t.getTime() < endMs);
}}

function computeWindRoseData(obs) {{
  const counts = Array.from({{length: N_DIRS}}, () => new Array(SPEED_LABELS.length).fill(0));
  let total = 0;
  for (const {{dir, speed}} of obs) {{
    const dBin = Math.floor((parseFloat(dir) + DIR_SIZE / 2) / DIR_SIZE) % N_DIRS;
    let sBin = SPEED_LABELS.length - 1;
    for (let j = 0; j < SPEED_BINS.length - 1; j++) {{
      if (speed < SPEED_BINS[j + 1]) {{ sBin = j; break; }}
    }}
    counts[dBin][sBin]++;
    total++;
  }}
  return {{ counts, total }};
}}

function renderWindRose(st, windowIndex) {{
  const canvas = document.getElementById('rose-' + st.id);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const cx = W / 2, cy = H / 2;
  const maxR = Math.min(W, H) / 2 - 36;

  const obs = filterWindObs(st, windowIndex);
  const {{counts, total}} = computeWindRoseData(obs);

  if (total === 0) {{
    ctx.fillStyle = '#94a3b8';
    ctx.font = '13px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('No wind data for this window', cx, cy);
    updateLegend(st.id, false);
    return;
  }}

  const dirTotals = counts.map(b => b.reduce((a, x) => a + x, 0));
  const maxCount  = Math.max(...dirTotals, 1);

  // Reference rings
  const NUM_RINGS = 4;
  for (let r = 1; r <= NUM_RINGS; r++) {{
    const rr = maxR * r / NUM_RINGS;
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, rr, 0, 2 * Math.PI);
    ctx.stroke();

    const pct = Math.round(maxCount * r / NUM_RINGS / total * 100);
    const lx  = cx + rr * Math.cos(Math.PI / 4) + 3;
    const ly  = cy + rr * Math.sin(Math.PI / 4);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(pct + '%', lx, ly);
  }}

  // Spoke lines
  ctx.strokeStyle = '#f1f5f9';
  ctx.lineWidth = 1;
  for (let i = 0; i < N_DIRS; i++) {{
    const a = compassAngle(i * DIR_SIZE);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + maxR * Math.cos(a), cy + maxR * Math.sin(a));
    ctx.stroke();
  }}

  // Stacked wedges
  const half = (DIR_SIZE / 2 - 0.4) * Math.PI / 180;
  for (let i = 0; i < N_DIRS; i++) {{
    const ca  = compassAngle(i * DIR_SIZE);
    const sa  = ca - half, ea = ca + half;
    let cumIn = 0;
    for (let j = 0; j < SPEED_LABELS.length; j++) {{
      const cnt = counts[i][j];
      if (cnt === 0) {{ cumIn += cnt; continue; }}
      const cumOut = maxR * counts[i].slice(0, j + 1).reduce((a, b) => a + b, 0) / maxCount;
      const rIn    = maxR * counts[i].slice(0, j).reduce((a, b) => a + b, 0) / maxCount;

      ctx.fillStyle = SPEED_COLORS[j];
      ctx.beginPath();
      if (rIn < 1) {{
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, cumOut, sa, ea);
        ctx.closePath();
      }} else {{
        ctx.arc(cx, cy, cumOut, sa, ea);
        ctx.arc(cx, cy, rIn, ea, sa, true);
        ctx.closePath();
      }}
      ctx.fill();
    }}
  }}

  // Compass labels
  const labelR = maxR + 18;
  for (let i = 0; i < N_DIRS; i++) {{
    const a = compassAngle(i * DIR_SIZE);
    const lx = cx + labelR * Math.cos(a);
    const ly = cy + labelR * Math.sin(a);
    const cardinal = i % 4 === 0;
    ctx.font = cardinal ? 'bold 12px sans-serif' : '9px sans-serif';
    ctx.fillStyle = cardinal ? '#1e293b' : '#64748b';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(DIR_LABELS[i], lx, ly);
  }}

  // Center dot
  ctx.fillStyle = '#fff';
  ctx.strokeStyle = '#94a3b8';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, 3, 0, 2 * Math.PI);
  ctx.fill(); ctx.stroke();

  updateLegend(st.id, true);
}}

// Compass bearing (0=N clockwise) → canvas angle (radians, 0=East)
function compassAngle(deg) {{
  return (deg - 90) * Math.PI / 180;
}}

function updateLegend(id, show) {{
  const el = document.getElementById('legend-' + id);
  if (!el) return;
  el.innerHTML = show
    ? SPEED_LABELS.map((lbl, i) =>
        `<div class="legend-item">
          <div class="legend-swatch" style="background:${{SPEED_COLORS[i]}}"></div>
          ${{lbl}} mph
         </div>`
      ).join('')
    : '';
}}

// ── Wind rose time-window navigation ─────────────────────────
function stepRose(id, direction) {{
  const st  = DASHBOARD_DATA.stations.find(s => s.id === id);
  const cur = roseWindow[id];

  let next;
  if (cur === -1) {{
    // From "All 48h": left (older) enters most recent 4h window
    next = direction === -1 ? 0 : -1;
  }} else {{
    // Left (direction=-1) = older = higher window index
    // Right (direction=+1) = newer = lower window index
    next = cur - direction;
    if (next < 0) next = -1;          // crossed back to "All 48h"
    if (next > MAX_WINDOW) return;    // can't go past 48h
  }}

  roseWindow[id] = next;
  renderWindRose(st, next);
  updateRoseUI(id, st, next);
}}

function resetRose(id) {{
  const st = DASHBOARD_DATA.stations.find(s => s.id === id);
  roseWindow[id] = -1;
  renderWindRose(st, -1);
  updateRoseUI(id, st, -1);
}}

function updateRoseUI(id, st, windowIndex) {{
  const lbl  = document.getElementById('rose-lbl-' + id);
  const prev = document.getElementById('prev-' + id);
  const next = document.getElementById('next-' + id);
  const all  = document.getElementById('all-' + id);

  if (windowIndex === -1) {{
    lbl.textContent  = 'Last {HOURS}h';
    prev.disabled    = false;
    next.disabled    = true;
    all.classList.add('active');
  }} else {{
    const lastMs  = st._times ? st._times[st._times.length - 1].getTime()
                              : new Date(st.times[st.times.length - 1]).getTime();
    const endMs   = lastMs - windowIndex * 4 * 3600000;
    const startMs = endMs  - 4 * 3600000;

    const fmt = d => new Date(d).toLocaleString('en-US', {{
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    }});
    lbl.textContent  = fmt(startMs) + ' – ' + fmt(endMs);
    prev.disabled    = windowIndex >= MAX_WINDOW;
    next.disabled    = false;
    all.classList.remove('active');
  }}
}}

// ── Go! ───────────────────────────────────────────────────────
init();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def write_refresh_php(output_html_path: str, server_script_path: str,
                      python_path: str = "python3") -> str:
    """Write a PHP helper next to the HTML file that reruns this script."""
    html_dir  = os.path.dirname(os.path.abspath(output_html_path))
    html_name = os.path.basename(output_html_path)
    php_path  = os.path.join(html_dir, "refresh-wasatch.php")

    php = """<?php
// Auto-generated by generate_wasatch_dashboard.py
// Reruns the weather dashboard generator and redirects back to the dashboard.
$python = """ + repr(python_path) + """;
$script = """ + repr(server_script_path) + """;
$output = __DIR__ . '""" + "/" + html_name + """';
$cmd    = $python . " " . escapeshellarg($script) . " --output " . escapeshellarg($output) . " 2>&1";
shell_exec($cmd);
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Pragma: no-cache');
header('Location: """ + html_name + """?t=' . time());
exit;
"""
    with open(php_path, "w", encoding="utf-8") as f:
        f.write(php)
    return php_path


def main():
    global OUTPUT_PATH, SERVER_SCRIPT_PATH
    parser = argparse.ArgumentParser(description="Generate Wasatch weather dashboard HTML.")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path to write the HTML file (overrides DASHBOARD_OUTPUT_PATH env var and default)",
    )
    parser.add_argument(
        "--server-script-path",
        default=None,
        help=(
            "Absolute path to this script on the server (e.g. "
            "/home2/vofgesmy/python/scripts/generate_wasatch_dashboard.py). "
            "When set, writes a refresh-wasatch.php helper alongside the HTML."
        ),
    )
    parser.add_argument(
        "--python-path",
        default="/bin/python3",
        help="Absolute path to python3 on the server (default: /bin/python3).",
    )
    args = parser.parse_args()
    if args.output:
        OUTPUT_PATH = args.output
    if args.server_script_path:
        SERVER_SCRIPT_PATH = args.server_script_path

    generated_at = datetime.now().strftime("%B %-d, %Y at %-I:%M %p")
    print(f"\n=== Weather Dashboard Generator ===")
    print(f"Region  : {REGION}")
    print(f"Stations: {len(STATIONS)}")
    print(f"Hours   : {HOURS}")
    print(f"Output  : {OUTPUT_PATH}\n")

    raw = fetch_stations()
    station_list = parse_stations(raw)

    if not station_list:
        print("\nERROR: No station data parsed. HTML not written.")
        return 1

    refresh_url = "refresh-wasatch.php"
    if SERVER_SCRIPT_PATH:
        php_path = write_refresh_php(OUTPUT_PATH, SERVER_SCRIPT_PATH, args.python_path)
        print(f"  PHP refresh helper: {php_path}")

    html = generate_html(station_list, generated_at, refresh_url=refresh_url)

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"\nWritten: {OUTPUT_PATH} ({size_kb:.1f} KB)")
    print(f"  {len(station_list)}/{len(STATIONS)} stations included")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
