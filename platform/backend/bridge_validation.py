"""Validated BBB alert bridge. Preserve original levels and M15 timeframe."""
import hashlib
import math
import re
from datetime import datetime,timezone

ALERTS={6094195326:('CAPITALCOM:SPX500','SELL'),6094195172:('CAPITALCOM:SPX500','BUY'),
6094194393:('SKILLING:US30','SELL'),6094188313:('SKILLING:US30','BUY'),
6094187680:('CAPITALCOM:NAS100','SELL'),6094187510:('CAPITALCOM:NAS100','BUY'),
6094187269:('FOREXCOM:XAUUSD','SELL'),6094187030:('FOREXCOM:XAUUSD','BUY')}

def normalize(payload,now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(payload,dict) or payload.get('schema')!='bigben.bbb.v1':raise ValueError('مخطط التنبيه غير صالح')
    if type(payload.get('alert_id')) is not int or payload['alert_id'] not in ALERTS:raise ValueError('التنبيه غير مسجل')
    symbol,side=ALERTS[payload['alert_id']]
    if payload.get('symbol')!=symbol or payload.get('event')!=side or str(payload.get('timeframe'))!='15':raise ValueError('بيانات التنبيه لا تطابق إعداداته')
    def number(key):
        raw=payload.get(key)
        if type(raw) not in (str,int,float) or isinstance(raw,bool):raise ValueError('مستوى سعري غير صالح')
        try:value=float(raw)
        except (ValueError,TypeError):raise ValueError('تعذر قراءة مستوى السعر') from None
        if not math.isfinite(value) or value<=0:raise ValueError('مستوى سعري غير صالح')
        return value
    entry,stop,target,close=[number(k) for k in ('entry','sl','tp','close')]
    if not (stop<entry<target if side=='BUY' else target<entry<stop):raise ValueError('ترتيب الدخول والوقف والهدف غير صالح')
    def stamp(key):
        try:
            dt=datetime.fromisoformat(str(payload[key]).replace('Z','+00:00'))
            if dt.tzinfo is None:raise ValueError()
            return dt.astimezone(timezone.utc)
        except (KeyError,ValueError,TypeError):raise ValueError('توقيت التنبيه غير صالح') from None
    sent=stamp('time');bar=stamp('bar_time')
    if not 0<=(now-sent).total_seconds()<=180:raise ValueError('التنبيه متأخر أو توقيته مستقبلي')
    if not 900<=(sent-bar).total_seconds()<=1080:raise ValueError('شمعة M15 لم تغلق أو قديمة')
    if bar.minute%15 or bar.second:raise ValueError('توقيت شمعة M15 غير مطابق')
    key=hashlib.sha256((str(payload['alert_id'])+symbol+side+bar.isoformat()).encode()).hexdigest()
    return {'schema':'bigben.v1','event_id':'bbb:'+key,'symbol':symbol,'event':side,
        'entry':entry,'sl':stop,'tp':target,'rr':abs(target-entry)/abs(entry-stop),
        'close':close,'time':sent.isoformat(),'bar_time':bar.isoformat(),'timeframe':'15',
        'strategy_version':'BBB Ref9.1','bridge_version':'bbb.v1','asset_class':'cfd',
        'provider':'TradingView alert snapshot','source_identity_verified':False,
        'market_open_verified':False,'broker_execution':False}

def template(alert_id,token_placeholder='ضع_السر_من_إعدادات_الخادم'):
    symbol,side=ALERTS[alert_id]
    return {'schema':'bigben.bbb.v1','alert_id':alert_id,'token':token_placeholder,
        'symbol':symbol,'event':side,'timeframe':'{{interval}}','time':'{{timenow}}','bar_time':'{{time}}',
        'entry':'{{plot("Entry")}}','sl':'{{plot("SL")}}','tp':'{{plot("TP")}}','close':'{{plot("Regular close")}}'}
