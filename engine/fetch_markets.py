"""
Download real market prices and save them for the dashboard.

Pulls about two years of daily prices for ten well known markets from Yahoo
Finance, and writes them to output/real_markets.json. Re-run this whenever you
want fresher prices. The dashboard reads this file when you build it.

    python fetch_markets.py

Coding done with the help of AI, because coding is not the author's strong area.
"""

import json
import os
import time
import urllib.request
from urllib.parse import quote
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "output", "real_markets.json")

# yahoo symbol, friendly name, group
MARKETS = [
    ("AAPL", "Apple", "Stocks"),
    ("MSFT", "Microsoft", "Stocks"),
    ("GC=F", "Gold", "Commodities"),
    ("CL=F", "Crude Oil", "Commodities"),
    ("NG=F", "Natural Gas", "Natural resources"),
    ("HG=F", "Copper", "Natural resources"),
    ("EURUSD=X", "Euro / Dollar", "Currencies"),
    ("GBPUSD=X", "Pound / Dollar", "Currencies"),
    ("BTC-USD", "Bitcoin", "Crypto"),
    ("ETH-USD", "Ethereum", "Crypto"),
]


def fetch_one(symbol):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + quote(symbol) + "?range=2y&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    res = json.loads(raw)["chart"]["result"][0]
    times = res["timestamp"]
    q = res["indicators"]["quote"][0]
    currency = res["meta"].get("currency", "USD")
    candles = []
    for i, ts in enumerate(times):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        v = q.get("volume", [None] * len(times))[i]
        if c is None:                       # skip missing days
            continue
        o = o if o is not None else c
        h = h if h is not None else c
        l = l if l is not None else c
        candles.append({
            "t": len(candles),              # simple 0,1,2 index for the chart
            "d": date.fromtimestamp(ts).isoformat(),
            "o": round(o, 4), "h": round(h, 4), "l": round(l, 4), "c": round(c, 4),
            "v": int(v) if v else 0,
        })
    return currency, candles


def main():
    instruments = []
    gbp_rate = 1.27                          # pounds per dollar fallback
    for symbol, name, group in MARKETS:
        try:
            currency, candles = fetch_one(symbol)
            instruments.append({"symbol": symbol, "name": name, "group": group,
                                "currency": currency, "candles": candles})
            print(f"  {name:16} {len(candles):>4} days   {candles[0]['d']} -> {candles[-1]['d']}"
                  f"   last {candles[-1]['c']}")
            if symbol == "GBPUSD=X":
                gbp_rate = 1.0 / candles[-1]["c"]   # dollars->pounds
        except Exception as e:
            print(f"  {name:16} FAILED  {type(e).__name__} {e}")
        time.sleep(0.5)                      # be gentle on the server

    data = {"fetched": date.today().isoformat(), "usd_to_gbp": round(gbp_rate, 4),
            "instruments": instruments}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    print(f"\nSaved {len(instruments)} markets to {OUT}")


if __name__ == "__main__":
    main()
