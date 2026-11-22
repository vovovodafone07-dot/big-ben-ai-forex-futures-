"""Send an authorized watchlist export; never fetch private TV URLs or credentials."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request
from urllib.parse import urlsplit

def main():
    parser=argparse.ArgumentParser(description='مزامنة لقطة قائمة TradingView المصرح بها')
    parser.add_argument('snapshot',type=Path)
    args=parser.parse_args()
    base=os.getenv('BIGBEN_BASE_URL','').rstrip('/')
    key=os.getenv('BIGBEN_WATCHLIST_SYNC_TOKEN','')
    parsed=urlsplit(base)
    if parsed.scheme!='https' or parsed.hostname!='bigben-ai-pro-rebound.onrender.com' or parsed.username or parsed.query or parsed.fragment or parsed.path or len(key)<32:
        print('يلزم عنوان الخدمة المعتمد ورمز المزامنة في البيئة؛ لا تمرر الأسرار كوسيط سطر أوامر.');return 2
    try:
        payload=json.loads(args.snapshot.read_text(encoding='utf-8'))
        raw=json.dumps(payload,ensure_ascii=False).encode()
        if not 0<len(raw)<=65536:raise ValueError()
        req=urllib.request.Request(base+'/v1/tradingview/watchlist-sync',data=raw,
            headers={'Content-Type':'application/json','X-BigBen-Watchlist-Token':key},method='POST')
        # Do not forward a scope token on redirects.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=15) as response:
            result=json.loads(response.read(8192))
        print(json.dumps(result,ensure_ascii=False));return 0
    except Exception:
        print('تعذر إكمال المزامنة؛ لم تُطبع الاستجابة الخام أو رمز الدخول.');return 1

if __name__=='__main__':sys.exit(main())
