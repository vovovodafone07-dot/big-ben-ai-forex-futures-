"""Bounded official RSS/calendar ingestion; no invented events or forecasts."""
import hashlib
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SOURCES={
    "fed":{"name":"Federal Reserve","url":"https://www.federalreserve.gov/feeds/press_all.xml","hosts":{"www.federalreserve.gov","federalreserve.gov"},"currency":"USD","kind":"rss"},
    "ecb":{"name":"ECB","url":"https://www.ecb.europa.eu/rss/press.html","hosts":{"www.ecb.europa.eu","ecb.europa.eu"},"currency":"EUR","kind":"rss"},
    "bls":{"name":"BLS Calendar","url":"https://www.bls.gov/schedule/news_release/bls.ics","hosts":{"www.bls.gov","bls.gov"},"currency":"USD","kind":"calendar"}}
MAX_BYTES=2_000_000
FEED_ADAPTER_VERSION=2

class FeedError(ValueError):pass

def clean(value,limit=180):
    return re.sub(r"\s+"," ",re.sub(r"<[^>]*>","",str(value or ""))).strip()[:limit]

def safe_link(link,source):
    parsed=urlsplit(str(link or ""))
    return str(link) if parsed.scheme=="https" and parsed.hostname in source["hosts"] and not parsed.username else None

def parse_rss(raw,source_id,now=None):
    source=SOURCES[source_id];now=now or datetime.now(timezone.utc)
    if len(raw)>MAX_BYTES or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():raise FeedError("unsafe_or_oversized_feed")
    try:root=ET.fromstring(raw)
    except (ET.ParseError,ValueError):raise FeedError("invalid_xml") from None
    items=[];seen=set()
    for item in root.findall("./channel/item")[:100]:
        title=clean(item.findtext("title"));link=safe_link(item.findtext("link"),source)
        if not title or not link or link in seen:continue
        try:
            stamp=parsedate_to_datetime(item.findtext("pubDate") or "")
            if stamp.tzinfo is None:continue
            stamp=stamp.astimezone(timezone.utc)
            if (stamp-now).total_seconds()>300:continue
        except (ValueError,TypeError,OverflowError):continue
        seen.add(link)
        items.append({"id":hashlib.sha256(link.encode()).hexdigest()[:24],"title":title,
            "url":link,"published_at":stamp.isoformat(),"source":source["name"],
            "currency":source["currency"],"kind":"official_release"})
    if not items:raise FeedError("no_valid_items")
    return sorted(items,key=lambda x:x["published_at"],reverse=True)[:12]

