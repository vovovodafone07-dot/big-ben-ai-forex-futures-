"""Run bounded, dated research from a verified application export; no API calls."""
import argparse
import hashlib
import importlib.util
import json
import math
from datetime import datetime,timezone
from pathlib import Path

root=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,root/path)
    loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded


backup=module('walk_backup','platform/backend/backup.py')
wf=module('walk_engine','research/walk_forward.py')
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('snapshot',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.snapshot.stat().st_size>backup.MAX_BYTES:raise SystemExit('Snapshot size limit')
bundle=json.loads(args.snapshot.read_text(encoding='utf-8'));backup.verify(bundle)
manifest=json.loads((root/'tradingview/current_strategy.json').read_text(encoding='utf-8'))
code=(root/'tradingview'/manifest['source']).read_text(encoding='utf-8')
if hashlib.sha256(code.encode()).hexdigest()!=manifest['source_sha256']:raise SystemExit('Pine hash mismatch')
source_time=datetime.fromisoformat(bundle['created_at'])
events=bundle['tables']['events'];event_rows=[dict(zip(events['columns'],r)) for r in events['rows']]
ticks={}
for row in event_rows:
    event=json.loads(row['payload'])
    tick=event.get('tick_size')
    if type(tick) not in (int,float) or not math.isfinite(tick) or tick<=0:continue
    stamp=datetime.fromisoformat(row['time'].replace('Z','+00:00'))
    if stamp>source_time:continue
    if row['symbol'] not in ticks or ticks[row['symbol']][0]<stamp:ticks[row['symbol']]=(stamp,tick)
table=bundle['tables']['market_candles'];candles=[dict(zip(table['columns'],r)) for r in table['rows']]
reports=[];skipped=[]
for label in ('EUR/USD','GBP/USD','USD/JPY'):
    symbol='OANDA:'+label.replace('/','')
    rows=sorted(({k:r[k] for k in ('time','open','high','low','close')} for r in candles if r['provider']=='Twelve Data' and r['symbol']==label),key=lambda r:r['time'])
    if symbol not in ticks or len(rows)<660:
        skipped.append({'symbol':symbol,'reason':'insufficient_history_or_authenticated_tick_metadata'});continue
    report=wf.run(rows[-10000:],ticks[symbol][1],manifest,now=source_time)
    report.update(symbol=symbol,history_symbol=label,source_provider='Twelve Data',
                  source_feed_differs_from_pine=True,tick_size_source='stored authenticated TradingView event',
                  input_snapshot_sha256=hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
                  runner_sha256=hashlib.sha256(((root/'research/walk_forward.py').read_text(encoding='utf-8')+Path(__file__).read_text(encoding='utf-8')).encode()).hexdigest())
    reports.append(report)
result={'mode':'STATIC_DATED_RESEARCH_SNAPSHOT','created_at':datetime.now(timezone.utc).isoformat(),
        'input_snapshot_created_at':bundle['created_at'],'runs':reports,'skipped':skipped,
        'automatic_refresh':False,'promotion_allowed':False}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print('Saved historical walk-forward reports:',len(reports))
for report in reports:
    print(report['symbol'],report['candles'],'candles',len(report['folds']),'folds',report['status'])
