"""Synthetic fixtures for bounded news, evidence and optional AI. No live requests."""
import importlib.util,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from contextlib import contextmanager
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[1]/'backend'
def load(name):
 s=importlib.util.spec_from_file_location('test_desk_'+name,ROOT/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
news=load('news');desk=load('desk');ai=load('ai_provider')
NOW=datetime(2026,11,14,tzinfo=timezone.utc)
class NewsTests(unittest.TestCase):
 def test_official_rss_rejects_external_links_future_and_duplicates(self):
  raw=b'<rss><channel><item><title>&lt;b&gt;Policy&lt;/b&gt;</title><link>https://www.federalreserve.gov/newsevents/pressreleases/test.htm</link><pubDate>Fri, 13 Nov 2026 18:00:00 GMT</pubDate></item><item><title>Bad</title><link>https://evil.example/a</link><pubDate>Fri, 13 Nov 2026 18:00:00 GMT</pubDate></item></channel></rss>'
  result=news.parse_rss(raw,'fed',NOW);self.assertEqual(len(result),1);self.assertEqual(result[0]['title'],'Policy')
 def test_unsafe_xml_and_html_calendar_rejected(self):
  for raw in (b'<!DOCTYPE rss><rss/>',b'<broken>'):
   with self.assertRaises(news.FeedError):news.parse_rss(raw,'fed',NOW)
  with self.assertRaises(news.FeedError):news.parse_calendar(b'<html>Access denied</html>',NOW)
 def test_calendar_timezone_without_inventing_consensus(self):
  raw=b'''BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20261116T083000
SUMMARY:Release
END:VEVENT
END:VCALENDAR'''
  events=news.parse_calendar(raw,NOW);self.assertEqual(events[0]['time'],'2026-11-16T13:30:00+00:00');self.assertIsNone(events[0]['consensus']);self.assertFalse(events[0]['impact_verified'])
 def test_failed_refresh_preserves_items_and_cooldown(self):
  with tempfile.TemporaryDirectory() as t:
   @contextmanager
   def connection():
    c=sqlite3.connect(str(Path(t)/'db'));yield c;c.commit();c.close()
   with connection() as c:news.migrate(c)
   with patch.object(news,'fetch',side_effect=news.FeedError('source_access_denied')) as fetch:
    news.refresh(connection,now=NOW);news.refresh(connection,now=NOW+timedelta(minutes=1));self.assertEqual(fetch.call_count,3)
   with connection() as c:
    s=news.snapshot(c,NOW);self.assertEqual(len(s['sources']),3);self.assertEqual(s['news'],[]);self.assertTrue(all(x['state']=='DEGRADED' for x in s['sources']))
class DeskTests(unittest.TestCase):
 def row(self,event='BUY',age=0,checks=None):
  p={'event_id':'synthetic-'+event,'symbol':'OANDA:EURUSD','event':event,'time':(NOW-timedelta(seconds=age)).isoformat(),'entry':100,'sl':98,'tp':105,'rr':2.5,'close':100,'strategy_version':'fixture','timeframe':'5'}
  if checks is not None:p['analysis']={'checks':checks}
  return (p['symbol'],event,p['time'],json.dumps(p))
 def test_empty_and_heartbeat_never_manufacture_trade(self):
  for rows in ([],[self.row('HEARTBEAT')]):
   d=desk.analyze('EUR/USD',rows,{},NOW);self.assertEqual(d['decision'],'WAIT');self.assertIsNone(d['full_trade']);self.assertTrue(all(c['state']=='UNKNOWN' for c in d['checks']))
 def test_fresh_signal_has_both_targets_and_own_checks(self):
  d=desk.analyze('EURUSD',[self.row('HEARTBEAT',checks={'ready':False}),self.row(age=60,checks={'ready':True})],{},NOW)
  self.assertEqual(d['decision'],'BUY');self.assertEqual(d['full_trade']['tp'],105);self.assertEqual(d['scalp']['tp'],102);self.assertEqual(next(c for c in d['checks'] if c['key']=='ready')['state'],'PASSED')
 def test_failed_live_checks_explain_wait(self):
  d=desk.analyze('EURUSD',[self.row('HEARTBEAT',checks={'ready':False,'trigger_buy':False})],{},NOW)
  self.assertEqual(d['decision'],'WAIT');self.assertTrue(any('الكولداون' in r for r in d['reasons']))
 def test_stale_signal_waits(self):
  self.assertEqual(desk.analyze('EURUSD',[self.row(age=720)],{},NOW)['decision'],'WAIT')
 def test_disabled_filters_are_not_claimed_as_evidence(self):
  d=desk.condition_checks({'checks':{'ha_long':True,'volatility_ok':True},'filters':{'use_ha':False,'use_atr_floor':False}})
  self.assertEqual(next(c for c in d if c['key']=='ha_long')['state'],'DISABLED')
  self.assertEqual(next(c for c in d if c['key']=='trigger_buy')['state'],'UNKNOWN')
 def test_unknown_symbol_rejected(self):
  with self.assertRaises(ValueError):desk.normalize('FAKE')
  self.assertEqual(desk.normalize('MES1!'),'CME_MINI:MES1!')
class AITests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=str(Path(self.temp.name)/'ai.db')
  with self.connection() as c:ai.migrate(c)
  self.env=patch.dict(os.environ,{'GEMINI_API_KEY':'synthetic-key','BIGBEN_AI_ENABLED':'1','BIGBEN_AI_MODEL':'gemini-test'});self.env.start()
 def tearDown(self):self.env.stop();self.temp.cleanup()
 @contextmanager
 def connection(self):
  c=sqlite3.connect(self.db);yield c;c.commit();c.close()
 def evidence(self):return {'symbol':'OANDA:EURUSD','decision':'WAIT','checks':[],'news':[],'token':'must-not-be-sent'}
 def test_no_key_does_not_request(self):
  with patch.dict(os.environ,{'GEMINI_API_KEY':''}),patch.object(ai.urllib.request,'urlopen') as fetch:
   self.assertEqual(ai.review(self.evidence(),self.connection,now=NOW)['state'],'NOT_CONFIGURED');fetch.assert_not_called()
 def test_review_cache_ignores_model_decision_and_does_not_send_secret(self):
  output={'summary':'Synthetic review','roles':{k:'fixture' for k in ('trading','news','risk','learning')},'decision':'BUY','entry':999}
  response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'candidates':[{'content':{'parts':[{'text':json.dumps(output)}]}}]}).encode()
  with patch.object(ai.urllib.request,'urlopen',return_value=response) as fetch:
   result=ai.review(self.evidence(),self.connection,now=NOW);self.assertTrue(result['connection_verified']);self.assertNotIn('decision',result);self.assertNotIn(b'must-not-be-sent',fetch.call_args.args[0].data)
   self.assertTrue(ai.review(self.evidence(),self.connection,now=NOW)['cached']);self.assertEqual(fetch.call_count,1)
 def test_http_failure_reports_safe_reason_and_clears_verification(self):
  import urllib.error,io
  error=urllib.error.HTTPError('https://example.invalid',404,'synthetic-secret',{},io.BytesIO())
  with patch.object(ai.urllib.request,'urlopen',side_effect=error):
   result=ai.review(self.evidence(),self.connection,now=NOW)
  self.assertEqual(result['http_status'],404);self.assertEqual(result['reason'],'provider_model_unavailable');self.assertFalse(ai.status()['connection_verified']);self.assertNotIn('synthetic-secret',json.dumps(result))
 def test_unmapped_http_failure_preserves_only_numeric_status(self):
  import urllib.error,io
  error=urllib.error.HTTPError('https://example.invalid',503,'synthetic-secret',{},io.BytesIO(b'synthetic-secret'))
  with patch.object(ai.urllib.request,'urlopen',side_effect=error):result=ai.review(self.evidence(),self.connection,now=NOW)
  self.assertEqual(result['http_status'],503);self.assertEqual(ai.status()['last_check']['http_status'],503);self.assertNotIn('synthetic-secret',json.dumps(result))
 def test_budget_and_sanitized_failures(self):
  with patch.object(ai.urllib.request,'urlopen',side_effect=OSError('synthetic-secret')) as fetch:
   for _ in range(10):self.assertEqual(ai.review(self.evidence(),self.connection,now=NOW)['state'],'UNAVAILABLE')
   result=ai.review(self.evidence(),self.connection,now=NOW);self.assertEqual(result['state'],'BUDGET_EXHAUSTED');self.assertEqual(fetch.call_count,10);self.assertNotIn('synthetic-secret',json.dumps(result))
