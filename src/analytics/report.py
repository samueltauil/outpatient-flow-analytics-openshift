"""
Standalone HTML Report Generator for Outpatient Flow Analytics.

Reads analytics_results.json + aggregates.csv and produces a single
self-contained HTML file with KPI cards, Chart.js visualisations,
facility comparisons, model metrics, and actionable insights.

Usage:
    python -m src.analytics.report --results output/analytics/analytics_results.json \
                                    --aggregates output/analytics/aggregates.csv \
                                    --output output/analytics/report.html
"""

import argparse
import json
import html
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chart.js helpers
# ---------------------------------------------------------------------------

def _bar_chart(canvas_id: str, labels: list, datasets: list, title: str,
               y_label: str = "Minutes", stacked: bool = False) -> str:
    """Return a <script> block that renders a Chart.js bar chart."""
    cfg = json.dumps({
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": True, "text": title, "color": "#c9d1d9",
                          "font": {"size": 14, "weight": "500"}},
                "legend": {"labels": {"color": "#8b949e", "font": {"size": 11}}}
            },
            "scales": {
                "x": {"ticks": {"color": "#8b949e", "font": {"size": 10}},
                       "grid": {"color": "#21262d"}},
                "y": {"ticks": {"color": "#8b949e", "font": {"size": 10}},
                       "grid": {"color": "#21262d"},
                       "title": {"display": True, "text": y_label, "color": "#8b949e"},
                       "stacked": stacked},
            },
        },
    }, default=str)
    return f'<script>new Chart(document.getElementById("{canvas_id}"),{cfg});</script>'


def _doughnut_chart(canvas_id: str, labels: list, values: list, colours: list, title: str) -> str:
    cfg = json.dumps({
        "type": "doughnut",
        "data": {"labels": labels, "datasets": [{"data": values, "backgroundColor": colours,
                                                   "borderWidth": 0, "hoverOffset": 6}]},
        "options": {
            "responsive": True, "maintainAspectRatio": False, "cutout": "65%",
            "plugins": {
                "title": {"display": True, "text": title, "color": "#c9d1d9",
                          "font": {"size": 14, "weight": "500"}},
                "legend": {"position": "bottom", "labels": {"color": "#c9d1d9",
                           "padding": 16, "font": {"size": 11}}}
            },
        },
    }, default=str)
    return f'<script>new Chart(document.getElementById("{canvas_id}"),{cfg});</script>'


# ---------------------------------------------------------------------------
# KPI card
# ---------------------------------------------------------------------------

def _kpi_card(label: str, value: str, sub: str = "", colour: str = "#58a6ff") -> str:
    return f"""
    <div class="kpi">
      <div class="kpi-value" style="color:{colour}">{html.escape(str(value))}</div>
      <div class="kpi-label">{html.escape(label)}</div>
      <div class="kpi-sub">{html.escape(sub)}</div>
    </div>"""


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

