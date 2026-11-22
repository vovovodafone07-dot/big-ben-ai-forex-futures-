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
  setAttribute(name,value) { (this.attributes ||= {})[name]=value; }
  getContext() { return null; } // Node DOM mock: browser canvas drawing tested through API contracts.
  async emit(type, detail = {}) { for (const listener of this.listeners[type] || []) await listener({type, preventDefault() {}, ...detail}); }
}
function boot(savedSymbol = '') {
  const elements = new Map();
  const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const listeners = new Map();
  const calls = [], pending = new Map(), storage = new Map(savedSymbol ? [['bigben-desk-symbol', savedSymbol]] : []);
  let defer = false;
  const analysis = symbol => ({symbol: symbol === 'EURUSD' ? 'OANDA:EURUSD' : symbol, mode:'scalp', status:'DATA_UNAVAILABLE', reason_code:'SOURCE_IDENTITY_UNVERIFIED', instrument:{name:symbol}, provider:null, entry:null, sl:null, targets:[], broker_execution:false});
  const fetch = async (url, options = {}) => {
    let data;
    if (url === '/api/integrations') data = {tradingview:{symbols:[{symbol:'FOREXCOM:XAUUSD',fresh:true}],observed_symbols:11,fresh_symbols:1,heartbeat_recent:true,live_feed_verified:false},news:[],ai:{key_configured:true,enabled:true,model:'fixture-model',connection_verified:false},storage:'fixture'};
    else if (url === '/api/news') data = {sources:[], news:[], calendar:[]};
    else if (url === '/api/research/pine-runs') data = {count:0,runs:[]};
    else if (url === '/api/instant/analyze') {
      const body = JSON.parse(options.body); calls.push(body);
      if (defer) return new Promise(resolve => pending.set(body.symbol, () => resolve({ok:true,json:async () => analysis(body.symbol)})));
      data = analysis(body.symbol);
    } else if (url.startsWith('/api/chart/candles?symbol=')) { const symbol=decodeURIComponent(url.split('symbol=')[1]); data={symbol,provider:'Twelve Data',fresh:false,candles:[]};
    } else throw Error('Unexpected fixture fetch: ' + url);
    return {ok:true,json:async () => data};
  };
  const window = {matchMedia() { return {matches:false}; }, addEventListener(type, listener) { (listeners.get(type) || (listeners.set(type, []), listeners.get(type))).push(listener); }, dispatchEvent(event) { for (const listener of listeners.get(event.type) || []) listener(event); }};
  const context = vm.createContext({document:{getElementById:get,createElement:tag => new Element(tag),activeElement:null},window,fetch,localStorage:{getItem:key => storage.get(key) || null,setItem:(key,value) => storage.set(key,value)},CustomEvent:class {constructor(type,options) {this.type=type;this.detail=options.detail;}},setInterval() {},Date,URL,JSON,Object,String,console});
  vm.runInContext(script('symbol-chart-controller'), context);
  vm.runInContext(script('pearl-desk-controller'), context);
  return {get, window, calls, pending, storage, setDefer(value) {defer=value;}};
}
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
const chartSymbol = app => decodeURIComponent((app.get('desk-chart-link').href||'').split('symbol=')[1]?.split('&')[0]||'');
(async () => {
  const app = boot(); await flush();
  assert.equal(app.get('desk-symbol').value, 'OANDA:EURUSD', 'native OHLC chart defaults to supported EURUSD rather than an unsupported historical TradingView symbol');
  assert.equal(app.get('desk-live-chart').children[0].tagName,'canvas','chart is platform native canvas, not TradingView embed');
  assert.equal(chartSymbol(app), 'OANDA:EURUSD');
  assert.ok(!script('symbol-chart-controller').includes('embed-widget-advanced-chart.js'),'no TradingView embedding');
  assert.equal(app.calls[0].mode, 'scalp', 'automatic analysis must not request the LLM');
  assert.ok(app.get('desk-analysis-status').textContent.includes('SOURCE_IDENTITY_UNVERIFIED'));
  assert.ok(app.get('desk-chart-link').href.includes('OANDA%3AEURUSD'));
  app.get('desk-symbol').value = 'EURUSD'; await app.get('desk-symbol').emit('change'); await flush();
  assert.equal(chartSymbol(app), 'OANDA:EURUSD');
  assert.equal(app.get('desk-symbol').value, 'OANDA:EURUSD');
  app.get('desk-symbol').value = 'CME_MINI:NQ1!'; await app.get('desk-symbol').emit('change'); await flush();
  assert.equal(chartSymbol(app), 'CME_MINI:NQ1!', 'Futures symbol remains unchanged; no CFD substitution');
  assert.ok(app.get('desk-chart-link').href.includes('CME_MINI%3ANQ1!'));
  assert.ok(app.calls.every(call => call.mode === 'scalp'));
  app.setDefer(true);
  app.get('desk-symbol').value = 'CME_MINI:ES1!'; const old = app.get('desk-symbol').emit('change');
  app.get('desk-symbol').value = 'OANDA:GBPUSD'; const latest = app.get('desk-symbol').emit('change');
  await flush();
  app.pending.get('OANDA:GBPUSD')(); await latest;
  app.pending.get('CME_MINI:ES1!')(); await old; await flush();
  assert.equal(chartSymbol(app), 'OANDA:GBPUSD', 'late response for prior symbol must be ignored');
  assert.equal(app.get('desk-symbol').value, 'OANDA:GBPUSD');
  assert.equal(app.storage.get('bigben-desk-symbol'), 'OANDA:GBPUSD');
  assert.equal(app.get('desk-analyze').disabled, false);
  app.window.dispatchEvent({type:'bigben:instrument',detail:{symbol:'https://evil.invalid/script'}});
  assert.equal(chartSymbol(app), 'OANDA:GBPUSD', 'invalid symbol cannot inject URL');
  app.setDefer(false); await app.get('desk-analyze').emit('click');
  assert.equal(app.calls.at(-1).mode, 'scalp', 'native platform Analyze must not invoke external LLM');
  const restored = boot('CME_MINI:MNQ1!'); await flush();
  assert.equal(chartSymbol(restored), 'CME_MINI:MNQ1!', 'remembered Futures selection survives reload');
  console.log('Passed native chart/analysis symbol selection, no TV embed, futures identity, stale-response isolation, and no LLM request.');
})().catch(error => {console.error(error);process.exitCode = 1;});
