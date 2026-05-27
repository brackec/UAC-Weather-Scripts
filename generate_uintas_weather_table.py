#!/usr/bin/env python3
"""
UAC Uintas 7-Day Hourly Weather Table Generator
=====================================================
Fetches 7 days of data from the Synoptic API and writes a self-contained
tabular HTML file.

Usage:
  python3 generate_uintas_UAC_7day_table.py
  python3 generate_uintas_UAC_7day_table.py --output /path/to/output.html
"""

import argparse
import base64
import json
import math
import os
import requests
from collections import defaultdict
from datetime import datetime
from typing import List, Optional

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION  ← edit here
# ─────────────────────────────────────────────────────────────

TOKEN  = "1643bf6fc1c2450b8ac5b25ff91a1fab"
REGION = "Uintas"
HOURS  = 168   # 7 days

STATIONS = [
    {"id": "UTBMP"},
    {"id": "LOFTY"},
    {"id": "WDYPK"},
    {"id": "TRLU1"},
    {"id": "TPRUT"},
    {"id": "SMMU1"},
    {"id": "DSRUT"},
    {"id": "CCPUT"},
    {"id": "CCSUT"},
    {"id": "MHSUT"},
    {"id": "CUCU1"},
]

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "uintas-weather-table.html")
OUTPUT_PATH = os.environ.get("TABLE_OUTPUT_PATH", _DEFAULT_OUTPUT)

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
#  UTILITIES
# ─────────────────────────────────────────────────────────────

def _avg(vals) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None

def _max(vals) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return max(v) if v else None

def _last(vals) -> Optional[float]:
    v = [x for x in vals if x is not None]
    return v[-1] if v else None

def circular_mean(degrees: list) -> Optional[float]:
    valid = [d for d in degrees if d is not None]
    if not valid:
        return None
    s = sum(math.sin(math.radians(d)) for d in valid)
    c = sum(math.cos(math.radians(d)) for d in valid)
    return math.degrees(math.atan2(s, c)) % 360

def hour_key(ts: str) -> str:
    return ts[:13].replace("T", " ")

def fmt_hour_label(hk: str) -> str:
    dt = datetime.strptime(hk, "%Y-%m-%d %H")
    return dt.strftime("%a %b %-d, %H:00")

# ─────────────────────────────────────────────────────────────
#  DATA FETCH
# ─────────────────────────────────────────────────────────────

def fetch_stations() -> List[dict]:
    stids   = ",".join(s["id"] for s in STATIONS)
    minutes = HOURS * 60
    url = (
        "https://api.synopticdata.com/v2/stations/timeseries"
        f"?stid={stids}&token={TOKEN}&recent={minutes}"
        "&vars=air_temp,wind_speed,wind_gust,wind_direction,snow_depth"
        "&precip=1"
        "&obtimezone=local"
    )
    print(f"  Fetching {len(STATIONS)} stations ...")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "STATION" not in data or not data["STATION"]:
        print("  WARNING: API returned no stations.")
        return []
    return data["STATION"]

# ─────────────────────────────────────────────────────────────
#  PARSE + AGGREGATE TO HOURLY
# ─────────────────────────────────────────────────────────────

