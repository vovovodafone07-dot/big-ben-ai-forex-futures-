# Render
المساحة المؤكدة HUSSAIN's workspace: tea-dbnq0ms9v7es73denie0.
الخدمة الحالية البديلة srv-dbt68qe1egvs73fhqbg0، bigben-ai-pro-rebound، على main، والرابط https://bigben-ai-pro-rebound.onrender.com.
الخدمة القديمة srv-dbq8kt8ae00c73aa1a6g، bigben-ai-pro-api، تبقى محفوظة حتى وصول حدث TradingView حديث إلى البديلة والتحقق من المصادقة والبيانات والتنبيهات. لا تحذف قاعدة PostgreSQL المشتركة أو مجموعة البيئة الآمنة عند حذف خدمة الويب لاحقاً.
لا تلمس الخدمة القديمة bigben-ai-readonly أو مشروع Railway PR #3.
Build: python -m pip install -r platform/backend/requirements.txt && python -m compileall -q platform/backend/app.py.
Start: python platform/backend/app.py.
انتظر CI ثم انشر commit مجازًا؛ نجاح trigger لا يعني نجاح النشر. تحقق من الحالة live والـcommit وفحص /healthz/storage والسجلات.
المهارة الحالية للنشر تفضل استخدام المستودع الموصول. لم تُنشأ موارد مدفوعة جديدة.

آخر نشر مؤكد للخدمة البديلة: dep-dbt6dkt6e07s73biikf0، commit 0c25909e58cf39fc57ac1621802f2db6ca3b07e0، live في 16 نوفمبر 2026. بعد ربط مجموعة `bigben-ai-pro-production` أعاد `/healthz/storage` الحالة `postgres`، وأكد `/healthz/integrations` وجود كلمة المرور، Webhook، Telegram وTwelve Data دون عرض أي قيمة.