REPORT_CSS = """\
:root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#c9d1d9; --muted:#8b949e;
        --blue:#58a6ff; --green:#3fb950; --purple:#a78bfa; --orange:#f0883e; --red:#f85149; }
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
     background:var(--bg);color:var(--text);line-height:1.6;padding:32px 40px;max-width:1400px;margin:0 auto}

/* Header */
.header{margin-bottom:36px;border-bottom:1px solid var(--border);padding-bottom:20px}
.header h1{font-size:22px;font-weight:600;letter-spacing:-0.3px;margin-bottom:6px}
.header .sub{color:var(--muted);font-size:13px;display:flex;align-items:center;gap:12px}
.tag{display:inline-block;padding:2px 10px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:0.3px}
.tag-gpu{background:#238636;color:#fff}
.tag-cpu{background:var(--card);color:var(--muted);border:1px solid var(--border)}

/* KPI */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:36px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px;text-align:center}
.kpi-value{font-size:30px;font-weight:700;letter-spacing:-0.5px}
.kpi-label{color:var(--muted);font-size:11px;margin-top:6px;text-transform:uppercase;letter-spacing:0.8px;font-weight:600}
.kpi-sub{color:var(--muted);font-size:11px;margin-top:2px}

/* Sections */
.section{margin-bottom:36px}
.section h2{font-size:16px;font-weight:600;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid var(--border);letter-spacing:-0.2px}

/* Charts */
.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:16px}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px}
.chart-wrap{position:relative;height:280px}

/* Tables */
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--muted);font-weight:600;padding:8px 12px;border-bottom:2px solid var(--border);
   text-transform:uppercase;font-size:10px;letter-spacing:0.6px}
td{padding:8px 12px;border-bottom:1px solid var(--border)}
tr:hover td{background:rgba(88,166,255,0.03)}
.num{text-align:right;font-variant-numeric:tabular-nums}

/* Pills */
.pill{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;letter-spacing:0.3px;text-transform:uppercase}
.pill-high{background:rgba(248,81,73,0.15);color:var(--red)}
.pill-medium{background:rgba(240,136,62,0.15);color:var(--orange)}
.pill-info{background:rgba(88,166,255,0.12);color:var(--blue)}

/* Insight tabs (pure CSS) */
.insight-section{margin-bottom:40px}
.insight-section>h2{font-size:16px;font-weight:600;margin-bottom:6px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.insight-summary{color:var(--muted);font-size:13px;margin-bottom:20px;display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.sev-badge{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600}
.sev-badge .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot-high{background:var(--red)} .dot-med{background:var(--orange)} .dot-info{background:var(--blue)}

.tab-bar{display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:20px;overflow-x:auto}
.tab-radio{display:none}
.tab-label{padding:10px 18px;font-size:12px;font-weight:600;color:var(--muted);cursor:pointer;
           border-bottom:2px solid transparent;margin-bottom:-2px;white-space:nowrap;transition:color 0.15s,border-color 0.15s;
           letter-spacing:0.2px;display:flex;align-items:center;gap:6px}
.tab-label:hover{color:var(--text)}
.tab-count{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:0 7px;font-size:11px;
           font-variant-numeric:tabular-nums;line-height:18px}
.tab-radio:checked+.tab-label{color:var(--blue);border-bottom-color:var(--blue)}
.tab-radio:checked+.tab-label .tab-count{background:rgba(88,166,255,0.12);border-color:rgba(88,166,255,0.3);color:var(--blue)}
.tab-panel{display:none}
.tab-radio:checked~.tab-panel{display:block}
/* Each tab group needs its own panel selector — handled via id matching in JS below */

/* Insight cards */
.i-card{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:12px;overflow:hidden}
.i-card:hover{border-color:rgba(88,166,255,0.25)}
.i-head{padding:16px 20px;display:flex;align-items:center;gap:12px}
.i-sev{width:4px;align-self:stretch;border-radius:2px;flex-shrink:0}
.i-sev-high{background:var(--red)} .i-sev-medium{background:var(--orange)} .i-sev-info{background:var(--blue)}
.i-title{font-size:14px;font-weight:600;flex:1}
.i-facility{color:var(--muted);font-size:12px;flex-shrink:0}
.i-body{padding:0 20px 18px 36px;display:grid;grid-template-columns:1fr 1fr;gap:16px}
.i-block{font-size:13px;line-height:1.6}
.i-block-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:var(--muted);margin-bottom:6px}
.i-block-full{grid-column:1/-1}
.i-block-action{background:rgba(56,139,253,0.06);border:1px solid rgba(56,139,253,0.15);border-radius:6px;padding:14px 16px}
.i-block-action .i-block-label{color:var(--blue)}
.i-block-impact{background:rgba(240,136,62,0.04);border:1px solid rgba(240,136,62,0.1);border-radius:6px;padding:14px 16px}

/* Model cards */
.model-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
.model-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:24px}
.model-card h3{margin-bottom:14px;font-size:14px;font-weight:600}
.metric-row{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border);font-size:13px}
.metric-row:last-child{border-bottom:none}
.metric-label{color:var(--muted)}
.metric-value{font-weight:600;font-variant-numeric:tabular-nums}

/* Footer */
.footer{text-align:center;color:var(--muted);font-size:11px;margin-top:48px;padding-top:16px;
        border-top:1px solid var(--border);letter-spacing:0.2px}
"""


