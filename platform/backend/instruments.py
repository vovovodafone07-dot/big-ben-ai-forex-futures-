"""Multi-asset identifiers, independent of data subscription or alert coverage."""
import re
from urllib.parse import urlencode

CURRENCIES = ("EUR", "USD", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD")
FOREX = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
         "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD", "GBPJPY",
         "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD", "AUDJPY", "AUDCHF", "AUDCAD",
         "AUDNZD", "NZDJPY", "NZDCHF", "NZDCAD", "CADJPY", "CADCHF", "CHFJPY")
FUTURES = {
    "ES": ("CME_MINI", "E-mini S&P 500"), "MES": ("CME_MINI", "Micro E-mini S&P 500"),
    "NQ": ("CME_MINI", "E-mini Nasdaq-100"), "MNQ": ("CME_MINI", "Micro E-mini Nasdaq-100"),
    "YM": ("CBOT_MINI", "E-mini Dow Jones"), "MYM": ("CBOT_MINI", "Micro E-mini Dow Jones"),
    "RTY": ("CME_MINI", "E-mini Russell 2000"), "M2K": ("CME_MINI", "Micro E-mini Russell 2000"),
    "6E": ("CME", "Euro FX"), "6B": ("CME", "British Pound"), "6J": ("CME", "Japanese Yen"),
    "6A": ("CME", "Australian Dollar"), "6C": ("CME", "Canadian Dollar"), "6S": ("CME", "Swiss Franc"),
    "GC": ("COMEX", "Gold"), "MGC": ("COMEX_MINI", "Micro Gold"), "SI": ("COMEX", "Silver"),
    "HG": ("COMEX", "Copper"), "CL": ("NYMEX", "WTI Crude Oil"), "MCL": ("NYMEX", "Micro WTI Crude Oil"),
    "NG": ("NYMEX", "Natural Gas"), "ZB": ("CBOT", "US Treasury Bond"), "ZN": ("CBOT", "10-Year Treasury Note"),
    "ZF": ("CBOT", "5-Year Treasury Note"), "ZT": ("CBOT", "2-Year Treasury Note"),
    "ZC": ("CBOT", "Corn"), "ZW": ("CBOT", "Wheat"), "ZS": ("CBOT", "Soybeans"),
    "MBT": ("CME", "Micro Bitcoin Futures"),
}
SYMBOLS = {**{pair: "OANDA:"+pair for pair in FOREX},
           "XAUUSD": "FOREXCOM:XAUUSD", "XAGUSD": "OANDA:XAGUSD",
           **{root: exchange+":"+root+"1!" for root, (exchange, _) in FUTURES.items()},
           "BTCUSD":"BITSTAMP:BTCUSD", "ETHUSD":"BITSTAMP:ETHUSD", "XRPUSD":"BITSTAMP:XRPUSD",
           "SOLUSD":"BITSTAMP:SOLUSD", "LTCUSD":"BITSTAMP:LTCUSD", "ADAUSD":"BITSTAMP:ADAUSD",
           "DOGEUSD":"BITSTAMP:DOGEUSD", "BTCEUR":"BITSTAMP:BTCEUR", "ETHEUR":"BITSTAMP:ETHEUR", "US100":"CAPITALCOM:NAS100", "NAS100":"CAPITALCOM:NAS100",
           "US30":"SKILLING:US30", "US500":"CAPITALCOM:SPX500", "SPX500":"CAPITALCOM:SPX500", "USOIL":"TVC:USOIL"}

EXTRA_NAMES = {"BITSTAMP:BTCUSD":"Bitcoin / U.S. Dollar", "CAPITALCOM:NAS100":"US 100 Cash CFD",
               "SKILLING:US30":"Dow Jones Index CFD", "CAPITALCOM:SPX500":"S&P 500 Index CFD",
               "TVC:USOIL":"WTI Crude Oil CFD"}

# Research comparison candidates, not guaranteed or measured correlations.
PEERS = {
    "EURUSD":"GBPUSD", "GBPUSD":"EURUSD", "USDJPY":"USDCHF", "USDCHF":"USDJPY",
    "USDCAD":"USDCHF", "AUDUSD":"NZDUSD", "NZDUSD":"AUDUSD",
    "EURGBP":"EURCHF", "EURJPY":"GBPJPY", "GBPJPY":"EURJPY", "EURCHF":"GBPCHF", "GBPCHF":"EURCHF",
    "EURCAD":"GBPCAD", "GBPCAD":"EURCAD", "EURAUD":"GBPAUD", "GBPAUD":"EURAUD",
    "EURNZD":"GBPNZD", "GBPNZD":"EURNZD", "AUDJPY":"NZDJPY", "NZDJPY":"AUDJPY",
    "AUDCHF":"NZDCHF", "NZDCHF":"AUDCHF", "AUDCAD":"NZDCAD", "NZDCAD":"AUDCAD",
    "AUDNZD":"AUDUSD", "CADJPY":"USDJPY", "CADCHF":"USDCHF", "CHFJPY":"USDJPY",
    "XAUUSD":"XAGUSD", "XAGUSD":"XAUUSD", "ES":"NQ", "NQ":"ES", "MES":"MNQ", "MNQ":"MES",
    "YM":"ES", "MYM":"MES", "RTY":"ES", "M2K":"MES", "6E":"6B", "6B":"6E", "6A":"6C", "6C":"6A",
    "6J":"6S", "6S":"6J", "GC":"SI", "MGC":"SI", "SI":"GC", "HG":"SI", "CL":"MCL", "MCL":"CL",
    "ZB":"ZN", "ZN":"ZB", "ZF":"ZT", "ZT":"ZF", "ZC":"ZW", "ZW":"ZC", "ZS":"ZC",
}