def parse_calendar(raw,now=None):
    now=now or datetime.now(timezone.utc)
    if len(raw)>MAX_BYTES:raise FeedError("oversized_calendar")
    try:text=raw.decode("utf-8-sig")
    except UnicodeDecodeError:raise FeedError("invalid_calendar_encoding") from None
    text=re.sub(r"\r?\n[ \t]","",text)
    if not text.strip().startswith("BEGIN:VCALENDAR") or "END:VCALENDAR" not in text:raise FeedError("invalid_calendar")
    events=[]
    for block in text.split("BEGIN:VEVENT")[1:501]:
        fields={}
        for line in block.split("END:VEVENT")[0].splitlines():
            if ":" in line:
                key,value=line.split(":",1);fields[key]=value
        start=next(((k,v) for k,v in fields.items() if k.startswith("DTSTART")),None)
        if not start or "SUMMARY" not in fields:continue
        key,value=start
        try:
            if value.endswith("Z"):stamp=datetime.strptime(value,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            elif "TZID=" in key:
                zone=key.split("TZID=",1)[1].strip('"')
                if zone=="US-Eastern":zone="America/New_York"  # BLS declares this TZID with US Eastern DST rules.
                if zone not in ("America/New_York","US/Eastern","UTC"):continue
                stamp=datetime.strptime(value,"%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
            else:continue  # Do not guess a timezone or time for all-day releases.
        except (ValueError,KeyError):continue
        if not 0<=(stamp-now).total_seconds()<=45*86400:continue
        title=clean(fields["SUMMARY"].replace("\\,",","))
        url=safe_link(fields.get("URL"),SOURCES["bls"]) or "https://www.bls.gov/schedule/news_release/"
        events.append({"id":hashlib.sha256((title+stamp.isoformat()).encode()).hexdigest()[:24],
            "title":title,"time":stamp.isoformat(),"source":"BLS Calendar","currency":"USD",
            "url":url,"consensus":None,"actual":None,"impact_verified":False})
    return sorted({e["id"]:e for e in events}.values(),key=lambda x:x["time"])[:30]

def fetch(source_id,now=None):
    source=SOURCES[source_id];now=now or datetime.now(timezone.utc)
    request=urllib.request.Request(source["url"],headers={"User-Agent":"BigBenAIPro-NewsReader/1.0","Accept":"application/rss+xml,text/xml,text/calendar"})
    try:
        with urllib.request.urlopen(request,timeout=8) as response:
            if urlsplit(response.geturl()).hostname not in source["hosts"]:raise FeedError("unexpected_redirect")
            raw=response.read(MAX_BYTES+1)
        items=parse_rss(raw,source_id,now) if source["kind"]=="rss" else parse_calendar(raw,now)
        return {"source":source["name"],"source_id":source_id,"state":"CONNECTED",
            "checked_at":now.isoformat(),"last_success_at":now.isoformat(),"items":items,
            "reason":"validated_feed","kind":source["kind"],"url":source["url"],"adapter_version":FEED_ADAPTER_VERSION}
    except FeedError:raise
    except urllib.error.HTTPError as error:
        raise FeedError({403:"source_access_denied",429:"source_rate_limited"}.get(error.code,"source_http_error")) from None
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):raise FeedError("source_connection_failure") from None

def migrate(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS external_feeds (source_id TEXT PRIMARY KEY,payload TEXT NOT NULL)")

def load(connection):
    import json
    return {key:json.loads(payload) for key,payload in connection.execute("SELECT source_id,payload FROM external_feeds").fetchall()}

def save(connection,source_id,result,postgres=False):
    import json
    marker="%s" if postgres else "?"
    connection.execute("INSERT INTO external_feeds(source_id,payload) VALUES ("+marker+","+marker+") ON CONFLICT(source_id) DO UPDATE SET payload=excluded.payload",(source_id,json.dumps(result)))

def refresh(connection_factory,postgres=False,now=None):
    now=now or datetime.now(timezone.utc)
    with connection_factory() as connection:previous=load(connection)
    for key,source in SOURCES.items():
        prior=previous.get(key,{})
        if prior.get("adapter_version")==FEED_ADAPTER_VERSION and prior.get("checked_at") and (now-datetime.fromisoformat(prior["checked_at"])).total_seconds()<3600:continue
        try:result=fetch(key,now)
        except FeedError as error:
            result={**prior,"source_id":key,"source":source["name"],"kind":source["kind"],
                "url":source["url"],"state":"DEGRADED","checked_at":now.isoformat(),
                "adapter_version":FEED_ADAPTER_VERSION,"reason":str(error),"items":prior.get("items",[]),"last_success_at":prior.get("last_success_at")}
        with connection_factory() as connection:save(connection,key,result,postgres)

def snapshot(connection,now=None):
    now=now or datetime.now(timezone.utc);stored=load(connection)
    sources=[];news=[];events=[]
    for key,definition in SOURCES.items():
        data=stored.get(key,{"source_id":key,"source":definition["name"],"kind":definition["kind"],"state":"UNKNOWN","reason":"not_checked","items":[]})
        success=data.get("last_success_at")
        fresh=bool(success and 0<=(now-datetime.fromisoformat(success)).total_seconds()<7200)
        sources.append({k:v for k,v in {**data,"fresh":fresh}.items() if k!="items"})
        for item in data.get("items",[]):
            if definition["kind"]=="rss":news.append({**item,"feed_fresh":fresh,"feed_state":data["state"]})
            elif datetime.fromisoformat(item["time"])>=now:events.append({**item,"feed_fresh":fresh,"feed_state":data["state"]})
    return {"generated_at":now.isoformat(),"sources":sources,
        "news":sorted(news,key=lambda x:x["published_at"],reverse=True)[:20],
        "calendar":sorted(events,key=lambda x:x["time"]),"consensus_available":False,
        "forecast_policy":"Conditional scenarios only; future releases and consensus are not fabricated"}
