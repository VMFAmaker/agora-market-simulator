"""
Build the dashboard page from the template and the latest real prices.

This just pours output/real_markets.json into dashboard_template.html and writes
index.html (what the website serves) and Agora Dashboard.html. It needs nothing
except plain Python, so the daily refresh job can run it quickly.

    python build_page.py

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "dashboard_template.html")
REAL = os.path.join(ROOT, "output", "real_markets.json")

real = json.load(open(REAL, encoding="utf-8")) if os.path.exists(REAL) else \
    {"fetched": "not downloaded", "usd_to_gbp": 0.79, "instruments": []}
html = open(TEMPLATE, encoding="utf-8").read().replace("__REAL_DATA__", json.dumps(real))
for name in ("index.html", "Agora Dashboard.html"):
    open(os.path.join(ROOT, name), "w", encoding="utf-8").write(html)
print("Built the page with real data from", real.get("fetched"))
