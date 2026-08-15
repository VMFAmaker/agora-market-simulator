# Agora, a simple agent based market simulator

Instead of drawing a price from a formula, Agora fills a market with lots of small
software traders, each following one simple rule, and lets them buy and sell from
each other on an order book. The price is just whatever they last traded at. Out
of all these simple rules, realistic looking market behaviour appears on its own.

The dashboard also shows **real market prices** next to the simulation, so you can
test simple trading strategies on both.

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
- A **Simulation / Real market** switch. Real market shows ten actual instruments
  (shares, commodities, natural resources, currencies, crypto) in dollars or pounds.
- A **strategy tester**: pick a rule (moving average cross, momentum, mean
  reversion, breakout, buy the dip, buy and hold), tune it, and see how it would
  have done against buying and holding, on either the simulation or real prices.
- Checks that the simulated market shows the two facts every real market shows,
  fat tails and volatility clustering.

## Run it yourself

```
cd engine
pip install -r requirements.txt
python fetch_markets.py       # download real prices (needs internet)
python run_simulation.py      # run the model and rebuild the dashboard
```

See [`engine/README.md`](engine/README.md) for how the code is laid out. The whole
simulator is one readable file, `engine/agora.py`.

## Note

This is a learning and portfolio project, not investment advice. The real prices
are a snapshot taken when the page was built, not a live feed.
