from __future__ import annotations
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from osint_core.domain import Factor, posterior, replace_factor
from .archive import make_export, sync_export
from .collector import refresh
from .drive import Drive
from .logic import AppError, MODES, assessment_for_session, baseline, create_session, graph, selected, session
from .model import answer_job
from .settings import ROOT, Settings
from .store import Store, dump, now, sha, uid

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Login(Strict):
    password: str=Field(min_length=1,max_length=256)
class NewSession(Strict):
    mode: Literal['CURRENT_INVESTIGATION','HISTORICAL_RECONSTRUCTION','RECORDED_REPLAY']='CURRENT_INVESTIGATION'
    cutoff: str | None=None
    from_session_id: str | None=None
class Refresh(Strict):
    source_ids: list[str]=Field(min_length=1,max_length=4)
class Exclusion(Strict):
    source_id: str
    excluded: bool
class Question(Strict):
    question: str=Field(min_length=1,max_length=4000)
    use_ai: bool=False
    challenge: bool=False
    source_ids: list[str]=Field(default_factory=list,max_length=5)
class Review(Strict):
    job_id: str
    expected_revision: int=Field(ge=0)
    rationale: str=Field(min_length=10,max_length=2000)
    support_checked: Literal[True]
class Sensitivity(Strict):
    prior: float=Field(gt=0,lt=1,allow_inf_nan=False)
    initial_lr: float=Field(gt=0,le=1000,allow_inf_nan=False)
    replacement_lr: float=Field(gt=0,le=1000,allow_inf_nan=False)


