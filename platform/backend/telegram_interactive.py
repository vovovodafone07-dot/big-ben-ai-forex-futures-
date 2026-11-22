"""Arabic private Telegram interactions; no polling, broker orders, or fabricated news."""
import hashlib
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ZONE=ZoneInfo('Asia/Muscat')
def migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS telegram_bot_state (chat TEXT PRIMARY KEY, mode TEXT NOT NULL, symbol TEXT, news_enabled INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS telegram_bot_receipts (id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL)')

def claim(db,key,postgres=False,now=None):
    m='%s' if postgres else '?'
    return db.execute('INSERT INTO telegram_bot_receipts(id,status,created_at) VALUES ('+','.join([m]*3)+') ON CONFLICT(id) DO NOTHING',
        (key,'claimed',(now or datetime.now(timezone.utc)).isoformat())).rowcount==1

def keyboard(rows):
    return {'inline_keyboard':[[{'text':title,'callback_data':data} for title,data in row] for row in rows]}

def home():
    return keyboard([[('⚡ سكالب','mode:scalp'),('🌊 سوينغ','mode:swing')],
        [('🔔 تنبيه الأخبار','news'),('📌 اختيار الزوج','symbols:0')],
        [('🟢 حالة السوق','market'),('🎯 الصفقات النشطة','active')], [('🔄 تحديث التحليل','refresh')]])

def token(symbol):return hashlib.sha256(symbol.encode()).hexdigest()[:16]

def scenario(kind):
    if kind=='CPI':
        return '🧪 اختبار تعليمي لخبر التضخم، وليس توصية\nأعلى من المتوقع: 🔴 سيناريو هبوط الذهب والناسداك وصعود الدولار.\nأقل من المتوقع: 🔵 سيناريو صعود الذهب والناسداك وهبوط الدولار.\nيلزم تأكيد السعر؛ المكونات والتوقعات المسبقة قد تعكس الاستجابة.'
    if kind=='NFP':
        return '🧪 اختبار تعليمي لخبر الوظائف، وليس توصية\nوظائف أقوى من المتوقع: احتمال صعود الدولار وضغط على الذهب.\nوظائف أضعف: احتمال هبوط الدولار وصعود الذهب.\nالأجور والبطالة والمراجعات قد تعكس النتيجة؛ لا يُستنتج اتجاه الناسداك من الرقم وحده.'
    return '🧪 قرار الفائدة\nتشديد يفوق التوقعات: احتمال صعود الدولار وضغط على الذهب والناسداك.\nتيسير يفوق التوقعات: الاحتمال المعاكس.\nيلزم مقارنة القرار والتوجيه بالمُسعّر مسبقاً وتأكيد حركة السعر.'

def today_events(snapshot,now):
    events=[]
    for e in (snapshot or {}).get('calendar',[]):
        if not isinstance(e,dict) or not e.get('feed_fresh') or e.get('feed_state')!='CONNECTED':continue
        try:
            dt=datetime.fromisoformat(e['time'].replace('Z','+00:00'))
            if dt.tzinfo is None:continue
            dt=dt.astimezone(ZONE)
        except (ValueError,TypeError,KeyError):continue
        if dt.date()==now.astimezone(ZONE).date():events.append((dt,e))
    return sorted(events,key=lambda item:item[0])

def digest(snapshot,now=None):
    now=now or datetime.now(timezone.utc)
    lines=['📰 نشرة الأخبار الصباحية وتوقعات السعر | التاريخ: '+now.astimezone(ZONE).date().isoformat(), '━━━━━━━━━━━━━━━━━━']
    events=today_events(snapshot,now)
    if not events:lines.append('لا تتوفر قائمة موثقة ومحدثة لأخبار اليوم؛ هذا لا يعني خلو اليوم من الأخبار.')
    for dt,e in events:
        title=str(e.get('title_ar') or 'إصدار اقتصادي مجدول')[:100]
        lines.append('⏰ '+dt.strftime('%H:%M')+' — '+title+' | التوقع: '+str(e.get('consensus') if e.get('consensus') is not None else 'غير موثق')+' | السابق: '+str(e.get('previous') if e.get('previous') is not None else 'غير موثق'))
        kind=str(e.get('classification') or e.get('title','')).upper()
        if 'CPI' in kind or 'CONSUMER PRICE' in kind:lines.append('أعلى من التوقع: 🔴 هبوط محتمل للذهب والناسداك؛ أقل: 🔵 صعود محتمل. يلزم تأكيد السعر.')
        elif 'NFP' in kind or 'EMPLOYMENT' in kind:lines.append('قوة الوظائف قد تدعم الدولار وتضغط على الذهب؛ تُراجع الأجور والبطالة قبل استنتاج الاتجاه.')
        else:lines.append('اتجاه السعر غير محسوم من موعد الخبر وحده؛ يلزم الرقم الفعلي والتوقع الموثق وتأكيد السعر.')
    lines.append('الأوقات بتوقيت عُمان. السيناريوهات احتمالية، ولا تُنشئ صفقة.')
    text='\n'.join(lines)
    if len(text)>3900:
        return '\n'.join(lines[:2])+ '\nعدد الأخبار يتجاوز حجم رسالة واحدة؛ افتح التقويم في المنصة للاطلاع على القائمة كاملة.\nلم تُرسل قائمة مبتورة على أنها كاملة.'
    return text

def handle(db,update,*,allowed_users,connected,news,journal,postgres=False,now=None):
    now=now or datetime.now(timezone.utc)
    callback=update.get('callback_query') or {}
    msg=callback.get('message') or update.get('message') or {}
    sender=callback.get('from') or msg.get('from') or {}
    chat=msg.get('chat') or {}
    # Private conversations only; a configured group does not authorize all its members.
    if chat.get('type')!='private' or str(sender.get('id')) not in allowed_users or sender.get('id')!=chat.get('id'):
        raise PermissionError('هذا الحساب غير مصرح له باستخدام البوت')
    ident=update.get('update_id')
    if type(ident) is not int or ident<0:raise ValueError('تحديث غير صالح')
    if not claim(db,'update:'+str(ident),postgres,now):return None
    m='%s' if postgres else '?';chat_id=str(chat['id'])
    db.execute('INSERT INTO telegram_bot_state(chat,mode,news_enabled) VALUES ('+m+",'scalp',0) ON CONFLICT(chat) DO NOTHING",(chat_id,))
    mode,symbol,enabled=db.execute('SELECT mode,symbol,news_enabled FROM telegram_bot_state WHERE chat='+m,(chat_id,)).fetchone()
    action=callback.get('data') or 'home'
    text='اختر نوع التحليل أو الخدمة المطلوبة.';markup=home();request=None
    assets=[a for a in connected() if a.get('asset_class') in ('forex','cfd','futures')]
    if action.startswith('mode:'):
        mode=action.split(':',1)[1]
        if mode not in ('scalp','swing'):raise ValueError('نمط غير صالح')
        db.execute('UPDATE telegram_bot_state SET mode='+m+' WHERE chat='+m,(mode,chat_id));action='symbols:0'
    if action.startswith('symbols:'):
        try:page=max(0,int(action.split(':',1)[1]))
        except ValueError:raise ValueError('صفحة غير صالحة')
        rows=[[(a.get('label') or a['symbol'],'pick:'+token(a['symbol']))] for a in assets[page*12:(page+1)*12]]
        if page:rows.append([('السابق','symbols:'+str(page-1))])
        if (page+1)*12<len(assets):rows.append([('التالي','symbols:'+str(page+1))])
        rows.append([('القائمة الرئيسية','home')]);markup=keyboard(rows)
        text=('اختر الأصل لتحليل '+('السكالب' if mode=='scalp' else 'السوينغ')+'.' if assets else 'لا توجد أصول مؤهلة ذات مصدر أسعار موثق حالياً؛ لا يكفي ظهور الأصل في قائمة TradingView.')
    elif action.startswith('pick:') or action=='refresh':
        selected=next((a['symbol'] for a in assets if (token(a['symbol'])==action[5:] if action.startswith('pick:') else a['symbol']==symbol)),None)
        if not selected:text='الأصل غير متصل حالياً أو لم يُحدّد؛ اختر أصلاً من القائمة.'
        else:
            db.execute('UPDATE telegram_bot_state SET symbol='+m+' WHERE chat='+m,(selected,chat_id))
            request={'symbol':selected,'mode':mode}
            text='جار فحص البيانات وشروط الدخول.'
    elif action=='news':
        text='إعدادات الأخبار';markup=keyboard([[('⏰ '+('إيقاف' if enabled else 'تفعيل')+' تنبيه الأخبار','news:off' if enabled else 'news:on')],[('📰 نشرة اليوم الصباحية','digest')],[('🧪 اختبار سيناريو خبر','scenario')],[('القائمة الرئيسية','home')]])
    elif action in ('news:on','news:off'):
        db.execute('UPDATE telegram_bot_state SET news_enabled='+m+' WHERE chat='+m,(int(action=='news:on'),chat_id))
        text='تم تفعيل تنبيهات الأخبار والنشرة الصباحية.' if action=='news:on' else 'تم إيقاف التنبيهات الإضافية لهذا الحساب.'
    elif action=='digest':text=digest(news(),now)
    elif action=='scenario':
        text='اختر اختباراً تعليمياً؛ لن يُرسل كصفقة.';markup=keyboard([[('التضخم','scenario:CPI'),('الوظائف','scenario:NFP')],[('الفائدة','scenario:RATE')]])
    elif action.startswith('scenario:'):text=scenario(action.split(':',1)[1])
    elif action=='market':text='🟢 حالة السوق\n'+ ('\n'.join(a['symbol']+' — '+str(a.get('market_state','حالة الجلسة غير مؤكدة')) for a in assets) or 'لا توجد تغذية موثقة متصلة؛ إرسال الصفقات غير مفعل لهذه الأصول.')
    elif action=='active':
        active=[e for e in journal() if e.get('state') not in ('الهدف الثالث تحقق','وقف الخسارة تحقق','نتيجة غير محسومة')]
        text='🎯 متابعة الصفقات البحثية النشطة\n'+ ('\n'.join(str(e['symbol'])+' — '+str(e['state']) for e in active[:20]) or 'لا توجد صفقات نشطة مسجلة.')
    return {'chat_id':chat_id,'text':text,'reply_markup':markup,'callback_id':callback.get('id'),'analysis_request':request}

def configure_webhook(token,secret,base_url,allowed_users,opener=None):
    """Register only an unused webhook or this exact endpoint; preserve another receiver."""
    import urllib.request
    from urllib.parse import urlsplit
    if not token or len(secret)<32 or not allowed_users:return 'غير مهيأ'
    parsed=urlsplit(base_url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        return 'عنوان استقبال غير صالح'
    endpoint=base_url.rstrip('/')+'/v1/telegram/updates'
    opener=opener or urllib.request.urlopen
    def call(method,payload=None):
        request=urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'})
        with opener(request,timeout=8) as response:
            if response.status!=200:raise ValueError('response')
            data=response.read(65537)
            if len(data)>65536:raise ValueError('oversized')
            result=json.loads(data)
            if result.get('ok') is not True:raise ValueError('rejected')
            return result.get('result')
    try:
        info=call('getWebhookInfo')
        if not isinstance(info,dict):return 'تعذر التحقق'
        if info.get('url') not in ('',endpoint):return 'يوجد مستقبل آخر؛ لم يجر تغييره'
        result=call('setWebhook',{'url':endpoint,'secret_token':secret,
              'allowed_updates':['message','callback_query'],'drop_pending_updates':False})
        if result is not True:return 'تعذر التسجيل'
        verified=call('getWebhookInfo')
        return 'تم تسجيل المستقبل' if isinstance(verified,dict) and verified.get('url')==endpoint else 'تعذر تأكيد التسجيل'
    except Exception:return 'تعذر اتصال Telegram'
