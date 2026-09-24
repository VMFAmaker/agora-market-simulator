"""
EXECUTION MODEL. What really happens when an order reaches the market.

A strategy says BUY. That does not mean it gets the price that triggered the
signal. This model decides the fill, and every cost on top:

  timing      the order is filled at the NEXT bar's open, because the signal was
              only known once the last bar had closed. ("same close" is offered
              only as an optimistic comparison, it quietly assumes you could trade
              at a price you had not seen yet.)
  spread      buyers pay the ask, sellers get the bid. Without real bid and ask
              data we assume the gap between them, spread_bps wide (5 bps = 0.05%).
  slippage    the price moves a little against you while the order is worked.
  impact      a big order pushes the price. We use the well known square root
              rule, impact = daily volatility x sqrt(order / average daily value
              traded). 500 of Apple is nothing. Half a day's volume is a lot.
  liquidity   no single order may be more than max_participation of the average
              daily volume. Anything bigger is cut down, and the log says so.
  commission  a fixed fee, a percentage of the trade, and a minimum.

All of this uses only bars that had already closed, so it cannot see the future.

Coding done with the help of AI, because coding is not the author's strong area.
"""
import math

SLIPPAGE_PRESETS = [0.0, 1.0, 5.0, 10.0, 25.0]      # in bps: 0, 0.01%, 0.05%, 0.10%, 0.25%


class Execution:
    def __init__(self, commission_pct=0.0005, commission_min=1.0, commission_fixed=0.0,
                 spread_bps=5.0, slippage_bps=1.0, impact=True, max_participation=0.10,
                 fill_at="next_open", adv_bars=20):
        self.commission_pct, self.commission_min = commission_pct, commission_min
        self.commission_fixed, self.spread_bps, self.slippage_bps = commission_fixed, spread_bps, slippage_bps
        self.impact, self.max_participation = impact, max_participation
        self.fill_at, self.adv_bars = fill_at, adv_bars

    def describe(self):
        bits = [f"fills at {'the next open' if self.fill_at == 'next_open' else 'the same close (optimistic)'}",
                f"spread {self.spread_bps:g} bps", f"slippage {self.slippage_bps:g} bps",
                f"commission {self.commission_pct:.2%} (min {self.commission_min:g})"]
        bits.append("square root market impact" if self.impact else "no market impact")
        return ", ".join(bits)

    def commission(self, value):
        if value <= 0:
            return 0.0
        return max(self.commission_min, self.commission_fixed + self.commission_pct * value)

    def liquidity(self, history):
        """Average shares traded per bar, average value traded, and volatility, from past bars."""
        vols, closes = history.volumes[-self.adv_bars:], history.closes[-self.adv_bars - 1:]
        if not vols:
            return 0.0, 0.0, 0.0
        adv = sum(vols) / len(vols)
        adv_value = sum(v * c for v, c in zip(vols, history.closes[-len(vols):])) / len(vols)
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        if len(rets) > 1:
            m = sum(rets) / len(rets)
            vol = math.sqrt(sum((r - m) ** 2 for r in rets) / len(rets))
        else:
            vol = 0.0
        return adv, adv_value, vol

    def cap_quantity(self, qty, history):
        """Cut an order down to the most the market can take. Returns (qty, note)."""
        adv, _, _ = self.liquidity(history)
        if adv <= 0 or self.max_participation <= 0:
            return qty, ""
        most = self.max_participation * adv
        if qty > most:
            return most, f"cut from {qty:,.0f} to {most:,.0f}, {self.max_participation:.0%} of average volume"
        return qty, ""

    def fill(self, side, qty, reference, history):
        """
        Price one fill. side is +1 to buy, -1 to sell. reference is the price we
        expected (the open, or the stop level). Returns the fill price and the
        cost of each piece, in money.
        """
        _, adv_value, vol = self.liquidity(history)
        half_spread = reference * self.spread_bps / 2 / 10_000
        slip = reference * self.slippage_bps / 10_000
        participation = (qty * reference / adv_value) if adv_value > 0 else 0.0
        impact = reference * vol * math.sqrt(participation) if (self.impact and participation > 0) else 0.0
        price = reference + side * (half_spread + slip + impact)
        value = qty * price
        return {
            "expected": reference, "price": price, "commission": self.commission(value),
            "spread_cost": qty * half_spread, "slippage_cost": qty * slip, "impact_cost": qty * impact,
            "participation": participation,
        }


def preset(name):
    """A few ready made cost settings."""
    if name == "zero":
        return Execution(commission_pct=0, commission_min=0, spread_bps=0, slippage_bps=0, impact=False,
                         max_participation=0)
    if name == "institutional":
        return Execution(commission_pct=0.0002, commission_min=0, spread_bps=2, slippage_bps=1)
    return Execution()
