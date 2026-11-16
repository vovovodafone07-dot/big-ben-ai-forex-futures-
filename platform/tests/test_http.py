"""Real local HTTP tests. Synthetic fixtures only; no external notifications."""
import base64
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("http_app", Path(__file__).resolve().parents[1] / "backend" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class WebhookHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = app.DB
        app.DB = Path(self.temp.name) / "events.sqlite3"
        self.environment = patch.dict(os.environ, {
            "DATABASE_URL": "", "BIGBEN_WEBHOOK_TOKEN": "t" * 40,
            "BIGBEN_DASHBOARD_PASSWORD": "p" * 24,
            "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "BIGBEN_SIGNAL_ANALYSIS_ENABLED":"0"
        })
        self.environment.start()
        self.notify = patch.object(app, "telegram_notify", return_value="not_configured")
        self.notify.start()
        app.init()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.auth = "Basic " + base64.b64encode(("bigben:" + "p" * 24).encode()).decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.notify.stop()
        self.environment.stop()
        app.DB = self.original_db
        self.temp.cleanup()

    def request(self, method, path, data=None, auth=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            headers = {"Content-Type": "application/json"}
            if auth is not None:
                headers["Authorization"] = auth
            conn.request(method, path, json.dumps(data) if data is not None else None, headers)
            response = conn.getresponse()
            body = response.read()
            return response.status, json.loads(body) if body else {}
        finally:
            conn.close()

    def payload(self, event="HEARTBEAT"):
        result = {"schema": "bigben.v1", "event": event, "symbol": "OANDA:EURUSD",
                  "event_id": "synthetic-http-" + event,
                  "time": datetime.now(timezone.utc).isoformat(), "token": "t" * 40}
        if event == "HEARTBEAT":
            result["close"] = 100
        elif event == "BUY":
            result.update(entry=100, sl=98, tp=106, rr=3)
        else:
            result.update(entry=100, sl=102, tp=94, rr=3)
        return result

    def test_desk_news_and_replay_are_private_and_wait_without_data(self):
        for endpoint in ('/api/news','/api/integrations','/api/research/pine-runs'):
            self.assertEqual(self.request('GET',endpoint)[0],401)
            self.assertEqual(self.request('GET',endpoint,auth=self.auth)[0],200)
        self.assertEqual(self.request('POST','/api/analyze',{'symbol':'EURUSD'})[0],401)
        status,result=self.request('POST','/api/analyze',{'symbol':'EURUSD','ai':False},auth=self.auth)
        self.assertEqual(status,200);self.assertEqual(result['decision'],'WAIT');self.assertIsNone(result['full_trade'])
        self.assertEqual(len(result['agent_tasks']),9);self.assertFalse(result['ai']['connection_verified'])
        self.assertEqual(self.request('POST','/api/analyze',{'symbol':'FAKE'},auth=self.auth)[0],400)

    def test_private_api_requires_authentication(self):
        self.assertEqual(self.request("GET", "/api/events")[0], 401)
        self.assertEqual(self.request("GET", "/api/events", auth=self.auth)[0], 200)

    def test_market_sessions_are_public_and_news_test_is_authenticated(self):
        status, session = self.request("GET", "/api/market/sessions")
        self.assertEqual(status, 200)
        self.assertIn(session["state"], ("OPEN", "CLOSED"))
        self.assertGreaterEqual(session["seconds_remaining"], 0)
        self.assertEqual(self.request("POST", "/api/news/test", {}, auth=None)[0], 401)
        with patch.object(app._news, "refresh") as refresh:
            status, result = self.request("POST", "/api/news/test", {}, auth=self.auth)
        self.assertEqual(status, 200)
        self.assertTrue(result["test_only"])
        refresh.assert_called_once()

    def test_tradingview_csv_export_is_private_and_uses_utf8_bom(self):
        self.assertEqual(self.request("GET", "/api/events.csv")[0], 401)
        self.assertEqual(self.request("POST", "/v1/tradingview/events", self.payload("HEARTBEAT"))[0], 202)
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            conn.request("GET", "/api/events.csv", headers={"Authorization": self.auth})
            response = conn.getresponse()
            body = response.read()
        finally:
            conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=\"bigben-tradingview-events.csv\"", response.getheader("Content-Disposition"))
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"event_id", body)
        self.assertIn(b"synthetic-http-HEARTBEAT", body)

    def test_walk_forward_snapshot_is_private_and_never_promotes(self):
        self.assertEqual(self.request('GET','/api/research/walk-forward')[0],401)
        status,report=self.request('GET','/api/research/walk-forward',auth=self.auth)
        self.assertEqual(status,200);self.assertFalse(report['automatic_refresh'])
        self.assertTrue(report['runs'])
        for run in report['runs']:
            self.assertFalse(run['promotion_allowed']);self.assertFalse(run['holdout']['selection_uses_holdout'])

    def test_walk_forward_report_fails_closed_when_source_changes(self):
        source=app.current_strategy_source()
        with patch.object(app,'current_strategy_source',return_value={**source,'source_sha256':'b'*64}):
            status,result=self.request('GET','/api/research/walk-forward',auth=self.auth)
        self.assertEqual(status,503);self.assertEqual(result,{'error':'walk_forward_report_unavailable'})

    def test_application_export_is_private_complete_and_cannot_restore_over_http(self):
        self.assertEqual(self.request('GET','/api/backup/export')[0],401)
        self.assertEqual(self.request('POST','/api/backup/restore',{},auth=self.auth)[0],404)
        status,bundle=self.request('GET','/api/backup/export',auth=self.auth)
        self.assertEqual(status,200);self.assertTrue(bundle['complete'])
        self.assertEqual(app._backup.verify(bundle),bundle['row_count'])
        with patch.object(app._backup,'MAX_BYTES',10):
            status,result=self.request('GET','/api/backup/export',auth=self.auth)
        self.assertEqual(status,413);self.assertNotIn('tables',result)
        self.assertEqual(self.request('GET','/api/backup/export',auth=self.auth)[0],200)

    def test_workspace_routes_are_private_and_drafts_and_notes_persist(self):
        for endpoint in ('/api/workspace/drafts','/api/workspace/notes','/api/operations'):
            self.assertEqual(self.request('GET',endpoint)[0],401)
            self.assertEqual(self.request('GET',endpoint,auth=self.auth)[0],200)
        draft={'title':'HTTP research candidate','rationale':'Review a controlled research hypothesis','code':'//@version=6\nindicator("draft")\n'}
        self.assertEqual(self.request('POST','/api/workspace/drafts',draft)[0],401)
        status,result=self.request('POST','/api/workspace/drafts',draft,auth=self.auth)
        self.assertEqual(status,201);self.assertFalse(result['promotion_allowed'])
        self.assertEqual(len(self.request('GET','/api/workspace/drafts',auth=self.auth)[1]['drafts']),1)
        self.assertEqual(self.request('POST','/api/workspace/notes',{'symbol':'EURUSD','text':'Review after market open'},auth=self.auth)[0],201)
        self.assertEqual(len(self.request('GET','/api/workspace/notes?symbol=EURUSD',auth=self.auth)[1]['notes']),1)
        self.assertEqual(self.request('GET','/api/workspace/notes?symbol=INVALID',auth=self.auth)[0],400)

    def test_history_cycle_records_partial_failure_and_daily_report_without_duplicate_delivery(self):
        with patch.object(app,'refresh_market_history',side_effect=RuntimeError('private credential')),patch.object(app,'run_daily_research'),patch.object(app,'run_pine_research'),patch.object(app,'send_telegram_message',return_value='sent') as send:
            self.assertEqual(app.run_history_cycle(),'FAILED')
            self.assertEqual(app.run_history_cycle(),'FAILED')
        self.assertEqual(send.call_count,1)
        status,result=self.request('GET','/api/operations',auth=self.auth)
        self.assertEqual(status,200);self.assertEqual(len(result['runs']),2)
        self.assertEqual(len(result['daily_reports']),1)
        self.assertNotIn('private credential',json.dumps(result))
        self.assertEqual(result['daily_reports'][0]['notification_status'],'sent')

    def test_history_coverage_is_private_and_never_guesses_contracts(self):
        self.assertEqual(self.request("GET", "/api/market/coverage")[0], 401)
        status, result = self.request("GET", "/api/market/coverage", auth=self.auth)
        self.assertEqual(status, 200)
        self.assertEqual(len(result["symbols"]), 9)
        self.assertFalse(result["futures_coverage_verified"])
        self.assertEqual(result["symbols"][3]["reason"], "licensed_contract_mapping_required")

    def test_research_runs_api_requires_auth_and_does_not_fabricate_results(self):
        self.assertEqual(self.request("GET", "/api/research/runs")[0],401)
        status,result=self.request("GET", "/api/research/runs",auth=self.auth)
        self.assertEqual(status,200)
        self.assertEqual(result["runs"],[])
        self.assertFalse(result["promotion_allowed"])

    def test_daily_research_consumes_history_once_and_never_calls_provider(self):
        now=datetime.now(timezone.utc)
        rows=[{"time":(now-timedelta(minutes=(120-i)*5)).isoformat(),"open":100.0,"high":101.0,"low":99.0,"close":100.5} for i in range(120)]
        with app.history_connection() as c:
            app._history.store_check(c,"EUR/USD",{"checked_at":now.isoformat()},rows)
        with patch.object(app._history,"fetch_m5") as provider:
            app.run_daily_research()
            app.run_daily_research()
        provider.assert_not_called()
        status,result=self.request("GET","/api/research/runs",auth=self.auth)
        self.assertEqual(status,200)
        self.assertEqual(result["count"],1)
        self.assertEqual(len(result["runs"][0]["tasks"]),9)
        self.assertEqual(app.list_events(),[])

    def test_history_refresh_is_bounded_and_restart_safe(self):
        with patch.object(app._history, "fetch_m5", side_effect=app._history.HistoryError("rate_limited")) as fetch:
            app.refresh_market_history()
            app.refresh_market_history()
        self.assertEqual(fetch.call_count, 3)
        with app.history_connection() as c:
            checks=app._history.coverage(c)["symbols"][:3]
        self.assertTrue(all(s["reason"]=="rate_limited" for s in checks))
        self.assertEqual(app.list_events(), [])

    def test_scalp_api_is_private_and_paired(self):
        self.assertEqual(self.request("GET", "/api/scalping")[0], 401)
        self.request("POST", "/v1/tradingview/events", self.payload("BUY"))
        status, result = self.request("GET", "/api/scalping?rr=1", auth=self.auth)
        self.assertEqual(status, 200)
        self.assertEqual(result["signals"][0]["full_trade"]["tp"], 106)
        self.assertEqual(result["signals"][0]["scalp"]["tp"], 102)
        self.assertEqual(self.request("GET", "/api/scalping?rr=nan", auth=self.auth)[0], 400)

    def test_notification_contains_full_and_scalp_without_pine_edits(self):
        message=app.trade_notification_text(self.payload("BUY"))
        self.assertIn("106.0",message)
        self.assertIn("102.0",message)
        self.assertIn("الصفقة الكاملة",message)
        self.assertIn("خيار السكالب",message)
        self.assertIn("التحليل قد يفشل",message)
        self.assertIn("مسؤوليتك",message)

    def test_recipients_are_private_validated_and_persisted(self):
        values={'telegram_chat_id':'123456789','whatsapp_number':'+96891234567','watchlist':['GBPJPY','NYMEX:CL1!']}
        self.assertEqual(self.request('GET','/api/destinations')[0],401)
        self.assertEqual(self.request('POST','/api/destinations',values)[0],401)
        self.assertEqual(self.request('POST','/api/destinations',values,auth=self.auth)[0],200)
        status,result=self.request('GET','/api/destinations',auth=self.auth)
        self.assertEqual(status,200);self.assertEqual(result['whatsapp_number'],values['whatsapp_number'])
        self.assertFalse(result['whatsapp_automatic_connected']);self.assertEqual(result['watchlist'],['OANDA:GBPJPY','NYMEX:CL1!'])
        self.assertEqual(app.telegram_destination(),'123456789')
        for key,bad in [('telegram_chat_id','+96891234567'),('whatsapp_number','91234567'),('watchlist',['INVALID'])]:
            self.assertEqual(self.request('POST','/api/destinations',{**values,key:bad},auth=self.auth)[0],400)

    def test_catalog_expands_and_observed_symbols_are_discovered(self):
        self.assertEqual(self.request('GET','/api/instruments')[0],401)
        event=self.payload();event['symbol']='EUREX:FDAX1!'
        self.request('POST','/v1/tradingview/events',event)
        status,result=self.request('GET','/api/instruments',auth=self.auth)
        self.assertEqual(status,200);self.assertGreater(len(result['instruments']),50)
        instrument=next(i for i in result['instruments'] if i['symbol']=='EUREX:FDAX1!')
        self.assertTrue(instrument['observed']);self.assertEqual(instrument['asset_class'],'futures')

    def test_trade_stream_has_forex_names_and_formatted_share_text(self):
        self.request('POST','/v1/tradingview/events',self.payload('BUY'))
        status,result=self.request('GET','/api/events?type=trades',auth=self.auth)
        self.assertEqual(status,200)
        event=result['events'][0]
        self.assertEqual(event['instrument']['asset_class'],'forex')
        self.assertIn('EUR / USD',event['notification_text'])
        self.assertIn('TradingView'.lower(),event['notification_text'].lower())

    def test_signal_specialists_use_shared_analysis_and_persist_tasks(self):
        event=self.payload('BUY');event.pop('token');app.save_event(event)
        with patch.object(app._ai_provider,'review',return_value={'state':'NOT_CONFIGURED','connection_verified':False}) as model:
            app.run_signal_analysis(event['symbol'])
        self.assertEqual(model.call_count,1)
        self.assertEqual(self.request('GET','/api/analysis/runs')[0],401)
        status,result=self.request('GET','/api/analysis/runs',auth=self.auth)
        self.assertEqual(status,200);self.assertEqual(len(result['runs']),1)
        run=result['runs'][0]
        self.assertEqual(run['decision'],'BUY');self.assertEqual(len(run['agent_tasks']),9)
        self.assertTrue(all(task['task_id'] for task in run['agent_tasks']))

    def test_signal_specialists_are_bounded_without_retry_or_model_request(self):
        with patch.object(app,'SIGNAL_ANALYSIS_SLOTS') as slots,patch.object(app,'analyze_instrument') as analyze:
            slots.acquire.return_value=False
            app.run_signal_analysis('EURUSD')
            analyze.assert_not_called();slots.release.assert_not_called()

    def test_integration_status_reports_agent_activation_and_recent_delivery(self):
        with patch.dict(os.environ, {"BIGBEN_SIGNAL_ANALYSIS_ENABLED":"1","TELEGRAM_BOT_TOKEN":"configured","TELEGRAM_CHAT_ID":"123456789"}):
            with app.history_connection() as c:
                app._destinations.receipt(c,"event-1","telegram","sent")
            status=app.integration_status()
        self.assertTrue(status["agents"]["signal_analysis_enabled"])
        self.assertEqual(status["agents"]["deterministic_roles"],9)
        self.assertEqual(status["agents"]["mode"],"read_only")
        self.assertTrue(status["telegram"]["delivery_verified_now"])
        self.assertEqual(status["telegram"]["last_delivery"]["event_id"],"event-1")

    def test_analysis_api_is_private_and_uses_stored_heartbeat(self):
        self.assertEqual(self.request("GET", "/api/analysis")[0], 401)
        self.request("POST", "/v1/tradingview/events", self.payload())
        status, result = self.request("GET", "/api/analysis", auth=self.auth)
        self.assertEqual(status, 200)
        self.assertEqual(result["count"], 1)
        self.assertIsNone(result["symbols"][0]["new_signal"])

    def test_market_pulse_uses_closed_candles_without_creating_trade(self):
        now = datetime.now(timezone.utc)
        rows = []
        for i in range(60):
            stamp = now - timedelta(minutes=5 * (60 - i))
            close = 100 + i * 0.05
            rows.append((stamp.isoformat(), close - 0.02, close + 0.10, close - 0.10, close))
        with app.history_connection() as connection:
            result = app._market_pulses.analyze("EUR/USD", rows, now)
            app._market_pulses.save(connection, result)
        self.assertIn(result["state"], ("BULLISH", "MIXED", "STALE"))
        self.assertEqual(result["decision"], "MONITOR_LONG_SETUP" if result["state"] == "BULLISH" else "WAIT")
        self.assertIsNone(result["entry"])
        self.assertEqual(self.request("GET", "/api/market/pulses")[0], 401)
        status, payload = self.request("GET", "/api/market/pulses", auth=self.auth)
        self.assertEqual(status, 200)
        self.assertTrue(payload["pulses"])
        self.assertFalse(payload["trades_created"])
        self.assertEqual(app.list_events(), [])

    def test_pine_api_matches_synced_registry(self):
        self.assertEqual(self.request("GET", "/api/pine/current")[0], 401)
        status, result=self.request("GET", "/api/pine/current", auth=self.auth)
        self.assertEqual(status, 200)
        self.assertEqual(result["version"], "v6.4.1-sync")
        self.assertIn(result["pine_title"], result["code"])

    def test_pine_registry_mismatch_returns_503(self):
        with patch.object(app,"current_strategy_source",side_effect=ValueError("private path")):
            status, result=self.request("GET", "/api/pine/current", auth=self.auth)
        self.assertEqual(status,503)
        self.assertEqual(result,{"error":"source_unavailable_or_mismatched"})

    def test_new_pine_metadata_is_accepted(self):
        payload=self.payload("BUY")
        payload.update(strategy_version="v6.4.1-sync",timeframe="5",tick_size=.25)
        self.assertEqual(self.request("POST", "/v1/tradingview/events",payload)[0],202)

    def test_missing_token_rejected_and_not_persisted(self):
        payload = self.payload()
        payload.pop("token")
        self.assertEqual(self.request("POST", "/v1/tradingview/events", payload)[0], 401)
        self.assertEqual(app.list_events(), [])

    def test_unicode_token_returns_401_without_crashing(self):
        payload = self.payload()
        payload["token"] = "غير_صحيح"
        self.assertEqual(self.request("POST", "/v1/tradingview/events", payload)[0], 401)

    def test_buy_sell_are_accepted(self):
        for side in ("BUY", "SELL"):
            self.assertEqual(self.request("POST", "/v1/tradingview/events", self.payload(side))[0], 202)
        self.assertEqual(len(app.list_events(kind="trades")), 2)

    def test_duplicate_is_idempotent_and_original_receipt_preserved(self):
        payload = self.payload()
        self.assertEqual(self.request("POST", "/v1/tradingview/events", payload)[0], 202)
        first = app.list_events()[0][3]
        status, result = self.request("POST", "/v1/tradingview/events", payload)
        self.assertEqual(status, 200)
        self.assertTrue(result["duplicate"])
        self.assertEqual(len(app.list_events()), 1)
        self.assertEqual(first, app.list_events()[0][3])

    def test_receipt_time_is_server_generated_and_token_not_stored(self):
        payload = self.payload()
        payload["received_at"] = "untrusted"
        self.request("POST", "/v1/tradingview/events", payload)
        stored = json.loads(app.list_events()[0][3])
        self.assertNotIn("token", stored)
        self.assertNotEqual(stored["received_at"], "untrusted")
        self.assertEqual(stored["time"], payload["time"])
        self.assertIsNotNone(datetime.fromisoformat(stored["received_at"]).tzinfo)

    def test_heartbeat_is_excluded_from_trades_and_outcomes(self):
        self.request("POST", "/v1/tradingview/events", self.payload())
        status, result = self.request("GET", "/api/events?type=trades", auth=self.auth)
        self.assertEqual((status, result["count"]), (200, 0))
        self.assertEqual(app.evaluate_signals()["count"], 0)

    def test_invalid_levels_return_422(self):
        payload = self.payload("BUY")
        payload["sl"] = 101
        self.assertEqual(self.request("POST", "/v1/tradingview/events", payload)[0], 422)
        self.assertEqual(app.list_events(), [])

    def test_storage_failure_returns_503_without_details(self):
        with patch.object(app, "save_event", side_effect=RuntimeError("private connection detail")):
            status, result = self.request("POST", "/v1/tradingview/events", self.payload())
        self.assertEqual(status, 503)
        self.assertEqual(result, {"error": "storage_unavailable"})

class MigrationTests(unittest.TestCase):
    def test_existing_event_preserved_and_migration_repeatable(self):
        from contextlib import closing
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE TABLE events (id TEXT PRIMARY KEY,symbol TEXT,event TEXT,time TEXT,payload TEXT)")
            connection.execute("INSERT INTO events VALUES ('old','EURUSD','BUY','2020-01-01','{}')")
            app._migrations.migrate_events(connection)
            app._migrations.migrate_events(connection)
            self.assertEqual(connection.execute("SELECT id,received_at FROM events").fetchall(), [("old", None)])
            self.assertEqual(connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 1)

if __name__ == "__main__":
    unittest.main()
