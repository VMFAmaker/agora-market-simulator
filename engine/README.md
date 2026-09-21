# Agora, a simple agent based market simulator

Instead of drawing a price from a formula, Agora fills a market with lots of small
software traders, each following one simple rule, and lets them buy and sell from
each other on an order book. The price is just whatever they last traded at. Out
of all these simple rules, realistic looking market behaviour appears on its own.

> Coding was done with the help of AI. I am not proficient at coding, so I set the
> direction, made the decisions, and tested the app. The code is kept deliberately
> simple so that I can read it.

## The idea that holds it together

A strategy should not know or care where its prices come from. It just reads bars.
So a real company, a real index, and a made-up market all come through in the same
simple shape (date, open, high, low, close, volume). The same rule can then be
tested on Apple, on the S&P 500, or on a synthetic crash, without changing a line.

## Two simulations, and why

- **The full model** is the Python file `agora.py`. It runs the real agent based
  order book, with ten trader types, a leverage crash, and a circuit breaker, and
  checks the result against the facts a real market shows. Run it to study the model.
- **The dashboard** builds its own market in the browser (a lighter generator, in
  `dashboard_template.html`). This is so every visit and every "New market" gives a
  fresh, random market from the first candle, which a fixed page could not do if it
  just replayed one baked run.

## Real market data

`fetch_data.py` downloads ten years of daily prices for the whole universe (29
companies and 5 indices, set in `universe.py`), plus a small recent intraday demo
(1 hour and 1 minute) for a few busy names. Each market is saved as its own file in
`data/`, and `data/catalogue.json` lists them all. The page loads a market's file
only when you pick it, so the page itself stays small.

## Run it

```
pip install -r requirements.txt
python fetch_data.py          # download the whole universe (needs internet)
python build_page.py          # build the website page
python run_simulation.py      # optional: run the full agent model and print a report
python run_research.py        # optional: run the strategy study and draw the charts
```

`build_page.py` pours the catalogue into `dashboard_template.html` and writes
`index.html` and `Agora Dashboard.html` in the folder above. The website refreshes
the real prices by itself once a day, using the job in
`.github/workflows/refresh-data.yml`, so the live page follows the current market.

## What is inside

| File | What it does |
| --- | --- |
| `agora.py` | The full agent model. Order book, traders, the clock, the checks. |
| `universe.py` | The list of markets, their sectors and benchmark indices. |
| `fetch_data.py` | Downloads daily (and demo intraday) prices, one file per market. |
| `feeds.py` | The source agnostic layer. Real or synthetic, all become one Feed. |
| `strategies.py` | The trading rules, each a small class that only sees prices. |
| `tester.py` | Backtests a rule, compares it to a benchmark, and stress tests it. |
| `run_research.py` | Runs the whole study across a basket and draws the charts. |
| `build_page.py` | Builds the dashboard page from the template and the catalogue. |
| `run_simulation.py` | Runs the full agent model and prints a report. |
| `dashboard_template.html` | The web page, including the in-browser generator. |

## The traders (in the Python agent model)

- **Noise** random flow, **market maker** quoting both sides, **momentum** buying
  strength, **value** buying cheap and selling dear, and, in the busier scenarios,
  **leveraged trend, mean reversion, breakout, news, whale and panic herd**.

## Does it look like a real market?

Both the model and the dashboard check two facts every real market shows. **Fat
tails**, big moves happen more often than a bell curve says. **Volatility
clustering**, busy and calm periods come in runs. The dashboard shows a yes or no
for each in the Details panel.
