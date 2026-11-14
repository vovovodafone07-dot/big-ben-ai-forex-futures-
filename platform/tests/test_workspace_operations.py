import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'backend'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


workspace=load('workspace');operations=load('operations');instruments=load('instruments')


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');workspace.migrate(self.c)
        self.stable={'code':'//@version=6\nindicator("baseline")\n','source_sha256':'a'*64,'version':'v6.4.3'}

    def tearDown(self):self.c.close()

    def test_draft_records_immutable_baseline_and_never_executes_or_promotes(self):
        item=workspace.create_draft(self.c,{'title':'candidate','rationale':'Investigate controlled hypothesis','code':'//@version=6\nindicator("candidate")\n'},self.stable)
        self.assertEqual(item['state'],'DRAFT');self.assertFalse(item['promotion_allowed'])
        self.assertIn('-indicator("baseline")',item['diff'])
        next_source={**self.stable,'code':'//@version=6\nindicator("different baseline")\n','source_sha256':'b'*64}
        saved=workspace.drafts(self.c,next_source)['drafts'][0]
        self.assertFalse(saved['baseline_is_current']);self.assertIn('-indicator("baseline")',saved['diff'])
        self.assertNotIn('different baseline',saved['diff']);self.assertEqual(saved['code'],item['code'])

    def test_invalid_or_oversized_draft_and_forged_approval_rejected(self):
        good={'title':'draft','rationale':'Research only reason','code':'//@version=6\nindicator("test")'}
        for data in ({**good,'state':'APPROVED'},{**good,'code':'print("execute")'}, {**good,'code':'x'*100001}):
            with self.assertRaises(ValueError):workspace.create_draft(self.c,data,self.stable)
        self.assertEqual(workspace.drafts(self.c,self.stable)['drafts'],[])

    def test_notes_are_symbol_scoped_and_preserve_plain_text(self):
        workspace.save_note(self.c,{'symbol':'EURUSD','text':'<script>research note</script>'},instruments.normalize)
        workspace.save_note(self.c,{'symbol':'MES','text':'Different market'},instruments.normalize)
        notes=workspace.notes(self.c,'OANDA:EURUSD')['notes']
        self.assertEqual(len(notes),1);self.assertEqual(notes[0]['text'],'<script>research note</script>')
        with self.assertRaises(ValueError):workspace.save_note(self.c,{'symbol':'EURUSD','text':'x','analysis_id':'../../secret'},instruments.normalize)


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');operations.migrate(self.c)
        self.now=datetime(2026,11,14,10,tzinfo=timezone.utc)

    def tearDown(self):self.c.close()

    def test_lease_prevents_overlap_and_interrupted_run_is_never_success(self):
        token=operations.claim(self.c,'research',self.now)
        self.assertIsNone(operations.claim(self.c,'research',self.now+timedelta(minutes=1)))
        resumed=operations.claim(self.c,'research',self.now+timedelta(minutes=21))
        self.assertNotEqual(token,resumed)
        runs=operations.snapshot(self.c)['runs']
        self.assertEqual(next(r for r in runs if r['id']==token)['status'],'INTERRUPTED')
        operations.finish(self.c,resumed,[{'name':'history','status':'FAILED','reason':'sanitized'}],self.now+timedelta(minutes=22))
        self.assertEqual(operations.snapshot(self.c)['runs'][0]['status'],'FAILED')

    def test_daily_report_is_idempotent_and_provider_acceptance_is_separate(self):
        evidence={'coverage':{'symbols':[{'state':'DEGRADED'}]},'research':{'runs':[]},'replay':{'runs':[]},'cycle_status':'FAILED'}
        report=operations.save_daily(self.c,evidence,self.now)
        self.assertIn('0 / 1',report['arabic_report']);self.assertFalse(report['automatic_promotion'])
        self.assertIsNone(operations.save_daily(self.c,evidence,self.now))
        operations.notification_result(self.c,report,'failed')
        result=operations.snapshot(self.c)
        self.assertEqual(len(result['daily_reports']),1)
        self.assertEqual(result['daily_reports'][0]['notification_status'],'failed')
        self.assertFalse(result['next_run_guaranteed'])


if __name__=='__main__':unittest.main()
