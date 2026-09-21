# Agora, a simple agent based market simulator

Instead of drawing a price from a formula, Agora fills a market with lots of small
software traders, each following one simple rule, and lets them buy and sell from
each other on an order book. The price is just whatever they last traded at. Out
of all these simple rules, realistic looking market behaviour appears on its own.

The dashboard also shows **real market prices** next to the simulation, so you can
test simple trading strategies on both. It carries 29 companies and 5 indices, with
ten years of daily history each, and a small recent intraday demo (1 hour and 1
minute) for a handful of busy names.

> Coding was done with the help of AI. I am not proficient at coding, so I set the
> direction, made the decisions, and tested the app. The code is kept deliberately
> simple so that I can read it.

## See it

- **The app:** open [`index.html`](index.html) (or `Agora Dashboard.html`) in any
  browser. If GitHub Pages is turned on for this repo, it is live at the Pages URL.
- **The story of how it was built:** `Agora - Development Log.docx`.
- **The original plan:** `Agora - Architecture and Design Specification.docx`.

## What it does

- A live, streaming simulated market that plays in real time and can be sped up.
- Four scenarios: a normal market, a leverage driven crash, a crash arrested by a
  circuit breaker, and a full market with ten trader types.
- A **Simulation / Real market** switch. Real market lets you pick any of 29
  companies (grouped by sector) or 5 indices, choose the horizon (1 month to the
  full ten years), and switch to hourly or 1 minute where the demo offers it.
- A **strategy tester**: pick a rule (moving average cross, momentum, mean
  reversion, breakout, buy the dip, buy and hold), tune it, and see how it would
  have done against buying and holding **and against the market's own benchmark
  index**, with the excess return, on either the simulation or real prices.
- Checks that the simulated market shows the two facts every real market shows,
  fat tails and volatility clustering.

The page loads each market's prices only when you pick it, so the file stays small
and follows the whole universe. The prices refresh by themselves once a day.

## Run it yourself

```
cd engine
pip install -r requirements.txt
python fetch_data.py          # download the whole universe (needs internet)
python build_page.py          # build the website page
python run_simulation.py      # optional: run the full agent model and print a report
python run_research.py        # optional: run the strategy study and draw the charts
```

See [`engine/README.md`](engine/README.md) for how the code is laid out. The whole
agent model is one readable file, `engine/agora.py`.

## Note

This is a learning and portfolio project, not investment advice. The real prices
are refreshed daily but are still only a public end of day feed, not a trading feed.
