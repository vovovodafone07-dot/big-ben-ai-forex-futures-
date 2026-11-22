"""Closed-candle sweep -> displacement/MSB -> FVG retest evidence, no Pine edits."""
def inspect(bars,side,bias,atr,tick):
    checks={'اتجاه متوافق':bias==('BULLISH' if side=='BUY' else 'BEARISH'),
            'سحب سيولة واضح':False,'كسر هيكل بزخم':False,'إعادة اختبار فجوة سعرية':False,
            'نطاق حركة كاف':False}
    if len(bars)<30 or atr<=0:return {'confirmed':False,'checks':checks}
    sign=1 if side=='BUY' else -1
    span=max(b[2] for b in bars[-12:])-min(b[3] for b in bars[-12:])
    checks['نطاق حركة كاف']=span>=max(2*atr,8*tick)
    last=bars[-1]
    for i in range(len(bars)-3,max(12,len(bars)-25)-1,-1):
        before=bars[i-12:i];sweep=bars[i]
        boundary=min(b[3] for b in before) if sign==1 else max(b[2] for b in before)
        swept=(sweep[3]<boundary and sweep[4]>boundary) if sign==1 else (sweep[2]>boundary and sweep[4]<boundary)
        if not swept:continue
        checks['سحب سيولة واضح']=True
        structure=max(b[2] for b in before[-3:]) if sign==1 else min(b[3] for b in before[-3:])
        for j in range(i+1,len(bars)-1):
            bar=bars[j]
            broken=bar[4]>structure if sign==1 else bar[4]<structure
            if not broken or (bar[4]-bar[1])*sign<.5*atr:continue
            checks['كسر هيكل بزخم']=True
            if j<2:continue
            low,high=(bars[j-2][2],bar[3]) if sign==1 else (bar[2],bars[j-2][3])
            if high-low<tick:continue
            # Reject a zone invalidated before its final retest.
            if any((b[4]<low if sign==1 else b[4]>high) for b in bars[j+1:-1]):continue
            retest=last[3]<=high and last[2]>=low
            hold=(last[4]>high and last[4]>last[1]) if sign==1 else (last[4]<low and last[4]<last[1])
            if not (retest and hold):continue
            checks['إعادة اختبار فجوة سعرية']=True
            anchor=min(sweep[3],last[3],low) if sign==1 else max(sweep[2],last[2],high)
            return {'confirmed':all(checks.values()),'checks':checks,'zone':[low,high],
                'entry':high if sign==1 else low,'anchor':anchor,'level':structure,
                'sweep_time':sweep[0].isoformat(),'msb_time':bar[0].isoformat(),
                'zone_time':bar[0].isoformat(),'reason':'سحب سيولة ثم كسر هيكل بزخم وإعادة اختبار فجوة سعرية مغلقة'}
    return {'confirmed':False,'checks':checks}
