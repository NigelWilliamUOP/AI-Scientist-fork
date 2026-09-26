"""Explicit integration gate checker. Defaults to no network/provider actions.

Run against an authorised host and set OSINT_OWNER_PASSWORD privately.
--capture makes real government requests. --ai authorises one already-configured
model request subject to server caps. --drive uploads an audit to the owner's
connected app folder. None of these flags changes server-side configuration.
"""
import argparse,json,os,time,sys
from pathlib import Path
from datetime import datetime,timezone
import httpx
parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8000');parser.add_argument('--capture',action='store_true');parser.add_argument('--ai',action='store_true');parser.add_argument('--drive',action='store_true');parser.add_argument('--output',type=Path,default=Path('reports/live-integration.json'));args=parser.parse_args()
password=os.getenv('OSINT_OWNER_PASSWORD')
if not password:raise SystemExit('Set OSINT_OWNER_PASSWORD in this process environment. Never put it in source or a command-line argument.')
report={'at':datetime.now(timezone.utc).isoformat(),'url':args.url,'checks':{},'live_ai_calls_requested':int(args.ai)}
with httpx.Client(base_url=args.url,timeout=30,follow_redirects=False,trust_env=False,headers={'Origin':args.url}) as c:
    def post(path,payload):
        r=c.post('/api/v1'+path,json=payload);r.raise_for_status();return r.json()
    def wait(job):
        for _ in range(200):
            r=c.get('/api/v1/jobs/'+job);r.raise_for_status();j=r.json()
            if j['state'] in ('completed','failed'):return j
            time.sleep(.5)
        return {'state':'still_running','id':job}
    r=c.get('/api/v1/health');r.raise_for_status();report['checks']['native_http_health']='passed'
    auth=post('/auth/login',{'password':password});c.headers['X-CSRF-Token']=auth['csrf'];report['checks']['native_http_login']='passed'
    sid=post('/sessions',{})['id'];report['session_id']=sid
    template=wait(post('/sessions/'+sid+'/questions',{'question':'Compile the admitted evidence.','use_ai':False})['job_id'])
    report['checks']['native_http_job']=template['state']
    if args.capture:
        j=wait(post('/sessions/'+sid+'/refresh',{'source_ids':['CF-AWARD','FTS-PIN','FTS-TENDER','FTS-CORRECTION']})['job_id'])
        report['checks']['source_capture']={'job_state':j['state'],'result':j.get('result'),'error':j.get('error')}
    else:report['checks']['source_capture']='not_requested'
    if args.ai:
        try:
            j=wait(post('/sessions/'+sid+'/questions',{'question':'Which dates are targets rather than confirmed operating dates?','use_ai':True})['job_id'])
            report['checks']['live_ai']={'job_state':j['state'],'result':j.get('result'),'error':j.get('error')}
        except httpx.HTTPStatusError as e:report['checks']['live_ai']={'status':'blocked','http_status':e.response.status_code,'error':e.response.json().get('error')}
    else:report['checks']['live_ai']='not_requested'
    e=post('/sessions/'+sid+'/exports',{});r=c.get('/api/v1/exports/'+e['id']+'/download');r.raise_for_status()
    import hashlib
    report['checks']['local_export_sha256']=hashlib.sha256(r.content).hexdigest()==e['sha256']
    if args.drive:
        try:
            j=wait(post('/exports/'+e['id']+'/sync',{})['job_id']);report['checks']['live_drive']={'job_state':j['state'],'result':j.get('result'),'error':j.get('error')}
        except httpx.HTTPStatusError as exc:report['checks']['live_drive']={'status':'blocked','http_status':exc.response.status_code,'error':exc.response.json().get('error')}
    else:report['checks']['live_drive']='not_requested'
args.output.parent.mkdir(exist_ok=True,parents=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