def parse_stations(raw_stations: List[dict]) -> List[dict]:
    by_id  = {s["STID"]: s for s in raw_stations}
    result = []

    for cfg in STATIONS:
        raw = by_id.get(cfg["id"])
        if raw is None:
            print(f"  WARNING: No data for {cfg['id']}")
            continue

        obs   = raw.get("OBSERVATIONS", {})
        times = obs.get("date_time", [])
        n     = len(times)

        def get(key):
            return obs.get(key, [None] * n)

        raw_temp   = get("air_temp_set_1")
        raw_wind   = get("wind_speed_set_1")
        raw_gust   = get("wind_gust_set_1")
        raw_dir    = get("wind_direction_set_1")
        raw_precip = (
            obs.get("precip_intervals_set_1d") or
            obs.get("precip_intervals_set_1") or
            [None] * n
        )
        raw_snow   = get("snow_depth_set_1")

        buckets = defaultdict(lambda: {
            "temps": [], "winds": [], "gusts": [], "dirs": [],
            "precips": [], "snows": [],
        })
        for i, ts in enumerate(times):
            hk = hour_key(ts)
            b  = buckets[hk]
            if raw_temp[i]   is not None: b["temps"].append(raw_temp[i]   * 9/5 + 32)
            if raw_wind[i]   is not None: b["winds"].append(raw_wind[i]   * 2.23694)
            if raw_gust[i]   is not None: b["gusts"].append(raw_gust[i]   * 2.23694)
            if raw_dir[i]    is not None: b["dirs"].append(raw_dir[i])
            if raw_precip[i] is not None: b["precips"].append(raw_precip[i] * 0.0393701)
            if raw_snow[i]   is not None: b["snows"].append(raw_snow[i]   * 0.0393701)

        hourly = []
        for hk in sorted(buckets):
            b = buckets[hk]
            t = _avg(b["temps"])
            w = _avg(b["winds"])
            g = _max(b["gusts"])
            d = circular_mean(b["dirs"])
            p = sum(b["precips"]) if b["precips"] else None
            s = _last(b["snows"])
            hourly.append({
                "hour":      hk,
                "label":     fmt_hour_label(hk),
                "temp_f":    round(t, 1) if t is not None else None,
                "wind_mph":  round(w, 1) if w is not None else None,
                "gust_mph":  round(g, 1) if g is not None else None,
                "wind_dir":  round(d)    if d is not None else None,
                "precip_in": round(p, 2) if p is not None else None,
                "snow_in":   round(s, 1) if s is not None else None,
            })

        has_precip = any(r["precip_in"] is not None for r in hourly)
        has_snow   = any(r["snow_in"]   is not None for r in hourly)

        result.append({
            "id":         raw["STID"],
            "name":       raw.get("NAME", cfg["id"]),
            "elevation":  raw.get("ELEVATION"),
            "lat":        raw.get("LATITUDE"),
            "lon":        raw.get("LONGITUDE"),
            "hourly":     hourly,
            "has_precip": has_precip,
            "has_snow":   has_snow,
        })

        print(f"  {cfg['id']:8s}  {n:4d} raw obs -> {len(hourly):3d} hourly rows  "
              f"precip:{'Y' if has_precip else 'N'}  snow:{'Y' if has_snow else 'N'}")

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
  <title>{REGION} &#8212; UAC 7-Day Weather</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=PT+Sans:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --uac-red:   #d50032;
      --uac-dark:  #a0001f;
      --uac-tab:   #b8002b;
      --border:    #d1d5db;
      --bg:        #f0f0f0;
      --card:      #ffffff;
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
      border-radius: 12px 12px 0 0;
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

    /* ── Station tabs ── */
    .tab-bar {{
      background: var(--uac-tab);
      padding: 0 12px;
      display: flex;
      flex-wrap: wrap;
      gap: 2px;
      border-bottom: 3px solid var(--uac-dark);
    }}
    .tab-btn {{
      background: transparent;
      color: rgba(255,255,255,0.70);
      border: none;
      padding: 9px 13px;
      cursor: pointer;
      font-family: 'PT Sans', sans-serif;
      font-size: 0.8rem;
      font-weight: 700;
      border-radius: 6px 6px 0 0;
      transition: background 0.1s, color 0.1s;
      white-space: nowrap;
    }}
    .tab-btn:hover  {{ background: rgba(255,255,255,0.15); color: #fff; }}
    .tab-btn.active {{ background: #fff; color: var(--uac-red); }}

    /* ── Station panels ── */
    .station-panel {{ display: none; }}
    .station-panel.active {{ display: block; }}

    .station-meta-bar {{
      background: #f9fafb;
      border: 1px solid var(--border);
      border-top: none;
      padding: 8px 20px;
      display: flex;
      gap: 24px;
      flex-wrap: wrap;
      font-size: 0.8rem;
      color: var(--muted);
    }}
    .station-meta-bar strong {{ color: var(--text); }}

    /* ── Table ── */
    .table-wrap {{
      overflow-x: auto;
      background: var(--card);
      border: 1px solid var(--border);
      border-top: none;
      border-radius: 0 0 12px 12px;
      max-height: 75vh;
      overflow-y: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }}
    thead th {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #1a1a1a;
      color: #fff;
      font-family: 'PT Sans', sans-serif;
      font-weight: 700;
      padding: 8px 14px;
      text-align: right;
      white-space: nowrap;
      border-right: 1px solid #333;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    thead th:first-child {{ text-align: left; min-width: 148px; }}
    thead th:last-child  {{ border-right: none; }}

    tbody tr:nth-child(even) td {{ background-color: #f9fafb; }}
    tbody tr:hover td {{ background-color: #fee2e2 !important; }}

    td {{
      padding: 4px 14px;
      border-right: 1px solid #e5e7eb;
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    td:first-child {{ text-align: left; color: var(--muted); font-size: 0.77rem; }}
    td:last-child  {{ border-right: none; }}
    .no-val {{ color: #d1d5db; }}

    /* ── Day separator rows ── */
    tr.day-sep td {{
      background: var(--uac-red) !important;
      color: #fff;
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 5px 14px;
      border-top: 2px solid var(--uac-dark);
    }}

    /* ── Legend button ── */
    .header-btns {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    .legend-btn {{
      display: inline-flex; align-items: center; gap: 6px;
      background: rgba(255,255,255,0.20);
      color: #fff;
      border: 1px solid rgba(255,255,255,0.45);
      padding: 7px 14px;
      border-radius: 8px;
      font-family: 'PT Sans', sans-serif;
      font-size: 0.82rem;
      font-weight: 700;
      text-decoration: underline;
      cursor: pointer;
      transition: background 0.15s;
      white-space: nowrap;
    }}
    .legend-btn:hover {{ background: rgba(255,255,255,0.30); }}

    /* ── Modal overlay ── */
    .modal-overlay {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.45);
      z-index: 100;
      align-items: flex-start;
      justify-content: center;
      padding: 48px 16px;
      overflow-y: auto;
    }}
    .modal-overlay.open {{ display: flex; }}
    .modal-box {{
      background: #fff;
      border-radius: 12px;
      padding: 28px 32px;
      max-width: 580px;
      width: 100%;
      position: relative;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }}
    .modal-close {{
      position: absolute;
      top: 14px; right: 16px;
      background: none;
      border: none;
      font-size: 1.2rem;
      cursor: pointer;
      color: var(--muted);
      line-height: 1;
      padding: 4px;
    }}
    .modal-close:hover {{ color: var(--text); }}
    .modal-box h2 {{
      font-size: 1.1rem;
      font-weight: 700;
      margin-bottom: 20px;
      color: var(--uac-red);
    }}
    .legend-section {{ margin-bottom: 18px; }}
    .legend-section h3 {{
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
      margin-bottom: 7px;
    }}
    .legend-swatches {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .swatch {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 0.78rem;
      font-weight: 700;
      border: 1px solid rgba(0,0,0,0.1);
      white-space: nowrap;
    }}
    .legend-note {{
      background: #f9fafb;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 0.82rem;
      color: var(--muted);
      line-height: 1.55;
      margin-top: 4px;
    }}
    .legend-note strong {{ color: var(--text); }}
  </style>
</head>
<body>

<div class="page-header">
  {logo_html}
  <div class="header-text" style="flex:1">
    <h1>{REGION} &#8212; 7-Day Hourly Weather</h1>
    <div class="meta">Generated {generated_at} &nbsp;&bull;&nbsp; Last {HOURS} hours (local time) &nbsp;&bull;&nbsp; Newest first</div>
  </div>
  <div class="header-btns">
    <button class="legend-btn" onclick="openLegend()">&#9432; Legend</button>
  </div>
</div>

<div class="modal-overlay" id="legend-modal" onclick="closeOnOverlay(event)">
  <div class="modal-box">
    <button class="modal-close" onclick="closeLegend()" title="Close">&#x2715;</button>
    <h2>Color Legend &amp; Notes</h2>

    <div class="legend-section">
      <h3>Temperature (&#176;F)</h3>
      <div class="legend-swatches">
        <span class="swatch" style="background:#1d4ed8;color:#fff">&le; 0&deg;</span>
        <span class="swatch" style="background:#2563eb;color:#fff">1&ndash;10&deg;</span>
        <span class="swatch" style="background:#60a5fa;color:#1e3a5f">11&ndash;20&deg;</span>
        <span class="swatch" style="background:#bae6fd;color:#0c4a6e">21&ndash;32&deg;</span>
        <span class="swatch" style="background:#bbf7d0;color:#14532d">33&ndash;40&deg;</span>
        <span class="swatch" style="background:#fef9c3;color:#713f12">41&ndash;50&deg;</span>
        <span class="swatch" style="background:#fed7aa;color:#7c2d12">51&ndash;60&deg;</span>
        <span class="swatch" style="background:#fca5a5;color:#7f1d1d">&gt; 60&deg;</span>
      </div>
    </div>

    <div class="legend-section">
      <h3>Wind Speed &amp; Gust (mph)</h3>
      <div class="legend-swatches">
        <span class="swatch" style="background:#fff;color:#6b7280;border-color:#d1d5db">&lt; 5</span>
        <span class="swatch" style="background:#fef9c3;color:#713f12">5&ndash;14</span>
        <span class="swatch" style="background:#fdba74;color:#7c2d12">15&ndash;24</span>
        <span class="swatch" style="background:#f97316;color:#fff">25&ndash;34</span>
        <span class="swatch" style="background:#ef4444;color:#fff">&ge; 35</span>
      </div>
    </div>

    <div class="legend-section">
      <h3>Hourly Precipitation (in)</h3>
      <div class="legend-swatches">
        <span class="swatch" style="background:#fff;color:#6b7280;border-color:#d1d5db">0&quot;</span>
        <span class="swatch" style="background:#dbeafe;color:#1e40af">&lt; 0.05&quot;</span>
        <span class="swatch" style="background:#93c5fd;color:#1e3a8a">0.05&ndash;0.24&quot;</span>
        <span class="swatch" style="background:#2563eb;color:#fff">&ge; 0.25&quot;</span>
      </div>
    </div>

    <div class="legend-section">
      <h3>Snow Depth (in)</h3>
      <div class="legend-swatches">
        <span class="swatch" style="background:#fff;color:#6b7280;border-color:#d1d5db">0&quot;</span>
        <span class="swatch" style="background:#dbeafe;color:#1e40af">&lt; 12&quot;</span>
        <span class="swatch" style="background:#93c5fd;color:#1e3a8a">12&ndash;35&quot;</span>
        <span class="swatch" style="background:#2563eb;color:#fff">&ge; 36&quot;</span>
      </div>
    </div>

    <div class="legend-note">
      <strong>Precip &amp; Snow Depth columns:</strong> Only shown for stations that
      reported those variables during the 7-day window.
    </div>
  </div>
</div>

<div class="tab-bar" id="tab-bar"></div>
<div id="panels-container"></div>

<script>
const DATA = {data_json};

const DIR16 = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];

function dirLabel(deg) {{
  if (deg == null) return '';
  return DIR16[Math.round(parseFloat(deg) / 22.5) % 16];
}}

function tempStyle(f) {{
  if (f == null) return '';
  if (f <= 0)  return 'background:#1d4ed8;color:#fff';
  if (f <= 10) return 'background:#2563eb;color:#fff';
  if (f <= 20) return 'background:#60a5fa;color:#1e3a5f';
  if (f <= 32) return 'background:#bae6fd;color:#0c4a6e';
  if (f <= 40) return 'background:#bbf7d0;color:#14532d';
  if (f <= 50) return 'background:#fef9c3;color:#713f12';
  if (f <= 60) return 'background:#fed7aa;color:#7c2d12';
  return 'background:#fca5a5;color:#7f1d1d';
}}

function windStyle(mph) {{
  if (mph == null || mph < 5) return '';
  if (mph < 15) return 'background:#fef9c3;color:#713f12';
  if (mph < 25) return 'background:#fdba74;color:#7c2d12';
  if (mph < 35) return 'background:#f97316;color:#fff';
  return 'background:#ef4444;color:#fff';
}}

function precipStyle(p) {{
  if (p == null || p === 0) return '';
  if (p < 0.05) return 'background:#dbeafe;color:#1e40af';
  if (p < 0.25) return 'background:#93c5fd;color:#1e3a8a';
  return 'background:#2563eb;color:#fff';
}}

function snowStyle(s) {{
  if (s == null || s === 0) return '';
  if (s < 12)  return 'background:#dbeafe;color:#1e40af';
  if (s < 36)  return 'background:#93c5fd;color:#1e3a8a';
  return 'background:#2563eb;color:#fff';
}}

function cell(val, style, decimals, suffix) {{
  if (val == null) return '<td class="no-val">\u2014</td>';
  const disp = (decimals != null) ? val.toFixed(decimals) : val;
  const attr  = style ? ` style="${{style}}"` : '';
  return `<td${{attr}}>${{disp}}${{suffix || ''}}</td>`;
}}

function buildPanel(st) {{
  const elev   = st.elevation ? parseInt(st.elevation).toLocaleString() + ' ft' : '\u2014';
  const coords = (st.lat && st.lon)
    ? parseFloat(st.lat).toFixed(3) + '\u00b0N, ' + Math.abs(parseFloat(st.lon)).toFixed(3) + '\u00b0W'
    : '\u2014';

  const sp = st.has_precip;
  const ss = st.has_snow;
  const ncols = 5 + (sp ? 1 : 0) + (ss ? 1 : 0);

  const headerRow = `
    <th>Date / Time</th>
    <th>Temp \u00b0F</th>
    <th>Wind mph</th>
    <th>Gust mph</th>
    <th>Wind Dir</th>
    ${{sp ? '<th>Precip in</th>' : ''}}
    ${{ss ? '<th>Snow Depth in</th>' : ''}}
  `;

  const rows_data = [...st.hourly].reverse();
  let rows = '';
  let lastDay = '';

  for (const r of rows_data) {{
    const day = r.hour.slice(0, 10);
    if (day !== lastDay) {{
      lastDay = day;
      const [y, m, d] = day.split('-').map(Number);
      const dt = new Date(y, m - 1, d, 12);
      const dayStr = dt.toLocaleDateString('en-US', {{
        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
      }});
      rows += `<tr class="day-sep"><td colspan="${{ncols}}">${{dayStr}}</td></tr>`;
    }}

    const dirText = r.wind_dir != null
      ? `${{r.wind_dir}}° ${{dirLabel(r.wind_dir)}}`
      : '<span class="no-val">\u2014</span>';

    rows += `<tr>
      <td>${{r.label}}</td>
      ${{cell(r.temp_f,   tempStyle(r.temp_f),   1, '\u00b0')}}
      ${{cell(r.wind_mph, windStyle(r.wind_mph), 1, '')}}
      ${{cell(r.gust_mph, windStyle(r.gust_mph), 1, '')}}
      <td>${{dirText}}</td>
      ${{sp ? cell(r.precip_in, precipStyle(r.precip_in), 2, '"') : ''}}
      ${{ss ? cell(r.snow_in,   snowStyle(r.snow_in),     1, '"') : ''}}
    </tr>`;
  }}

  return `
    <div class="station-meta-bar">
      <span><strong>${{st.name}}</strong> &nbsp;(${{st.id}})</span>
      <span>Elevation: ${{elev}}</span>
      <span>Coords: ${{coords}}</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>${{headerRow}}</tr></thead>
        <tbody>${{rows}}</tbody>
      </table>
    </div>
  `;
}}

function init() {{
  const tabBar    = document.getElementById('tab-bar');
  const container = document.getElementById('panels-container');

  DATA.stations.forEach((st, i) => {{
    const btn = document.createElement('button');
    btn.className   = 'tab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = st.name || st.id;
    btn.onclick     = () => switchTab(i);
    tabBar.appendChild(btn);

    const panel = document.createElement('div');
    panel.className = 'station-panel' + (i === 0 ? ' active' : '');
    panel.id        = 'panel-' + i;
    panel.innerHTML = buildPanel(st);
    container.appendChild(panel);
  }});
}}

function switchTab(index) {{
  document.querySelectorAll('.tab-btn').forEach((b, i) =>
    b.classList.toggle('active', i === index));
  document.querySelectorAll('.station-panel').forEach((p, i) =>
    p.classList.toggle('active', i === index));
}}

function openLegend() {{
  document.getElementById('legend-modal').classList.add('open');
}}
function closeLegend() {{
  document.getElementById('legend-modal').classList.remove('open');
}}
function closeOnOverlay(e) {{
  if (e.target === e.currentTarget) closeLegend();
}}
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeLegend(); }});

init();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def main():
    global OUTPUT_PATH
    parser = argparse.ArgumentParser(description="Generate Uintas UAC 7-day weather table HTML.")
    parser.add_argument("--output", "-o", default=None,
                        help="Path to write the HTML file (overrides TABLE_OUTPUT_PATH env var)")
    args = parser.parse_args()
    if args.output:
        OUTPUT_PATH = args.output

    generated_at = datetime.now().strftime("%B %-d, %Y at %-I:%M %p")
    print(f"\n=== UAC 7-Day Hourly Weather Table Generator ===")
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
