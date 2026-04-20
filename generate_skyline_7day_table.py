#!/usr/bin/env python3
"""
UAC 7-Day Hourly Weather Table Generator
==========================================
Fetches 7 days of data from the Synoptic API and writes a self-contained
tabular HTML file — one row per hour per station.

Variables: temperature, wind speed/gust/direction, hourly precip, snow depth.

Usage:
  python3 generate_7day_table.py
  python3 generate_7day_table.py --output /path/to/output.html
"""

import argparse
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
REGION = "Skyline"
HOURS  = 168   # 7 days

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

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "Skyline-7Day-Table.html")
OUTPUT_PATH = os.environ.get("TABLE_OUTPUT_PATH", _DEFAULT_OUTPUT)

# Absolute path to THIS script on the server — used to generate the PHP refresh helper.
# Set via --server-script-path CLI arg. If not set, no PHP file is written.
SERVER_SCRIPT_PATH = None

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
    """'2026-04-10T09:10:00-0600' → '2026-04-10 09'"""
    return ts[:13].replace("T", " ")

def fmt_hour_label(hk: str) -> str:
    """'2026-04-10 09' → 'Mon Apr 10, 09:00'"""
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
        "&vars=air_temp,wind_speed,wind_gust,wind_direction,precip_accum_one_hour,snow_depth"
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
        raw_precip = get("precip_accum_one_hour_set_1")
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
            p = _max(b["precips"])
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