def build_report(results: Dict[str, Any], aggs: pd.DataFrame) -> str:
    """Build a complete self-contained HTML report string."""

    ts = results.get("timestamp", datetime.now(timezone.utc).isoformat())
    gpu = results.get("gpu_available", False)
    insights: List[Dict] = results.get("insights", [])

    facility_summaries = [i for i in insights if i["type"] == "facility_summary"]
    total_cases = sum(i["total_cases"] for i in facility_summaries)
    avg_total = sum(i["avg_total_minutes"] * i["total_cases"] for i in facility_summaries) / max(total_cases, 1)
    cancel = next((i for i in insights if i["type"] == "cancellation_rate"), None)
    cancel_rate = f"{cancel['rate']:.1%}" if cancel else "N/A"
    cancel_count = cancel["count"] if cancel else 0
    n_facilities = len(facility_summaries)

    dp = results.get("discharge_predictor", {})
    rc = results.get("extended_recovery_classifier", {})

    fac_labels = [i["facility"] for i in facility_summaries]
    fac_volumes = [i["total_cases"] for i in facility_summaries]
    fac_avg = [round(i["avg_total_minutes"], 1) for i in facility_summaries]
    fac_colours = ["#58a6ff", "#a78bfa", "#3fb950"]

    top_procs = aggs.nlargest(10, "case_volume")
    proc_labels = [f"{r['procedure_type']} ({r['facility_id']})" for _, r in top_procs.iterrows()]
    proc_means = [round(r["dur_total_mean"], 1) for _, r in top_procs.iterrows()]
    proc_p90 = [round(r["dur_total_p90"], 1) for _, r in top_procs.iterrows()]

    phase_cols = ["dur_checkin_to_preop_mean", "dur_preop_to_op_mean",
                  "dur_op_to_postop_mean", "dur_postop_to_discharge_mean"]
    phase_nice = ["Check-in to Pre-op", "Pre-op to OR", "OR to PACU", "PACU to Discharge"]
    phase_colors = ["#58a6ff", "#a78bfa", "#f0883e", "#3fb950"]
    phase_datasets = []
    for col, nice, clr in zip(phase_cols, phase_nice, phase_colors):
        vals = []
        for fac in fac_labels:
            fac_rows = aggs[aggs["facility_id"] == fac]
            vals.append(round(fac_rows[col].mean(), 1))
        phase_datasets.append({"label": nice, "data": vals, "backgroundColor": clr})

    fi = dp.get("feature_importance", {})
    fi_sorted = sorted(fi.items(), key=lambda x: x[1], reverse=True)
    fi_labels = [k.replace("_enc", "").replace("dur_", "").replace("_", " ").title() for k, _ in fi_sorted]
    fi_values = [round(v * 100, 1) for _, v in fi_sorted]

    completed = total_cases
    canceled = cancel_count
    other = (cancel["total"] - completed - canceled) if cancel else 0

    charts_js = []
    parts = []

    tag_class = "tag-gpu" if gpu else "tag-cpu"
    tag_text = "GPU — RAPIDS" if gpu else "CPU"

    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Outpatient Flow Analytics Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>{REPORT_CSS}</style>
</head>
<body>

<div class="header">
  <h1>Outpatient Flow Analytics Report</h1>
  <div class="sub">
    <span>Generated {html.escape(ts[:19].replace("T"," "))} UTC</span>
    <span class="tag {tag_class}">{tag_text}</span>
  </div>
