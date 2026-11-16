"""Demo account verification only. No market-data or order-writing capability.

Run explicitly: python3 platform/backend/tradovate_demo.py --verify
Credentials are read from environment; no raw provider responses are printed.
"""
import argparse
import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEMO_BASE_URL = "https://demo.tradovateapi.com/v1"
AUTH_PATH = "/auth/accesstokenrequest"
READ_PATHS = frozenset(("/account/list", "/position/list", "/order/list", "/fill/list", "/cashBalance/list"))
SECRET_FIELDS = ("TRADOVATE_DEMO_USERNAME", "TRADOVATE_DEMO_PASSWORD", "TRADOVATE_DEMO_CID", "TRADOVATE_DEMO_SECRET")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class DemoError(Exception):
    """Contains only a controlled reason code, never provider text."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DemoError("redirect_blocked")


def configuration_status():
    missing = [key for key in SECRET_FIELDS if not os.getenv(key, "").strip()]
    return {
        "provider": "Tradovate", "environment": "demo", "mode": "verification_only",
        "credentials_configured": not missing, "missing_settings": missing,
        "connection_verified": False, "broker_execution": "disabled",
        "execution_kill_switch": True, "execution_allowlist": [],
        "market_data_entitlement_verified": False,
        "reason": "not_verified" if not missing else "credentials_missing",
    }


class DemoReadOnlyClient:
    def __init__(self, base_url=DEMO_BASE_URL, timeout=10):
        if base_url != DEMO_BASE_URL:
            raise DemoError("non_demo_url_blocked")
        if type(timeout) not in (int, float) or not 1 <= timeout <= 30:
            raise DemoError("invalid_timeout")
        self._base_url = base_url
        self._timeout = timeout
        self._opener = urllib.request.build_opener(NoRedirect())
        self._token = None
        self._expires = None
        self._lock = threading.Lock()

    def _request(self, method, path, payload=None, token=None):
        # Defense in depth: no arbitrary URL, method, redirect, or order route.
        if self._base_url != DEMO_BASE_URL:
            raise DemoError("non_demo_url_blocked")
        if not ((method == "POST" and path == AUTH_PATH and token is None)
                or (method == "GET" and path in READ_PATHS and payload is None and token)):
            raise DemoError("operation_blocked")
        headers = {"Accept": "application/json", "User-Agent": "BigBenAIPro/1.0"}
        if token:
            headers["Authorization"] = "Bearer " + token
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self._base_url + path, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                if response.geturl() != self._base_url + path:
                    raise DemoError("redirect_blocked")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise DemoError("response_too_large")
                result = json.loads(raw)
        except DemoError:
            raise
        except urllib.error.HTTPError as error:
            reason = {401: "authentication_failed", 403: "permission_denied", 429: "rate_limited"}.get(error.code, "provider_http_error")
            raise DemoError(reason) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise DemoError("connection_failed") from None
        except (ValueError, TypeError, UnicodeDecodeError):
            raise DemoError("invalid_provider_response") from None
        return result

    def _authenticate(self):
        if self._token and self._expires and datetime.now(timezone.utc) < self._expires:
            return self._token
        self._token = None
        self._expires = None
        values = {key: os.getenv(key, "") for key in SECRET_FIELDS}
        if not all(value.strip() for value in values.values()):
            raise DemoError("credentials_missing")
        cid = values["TRADOVATE_DEMO_CID"].strip()
        if not cid.isascii() or not cid.isdecimal() or len(cid) > 18 or int(cid) <= 0:
            raise DemoError("invalid_cid")
        result = self._request("POST", AUTH_PATH, {
            "name": values["TRADOVATE_DEMO_USERNAME"],
            "password": values["TRADOVATE_DEMO_PASSWORD"],
            "cid": int(cid), "sec": values["TRADOVATE_DEMO_SECRET"],
            "appId": "BigBenAIPro", "appVersion": "1.0",
        })
        if not isinstance(result, dict):
            raise DemoError("invalid_provider_response")
        if any(key in result for key in ("p-ticket", "p-time", "p-captcha")):
            raise DemoError("authentication_challenge_requires_user")
        if result.get("errorText"):
            raise DemoError("authentication_failed")
        token = result.get("accessToken")
        if not isinstance(token, str) or not token or any(ch in token for ch in "\r\n"):
            raise DemoError("authentication_failed")
        try:
            expiry = datetime.fromisoformat(str(result["expirationTime"]).replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError()
        except (ValueError, KeyError, TypeError, OverflowError):
            raise DemoError("invalid_token_expiry") from None
        self._token, self._expires = token, expiry
        return token

    def read_list(self, path):
        if path not in READ_PATHS:
            raise DemoError("operation_blocked")
        with self._lock:
            token = self._authenticate()
            try:
                result = self._request("GET", path, token=token)
            except DemoError as error:
                if str(error) == "authentication_failed":
                    self._token, self._expires = None, None
                raise
            if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
                raise DemoError("invalid_provider_response")
            return result

    def verify(self):
        """One token exchange + account/list. No retry and no auto-trading."""
        summary = configuration_status()
        summary["checked_at"] = datetime.now(timezone.utc).isoformat()
        try:
            accounts = self.read_list("/account/list")
            if any(type(row.get("id")) is not int or row["id"] <= 0 for row in accounts):
                raise DemoError("invalid_account_response")
            summary.update(connection_verified=True, account_count=len(accounts),
                           account_available=bool(accounts), reason="demo_account_list_verified" if accounts else "no_demo_accounts")
        except DemoError as error:
            summary.update(reason=str(error), account_available=False)
        return summary

    def reconciliation_snapshot(self):
        """Private in-memory read-only snapshot. Never CLI-print account data."""
        accounts = self.read_list("/account/list")
        if not accounts:
            raise DemoError("no_demo_accounts")
        return {
            "environment": "demo", "captured_at": datetime.now(timezone.utc).isoformat(),
            "accounts": accounts, "positions": self.read_list("/position/list"),
            "orders": self.read_list("/order/list"), "fills": self.read_list("/fill/list"),
            "cash_balances": self.read_list("/cashBalance/list"),
            "atomic": False, "execution_authorized": False,
        }


def main():
    parser = argparse.ArgumentParser(description="Verify Tradovate Demo account access without orders.")
    parser.add_argument("--verify", action="store_true", required=True)
    parser.parse_args()
    result = DemoReadOnlyClient().verify()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["connection_verified"] and result.get("account_available") else 1


if __name__ == "__main__":
    raise SystemExit(main())
