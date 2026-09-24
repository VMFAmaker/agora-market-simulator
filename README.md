# Agora, a market simulator and an honest strategy tester

Agora started as a market simulator, a crowd of small software traders whose orders
make the price. It has grown into a place to test trading rules properly, on made up
markets and on ten years of real prices, with one backtest engine for both.

> Coding was done with the help of AI. I am not proficient at coding, so I set the
> direction, made the decisions, and tested the results. The code is kept simple and
> heavily commented so that I can read it.

## See it

- **The app** is live at the GitHub Pages address for this repo (or serve the folder
  and open `index.html`).
- **The findings** are in `Agora - Strategy Research.docx`.
- **How it was built** is in `Agora - Development Log.docx`, and the original plan in
  `Agora - Architecture and Design Specification.docx`.

## What it does

- **Real markets you can move around in.** Ten years of daily prices for 29 companies
  (grouped by sector) and 6 indices, refreshed every day. Scroll and zoom through all
  of it. Candles change size to suit the zoom (daily, weekly, monthly), a navigator
  strip maps the whole history, and there is a log scale for the long view. A recent
  intraday demo (1 hour and 1 minute) covers six busy names.
- **Replay.** Go back to any day and step forward one bar at a time with the future
  hidden. The strategy tester only uses data up to that day, so you face each bar the
  way you would have at the time.
- **A strategy tester built not to cheat.** Seven rules (buy and hold, moving average
  cross, RSI mean reversion, momentum, mean reversion, breakout, buy the dip), each
  with stop loss and take profit. Orders fill at the next bar's open, never at the
  price that triggered them, and pay the spread, slippage, market impact and
  commission. Positions are sized by a rule (a share of the account, a fixed amount,
  or by volatility) inside limits on exposure and leverage, and shorting is possible
  with margin calls.
- **Four ways to test.** A historical backtest, an out-of-sample test, a walk-forward
  test, and a stress test on six synthetic markets. Every result also shows how it
  holds up with more slippage, with optimistic fills, and across every setting in
  the strategy's grid.
- **Compared with a benchmark.** Excess return, beta, alpha and information ratio
  against the market's own index, or the S&P 500 Total Return for a like for like
  comparison including dividends.
- **The live simulation.** A fresh random market every time, playing in real time,
  with four scenarios including a leverage crash and a circuit breaker.

## How it is built

The engine is four parts. **Market data** (download, check and store bars),
**strategy engine** (rules that only produce signals), **market simulator**
(synthetic markets and the full agent model), and **strategy tester** (sizing,
execution, the account, and the test methods). A strategy never knows whether its
prices are real or simulated, so the same rule runs on Apple, the S&P 500 or a
synthetic crash without a change. See [`engine/README.md`](engine/README.md).

Two tests matter most. One cuts the future off the data and checks that the past
results do not change, which proves the engine has no look-ahead. The other runs the
same experiments through the Python engine and the browser engine and checks that
every number matches.

## Run it yourself

```
cd engine
pip install -r requirements.txt
python fetch_data.py          # download the whole universe (needs internet)
python build_page.py          # build the website page
python tests/test_engine.py   # the engine tests
python run_research.py        # the full study behind the report
```

## Note

This is a learning and portfolio project, not investment advice. Prices come from a
free public end of day source, and the costs in the tester are modelled, not measured.
