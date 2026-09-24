"""
MARKET DATA. Download prices for the whole universe and store them, one file per market.

Every market is saved in the SAME strict bar format (time, open, high, low, close,
volume), so nothing downstream needs to know where a bar came from. A strategy
just reads bars. Real company, real index, or a synthetic market, all look the same.

The rules this file follows, so the backtest cannot cheat:
  * Times are in the exchange's own time zone (New York for US shares, London for
    the FTSE), so 09:30 means the opening bell. A bar is labelled by the time it
    STARTS. Its close is only known once the bar has ended.
  * A bar that has not finished yet (today's daily bar while the market is open, or
    the current minute) is dropped. It is not a real bar yet.
  * Prices are split adjusted (that is how the source gives them). Dividends and
    splits are saved separately, as events, so the tester can pay dividends on the
    day they happen instead of baking them into past prices.
  * Every bar is checked. High must be the highest price, low the lowest, times
    must go forward, and nothing can be zero or negative.

    python fetch_data.py

Writes data/daily/<symbol>.json, data/intraday/<symbol>_<interval>.json and
data/catalogue.json. Re-run it any time to refresh. Coding done with the help of AI.
"""
import json
import os
import time
import urllib.request
from urllib.parse import quote
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import universe as U

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DAILY = os.path.join(ROOT, "data", "daily")
INTRADAY = os.path.join(ROOT, "data", "intraday")
CATALOGUE = os.path.join(ROOT, "data", "catalogue.json")

# intraday interval -> how far back the free source goes
INTRADAY_KINDS = {"1m": "7d", "1h": "60d"}
SECONDS = {"1m": 60, "1h": 3600}

PRICE_BASIS = ("Open, high, low, close and volume are split adjusted. 'a' is the close "
               "adjusted for splits and dividends, kept only for checking. Dividends and "
               "splits are listed as events. Times are the exchange's local time and "
               "label the START of each bar.")


def _fetch(symbol, rng, interval):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + quote(symbol)
           + "?range=" + rng + "&interval=" + interval + "&events=div,splits")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    return json.loads(raw)["chart"]["result"][0]


def _zone(res):
    return ZoneInfo(res["meta"].get("exchangeTimezoneName") or "UTC")


def _local(ts, tz, intraday):
    t = datetime.fromtimestamp(ts, timezone.utc).astimezone(tz)
    return t.strftime("%Y-%m-%d %H:%M") if intraday else t.date().isoformat()


def validate(bars, intraday, crypto):
    """Check every bar and fix or drop the bad ones. Returns (clean bars, report)."""
    clean, fixed, dropped = [], 0, 0
    for b in bars:
        if min(b["o"], b["h"], b["l"], b["c"]) <= 0 or b["v"] < 0:
            dropped += 1                                  # a price of zero is a data error
            continue
        if intraday and not crypto and b["v"] == 0 and b["o"] == b["h"] == b["l"] == b["c"]:
            dropped += 1                                  # an empty stub bar, not real trading
            continue
        hi, lo = max(b["o"], b["h"], b["l"], b["c"]), min(b["o"], b["h"], b["l"], b["c"])
        if hi != b["h"] or lo != b["l"]:
            b["h"], b["l"] = hi, lo                       # high must be the highest, low the lowest
            fixed += 1
        if clean and b["d"] <= clean[-1]["d"]:
            if b["d"] == clean[-1]["d"]:
                clean[-1] = b                             # same time twice, keep the later one
            dropped += 1
            continue
        clean.append(b)
    return clean, {"fixed": fixed, "dropped": dropped}


def _bars_from(res, intraday, interval):
    """Turn a source result into our plain bar list, dropping unfinished bars."""
    tz = _zone(res)
    ts, q = res.get("timestamp") or [], res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    vols = q.get("volume") or [None] * len(ts)
    now = time.time()
    regular_end = ((res["meta"].get("currentTradingPeriod") or {}).get("regular") or {}).get("end", 0)
    today = datetime.fromtimestamp(now, timezone.utc).astimezone(tz).date().isoformat()
    bars = []
    for i, t in enumerate(ts):
        c = q["close"][i]
        if c is None:
            continue
        if intraday and t + SECONDS[interval] > now:
            continue                                      # this bar has not finished yet
        o = q["open"][i] if q["open"][i] is not None else c
        h = q["high"][i] if q["high"][i] is not None else c
        l = q["low"][i] if q["low"][i] is not None else c
        v = vols[i]
        d = _local(t, tz, intraday)
        if not intraday and d == today and now < regular_end:
            continue                                      # today's daily bar is still forming
        bar = {"d": d, "o": round(o, 4), "h": round(h, 4), "l": round(l, 4),
               "c": round(c, 4), "v": int(v) if v else 0}
        if not intraday and adj and adj[i] is not None:
            bar["a"] = round(adj[i], 4)
        bars.append(bar)
    return bars