def generate_html(station_list: List[dict], generated_at: str, refresh_url: str = "") -> str:
    refresh_btn = (
        f'<a href="{refresh_url}" class="refresh-btn">'
        '<svg viewBox="0 0 24 24"><polyline points="23 4 23 10 17 10"/>'
        '<path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>'
        'Refresh Data</a>'
    ) if refresh_url else ""

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
  <title>{REGION} — 7-Day Weather Table</title>
  <style>
    :root {{
      --blue-dark: #1e3a5f;
      --blue:      #2563eb;
      --border:    #cbd5e1;
      --bg:        #e8eef4;
      --card:      #ffffff;
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
      border-radius: 12px 12px 0 0;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .page-header h1   {{ font-size: 1.45rem; font-weight: 700; }}
    .page-header .meta {{ font-size: 0.82rem; opacity: 0.75; margin-top: 4px; }}

    /* ── Station tabs ── */
    .tab-bar {{
      background: #253f6a;
      padding: 0 12px;
      display: flex;
      flex-wrap: wrap;
      gap: 2px;
      border-bottom: 2px solid var(--blue);
    }}
    .tab-btn {{
      background: transparent;
      color: rgba(255,255,255,0.65);
      border: none;
      padding: 9px 13px;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 600;
      border-radius: 6px 6px 0 0;
      transition: background 0.1s, color 0.1s;
      white-space: nowrap;
    }}
    .tab-btn:hover  {{ background: rgba(255,255,255,0.12); color: #fff; }}
    .tab-btn.active {{ background: var(--blue); color: #fff; }}

    /* ── Station panels ── */
    .station-panel {{ display: none; }}
    .station-panel.active {{ display: block; }}

    .station-meta-bar {{
      background: #f8fafc;
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
      background: #334155;
      color: #fff;
      font-weight: 600;
      padding: 8px 14px;
      text-align: right;
      white-space: nowrap;
      border-right: 1px solid #475569;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    thead th:first-child {{ text-align: left; min-width: 148px; }}
    thead th:last-child  {{ border-right: none; }}

    tbody tr:nth-child(even) td {{ background-color: #f8fafc; }}
    tbody tr:hover td {{ background-color: #dbeafe !important; }}

    td {{
      padding: 4px 14px;
      border-right: 1px solid #e2e8f0;
      text-align: right;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    td:first-child {{ text-align: left; color: var(--muted); font-size: 0.77rem; }}
    td:last-child  {{ border-right: none; }}
    .no-val {{ color: #cbd5e1; }}

    /* ── Day separator rows ── */
    tr.day-sep td {{
      background: #e2e8f0 !important;
      color: #334155;
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 5px 14px;
      border-top: 2px solid #94a3b8;
    }}

    /* ── Header buttons (Refresh + Legend) ── */
    .header-btns {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    .refresh-btn, .legend-btn {{
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
    .refresh-btn:hover, .legend-btn:hover {{ background: rgba(255,255,255,0.25); }}
    .refresh-btn svg {{ width: 14px; height: 14px; fill: none; stroke: currentColor;
                        stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round;
                        pointer-events: none; }}

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
      color: var(--blue-dark);
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
      font-weight: 600;
      border: 1px solid rgba(0,0,0,0.1);
      white-space: nowrap;
    }}
    .legend-note {{
      background: #f8fafc;
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
  <div>
    <h1>{REGION} &mdash; 7-Day Hourly Weather</h1>
    <div class="meta">Generated {generated_at} &nbsp;&bull;&nbsp; Last {HOURS} hours (local time) &nbsp;&bull;&nbsp; Newest first</div>
  </div>
  <div class="header-btns">
    {refresh_btn}
    <button class="legend-btn" onclick="openLegend()">&#9432; Legend</button>
  </div>
</div>

<div class="modal-overlay" id="legend-modal" onclick="closeOnOverlay(event)">
  <div class="modal-box">
    <button class="modal-close" onclick="closeLegend()" title="Close">&#x2715;</button>
    <h2>Color Legend &amp; Notes</h2>

    <div class="legend-section">
      <h3>Temperature (°F)</h3>
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
        <span class="swatch" style="background:#fff;color:#64748b;border-color:#cbd5e1">&lt; 5</span>
        <span class="swatch" style="background:#fef9c3;color:#713f12">5&ndash;14</span>
        <span class="swatch" style="background:#fdba74;color:#7c2d12">15&ndash;24</span>
        <span class="swatch" style="background:#f97316;color:#fff">25&ndash;34</span>
        <span class="swatch" style="background:#ef4444;color:#fff">&ge; 35</span>
      </div>
    </div>

    <div class="legend-section">
      <h3>Hourly Precipitation (in)</h3>
      <div class="legend-swatches">
        <span class="swatch" style="background:#fff;color:#64748b;border-color:#cbd5e1">0&quot;</span>
        <span class="swatch" style="background:#dbeafe;color:#1e40af">&lt; 0.05&quot;</span>
        <span class="swatch" style="background:#93c5fd;color:#1e3a8a">0.05&ndash;0.24&quot;</span>
        <span class="swatch" style="background:#2563eb;color:#fff">&ge; 0.25&quot;</span>
      </div>
    </div>

    <div class="legend-section">
      <h3>Snow Depth (in)</h3>
      <div class="legend-swatches">
        <span class="swatch" style="background:#fff;color:#64748b;border-color:#cbd5e1">0&quot;</span>
        <span class="swatch" style="background:#dbeafe;color:#1e40af">&lt; 12&quot;</span>
        <span class="swatch" style="background:#93c5fd;color:#1e3a8a">12&ndash;35&quot;</span>
        <span class="swatch" style="background:#2563eb;color:#fff">&ge; 36&quot;</span>
      </div>
    </div>

    <div class="legend-note">
      <strong>Precip &amp; Snow Depth columns:</strong> The <em>Precip in</em> and
      <em>Snow Depth in</em> columns are only shown for stations that actually reported
      those variables during the 7-day window. If a station never returned precipitation
      or snow depth data, that column is hidden to keep the table uncluttered.
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

// ── Cell color scales ─────────────────────────────────────────

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

// ── Build one table cell ──────────────────────────────────────

function cell(val, style, decimals, suffix) {{
  if (val == null) return '<td class="no-val">—</td>';
  const disp = (decimals != null) ? val.toFixed(decimals) : val;
  const attr  = style ? ` style="${{style}}"` : '';
  return `<td${{attr}}>${{disp}}${{suffix || ''}}</td>`;
}}

// ── Build panel HTML for one station ─────────────────────────

function buildPanel(st) {{
  const elev   = st.elevation ? parseInt(st.elevation).toLocaleString() + ' ft' : '—';
  const coords = (st.lat && st.lon)
    ? parseFloat(st.lat).toFixed(3) + '°N, ' + Math.abs(parseFloat(st.lon)).toFixed(3) + '°W'
    : '—';

  const sp = st.has_precip;
  const ss = st.has_snow;
  const ncols = 5 + (sp ? 1 : 0) + (ss ? 1 : 0);

  const headerRow = `
    <th>Date / Time</th>
    <th>Temp °F</th>
    <th>Wind mph</th>
    <th>Gust mph</th>
    <th>Wind Dir</th>
    ${{sp ? '<th>Precip in</th>' : ''}}
    ${{ss ? '<th>Snow Depth in</th>' : ''}}
  `;

  // Newest first
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
      : '<span class="no-val">—</span>';

    rows += `<tr>
      <td>${{r.label}}</td>
      ${{cell(r.temp_f,    tempStyle(r.temp_f),    1, '°')}}
      ${{cell(r.wind_mph,  windStyle(r.wind_mph),  1, '')}}
      ${{cell(r.gust_mph,  windStyle(r.gust_mph),  1, '')}}
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

// ── Init ──────────────────────────────────────────────────────

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

// ── Legend modal ─────────────────────────────────────────────

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

// ── Go! ───────────────────────────────────────────────────────
init();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
#  PHP REFRESH HELPER
# ─────────────────────────────────────────────────────────────

def write_refresh_php(output_html_path: str, server_script_path: str,
                      python_path: str = "python3") -> str:
    html_dir  = os.path.dirname(os.path.abspath(output_html_path))
    html_name = os.path.basename(output_html_path)
    php_path  = os.path.join(html_dir, "refresh-skyline-7day.php")

    php = """<?php
// Auto-generated by generate_7day_table.py
$python = """ + repr(python_path) + """;
$script = """ + repr(server_script_path) + """;
$output = __DIR__ . '""" + "/" + html_name + """';
$log    = __DIR__ . '/refresh-7day.log';
$cmd    = $python . " " . escapeshellarg($script) . " --output " . escapeshellarg($output) . " 2>&1";
$result = shell_exec($cmd);
file_put_contents($log, date('Y-m-d H:i:s') . "\\n" . $cmd . "\\n" . $result . "\\n---\\n", FILE_APPEND);
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Pragma: no-cache');
header('Location: """ + html_name + """?t=' . time());
exit;
"""
    with open(php_path, "w", encoding="utf-8") as f:
        f.write(php)
    return php_path


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def main():
    global OUTPUT_PATH, SERVER_SCRIPT_PATH
    parser = argparse.ArgumentParser(description="Generate 7-day hourly weather table HTML.")
    parser.add_argument("--output", "-o", default=None,
                        help="Path to write the HTML file (overrides TABLE_OUTPUT_PATH env var)")
    parser.add_argument("--server-script-path", default=None,
                        help="Absolute path to this script on the server. "
                             "When set, writes a refresh-skyline-7day.php helper alongside the HTML.")
    parser.add_argument("--python-path", default="/bin/python3",
                        help="Absolute path to python3 on the server (default: /bin/python3).")
    args = parser.parse_args()
    if args.output:
        OUTPUT_PATH = args.output
    if args.server_script_path:
        SERVER_SCRIPT_PATH = args.server_script_path

    generated_at = datetime.now().strftime("%B %-d, %Y at %-I:%M %p")
    print(f"\n=== 7-Day Hourly Weather Table Generator ===")
    print(f"Region  : {REGION}")
    print(f"Stations: {len(STATIONS)}")
    print(f"Hours   : {HOURS}")
    print(f"Output  : {OUTPUT_PATH}\n")

    raw          = fetch_stations()
    station_list = parse_stations(raw)

    if not station_list:
        print("\nERROR: No station data parsed. HTML not written.")
        return 1

    refresh_url = "refresh-skyline-7day.php"
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
