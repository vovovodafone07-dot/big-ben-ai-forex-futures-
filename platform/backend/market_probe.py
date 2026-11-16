"""One bounded server-side credential probe; never return credentials or raw errors."""
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

def probe_twelve_data(key):
    result={"provider":"Twelve Data","symbol_tested":"EUR/USD","diagnostic_only":True,
            "analysis_scope":"TradingView events accept all exchange-qualified supported symbols; this probe does not restrict live analysis",
            "state":"UNKNOWN",
            "checked_at":datetime.now(timezone.utc).isoformat(),
            "credentials_configured":bool(key),"request_budget":1,
            "realtime_verified":False,"futures_coverage_verified":False,
            "quote_timestamp_verified":False}
    if not key:
        return {**result,"state":"DISCONNECTED","reason":"not_configured"}
    query=urllib.parse.urlencode({"symbol":"EUR/USD","apikey":key})
    request=urllib.request.Request("https://api.twelvedata.com/price?"+query,
                                   headers={"User-Agent":"BigBenAIPro-ConnectionProbe/1.0"})
    try:
        with urllib.request.urlopen(request,timeout=8) as response:
            data=json.loads(response.read(16384))
        if not isinstance(data,dict) or "price" not in data:
            code=str(data.get("code","")) if isinstance(data,dict) else ""
            reason={"401":"authentication_failed","403":"entitlement_denied","429":"rate_limited"}.get(code,"provider_rejected")
            return {**result,"state":"DEGRADED","reason":reason}
        value=data["price"]
        if isinstance(value,bool):
            raise ValueError()
        price=float(value)
        if not math.isfinite(price) or price<=0:
            raise ValueError()
        # Successful /price response proves access for this symbol, not real-time entitlement.
        return {**result,"state":"CONNECTED","reason":"valid_price_response",
                "scope":"single EUR/USD diagnostic price request; not a continuous feed and not a live-analysis symbol restriction"}
    except urllib.error.HTTPError as error:
        reason={401:"authentication_failed",403:"entitlement_denied",429:"rate_limited"}.get(error.code,"provider_http_error")
        return {**result,"state":"DEGRADED","reason":reason}
    except (urllib.error.URLError,TimeoutError,ValueError,TypeError,OverflowError,OSError):
        return {**result,"state":"UNKNOWN","reason":"connection_or_response_failure"}
