"""Bounded application-data snapshot, with checksums and offline-only restore."""
import hashlib
import json
from datetime import datetime, timezone

LEGACY_TABLES=('events','schema_migrations','market_candles','market_history_checks','external_feeds',
        'ai_daily_budget','ai_reviews','analysis_runs','notification_preferences',
        'notification_deliveries','job_runs','daily_reports','strategy_drafts',
        'analysis_notes','research_runs','agent_runs','pine_replay_runs')
V2_TABLES=LEGACY_TABLES+('native_telegram_alerts','native_trade_journal','native_market_open_state',
                     'tradingview_discovered_symbols','native_management_outbox')
TABLES=V2_TABLES+('telegram_bot_state','telegram_bot_receipts')
MAX_BYTES=32*1024*1024
MAX_ROWS=100000


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def snapshot(c,postgres=False):
    # The caller supplies a fresh connection; all reads share one snapshot.
    c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY' if postgres else 'BEGIN')
    tables={};total=0;size=0
    for name in TABLES:
        cursor=c.execute('SELECT * FROM '+name)
        columns=[d[0] for d in cursor.description]
        rows=[]
        while True:
            batch=cursor.fetchmany(250)
            if not batch:break
            for row in batch:
                value=list(row);total+=1;size+=len(canonical(value))
                if total>MAX_ROWS or size>MAX_BYTES:raise ValueError('snapshot_too_large')
                rows.append(value)
        data={'columns':columns,'rows':rows}
        tables[name]={**data,'sha256':hashlib.sha256(canonical(data)).hexdigest()}
    bundle={'schema':'bigben.application-backup.v3','created_at':datetime.now(timezone.utc).isoformat(),
            'tables':tables,'row_count':total,'complete':True,
            'excluded':['environment secrets','broker credentials','job leases','Render infrastructure and database roles'],
            'restore_scope':'application rows into a new local database; not a PostgreSQL infrastructure backup'}
    if len(canonical(bundle))>MAX_BYTES:raise ValueError('snapshot_too_large')
    return bundle


def verify(bundle):
    if not isinstance(bundle,dict) or bundle.get('schema') not in ('bigben.application-backup.v1','bigben.application-backup.v2','bigben.application-backup.v3') or bundle.get('complete') is not True:
        raise ValueError('backup_schema')
    tables=bundle.get('tables')
    expected=TABLES if bundle['schema'].endswith('.v3') else V2_TABLES if bundle['schema'].endswith('.v2') else LEGACY_TABLES
    if not isinstance(tables,dict) or set(tables)!=set(expected):raise ValueError('backup_tables')
    total=0
    for name,data in tables.items():
        if not isinstance(data,dict) or set(data)!={'columns','rows','sha256'}:raise ValueError('backup_table')
        columns=data['columns'];rows=data['rows']
        if not isinstance(columns,list) or not columns or any(not isinstance(k,str) for k in columns) or len(set(columns))!=len(columns):raise ValueError('backup_columns')
        if not isinstance(rows,list) or any(not isinstance(r,list) or len(r)!=len(columns) for r in rows):raise ValueError('backup_rows')
        if any(type(v) not in (str,int,float,bool,type(None)) for row in rows for v in row):raise ValueError('backup_value')
        total+=len(rows)
        if hashlib.sha256(canonical({'columns':columns,'rows':rows})).hexdigest()!=data['sha256']:raise ValueError('backup_checksum')
    if total!=bundle.get('row_count') or total>MAX_ROWS or len(canonical(bundle))>MAX_BYTES:raise ValueError('backup_size_or_count')
    return total


def restore_new_database(c,bundle):
    """Only used by the offline tool and tests; no HTTP restore endpoint exists."""
    verify(bundle)
    # Validate ALL destinations before writing any source row.
    for name in bundle['tables']:
        expected=[d[0] for d in c.execute('SELECT * FROM '+name+' LIMIT 0').description]
        if expected!=bundle['tables'][name]['columns']:raise ValueError('restore_schema_mismatch')
        count=c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
        # Fresh init records its migration version. Preserve and compare it.
        if count and name!='schema_migrations':raise ValueError('restore_target_not_empty')
        if name=='schema_migrations':
            existing={tuple(row) for row in c.execute('SELECT * FROM schema_migrations').fetchall()}
            source={tuple(row) for row in bundle['tables'][name]['rows']}
            if not existing.issubset(source):raise ValueError('restore_migrations')
    for name in bundle['tables']:
        rows=bundle['tables'][name]['rows']
        if not rows:continue
        count=len(bundle['tables'][name]['columns'])
        statement='INSERT '+('OR IGNORE ' if name=='schema_migrations' else '')+'INTO '+name+' VALUES ('+','.join(['?']*count)+')'
        c.executemany(statement,rows)
    return bundle['row_count']
