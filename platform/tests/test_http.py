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
            "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""
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

    def test_analysis_api_is_private_and_uses_stored_heartbeat(self):
        self.assertEqual(self.request("GET", "/api/analysis")[0], 401)
        self.request("POST", "/v1/tradingview/events", self.payload())
        status, result = self.request("GET", "/api/analysis", auth=self.auth)
        self.assertEqual(status, 200)
        self.assertEqual(result["count"], 1)
        self.assertIsNone(result["symbols"][0]["new_signal"])

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
