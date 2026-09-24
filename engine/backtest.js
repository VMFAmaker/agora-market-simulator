/*
  THE BACKTEST ENGINE, for the browser.

  This is the same engine as the Python files (indicators.py, strategies.py,
  sizing.py, execution.py, portfolio.py, backtest.py, metrics.py, tester.py),
  written again in JavaScript so the web page can run it. Same names, same steps,
  same order. tests/test_parity.py runs both on the same data and checks that
  they give the same answers, so the page and the research report always agree.

  The one rule that matters most: a bar only reaches the strategy once it has
  closed, and any order it sends is filled at the NEXT bar's open. See the
  comments in backtest.py for the full walk through of one bar.

  Coding done with the help of AI, because coding is not the author's strong area.
*/
(function (root) {
  'use strict';

  // =============================== INDICATORS ===============================
  function sma(values, n) {
    if (n <= 0 || values.length < n) return null;
    let s = 0;
    for (let i = values.length - n; i < values.length; i++) s += values[i];
    return s / n;
  }
  function change(values, n) {
    if (values.length <= n) return null;
    return values[values.length - 1] / values[values.length - 1 - n] - 1;
  }
  function rsi(values, n) {
    if (values.length <= n) return null;
    let ups = 0, downs = 0;
    for (let i = values.length - n; i < values.length; i++) {
      const move = values[i] - values[i - 1];
      if (move > 0) ups += move; else downs -= move;
    }
    if (downs === 0) return 100;
    return 100 - 100 / (1 + ups / downs);
  }
  function highest(values, n, skip) {
    skip = skip || 0;
    if (values.length < n + skip) return null;
    const end = values.length - skip;
    let m = -Infinity;
    for (let i = end - n; i < end; i++) if (values[i] > m) m = values[i];
    return m;
  }
  function lowest(values, n, skip) {
    skip = skip || 0;
    if (values.length < n + skip) return null;
    const end = values.length - skip;
    let m = Infinity;
    for (let i = end - n; i < end; i++) if (values[i] < m) m = values[i];
    return m;
  }
  function atr(h, n) {
    n = n || 14;
    if (h.length <= n) return null;
    const c = h.closes, hi = h.highs, lo = h.lows;
    let total = 0;
    for (let i = c.length - n; i < c.length; i++)
      total += Math.max(hi[i] - lo[i], Math.abs(hi[i] - c[i - 1]), Math.abs(lo[i] - c[i - 1]));
    return total / n;
  }
  const ind = { sma, change, rsi, highest, lowest, atr };

  // =============================== HISTORY (the time frontier) ===============================
  class LookAheadError extends Error {}
  class History {
    constructor(symbol) {
      this.symbol = symbol;
      this.bars = []; this.closes = []; this.highs = []; this.lows = []; this.volumes = [];
    }
    add(bar) {
      if (this.bars.length && bar.d <= this.bars[this.bars.length - 1].d)
        throw new Error('bars must arrive in time order');
      this.bars.push(bar); this.closes.push(bar.c); this.highs.push(bar.h);
      this.lows.push(bar.l); this.volumes.push(bar.v || 0);
    }
    get length() { return this.bars.length; }
    get now() { return this.bars[this.bars.length - 1].d; }
    close(ago) {
      ago = ago || 0;
      if (ago < 0) throw new LookAheadError('asked for a close ' + (-ago) + ' bars in the future');
      return this.closes[this.closes.length - 1 - ago];
    }
  }

  // =============================== STRATEGIES ===============================
  const BUY = (reason) => ({ action: 'BUY', reason: reason || '' });
  const SELL = (reason) => ({ action: 'SELL', reason: reason || '' });
  const HOLD = { action: 'HOLD', reason: '' };
  const pct1 = (x) => (x * 100).toFixed(1) + '%';

  class Strategy {
    constructor(params) {
      this.params = {};
      for (const s of this.constructor.settings) this.params[s[0]] = s[2];
      if (!('stop_loss' in this.params)) this.params.stop_loss = 0;
      if (!('take_profit' in this.params)) this.params.take_profit = this.constructor.defaultTakeProfit || 0;
      Object.assign(this.params, params || {});
    }
    get p() { return this.params; }
    initialize(ctx) {}
    onMarketData(ctx) { this.managePosition(ctx, this.generateSignal(ctx.history)); }
    generateSignal(h) { return HOLD; }
    managePosition(ctx, signal) {
      const held = ctx.position;
      const sl = this.p.stop_loss, tp = this.p.take_profit;
      if (signal.action === 'BUY') {
        if (held < 0) ctx.close(signal.reason);
        if (held <= 0) ctx.buy(signal.reason, sl, tp);
      } else if (signal.action === 'SELL') {
        if (held > 0) ctx.close(signal.reason);
        if (ctx.allowShort && held >= 0) ctx.short(signal.reason, sl, tp);
      }
    }
  }
  Strategy.settings = []; Strategy.grid = {};

  class BuyHold extends Strategy {
    generateSignal(h) { return BUY('buy and hold'); }
  }
  Object.assign(BuyHold, { key: 'bh', label: 'Buy and hold', settings: [], grid: {},
    about: 'Buy on the first bar and never sell. The yardstick every rule has to beat.' });

  class SMACross extends Strategy {
    generateSignal(h) {
      const fast = sma(h.closes, Math.trunc(this.p.fast)), slow = sma(h.closes, Math.trunc(this.p.slow));
      if (fast === null || slow === null) return HOLD;
      if (fast > slow) return BUY('fast average ' + fast.toFixed(2) + ' above slow ' + slow.toFixed(2));
      return SELL('fast average ' + fast.toFixed(2) + ' below slow ' + slow.toFixed(2));
    }
  }
  Object.assign(SMACross, { key: 'sma', label: 'Moving average cross',
    settings: [['fast', 'fast average', 20, 2, 200, 1], ['slow', 'slow average', 50, 5, 400, 5]],
    grid: { fast: [10, 20, 30, 50], slow: [50, 100, 150, 200] },
    about: 'Long while the fast average is above the slow one, out when it drops below.' });

  class RSIReversion extends Strategy {
    generateSignal(h) {
      const v = rsi(h.closes, Math.trunc(this.p.period));
      if (v === null) return HOLD;
      if (v < this.p.low) return BUY('RSI ' + v.toFixed(1) + ' below ' + this.p.low);
      if (v > this.p.high) return SELL('RSI ' + v.toFixed(1) + ' above ' + this.p.high);
      return HOLD;
    }
  }
  Object.assign(RSIReversion, { key: 'rsi', label: 'RSI mean reversion',
    settings: [['period', 'RSI period', 14, 2, 50, 1], ['low', 'buy below', 30, 5, 50, 1], ['high', 'sell above', 70, 50, 95, 1]],
    grid: { period: [7, 14], low: [25, 30, 35], high: [65, 70, 75] },
    about: 'Buy when RSI says oversold, sell when it says overbought.' });

  class Momentum extends Strategy {
    generateSignal(h) {
      const n = Math.trunc(this.p.lookback), move = change(h.closes, n);
      if (move === null) return HOLD;
      if (move > this.p.threshold) return BUY('up ' + pct1(move) + ' over ' + n + ' bars');
      if (move < 0) return SELL('down ' + pct1(move) + ' over ' + n + ' bars');
      return HOLD;
    }
  }
  Object.assign(Momentum, { key: 'mom', label: 'Momentum',
    settings: [['lookback', 'lookback bars', 60, 5, 300, 5], ['threshold', 'buy above', 0.05, 0, 0.5, 0.01]],
    grid: { lookback: [20, 60, 120, 250], threshold: [0.0, 0.05, 0.10] },
    about: 'Buy when the price is up strongly over the lookback, sell when that turns negative.' });

  class MeanReversion extends Strategy {
    generateSignal(h) {
      const avg = sma(h.closes, Math.trunc(this.p.window));
      if (avg === null) return HOLD;
      const price = h.close();
      if (price < avg * (1 - this.p.band)) return BUY('price ' + price.toFixed(2) + ' is ' + pct1(1 - price / avg) + ' below its average');
      if (price >= avg) return SELL('price back to its average ' + avg.toFixed(2));
      return HOLD;
    }
  }
  Object.assign(MeanReversion, { key: 'mr', label: 'Mean reversion',
    settings: [['window', 'average of', 20, 5, 200, 1], ['band', 'buy below by', 0.05, 0.005, 0.3, 0.005]],
    grid: { window: [10, 20, 50], band: [0.03, 0.05, 0.08] },
    about: 'Buy when the price falls well below its average, sell once it gets back.' });

  class Breakout extends Strategy {
    generateSignal(h) {
      const n = Math.trunc(this.p.window), half = Math.max(2, Math.floor(n / 2));
      const top = highest(h.closes, n, 1), bottom = lowest(h.closes, half, 1);
      if (top === null || bottom === null) return HOLD;
      const price = h.close();
      if (price > top) return BUY('new ' + n + ' bar high ' + price.toFixed(2));
      if (price < bottom) return SELL('new ' + half + ' bar low ' + price.toFixed(2));
      return HOLD;
    }
  }
  Object.assign(Breakout, { key: 'brk', label: 'Breakout',
    settings: [['window', 'channel bars', 40, 5, 250, 5]], grid: { window: [20, 40, 60, 100] },
    about: 'Buy a new high of the channel, sell a new low of half the channel.' });

  class BuyTheDip extends Strategy {
    generateSignal(h) {
      const n = Math.trunc(this.p.lookback), peak = highest(h.closes, n);
      if (peak === null) return HOLD;
      const price = h.close();
      if (price <= peak * (1 - this.p.drop)) return BUY(pct1(1 - price / peak) + ' below the ' + n + ' bar peak');
      return HOLD;
    }
  }
  Object.assign(BuyTheDip, { key: 'dip', label: 'Buy the dip', defaultTakeProfit: 0.12,
    settings: [['drop', 'buy after a fall of', 0.10, 0.02, 0.5, 0.01], ['lookback', 'peak over bars', 60, 10, 300, 5]],
    grid: { drop: [0.05, 0.10, 0.15, 0.20], take_profit: [0.10, 0.20, 0.30] },
    about: 'Buy after a fall from the recent peak, and let the take profit (or stop) close it.' });

  const STRATEGIES = [BuyHold, SMACross, RSIReversion, Momentum, MeanReversion, Breakout, BuyTheDip];
  const BY_KEY = {};
  STRATEGIES.forEach(s => { BY_KEY[s.key] = s; });

  // =============================== SIZING ===============================
  function makeSizing(kind, value) {
    if (kind === 'amount') return { name: Math.round(value).toLocaleString() + ' per position',
      quantity: (price, equity) => Math.min(value, equity) / price };
    if (kind === 'volatility') return { name: 'risk ' + (value * 100).toFixed(1) + '% of the account per trade',
      quantity: (price, equity, h) => { const m = atr(h, 14); return m ? value * equity / (2 * m) : 0; } };
    return { name: Math.round(value * 100) + '% of the account', quantity: (price, equity) => value * equity / price };
  }

  // =============================== EXECUTION ===============================
  const SLIPPAGE_PRESETS = [0, 1, 5, 10, 25];
  function makeExecution(o) {
    o = o || {};
    const d = (k, v) => (o[k] === undefined ? v : o[k]);
    return { commission_pct: d('commission_pct', 0.0005), commission_min: d('commission_min', 1.0),
      commission_fixed: d('commission_fixed', 0), spread_bps: d('spread_bps', 5), slippage_bps: d('slippage_bps', 1),
      impact: d('impact', true), max_participation: d('max_participation', 0.10), fill_at: d('fill_at', 'next_open'),
      adv_bars: d('adv_bars', 20) };
  }
  function presetExecution(name) {
    if (name === 'zero') return makeExecution({ commission_pct: 0, commission_min: 0, spread_bps: 0, slippage_bps: 0, impact: false, max_participation: 0 });
    return makeExecution();
  }
  function commission(ex, value) {
    if (value <= 0) return 0;
    return Math.max(ex.commission_min, ex.commission_fixed + ex.commission_pct * value);
  }
  function liquidity(ex, h) {
    const vols = h.volumes.slice(-ex.adv_bars), closes = h.closes.slice(-ex.adv_bars - 1);
    if (!vols.length) return [0, 0, 0];
    let s = 0; for (const v of vols) s += v;
    const adv = s / vols.length;
    const cl = h.closes.slice(-vols.length);
    let sv = 0; for (let i = 0; i < vols.length; i++) sv += vols[i] * cl[i];
    const advValue = sv / vols.length;
    const rets = [];
    for (let i = 1; i < closes.length; i++) rets.push(Math.log(closes[i] / closes[i - 1]));
    let vol = 0;
    if (rets.length > 1) {
      let m = 0; for (const r of rets) m += r; m /= rets.length;
      let q = 0; for (const r of rets) q += (r - m) * (r - m);
      vol = Math.sqrt(q / rets.length);
    }
    return [adv, advValue, vol];
  }
  function capQuantity(ex, qty, h) {
    const adv = liquidity(ex, h)[0];
    if (adv <= 0 || ex.max_participation <= 0) return [qty, ''];
    const most = ex.max_participation * adv;
    if (qty > most) return [most, 'cut from ' + Math.round(qty).toLocaleString() + ' to ' + Math.round(most).toLocaleString() + ', ' + Math.round(ex.max_participation * 100) + '% of average volume'];
    return [qty, ''];
  }
  function priceFill(ex, side, qty, reference, h) {
    const lq = liquidity(ex, h), advValue = lq[1], vol = lq[2];
    const halfSpread = reference * ex.spread_bps / 2 / 10000;
    const slip = reference * ex.slippage_bps / 10000;
    const participation = advValue > 0 ? qty * reference / advValue : 0;
    const impact = (ex.impact && participation > 0) ? reference * vol * Math.sqrt(participation) : 0;
    const price = reference + side * (halfSpread + slip + impact);
    return { expected: reference, price, commission: commission(ex, qty * price),
      spread_cost: qty * halfSpread, slippage_cost: qty * slip, impact_cost: qty * impact, participation };
  }

  // =============================== PORTFOLIO ===============================
  class Portfolio {
    constructor(cash, maxLeverage, maintenance) {
      this.startCash = cash; this.cash = cash; this.positions = {}; this.prices = {};
      this.maxLeverage = maxLeverage; this.maintenance = maintenance === undefined ? 0.25 : maintenance;
      this.fees = { commission: 0, spread: 0, slippage: 0, impact: 0 }; this.dividends = 0;
    }
    position(s) { if (!this.positions[s]) this.positions[s] = { qty: 0, avg: 0, realised: 0, stop: null, target: null }; return this.positions[s]; }
    qty(s) { const p = this.positions[s]; return p ? p.qty : 0; }
    marketValue() { let v = 0; for (const s in this.positions) v += this.positions[s].qty * (this.prices[s] || 0); return v; }
    get equity() { return this.cash + this.marketValue(); }
    get gross() { let v = 0; for (const s in this.positions) v += Math.abs(this.positions[s].qty) * (this.prices[s] || 0); return v; }
    get net() { return this.marketValue(); }
    unrealised() { let v = 0; for (const s in this.positions) { const p = this.positions[s]; if (p.qty) v += p.qty * ((this.prices[s] || 0) - p.avg); } return v; }
    get realised() { let v = 0; for (const s in this.positions) v += this.positions[s].realised; return v; }
    marginCall() { const g = this.gross; return g > 0 && this.equity < this.maintenance * g; }
    mark(s, price) { this.prices[s] = price; }
    applyFill(s, qty, price, costs) {
      const p = this.position(s);
      this.cash -= qty * price + costs.commission;
      this.fees.commission += costs.commission; this.fees.spread += costs.spread_cost;
      this.fees.slippage += costs.slippage_cost; this.fees.impact += costs.impact_cost;
      let realised = 0;
      if (p.qty === 0 || (p.qty > 0) === (qty > 0)) {
        const total = p.qty + qty;
        p.avg = (p.qty * p.avg + qty * price) / total;
        p.qty = total;
      } else {
        const closing = Math.min(Math.abs(qty), Math.abs(p.qty));
        const direction = p.qty > 0 ? 1 : -1;
        realised = closing * (price - p.avg) * direction;
        p.realised += realised;
        const left = p.qty + qty;
        if (Math.abs(left) < 1e-9) { p.qty = 0; p.avg = 0; p.stop = null; p.target = null; }
        else if ((left > 0) !== (p.qty > 0)) { p.qty = left; p.avg = price; p.stop = null; p.target = null; }
        else p.qty = left;
      }
      if (!(s in this.prices)) this.prices[s] = price;
      return realised;
    }
    payDividend(s, perShare) { const amount = this.qty(s) * perShare; this.cash += amount; this.dividends += amount; return amount; }
  }

  function snapshot(pf) {
    const positions = {};
    for (const s in pf.positions) {
      const p = pf.positions[s];
      if (p.qty) positions[s] = { qty: p.qty, avg_price: p.avg, price: pf.prices[s], unrealised: p.qty * (pf.prices[s] - p.avg), realised: p.realised };
    }
    return { cash: pf.cash, equity: pf.equity, gross: pf.gross, net: pf.net, realised: pf.realised,
      unrealised: pf.unrealised(), dividends: pf.dividends, fees: Object.assign({}, pf.fees), positions };
  }

  // =============================== MARKETS ===============================
  // A market is { symbol, name, bars: [{d,o,h,l,c,v}], interval, periodsPerYear, dividends: {date: amount}, fractional }
  function indexOf(market, time) {
    let lo = 0, hi = market.bars.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (market.bars[mid].d < time) lo = mid + 1; else hi = mid; }
    return lo;
  }
  function marketFromFile(obj, meta) {
    meta = meta || {};
    const perDay = {};
    for (const b of obj.bars) { const k = b.d.slice(0, 10); perDay[k] = (perDay[k] || 0) + 1; }
    const counts = Object.values(perDay).sort((a, b) => a - b);
    const bpd = counts.length ? counts[Math.floor(counts.length / 2)] : 1;
    const days = obj.days_per_year || meta.days_per_year || 252;
    const interval = obj.interval || '1d';
    const divs = {};
    for (const d of (obj.dividends || [])) divs[d.d] = d.amount;
    return { symbol: obj.symbol, name: meta.name || obj.name || obj.symbol, bars: obj.bars, interval,
      periodsPerYear: interval === '1d' ? days : days * bpd, dividends: interval === '1d' ? divs : {},
      fractional: (meta.group || obj.group) === 'Crypto' || !!(meta.is_index || obj.is_index),
      benchmark: meta.benchmark || obj.benchmark || null };
  }

  // =============================== THE ENGINE ===============================
  function defaultConfig(o) {
    o = o || {};
    const d = (k, v) => (o[k] === undefined ? v : o[k]);
    return { cash: d('cash', 100000), sizing: d('sizing', makeSizing('percent', 1.0)), execution: d('execution', makeExecution()),
      allow_short: d('allow_short', false), max_leverage: d('max_leverage', 1.0), max_position: d('max_position', 1.0),
      dividends: d('dividends', true), whole_shares: d('whole_shares', true), start: d('start', null), end: d('end', null),
      warmup: d('warmup', 300) };
  }
  function withConfig(cfg, changes) { return Object.assign({}, cfg, changes); }

  function runBacktest(markets, StrategyClass, params, config) {
    const cfg = config || defaultConfig();
    const M = {}; markets.forEach(m => { M[m.symbol] = m; });
    const syms = markets.map(m => m.symbol);
    const pf = new Portfolio(cfg.cash, cfg.max_leverage);
    const hist = {}, strat = {}, pending = {}, ctxs = {};
    const orders = [], fills = [], trips = [], dividends = [], openTrips = {};
    let now = null, trading = false, blown = false, nextId = 1;
    const ex = cfg.execution;
    const fractional = (s) => !cfg.whole_shares || M[s].fractional;
    const round = (s, q) => fractional(s) ? q : Math.floor(q + 1e-9);

    function newOrder(s, side, qty, purpose, reason, sl, tp) {
      const o = { id: nextId++, time: now, symbol: s, side: side > 0 ? 'buy' : 'sell', qty, purpose, reason,
        stop_loss: sl || 0, take_profit: tp || 0, status: 'pending', note: '' };
      orders.push(o); return o;
    }
    function submitEntry(s, side, reason, sl, tp) {
      if (!trading) return;
      const h = hist[s], price = h.close(), equity = pf.equity;
      let qty = cfg.sizing.quantity(price, equity, h);
      qty = Math.min(qty, cfg.max_position * equity / price);
      const others = pf.gross - Math.abs(pf.qty(s)) * price;
      qty = Math.min(qty, Math.max(0, cfg.max_leverage * equity - others) / price);
      qty = round(s, qty);
      const o = newOrder(s, side, qty, 'entry', reason, sl, tp);
      if (qty <= 0) { o.status = 'rejected'; o.note = 'too small, or no buying power left'; return; }
      queue(o);
    }
    function submitExit(s, reason, purpose) {
      const q = pf.qty(s);
      if (!trading || q === 0) return;
      queue(newOrder(s, q > 0 ? -1 : 1, Math.abs(q), purpose, reason));
    }
    function queue(o) {
      if (ex.fill_at === 'close') { const h = hist[o.symbol]; execute(o, h.close(), h); }
      else pending[o.symbol].push(o);
    }
    function execute(o, reference, h) {
      const s = o.symbol, side = o.side === 'buy' ? 1 : -1, held = pf.qty(s);
      let qty = o.qty;
      if (o.purpose !== 'entry') {
        if (held === 0 || (held > 0) === (side > 0)) { o.status = 'cancelled'; o.note = 'nothing left to close'; return; }
        qty = Math.min(qty, Math.abs(held));
      } else {
        const others = pf.gross - Math.abs(held) * (s in pf.prices ? pf.prices[s] : reference);
        const room = Math.max(0, cfg.max_leverage * pf.equity - others - ex.commission_min);
        const est = reference * (1 + ex.spread_bps / 20000 + ex.slippage_bps / 10000 + ex.commission_pct);
        qty = round(s, Math.min(qty, room / est));
      }
      const capped = capQuantity(ex, qty, h);
      qty = capped[0]; const note = capped[1];
      if (o.purpose === 'entry') qty = round(s, qty);
      if (qty <= 0) { o.status = 'rejected'; o.note = note || 'no buying power left at the open'; return; }
      const f = priceFill(ex, side, qty, reference, h);
      const before = held;
      const realised = pf.applyFill(s, side * qty, f.price, f);
      o.status = qty < o.qty - 1e-9 ? 'partial' : 'filled'; o.note = note;
      const fill = { order: o.id, time: now, symbol: s, side: o.side, qty, purpose: o.purpose, reason: o.reason,
        expected: f.expected, price: f.price, commission: f.commission, spread_cost: f.spread_cost,
        slippage_cost: f.slippage_cost, impact_cost: f.impact_cost, participation: f.participation,
        value: qty * f.price, realised, note };
      fills.push(fill);
      const after = pf.qty(s);
      if (o.purpose === 'entry' && after !== 0 && (o.stop_loss || o.take_profit)) {
        const pos = pf.position(s), d = after > 0 ? 1 : -1;
        pos.stop = o.stop_loss ? f.price * (1 - d * o.stop_loss) : null;
        pos.target = o.take_profit ? f.price * (1 + d * o.take_profit) : null;
      }
      trackTrip(s, before, after, fill);
    }
    function trackTrip(s, before, after, fill) {
      let trip = openTrips[s];
      if (trip) {
        trip.pnl += fill.realised - fill.commission;
        trip.costs += fill.commission + fill.spread_cost + fill.slippage_cost + fill.impact_cost;
      }
      if (trip && (after === 0 || (after > 0) !== (before > 0))) {
        trip.exit_time = now; trip.exit_price = fill.price; trip.exit_reason = fill.reason; trip.exit_kind = fill.purpose;
        trip.return = trip.cost_basis ? trip.pnl / trip.cost_basis : 0;
        trips.push(trip); delete openTrips[s]; trip = null;
      }
      if (after !== 0 && !trip) {
        openTrips[s] = { symbol: s, side: after > 0 ? 'long' : 'short', entry_time: now, entry_price: fill.price,
          entry_reason: fill.reason, qty: Math.abs(after), cost_basis: Math.abs(after) * fill.price, bars: 0,
          pnl: before === 0 ? -fill.commission : 0,
          costs: fill.commission + fill.spread_cost + fill.slippage_cost + fill.impact_cost };
      }
    }
    function checkExits(s, bar, h) {
      const pos = pf.positions[s];
      if (!pos || pos.qty === 0 || (pos.stop === null && pos.target === null)) return;
      const long = pos.qty > 0;
      let hit = false, level = null, why = '', kind = '';
      if (pos.stop !== null) {
        kind = 'stop';
        if ((long && bar.o <= pos.stop) || (!long && bar.o >= pos.stop)) { hit = true; level = bar.o; why = 'stop loss, gapped through at the open'; }
        else if ((long && bar.l <= pos.stop) || (!long && bar.h >= pos.stop)) { hit = true; level = pos.stop; why = 'stop loss hit'; }
      }
      if (!hit && pos.target !== null) {
        kind = 'target';
        if ((long && bar.o >= pos.target) || (!long && bar.o <= pos.target)) { hit = true; level = bar.o; why = 'take profit, gapped past at the open'; }
        else if ((long && bar.h >= pos.target) || (!long && bar.l <= pos.target)) { hit = true; level = pos.target; why = 'take profit hit'; }
      }
      if (hit) execute(newOrder(s, long ? -1 : 1, Math.abs(pos.qty), kind, why), level, h);
    }
    function blowUp() {
      blown = true;
      for (const s in pf.positions) { const p = pf.positions[s]; if (p.qty) { pf.cash += p.qty * pf.prices[s]; p.qty = 0; } }
      trading = false;
    }

    syms.forEach(s => {
      hist[s] = new History(s); strat[s] = new StrategyClass(params); pending[s] = [];
      ctxs[s] = { history: hist[s], trading: false, symbol: s,
        get position() { return pf.qty(s); },
        get entryPrice() { const p = pf.positions[s]; return p && p.qty ? p.avg : null; },
        get allowShort() { return cfg.allow_short; },
        get equity() { return pf.equity; },
        buy: (reason, sl, tp) => submitEntry(s, 1, reason, sl, tp),
        short: (reason, sl, tp) => submitEntry(s, -1, reason, sl, tp),
        close: (reason) => submitExit(s, reason, 'exit') };
    });

    const cursors = {}, ends = {};
    for (const s of syms) {
      const m = M[s];
      const a = cfg.start ? indexOf(m, cfg.start) : 0;
      cursors[s] = cfg.start ? Math.max(0, a - cfg.warmup) : 0;
      ends[s] = cfg.end ? indexOf(m, cfg.end + '~') : m.bars.length;
    }
    const timeSet = new Set();
    for (const s of syms) for (let i = cursors[s]; i < ends[s]; i++) timeSet.add(M[s].bars[i].d);
    const times = Array.from(timeSet).sort();
    const rec = { times: [], equity: [], cash: [], gross: [], net: [], qty: {}, price: {} };
    syms.forEach(s => { rec.qty[s] = []; rec.price[s] = []; });
    let started = false;
    syms.forEach(s => strat[s].initialize(ctxs[s]));

    for (const t of times) {
      now = t;
      trading = (!cfg.start || t >= cfg.start) && !blown;
      const updated = [];
      for (const s of syms) {
        const m = M[s], i = cursors[s];
        if (i >= ends[s] || m.bars[i].d !== t) continue;
        const bar = m.bars[i], h = hist[s];
        cursors[s] = i + 1;
        if (trading && cfg.dividends && (t in m.dividends) && pf.qty(s)) {
          const amount = pf.payDividend(s, m.dividends[t]);
          dividends.push({ time: t, symbol: s, per_share: m.dividends[t], amount });
          if (openTrips[s]) openTrips[s].pnl += amount;
        }
        for (const o of pending[s]) execute(o, bar.o, h);
        pending[s] = [];
        checkExits(s, bar, h);
        pf.mark(s, bar.c);
        h.add(bar);
        if (openTrips[s]) openTrips[s].bars += 1;
        updated.push(s);
      }
      if (trading && pf.equity <= 0) blowUp();
      else if (trading && pf.marginCall()) for (const s of syms) submitExit(s, 'margin call, equity below maintenance', 'margin');
      for (const s of updated) { ctxs[s].trading = trading; strat[s].onMarketData(ctxs[s]); }
      if (trading || started) {
        started = true;
        rec.times.push(t); rec.equity.push(Math.max(0, pf.equity)); rec.cash.push(pf.cash);
        rec.gross.push(pf.gross); rec.net.push(pf.net);
        for (const s of syms) { rec.qty[s].push(pf.qty(s)); rec.price[s].push(s in pf.prices ? pf.prices[s] : null); }
      }
    }
    const first = strat[syms[0]];
    const openList = Object.keys(openTrips).map(s => {           // open positions, valued at the last price
      const t = Object.assign({}, openTrips[s]), p = pf.positions[s];
      t.unrealised = p && p.qty ? p.qty * (pf.prices[s] - p.avg) : 0;
      t.pnl_marked = t.pnl + t.unrealised; t.return = t.cost_basis ? t.pnl_marked / t.cost_basis : 0; t.open = true;
      return t;
    });
    return Object.assign({ symbols: syms, strategy: StrategyClass.label, params: Object.assign({}, first.params),
      periods_per_year: markets[0].periodsPerYear, interval: markets[0].interval, start_cash: cfg.cash },
      rec, { orders, fills, trips, open_trips: openList, dividends, fees: Object.assign({}, pf.fees),
      dividends_total: pf.dividends, blown, realised: pf.realised, unrealised: pf.unrealised(), cash_end: pf.cash,
      final: snapshot(pf) });
  }

  // =============================== METRICS ===============================
  const mean = (xs) => { if (!xs.length) return 0; let s = 0; for (const x of xs) s += x; return s / xs.length; };
  function stdev(xs) {
    if (xs.length < 2) return 0;
    const m = mean(xs); let q = 0; for (const x of xs) q += (x - m) * (x - m);
    return Math.sqrt(q / (xs.length - 1));
  }
  function returnsOf(v) { const out = []; for (let i = 1; i < v.length; i++) out.push(v[i - 1] > 0 ? v[i] / v[i - 1] - 1 : 0); return out; }
  function drawdown(v) {
    let peak = -1e18, worst = 0, under = 0, longest = 0;
    for (const x of v) {
      if (x >= peak) { peak = x; under = 0; } else { under += 1; longest = Math.max(longest, under); }
      if (peak > 0) worst = Math.min(worst, x / peak - 1);
    }
    return [worst, longest];
  }
  function align(times, bTimes, bValues) {
    const out = []; let j = 0, last = null;
    for (const t of times) { while (j < bTimes.length && bTimes[j] <= t) { last = bValues[j]; j++; } out.push(last); }
    const first = out.find(x => x !== null);
    return out.map(x => (x !== null ? x : (first === undefined ? null : first)));
  }
  function summarise(r, bench) {
    const eq = r.equity, ppy = r.periods_per_year || 252;
    if (eq.length < 2) return {};
    const start = eq[0], end = eq[eq.length - 1], rets = returnsOf(eq), years = rets.length / ppy;
    const sd = stdev(rets);
    const down = rets.map(x => Math.min(0, x));
    const ddDev = down.length ? Math.sqrt(down.reduce((a, d) => a + d * d, 0) / down.length) : 0;
    const dd = drawdown(eq);
    const cagr = (start > 0 && end > 0 && years > 0) ? Math.pow(end / start, 1 / years) - 1 : -1;
    const trips = r.trips, opens = r.open_trips || [];
    const pnls = trips.map(t => t.pnl).concat(opens.map(t => t.pnl_marked));
    const tripRets = trips.map(t => t.return).concat(opens.map(t => t.return));
    const held = trips.map(t => t.bars).concat(opens.map(t => t.bars));
    const wins = pnls.filter(x => x > 0);
    const won = wins.reduce((a, x) => a + x, 0), lost = -pnls.filter(x => x <= 0).reduce((a, x) => a + x, 0);
    const exp = []; for (let i = 0; i < eq.length; i++) if (eq[i] > 0) exp.push(r.gross[i] / eq[i]);
    const traded = r.fills.reduce((a, f) => a + f.value, 0);
    const fees = r.fees, costs = fees.commission + fees.spread + fees.slippage + fees.impact;
    const m = { start: r.times[0], end: r.times[r.times.length - 1], years, start_value: start, end_value: end,
      total_return: start ? end / start - 1 : 0, cagr, volatility: sd * Math.sqrt(ppy),
      sharpe: sd > 0 ? mean(rets) / sd * Math.sqrt(ppy) : 0, sortino: ddDev > 0 ? mean(rets) / ddDev * Math.sqrt(ppy) : 0,
      max_drawdown: dd[0], longest_underwater_bars: dd[1], calmar: dd[0] < 0 ? cagr / Math.abs(dd[0]) : 0,
      trades: trips.length, open_trades: opens.length, win_rate: pnls.length ? wins.length / pnls.length : 0,
      profit_factor: lost > 0 ? won / lost : (won > 0 ? Infinity : 0), avg_trade: mean(tripRets),
      avg_bars_held: mean(held), time_in_market: r.gross.filter(g => g > 0).length / r.gross.length,
      avg_exposure: mean(exp), turnover: years > 0 ? traded / mean(eq) / years : 0, costs, costs_pct: costs / r.start_cash,
      commission: fees.commission, spread: fees.spread, slippage: fees.slippage, impact: fees.impact,
      dividends: r.dividends_total || 0, blown_up: !!r.blown };
    if (bench) Object.assign(m, compare(r, bench));
    return m;
  }
  function compare(r, bench) {
    const eq = r.equity, ppy = r.periods_per_year || 252;
    const b = align(r.times, bench.bars.map(x => x.d), bench.bars.map(x => x.c));
    if (!b.length || b[0] === null) return {};
    const rs = returnsOf(eq), rb = returnsOf(b), years = rs.length / ppy;
    const bTotal = b[b.length - 1] / b[0] - 1;
    const bCagr = years > 0 ? Math.pow(b[b.length - 1] / b[0], 1 / years) - 1 : 0;
    const sCagr = (years > 0 && eq[eq.length - 1] > 0) ? Math.pow(eq[eq.length - 1] / eq[0], 1 / years) - 1 : -1;
    const mb = mean(rb), ms = mean(rs);
    const varB = mean(rb.map(x => (x - mb) * (x - mb)));
    const cov = mean(rs.map((a, i) => (a - ms) * (rb[i] - mb)));
    const beta = varB > 0 ? cov / varB : 0;
    const active = rs.map((a, i) => a - rb[i]);
    const te = stdev(active) * Math.sqrt(ppy);
    const sdS = stdev(rs), sdB = stdev(rb);
    return { benchmark: bench.name, benchmark_symbol: bench.symbol, benchmark_return: bTotal, benchmark_cagr: bCagr,
      excess_return: (eq[eq.length - 1] / eq[0] - 1) - bTotal, excess_cagr: sCagr - bCagr, beta,
      alpha: (ms - beta * mb) * ppy, tracking_error: te, information_ratio: te > 0 ? mean(active) * ppy / te : 0,
      correlation: (sdS > 0 && sdB > 0) ? cov / (sdS * sdB) : 0, benchmark_curve: b };
  }

  // =============================== SYNTHETIC MARKETS (for stress tests) ===============================
  // The same six recipes as simulator.py. The random draws differ from Python's,
  // so the browser's stress numbers are close to, not identical to, the report's.
  const SCENARIOS = ['normal', 'crash', 'volatile', 'bear', 'sideways', 'flash'];
  const SCENARIO_ABOUT = { normal: 'A steady rise with everyday noise.', crash: 'A rise, then a sharp 45% fall over a month, then a slow recovery.',
    volatile: 'Choppy and nervous, high volatility with the odd shock.', bear: 'A long slow grind down, about 12% a year.',
    sideways: 'No trend at all, the price wanders inside a range.', flash: 'Calm, then a sudden 20% one day drop that half recovers.' };
  function seeded(seed) {
    let a = (seed * 2654435761) >>> 0;
    const next = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const gauss = () => { let u = 0, v = 0; while (u === 0) u = next(); while (v === 0) v = next(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
    return { next, gauss };
  }
  function synthetic(scenario, seed, n) {
    n = n || 1000; const R = seeded(seed || 1), g = R.gauss;
    let drift = 0.0005, vol = 0.011, crashAt = -1, crashLen = 0, depth = 0;
    if (scenario === 'crash') { crashAt = Math.floor(n * 0.55); crashLen = 22; depth = 0.45; vol = 0.012; }
    else if (scenario === 'volatile') { drift = 0.0002; vol = 0.028; }
    else if (scenario === 'bear') { drift = -0.0005; vol = 0.013; }
    else if (scenario === 'sideways') { drift = 0; vol = 0.012; }
    else if (scenario === 'flash') { drift = 0.0004; vol = 0.009; }
    let price = 100, prev = 100; const bars = [], flashAt = Math.floor(n * 0.6);
    for (let i = 0; i < n; i++) {
      let r = drift + vol * g();
      if (scenario === 'volatile' && R.next() < 0.03) r += 0.05 * g();
      if (scenario === 'sideways') r += 0.02 * Math.log(100 / price);
      if (crashAt > 0 && i >= crashAt && i < crashAt + crashLen) r += Math.log(1 - depth) / crashLen;
      if (scenario === 'flash' && i === flashAt) r += Math.log(0.8);
      if (scenario === 'flash' && i > flashAt && i <= flashAt + 10) r += Math.log(1.1) / 10;
      const open = prev * Math.exp(vol * 0.3 * g());
      price *= Math.exp(r);
      const wig = Math.abs(g()) * vol * 0.5;
      bars.push({ d: 'D' + String(i + 1).padStart(5, '0'), o: open, h: Math.max(open, price) * (1 + wig),
        l: Math.min(open, price) * (1 - wig), c: price, v: Math.round(2e6 * Math.exp(0.3 * g()) * (1 + 20 * Math.abs(r))) });
      prev = price;
    }
    return { symbol: 'SIM-' + scenario.toUpperCase(), name: 'Synthetic ' + scenario, bars, interval: '1d',
      periodsPerYear: 252, dividends: {}, fractional: false, benchmark: null };
  }

  // =============================== THE TESTER ===============================
  const METHOD_LABEL = { backtest: 'Historical backtest', out_of_sample: 'Out-of-sample test',
    walk_forward: 'Walk-forward test', stress: 'Stress test on synthetic markets' };
  const METHOD_WARNING = {
    backtest: 'This is how the rule would have done on data it was tuned on. It does not prove future profit.',
    out_of_sample: 'Settings were chosen on the training years only, then frozen and tested on years the optimiser never saw.',
    walk_forward: 'Settings were re-chosen every year using only the years before it. Only the unseen test years count.',
    stress: 'Synthetic markets, each built to be one clear kind of market. They say how a rule copes, not what it will earn.' };

  function validParams(p) {
    if ('fast' in p && 'slow' in p && p.fast >= p.slow) return false;
    if ('low' in p && 'high' in p && p.low >= p.high) return false;
    return true;
  }
  function gridOf(S, base) {
    const keys = Object.keys(S.grid || {});
    let combos = [Object.assign({}, base)];
    for (const k of keys) {                     // same order as itertools.product
      const next = [];
      for (const c of combos) for (const v of S.grid[k]) { const p = Object.assign({}, c); p[k] = v; next.push(p); }
      combos = next;
    }
    combos = combos.filter(validParams);
    return combos.length ? combos : [Object.assign({}, base)];
  }
  function score(m, objective) {
    if (!m || m.sharpe === undefined) return -1e9;
    if (objective === 'cagr') return m.cagr;
    if (objective === 'calmar') return m.calmar;
    return m.sharpe;
  }
  function one(exp, params, start, end, bench, cfg) {
    const c = withConfig(cfg || exp.config, { start, end });
    const r = runBacktest(exp.markets, exp.strategy, params, c);
    return [r, summarise(r, bench || null)];
  }
  function optimise(exp, start, end) {
    const table = [];
    for (const p of gridOf(exp.strategy, exp.params)) {
      const m = one(exp, p, start, end)[1];
      table.push({ params: p, score: score(m, exp.objective), cagr: m.cagr, sharpe: m.sharpe, max_drawdown: m.max_drawdown, trades: m.trades });
    }
    table.sort((a, b) => b.score - a.score);
    return [table[0].params, table];
  }
  function timesOf(m, start, end) {
    return m.bars.filter(b => (!start || b.d >= start) && (!end || b.d.slice(0, end.length) <= end)).map(b => b.d);
  }
  function pack(r, m) {
    const sym = r.symbols ? r.symbols[0] : null;
    const out = { metrics: Object.assign({}, m), times: r.times, equity: r.equity, gross: r.gross, cash: r.cash,
      fills: r.fills, trips: r.trips, open_trips: r.open_trips || [], orders: r.orders, dividends: r.dividends,
      fees: r.fees, params: r.params, qty: r.qty && sym ? r.qty[sym] : (r.qtyList || null), final: r.final || null };
    delete out.metrics.benchmark_curve;
    if (m.benchmark_curve) out.benchmark_curve = m.benchmark_curve;
    return out;
  }
  function hold(exp, start, end, bench, cfg) { return one(Object.assign({}, exp, { strategy: BuyHold }), {}, start, end, bench, cfg); }

  function mBacktest(exp) {
    const res = one(exp, exp.params, exp.start, exp.end, exp.bench);
    const h = exp.strategy === BuyHold ? res : hold(exp, exp.start, exp.end, exp.bench);
    return { method: 'backtest', label: METHOD_LABEL.backtest, warning: METHOD_WARNING.backtest,
      main: pack(res[0], res[1]), buy_hold: { metrics: h[1], equity: h[0].equity, times: h[0].times } };
  }
  function mOutOfSample(exp) {
    const times = timesOf(exp.markets[0], exp.start, exp.end);
    const cut = typeof exp.split === 'string' ? exp.split : times[Math.floor(times.length * exp.split)];
    let trainEnd = null; for (const t of times) if (t < cut) trainEnd = t;
    const opt = optimise(exp, times[0], trainEnd), best = opt[0];
    const tr = one(exp, best, times[0], trainEnd, exp.bench);
    const te = one(exp, best, cut, times[times.length - 1], exp.bench);
    const h = hold(exp, cut, times[times.length - 1], exp.bench);
    return { method: 'out_of_sample', label: METHOD_LABEL.out_of_sample, warning: METHOD_WARNING.out_of_sample,
      train: { start: times[0], end: trainEnd, metrics: tr[1] }, test: { start: cut, end: times[times.length - 1] },
      chosen: best, grid: opt[1].slice(0, 10), main: pack(te[0], te[1]),
      buy_hold: { metrics: h[1], equity: h[0].equity, times: h[0].times },
      degradation: { sharpe: (te[1].sharpe || 0) - (tr[1].sharpe || 0), cagr: (te[1].cagr || 0) - (tr[1].cagr || 0) } };
  }
  function mWalkForward(exp) {
    const ppy = exp.markets[0].periodsPerYear || 252;
    const times = timesOf(exp.markets[0], exp.start, exp.end);
    const trainN = exp.train_bars || Math.trunc(exp.train_years * ppy), testN = exp.test_bars || Math.trunc(exp.test_years * ppy);
    const folds = [], st = { times: [], equity: [], gross: [], cash: [] };
    let qtyList = [], final = null;
    let fills = [], trips = [], orders = [], divs = [], opens = [];
    const fees = { commission: 0, spread: 0, slippage: 0, impact: 0 };
    let cash = exp.config.cash, a = 0;
    while (a + trainN < times.length) {
      const trA = times[a], trB = times[a + trainN - 1], teA = times[a + trainN];
      const stop = Math.min(times.length, a + trainN + testN), teB = times[stop - 1];
      if (stop - (a + trainN) < 20) break;
      const best = optimise(exp, trA, trB)[0];
      const isM = one(exp, best, trA, trB)[1];
      const res = one(exp, best, teA, teB, exp.bench, withConfig(exp.config, { cash }));
      const r = res[0], m = res[1];
      folds.push({ train: [trA, trB], test: [teA, teB], params: best, train_cagr: isM.cagr, train_sharpe: isM.sharpe,
        test_return: m.total_return, test_sharpe: m.sharpe, test_max_drawdown: m.max_drawdown, trades: m.trades,
        benchmark_return: m.benchmark_return === undefined ? null : m.benchmark_return });
      st.times = st.times.concat(r.times); st.equity = st.equity.concat(r.equity); st.gross = st.gross.concat(r.gross);
      st.cash = st.cash.concat(r.cash); qtyList = qtyList.concat(r.qty[r.symbols[0]]); final = r.final;
      fills = fills.concat(r.fills); trips = trips.concat(r.trips); opens = opens.concat(r.open_trips); orders = orders.concat(r.orders); divs = divs.concat(r.dividends);
      for (const k in fees) fees[k] += r.fees[k];
      cash = r.equity[r.equity.length - 1];
      a += testN;
    }
    if (!folds.length) throw new Error('not enough data for one training window and one test window');
    const joined = Object.assign({}, st, { fills, trips, open_trips: opens, orders, dividends: divs, fees, periods_per_year: ppy,
      start_cash: exp.config.cash, dividends_total: divs.reduce((x, d) => x + d.amount, 0), params: folds[folds.length - 1].params,
      qtyList, final });
    const m = summarise(joined, exp.bench);
    const h = hold(exp, folds[0].test[0], folds[folds.length - 1].test[1], exp.bench);
    const isC = folds.map(f => f.train_cagr).filter(x => x !== undefined && x !== null);
    const avgIs = isC.length ? mean(isC) : 0;
    const distinct = new Set(folds.map(f => JSON.stringify(Object.keys(f.params).sort().map(k => [k, f.params[k]]))));
    return { method: 'walk_forward', label: METHOD_LABEL.walk_forward, warning: METHOD_WARNING.walk_forward, folds,
      main: pack(joined, m), buy_hold: { metrics: h[1], equity: h[0].equity, times: h[0].times },
      efficiency: avgIs > 0 ? m.cagr / avgIs : null, stability: { folds: folds.length, different_settings: distinct.size } };
  }
  function mStress(exp) {
    const rows = [];
    const cfg = withConfig(exp.config, { start: null, end: null });
    for (const scen of exp.scenarios || SCENARIOS) {
      const res = [], holds = [];
      for (const seed of exp.seeds || [1, 2, 3]) {
        const mk = synthetic(scen, seed);
        res.push(summarise(runBacktest([mk], exp.strategy, exp.params, cfg)));
        holds.push(summarise(runBacktest([mk], BuyHold, {}, cfg)));
      }
      const avg = (k, xs) => mean(xs.map(x => x[k]));
      rows.push({ scenario: scen, about: SCENARIO_ABOUT[scen], return: avg('total_return', res),
        worst_return: Math.min.apply(null, res.map(x => x.total_return)), max_drawdown: avg('max_drawdown', res),
        sharpe: avg('sharpe', res), trades: avg('trades', res), buy_hold_return: avg('total_return', holds),
        buy_hold_drawdown: avg('max_drawdown', holds) });
    }
    const ex = synthetic('crash', (exp.seeds || [1])[0]);
    const r = runBacktest([ex], exp.strategy, exp.params, cfg);
    return { method: 'stress', label: METHOD_LABEL.stress, warning: METHOD_WARNING.stress, scenarios: rows,
      main: pack(r, summarise(r)), market: ex };
  }
  function costSensitivity(exp, levels) {
    return (levels || SLIPPAGE_PRESETS).map(bps => {
      const ex = Object.assign({}, exp.config.execution, { slippage_bps: bps });
      const m = one(exp, exp.params, exp.start, exp.end, exp.bench, withConfig(exp.config, { execution: ex }))[1];
      return { slippage_bps: bps, cagr: m.cagr, sharpe: m.sharpe, excess_cagr: m.excess_cagr === undefined ? null : m.excess_cagr,
        costs_pct: m.costs_pct, trades: m.trades };
    });
  }
  function fillSensitivity(exp) {
    return ['next_open', 'close'].map(mode => {
      const ex = Object.assign({}, exp.config.execution, { fill_at: mode });
      const m = one(exp, exp.params, exp.start, exp.end, exp.bench, withConfig(exp.config, { execution: ex }))[1];
      return { fill_at: mode, cagr: m.cagr, sharpe: m.sharpe, max_drawdown: m.max_drawdown };
    });
  }
  function parameterMap(exp) {
    return gridOf(exp.strategy, exp.params).map(p => {
      const m = one(exp, p, exp.start, exp.end, exp.bench)[1];
      return { params: p, cagr: m.cagr, sharpe: m.sharpe, max_drawdown: m.max_drawdown };
    });
  }
  // exp = { strategy (class or key), params, markets: [market], bench, start, end, config,
  //         method, split, train_years, test_years, objective, scenarios, seeds }
  function runExperiment(exp, robustness) {
    exp = Object.assign({ params: {}, bench: null, start: null, end: null, config: defaultConfig(), method: 'backtest',
      split: 0.7, train_years: 3, test_years: 1, objective: 'sharpe' }, exp);
    if (typeof exp.strategy === 'string') exp.strategy = BY_KEY[exp.strategy];
    const fn = { backtest: mBacktest, out_of_sample: mOutOfSample, walk_forward: mWalkForward, stress: mStress }[exp.method];
    const res = fn(exp);
    if (robustness !== false && exp.method !== 'stress') res.robustness = { costs: costSensitivity(exp), fills: fillSensitivity(exp) };
    return res;
  }

  const api = { ind, History, LookAheadError, STRATEGIES, BY_KEY, BUY, SELL, HOLD, Strategy, makeSizing,
    makeExecution, presetExecution, SLIPPAGE_PRESETS, Portfolio, marketFromFile, indexOf, defaultConfig, withConfig,
    runBacktest, summarise, compare, align, drawdown, synthetic, SCENARIOS, SCENARIO_ABOUT, METHOD_LABEL, METHOD_WARNING,
    gridOf, optimise, runExperiment, costSensitivity, fillSensitivity, parameterMap };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AgoraEngine = api;
})(typeof window !== 'undefined' ? window : this);
