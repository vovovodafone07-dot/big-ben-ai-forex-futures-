"""Exercise PostgreSQL additive migration on a disposable CI database only."""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform"/"backend"))
from migrations import migrate_events
from market_history import migrate as migrate_history, store_check, coverage
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
from orchestrator import migrate as migrate_research, save as save_research, latest as latest_research
import news, ai_provider, pine_replay, desk, workspace, operations, instruments
from datetime import datetime,timezone,timedelta
import psycopg

url=os.environ["BIGBEN_TEST_DATABASE_URL"]
parsed=urlsplit(url)
if parsed.hostname not in ("localhost","127.0.0.1") or parsed.path!="/bigben_ci":
    raise SystemExit("Refusing non-local or non-CI database")
with psycopg.connect(url) as connection:
    connection.execute("CREATE TEMP TABLE events (id TEXT PRIMARY KEY,symbol TEXT,event TEXT,time TEXT,payload TEXT)")
    connection.execute("INSERT INTO events VALUES ('old','EURUSD','BUY','2020-01-01','{}')")
    migrate_events(connection,postgres=True)
    migrate_events(connection,postgres=True)
    assert connection.execute("SELECT id,received_at FROM events").fetchall()==[("old",None)]
    assert connection.execute("SELECT version FROM schema_migrations").fetchall()==[("001_event_receipt",)]
    migrate_history(connection)
    migrate_history(connection)
    result={"symbol":"EUR/USD","state":"CONNECTED","reason":"validated_closed_m5_history","checked_at":"2026-11-13T18:00:00+00:00","last_candle":"2026-11-13T17:55:00+00:00"}
    rows=[{"time":"2026-11-13T17:55:00+00:00","open":1.1,"high":1.2,"low":1.0,"close":1.15}]
    assert store_check(connection,"EUR/USD",result,rows,postgres=True)["candles_inserted"]==1
    assert store_check(connection,"EUR/USD",result,rows,postgres=True)["candles_inserted"]==0
    assert coverage(connection,postgres=True)["symbols"][0]["stored_candles"]==1
    migrate_research(connection)
    migrate_research(connection)
    fixture={"run_id":"fixture","symbol":"EUR/USD","created_at":"2026-11-13T18:00:00+00:00","tasks":[{"task_id":"fixture:market_data","role":"market_data","status":"COMPLETED"}]}
    assert save_research(connection,fixture,postgres=True)
    assert not save_research(connection,fixture,postgres=True)
    assert latest_research(connection)["count"]==1
    assert connection.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]==1
    for module in (news,ai_provider,pine_replay,desk,workspace,operations):
        module.migrate(connection);module.migrate(connection)
    news.save(connection,'fed',{'source':'fixture','items':[]},postgres=True)
    assert news.load(connection)['fed']['source']=='fixture'
    replay_fixture={'run_id':'a'*64,'symbol':'EUR/USD','created_at':'2026-11-14T00:00:00+00:00','trades':[],'diagnostics':[]}
    assert pine_replay.save(connection,replay_fixture,postgres=True)
    assert not pine_replay.save(connection,replay_fixture,postgres=True)
    assert pine_replay.latest(connection)['count']==1
    stable={'code':'//@version=6\nindicator("baseline")','source_sha256':'b'*64,'version':'fixture'}
    candidate=workspace.create_draft(connection,{'title':'fixture','rationale':'Test durable candidate storage','code':'//@version=6\nindicator("candidate")'},stable,True)
    assert workspace.drafts(connection,stable)['drafts'][0]['id']==candidate['id']
    assert not candidate['promotion_allowed']
    workspace.save_note(connection,{'symbol':'EURUSD','text':'CI note'},instruments.normalize,True)
    assert len(workspace.notes(connection,'OANDA:EURUSD',True)['notes'])==1
    now=datetime.now(timezone.utc)
    token=operations.claim(connection,'ci_research',now,True)
    assert token and operations.claim(connection,'ci_research',now,True) is None
    assert operations.finish(connection,token,[{'name':'ci','status':'COMPLETED'}],now+timedelta(seconds=1),True)=='COMPLETED'
    report=operations.save_daily(connection,{'coverage':{'symbols':[]},'research':{'runs':[]},'replay':{'runs':[]}},now,True)
    assert report and operations.save_daily(connection,report['evidence'],now,True) is None
    assert len(operations.snapshot(connection)['daily_reports'])==1
    marker='%s'
    assert connection.execute('INSERT INTO ai_daily_budget(day,requests) VALUES (%s,1) ON CONFLICT(day) DO UPDATE SET requests=ai_daily_budget.requests+1 WHERE ai_daily_budget.requests<10 RETURNING requests',('2026-11-14',)).fetchone()[0]==1
    connection.rollback()
import tempfile
import app as backup_app
original_url=os.environ.get('DATABASE_URL')
try:
    os.environ['DATABASE_URL']=url
    backup_app.init()
    with backup_app.history_connection() as connection:
        backup_app._workspace.save_note(connection,{'symbol':'EURUSD','text':'PostgreSQL portable snapshot fixture'},instruments.normalize,True)
    with backup_app.history_connection() as connection:
        bundle=backup_app._backup.snapshot(connection,True)
    assert backup_app._backup.verify(bundle)==bundle['row_count']
    os.environ['DATABASE_URL']=''
    with tempfile.TemporaryDirectory() as temporary:
        backup_app.DB=Path(temporary)/'restored.sqlite3'
        backup_app.init()
        with backup_app.history_connection() as connection:
            backup_app._backup.restore_new_database(connection,bundle)
        with backup_app.history_connection() as connection:
            assert backup_app._workspace.notes(connection)['notes'][0]['text']=='PostgreSQL portable snapshot fixture'
finally:
    if original_url is None:os.environ.pop('DATABASE_URL',None)
    else:os.environ['DATABASE_URL']=original_url
print("PostgreSQL migrations and portable snapshot restore verified on isolated CI data")
