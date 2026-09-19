"""
Download daily history for the whole universe and store it, one file per market.

Every market is saved in the SAME simple bar format, so nothing downstream needs
to know or care where a bar came from. This is the point: a strategy just reads
bars. Real company, real index, or a synthetic market later, all look the same.

    python fetch_data.py

Writes data/daily/<symbol>.json for each market, and data/catalogue.json listing
them all. Re-run it any time to refresh. Coding done with the help of AI.
"""
import json
import os
import time
import urllib.request
from urllib.parse import quote
from datetime import date

import universe as U

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DAILY = os.path.join(ROOT, "data", "daily")
CATALOGUE = os.path.join(ROOT, "data", "catalogue.json")


def fetch_daily(symbol, years=10):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + quote(symbol) + "?range=" + str(years) + "y&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    res = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore"))["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    currency = res["meta"].get("currency", "USD")
    bars = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        o = q["open"][i] if q["open"][i] is not None else c
        h = q["high"][i] if q["high"][i] is not None else c
        l = q["low"][i] if q["low"][i] is not None else c
        v = (q.get("volume") or [None] * len(ts))[i]
        bars.append({"d": date.fromtimestamp(t).isoformat(), "o": round(o, 4), "h": round(h, 4),
                     "l": round(l, 4), "c": round(c, 4), "v": int(v) if v else 0})
    return currency, bars


def save(symbol, name, group, benchmark, is_index):
    currency, bars = fetch_daily(symbol)
    if not bars:                                  # keep the old file if the download was empty
        raise ValueError("no bars")
    obj = {"symbol": symbol, "name": name, "group": group, "currency": currency,
           "benchmark": benchmark, "is_index": is_index, "bars": bars}
    os.makedirs(DAILY, exist_ok=True)
    with open(os.path.join(DAILY, U.safe_name(symbol) + ".json"), "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return {"symbol": symbol, "name": name, "group": group, "benchmark": benchmark,
            "is_index": is_index, "file": "data/daily/" + U.safe_name(symbol) + ".json",
            "currency": currency, "days": len(bars), "first": bars[0]["d"], "last": bars[-1]["d"],
            "last_close": bars[-1]["c"]}


def main():
    rows = [(s, n, g, b, False) for (s, n, g, b) in U.SECURITIES] + \
           [(s, n, "Index", None, True) for (s, n) in U.INDICES]
    catalogue = {"built": date.today().isoformat(), "securities": [], "indices": []}
    for symbol, name, group, benchmark, is_index in rows:
        try:
            meta = save(symbol, name, group, benchmark, is_index)
            (catalogue["indices"] if is_index else catalogue["securities"]).append(meta)
            print(f"  {name:20} {meta['days']:>5} days  {meta['first']} -> {meta['last']}  last {meta['last_close']}")
        except Exception as e:
            print(f"  {name:20} FAILED  {type(e).__name__} {e}")
        time.sleep(0.4)
    os.makedirs(os.path.dirname(CATALOGUE), exist_ok=True)
    with open(CATALOGUE, "w", encoding="utf-8") as fh:
        json.dump(catalogue, fh, indent=1)
    print(f"\n{len(catalogue['securities'])} securities and {len(catalogue['indices'])} indices saved.")


if __name__ == "__main__":
    main()
