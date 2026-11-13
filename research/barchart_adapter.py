"""Barchart OnDemand research feed. Read-only; validates actual licensed symbol returns."""
import json,os,urllib.request,urllib.parse,urllib.error,datetime,math,re
from pathlib import Path
from candle_quality import validate_candles,DataQualityError

URL="https://ondemand.websol.barchart.com/getHistory.json"

class ProviderError(RuntimeError):
 pass

def validated_symbol(raw):
 if not isinstance(raw,str) or not re.fullmatch(r"[A-Za-z0-9^:!./_*\-]{2,60}",raw) or ".." in raw or raw[0] in "./-":raise ValueError("invalid symbol")
 return raw

def get_m5(symbol,api_key,days=30):
 symbol=validated_symbol(symbol)
 if not api_key:raise ProviderError("BARCHART_API_KEY missing; no live data access claimed")
 days=int(days)
 if not 1<=days<=90:raise ValueError("days must be 1..90")
 end=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=1)
 start=end-datetime.timedelta(days=days+1)
 request_body=urllib.parse.urlencode({"apikey":api_key,"symbol":symbol,"type":"minutes","interval":5,
      "startDate":start.strftime("%Y%m%d"),"endDate":end.strftime("%Y%m%d"),"maxRecords":30000,
      "order":"asc"}).encode()
 req=urllib.request.Request(URL,data=request_body,headers={"Content-Type":"application/x-www-form-urlencoded","User-Agent":"BigBen-Research/1.0"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=35) as response:
   payload=json.load(response)
 except (urllib.error.URLError,TimeoutError,ValueError) as e:
  raise ProviderError("Barchart API connection or response failure") from e
 if not isinstance(payload,dict):raise ProviderError("Barchart response not a JSON object")
 status=payload.get("status") or {}
 if str(status.get("code"))!="200":
  raise ProviderError("Barchart rejected request; verify symbol and entitlement in provider dashboard")
 items=payload.get("results") or []
 if not items:raise ProviderError("No historical 5m bars returned for "+symbol+"; check symbol, market license, or market session")
 if len(items)>=30000:raise ProviderError("Result at 30000-bar cap; shorten date range to avoid silent truncation")
 rows=[]
 for row in items:
  if not isinstance(row,dict):raise ProviderError("Invalid historical bar type")
  try:
   ts=datetime.datetime.fromisoformat(str(row["timestamp"]).replace("Z","+00:00"))
   if ts.tzinfo is None:raise ValueError("timestamp without timezone")
   t=ts.astimezone(datetime.timezone.utc).isoformat()
   values={k:float(row[k]) for k in ("open","high","low","close")}
   if not all(math.isfinite(x) and x>0 for x in values.values()):raise ValueError("invalid OHLC")
   if values["high"]<max(values["open"],values["close"],values["low"]):raise ValueError("invalid high")
   if values["low"]>min(values["open"],values["close"]):raise ValueError("invalid low")
   rows.append({"time":t,**values})
  except (ValueError,KeyError,TypeError,OverflowError) as error:
   raise ProviderError("Invalid historical bar") from error
 try:
  rows,quality=validate_candles(rows)
 except DataQualityError as error:
  raise ProviderError("Historical candle quality validation failed") from error
 if len(rows)<120:raise ProviderError("Insufficient valid M5 bars for "+symbol+" ("+str(len(rows))+")")
 if (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(rows[-1]["time"])).total_seconds()>4*86400:
  raise ProviderError("Historical data is stale for "+symbol+"; verify exchange session and source permissions")
 if any((datetime.datetime.fromisoformat(rows[i]["time"])-datetime.datetime.fromisoformat(rows[i-1]["time"])).total_seconds()<300 for i in range(1,len(rows))):
  raise ProviderError("Sub-5m or duplicate timestamps detected")
 return rows

def load_requested_symbols():
 """Explicit, provider-verified map; never translate TradingView futures prefixes by guess."""
 raw=os.getenv("BIGBEN_BARCHART_SYMBOL_MAP","").strip()
 if not raw:return {}
 try:m=json.loads(raw)
 except ValueError as e:raise ValueError("BIGBEN_BARCHART_SYMBOL_MAP must be JSON") from e
 if not isinstance(m,dict) or len(m)>25:raise ValueError("symbol map must be a dictionary <=25 entries")
 return {validated_symbol(k):validated_symbol(v) for k,v in m.items()}
