"""
Report Viewer — lightweight web UI for browsing analytics reports.

Serves a landing page that lists all generated HTML reports and lets
users open them directly in the browser.  Designed to run as a sidecar
or standalone pod alongside the analytics output PVC.

Usage:
    python -m src.viewer.app --report-dir output/analytics --port 8080
"""

import argparse
import html as html_mod
import logging
import os
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


LANDING_CSS = """
:root { --bg:#0d1117; --surface:#161b22; --border:#30363d; --text:#c9d1d9;
        --muted:#8b949e; --accent:#58a6ff; --green:#3fb950; --purple:#a78bfa; }
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
     background:var(--bg);color:var(--text);min-height:100vh;display:flex;
     flex-direction:column;align-items:center;padding:48px 24px}

/* Header */
.header{text-align:center;margin-bottom:40px}
.header h1{font-size:22px;font-weight:600;letter-spacing:-0.3px;margin-bottom:6px}
.header .subtitle{color:var(--muted);font-size:13px}
.header .counts{color:var(--muted);font-size:12px;margin-top:8px;display:flex;
                justify-content:center;gap:20px}
.header .counts span{display:flex;align-items:center;gap:6px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot-html{background:var(--accent)}
.dot-json{background:var(--purple)}

/* Card grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));
      gap:12px;width:100%;max-width:960px}
a.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;
       padding:20px 24px;text-decoration:none;color:var(--text);transition:border-color .15s,box-shadow .15s}
a.card:hover{border-color:var(--accent);box-shadow:0 2px 8px rgba(88,166,255,.1)}
.card-title{font-size:14px;font-weight:600;margin-bottom:6px;display:flex;align-items:center;gap:8px}
.card-meta{color:var(--muted);font-size:12px;display:flex;gap:16px}
.tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600;
     letter-spacing:0.4px;text-transform:uppercase}
.tag-html{background:rgba(88,166,255,.12);color:var(--accent)}
.tag-json{background:rgba(167,139,250,.12);color:var(--purple)}

/* Empty state */
.empty{color:var(--muted);font-size:14px;margin-top:48px;text-align:center;
       max-width:400px;line-height:1.6}
.empty strong{color:var(--text);display:block;margin-bottom:4px}

/* Footer */
.footer{color:var(--muted);font-size:11px;margin-top:auto;padding-top:48px;letter-spacing:0.2px}
"""


def build_landing(report_dir: str) -> str:
    """Build the landing page HTML listing all report files."""
    reports = []
    report_path = Path(report_dir)

    for f in sorted(report_path.rglob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        rel = f.relative_to(report_path)
        stat = f.stat()
        size_kb = stat.st_size / 1024
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        reports.append((str(rel), f.stem, size_kb, mtime))

    json_files = []
    for f in sorted(report_path.rglob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        rel = f.relative_to(report_path)
        stat = f.stat()
        json_files.append((str(rel), f.stem, stat.st_size / 1024,
                           datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)))

    cards_html = []
    for rel, name, size_kb, mtime in reports:
        nice_name = name.replace("_", " ").replace("-", " ").title()
        cards_html.append(f"""
        <a class="card" href="/reports/{quote(rel)}" target="_blank">
          <div class="card-title">{html_mod.escape(nice_name)} <span class="tag tag-html">HTML</span></div>
          <div class="card-meta">
            <span>{html_mod.escape(rel)}</span>
            <span>{size_kb:.0f} KB</span>
            <span>{mtime.strftime('%Y-%m-%d %H:%M')} UTC</span>
          </div>
        </a>""")

    for rel, name, size_kb, mtime in json_files:
        nice_name = name.replace("_", " ").replace("-", " ").title()
        cards_html.append(f"""
        <a class="card" href="/reports/{quote(rel)}" target="_blank">
          <div class="card-title">{html_mod.escape(nice_name)} <span class="tag tag-json">JSON</span></div>
          <div class="card-meta">
            <span>{html_mod.escape(rel)}</span>
            <span>{size_kb:.0f} KB</span>
            <span>{mtime.strftime('%Y-%m-%d %H:%M')} UTC</span>
          </div>
        </a>""")

    if not cards_html:
        cards_html.append(
            '<div class="empty"><strong>No reports available</strong>'
            'Run the analytics pipeline to generate reports.</div>')

    count_section = f"""
    <div class="counts">
      <span><span class="dot dot-html"></span>{len(reports)} report{"s" if len(reports) != 1 else ""}</span>
      <span><span class="dot dot-json"></span>{len(json_files)} data file{"s" if len(json_files) != 1 else ""}</span>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Report Viewer — Outpatient Flow Analytics</title>
<style>{LANDING_CSS}</style>
</head>
<body>
  <div class="header">
    <h1>Outpatient Flow Analytics</h1>
    <div class="subtitle">Report Viewer</div>
    {count_section}
  </div>
  <div class="grid">
    {"".join(cards_html)}
  </div>
  <div class="footer">Outpatient Flow Analytics &middot; OpenShift 4.21</div>
</body>
</html>"""


class ReportHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves the landing page and report files."""

    report_dir: str = "output/analytics"

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            content = build_landing(self.report_dir).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path.startswith("/reports/"):
            rel = self.path[len("/reports/"):]
            file_path = Path(self.report_dir) / rel
            if file_path.is_file() and file_path.resolve().is_relative_to(Path(self.report_dir).resolve()):
                content = file_path.read_bytes()
                ctype = "text/html" if file_path.suffix == ".html" else \
                        "application/json" if file_path.suffix == ".json" else \
                        "text/csv" if file_path.suffix == ".csv" else "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", f"{ctype}; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Report not found")
        elif self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        logger.info(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description="Report Viewer Web UI")
    parser.add_argument("--report-dir", type=str, default="output/analytics",
                        help="Directory containing analytics reports")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind address")
    args = parser.parse_args()

    ReportHandler.report_dir = os.path.abspath(args.report_dir)
    server = HTTPServer((args.host, args.port), ReportHandler)
    logger.info("Report viewer running at http://%s:%d (serving %s)", args.host, args.port, args.report_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
