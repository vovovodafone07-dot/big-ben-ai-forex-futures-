"""Private, durable research drafts and analysis notes. Never executes Pine."""
import difflib
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone


def migrate(c):
    c.execute("CREATE TABLE IF NOT EXISTS strategy_drafts (id TEXT PRIMARY KEY,created_at TEXT NOT NULL,payload TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS analysis_notes (id TEXT PRIMARY KEY,symbol TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)")


def create_draft(c, value, stable, postgres=False):
    if not isinstance(value, dict) or set(value)-{'title','rationale','code'}:
        raise ValueError('draft_fields')
    title, rationale, code = (value.get(k) for k in ('title','rationale','code'))
    if not isinstance(title,str) or not 1<=len(title.strip())<=120:
        raise ValueError('draft_title')
    if not isinstance(rationale,str) or not 10<=len(rationale.strip())<=4000:
        raise ValueError('draft_rationale')
    if not isinstance(code,str) or not 20<=len(code.encode('utf-8'))<=100000 or not re.match(r'^\s*//@version=[56]\b',code):
        raise ValueError('pine_source')
    code=code.replace('\r\n','\n')
    # Draft storage does not evaluate code, import modules, or contact a broker.
    item={'id':uuid.uuid4().hex,'title':title.strip(),'rationale':rationale.strip(),
          'created_at':datetime.now(timezone.utc).isoformat(),'state':'DRAFT','author':'owner_workspace',
          'source_sha256':hashlib.sha256(code.encode()).hexdigest(),'baseline_sha256':stable['source_sha256'],
          'baseline_version':stable.get('strategy_version',stable.get('version')),'code':code,
          'baseline_code':stable['code'],'validation':'not_run','promotion_allowed':False,
          'changes_to_live_tradingview':False}
    marker='%s' if postgres else '?'
    c.execute('INSERT INTO strategy_drafts(id,created_at,payload) VALUES ('+','.join([marker]*3)+')',
              (item['id'],item['created_at'],json.dumps(item)))
    return public_draft(item,stable)


def public_draft(item, stable):
    baseline=item.get('baseline_code',stable['code'])
    return {**{k:v for k,v in item.items() if k!='baseline_code'},
            'baseline_is_current':item['baseline_sha256']==stable['source_sha256'],
            'diff':''.join(difflib.unified_diff(baseline.splitlines(True),item['code'].splitlines(True),
                                            fromfile='baseline.pine',tofile='draft.pine')),
            'required_before_release':['Pine compilation','rule parity review','licensed historical replay',
                                       'realistic costs and sessions','walk-forward and independent holdout','owner release decision']}


def drafts(c,stable):
    rows=c.execute('SELECT payload FROM strategy_drafts ORDER BY created_at DESC LIMIT 20').fetchall()
    return {'drafts':[public_draft(json.loads(r[0]),stable) for r in rows],
            'mode':'private_research_only','automatic_promotion':False}


def save_note(c,value,normalize,postgres=False):
    if not isinstance(value,dict) or set(value)-{'symbol','text','analysis_id'}:raise ValueError('note_fields')
    symbol=normalize(value.get('symbol'))
    text=value.get('text')
    analysis_id=value.get('analysis_id','')
    if not isinstance(text,str) or not 1<=len(text.strip())<=4000:raise ValueError('note_text')
    if not isinstance(analysis_id,str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{0,128}',analysis_id):raise ValueError('analysis_id')
    item={'id':uuid.uuid4().hex,'symbol':symbol,'text':text.strip(),'analysis_id':analysis_id,
          'created_at':datetime.now(timezone.utc).isoformat()}
    marker='%s' if postgres else '?'
    c.execute('INSERT INTO analysis_notes(id,symbol,created_at,payload) VALUES ('+','.join([marker]*4)+')',
              (item['id'],symbol,item['created_at'],json.dumps(item)))
    return item


def notes(c,symbol=None,postgres=False):
    if symbol:
        rows=c.execute('SELECT payload FROM analysis_notes WHERE symbol='+('%s' if postgres else '?')+' ORDER BY created_at DESC LIMIT 50',(symbol,)).fetchall()
    else:rows=c.execute('SELECT payload FROM analysis_notes ORDER BY created_at DESC LIMIT 50').fetchall()
    return {'notes':[json.loads(r[0]) for r in rows]}
