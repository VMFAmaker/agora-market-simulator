"""
The page (backtest.js) and the research (the Python engine) must agree. This runs
the same experiments through both and checks every number matches.

    python tests/test_parity.py

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import execution
import sizing
import tester
from backtest import Config

CASES = [
    {"strategy": "sma", "symbol": "MSFT", "bench": "^IXIC", "method": "backtest", "sizing": ["percent", 1.0], "robustness": True},
    {"strategy": "rsi", "symbol": "AAPL", "bench": "^IXIC", "method": "backtest", "sizing": ["percent", 0.5],
     "params": {"stop_loss": 0.05, "take_profit": 0.10}},
    {"strategy": "mom", "symbol": "NVDA", "bench": "^IXIC", "method": "out_of_sample", "sizing": ["percent", 1.0]},
    {"strategy": "sma", "symbol": "JPM", "bench": "^GSPC", "method": "walk_forward", "sizing": ["percent", 1.0]},
    {"strategy": "dip", "symbol": "KO", "bench": "^SP500TR", "method": "backtest", "sizing": ["volatility", 0.01]},
    {"strategy": "brk", "symbol": "TSLA", "bench": None, "method": "backtest", "sizing": ["amount", 20000],
     "allow_short": True, "max_leverage": 1.5},
    {"strategy": "mr", "symbol": "BTC-USD", "bench": "^GSPC", "method": "backtest", "sizing": ["percent", 1.0],
     "execution": {"fill_at": "close", "slippage_bps": 10}},
    {"strategy": "bh", "symbol": "WMT", "bench": "^SP500TR", "method": "backtest", "sizing": ["percent", 1.0], "zero": True,
     "start": "2019-01-01", "end": "2023-12-31"},
]


def python_side(c):
    ex = execution.preset("zero") if c.get("zero") else execution.Execution(**c.get("execution", {}))
    cfg = Config(sizing=sizing.make(*c["sizing"]), execution=ex, allow_short=c.get("allow_short", False),
                 max_leverage=c.get("max_leverage", 1.0))
    exp = tester.Experiment(c["strategy"], params=c.get("params"), symbols=[c["symbol"]],
                            benchmark=c["bench"], method=c["method"], config=cfg,
                            start=c.get("start"), end=c.get("end"))
    res = tester.run(exp, robustness=c.get("robustness", False))
    m = res["main"]["metrics"]
    return {"total_return": m["total_return"], "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"],
            "trades": m["trades"], "fills": len(res["main"]["fills"]), "end_value": m["end_value"],
            "costs": m["costs"], "dividends": m["dividends"], "excess_cagr": m.get("excess_cagr"),
            "win_rate": m["win_rate"], "open_trades": m["open_trades"],
            "folds": [f["params"] for f in res["folds"]] if "folds" in res else None,
            "chosen": res.get("chosen"),
            "robustness": [r["cagr"] for r in res["robustness"]["costs"]] if "robustness" in res else None}


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    return a == b


def test_browser_engine_matches_python():
    for c in CASES:
        c.setdefault("robustness", False)
    js = json.loads(subprocess.run(["node", os.path.join(HERE, "parity.js"), json.dumps(CASES)],
                                   capture_output=True, text=True, check=True).stdout)
    bad = []
    for c, j in zip(CASES, js):
        p = python_side(c)
        for k in p:
            if not close(p[k], j[k]):
                bad.append(f"{c['strategy']} on {c['symbol']} ({c['method']}): {k} python {p[k]} vs browser {j[k]}")
        print(f"  {c['strategy']:4} {c['symbol']:8} {c['method']:14} return {p['total_return']:+9.2%}  "
              f"fills {p['fills']:4}  {'same' if not any(c['symbol'] in b and c['strategy'] in b for b in bad) else 'DIFFERENT'}")
    assert not bad, "\n".join(bad)


if __name__ == "__main__":
    try:
        test_browser_engine_matches_python()
        print("\nThe browser engine and the Python engine agree on every number.")
    except AssertionError as e:
        print("\nMISMATCH\n" + str(e))
        sys.exit(1)
