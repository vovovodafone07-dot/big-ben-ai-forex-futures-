"""Credential probe fixtures only; external APIs are never contacted."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
spec=importlib.util.spec_from_file_location("market_probe",Path(__file__).resolve().parents[1]/"backend"/"market_probe.py")
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
class ProbeTests(unittest.TestCase):
    def test_no_key_no_request(self):
        with patch.object(probe.urllib.request,"urlopen") as request:
            result=probe.probe_twelve_data("")
        request.assert_not_called()
        self.assertEqual(result["state"],"DISCONNECTED")
    def test_valid_response_has_narrow_scope(self):
        with patch.object(probe.urllib.request,"urlopen",return_value=io.BytesIO(b'{"price":"1.08"}')) as request:
            result=probe.probe_twelve_data("synthetic-secret")
        self.assertEqual(request.call_count,1)
        self.assertEqual(result["state"],"CONNECTED")
        self.assertFalse(result["realtime_verified"])
        self.assertFalse(result["futures_coverage_verified"])
        self.assertNotIn("synthetic-secret",json.dumps(result))
    def test_invalid_prices_do_not_connect(self):
        for value in ("NaN","inf",-1,0,True):
            with patch.object(probe.urllib.request,"urlopen",return_value=io.BytesIO(json.dumps({"price":value}).encode())):
                self.assertEqual(probe.probe_twelve_data("fixture")["state"],"UNKNOWN")
    def test_provider_error_is_sanitized(self):
        with patch.object(probe.urllib.request,"urlopen",return_value=io.BytesIO(b'{"code":401,"message":"synthetic-secret"}')):
            result=probe.probe_twelve_data("synthetic-secret")
        self.assertEqual(result["reason"],"authentication_failed")
        self.assertNotIn("synthetic-secret",json.dumps(result))
    def test_http_rate_limit_does_not_retry(self):
        with patch.object(probe.urllib.request,"urlopen",side_effect=HTTPError("private",429,"synthetic-secret",{},None)) as request:
            result=probe.probe_twelve_data("synthetic-secret")
        self.assertEqual(request.call_count,1)
        self.assertEqual(result["reason"],"rate_limited")
        self.assertNotIn("synthetic-secret",json.dumps(result))
    def test_connection_error_is_not_reported_as_market_closed(self):
        with patch.object(probe.urllib.request,"urlopen",side_effect=URLError("synthetic-secret")):
            result=probe.probe_twelve_data("synthetic-secret")
        self.assertEqual(result["state"],"UNKNOWN")
        self.assertNotIn("synthetic-secret",json.dumps(result))
if __name__=="__main__":unittest.main()