def comparison(value):
    symbol = normalize(value)
    exchange, ticker = symbol.split(":", 1)
    peer = PEERS.get(ticker.removesuffix("1!"))
    if peer in FUTURES: candidate = SYMBOLS[peer]
    elif peer: candidate = exchange+":"+peer
    else: candidate = None
    same_underlying = ticker.removesuffix("1!") in {"CL", "MCL"}
    return {"candidate_symbol": candidate, "kind": "same_underlying_contract" if same_underlying else "research_candidate",
            "correlation_verified": False, "smt_confirmed": False,
            "requires": "synchronized source candles, matching session, and measured correlation; override when unsuitable"}


# Contract metadata only; these specs NEVER imply active market-data entitlement.
TICK_SPECS={"NQ":(.25,5.0),"MNQ":(.25,.5),"ES":(.25,12.5),
            "MES":(.25,1.25),"GC":(.1,10.0),"MGC":(.1,1.0),
            "CL":(.01,10.0),"MCL":(.01,1.0)}
MONTH_CODES="FGHJKMNQUVXZ"
def futures_contract(value):
    """Resolve explicit short root+month+two-digit-year; never guess expiries."""
    raw=str(value).upper().strip()
    match=re.fullmatch(r"(MNQ|MES|MGC|MCL|NQ|ES|GC|CL)(["+MONTH_CODES+r"])([0-9]{2})",raw)
    if not match:return None
    root,month,year=match.groups()
    exchange=FUTURES[root][0]
    return exchange+":"+root+month+year

def futures_tick(value):
    value=normalize(value)
    ticker=value.split(":",1)[1]
    root=next((x for x in sorted(TICK_SPECS,key=len,reverse=True) if ticker==x+"1!" or re.fullmatch(re.escape(x)+"["+MONTH_CODES+r"][0-9]{2}",ticker)),None)
    return {"price_tick":TICK_SPECS[root][0],"tick_value_usd":TICK_SPECS[root][1],
            "entitlement_verified":False,"provider_ohlc_verified":False} if root else None

def normalize(value):
    if not isinstance(value, str): raise ValueError("symbol")
    value = value.strip().upper().replace("/", "")
    contract=futures_contract(value)
    if contract:return contract
    if value in SYMBOLS: return SYMBOLS[value]
    if value.removesuffix("1!") in FUTURES: return SYMBOLS[value.removesuffix("1!")]
    # Accept additional valid TradingView exchange-qualified identifiers without
    # inventing their exchange, asset class, data access, or alert registration.
    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,19}:[A-Z0-9][A-Z0-9_.!-]{0,31}", value) and ".." not in value:
        return value
    # Additional currency crosses use the explicitly labelled OANDA default.
    if len(value) == 6 and value[:3] in CURRENCIES and value[3:] in CURRENCIES and value[:3] != value[3:]:
        return "OANDA:"+value
    raise ValueError("use_exchange_qualified_symbol")


def describe(value):
    symbol = normalize(value)
    exchange, ticker = symbol.split(":", 1)
    root = ticker.removesuffix("1!")
    if exchange in {"CME", "CME_MINI", "CBOT", "CBOT_MINI", "COMEX", "COMEX_MINI", "NYMEX", "ICEUS", "EUREX", "CME_DL", "NYMEX_DL", "COMEX_DL"}:
        kind = "futures"
        name = FUTURES[root][1] if root in FUTURES else ticker
    elif exchange in {"OANDA", "FX", "FXCM", "FOREXCOM", "SAXO", "PEPPERSTONE"} and re.fullmatch(r"[A-Z]{6}", ticker):
        kind = "metals" if ticker[:3] in {"XAU", "XAG"} else "forex"
        name = ticker[:3]+" / "+ticker[3:]
    elif exchange in {"CAPITALCOM", "SKILLING", "TVC"}:
        kind, name = "cfd", EXTRA_NAMES.get(symbol,ticker)
    elif exchange in {"BITSTAMP", "COINBASE", "BINANCE", "KRAKEN"}:
        kind, name = "crypto", EXTRA_NAMES.get(symbol,ticker)
    else:
        kind, name = "other", ticker
    return {"symbol": symbol, "ticker": ticker, "name": name, "asset_class": kind, "contract_specs": futures_tick(symbol) if kind=="futures" else None, "smt_comparison": comparison(symbol),
            "chart_url": "https://www.tradingview.com/chart/?"+urlencode({"symbol": symbol, "interval": "5"})}


def catalog(observed=(), custom=()):
    symbols = dict.fromkeys([*SYMBOLS.values(), *custom, *observed])
    result = []
    for symbol in symbols:
        try: result.append({**describe(symbol), "observed": symbol in observed})
        except ValueError: continue
    return result
