"""
Build the dashboard page from the template and the market catalogue.

The page no longer carries every price. It carries the small catalogue (the list
of markets), and it loads each market's prices from data/ only when you pick it.
So the file stays small and the page follows the whole universe.

    python build_page.py

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "dashboard_template.html")
CATALOGUE = os.path.join(ROOT, "data", "catalogue.json")

cat = json.load(open(CATALOGUE, encoding="utf-8")) if os.path.exists(CATALOGUE) else \
    {"built": "not built", "securities": [], "indices": []}
html = open(TEMPLATE, encoding="utf-8").read().replace("__CATALOGUE__", json.dumps(cat))
for name in ("index.html", "Agora Dashboard.html"):
    open(os.path.join(ROOT, name), "w", encoding="utf-8").write(html)
n = len(cat.get("securities", [])) + len(cat.get("indices", []))
print(f"Built the page with a catalogue of {n} markets, built {cat.get('built')}")