</div>
""")

    # KPIs
    parts.append('<div class="kpi-row">')
    parts.append(_kpi_card("Total Completed Cases", f"{total_cases:,}", f"across {n_facilities} facilities"))
    parts.append(_kpi_card("Avg Total Duration", f"{avg_total:.0f} min", "check-in to discharge", "#a78bfa"))
    parts.append(_kpi_card("Cancellation Rate", cancel_rate, f"{cancel_count} cancelled", "#f85149"))
    if dp:
        parts.append(_kpi_card("Discharge Prediction", f"R\u00b2 {dp.get('r2_score', 0):.2f}",
                                f"MAE {dp.get('mae_minutes', 0):.1f} min", "#3fb950"))
    if rc:
        parts.append(_kpi_card("Recovery Risk Model", f"AUC {rc.get('auc_score', 0):.2f}",
                                f"p90 threshold {rc.get('p90_threshold_minutes', 0):.0f} min", "#f0883e"))
    parts.append('</div>')

    # Charts
    parts.append('<div class="section"><h2>Facility and Procedure Analytics</h2><div class="chart-grid">')

    parts.append('<div class="chart-card"><div class="chart-wrap"><canvas id="c1"></canvas></div></div>')
    charts_js.append(_bar_chart("c1", fac_labels,
        [{"label": "Cases", "data": fac_volumes, "backgroundColor": fac_colours}],
        "Case Volume by Facility", "Cases"))

    parts.append('<div class="chart-card"><div class="chart-wrap"><canvas id="c2"></canvas></div></div>')
    charts_js.append(_bar_chart("c2", fac_labels,
        [{"label": "Avg Total (min)", "data": fac_avg, "backgroundColor": fac_colours}],
        "Average Total Duration by Facility"))

    parts.append('<div class="chart-card"><div class="chart-wrap"><canvas id="c3"></canvas></div></div>')
    charts_js.append(_bar_chart("c3", fac_labels, phase_datasets,
        "Duration Phase Breakdown by Facility", stacked=True))

    parts.append('<div class="chart-card"><div class="chart-wrap"><canvas id="c4"></canvas></div></div>')
    charts_js.append(_bar_chart("c4", proc_labels,
        [{"label": "Mean", "data": proc_means, "backgroundColor": "#58a6ff"},
         {"label": "p90", "data": proc_p90, "backgroundColor": "rgba(240,136,62,0.5)"}],
        "Top 10 Procedures — Mean vs p90 Duration"))

    parts.append('<div class="chart-card"><div class="chart-wrap"><canvas id="c5"></canvas></div></div>')
    charts_js.append(_doughnut_chart("c5",
        ["Completed", "Cancelled", "Other"],
        [completed, canceled, max(other, 0)],
        ["#3fb950", "#f85149", "#30363d"],
        "Case Status Distribution"))

    if fi_labels:
        parts.append('<div class="chart-card"><div class="chart-wrap"><canvas id="c6"></canvas></div></div>')
        charts_js.append(_bar_chart("c6", fi_labels,
            [{"label": "Importance %", "data": fi_values, "backgroundColor": "#a78bfa"}],
            "Discharge Model — Feature Importance", "Importance %"))

    parts.append('</div></div>')

    # ML Model cards
    parts.append('<div class="section"><h2>Machine Learning Models</h2><div class="model-grid">')
    if dp:
        accel = "GPU (RAPIDS + XGBoost)" if dp.get("gpu_used") else "CPU"
        parts.append(f"""
        <div class="model-card">
          <h3>Discharge Time Predictor</h3>
          <div class="metric-row"><span class="metric-label">Algorithm</span><span class="metric-value">{dp["model_type"]}</span></div>
          <div class="metric-row"><span class="metric-label">Mean Absolute Error</span><span class="metric-value">{dp["mae_minutes"]} min</span></div>
          <div class="metric-row"><span class="metric-label">R\u00b2 Score</span><span class="metric-value">{dp["r2_score"]}</span></div>
          <div class="metric-row"><span class="metric-label">Training / Test Split</span><span class="metric-value">{dp["n_train"]:,} / {dp["n_test"]:,}</span></div>
          <div class="metric-row"><span class="metric-label">Compute Backend</span><span class="metric-value">{accel}</span></div>
        </div>""")
    if rc:
        accel = "GPU (RAPIDS + XGBoost)" if rc.get("gpu_used") else "CPU"
        parts.append(f"""
        <div class="model-card">
          <h3>Extended Recovery Risk Classifier</h3>
          <div class="metric-row"><span class="metric-label">Algorithm</span><span class="metric-value">{rc["model_type"]}</span></div>
          <div class="metric-row"><span class="metric-label">AUC Score</span><span class="metric-value">{rc["auc_score"]}</span></div>
          <div class="metric-row"><span class="metric-label">p90 Threshold</span><span class="metric-value">{rc["p90_threshold_minutes"]} min</span></div>
          <div class="metric-row"><span class="metric-label">Training / Test Split</span><span class="metric-value">{rc["n_train"]:,} / {rc["n_test"]:,}</span></div>
          <div class="metric-row"><span class="metric-label">Compute Backend</span><span class="metric-value">{accel}</span></div>
        </div>""")
    parts.append('</div></div>')

    # ---------- Actionable Insights — tabbed interface ----------
    TAB_ORDER = [
        ("all", "All Findings"),
        ("bottleneck", "Bottlenecks"),
        ("high_variance", "Duration Variability"),
        ("late_starts", "Late Starts"),
        ("cross_facility", "Facility Comparisons"),
        ("cancellation_rate", "Cancellations"),
        ("facility_summary", "Facility Overviews"),
    ]

    grouped: Dict[str, list] = {}
    for ins in insights:
        grouped.setdefault(ins["type"], []).append(ins)
    n_high = sum(1 for i in insights if i.get("severity") == "high")
    n_med = sum(1 for i in insights if i.get("severity") == "medium")
    n_info = sum(1 for i in insights if i.get("severity") == "info")

    parts.append('<div class="insight-section">')
    parts.append('<h2>Actionable Insights</h2>')
    parts.append('<div class="insight-summary">')
    parts.append(f'<span>{len(insights)} findings across {n_facilities} facilities</span>')
    if n_high:
        parts.append(f'<span class="sev-badge"><span class="dot dot-high"></span>{n_high} high priority</span>')
    if n_med:
        parts.append(f'<span class="sev-badge"><span class="dot dot-med"></span>{n_med} need review</span>')
    if n_info:
        parts.append(f'<span class="sev-badge"><span class="dot dot-info"></span>{n_info} informational</span>')
    parts.append('</div>')

    # Tab bar
    parts.append('<div class="tab-bar">')
    for idx, (tab_key, tab_label) in enumerate(TAB_ORDER):
        count = len(insights) if tab_key == "all" else len(grouped.get(tab_key, []))
        if count == 0 and tab_key != "all":
            continue
        checked = ' checked' if idx == 0 else ''
        parts.append(f'<input class="tab-radio" type="radio" name="itab" id="itab-{tab_key}"{checked}/>')
        parts.append(f'<label class="tab-label" for="itab-{tab_key}">'
                     f'{html.escape(tab_label)}<span class="tab-count">{count}</span></label>')
    parts.append('</div>')

    # Tab panels — rendered as divs, toggled by JS (simpler than pure CSS sibling selectors for N tabs)
    def _render_cards(items: List[Dict]) -> str:
        """Render a list of insight cards as HTML."""
        out = []
        for ins in items:
            sev = ins.get("severity", "info")
            fac = ins.get("facility", "All")
            title = ins.get("title", ins.get("type", "").replace("_", " ").title())
            msg = ins.get("message", "")
            impact = ins.get("impact", "")
            action = ins.get("action", "")
            sev_label = {"high": "High Priority", "medium": "Needs Review", "info": "Informational"}.get(sev, sev)

            out.append(f'<div class="i-card">')
            out.append(f'<div class="i-head">'
                       f'<div class="i-sev i-sev-{sev}"></div>'
                       f'<span class="pill pill-{sev}">{html.escape(sev_label)}</span>'
                       f'<span class="i-title">{html.escape(title)}</span>'
                       f'<span class="i-facility">{html.escape(fac)}</span>'
                       f'</div>')
            out.append('<div class="i-body">')

            # What we found — always full width
            out.append(f'<div class="i-block i-block-full">'
                       f'<div class="i-block-label">What we found</div>'
                       f'{html.escape(msg)}</div>')

            # Why it matters + What to do — side by side
            if impact:
                out.append(f'<div class="i-block i-block-impact">'
                           f'<div class="i-block-label">Why it matters</div>'
                           f'{html.escape(impact)}</div>')
            if action:
                out.append(f'<div class="i-block i-block-action">'
                           f'<div class="i-block-label">Recommended actions</div>'
                           f'{html.escape(action)}</div>')

            out.append('</div></div>')  # close i-body, i-card
        return "\n".join(out)

    for tab_key, _ in TAB_ORDER:
        items = insights if tab_key == "all" else grouped.get(tab_key, [])
        if not items and tab_key != "all":
            continue
        display = "block" if tab_key == "all" else "none"
        parts.append(f'<div class="tab-panel" id="panel-{tab_key}" style="display:{display}">')
        parts.append(_render_cards(items))
        parts.append('</div>')

    # Tiny JS for tab switching (no external deps)
    parts.append("""<script>