def create_app(settings: Settings | None=None) -> FastAPI:
    cfg=settings or Settings(); store=Store(cfg.data_dir); store.seed(ROOT/'seeds')
    if not cfg.owner_password:
        bootstrap=store.root/'secrets'/'owner-password.txt'
        if not bootstrap.exists():
            bootstrap.write_text(secrets.token_urlsafe(24)+'\n'); bootstrap.chmod(0o600)
        cfg.owner_password=bootstrap.read_text().strip()
    salt=b'OSINT-Bayes-auth-0.4.1'
    def password_hash(value: str) -> bytes:
        return hashlib.scrypt(value.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    owner_hash=password_hash(cfg.owner_password)
    reviewer_hash=password_hash(cfg.reviewer_password or secrets.token_urlsafe(32))
    drive=Drive(cfg,store); stopped=threading.Event()
    def worker() -> None:
        store.recover()
        while not stopped.is_set():
            job=store.claim_job()
            if not job:
                stopped.wait(.15); continue
            try:
                if job['kind']=='refresh':
                    result=refresh(store,job,ROOT/'seeds')
                elif job['kind']=='question':
                    result=answer_job(store,cfg,job)
                elif job['kind']=='drive_sync':
                    result=sync_export(store,drive,job)
                else:
                    raise AppError('JOB_KIND_NOT_SUPPORTED')
                store.finish_job(job,result=result)
            except Exception as exc:
                store.finish_job(job,error=exc.code if isinstance(exc,AppError) else 'JOB_FAILED')
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        thread=None
        if cfg.start_worker:
            thread=threading.Thread(target=worker,daemon=True,name='osint-single-worker'); thread.start()
        yield
        stopped.set()
        if thread:
            thread.join(timeout=2)
    app=FastAPI(title='OSINT Bayes',version='0.4.1',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store=store; app.state.settings=cfg; app.state.drive=drive
    def auth(request: Request, owner: bool=False) -> dict:
        token=request.cookies.get('osint_session','')
        if not token or len(token)>200:
            raise AppError('AUTH_REQUIRED',401)
        row=store.one('SELECT * FROM auth WHERE id=?',(sha(token),))
        if not row or row['expires']<time.time():
            raise AppError('AUTH_REQUIRED',401)
        if owner and row['role']!='owner':
            raise AppError('FORBIDDEN',403)
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not hmac.compare_digest(request.headers.get('x-csrf-token',''),row['csrf']):
                raise AppError('CSRF_INVALID',403)
        return row
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse({'error':exc.code},status_code=exc.status)
    @app.middleware('http')
    async def boundary(request: Request, call_next):
        try:
            if request.url.hostname not in (urlparse(cfg.public_url).hostname,):
                return JSONResponse({'error':'HOST_NOT_ALLOWED'},status_code=400)
            if request.method not in ('GET','HEAD','OPTIONS'):
                if request.headers.get('origin')!=cfg.public_url:
                    return JSONResponse({'error':'ORIGIN_NOT_ALLOWED'},status_code=403)
                try:
                    if int(request.headers.get('content-length','0'))>65536:
                        return JSONResponse({'error':'REQUEST_TOO_LARGE'},status_code=413)
                except ValueError:
                    return JSONResponse({'error':'INVALID_LENGTH'},status_code=400)
                # Do not trust Content-Length for chunked requests.
                size=0; chunks=[]
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>65536:
                        return JSONResponse({'error':'REQUEST_TOO_LARGE'},status_code=413)
                    chunks.append(chunk)
                request._body=b''.join(chunks)
            response=await call_next(request)
        except Exception:
            return JSONResponse({'error':'INTERNAL_ERROR'},status_code=500)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',
            'Referrer-Policy':'strict-origin-when-cross-origin','Permissions-Policy':'camera=(), microphone=(), geolocation=()',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        if cfg.production:
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.get('/api/v1/health')
    def health():
        return {'status':'ok','version':'0.4.1','release':cfg.release}

    @app.post('/api/v1/auth/login')
    def login(payload: Login,request: Request):
        peer=request.client.host if request.client else 'unknown'; current=time.time()
        with store.connect(write=True) as db:
            db.execute('DELETE FROM attempts WHERE at<?',(current-60,))
            count=db.execute('SELECT COUNT(*) FROM attempts WHERE peer=?',(peer,)).fetchone()[0]
            if count>=8:
                raise AppError('LOGIN_RATE_LIMITED',429)
            db.execute('INSERT INTO attempts VALUES (?,?)',(peer,current))
        hashed=password_hash(payload.password)
        owner_ok=hmac.compare_digest(hashed,owner_hash); reviewer_ok=hmac.compare_digest(hashed,reviewer_hash)
        if not owner_ok and not (cfg.reviewer_password and reviewer_ok):
            raise AppError('LOGIN_FAILED',401)
        role='owner' if owner_ok else 'reviewer'; token=secrets.token_urlsafe(40); csrf=secrets.token_urlsafe(32)
        # Every reviewer login is a separate, private sandbox identity.
        actor='owner' if role=='owner' else uid('reviewer-')
        store.execute('INSERT INTO auth VALUES (?,?,?,?,?)',(sha(token),actor,role,csrf,current+cfg.session_ttl))
        response=JSONResponse({'role':role,'csrf':csrf})
        response.set_cookie('osint_session',token,max_age=cfg.session_ttl,httponly=True,secure=cfg.production,samesite='lax',path='/')
        return response

    @app.post('/api/v1/auth/logout')
    def logout(request: Request):
        who=auth(request); store.execute('DELETE FROM auth WHERE id=?',(who['id'],))
        response=JSONResponse({'logged_out':True}); response.delete_cookie('osint_session',path='/'); return response

    @app.get('/api/v1/me')
    def me(request: Request):
        who=auth(request)
        return {'role':who['role'],'csrf':who['csrf'],'release':cfg.release,'ai_status':cfg.ai_status,'drive_status':drive.status,
                'reviewer_login_enabled':bool(cfg.reviewer_password),
                'limits':{'session_usd':cfg.session_budget,'day_usd':cfg.daily_budget,'call_usd':cfg.call_ceiling},
                'credentials_in_browser':False}

    @app.get('/api/v1/cases')
    def cases(request: Request):
        auth(request); return [json.loads((ROOT/'seeds/case.json').read_text())]

    @app.get('/api/v1/sessions')
    def sessions(request: Request):
        who=auth(request)
        return store.all('SELECT id,mode,cutoff,created_at FROM sessions WHERE actor=? ORDER BY created_at DESC LIMIT 30',(who['actor'],))

    @app.post('/api/v1/sessions',status_code=201)
    def start(payload: NewSession,request: Request):
        who=auth(request)
        original=session(store,payload.from_session_id,who['actor']) if payload.from_session_id else None
        if original and payload.mode!='RECORDED_REPLAY':
            raise AppError('SOURCE_SESSION_ONLY_FOR_REPLAY')
        identity=create_session(store,who['actor'],payload.mode,payload.cutoff,ROOT/'seeds')
        if payload.mode=='RECORDED_REPLAY':
            reference=original or session(store,identity,who['actor'])
            records=selected(store,reference)
            assessed=assessment_for_session(store,reference,records)
            if not original:
                current=dict(reference,mode='CURRENT_INVESTIGATION')
                assessed=assessment_for_session(store,current,records)
            audit=store.all('SELECT id,kind,detail,at FROM events WHERE session_id=? ORDER BY id',(reference['id'],))
            prior=store.one('SELECT audit FROM snapshots WHERE session_id=?',(reference['id'],))
            if prior: audit=json.loads(prior['audit'])+audit
            with store.connect(write=True) as db:
                db.execute('UPDATE sessions SET selection=?,exclusions=? WHERE id=?',
                    (dump({r['id']:r['version_id'] for r in records}),'[]',identity))
                db.execute('INSERT INTO snapshots VALUES (?,?,?,?)',(identity,dump(assessed),dump(audit),
                    dump({'original_session':reference['id'],'original_mode':reference['mode'],'original_cutoff':reference['cutoff']})))
        return {'id':identity}

    @app.get('/api/v1/sessions/{sid}/workspace')
    def workspace(sid: str,request: Request):
        who=auth(request); sess=session(store,sid,who['actor']); records=selected(store,sess)
        cards=[]
        for r in selected(store,sess,True):
            item={k:r.get(k) for k in ('id','display_title','publisher','publisher_date','publisher_timestamp','date_precision','source_type','version_id','representation','origin_group','acquired_at')}
            item['excluded']=r['id'] in sess['exclusions']
            last=store.one('SELECT state,metadata,at FROM captures WHERE source_id=? ORDER BY at DESC LIMIT 1',(r['id'],)) if sess['mode']=='CURRENT_INVESTIGATION' else None
            item['last_attempt']={'state':last['state'],'at':last['at'],'error':json.loads(last['metadata']).get('error')} if last else None
            cards.append(item)
        accepted=assessment_for_session(store,sess,records)
        total=store.one('SELECT COALESCE(SUM(COALESCE(actual,reservation)),0) AS total FROM budget WHERE session_id=?',(sid,))
        source_case=json.loads((ROOT/'seeds/case.json').read_text())
        case={k:source_case[k] for k in ('id','title','question','location') if k in source_case}
        case['mode']=sess['mode']
        if sess['mode']=='HISTORICAL_RECONSTRUCTION':
            case['location']=None  # Current visitor directions cannot leak into dated reconstruction.
        return {'session':{k:v for k,v in sess.items() if k!='actor'},'case':case,'sources':cards,'graph':graph(records),
                'assessment':accepted,'baseline':baseline(records),'budget_committed_usd':total['total'],
                'evidence_label':'REAL PUBLIC SOURCES; EACH CAPTURE / EXTRACT LABELLED',
                'events':store.all('SELECT id,job_id,kind,detail,at FROM events WHERE session_id=? ORDER BY id DESC LIMIT 30',(sid,))}

    @app.get('/api/v1/sessions/{sid}/versions/{version_id}')
    def version(sid: str,version_id: str,request: Request):
        who=auth(request); sess=session(store,sid,who['actor'])
        records=selected(store,sess)
        for r in records:
            if r['version_id']==version_id:
                return r
        raise AppError('VERSION_NOT_ADMITTED',404)

    @app.post('/api/v1/sessions/{sid}/refresh',status_code=202)
    def refresh_sources(sid: str,payload: Refresh,request: Request):
        who=auth(request,True); sess=session(store,sid,who['actor'])
        if sess['mode']!='CURRENT_INVESTIGATION':
            raise AppError('REFRESH_DISABLED_IN_REPLAY',409)
        ids=payload.source_ids
        rules=json.loads((ROOT/'seeds/sources.json').read_text())['sources']
        allowed={s['id'] for s in rules if s['enabled_for_live_fetch']}
        if len(ids)!=len(set(ids)) or not set(ids)<=allowed:
            raise AppError('SOURCE_NOT_ALLOWED')
        try:
            identity=store.new_job(who['actor'],sid,'refresh',{'source_ids':ids})
        except ValueError as exc:
            raise AppError(str(exc),429)
        return {'job_id':identity,'state':'queued'}

    @app.post('/api/v1/sessions/{sid}/exclusions')
    def exclude(sid: str,payload: Exclusion,request: Request):
        who=auth(request); sess=session(store,sid,who['actor'])
        if sess['mode']=='RECORDED_REPLAY':
            raise AppError('REPLAY_READ_ONLY',409)
        if payload.source_id not in sess['selection']:
            raise AppError('SOURCE_NOT_ALLOWED')
        with store.connect(write=True) as db:
            current=db.execute('SELECT exclusions FROM sessions WHERE id=?',(sid,)).fetchone()
            exclusions=set(json.loads(current['exclusions']))
            exclusions.add(payload.source_id) if payload.excluded else exclusions.discard(payload.source_id)
            db.execute('UPDATE sessions SET exclusions=?,scope_revision=scope_revision+1 WHERE id=?',(dump(sorted(exclusions)),sid))
        store.event('source_excluded' if payload.excluded else 'source_reinstated',{'source_id':payload.source_id,'shared_assessment_changed':False},sid)
        return {'excluded':sorted(exclusions)}

    @app.post('/api/v1/sessions/{sid}/questions',status_code=202)
    def ask(sid: str,payload: Question,request: Request):
        who=auth(request); sess=session(store,sid,who['actor'])
        if sess['mode']=='RECORDED_REPLAY':
            raise AppError('REPLAY_READ_ONLY',409)
        records=selected(store,sess)
        if not set(payload.source_ids)<=set(sess['selection']):
            raise AppError('SOURCE_NOT_ALLOWED')
        if not records or (payload.source_ids and not any(r['id'] in payload.source_ids for r in records)):
            raise AppError('NO_ADMITTED_EVIDENCE',409)
        if payload.use_ai and cfg.ai_status!='CONFIGURED_NOT_LIVE_VERIFIED':
            raise AppError(cfg.ai_status,409)
        if payload.challenge and not payload.use_ai:
            raise AppError('CHALLENGE_REQUIRES_AI')
        try:
            identity=store.new_job(who['actor'],sid,'question',{**payload.model_dump(),'scope_revision':sess['scope_revision']})
        except ValueError as exc:
            raise AppError(str(exc),429)
        return {'job_id':identity,'state':'queued'}

    def permitted_job(identity: str,who: dict) -> dict:
        row=store.one('SELECT * FROM jobs WHERE id=? AND actor=?',(identity,who['actor']))
        if not row:
            raise AppError('JOB_NOT_FOUND',404)
        sess=session(store,row['session_id'],who['actor'])
        result=json.loads(row['result']) if row['result'] else None
        if result and result.get('kind')=='answer':
            if not set(result['source_versions'])<={r['version_id'] for r in selected(store,sess)}:
                raise AppError('RESULT_OUTSIDE_CURRENT_SCOPE',409)
        row['result']=result
        return row

    @app.get('/api/v1/jobs/{identity}')
    def job_status(identity: str,request: Request):
        who=auth(request); row=permitted_job(identity,who)
        return {k:row[k] for k in ('id','session_id','kind','state','result','error','created_at','updated_at')}

    @app.get('/api/v1/sessions/{sid}/jobs')
    def session_jobs(sid: str, request: Request):
        who=auth(request); session(store,sid,who['actor'])
        return store.all('SELECT id,kind,state,error,created_at FROM jobs WHERE session_id=? AND actor=? ORDER BY created_at DESC LIMIT 30',(sid,who['actor']))

    @app.get('/api/v1/jobs/{identity}/events')
    def job_events(identity: str,request: Request):
        who=auth(request); permitted_job(identity,who)
        return store.all('SELECT id,kind,detail,at FROM events WHERE job_id=? ORDER BY id',(identity,))

    @app.post('/api/v1/sessions/{sid}/review')
    def review(sid: str,payload: Review,request: Request):
        who=auth(request,True); sess=session(store,sid,who['actor'])
        if sess['mode']!='CURRENT_INVESTIGATION':
            raise AppError('REPLAY_READ_ONLY',409)
        row=permitted_job(payload.job_id,who)
        if row['session_id']!=sid or row['state']!='completed' or not row['result'] or row['result'].get('kind')!='answer':
            raise AppError('NO_REVIEWABLE_DRAFT',409)
        result=row['result']
        if result['scope_revision']!=sess['scope_revision']:
            raise AppError('STALE_REVIEW_CONFLICT',409)
        with store.connect(write=True) as db:
            scope=db.execute('SELECT scope_revision FROM sessions WHERE id=?',(sid,)).fetchone()
            if scope['scope_revision']!=result['scope_revision']:
                raise AppError('STALE_REVIEW_CONFLICT',409)
            accepted=db.execute("SELECT revision FROM assessments WHERE case_id='SEA-CHANGE'").fetchone()
            if accepted['revision']!=payload.expected_revision:
                raise AppError('STALE_REVIEW_CONFLICT',409)
            body={'status':'HUMAN_REVIEWED','source_versions':result['source_versions'],
                  'statements':result['answer']['statements'],'rationale':payload.rationale,
                  'reviewed_from_job':payload.job_id,'inference':result['inference'],'support_checked':True}
            db.execute("UPDATE assessments SET revision=revision+1,body=?,stale=0,at=? WHERE case_id='SEA-CHANGE'",(dump(body),now()))
        store.event('assessment_accepted',{'revision':payload.expected_revision+1,'job_id':payload.job_id},sid)
        return {'revision':payload.expected_revision+1,'status':'HUMAN_REVIEWED'}

    @app.post('/api/v1/sessions/{sid}/exports',status_code=201)
    def export(sid: str,request: Request):
        who=auth(request); session(store,sid,who['actor']); return make_export(store,who['actor'],sid)

    def permitted_export(identity: str,who: dict) -> dict:
        row=store.one('SELECT * FROM exports WHERE id=? AND actor=?',(identity,who['actor']))
        if not row:
            raise AppError('EXPORT_NOT_FOUND',404)
        return row

    @app.get('/api/v1/exports/{identity}')
    def export_status(identity: str,request: Request):
        row=permitted_export(identity,auth(request))
        return {k:row[k] for k in ('id','state','sha256','size','remote_id','manifest_id','error','created_at','verified_at')}

    @app.get('/api/v1/exports/{identity}/download')
    def download(identity: str,request: Request):
        row=permitted_export(identity,auth(request)); path=Path(row['path'])
        if not path.exists() or sha(path.read_bytes())!=row['sha256']:
            raise AppError('LOCAL_ARCHIVE_HASH_MISMATCH',409)
        return FileResponse(path,media_type='application/zip',filename=row['id']+'.zip')

    @app.post('/api/v1/exports/{identity}/sync',status_code=202)
    def sync(identity: str,request: Request):
        who=auth(request,True); row=permitted_export(identity,who)
        if drive.status=='DRIVE_NOT_CONNECTED':
            raise AppError('DRIVE_NOT_CONNECTED',409)
        try:
            jid=store.new_job(who['actor'],row['session_id'],'drive_sync',{'export_id':identity})
        except ValueError as exc:
            raise AppError(str(exc),429)
        return {'job_id':jid,'state':'queued'}

    @app.post('/api/v1/owner/drive/connect')
    def drive_connect(request: Request):
        who=auth(request,True); return {'authorization_url':drive.begin(who['actor'])}

    @app.get('/api/v1/owner/drive/callback')
    def drive_callback(request: Request,state: str,code: str):
        who=auth(request,True); drive.callback(who['actor'],state,code); return RedirectResponse('/?drive=connected',status_code=303)

    @app.post('/api/v1/training/sensitivity')
    def training(payload: Sensitivity,request: Request):
        auth(request)
        first=[Factor('E1','fictional-origin',payload.initial_lr,'synthetic-v1')]
        replacement=replace_factor(first,'E1',Factor('E1','fictional-origin',payload.replacement_lr,'synthetic-v2'))
        return {'namespace':'synthetic_training','label':'ILLUSTRATIVE ASSUMPTIONS; NOT A SEA CHANGE FORECAST',
                'prior':payload.prior,'initial':posterior(payload.prior,first),'duplicate':posterior(payload.prior,first),
                'replacement':posterior(payload.prior,replacement),'operation':'Replace the old likelihood factor, never multiply both versions.'}

    app.mount('/',StaticFiles(directory=ROOT/'frontend/public',html=True),name='frontend')
    return app

app=create_app()
