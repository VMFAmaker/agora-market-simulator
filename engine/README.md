# Agora, a simple agent based market simulator

Instead of drawing a price from a formula, Agora fills a market with lots of small
software traders, each following one simple rule, and lets them buy and sell from
each other on an order book. The price is just whatever they last traded at. Out
of all these simple rules, realistic looking market behaviour appears on its own.

> Coding was done with the help of AI. I am not proficient at coding, so I set the
> direction, made the decisions, and tested the app. The code is kept deliberately
> simple so that I can read it.

## Two simulations, and why

- **The full model** is the Python file `agora.py`. It runs the real agent based
  order book, with ten trader types, a leverage crash, and a circuit breaker, and
  checks the result against the facts a real market shows. Run it to study or test
  the model.
- **The dashboard** builds its own market in the browser (a lighter generator, in
  `dashboard_template.html`). This is so every visit and every "New market" gives a
  fresh, random market from the first candle, which a fixed page could not do if it
  just replayed one baked run. It keeps the same lively behaviour, trends,
  clustering and the odd crash.

## Run it

```
pip install -r requirements.txt
python fetch_markets.py       # download real prices (needs internet)
python build_page.py          # build the dashboard page
python run_simulation.py      # optional: run the full Python model and print a report
```

`fetch_markets.py` saves real daily prices to `output/real_markets.json`.
`build_page.py` pours those into `dashboard_template.html` and writes `index.html`
and `Agora Dashboard.html` in the folder above. Open either in a browser.

The website refreshes the real prices by itself once a day, using the job in
`.github/workflows/refresh-data.yml`, so the live page follows the current market
rather than a one-off snapshot.

## What is inside

| File | What it does |
| --- | --- |
| `agora.py` | The full simulator. Order book, traders, the clock, the checks. |
| `fetch_markets.py` | Downloads real daily prices from Yahoo Finance. |
| `build_page.py` | Builds the dashboard page from the template and the real prices. |
| `run_simulation.py` | Runs the full Python model and prints a report. |
| `dashboard_template.html` | The web page, including the in-browser market generator. |

## The traders (in the Python model)

- **Noise** random flow, **market maker** quoting both sides, **momentum** buying
  strength, **value** buying cheap and selling dear, and, in the busier scenarios,
  **leveraged trend, mean reversion, breakout, news, whale and panic herd**.

## Does it look like a real market?

Both the model and the dashboard check two facts every real market shows. **Fat
tails**, big moves happen more often than a bell curve says. **Volatility
clustering**, busy and calm periods come in runs. The dashboard shows a yes or no
for each in the Details panel.
