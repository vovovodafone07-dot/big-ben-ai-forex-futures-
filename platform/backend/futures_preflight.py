"""Contract-aware NQ Scalp preflight (read-only, no unlicensed futures quotes).

This module never maps NAS100 CFD to NQ futures, never assumes a TradingView
continuous series is a tradeable expiry, and never fabricates Entry/SL/TP.
"""
import re
from datetime import datetime, timezone

NQ = {"root": "NQ", "exchange": "CME", "asset_class": "futures",
      "instrument_name": "E-mini Nasdaq-100 Futures",
      "tick_size": 0.25, "tick_value_usd": 5.0, "point_value_usd": 20.0,
      "expected_ohlc_interval": "5min", "mode": "scalp",
      "expected_symbol": "CME_MINI:NQ1!"}
_EXPLICIT = re.compile(r"^CME_MINI:NQ[HMUZ][0-9]{2}$")

def resolve(symbol):
    if not isinstance(symbol,str):raise ValueError("unsupported_nq_instrument")
    symbol=symbol.strip().upper()
    if symbol in ("NQ","NQ1!","CME_MINI:NQ1!"):
        return NQ["expected_symbol"],"continuous_reference",None
    if _EXPLICIT.fullmatch(symbol):
        return symbol,"expiry_specific",symbol.split(":",1)[1]
    raise ValueError("unsupported_nq_instrument")

def inspect(symbol, *, barchart_key_configured=False, mapped_provider_symbol=None,
            verified_license=False, verified_contract=None, provider=None,
            latest_closed_m5=None, now=None):
    """Diagnostic only. A verified data pipeline can supply its attestations later.

    No OHLC prices are read here. License + contract identity + fresh validated M5
    are all mandatory, and a continuous reference alone cannot be trade-ready.
    """
    normalized,kind,contract=resolve(symbol)
    now=now or datetime.now(timezone.utc)
    issues=[]
    if kind!="expiry_specific":
        issues.append("explicit_expiry_contract_required")
    if not barchart_key_configured:issues.append("barchart_credentials_not_configured")
    if not mapped_provider_symbol:issues.append("provider_contract_mapping_not_confirmed")
    if not verified_license:issues.append("futures_ohlc_entitlement_not_verified")
    if provider!="Barchart OnDemand":issues.append("ohlc_provider_not_verified")
    if not contract or verified_contract!=contract:issues.append("contract_identity_not_verified")
    age=None
    if isinstance(latest_closed_m5,datetime) and latest_closed_m5.tzinfo is not None:
        age=(now-latest_closed_m5.astimezone(timezone.utc)).total_seconds()
    if age is None or age<300 or age>900:
        issues.append("fresh_closed_m5_not_verified")
    return {
        "symbol":normalized,"requested_mode":"scalp","asset_class":"futures",
        "instrument":dict(NQ),"contract_kind":kind,
        "expiration_contract":contract,"expected_provider":"Barchart OnDemand",
        "candidate_provider_symbol":mapped_provider_symbol if kind=="expiry_specific" else None,
        "provider_configured":bool(barchart_key_configured),
        "license_verified":bool(verified_license),
        "closed_m5_time":latest_closed_m5.isoformat() if isinstance(latest_closed_m5,datetime) else None,
        "closed_m5_age_seconds":int(age) if age is not None else None,
        "verified_source_ready":not issues,
        "analysis_status":"SOURCE_VERIFIED_NEEDS_SCALP_ENGINE" if not issues else "DATA_UNAVAILABLE",
        "decision":"NO_TRADE_DATA" if issues else "RESEARCH_PENDING",
        "issues":issues,"entry":None,"sl":None,"tp":None,"targets":[],
        "technical_bias":None,"confirmation":None,
        "news_state":"NOT_EVALUATED",
        "message":"NQ Scalp requires the exact CME expiry, matching licensed OHLC and recent closed M5 candles. NAS100 CFD and TradingView alerts are not NQ futures market data.",
        "broker_execution":False,"uses_tradingview_signals":False
    }
