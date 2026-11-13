"""Exercise PostgreSQL additive migration on a disposable CI database only."""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"platform"/"backend"))
from migrations import migrate_events
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
    connection.rollback()
print("PostgreSQL migration preserves existing rows and is repeatable")
