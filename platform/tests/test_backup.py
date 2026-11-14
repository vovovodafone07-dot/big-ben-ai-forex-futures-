import copy
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('backup_test_app',Path(__file__).resolve().parents[1]/'backend/app.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=app.DB
        self.env=patch.dict(os.environ,{'DATABASE_URL':''});self.env.start()
        app.DB=Path(self.temp.name)/'source.sqlite3';app.init()
        with app.history_connection() as c:
            app._workspace.save_note(c,{'symbol':'EURUSD','text':'ملاحظة أصلية'},app._desk.normalize)
            app._workspace.create_draft(c,{'title':'baseline','rationale':'Backup an unchanged research baseline','code':app.current_strategy_source()['code']},app.current_strategy_source())
        with app.history_connection() as c:self.bundle=app._backup.snapshot(c)

    def tearDown(self):
        app.DB=self.old;self.env.stop();self.temp.cleanup()

    def test_export_restore_round_trip_preserves_notes_drafts_and_migrations(self):
        self.assertEqual(set(self.bundle['tables']),set(app._backup.TABLES))
        app.DB=Path(self.temp.name)/'restored.sqlite3';app.init()
        with app.history_connection() as c:count=app._backup.restore_new_database(c,self.bundle)
        self.assertEqual(count,self.bundle['row_count'])
        with app.history_connection() as c:
            self.assertEqual(app._workspace.notes(c)['notes'][0]['text'],'ملاحظة أصلية')
            self.assertEqual(app._workspace.drafts(c,app.current_strategy_source())['drafts'][0]['code'],app.current_strategy_source()['code'])
        with app.history_connection() as c:
            with self.assertRaisesRegex(ValueError,'target_not_empty'):app._backup.restore_new_database(c,self.bundle)

    def test_corruption_missing_tables_and_untrusted_identifier_are_rejected(self):
        changed=copy.deepcopy(self.bundle);changed['tables']['analysis_notes']['rows'][0][-1]='tampered'
        with self.assertRaisesRegex(ValueError,'checksum'):app._backup.verify(changed)
        changed=copy.deepcopy(self.bundle);changed['tables']['events; DROP TABLE events']=changed['tables'].pop('events')
        with self.assertRaisesRegex(ValueError,'tables'):app._backup.verify(changed)
        changed=copy.deepcopy(self.bundle);changed['complete']=False
        with self.assertRaisesRegex(ValueError,'schema'):app._backup.verify(changed)

    def test_size_limit_fails_instead_of_returning_partial_success(self):
        with patch.object(app._backup,'MAX_BYTES',100):
            with app.history_connection() as c:
                with self.assertRaisesRegex(ValueError,'too_large'):app._backup.snapshot(c)
        self.assertNotIn('job_leases',self.bundle['tables'])
        self.assertNotIn('DATABASE_URL',json.dumps(self.bundle))

    def test_offline_cli_restores_only_a_new_local_file(self):
        root=Path(__file__).resolve().parents[2]
        archive=Path(self.temp.name)/'fixture.json'
        archive.write_bytes(app._backup.canonical(self.bundle))
        target=Path(self.temp.name)/'cli-copy.sqlite3'
        command=[sys.executable,str(root/'scripts/restore_application_backup.py'),str(archive),'--new-sqlite',str(target)]
        result=subprocess.run(command,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        with closing(sqlite3.connect(target)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM analysis_notes').fetchone()[0],1)
        before=target.read_bytes()
        again=subprocess.run(command,capture_output=True,timeout=30)
        self.assertNotEqual(again.returncode,0);self.assertEqual(before,target.read_bytes())


if __name__=='__main__':unittest.main()
