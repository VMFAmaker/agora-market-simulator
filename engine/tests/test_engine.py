"""
Tests for the engine. The most important ones prove there is no look-ahead bias.

    python tests/test_engine.py          (or: python -m pytest tests)

Coding done with the help of AI, because coding is not the author's strong area.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import execution
import simulator
import tester
from backtest import Config, run
from market_data import Bar, LookAheadError, Market, load
from strategies import BUY, HOLD, SELL, BuyHold, RSIReversion, SMACross, Strategy


def cut(market, k):
    """The same market with everything from bar k onwards removed (the future deleted)."""
    m = copy.copy(market)
    m.bars = market.bars[:k]
    return m


def zero_cost(**kw):
    return Config(execution=execution.preset("zero"), whole_shares=False, **kw)


# ---------------- look-ahead ----------------
def test_cutting_off_the_future_never_changes_the_past():
    msft = load("MSFT")
    full = run([msft], SMACross, {"fast": 20, "slow": 50}, Config())
    for k in (300, 900, 1500, 2200):
        part = run([cut(msft, k)], SMACross, {"fast": 20, "slow": 50}, Config())
        last = msft.bars[k - 1].time
        n = len(part["equity"])
        assert full["equity"][:n] == part["equity"], f"equity differs when the future after {last} is removed"
        before = lambda fills: [(f["time"], f["side"], f["qty"], f["price"]) for f in fills if f["time"] <= last]
        assert before(full["fills"]) == before(part["fills"]), f"fills differ before {last}"


def test_a_strategy_cannot_ask_for_the_future():
    class Cheat(Strategy):
        def generate_signal(self, h):
            h.close(-1)                                   # tomorrow's close
            return HOLD
    try:
        run([load("AAPL")], Cheat, {}, Config())
    except LookAheadError:
        return
    raise AssertionError("the cheat was not stopped")


def test_strategy_sees_each_bar_only_after_it_closes_and_fills_next_open():
    seen = []

    class Spy(Strategy):
        def generate_signal(self, h):
            seen.append((h.now, h.close(), len(h)))
            return BUY("spy") if len(h) == 30 else HOLD

    ko = load("KO")
    r = run([ko], Spy, {}, Config())
    for i, (now, close, length) in enumerate(seen):
        assert now == ko.bars[i].time and close == ko.bars[i].close and length == i + 1
    fill = r["fills"][0]
    assert fill["time"] == ko.bars[30].time, "the order must fill on the bar AFTER the decision"
    assert fill["expected"] == ko.bars[30].open, "and at that bar's open"


def test_walk_forward_folds_do_not_change_when_later_data_is_removed():
    exp = tester.Experiment("sma", symbols=["JPM"], method="walk_forward")
    full = tester.walk_forward(exp)
    third_end = full["folds"][2]["test"][1]
    exp_cut = tester.Experiment("sma", symbols=["JPM"], method="walk_forward", end=third_end)
    part = tester.walk_forward(exp_cut)
    for a, b in zip(full["folds"][:3], part["folds"][:3]):
        assert a["params"] == b["params"] and abs(a["test_return"] - b["test_return"]) < 1e-12
    for f in full["folds"]:
        assert f["train"][1] < f["test"][0], "training must end before testing starts"


# ---------------- accounting ----------------
def test_equity_is_always_cash_plus_positions():
    r = run([load("AAPL")], RSIReversion, {}, Config())
    for i in range(len(r["equity"])):
        value = r["cash"][i] + r["qty"]["AAPL"][i] * r["price"]["AAPL"][i]
        assert abs(value - r["equity"][i]) < 1e-6


def test_profit_adds_up():
    r = run([load("MSFT")], SMACross, {}, Config())
    made = r["realised"] + r["unrealised"] + r["dividends_total"] - r["fees"]["commission"]
    assert abs((r["equity"][-1] - r["start_cash"]) - made) < 1e-4


def test_zero_cost_buy_and_hold_matches_the_price():
    m = load("NVDA")
    r = run([m], BuyHold, {}, zero_cost(dividends=False))
    fill = r["fills"][0]
    first = m.index_of(fill["time"])
    assert fill["price"] == m.bars[first].open                     # no costs, so exactly the open
    leftover = r["start_cash"] - fill["qty"] * fill["price"]        # sized on the last close, so a gap leaves change
    assert abs(r["equity"][-1] - (fill["qty"] * m.bars[-1].close + leftover)) < 1e-6


def test_dividends_are_paid_as_cash():
    m = load("KO")
    r = run([m], BuyHold, {}, zero_cost())
    qty = r["fills"][0]["qty"]
    first = r["fills"][0]["time"]
    owed = sum(qty * amt for day, amt in m.dividends.items() if day > first)
    assert abs(r["dividends_total"] - owed) < 1e-6
    price_part = qty * m.bars[-1].close + (r["start_cash"] - qty * r["fills"][0]["price"])
    assert abs(r["equity"][-1] - (price_part + owed)) < 1e-6


# ---------------- execution ----------------
def _market(rows):
    bars = [Bar("D%05d" % i, *row) for i, row in enumerate(rows)]
    return Market("TEST", "Test", bars)


def test_a_stop_that_gaps_fills_at_the_open_not_the_stop():
    class BuyOnce(Strategy):
        def generate_signal(self, h):
            return BUY("go") if len(h) == 1 else HOLD
    rows = [(100, 101, 99, 100, 1e6), (100, 101, 99, 100, 1e6), (100, 101, 99, 100, 1e6),
            (80, 82, 78, 81, 1e6), (81, 82, 80, 81, 1e6)]
    r = run([_market(rows)], BuyOnce, {"stop_loss": 0.05}, zero_cost())
    stop = [f for f in r["fills"] if f["purpose"] == "stop"][0]
    assert stop["expected"] == 80 and stop["time"] == "D00003", "a gap through the stop fills at the open"


def test_more_slippage_never_helps():
    msft = load("MSFT")
    ends = []
    for bps in execution.SLIPPAGE_PRESETS:
        ex = execution.Execution(slippage_bps=bps)
        ends.append(run([msft], SMACross, {}, Config(execution=ex))["equity"][-1])
    assert all(a >= b for a, b in zip(ends, ends[1:]))


def test_big_orders_are_cut_to_what_the_market_can_take():
    thin = simulator.synthetic("normal", 1)
    for b in thin.bars:
        b.volume = 1000                                     # only 1,000 shares trade a day
    r = run([thin], BuyHold, {}, Config(cash=10_000_000))
    first = r["fills"][0]
    assert first["qty"] <= 100 + 1e-9 and "cut" in first["note"]


def test_shorts_get_a_margin_call_on_a_big_rally():
    class AlwaysShort(Strategy):
        def generate_signal(self, h):
            return SELL("short it")
    rows = [(100, 101, 99, 100, 1e7)] * 5 + [(100 * 1.15 ** i, 100 * 1.15 ** i, 100 * 1.15 ** i, 100 * 1.15 ** i, 1e7)
                                             for i in range(1, 15)]
    r = run([_market(rows)], AlwaysShort, {}, Config(allow_short=True, max_leverage=2.0,
                                                    sizing=__import__("sizing").FixedPercent(2.0)))
    assert any(f["purpose"] == "margin" for f in r["fills"]) or r["blown"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  pass ", name)
        except Exception as e:
            failed += 1
            print("  FAIL ", name, "->", type(e).__name__, e)
    print(f"\n{len(tests) - failed} of {len(tests)} tests passed")
    sys.exit(1 if failed else 0)
