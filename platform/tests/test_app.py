"""Run: python -m unittest discover -s platform/tests -v"""
import importlib.util, pathlib, unittest, datetime
spec=importlib.util.spec_from_file_location("bigben_backend",pathlib.Path(__file__).resolve().parents[1]/"backend"/"app.py")
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
class PayloadTests(unittest.TestCase):
 def payload(self):
  return {"schema":"bigben.v1","event":"BUY","event_id":"EURUSD-1234567890-BUY","symbol":"EURUSD","time":datetime.datetime.now(datetime.timezone.utc).isoformat(),"entry":1.1,"sl":1.09,"tp":1.13,"rr":3}
 def test_valid_buy(self):self.assertEqual(app.validate(self.payload())["event"],"BUY")
 def test_wrong_schema(self):
  p=self.payload();p["schema"]="other"
  with self.assertRaises(ValueError):app.validate(p)
 def test_wrong_rr(self):
  p=self.payload();p["rr"]=9
  with self.assertRaises(ValueError):app.validate(p)
 def test_wrong_direction(self):
  p=self.payload();p["sl"]=1.12
  with self.assertRaises(ValueError):app.validate(p)
 def test_stale_event(self):
  p=self.payload();p["time"]="2020-01-01T00:00:00Z"
  with self.assertRaises(ValueError):app.validate(p)
 def test_bad_symbol(self):
  p=self.payload();p["symbol"]="../../secret"
  with self.assertRaises(ValueError):app.validate(p)
 def test_invalid_number(self):
  p=self.payload();p["entry"]=float("nan")
  with self.assertRaises(ValueError):app.validate(p)
if __name__=="__main__":unittest.main()
