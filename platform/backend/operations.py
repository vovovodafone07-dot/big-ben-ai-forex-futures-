"""Durable evidence of real worker cycles; a configured timer is not a run."""
import json
import uuid
from datetime import datetime, timedelta, timezone


def migrate(c):
    c.execute('CREATE TABLE IF NOT EXISTS job_leases (name TEXT PRIMARY KEY,token TEXT NOT NULL,lease_until TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS job_runs (id TEXT PRIMARY KEY,name TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,payload TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS daily_reports (day TEXT PRIMARY KEY,created_at TEXT NOT NULL,payload TEXT NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS job_runs_time_idx ON job_runs(started_at)')


def claim(c,name,now=None,postgres=False):
    now=now or datetime.now(timezone.utc)
    marker='%s' if postgres else '?'
    token=uuid.uuid4().hex
    until=(now+timedelta(minutes=20)).isoformat()
    result=c.execute('INSERT INTO job_leases(name,token,lease_until) VALUES ('+','.join([marker]*3)+') ON CONFLICT(name) DO UPDATE SET token=excluded.token,lease_until=excluded.lease_until WHERE job_leases.lease_until<='+marker,
                     (name,token,until,now.isoformat()))
    if result.rowcount!=1:return None
    # An expired execution is evidence of interruption, never success.
    c.execute("UPDATE job_runs SET status='INTERRUPTED',finished_at="+marker+" WHERE name="+marker+" AND status='RUNNING'",(now.isoformat(),name))
    c.execute('INSERT INTO job_runs(id,name,started_at,status,payload) VALUES ('+','.join([marker]*5)+')',
              (token,name,now.isoformat(),'RUNNING','{}'))
    return token


def finish(c,token,stages,now=None,postgres=False):
    marker='%s' if postgres else '?'
    now=now or datetime.now(timezone.utc)
    payload={'stages':stages,'timer_interval_seconds':21600,'free_host_can_sleep':True}
    status='FAILED' if any(s['status']=='FAILED' for s in stages) else 'COMPLETED'
    c.execute('UPDATE job_runs SET finished_at='+marker+',status='+marker+',payload='+marker+' WHERE id='+marker+" AND status='RUNNING'",
              (now.isoformat(),status,json.dumps(payload),token))
    c.execute('UPDATE job_leases SET lease_until='+marker+' WHERE token='+marker,(now.isoformat(),token))
    return status


def save_daily(c,evidence,now=None,postgres=False):
    now=now or datetime.now(timezone.utc)
    coverage=evidence['coverage']; research=evidence['research']; replay=evidence['replay']
    successful=sum(s.get('state')=='CONNECTED' for s in coverage.get('symbols',[]))
    # Keep references rather than copying thousands of trades into every report.
    references={**evidence,
        'research':{'runs':[{k:r.get(k) for k in ('run_id','symbol','created_at','status','dataset_sha256')} for r in research.get('runs',[])[:20]]},
        'replay':{'runs':[{k:r.get(k) for k in ('run_id','symbol','created_at','dataset_sha256','pine_source_sha256')} for r in replay.get('runs',[])[:20]]}}
    report={'day':now.date().isoformat(),'created_at':now.isoformat(),
            'evidence':references,'automatic_promotion':False,'notification_status':'not_requested',
            'arabic_report':('\n'.join(['تقرير Big Ben البحثي — '+now.date().isoformat(),
                 'حالة دورة العامل: '+str(evidence.get('cycle_status','UNKNOWN')),
                 'مصادر تاريخ متصلة: '+str(successful)+' / '+str(len(coverage.get('symbols',[]))),
                 'تقارير البحث المحفوظة: '+str(len(research.get('runs',[]))),
                 'تقارير محاكاة قواعد المؤشر: '+str(len(replay.get('runs',[]))),
                 'النتائج بحثية؛ ليست صفقات منفذة أو إثبات ربحية.',
                 'لا ترقية تلقائية؛ تتطلب مطابقة Pine والتكاليف والتحقق المستقل.',
                 'الاستضافة المجانية قد تنام؛ توقيت هذا التقرير يثبت تشغيله فقط.']))}
    marker='%s' if postgres else '?'
    inserted=c.execute('INSERT INTO daily_reports(day,created_at,payload) VALUES ('+','.join([marker]*3)+') ON CONFLICT(day) DO NOTHING',
                       (report['day'],report['created_at'],json.dumps(report))).rowcount==1
    return report if inserted else None


def notification_result(c,report,status,postgres=False):
    report={**report,'notification_status':status}
    marker='%s' if postgres else '?'
    c.execute('UPDATE daily_reports SET payload='+marker+' WHERE day='+marker,(json.dumps(report),report['day']))


def snapshot(c):
    runs=[]
    for row in c.execute('SELECT id,name,started_at,finished_at,status,payload FROM job_runs ORDER BY started_at DESC LIMIT 20').fetchall():
        runs.append(dict(zip(('id','name','started_at','finished_at','status'),row[:5]))|json.loads(row[5]))
    reports=[json.loads(r[0]) for r in c.execute('SELECT payload FROM daily_reports ORDER BY day DESC LIMIT 14').fetchall()]
    return {'runs':runs,'daily_reports':reports,'timer_interval_seconds':21600,
            'free_host_can_sleep':True,'next_run_guaranteed':False}
