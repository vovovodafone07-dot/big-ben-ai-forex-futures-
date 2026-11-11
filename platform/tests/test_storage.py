"""Storage selection and SQLite persistence regression tests."""
import importlib.util, os, pathlib, tempfile, unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location("bb_storage",pathlib.Path(__file__).resolve().parents[1]/"backend"/"app.py")
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
class StorageTests(unittest.TestCase):
 def test_fallback(self):
  with patch.dict(os.environ,{"DATABASE_URL":""}):
   self.assertEqual(app.storage_kind(),"ephemeral")
 def test_postgres_selection(self):
  with patch.dict(os.environ,{"DATABASE_URL":"postgresql://example.invalid/db"}):
   self.assertEqual(app.storage_kind(),"postgres")
 def test_sqlite_idempotent(self):
  original=app.DB
  try:
   with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{"DATABASE_URL":""}):
    app.DB=pathlib.Path(d)/"events.db"
    item={"event_id":"EURUSD-1234567890-BUY","symbol":"EURUSD","event":"BUY","time":"2026-11-11T00:00:00Z","entry":1.1,"sl":1.09,"tp":1.13,"rr":3}
    self.assertFalse(app.save_event(item))
    self.assertTrue(app.save_event(item))
    self.assertEqual(len(app.list_events()),1)
  finally:
   app.DB=original
if __name__=="__main__":unittest.main()
