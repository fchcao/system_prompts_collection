#!/usr/bin/env python3
"""
Accumulate traffic history and generate a live dashboard.
Runs as a post-processing step after traffic-to-badge collects data.
Merges today's paths/referrers snapshot into growing history files,
then generates a self-contained HTML dashboard from all traffic data.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

REPO_SLUG = "system_prompts_leaks"
TRAFFIC_DIR = f"traffic-{REPO_SLUG}"
HISTORY_REFERRERS = "traffic_referrers_history.json"
HISTORY_PATHS = "traffic_paths_history.json"

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def fetch_from_branch(publish_dir, filename):
    """Try to fetch a file from the traffic branch via git."""
    full = f"{TRAFFIC_DIR}/{filename}"
    try:
        raw = subprocess.check_output(
            ["git", "show", f"origin/traffic:{full}"],
            stderr=subprocess.DEVNULL,
        )
        return json.loads(raw)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None

def accumulate(publish_dir):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data_dir = os.path.join(publish_dir, TRAFFIC_DIR)

    referrers = load_json(os.path.join(data_dir, "traffic_referrers.json"))
    paths = load_json(os.path.join(data_dir, "traffic_paths.json"))

    ref_history = (
        load_json(os.path.join(data_dir, HISTORY_REFERRERS))
        or fetch_from_branch(publish_dir, HISTORY_REFERRERS)
        or []
    )
    path_history = (
        load_json(os.path.join(data_dir, HISTORY_PATHS))
        or fetch_from_branch(publish_dir, HISTORY_PATHS)
        or []
    )

    existing_ref_dates = {e["date"] for e in ref_history}
    existing_path_dates = {e["date"] for e in path_history}

    if referrers and today not in existing_ref_dates:
        ref_history.append({"date": today, "referrers": referrers})
        ref_history.sort(key=lambda x: x["date"])

    if paths and today not in existing_path_dates:
        path_history.append({"date": today, "paths": paths})
        path_history.sort(key=lambda x: x["date"])

    with open(os.path.join(data_dir, HISTORY_REFERRERS), "w") as f:
        json.dump(ref_history, f, separators=(",", ":"))

    with open(os.path.join(data_dir, HISTORY_PATHS), "w") as f:
        json.dump(path_history, f, separators=(",", ":"))

    print(f"Accumulated: {len(ref_history)} referrer snapshots, {len(path_history)} path snapshots")
    return ref_history, path_history

def build_dashboard(publish_dir, ref_history, path_history):
    data_dir = os.path.join(publish_dir, TRAFFIC_DIR)
    views = load_json(os.path.join(data_dir, "traffic_views.json"))
    clones = load_json(os.path.join(data_dir, "traffic_clones.json"))

    if not views or not clones:
        print("Missing views/clones data, skipping dashboard")
        return

    embedded = json.dumps({
        "views": views,
        "clones": clones,
        "referrer_series": ref_history,
        "paths_series": path_history,
    }, separators=(",", ":"))

    html = DASHBOARD_TEMPLATE.replace("__DATA_PLACEHOLDER__", embedded)

    out_path = os.path.join(publish_dir, TRAFFIC_DIR, "dashboard.html")
    with open(out_path, "w") as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")

DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>system_prompts_leaks — Traffic Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  :root {
    --bg: #fafafa; --card: #fff; --border: #e5e7eb; --text: #1a1a2e;
    --text2: #6b7280; --accent: #6366f1; --accent2: #f59e0b;
    --accent3: #10b981; --accent4: #ef4444; --shadow: rgba(0,0,0,0.06);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0f0f1a; --card: #1a1a2e; --border: #2d2d44; --text: #e5e5ef;
      --text2: #9ca3af; --accent: #818cf8; --accent2: #fbbf24;
      --accent3: #34d399; --accent4: #f87171; --shadow: rgba(0,0,0,0.3);
    }
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); padding: 24px; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; }
  .subtitle { color: var(--text2); font-size: 0.875rem; margin-bottom: 24px; }
  .stats-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px var(--shadow); }
  .stat-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text2); margin-bottom: 4px; }
  .stat-value { font-size: 1.75rem; font-weight: 700; }
  .stat-sub { font-size: 0.8rem; color: var(--text2); margin-top: 2px; }
  .chart-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px var(--shadow); }
  .chart-title { font-size: 1rem; font-weight: 600; margin-bottom: 12px; }
  .chart-wrap { position: relative; height: 300px; }
  .tables-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
  @media (max-width: 768px) { .tables-row { grid-template-columns: 1fr; } }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; padding: 8px 12px; border-bottom: 2px solid var(--border); color: var(--text2); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }
  td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  .rank { color: var(--text2); font-weight: 500; width: 30px; }
  .bar-cell { position: relative; }
  .bar-bg { position: absolute; left: 0; top: 4px; bottom: 4px; border-radius: 4px; opacity: 0.15; }
  .path-text { max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.8rem; }
  .delta { font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; font-weight: 600; margin-left: 6px; }
  .delta-up { background: rgba(16,185,129,0.15); color: var(--accent3); }
  .delta-down { background: rgba(239,68,68,0.15); color: var(--accent4); }
  .section-title { font-size: 1.1rem; font-weight: 700; margin: 28px 0 12px; }
</style>
</head>
<body>
<h1>system_prompts_leaks</h1>
<p class="subtitle">Traffic history — auto-updated daily from the <code>traffic</code> branch</p>
<div class="stats-row" id="stats"></div>
<div class="chart-card"><div class="chart-title">Daily Views</div><div class="chart-wrap"><canvas id="viewsChart"></canvas></div></div>
<div class="chart-card"><div class="chart-title">Daily Clones</div><div class="chart-wrap"><canvas id="clonesChart"></canvas></div></div>
<div class="section-title">Top Pages &amp; Referrers (latest 14-day window)</div>
<div class="tables-row">
  <div class="chart-card" style="margin-bottom:0"><div class="chart-title">Top Pages</div><table id="pathsTable"></table></div>
  <div class="chart-card" style="margin-bottom:0"><div class="chart-title">Top Referrers (current window)</div><table id="referrersTable"></table></div>
</div>
<div class="section-title">All Referrers (union across all snapshots — peak 14-day count per source)</div>
<div class="chart-card"><table id="allReferrersTable"></table></div>
<div class="section-title">Referrer Trends (14-day rolling windows)</div>
<div class="chart-card"><div class="chart-title">Top Referrer Counts Over Time</div><div class="chart-wrap"><canvas id="refChart"></canvas></div></div>
<div class="chart-card"><div class="chart-title">Top Pages Over Time</div><div class="chart-wrap"><canvas id="pathsChart"></canvas></div></div>
<script>
const DATA = __DATA_PLACEHOLDER__;
const fmt = n => n.toLocaleString();
const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const gridColor = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
const tickColor = dark ? '#9ca3af' : '#6b7280';
const colors = ['#6366f1','#f59e0b','#10b981','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16','#a855f7','#fb923c','#2dd4bf','#f43f5e','#facc15','#38bdf8'];

function shortenPath(p) {
  const base = p.replace('/asgeirtj/system_prompts_leaks', '');
  if (!base) return 'Overview (repo landing)';
  if (base === '/tree/main') return '/ (root directory)';
  if (base.startsWith('/tree/main/')) return base.replace('/tree/main/', '') + '/';
  if (base.startsWith('/blob/main/')) return base.replace('/blob/main/', '');
  return base;
}

const views = DATA.views, clones = DATA.clones;
const vDays = views.views.sort((a,b) => a.timestamp.localeCompare(b.timestamp));
const cDays = clones.clones.sort((a,b) => a.timestamp.localeCompare(b.timestamp));
const peakView = vDays.reduce((a,b) => b.count > a.count ? b : a);
const avgViews = Math.round(views.count / vDays.length);
const last7v = vDays.slice(-7).reduce((s,d) => s + d.count, 0);
const prev7v = vDays.slice(-14,-7).reduce((s,d) => s + d.count, 0);
const weekDelta = prev7v ? Math.round((last7v - prev7v) / prev7v * 100) : 0;

document.getElementById('stats').innerHTML = [
  {label: 'Total Views', value: fmt(views.count), sub: fmt(views.uniques) + ' unique'},
  {label: 'Total Clones', value: fmt(clones.count), sub: fmt(clones.uniques) + ' unique'},
  {label: 'Daily Average', value: fmt(avgViews) + ' views', sub: fmt(Math.round(clones.count / cDays.length)) + ' clones'},
  {label: 'Peak Day', value: fmt(peakView.count), sub: peakView.timestamp.slice(0,10)},
  {label: '7-Day Trend', value: (weekDelta >= 0 ? '+' : '') + weekDelta + '%', sub: fmt(last7v) + ' vs ' + fmt(prev7v) + ' prior week'},
].map(s => `<div class="stat-card"><div class="stat-label">${s.label}</div><div class="stat-value">${s.value}</div><div class="stat-sub">${s.sub}</div></div>`).join('');

Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";
const commonScales = {
  x: { type: 'time', time: { unit: 'day', tooltipFormat: 'MMM d' }, grid: { color: gridColor }, ticks: { color: tickColor } },
  y: { grid: { color: gridColor }, ticks: { color: tickColor } }
};

new Chart(document.getElementById('viewsChart'), {
  type: 'line',
  data: { labels: vDays.map(d => d.timestamp), datasets: [
    { label: 'Views', data: vDays.map(d => d.count), borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.1)', fill: true, tension: 0.3, pointRadius: 3, pointHoverRadius: 6 },
    { label: 'Unique', data: vDays.map(d => d.uniques), borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 3, pointHoverRadius: 6 }
  ]},
  options: { responsive: true, maintainAspectRatio: false, scales: { ...commonScales, y: { ...commonScales.y, beginAtZero: true } }, plugins: { legend: { labels: { color: tickColor } } } }
});

new Chart(document.getElementById('clonesChart'), {
  type: 'bar',
  data: { labels: cDays.map(d => d.timestamp), datasets: [
    { label: 'Clones', data: cDays.map(d => d.count), backgroundColor: 'rgba(99,102,241,0.7)', borderRadius: 4 },
    { label: 'Unique', data: cDays.map(d => d.uniques), backgroundColor: 'rgba(245,158,11,0.7)', borderRadius: 4 }
  ]},
  options: { responsive: true, maintainAspectRatio: false, scales: { ...commonScales, y: { ...commonScales.y, beginAtZero: true } }, plugins: { legend: { labels: { color: tickColor } } } }
});

const latestPaths = DATA.paths_series.length ? DATA.paths_series[DATA.paths_series.length - 1].paths : [];
const latestRefs = DATA.referrer_series.length ? DATA.referrer_series[DATA.referrer_series.length - 1].referrers : [];
const prevRefs = DATA.referrer_series.length > 7 ? DATA.referrer_series[DATA.referrer_series.length - 8].referrers : null;
const maxPathCount = latestPaths[0]?.count || 1;
const maxRefCount = latestRefs[0]?.count || 1;

document.getElementById('pathsTable').innerHTML = '<thead><tr><th>#</th><th>Page</th><th>Views</th><th>Unique</th></tr></thead><tbody>' +
  latestPaths.map((p, i) => {
    const short = shortenPath(p.path);
    const w = Math.round(p.count / maxPathCount * 100);
    return `<tr><td class="rank">${i+1}</td><td class="bar-cell"><div class="bar-bg" style="width:${w}%;background:${colors[i]}"></div><span class="path-text" title="${p.path}">${short}</span></td><td>${fmt(p.count)}</td><td>${fmt(p.uniques)}</td></tr>`;
  }).join('') + '</tbody>';

document.getElementById('referrersTable').innerHTML = '<thead><tr><th>#</th><th>Referrer</th><th>Views</th><th>Trend</th></tr></thead><tbody>' +
  latestRefs.map((r, i) => {
    const w = Math.round(r.count / maxRefCount * 100);
    let deltaHtml = '';
    if (prevRefs) {
      const prev = prevRefs.find(p => p.referrer === r.referrer);
      if (prev) { const pct = Math.round((r.count - prev.count) / prev.count * 100); deltaHtml = pct !== 0 ? `<span class="delta ${pct > 0 ? 'delta-up' : 'delta-down'}">${pct > 0 ? '+' : ''}${pct}%</span>` : ''; }
      else { deltaHtml = '<span class="delta delta-up">new</span>'; }
    }
    return `<tr><td class="rank">${i+1}</td><td class="bar-cell"><div class="bar-bg" style="width:${w}%;background:${colors[i]}"></div>${r.referrer}</td><td>${fmt(r.count)}${deltaHtml}</td><td>${fmt(r.uniques)} unique</td></tr>`;
  }).join('') + '</tbody>';

const allRefsMap = {};
DATA.referrer_series.forEach(snap => { snap.referrers.forEach(r => { if (!allRefsMap[r.referrer] || r.count > allRefsMap[r.referrer].count) allRefsMap[r.referrer] = { count: r.count, uniques: r.uniques, peakDate: snap.date }; }); });
const allRefsRanked = Object.entries(allRefsMap).sort((a,b) => b[1].count - a[1].count);
const allRefMax = allRefsRanked[0]?.[1].count || 1;
document.getElementById('allReferrersTable').innerHTML = '<thead><tr><th>#</th><th>Referrer</th><th>Peak 14-day Count</th><th>Unique</th><th>Peak Snapshot</th></tr></thead><tbody>' +
  allRefsRanked.map(([name, data], i) => {
    const w = Math.round(data.count / allRefMax * 100);
    return `<tr><td class="rank">${i+1}</td><td class="bar-cell"><div class="bar-bg" style="width:${w}%;background:${colors[i % colors.length]}"></div>${name}</td><td>${fmt(data.count)}</td><td>${fmt(data.uniques)}</td><td>${data.peakDate}</td></tr>`;
  }).join('') + '</tbody>';

const allRefNames = new Set();
DATA.referrer_series.forEach(s => s.referrers.forEach(r => allRefNames.add(r.referrer)));
const topRefs = [...allRefNames].map(name => { const latest = latestRefs.find(r => r.referrer === name); return { name, count: latest ? latest.count : 0 }; }).sort((a,b) => b.count - a.count).slice(0, 8).map(r => r.name);

new Chart(document.getElementById('refChart'), {
  type: 'line',
  data: { labels: DATA.referrer_series.map(s => s.date), datasets: topRefs.map((name, i) => ({
    label: name, data: DATA.referrer_series.map(s => { const r = s.referrers.find(x => x.referrer === name); return r ? r.count : null; }),
    borderColor: colors[i], backgroundColor: 'transparent', tension: 0.3, pointRadius: 2, pointHoverRadius: 5, spanGaps: true
  }))},
  options: { responsive: true, maintainAspectRatio: false, scales: commonScales, plugins: { legend: { labels: { color: tickColor } } } }
});

const allPathNames = new Set();
DATA.paths_series.forEach(s => s.paths.forEach(p => allPathNames.add(p.path)));
const topPaths = [...allPathNames].map(name => { const latest = latestPaths.find(p => p.path === name); return { name, count: latest ? latest.count : 0 }; }).sort((a,b) => b.count - a.count).slice(0, 6).map(p => p.name);

new Chart(document.getElementById('pathsChart'), {
  type: 'line',
  data: { labels: DATA.paths_series.map(s => s.date), datasets: topPaths.map((name, i) => ({
    label: shortenPath(name), data: DATA.paths_series.map(s => { const p = s.paths.find(x => x.path === name); return p ? p.count : null; }),
    borderColor: colors[i], backgroundColor: 'transparent', tension: 0.3, pointRadius: 2, pointHoverRadius: 5, spanGaps: true
  }))},
  options: { responsive: true, maintainAspectRatio: false, scales: commonScales, plugins: { legend: { labels: { color: tickColor, font: { size: 11 } } } } }
});
</script>
</body>
</html>"""

if __name__ == "__main__":
    publish_dir = sys.argv[1]
    print(f"Processing traffic data in {publish_dir}")
    ref_history, path_history = accumulate(publish_dir)
    build_dashboard(publish_dir, ref_history, path_history)
