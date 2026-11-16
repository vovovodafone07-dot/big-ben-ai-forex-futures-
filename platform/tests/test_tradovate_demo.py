"""Local fixtures only; never contacts Tradovate or any production service."""
import importlib.util
import io
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

spec = importlib.util.spec_from_file_location("tradovate_demo_test", Path(__file__).resolve().parents[1] / "backend" / "tradovate_demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)
CREDS = {"TRADOVATE_DEMO_USERNAME": "fixture-user", "TRADOVATE_DEMO_PASSWORD": "fixture-password",
         "TRADOVATE_DEMO_CID": "17", "TRADOVATE_DEMO_SECRET": "fixture-secret"}
TOKEN = "fixture-private-token"


class Response(io.BytesIO):
    def __init__(self, payload, url):
        super().__init__(json.dumps(payload).encode())
        self.url = url

    def geturl(self):
        return self.url


def auth_response(**extra):
    return {"accessToken": TOKEN, "expirationTime": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(), **extra}


class DemoTests(unittest.TestCase):
    def responses(self, *lists, auth=None):
        return [Response(auth if auth is not None else auth_response(), demo.DEMO_BASE_URL + demo.AUTH_PATH)] + [Response(data, demo.DEMO_BASE_URL + path) for path, data in lists]

    def test_missing_credentials_make_no_request(self):
        with patch.dict(os.environ, {}, clear=True):
            client = demo.DemoReadOnlyClient()
            with patch.object(client._opener, "open") as request:
                result = client.verify()
            request.assert_not_called()
            self.assertFalse(result["connection_verified"])
            self.assertEqual(result["reason"], "credentials_missing")

    def test_all_other_base_urls_are_blocked(self):
        for url in ("https://live.tradovateapi.com/v1", "https://demo.tradovateapi.com/v1/", "http://demo.tradovateapi.com/v1", "https://demo.tradovateapi.com.evil/v1", "https://md.tradovateapi.com/v1"):
            with self.subTest(url=url), self.assertRaises(demo.DemoError):
                demo.DemoReadOnlyClient(url)

    def test_no_arbitrary_methods_or_order_operations(self):
        client = demo.DemoReadOnlyClient()
        with patch.object(client._opener, "open") as request:
            for method, path in (("POST", "/order/placeorder"), ("POST", "/order/cancelorder"), ("POST", "/account/list"), ("GET", "/auth/accesstokenrequest"), ("GET", "/account/list?secret=x"), ("GET", "https://live.tradovateapi.com/v1/account/list")):
                with self.subTest(path=path), self.assertRaises(demo.DemoError):
                    client._request(method, path, token=TOKEN)
            with self.assertRaises(demo.DemoError):
                client.read_list("/order/placeorder")
            request.assert_not_called()

    def test_demo_auth_then_account_list_are_sanitized(self):
        with patch.dict(os.environ, CREDS, clear=True):
            client = demo.DemoReadOnlyClient()
            with patch.object(client._opener, "open", side_effect=self.responses(("/account/list", [{"id": 42, "name": "private-account", "readonly": True}]))) as request:
                result = client.verify()
        self.assertTrue(result["connection_verified"])
        self.assertEqual(result["account_count"], 1)
        self.assertEqual(result["broker_execution"], "disabled")
        self.assertTrue(result["execution_kill_switch"])
        self.assertEqual(result["execution_allowlist"], [])
        self.assertFalse(result["market_data_entitlement_verified"])
        auth_req, account_req = [call.args[0] for call in request.call_args_list]
        self.assertEqual(auth_req.full_url, demo.DEMO_BASE_URL + demo.AUTH_PATH)
        self.assertEqual(auth_req.get_method(), "POST")
        body = json.loads(auth_req.data)
        self.assertEqual(body["cid"], 17)
        self.assertEqual(body["appId"], "BigBenAIPro")
        self.assertEqual(body["appVersion"], "1.0")
        self.assertEqual(account_req.get_method(), "GET")
        self.assertEqual(account_req.get_header("Authorization"), "Bearer " + TOKEN)
        self.assertNotIn("cid", result)
        for private in (CREDS["TRADOVATE_DEMO_USERNAME"], CREDS["TRADOVATE_DEMO_PASSWORD"], CREDS["TRADOVATE_DEMO_SECRET"], TOKEN, "private-account"):
            self.assertNotIn(private, json.dumps(result))

    def test_empty_accounts_do_not_prove_account_available(self):
        with patch.dict(os.environ, CREDS, clear=True):
            client = demo.DemoReadOnlyClient()
            with patch.object(client._opener, "open", side_effect=self.responses(("/account/list", []))):
                result = client.verify()
        self.assertTrue(result["connection_verified"])
        self.assertFalse(result["account_available"])

    def test_bad_cid_never_sends_auth(self):
        for cid in ("0", "-1", "abc", "1.5", "١", "9" * 30):
            with self.subTest(cid=cid), patch.dict(os.environ, {**CREDS, "TRADOVATE_DEMO_CID": cid}, clear=True):
                client = demo.DemoReadOnlyClient()
                with patch.object(client._opener, "open") as request:
                    result = client.verify()
                request.assert_not_called()
                self.assertEqual(result["reason"], "invalid_cid")

    def test_provider_errors_and_challenges_never_leak(self):
        for auth, reason in (({"errorText": "fixture-secret"}, "authentication_failed"), ({"p-ticket": "fixture-secret"}, "authentication_challenge_requires_user"), ({"accessToken": TOKEN}, "invalid_token_expiry")):
            with self.subTest(reason=reason), patch.dict(os.environ, CREDS, clear=True):
                client = demo.DemoReadOnlyClient()
                with patch.object(client._opener, "open", side_effect=self.responses(auth=auth)) as request:
                    result = client.verify()
                self.assertEqual(request.call_count, 1)
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("fixture-secret", json.dumps(result))
                self.assertNotIn(TOKEN, json.dumps(result))

    def test_http_network_errors_do_not_retry_or_leak(self):
        for error, reason in ((HTTPError("private", 401, "fixture-secret", {}, None), "authentication_failed"), (HTTPError("private", 403, "fixture-secret", {}, None), "permission_denied"), (HTTPError("private", 429, "fixture-secret", {}, None), "rate_limited"), (URLError("fixture-secret"), "connection_failed")):
            with self.subTest(reason=reason), patch.dict(os.environ, CREDS, clear=True):
                client = demo.DemoReadOnlyClient()
                with patch.object(client._opener, "open", side_effect=error) as request:
                    result = client.verify()
                self.assertEqual(request.call_count, 1)
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("fixture-secret", json.dumps(result))

    def test_redirects_are_blocked(self):
        with self.assertRaises(demo.DemoError):
            demo.NoRedirect().redirect_request(None, None, 302, "", {}, "https://live.tradovateapi.com/v1")
        with patch.dict(os.environ, CREDS, clear=True):
            client = demo.DemoReadOnlyClient()
            with patch.object(client._opener, "open", return_value=Response(auth_response(), "https://live.tradovateapi.com/v1")):
                self.assertEqual(client.verify()["reason"], "redirect_blocked")

    def test_oversized_and_invalid_response_are_blocked(self):
        with patch.dict(os.environ, CREDS, clear=True):
            client = demo.DemoReadOnlyClient()
            with patch.object(client._opener, "open", return_value=Response({"secret": "x" * demo.MAX_RESPONSE_BYTES}, demo.DEMO_BASE_URL + demo.AUTH_PATH)):
                self.assertEqual(client.verify()["reason"], "response_too_large")

    def test_reconciliation_reuses_token_and_only_reads(self):
        lists = [("/account/list", [{"id": 42}]), ("/position/list", []), ("/order/list", []), ("/fill/list", []), ("/cashBalance/list", [])]
        with patch.dict(os.environ, CREDS, clear=True):
            client = demo.DemoReadOnlyClient()
            with patch.object(client._opener, "open", side_effect=self.responses(*lists)) as request:
                result = client.reconciliation_snapshot()
        self.assertEqual(request.call_count, 6)
        self.assertEqual([call.args[0].get_method() for call in request.call_args_list], ["POST"] + ["GET"] * 5)
        self.assertFalse(result["atomic"])
        self.assertFalse(result["execution_authorized"])

    def test_import_and_configuration_never_connect(self):
        with patch.object(demo.urllib.request, "urlopen") as request, patch.dict(os.environ, CREDS, clear=True):
            status = demo.configuration_status()
        request.assert_not_called()
        self.assertTrue(status["credentials_configured"])
        self.assertFalse(status["connection_verified"])


if __name__ == "__main__":
    unittest.main()
