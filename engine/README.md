# Agora, the engine

Agora tests trading rules on real markets and on made up ones, with one backtest
engine for both. It is split into four parts, the way professional backtesting
systems are, and one rule holds them together. **A strategy never knows whether
its prices are real or simulated.** It just receives bars.

> Coding was done with the help of AI. I am not proficient at coding, so I set the
> direction, made the decisions, and tested the results. The code is kept simple
> and heavily commented so that I can read it.

## The four parts

| Part | Files | What it does |
| --- | --- | --- |
| **Market data** | `universe.py`, `fetch_data.py`, `market_data.py` | Downloads 29 companies and 6 indices, checks every bar, stores them in one strict shape, and gives strategies a history that stops at "now". |
| **Strategy engine** | `indicators.py`, `strategies.py` | Seven rules. Each one only turns bars into a signal (BUY, SELL or HOLD, with a reason). |
| **Market simulator** | `simulator.py`, `agora.py` | Six controlled synthetic markets for stress tests, and the full agent based order book model for study. |
| **Strategy tester** | `sizing.py`, `execution.py`, `portfolio.py`, `backtest.py`, `metrics.py`, `tester.py` | Sizes the order, fills it with costs, keeps the account, runs experiments and measures them. |
| Research report | `run_research.py` | Runs the whole study and draws the charts for the Word report. |
| The web page | `backtest.js`, `dashboard_template.html`, `build_page.py` | The same engine in JavaScript, and the page that uses it. |

## The rules that stop a backtest cheating

**The time frontier.** `backtest.py` walks through history one bar at a time. A bar
only reaches the strategy once it has closed, and any order is filled at the NEXT
bar's open. At 10.35 a strategy knows the 10.35 close and nothing after it. The
history object is filled one bar at a time, so a bar that has not arrived yet is
simply not there to peek at.

**Which price.** Prices are split adjusted, so every percentage move is real.
Dividends are stored as events and paid into the account as cash on the ex-dividend
day. The dividend adjusted close is kept only as a check, because it rewrites past
prices with dividends that were paid later.

**Strict data.** Times are in the exchange's own time zone and label the start of
each bar. Unfinished bars are dropped. Every bar is checked (high is the highest,
low the lowest, times move forward, nothing is zero).

**Signal, order, fill.** A strategy only says BUY. `sizing.py` decides how much,
`portfolio.py` applies the limits (most in one asset, leverage, whole shares), and
`execution.py` decides the fill price and every cost, the bid and ask spread,
slippage, square root market impact, commission, and a cap on the share of daily
volume one order can take.

## Proof

```
python tests/test_engine.py     # 12 tests, including cutting off the future
python tests/test_parity.py     # the browser engine and the Python engine agree
```

The key test runs a strategy on ten years of Microsoft, then again with everything
after a cut off deleted, at four cut offs. The trades and the account before each
cut off are identical. If the engine leaked the future, deleting it would change the past.

## Run it

```
pip install -r requirements.txt
python fetch_data.py          # download the whole universe (needs internet)
python build_page.py          # build the website page
python run_research.py        # the full study, about four minutes
python run_simulation.py      # optional: the full agent model
```

Or from Python:

```python
from tester import Experiment, run
res = run(Experiment("sma", symbols=["MSFT"], benchmark="^SP500TR", method="walk_forward"))
print(res["main"]["metrics"]["cagr"], res["efficiency"])
```

The methods are `backtest`, `out_of_sample`, `walk_forward` and `stress`, and every
result also carries robustness checks (the same test at five levels of slippage, and
next open fills against same close fills).

## The traders (in the agent model, agora.py)

**Noise** random flow, **market maker** quoting both sides, **momentum** buying
strength, **value** buying cheap and selling dear, and, in the busier scenarios,
**leveraged trend, mean reversion, breakout, news, whale and panic herd**. The model
checks that its market shows the two facts every real market shows, fat tails and
volatility clustering.
