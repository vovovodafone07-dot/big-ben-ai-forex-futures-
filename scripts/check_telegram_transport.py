"""اختبار نقل اصطناعي صريح؛ لا ينشئ صفقة حقيقية ولا يثبت منشأ TradingView."""
import json
import os
import re
import sys
import urllib.request
from urllib.parse import urlsplit

def main():
    base=os.getenv('BIGBEN_AUDIT_BASE_URL','https://bigben-ai-pro-rebound.onrender.com').rstrip('/')
    secret=os.getenv('BIGBEN_TRANSPORT_TEST_TOKEN','')
    ident=os.getenv('BIGBEN_TRANSPORT_SELF_TEST_ID','')
    url=urlsplit(base)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/') or len(secret)<32 or not re.fullmatch(r'[A-Za-z0-9_-]{8,60}',ident):
        print('يلزم عنوان آمن ورمز اختبار ومعرف تشغيل مطابق لإعداد الخادم.');return 2
    results=[]
    try:
        for case in ('closed','open','open'):
            req=urllib.request.Request(base+'/v1/tradingview/transport-test',data=json.dumps({'test_id':ident,'case':case}).encode(),headers={'Content-Type':'application/json','X-BigBen-Test-Token':secret},method='POST')
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read(65537)
            if len(raw)>65536:raise ValueError()
            results.append(json.loads(raw))
    except Exception:
        print('تعذر إكمال الاختبار؛ لا تعد الإرسال بمعرف جديد قبل مراجعة إيصالات الخادم.');return 1
    closed,opened,duplicate=results
    if closed.get('مكرر') or opened.get('مكرر'):
        print('سبق استخدام المعرف؛ راجع النتيجة المحفوظة، ولا تعتبر هذه محاولة إرسال جديدة.');return 1
    ids=[r.get('معرف_الرسالة') for r in opened.get('الرسائل',[])]
    ok=closed.get('بوابة_السوق_المغلق')=='حجبت الإرسال' and len(ids)==2 and all(type(i) is int for i in ids) and duplicate.get('مكرر') is True
    print('نجح حجب السوق المغلق وتسليم بطاقتي الاختبار ومنع التكرار.' if ok else 'الاختبار غير مكتمل؛ راجع الحالة دون إعادة إرسال عمياء.')
    if ok:print('إيصالات قبول Telegram: '+', '.join(map(str,ids))+'؛ يلزم تأكيد المستلم، ولا يثبت ذلك إشارة سوق فعلية.')
    return 0 if ok else 1

if __name__=='__main__':sys.exit(main())
