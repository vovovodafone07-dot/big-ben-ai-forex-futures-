/* Local DOM/network fixtures only. No browser, provider call, market price, or order. */
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '..', 'platform', 'index.html'), 'utf8');
const script = id => {
  const match = html.match(new RegExp('<script id="' + id + '">([\\s\\S]*?)<\\/script>'));
  assert.ok(match, 'script missing: ' + id);
  return match[1];
};
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.style = {}; this.listeners = {}; this.value = ''; this.textContent = ''; this.disabled = false; this.checked = false; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  async emit(type, detail = {}) { for (const listener of this.listeners[type] || []) await listener({type, preventDefault() {}, ...detail}); }
}
function boot(savedSymbol = '') {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const listeners = new Map();
  const calls = [], pending = new Map(), storage = new Map(savedSymbol ? [['bigben-desk-symbol', savedSymbol]] : []);
  let defer = false;
  const analysis = symbol => ({symbol: symbol === 'EURUSD' ? 'OANDA:EURUSD' : symbol, fresh:true, decision:'WAIT', decision_reason_code:'NO_VALID_SIGNAL', instrument:{name:symbol}, reasons:['Fixture: no trade'], checks:[], news:[], news_scenarios:[], agent_tasks:[], ai:{state:'CONFIGURED',connection_verified:false}, full_trade:null, scalp:null});
  const fetch = async (url, options = {}) => {
    let data;
    if (url === '/api/integrations') data = {tradingview:{symbols:[{symbol:'FOREXCOM:XAUUSD',fresh:true}],observed_symbols:11,fresh_symbols:1,heartbeat_recent:true,live_feed_verified:false},news:[],ai:{key_configured:true,enabled:true,model:'fixture-model',connection_verified:false},storage:'fixture'};
    else if (url === '/api/news') data = {sources:[], news:[], calendar:[]};
    else if (url === '/api/research/pine-runs') data = {count:0,runs:[]};
    else if (url === '/api/analyze') {
      const body = JSON.parse(options.body); calls.push(body);
      if (defer) return new Promise(resolve => pending.set(body.symbol, () => resolve({ok:true,json:async () => analysis(body.symbol)})));
      data = analysis(body.symbol);
    } else throw Error('Unexpected fixture fetch: ' + url);
    return {ok:true,json:async () => data};
  };
  const window = {addEventListener(type, listener) { (listeners.get(type) || (listeners.set(type, []), listeners.get(type))).push(listener); }, dispatchEvent(event) { for (const listener of listeners.get(event.type) || []) listener(event); }};
  const context = vm.createContext({document:{getElementById:get,createElement:tag => new Element(tag),activeElement:null},window,fetch,localStorage:{getItem:key => storage.get(key) || null,setItem:(key,value) => storage.set(key,value)},CustomEvent:class {constructor(type,options) {this.type=type;this.detail=options.detail;}},setInterval() {},Date,URL,JSON,Object,String,console});
  vm.runInContext(script('symbol-chart-controller'), context);
  vm.runInContext(script('pearl-desk-controller'), context);
  return {get, window, calls, pending, storage, setDefer(value) {defer=value;}};
}
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
const config = app => JSON.parse(app.get('desk-live-chart').children[0].children[2].textContent);
(async () => {
  const app = boot(); await flush();
  assert.equal(app.get('desk-symbol').value, 'FOREXCOM:XAUUSD', 'start from actually observed fresh symbol, not fixed EURUSD');
  assert.equal(config(app).symbol, 'FOREXCOM:XAUUSD');
  assert.equal(config(app).allow_symbol_change, false, 'platform picker is the single symbol source');
  assert.equal(app.calls[0].ai, false, 'automatic analysis must not request the LLM');
  assert.ok(app.get('desk-analysis-status').textContent.includes('لا توجد إشارة دخول صالحة'));
  assert.ok(app.get('desk-chart-link').href.includes('FOREXCOM%3AXAUUSD'));
  app.get('desk-symbol').value = 'EURUSD'; await app.get('desk-symbol').emit('change');
  assert.equal(config(app).symbol, 'OANDA:EURUSD');
  assert.equal(app.get('desk-symbol').value, 'OANDA:EURUSD');
  app.get('desk-symbol').value = 'CME_MINI:NQ1!'; await app.get('desk-symbol').emit('change');
  assert.equal(config(app).symbol, 'CME_MINI:NQ1!', 'Futures symbol must reach chart without CFD/Forex substitution');
  assert.ok(app.get('desk-chart-link').href.includes('CME_MINI%3ANQ1!'));
  assert.ok(app.calls.every(call => call.ai === false));
  app.setDefer(true);
  app.get('desk-symbol').value = 'CME_MINI:ES1!'; const old = app.get('desk-symbol').emit('change');
  app.get('desk-symbol').value = 'OANDA:GBPUSD'; const latest = app.get('desk-symbol').emit('change');
  await flush();
  app.pending.get('OANDA:GBPUSD')(); await latest;
  app.pending.get('CME_MINI:ES1!')(); await old;
  assert.equal(config(app).symbol, 'OANDA:GBPUSD', 'late response for prior symbol must be ignored');
  assert.equal(app.get('desk-symbol').value, 'OANDA:GBPUSD');
  assert.equal(app.storage.get('bigben-desk-symbol'), 'OANDA:GBPUSD');
  assert.equal(app.get('desk-analyze').disabled, false);
  app.window.dispatchEvent({type:'bigben:instrument',detail:{symbol:'https://evil.invalid/script'}});
  assert.equal(config(app).symbol, 'OANDA:GBPUSD', 'invalid symbol cannot inject URL');
  app.setDefer(false); await app.get('desk-analyze').emit('click');
  assert.equal(app.calls.at(-1).ai, true, 'LLM requires explicit Analyze action and checked option');
  const restored = boot('CME_MINI:MNQ1!'); await flush();
  assert.equal(config(restored).symbol, 'CME_MINI:MNQ1!', 'remembered Futures selection survives reload');
  console.log('Passed selected-symbol chart/analysis, Futures mapping, stale-response isolation, saved selection, and no automatic LLM request.');
})().catch(error => {console.error(error);process.exitCode = 1;});
