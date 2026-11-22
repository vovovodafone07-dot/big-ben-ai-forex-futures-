"""Authenticated webhook storage and additive discovery use one transaction."""
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

SPEC = importlib.util.spec_from_file_location('discovery_app', Path(__file__).resolve().parents[1] / 'backend' / 'app.py')
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)

class DiscoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'DATABASE_URL': ''})
        self.env.start()
        self.db_patch = patch.object(app, 'DB', Path(self.temp.name) / 'test.sqlite3')
        self.db_patch.start()
        app.init()

    def tearDown(self):
        self.db_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def event(self, symbol='CME_MINI:NQZ26', ident='test.discovery.1'):
        return {'schema': 'bigben.v1', 'event_id': ident, 'symbol': symbol,
                'event': 'HEARTBEAT', 'time': datetime.now(timezone.utc).isoformat(), 'close': 100}

    def test_retry_discovers_once_and_does_not_enable_feed(self):
        event = self.event()
        self.assertFalse(app.save_event(event))
        self.assertTrue(app.save_event(event))
        with app.history_connection() as db:
            records = app._tradingview_dynamic_sync.discovered(db)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['event_count'], 1)
        self.assertEqual(records[0]['asset_class'], 'futures')
        self.assertFalse(records[0]['feed_verified'])
        self.assertFalse(records[0]['enabled'])

    def test_cfd_stays_distinct_and_legacy_identifier_is_preserved(self):
        app.save_event(self.event('CAPITALCOM:NAS100'))
        app.save_event(self.event('legacy-market', 'test.discovery.legacy'))
        with app.history_connection() as db:
            records = app._tradingview_dynamic_sync.discovered(db)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 2)
        self.assertEqual(records[0]['asset_class'], 'cfd')

    def test_discovery_failure_rolls_back_event_for_safe_retry(self):
        with patch.object(app._tradingview_dynamic_sync, 'record_symbol', side_effect=RuntimeError('storage')):
            with self.assertRaises(RuntimeError): app.save_event(self.event())
        with app.history_connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
        self.assertFalse(app.save_event(self.event()))

if __name__ == '__main__': unittest.main()
