"""Descriptive paired SL comparison, never a strategy promotion.

Input opportunities must share symbol/time/entry definition and out-of-sample
data. This calculator cannot verify those assumptions from outcome labels.
"""
import math

def wilson(sl,n):
    if not n:return None
    z=1.959963984540054;p=sl/n;d=1+z*z/n
    center=(p+z*z/(2*n))/d
    spread=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*(center-spread),2),round(100*(center+spread),2)]

def compare(rows):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('عينة غير صالحة')
    seen=set();pairs=[]
    for r in rows:
        if not isinstance(r,dict) or not isinstance(r.get('id'),str) or not r['id'] or r['id'] in seen:raise ValueError('معرف فرصة غير صالح أو مكرر')
        seen.add(r['id'])
        if r.get('baseline') not in ('SL','TP','UNRESOLVED') or r.get('candidate') not in ('SL','TP','UNRESOLVED'):raise ValueError('نتيجة غير صالحة')
        if 'UNRESOLVED' not in (r['baseline'],r['candidate']):pairs.append(r)
    n=len(pairs);base=sum(r['baseline']=='SL' for r in pairs);candidate=sum(r['candidate']=='SL' for r in pairs)
    better=sum(r['baseline']=='SL' and r['candidate']=='TP' for r in pairs)
    worse=sum(r['baseline']=='TP' and r['candidate']=='SL' for r in pairs)
    discordant=better+worse
    p=min(1.,2*sum(math.comb(discordant,k) for k in range(min(better,worse)+1))/2**discordant) if discordant else 1.
    return {'عدد_الفرص':len(rows),'الأزواج_المكتملة':n,'غير_محسومة':len(rows)-n,
        'الوقف_قبل':base,'الوقف_بعد':candidate,
        'نسبة_الوقف_قبل':round(100*base/n,2) if n else None,
        'نسبة_الوقف_بعد':round(100*candidate/n,2) if n else None,
        'فاصل_ويلسون_قبل_95':wilson(base,n),'فاصل_ويلسون_بعد_95':wilson(candidate,n),
        'قيمة_احتمال_مقارنة_ماكنيمار_الدقيقة':round(p,8),
        'النتيجة':'انخفاض داخل هذه العينة فقط؛ يلزم التحقق من استقلال عينة الاختبار والتكاليف' if n>=30 and candidate<base and p<.05 else 'الأدلة غير كافية لإثبات تحسن الوقف',
        'تنبيه':'استبعاد النتائج غير المحسومة قد يسبب تحيزاً؛ المقارنة لا تثبت تنفيذ وسيط أو أداءً مستقبلياً'}
