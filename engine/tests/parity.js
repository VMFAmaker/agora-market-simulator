// Runs a set of experiments with the browser engine (backtest.js) and prints the
// results as JSON, so tests/test_parity.py can check them against the Python engine.
const fs = require('fs');
const path = require('path');
const E = require('../backtest.js');

const ROOT = path.join(__dirname, '..', '..');
const cat = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'catalogue.json'), 'utf8'));
const META = {};
cat.securities.concat(cat.indices).forEach(m => { META[m.symbol] = m; });
const safe = (s) => s.replace(/\^/g, '').replace(/=/g, '_');
function load(sym) {
  const obj = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'daily', safe(sym) + '.json'), 'utf8'));
  return E.marketFromFile(obj, META[sym]);
}

const cases = JSON.parse(process.argv[2]);
const out = cases.map(c => {
  const cfg = E.defaultConfig({
    sizing: E.makeSizing(c.sizing[0], c.sizing[1]),
    execution: c.zero ? E.presetExecution('zero') : E.makeExecution(c.execution || {}),
    allow_short: !!c.allow_short, max_leverage: c.max_leverage || 1.0,
  });
  const res = E.runExperiment({ strategy: c.strategy, params: c.params || {}, markets: [load(c.symbol)],
    bench: c.bench ? load(c.bench) : null, config: cfg, method: c.method, start: c.start || null, end: c.end || null }, c.robustness);
  const m = res.main.metrics;
  return { total_return: m.total_return, sharpe: m.sharpe, max_drawdown: m.max_drawdown, trades: m.trades,
    fills: res.main.fills.length, end_value: m.end_value, costs: m.costs, dividends: m.dividends, win_rate: m.win_rate, open_trades: m.open_trades,
    excess_cagr: m.excess_cagr === undefined ? null : m.excess_cagr,
    folds: res.folds ? res.folds.map(f => f.params) : null, chosen: res.chosen || null,
    robustness: res.robustness ? res.robustness.costs.map(r => r.cagr) : null };
});
process.stdout.write(JSON.stringify(out));
