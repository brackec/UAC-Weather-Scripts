#!/usr/bin/env python3
"""
UAC Skyline Weather Dashboard Generator
=============================================
Fetches weather station data from the Synoptic Data API and writes a
self-contained HTML file.  Run from cron twice daily (6 AM / 6 PM).

Cron example:
  0 6,18 * * * /usr/bin/python3 /path/to/generate_skyline_UAC_dashboard.py

Outputs:   OUTPUT_PATH (single HTML file, ready to serve)
"""

import argparse
import base64
import json
import os
import requests
from datetime import datetime
from typing import List

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION  ← edit here
# ─────────────────────────────────────────────────────────────

TOKEN  = "1643bf6fc1c2450b8ac5b25ff91a1fab"
REGION = "Skyline"
HOURS  = 48

STATIONS = [
    {"id": "SKY"},
    {"id": "ULAMB"},
    {"id": "UKALF"},
    {"id": "UTMPK"},
    {"id": "SEEU1"},
    {"id": "MCDU1"},
    {"id": "MTBU1"},
    {"id": "BUFU1"},
    {"id": "PC538"},
]

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "Skyline-UAC-Weather-Stations.html")
OUTPUT_PATH = os.environ.get("DASHBOARD_OUTPUT_PATH", _DEFAULT_OUTPUT)

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "UAC-logo.png")

# ─────────────────────────────────────────────────────────────
#  LOGO HELPER
# ─────────────────────────────────────────────────────────────

