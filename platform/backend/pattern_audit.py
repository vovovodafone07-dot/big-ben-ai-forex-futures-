"""Deterministic descriptive pattern checks; not seven autonomous trading strategies.

Every check exposes its operational definition. No new orders, trade levels,
remote calls, or claim of full ICT/SMC equivalence is made here.
"""
import math
from datetime import datetime, timezone

NAMES=('ICT','SMC','CRT','SMT','CISD','Turtle Soup','QM')

def inspect(symbol,provider,rows,now=None):
    now=now or datetime.now(timezone.utc)
    bars=[]
    try:
        for row in rows:
            stamp=datetime.fromisoformat(str(row[0]).replace('Z','+00:00'))
            values=list(map(float,row[1:5]))
            if stamp.tzinfo is None or not all(math.isfinite(v) and v>0 for v in values):raise ValueError()
            op,hi,lo,cl=values
            if not lo<=min(op,cl)<=max(op,cl)<=hi:raise ValueError()
            if stamp.minute%5 or stamp.second or stamp.microsecond:raise ValueError()
            # Candle timestamps are opens; only evaluate fully closed bars.
            if (now-stamp).total_seconds()>=300:bars.append((stamp,op,hi,lo,cl))
        bars.sort(key=lambda b:b[0])
        if len({b[0] for b in bars})!=len(bars):raise ValueError()
    except (ValueError,TypeError,IndexError):bars=[]
    # A gap terminates the sequence; never infer a pattern across a session gap.
    for i in range(len(bars)-1,0,-1):
        if (bars[i][0]-bars[i-1][0]).total_seconds()!=300:
            bars=bars[i:];break
    results=[]
    def add(name,rule,found=None,note=''):
        results.append({'name':name,'state':'requires_data' if found is None else 'observed' if found else 'not_observed',
                        'state_ar':'يحتاج بيانات إضافية' if found is None else 'رُصد النموذج' if found else 'فُحص؛ لم يُرصد النموذج',
                        'rule':rule,'detail':note})
    last=bars[-1] if bars else None
    fvg=None if len(bars)<3 else last[3]>bars[-3][2] or last[2]<bars[-3][3]
    msb=None if len(bars)<21 else last[4]>max(b[2] for b in bars[-21:-1]) or last[4]<min(b[3] for b in bars[-21:-1])
    sweep=None if len(bars)<21 else (last[2]>max(b[2] for b in bars[-21:-1]) and last[4]<max(b[2] for b in bars[-21:-1])) or (last[3]<min(b[3] for b in bars[-21:-1]) and last[4]>min(b[3] for b in bars[-21:-1]))
    add('ICT','فجوة ثلاث شموع مغلقة؛ فحص جزئي لمنهج ICT',fvg)
    add('SMC','إغلاق خارج نطاق آخر عشرين شمعة؛ فحص هيكل وصفي',msb)
    crt=None if len(bars)<2 else (last[2]>bars[-2][2] and bars[-2][3]<last[4]<bars[-2][2]) or (last[3]<bars[-2][3] and bars[-2][3]<last[4]<bars[-2][2])
    add('CRT','تجاوز طرف نطاق الشمعة السابقة ثم إغلاق داخله',crt)
    add('SMT','مقارنة قمم وقِيعان أصلين مرتبطين متزامنين من مصدر موثق',None,'لم تُحدد سلسلة مقارنة متزامنة؛ لا يُفترض اختلاف بين أصلين من أصل واحد.')
    cisd=None if len(bars)<2 else (bars[-2][4]<bars[-2][1] and last[4]>bars[-2][1] and last[4]>last[1]) or (bars[-2][4]>bars[-2][1] and last[4]<bars[-2][1] and last[4]<last[1])
    add('CISD','تجاوز افتتاح الشمعة السابقة المعاكسة بإغلاق؛ تعريف تشغيلي مبسط',cisd)
    add('Turtle Soup','تجاوز قمة أو قاع عشرين شمعة ثم إغلاق داخل النطاق',sweep)
    pivots=[]
    for i in range(2,len(bars)-2):
        b=bars[i];near=bars[i-2:i]+bars[i+1:i+3]
        kind='H' if b[2]>max(x[2] for x in near) else 'L' if b[3]<min(x[3] for x in near) else None
        if kind:
            value=b[2] if kind=='H' else b[3]
            if pivots and pivots[-1][0]==kind:
                if (kind=='H' and value>pivots[-1][1]) or (kind=='L' and value<pivots[-1][1]):pivots[-1]=(kind,value)
            else:pivots.append((kind,value))
    qm=None
    if len(bars)>=30:
        qm=False
        if len(pivots)>=5:
            p=pivots[-5:];k=''.join(x[0] for x in p);v=[x[1] for x in p]
            qm=(k=='HLHLH' and v[2]>v[0] and v[3]<v[1] and v[4]<v[2] and last[4]<v[4]) or (k=='LHLHL' and v[2]<v[0] and v[3]>v[1] and v[4]>v[2] and last[4]>v[4])
    add('QM','خمسة محاور مؤكدة بجارين؛ رأس متطرف وكسر هيكل وكتف أدنى أو أعلى؛ فحص وصفي',qm)
    age=(now-last[0]).total_seconds() if last else None
    return {'symbol':symbol,'provider':provider,'candles':len(bars),'source_time':last[0].isoformat() if last else None,
            'fresh':age is not None and 300<=age<=630,'checks':results,
            'notice':'فحوص أنماط وصفية بالقواعد المعروضة، وليست استراتيجيات مكتملة أو توصيات دخول.'}
