"""Nine bounded deterministic research roles. Never changes production strategy."""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def sibling(name):
    spec=importlib.util.spec_from_file_location("bigben_research_"+name, ROOT/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

engine=sibling("daily_agents")
quality=sibling("candle_quality")
ENGINE_SHA256=hashlib.sha256("".join((ROOT/name).read_text(encoding="utf-8") for name in ("daily_agents.py","candle_quality.py","orchestrator.py")).encode()).hexdigest()
ROLES=("market_data","signal_quality","backtesting","risk","optimization",
       "independent_validation","pine_engineering","devops_monitoring","coordinator")


def run(symbol, candles, strategy, now=None):
    now=now or datetime.now(timezone.utc)
    if len(candles)>1000:raise ValueError("research budget exceeded")
    rows,data_quality=quality.validate_candles(candles,now)
    if len(rows)<120:raise ValueError("at least 120 closed M5 candles required")
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    run_id=hashlib.sha256((symbol+now.date().isoformat()+digest+ENGINE_SHA256+strategy["source_sha256"]).encode()).hexdigest()
    report={"run_id":run_id,"symbol":symbol,"created_at":now.isoformat(),
        "dataset_sha256":digest,"engine_sha256":ENGINE_SHA256,
        "engine":"research_breakout_proxy_not_pine_v6_4", "source_provider":"Twelve Data",
        "strategy_version":strategy["version"],"pine_source_sha256":strategy["source_sha256"],
        "candles":len(rows),"start":rows[0]["time"],"end":rows[-1]["time"],
        "parameters":{"lookback":20,"rr":3,"hold_bars":48},"tasks":[],
        "promotion_allowed":False,"status":"research_only",
        "limitations":["Proxy does not reproduce the live Pine strategy or its RR 2.5 setting",
            "No spread, slippage, commission, rollover, session calendar or verified fills",
            "Ambiguous same-bar SL/TP is never counted as a win",
            "No automatic Pine edit, deployment, notification or broker order"]}
    outputs={}
    def task(role, work):
        started=datetime.now(timezone.utc).isoformat()
        item={"task_id":run_id+":"+role,"role":role,"input":{"dataset_sha256":digest,"symbol":symbol},
            "status":"RUNNING","started_at":started,"logs":["deterministic read-only task started"],
            "error":None,"artifacts":[]}
        try:
            output=work()
            item.update(status="COMPLETED",output=output,artifacts=["report.json#tasks/"+role])
            outputs[role]=output
        except Exception:
            # Do not persist raw provider errors or arbitrary exception strings.
            item.update(status="FAILED",output=None,error="task_execution_failed")
            report["status"]="partial_failure"
        item["completed_at"]=datetime.now(timezone.utc).isoformat()
        item["logs"].append("task finished: "+item["status"])
        report["tasks"].append(item)

    task("market_data", lambda:{**data_quality,"dataset_sha256":digest,"synthetic":False})
    task("backtesting", lambda:{"trades":engine.backtest(rows),"model":"proxy","exact_pine_parity":False})
    task("signal_quality", lambda:engine.agent_quality(outputs["backtesting"]["trades"]))
    task("risk", lambda:engine.agent_risk(outputs["backtesting"]["trades"]))
    # Select RR on the first 60%; validation and final holdout are disjoint.
    train_end=int(len(rows)*.6);validation_end=int(len(rows)*.8)
    def optimize():
        choices=[]
        for rr in (1.5,2.0,3.0,4.0):
            trades=engine.backtest(rows[:train_end],rr=rr)
            q=engine.agent_quality(trades)
            choices.append({"rr":rr,"quality":q,"conservative_r":q["tp"]*rr-q["sl"]-q["ambiguous"]})
        eligible=[c for c in choices if c["quality"]["resolved"]>=30]
        candidate=max(eligible,key=lambda c:c["conservative_r"]) if eligible else None
        rr=candidate["rr"] if candidate else 3.0
        return {"status":"candidate_for_validation" if candidate else "insufficient_training_trades",
            "training_end_exclusive":train_end,"candidates":choices,"selected_rr":rr,
            "validation":engine.agent_quality(engine.backtest(rows[train_end:validation_end],rr=rr)),
            "validation_range":[train_end,validation_end],"auto_deploy":False}
    task("optimization", optimize)
    def validate():
        rr=outputs["optimization"]["selected_rr"]
        q=engine.agent_quality(engine.backtest(rows[validation_end:],rr=rr))
        return {"decision":"REJECT_AUTOMATIC_DEPLOY","status":"descriptive_holdout_only",
            "holdout_range":[validation_end,len(rows)],"selected_rr":rr,"quality":q,
            "baseline":engine.agent_quality(engine.backtest(rows[validation_end:],rr=3)),
            "minimum_resolved":30,"sufficient_holdout":q["resolved"]>=30,
            "reasons":["Pine parity, execution costs, calendar and walk-forward not validated",
                "Single historical holdout cannot prove improved profitability"]}
    task("independent_validation",validate)
    task("pine_engineering",lambda:{"version":strategy["version"],"source_sha256":strategy["source_sha256"],
        "source_changed":False,"candidate_source_created":False,"promotion":"BLOCKED_VALIDATION"})
    task("devops_monitoring",lambda:{"last_candle":rows[-1]["time"],
        "last_candle_age_seconds":int((now-datetime.fromisoformat(rows[-1]["time"])).total_seconds()),
        "calendar_verified":False,"data_gaps":len(data_quality["gaps"]),"market_state":"UNKNOWN"})
    def coordinate():
        return {"completed_tasks":sum(t["status"]=="COMPLETED" for t in report["tasks"]),
            "failed_tasks":sum(t["status"]=="FAILED" for t in report["tasks"]),
            "decision":"RESEARCH_ONLY_NO_PROMOTION",
            "arabic_summary":"اكتمل فحص تاريخ M5 ومحاكاة اختراق بحثية مبسطة. النتائج ليست أداء المؤشر الحي؛ لا يسمح بتغيير الاستراتيجية أو التداول تلقائيًا."}
    task("coordinator",coordinate)
    return report


def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS research_runs (id TEXT PRIMARY KEY,symbol TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)")
    connection.execute("CREATE INDEX IF NOT EXISTS research_runs_created_idx ON research_runs(created_at)")
    connection.execute("CREATE TABLE IF NOT EXISTS agent_runs (task_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL)")


def save(connection, report, postgres=False):
    marker="%s" if postgres else "?"
    inserted=connection.execute("INSERT INTO research_runs(id,symbol,created_at,payload) VALUES ("+",".join([marker]*4)+") ON CONFLICT(id) DO NOTHING",
        (report["run_id"],report["symbol"],report["created_at"],json.dumps(report))).rowcount
    for task in report["tasks"]:
        connection.execute("INSERT INTO agent_runs(task_id,run_id,role,status,payload) VALUES ("+",".join([marker]*5)+") ON CONFLICT(task_id) DO NOTHING",
            (task["task_id"],report["run_id"],task["role"],task["status"],json.dumps(task)))
    return bool(inserted)


def latest(connection):
    rows=connection.execute("SELECT payload FROM research_runs ORDER BY created_at DESC LIMIT 3").fetchall()
    return {"runs":[json.loads(r[0]) for r in rows],"count":len(rows),"mode":"read_only_proxy_research",
        "promotion_allowed":False,"scheduler":"best_effort_while_server_active"}