document.querySelectorAll('input[name="itab"]').forEach(radio=>{
  radio.addEventListener('change',()=>{
    document.querySelectorAll('.tab-panel').forEach(p=>p.style.display='none');
    const id=radio.id.replace('itab-','panel-');
    const panel=document.getElementById(id);
    if(panel)panel.style.display='block';
  });
});
</script>""")

    parts.append('</div>')  # close insight-section

    # Top procedures table
    parts.append('<div class="section"><h2>Top 20 Procedures by Volume</h2><table>')
    parts.append('<tr><th>Facility</th><th>Procedure</th><th class="num">Volume</th>'
                 '<th class="num">Mean</th><th class="num">Median</th>'
                 '<th class="num">p90</th><th class="num">\u03c3</th><th class="num">Late Start</th></tr>')
    for _, r in aggs.nlargest(20, "case_volume").iterrows():
        late_pct = f"{r.get('late_start_rate', 0):.0%}" if pd.notna(r.get("late_start_rate")) else "\u2014"
        parts.append(
            f'<tr><td>{html.escape(str(r["facility_id"]))}</td>'
            f'<td>{html.escape(str(r["procedure_type"]))}</td>'
            f'<td class="num">{int(r["case_volume"])}</td>'
            f'<td class="num">{r["dur_total_mean"]:.1f}</td>'
            f'<td class="num">{r["dur_total_median"]:.1f}</td>'
            f'<td class="num">{r["dur_total_p90"]:.1f}</td>'
            f'<td class="num">{r["dur_total_std"]:.1f}</td>'
            f'<td class="num">{late_pct}</td></tr>')
    parts.append('</table></div>')

    # Footer
    parts.append(f"""
<div class="footer">
  Outpatient Flow Analytics &middot; OpenShift 4.21 &middot;
  {total_cases:,} cases &middot; {len(aggs)} facility/procedure combinations &middot;
  {"GPU (RAPIDS)" if gpu else "CPU"} backend
</div>
""")

    parts.append("\n".join(charts_js))
    parts.append("</body></html>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate HTML analytics report")
    parser.add_argument("--results", type=str, default="output/analytics/analytics_results.json",
                        help="Path to analytics_results.json")
    parser.add_argument("--aggregates", type=str, default="output/analytics/aggregates.csv",
                        help="Path to aggregates.csv")
    parser.add_argument("--output", type=str, default="output/analytics/report.html",
                        help="Output HTML file path")
    args = parser.parse_args()

    with open(args.results) as f:
        results = json.load(f)
    aggs = pd.read_csv(args.aggregates)

    report_html = build_report(results, aggs)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        f.write(report_html)
    logger.info("Report written to %s (%d KB)", args.output, len(report_html) // 1024)


if __name__ == "__main__":
    main()