def _events(res):
    """Dividends and splits, dated in the exchange's time zone."""
    tz, ev = _zone(res), res.get("events") or {}
    divs = [{"d": _local(x["date"], tz, False), "amount": round(x["amount"], 6)}
            for x in (ev.get("dividends") or {}).values()]
    splits = [{"d": _local(x["date"], tz, False), "ratio": x["numerator"] / x["denominator"]}
              for x in (ev.get("splits") or {}).values()]
    return sorted(divs, key=lambda x: x["d"]), sorted(splits, key=lambda x: x["d"])


def save_daily(symbol, name, group, benchmark, is_index, years=10):
    res = _fetch(symbol, str(years) + "y", "1d")
    crypto = group == "Crypto"
    bars, report = validate(_bars_from(res, False, "1d"), False, crypto)
    if not bars:                                          # keep the old file if the download was empty
        raise ValueError("no bars")
    divs, splits = _events(res)
    meta = res["meta"]
    obj = {"symbol": symbol, "name": name, "group": group, "currency": meta.get("currency", "USD"),
           "benchmark": benchmark, "is_index": is_index, "interval": "1d",
           "timezone": meta.get("exchangeTimezoneName", "UTC"),
           "days_per_year": 365 if crypto else 252, "price_basis": PRICE_BASIS,
           "quality": report, "dividends": divs, "splits": splits, "bars": bars}
    os.makedirs(DAILY, exist_ok=True)
    with open(os.path.join(DAILY, U.safe_name(symbol) + ".json"), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, separators=(",", ":"))
    return obj


def save_intraday(symbol, crypto):
    """Save the recent intraday demo files, and return the intervals that worked."""
    os.makedirs(INTRADAY, exist_ok=True)
    got = []
    for interval, rng in INTRADAY_KINDS.items():
        try:
            res = _fetch(symbol, rng, interval)
            bars, report = validate(_bars_from(res, True, interval), True, crypto)
            if not bars:
                continue
            path = os.path.join(INTRADAY, U.safe_name(symbol) + "_" + interval + ".json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"symbol": symbol, "interval": interval,
                           "timezone": res["meta"].get("exchangeTimezoneName", "UTC"),
                           "days_per_year": 365 if crypto else 252, "quality": report,
                           "bars": bars}, fh, separators=(",", ":"))
            got.append(interval)
        except Exception as e:
            print(f"      intraday {interval} FAILED  {type(e).__name__} {e}")
        time.sleep(0.4)
    return got


def main():
    rows = [(s, n, g, b, False) for (s, n, g, b) in U.SECURITIES] + \
           [(s, n, "Index", None, True) for (s, n) in U.INDICES]
    catalogue = {"built": date.today().isoformat(), "price_basis": PRICE_BASIS,
                 "securities": [], "indices": []}
    for symbol, name, group, benchmark, is_index in rows:
        try:
            obj = save_daily(symbol, name, group, benchmark, is_index)
            bars = obj["bars"]
            intraday = save_intraday(symbol, group == "Crypto") if symbol in U.INTRADAY_DEMO else []
            meta = {"symbol": symbol, "name": name, "group": group, "benchmark": benchmark,
                    "is_index": is_index, "file": "data/daily/" + U.safe_name(symbol) + ".json",
                    "currency": obj["currency"], "timezone": obj["timezone"],
                    "days": len(bars), "first": bars[0]["d"], "last": bars[-1]["d"],
                    "last_close": bars[-1]["c"], "dividends": len(obj["dividends"]),
                    "splits": len(obj["splits"]), "intraday": intraday}
            (catalogue["indices"] if is_index else catalogue["securities"]).append(meta)
            q = obj["quality"]
            extra = ("  intraday " + "/".join(intraday)) if intraday else ""
            checks = f"  fixed {q['fixed']} dropped {q['dropped']}" if (q["fixed"] or q["dropped"]) else ""
            print(f"  {name:22} {len(bars):>5} days  {bars[0]['d']} -> {bars[-1]['d']}"
                  f"  divs {len(obj['dividends']):>2} splits {len(obj['splits'])}{checks}{extra}")
        except Exception as e:
            print(f"  {name:22} FAILED  {type(e).__name__} {e}")
        time.sleep(0.4)
    os.makedirs(os.path.dirname(CATALOGUE), exist_ok=True)
    with open(CATALOGUE, "w", encoding="utf-8") as fh:
        json.dump(catalogue, fh, indent=1)
    print(f"\n{len(catalogue['securities'])} securities and {len(catalogue['indices'])} indices saved.")


if __name__ == "__main__":
    main()
