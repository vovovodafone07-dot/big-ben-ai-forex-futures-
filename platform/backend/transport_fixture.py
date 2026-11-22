"""Explicitly synthetic transport fixture. Never stored as a real signal/trade."""
from datetime import datetime,timezone,timedelta

def payload(normalize,side='BUY'):
    # Known, closed fixture interval, independent of today's exchange calendar.
    now=datetime(2026,11,20,15,15,tzinfo=timezone.utc)
    event={'schema':'bigben.bbb.v1','alert_id':6094187030 if side=='BUY' else 6094187269,
        'symbol':'FOREXCOM:XAUUSD','event':side,'timeframe':'15','time':now.isoformat(),
        'bar_time':(now-timedelta(minutes=15)).isoformat(),'entry':'100',
        'sl':'90' if side=='BUY' else '110','tp':'130' if side=='BUY' else '70','close':'101' if side=='BUY' else '99'}
    return normalize(event,now=now)

def cards(event,trade_card,analysis_card):
    side=event['event'];sign=1 if side=='BUY' else -1
    plan={'symbol':event['symbol'],'asset_class':'cfd','status':'READY','technical_direction':side,
        'entry':event['entry'],'sl':event['sl'],'targets':[{'price':100+sign*10*i} for i in (1,2,3)],
        'confirmation':{'confirmed':True},'conditions':['حالة اصطناعية لاختبار النقل فقط؛ لا شروط سوق حقيقية']}
    banner='🧪 اختبار نقل فقط — أسعار مصطنعة، وليست توصية أو صفقة حقيقية\n'
    technical={'symbol':event['symbol'],'trend':'اتجاه افتراضي للاختبار','event':'حدث اصطناعي لا يثبت سحب سيولة حقيقي',
        'zone':'منطقة اختبار مصطنعة','scenario':'فحص فصل الرسائل فقط، وليس توقعاً للسوق'}
    return [banner+trade_card(plan),banner+analysis_card(technical)]
