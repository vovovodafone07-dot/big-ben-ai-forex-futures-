"""Read-only audit with a scoped header credential; never prints credentials."""
import json,os,sys,urllib.request
from urllib.parse import urlsplit
url=os.getenv('BIGBEN_AUDIT_BASE_URL','https://bigben-ai-pro-rebound.onrender.com')
token=os.getenv('BIGBEN_AUDIT_TOKEN','')
if len(token)<32:raise SystemExit('يلزم ضبط سر الفحص في متغير البيئة دون وضعه في سطر الأوامر')
p=urlsplit(url)
if p.scheme!='https' or p.username or p.password or p.query or p.fragment or p.path not in ('','/'):
 raise SystemExit('عنوان المنصة غير صالح للفحص الآمن')
try:
 req=urllib.request.Request(url.rstrip('/')+'/v1/audit/state',headers={'X-BigBen-Audit-Token':token})
 with urllib.request.urlopen(req,timeout=20) as response:
  report=json.loads(response.read(131072))
 print('تمت قراءة حالة المنصة بمصادقة فحص محدودة الصلاحية')
 print(json.dumps(report,ensure_ascii=False,indent=2))
except Exception:raise SystemExit('تعذر فحص الحالة؛ تحقق من اتصال الخادم وصلاحية سر الفحص') from None
