"""
Build the dashboard page from the template, the engine and the market catalogue.

The page carries the backtest engine (backtest.js, the same engine as the Python
research code) and the small catalogue of markets. Each market's prices are
loaded from data/ only when you pick it, so the page stays small.

    python build_page.py

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "dashboard_template.html")
ENGINE = os.path.join(HERE, "backtest.js")
CATALOGUE = os.path.join(ROOT, "data", "catalogue.json")

cat = json.load(open(CATALOGUE, encoding="utf-8")) if os.path.exists(CATALOGUE) else \
    {"built": "not built", "securities": [], "indices": []}
engine = open(ENGINE, encoding="utf-8").read()
if "</script" in engine:
    raise ValueError("backtest.js must not contain a closing script tag")
html = open(TEMPLATE, encoding="utf-8").read()
html = html.replace("/*__ENGINE__*/", engine).replace("__CATALOGUE__", json.dumps(cat))
for name in ("index.html", "Agora Dashboard.html"):
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as fh:
        fh.write(html)
n = len(cat.get("securities", [])) + len(cat.get("indices", []))
print(f"Built the page ({len(html) // 1024} KB) with the engine and a catalogue of {n} markets, built {cat.get('built')}")
