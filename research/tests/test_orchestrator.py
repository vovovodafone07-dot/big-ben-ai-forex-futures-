"""Offline deterministic orchestration fixtures; not measured strategy returns."""
import importlib.util
import json
import sqlite3
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("orchestrator",Path(__file__).resolve().parents[1]/"orchestrator.py")
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
NOW=datetime(2026,11,13,18,tzinfo=timezone.utc)
STRATEGY={"version":"fixture","source_sha256":"a"*64}

def candles():
    result=[]
    for i in range(1000):
        price=100+(i%50)*.1
        result.append({"time":(NOW-timedelta(minutes=(1000-i)*5)).isoformat(),
            "open":price,"high":price+.2,"low":price-.1,"close":price+.1})
    return result

class OrchestrationTests(unittest.TestCase):
    def test_nine_roles_have_task_contract_and_no_promotion(self):
        report=runner.run("EUR/USD",candles(),STRATEGY,NOW)
        self.assertEqual(set(t["role"] for t in report["tasks"]),set(runner.ROLES))
        self.assertEqual(len(report["tasks"]),9)
        self.assertTrue(all(t["status"]=="COMPLETED" for t in report["tasks"]))
        for t in report["tasks"]:
            for key in ("task_id","input","output","status","logs","started_at","completed_at","error","artifacts"):self.assertIn(key,t)
        self.assertFalse(report["promotion_allowed"])
        self.assertIn("not_pine",report["engine"])

    def test_final_holdout_does_not_change_parameter_selection(self):
        rows=candles();a=runner.run("EUR/USD",rows,STRATEGY,NOW)
        for row in rows[800:]:
            for k in ("open","high","low","close"):row[k]*=2
        b=runner.run("EUR/USD",rows,STRATEGY,NOW)
        def output(r,role):return next(t["output"] for t in r["tasks"] if t["role"]==role)
        self.assertEqual(output(a,"optimization"),output(b,"optimization"))
        self.assertEqual(output(a,"independent_validation")["holdout_range"],[800,1000])
        self.assertNotEqual(a["dataset_sha256"],b["dataset_sha256"])

    def test_data_and_execution_budgets_enforced(self):
        for rows in (candles()[:100],candles()+candles()[:1],list(reversed(candles()))):
            with self.assertRaises(ValueError):runner.run("EUR/USD",rows,STRATEGY,NOW)

    def test_failed_tasks_are_sanitized_and_coordinator_still_runs(self):
        with patch.object(runner.engine,"agent_quality",side_effect=ValueError("private-secret")):
            report=runner.run("EUR/USD",candles(),STRATEGY,NOW)
        self.assertEqual(report["status"],"partial_failure")
        self.assertNotIn("private-secret",json.dumps(report))
        self.assertEqual(report["tasks"][-1]["status"],"COMPLETED")
        self.assertGreater(report["tasks"][-1]["output"]["failed_tasks"],0)

    def test_provenance_and_idempotent_persistence(self):
        a=runner.run("EUR/USD",candles(),STRATEGY,NOW)
        b=runner.run("EUR/USD",candles(),STRATEGY,NOW)
        self.assertEqual(a["run_id"],b["run_id"])
        with sqlite3.connect(":memory:") as c:
            runner.migrate(c);runner.migrate(c)
            self.assertTrue(runner.save(c,a));self.assertFalse(runner.save(c,b))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0],9)
            result=runner.latest(c)
            self.assertEqual(result["count"],1)
            self.assertEqual(result["runs"][0]["dataset_sha256"],a["dataset_sha256"])

if __name__=="__main__":unittest.main()
