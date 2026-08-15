# Agora, a simple agent based market simulator

Instead of drawing a price from a formula, Agora creates a crowd of little
software traders, each following one simple rule, and lets them buy and sell from
each other on an order book. The price is just whatever they last traded at. Out
of all these simple rules, realistic looking market behaviour appears on its own.

The whole model lives in **one file, `agora.py`**, written to be read top to
bottom. Coding was done with the help of AI, because coding is not the author's
strong area.

## Run it

```
pip install -r requirements.txt
python fetch_markets.py            # download real prices (needs internet)
python run_simulation.py           # run the model and build the page
python run_simulation.py 7         # a different random seed
```

`fetch_markets.py` downloads real daily prices for ten markets and saves them to
`output/real_markets.json`. Run it again whenever you want fresher prices.
`run_simulation.py` then runs the four made-up scenarios, saves the numbers, and
builds `Agora Dashboard.html` in the folder above, with both the simulation and
the real prices baked in. Open that file in any browser.

The dashboard has a **Simulation / Real market** switch at the top. Simulation is
the agent model and plays live. Real market shows the actual prices, which you
just scroll through (no fast-forward). The strategy tester works on either one.

## What is inside

| File | What it does |
| --- | --- |
| `agora.py` | The whole simulator. Order book, traders, the clock, and the checks. |
| `fetch_markets.py` | Downloads real daily prices from Yahoo Finance. |
| `run_simulation.py` | Runs the scenarios and builds the dashboard page. |
| `dashboard_template.html` | The web page. `run_simulation.py` fills in the numbers. |

Inside `agora.py`, in order: the settings (`Config`), the order book, the hidden
"true value", each trader's account, the traders themselves, the simulation loop,
and the analysis that turns prices into candles and quality checks.

## The traders

- **Noise trader.** Random buys and sells. The background flow.
- **Market maker.** Quotes a buy and a sell around the price to earn the spread,
  and leans its quotes against whatever it is holding.
- **Momentum trader.** Buys what is rising, sells what is falling.
- **Value investor.** Has a noisy guess of fair value and leans against the price
  when it strays too far.
- **Leveraged trend** (crash scenario). A momentum trader on borrowed money, so a
  reversal can wipe it out and force a sale.
- **Mean reversion, breakout, news, whale, panic herd** (full market). The extra
  types that make the full market lively.

## The four scenarios

Switch between them with the toggle at the top left of the dashboard.

- **Normal market.** The four core traders. The calm baseline.
- **Leverage crash.** Adds sixteen traders on borrowed money and a shock partway
  through. They get force sold, and those sales cascade into a flash crash. Red
  markers show the forced sales.
- **Crash + breaker.** A sharp news shock, with a circuit breaker switched on.
  Grey bands are the trading halts, which arrest the fall.
- **Full market.** All the trader types at once, the richest behaviour.

## Does it look like a real market?

Every run is scored against two facts that every real market shows. **Fat tails**,
big moves happen far more often than a bell curve says. **Volatility clustering**,
busy periods and calm periods come in runs. The report prints a yes or no for each.
The numbers in `Config` are a rough calibration, tuned so the model reproduces
those two facts and stays stable, not fitted to any one real asset.

## A note on the strategy tester

The dashboard's strategy tester runs a rule (buy and hold, moving average cross,
momentum, mean reversion, breakout, buy the dip) on the market's price path and
shows how it would have done, against buy and hold, with realistic costs. It is a
price taker, the standard way to backtest. An earlier version let a strategy trade
as its own agent, but the market turned out to be chaotic, even a small order
nudges the whole path, so there was no single market to measure against cleanly.
That reflexivity is a real feature of the model, not a bug.
