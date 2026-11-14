"""Verify an exported snapshot, optionally restore to a NEW local SQLite file."""
import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bigben_backup',root/'platform/backend/backup.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('snapshot',type=Path)
parser.add_argument('--new-sqlite',type=Path,help='Must not exist. Does not connect to production.')
args=parser.parse_args()
if args.snapshot.stat().st_size>backup.MAX_BYTES:raise SystemExit('Snapshot exceeds32MiB')
bundle=json.loads(args.snapshot.read_text(encoding='utf-8'))
rows=backup.verify(bundle)
if args.new_sqlite:
    destination=args.new_sqlite.resolve()
    if destination.exists():raise SystemExit('Refusing to overwrite an existing file')
    # Remove production selection in this process; never read or print secrets.
    os.environ.pop('DATABASE_URL',None)
    aspec=importlib.util.spec_from_file_location('restore_app',root/'platform/backend/app.py')
    app=importlib.util.module_from_spec(aspec);aspec.loader.exec_module(app)
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation protects against a concurrent file appearing.
    with destination.open('xb'):pass
    app.DB=destination;app.init()
    with closing(sqlite3.connect(destination)) as connection:
        with connection:backup.restore_new_database(connection,bundle)
    print('Verified and restored application rows:',rows)
else:print('Checksum verification passed. Application rows:',rows)