def _load_logo() -> str:
    try:
        with open(_LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""

# ─────────────────────────────────────────────────────────────
#  DATA FETCH
# ─────────────────────────────────────────────────────────────

def fetch_stations() -> List[dict]:
    stids   = ",".join(s["id"] for s in STATIONS)
    minutes = HOURS * 60
    url = (
        "https://api.synopticdata.com/v2/stations/timeseries"
        f"?stid={stids}"
        f"&token={TOKEN}"
        f"&recent={minutes}"
        "&vars=air_temp,wind_speed,wind_gust,wind_direction,snow_depth"
        "&precip=1"
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
    by_id = {s["STID"]: s for s in raw_stations}
    result = []
    for cfg in STATIONS:
        raw = by_id.get(cfg["id"])
        if raw is None:
            print(f"  WARNING: No data for {cfg['id']}")
            continue

        obs   = raw.get("OBSERVATIONS", {})
        times = obs.get("date_time", [])

        def to_f(vals):
            return [round(c * 9/5 + 32, 2) if c is not None else None for c in vals]
        def to_mph(vals):
            return [round(v * 2.23694, 2) if v is not None else None for v in vals]
        def to_in(vals):
            return [round(v * 0.0393701, 2) if v is not None else None for v in vals]

        raw_temp  = obs.get("air_temp_set_1",       [None]*len(times))
        raw_wind  = obs.get("wind_speed_set_1",      [None]*len(times))
        raw_gust  = obs.get("wind_gust_set_1",       [None]*len(times))
        raw_dir   = obs.get("wind_direction_set_1",  [None]*len(times))
        raw_snow  = obs.get("snow_depth_set_1",      [None]*len(times))

        raw_intervals = (
            obs.get("precip_intervals_set_1d") or
            obs.get("precip_intervals_set_1") or
            []
        )
        precip_accum_in = []
        running = 0.0
        for v in raw_intervals:
            if v is not None and v > 0:
                running += v
            precip_accum_in.append(round(running * 0.0393701, 3) if raw_intervals else None)

        result.append({
            "id":        raw["STID"],
            "name":      raw.get("NAME", cfg["id"]),
            "elevation": raw.get("ELEVATION"),
            "lat":       raw.get("LATITUDE"),
            "lon":       raw.get("LONGITUDE"),
            "times":     times,
            "temp_f":    to_f(raw_temp),
            "wind_mph":  to_mph(raw_wind),
            "gust_mph":  to_mph(raw_gust),
            "wind_dir":  raw_dir,
            "snow_in":   to_in(raw_snow),
            "precip_in": precip_accum_in if raw_intervals else [None] * len(times),
        })

        n = len(times)
        temps_valid  = sum(1 for v in raw_temp  if v is not None)
        snow_valid   = sum(1 for v in raw_snow  if v is not None)
        precip_valid = len(raw_intervals)
        print(f"  {cfg['id']:8s}  {n:4d} obs  "
              f"temp:{temps_valid}  snow:{snow_valid}  precip:{precip_valid}")

    return result


# ─────────────────────────────────────────────────────────────
#  HTML GENERATION
# ─────────────────────────────────────────────────────────────

def generate_html(station_list: List[dict], generated_at: str, logo_b64: str = "") -> str:
    logo_html = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="Utah Avalanche Center" class="uac-logo">'
        if logo_b64 else ""
    )

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
  <title>{REGION} &#8212; UAC Weather Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=PT+Sans:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
  <style>
    :root {{
      --uac-red:   #d50032;
      --uac-dark:  #a0001f;
      --red:       #ef4444;
      --green:     #16a34a;
      --precip:    #0ea5e9;
      --bg:        #f0f0f0;
      --card:      #ffffff;
      --border:    #d1d5db;
      --text:      #1a1a1a;
      --muted:     #6b7280;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'PT Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 16px;
    }}

    /* ── Page header ── */
    .page-header {{
      background: var(--uac-red);
      color: #fff;
      padding: 14px 24px;
      border-radius: 12px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .uac-logo {{
      height: 68px;
      width: auto;
      flex-shrink: 0;
    }}
    .header-text h1   {{ font-size: 1.45rem; font-weight: 700; }}
    .header-text .meta {{ font-size: 0.82rem; opacity: 0.85; margin-top: 4px; }}

    /* ── Station cards ── */
    .station-card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 24px;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .card-header {{
      background: var(--uac-red);
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
    .station-meta {{ font-size: 0.78rem; opacity: 0.85; }}
    .nws-link {{
      font-size: 1.05rem;
      color: rgba(255,255,255,0.85);
      text-decoration: underline;
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
      font-weight: 700;
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
      font-weight: 700;
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
      background: var(--uac-red);
      color: #fff;
      border: none;
      width: 32px; height: 32px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 1rem;
      display: flex; align-items: center; justify-content: center;
    }}
    .rose-step-btn:disabled {{ background: #94a3b8; cursor: default; }}
    .rose-step-btn:not(:disabled):hover {{ background: var(--uac-dark); }}
    .rose-window-label {{
      min-width: 160px;
      text-align: center;
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--text);
      padding: 5px 8px;
      background: #f3f4f6;
      border: 1px solid var(--border);
      border-radius: 6px;
    }}
    .rose-all-btn {{
      background: #f3f4f6;
      color: var(--uac-red);
      border: 1px solid var(--border);
      padding: 5px 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.73rem;
      font-weight: 700;
    }}
    .rose-all-btn.active,
    .rose-all-btn:hover {{ background: var(--uac-red); color: #fff; border-color: var(--uac-red); }}

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
      background: #f9fafb;
      border-top: 1px solid var(--border);
      padding: 12px 20px;
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
    }}
    .stat {{ display: flex; flex-direction: column; }}
    .stat-lbl {{ font-size: 0.67rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
    .stat-val {{ font-size: 0.98rem; font-weight: 700; }}
    .stat-val.temp   {{ color: var(--red); }}
    .stat-val.wind   {{ color: #2563eb; }}
    .stat-val.snow   {{ color: var(--green); }}
    .stat-val.precip {{ color: var(--precip); }}

    .no-data {{ color: var(--muted); font-size: 0.82rem; padding: 20px; text-align: center; }}
  </style>
</head>
<body>

<div class="page-header">
  {logo_html}
  <div class="header-text">
    <h1>{REGION} &#8212; Weather Station Dashboard</h1>
    <div class="meta">Generated {generated_at} &nbsp;&bull;&nbsp; Last {HOURS} hours (local time)</div>
  </div>
</div>

<div id="stations-container"></div>

<script>
const DASHBOARD_DATA = {data_json};
</script>

<script>
// ── Wind rose constants ──────────────────────────────────────
const N_DIRS     = 16;
const DIR_SIZE   = 360 / N_DIRS;
const DIR_LABELS = [
  'N','NNE','NE','ENE','E','ESE','SE','SSE',
  'S','SSW','SW','WSW','W','WNW','NW','NNW',
];
const SPEED_BINS   = [0, 5, 10, 15, 20, 25, 30, Infinity];
const SPEED_LABELS = ['0\u20135','5\u201310','10\u201315','15\u201320','20\u201325','25\u201330','30+'];
const SPEED_COLORS = [
  '#3b82f6','#22c55e','#eab308','#f97316','#ef4444','#8b5cf6','#dc2626',
];

const charts      = {{}};
const roseWindow  = {{}};
const MAX_WINDOW  = DASHBOARD_DATA.hours / 4 - 1;

function init() {{
  const container = document.getElementById('stations-container');
  for (const st of DASHBOARD_DATA.stations) {{
    st._times = st.times.map(t => new Date(t));
    roseWindow[st.id] = -1;
    const card = buildCard(st);
    container.appendChild(card);
    setTimeout(() => {{
      renderTempChart(st);
      renderWindRose(st, -1);
    }}, 0);
  }}
}}

function buildCard(st) {{
  const elev   = st.elevation ? parseInt(st.elevation, 10).toLocaleString() + ' ft' : '';
  const coords = (st.lat && st.lon)
    ? parseFloat(st.lat).toFixed(3) + '\u00b0N, ' + Math.abs(parseFloat(st.lon)).toFixed(3) + '\u00b0W'
    : '';
  const meta = [elev, coords].filter(Boolean).join('  |  ');

  const hasSnow = st.snow_in.some(v => v != null);
  const hasPrec = st.precip_in && st.precip_in.some(v => v != null);

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
        <div class="chart-label">${{          'Temperature' +
          (hasSnow && hasPrec ? ', Snow Depth &amp; Precip' :
           hasSnow            ? ' &amp; Snow Depth' :
           hasPrec            ? ' &amp; Precip' : '') +
          ' \u2014 Last {HOURS}h'
        }}</div>
        <canvas id="chart-${{st.id}}" height="146"></canvas>
      </div>
      <div class="rose-panel">
        <div class="rose-title">Wind Rose</div>
        <canvas id="rose-${{st.id}}" class="rose-canvas" width="420" height="420"></canvas>
        <div class="rose-controls">
          <button class="rose-step-btn" id="prev-${{st.id}}"
                  onclick="stepRose('${{st.id}}', -1)" title="Older 4-hour window">&#8592;</button>
          <span class="rose-window-label" id="rose-lbl-${{st.id}}">Last {HOURS}h</span>
          <button class="rose-step-btn" id="next-${{st.id}}"
                  onclick="stepRose('${{st.id}}', 1)" title="Newer 4-hour window">&#8594;</button>
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
  const validTemps  = st.temp_f.filter(v => v != null);
  const validWinds  = st.wind_mph.filter(v => v != null);
  const validGusts  = st.gust_mph.filter(v => v != null);
  const validSnow   = st.snow_in.filter(v => v != null);
  const validPrecip = (st.precip_in || []).filter(v => v != null);

  const items = [];
  if (validTemps.length) {{
    const cur = validTemps[validTemps.length - 1];
    const mn  = Math.min(...validTemps).toFixed(1);
    const mx  = Math.max(...validTemps).toFixed(1);
    items.push(['Current Temp',       cur.toFixed(1) + '\u00b0F',        'temp']);
    items.push(['{HOURS}h Temp Range', mn + '\u00b0 \u2013 ' + mx + '\u00b0F', 'temp']);
  }}
  if (validWinds.length) {{
    const cur = validWinds[validWinds.length - 1];
    items.push(['Current Wind', cur.toFixed(1) + ' mph', 'wind']);
    const validDirs = st.wind_dir.filter(v => v != null);
    if (validDirs.length) {{
      const curDir  = validDirs[validDirs.length - 1];
      const dirLabel = DIR_LABELS[Math.round(curDir / DIR_SIZE) % N_DIRS];
      items.push(['Current Direction', curDir.toFixed(0) + '\u00b0 (' + dirLabel + ')', 'wind']);
    }}
    if (validGusts.length) {{
      items.push(['{HOURS}h Max Gust', Math.max(...validGusts).toFixed(1) + ' mph', 'wind']);
    }} else {{
      items.push(['{HOURS}h Max Wind', Math.max(...validWinds).toFixed(1) + ' mph', 'wind']);
    }}
  }}
  if (validSnow.length) {{
    const cur      = validSnow[validSnow.length - 1];
    const snowfall = Math.max(0, cur - validSnow[0]).toFixed(1);
    items.push(['Snow Depth',        cur.toFixed(1) + '"', 'snow']);
    items.push(['{HOURS}h Snowfall', snowfall + '"',       'snow']);
  }}
  if (validPrecip.length) {{
    const total  = validPrecip[validPrecip.length - 1].toFixed(2);
    let maxHr = 0;
    for (let i = 1; i < validPrecip.length; i++) {{
      maxHr = Math.max(maxHr, validPrecip[i] - validPrecip[i - 1]);
    }}
    items.push(['{HOURS}h Precip Total', total + '"',              'precip']);
    items.push(['Max Hourly Precip',       maxHr.toFixed(2) + '"/hr', 'precip']);
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

function renderTempChart(st) {{
  const canvas = document.getElementById('chart-' + st.id);
  if (!canvas) return;

  const tempData = [], snowData = [], precipData = [];
  for (let i = 0; i < st._times.length; i++) {{
    const x = st._times[i];
    if (st.temp_f[i]  != null) tempData.push({{x, y: st.temp_f[i]}});
    if (st.snow_in[i] != null) snowData.push({{x, y: st.snow_in[i]}});
    if (st.precip_in && st.precip_in[i] != null) precipData.push({{x, y: st.precip_in[i]}});
  }}

  const datasets = [];
  if (tempData.length) {{
    datasets.push({{
      label: 'Temperature (\u00b0F)',
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
  if (precipData.length) {{
    datasets.push({{
      label: 'Precip Accum (in)',
      data: precipData,
      borderColor: '#0ea5e9',
      backgroundColor: 'rgba(14,165,233,0.10)',
      borderWidth: 2, pointRadius: 0, tension: 0.1,
      yAxisID: 'yPrecip', fill: true, spanGaps: true,
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
        unit: 'hour',
        stepSize: 2,
        tooltipFormat: 'MMM d, HH:mm',
        displayFormats: {{ hour: 'HH:mm', day: 'MMM d' }},
      }},
      ticks: {{
        maxTicksLimit: 40,
        major: {{ enabled: true }},
        font: ctx => ({{ size: 11, weight: ctx.tick && ctx.tick.major ? '600' : 'normal' }}),
        color: ctx => ctx.tick && ctx.tick.major ? '#1a1a1a' : '#94a3b8',
        callback(val, idx, ticks) {{
          const t = ticks[idx];
          if (!t || !t.major) return '';
          return new Date(val).toLocaleString('en-US', {{
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
          }});
        }},
      }},
      afterBuildTicks(axis) {{
        axis.ticks.forEach(tick => {{
          tick.major = new Date(tick.value).getHours() % 6 === 0;
        }});
      }},
      grid: {{
        color: ctx => ctx.tick && ctx.tick.major ? '#d1d5db' : '#f3f4f6',
      }},
    }},
  }};

  if (tempData.length) {{
    const mn = Math.min(...tempData.map(p => p.y));
    const mx = Math.max(...tempData.map(p => p.y));
    scales.yTemp = {{
      position: 'left',
      title: {{ display: true, text: '\u00b0F', color: '#ef4444', font: {{ size: 11 }} }},
      min: mn - 5, max: mx + 5,
      ticks: {{ font: {{ size: 11 }}, color: '#ef4444' }},
      grid: {{ color: '#e5e7eb' }},
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
  if (precipData.length) {{
    const mx = Math.max(...precipData.map(p => p.y));
    scales.yPrecip = {{
      position: 'right',
      title: {{ display: true, text: 'Accum (in)', color: '#0ea5e9', font: {{ size: 11 }} }},
      min: 0, max: Math.max(mx * 1.2, 0.05),
      ticks: {{ font: {{ size: 11 }}, color: '#0ea5e9' }},
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

  const obs  = filterWindObs(st, windowIndex);
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

  const NUM_RINGS = 4;
  for (let r = 1; r <= NUM_RINGS; r++) {{
    const rr = maxR * r / NUM_RINGS;
    ctx.strokeStyle = '#e5e7eb';
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

  ctx.strokeStyle = '#f3f4f6';
  ctx.lineWidth = 1;
  for (let i = 0; i < N_DIRS; i++) {{
    const a = compassAngle(i * DIR_SIZE);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + maxR * Math.cos(a), cy + maxR * Math.sin(a));
    ctx.stroke();
  }}

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

  const labelR = maxR + 18;
  for (let i = 0; i < N_DIRS; i++) {{
    const a = compassAngle(i * DIR_SIZE);
    const lx = cx + labelR * Math.cos(a);
    const ly = cy + labelR * Math.sin(a);
    const cardinal = i % 4 === 0;
    ctx.font = cardinal ? 'bold 12px sans-serif' : '9px sans-serif';
    ctx.fillStyle = cardinal ? '#1a1a1a' : '#6b7280';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(DIR_LABELS[i], lx, ly);
  }}

  ctx.fillStyle = '#fff';
  ctx.strokeStyle = '#94a3b8';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, 3, 0, 2 * Math.PI);
  ctx.fill(); ctx.stroke();

  updateLegend(st.id, true);
}}

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

function stepRose(id, direction) {{
  const st  = DASHBOARD_DATA.stations.find(s => s.id === id);
  const cur = roseWindow[id];
  let next;
  if (cur === -1) {{
    next = direction === -1 ? 0 : -1;
  }} else {{
    next = cur - direction;
    if (next < 0) next = -1;
    if (next > MAX_WINDOW) return;
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
    lbl.textContent = 'Last {HOURS}h';
    prev.disabled   = false;
    next.disabled   = true;
    all.classList.add('active');
  }} else {{
    const lastMs  = st._times ? st._times[st._times.length - 1].getTime()
                              : new Date(st.times[st.times.length - 1]).getTime();
    const endMs   = lastMs - windowIndex * 4 * 3600000;
    const startMs = endMs  - 4 * 3600000;
    const fmt = d => new Date(d).toLocaleString('en-US', {{
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    }});
    lbl.textContent = fmt(startMs) + ' \u2013 ' + fmt(endMs);
    prev.disabled   = windowIndex >= MAX_WINDOW;
    next.disabled   = false;
    all.classList.remove('active');
  }}
}}

init();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def main():
    global OUTPUT_PATH
    parser = argparse.ArgumentParser(description="Generate Skyline UAC weather dashboard HTML.")
    parser.add_argument("--output", "-o", default=None,
                        help="Path to write the HTML file (overrides DASHBOARD_OUTPUT_PATH env var and default)")
    args = parser.parse_args()
    if args.output:
        OUTPUT_PATH = args.output

    generated_at = datetime.now().strftime("%B %-d, %Y at %-I:%M %p")
    print(f"\n=== UAC Weather Dashboard Generator ===")
    print(f"Region  : {REGION}")
    print(f"Stations: {len(STATIONS)}")
    print(f"Hours   : {HOURS}")
    print(f"Output  : {OUTPUT_PATH}\n")

    raw          = fetch_stations()
    station_list = parse_stations(raw)

    if not station_list:
        print("\nERROR: No station data parsed. HTML not written.")
        return 1

    logo_b64 = _load_logo()
    html = generate_html(station_list, generated_at, logo_b64=logo_b64)

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"\nWritten: {OUTPUT_PATH} ({size_kb:.1f} KB)")
    print(f"  {len(station_list)}/{len(STATIONS)} stations included")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
