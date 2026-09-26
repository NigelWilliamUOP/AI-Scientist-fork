"""Application tests use isolated stores and clearly marked transport fixtures.

A mock response is never evidence that a live external integration works.
"""
import io
import json
import math
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs,urlparse
import httpx
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from osint.main import create_app
from osint.settings import Settings,ROOT
from osint.store import Store,sha,dump,now
from osint.logic import AppError,create_session,selected,session,baseline,graph,assessment_for_session,parse_notice
from osint.archive import make_export,verify_bundle,restore_bundle,sync_export
from osint.collector import refresh
from osint.drive import Drive,SCOPE
from osint.model import approved_price,inference,answer_job
from osint_core.grounding import validate_answer

ORIGIN='http://127.0.0.1:8000'
PASSWORD='test-owner-password-long'
REVIEWER='test-reviewer-password-long'

@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path);s.seed(ROOT/'seeds');return s

@pytest.fixture
def client(tmp_path):
    cfg=Settings(data_dir=tmp_path,owner_password=PASSWORD,reviewer_password=REVIEWER,start_worker=True)
    app=create_app(cfg)
    with TestClient(app,base_url=ORIGIN) as c:
        c.headers['origin']=ORIGIN
        yield c

def login(c,password=PASSWORD):
    r=c.post('/api/v1/auth/login',json={'password':password});assert r.status_code==200,r.text
    c.headers['x-csrf-token']=r.json()['csrf'];return r

def start(c,**kwargs):
    r=c.post('/api/v1/sessions',json=kwargs);assert r.status_code==201,r.text
    return r.json()['id']

def ws(c,sid):
    r=c.get(f'/api/v1/sessions/{sid}/workspace');assert r.status_code==200,r.text
    return r.json()

def completed(c,jid):
    for _ in range(150):
        r=c.get('/api/v1/jobs/'+jid);assert r.status_code==200,r.text
        result=r.json()
        if result['state'] in ('completed','failed'): return result
        time.sleep(.025)
    pytest.fail('Worker did not complete local fixture job')

def draft(c,sid):
    r=c.post(f'/api/v1/sessions/{sid}/questions',json={'question':'What do these records establish?','use_ai':False});assert r.status_code==202,r.text
    j=completed(c,r.json()['job_id']);assert j['state']=='completed',j
    return j

def accept(c,sid,jid,revision=0):
    return c.post(f'/api/v1/sessions/{sid}/review',json={'job_id':jid,'expected_revision':revision,'rationale':'Inspected the quoted records and checked the wording.','support_checked':True})

def test_health_discloses_no_configuration(client):
    assert set(client.get('/api/v1/health').json())=={'status','version','release'}
    assert client.get('/api/v1/cases').status_code==401

def test_login_cookie_and_headers(client):
    r=login(client);cookie=r.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    assert "script-src 'self'" in r.headers['content-security-policy']
    assert r.headers['x-frame-options']=='DENY'
    me=client.get('/api/v1/me').json();assert not me['credentials_in_browser']
    assert me['ai_status']=='AI_NOT_CONFIGURED' and me['drive_status']=='DRIVE_NOT_CONNECTED'

def test_bad_login_rate_limit(client):
    for _ in range(8):assert client.post('/api/v1/auth/login',json={'password':'wrong'}).status_code==401
    assert client.post('/api/v1/auth/login',json={'password':PASSWORD}).status_code==429

@pytest.mark.parametrize('origin',['https://attacker.test','null',''])
def test_cross_origin_mutations_denied(client,origin):
    login(client);r=client.post('/api/v1/sessions',json={},headers={'origin':origin})
    assert r.status_code==403

def test_csrf_and_extra_fields(client):
    login(client)
    assert client.post('/api/v1/sessions',json={},headers={'x-csrf-token':'wrong'}).status_code==403
    assert client.post('/api/v1/sessions',json={'unexpected':'x'}).status_code==422

def test_payload_size_and_host(client):
    assert client.post('/api/v1/auth/login',content='x'*65537).status_code==413
    assert client.get('/api/v1/health',headers={'host':'attacker.test'}).status_code==400

def test_expired_auth(client):
    login(client);client.app.state.store.execute('UPDATE auth SET expires=0')
    assert client.get('/api/v1/me').status_code==401

@pytest.mark.parametrize('kwargs',[
    {'production':True,'public_url':'http://example.test','owner_password':PASSWORD},
    {'production':True,'public_url':'https://example.test','owner_password':'short'},
    {'public_url':'http://example.test'},
    {'reviewer_password':PASSWORD,'owner_password':PASSWORD},
    {'session_budget':float('nan')},
    {'public_url':'https://example.test/path'},
])
def test_unsafe_configuration_rejected(tmp_path,kwargs):
    with pytest.raises(ValueError):Settings(data_dir=tmp_path,**kwargs)

def test_secure_production_cookie(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,production=True,public_url='https://app.example.test',owner_password=PASSWORD,start_worker=False))
    with TestClient(app,base_url='https://app.example.test') as c:
        r=c.post('/api/v1/auth/login',json={'password':PASSWORD},headers={'origin':'https://app.example.test'})
        assert 'Secure' in r.headers['set-cookie'] and 'strict-transport-security' in r.headers

def test_real_seed_integrity_and_safe_metadata(client):
    login(client);sid=start(client);w=ws(client,sid)
    assert len(w['sources'])==5 and len(w['graph']['nodes'])==9
    assert all(s['representation']=='curated_web_extract' for s in w['sources'])
    assert w['case']['location']['lat']==50.811823
    for s in w['sources']:
        r=client.get(f"/api/v1/sessions/{sid}/versions/{s['version_id']}").json()
        assert not r['acquired_at'] and not r['upstream_body_sha256']
        assert all(sha(p['text'])==p['sha256'] for p in r['segments'])

@pytest.mark.parametrize('cutoff,count,correction',[
 ('2024-03-26T00:00:00Z',0,False),('2024-03-27T00:00:00Z',1,False),
 ('2024-10-05T15:22:00Z',3,False),('2024-10-05T15:26:00Z',4,True)])
def test_historical_no_future_leak(client,cutoff,count,correction):
    login(client);sid=start(client,mode='HISTORICAL_RECONSTRUCTION',cutoff=cutoff);w=ws(client,sid)
    assert len(w['sources'])==count
    assert ('FTS-CORRECTION' in {s['id'] for s in w['sources']})==correction
    assert 'PORT-STATEMENT' not in dump(w) and w['case']['location'] is None
    assert w['assessment']['revision']==0
    assert client.post(f'/api/v1/sessions/{sid}/refresh',json={'source_ids':['FTS-PIN']}).status_code==409
    if not correction:
        assert not any(e['kind']=='title_correction' for e in w['graph']['edges'])

@pytest.mark.parametrize('payload',[{'mode':'BOGUS'},{'mode':'HISTORICAL_RECONSTRUCTION'},{'mode':'HISTORICAL_RECONSTRUCTION','cutoff':'nonsense'},{'cutoff':'2024-01-01T00:00:00Z'}])
def test_invalid_modes(client,payload):
    login(client);assert client.post('/api/v1/sessions',json=payload).status_code in (400,422)

def test_reviewer_sandbox_and_owner_only_mutations(client):
    login(client);owner_session=start(client)
    client.post('/api/v1/auth/logout',json={})
    login(client,REVIEWER);review_session=start(client)
    assert client.get(f'/api/v1/sessions/{owner_session}/workspace').status_code==404
    assert client.post(f'/api/v1/sessions/{review_session}/refresh',json={'source_ids':['FTS-PIN']}).status_code==403
    assert client.post('/api/v1/owner/drive/connect',json={}).status_code==403
    client.post('/api/v1/auth/logout',json={});login(client,REVIEWER)
    assert client.get(f'/api/v1/sessions/{review_session}/workspace').status_code==404

@pytest.mark.parametrize('source_id',['https://127.0.0.1/','PORT-STATEMENT','not-a-source'])
def test_collector_allowlist(client,source_id):
    login(client);sid=start(client)
    assert client.post(f'/api/v1/sessions/{sid}/refresh',json={'source_ids':[source_id]}).status_code==400

def test_unconfigured_services_fail_without_fakes(client):
    login(client);sid=start(client)
    assert client.post(f'/api/v1/sessions/{sid}/questions',json={'question':'test','use_ai':True}).json()['error']=='AI_NOT_CONFIGURED'
    assert client.post('/api/v1/owner/drive/connect',json={}).json()['error']=='GOOGLE_OAUTH_APP_NOT_CONFIGURED'
    assert client.app.state.store.all('SELECT * FROM model_runs')==[]

def test_template_draft_approval_and_race_guard(client):
    login(client);sid=start(client);j=draft(client,sid)
    assert j['result']['inference'] is False and j['result']['runs']==[]
    assert accept(client,sid,j['id']).status_code==200
    assert accept(client,sid,j['id']).status_code==409
    w=ws(client,sid);assert w['assessment']['revision']==1
    assert w['assessment']['body']['status']=='HUMAN_REVIEWED'

def test_exclusion_removes_citations_not_shared_record(client):
    login(client);sid=start(client);j=draft(client,sid);accept(client,sid,j['id'])
    r=client.post(f'/api/v1/sessions/{sid}/exclusions',json={'source_id':'CF-AWARD','excluded':True});assert r.status_code==200
    w=ws(client,sid);assert all('£0' not in s['text'] for s in w['baseline']['statements'])
    assert all(n['id']!='CF-AWARD' for n in w['graph']['nodes'])
    assert client.get('/api/v1/jobs/'+j['id']).status_code==409
    assert client.get(f'/api/v1/sessions/{sid}/versions/CF-AWARD-seed-extract-v1').status_code==404
    assert client.app.state.store.one('SELECT revision FROM assessments')['revision']==1
    assert ws(client,start(client))['assessment']['body']['status']=='HUMAN_REVIEWED'
    client.post(f'/api/v1/sessions/{sid}/exclusions',json={'source_id':'CF-AWARD','excluded':False})
    assert accept(client,sid,j['id'],1).status_code==409 # scope changed, even after reinstating

def test_empty_scope_and_training_separation(client):
    login(client);sid=start(client)
    for source in ws(client,sid)['sources']:
        client.post(f'/api/v1/sessions/{sid}/exclusions',json={'source_id':source['id'],'excluded':True})
    w=ws(client,sid);assert w['baseline']['statements']==[] and w['graph']['nodes']==[]
    assert client.post(f'/api/v1/sessions/{sid}/questions',json={'question':'hi'}).status_code==409
    r=client.post('/api/v1/training/sensitivity',json={'prior':.5,'initial_lr':3,'replacement_lr':.5}).json()
    assert r['namespace']=='synthetic_training' and r['initial']==r['duplicate']==.75
    assert r['replacement']==pytest.approx(1/3)
    assert ws(client,sid)['baseline']==w['baseline']

@pytest.mark.parametrize('data',[{'prior':0,'initial_lr':3,'replacement_lr':.5},{'prior':.5,'initial_lr':-1,'replacement_lr':.5},{'prior':1,'initial_lr':3,'replacement_lr':.5}])
def test_invalid_sensitivity(client,data):
    login(client);assert client.post('/api/v1/training/sensitivity',json=data).status_code==422

def test_frozen_scope_and_review_snapshot(client):
    login(client);sid=start(client);j=draft(client,sid);accept(client,sid,j['id'])
    frozen=start(client,mode='RECORDED_REPLAY',from_session_id=sid)
    assert ws(client,frozen)['assessment']['revision']==1
    client.app.state.store.execute("UPDATE assessments SET revision=8,body=?",(dump({'status':'later','source_versions':[]}),))
    assert ws(client,frozen)['assessment']['revision']==1
    assert client.post(f'/api/v1/sessions/{frozen}/questions',json={'question':'x'}).status_code==409
    assert client.post(f'/api/v1/sessions/{frozen}/exclusions',json={'source_id':'CF-AWARD','excluded':True}).status_code==409

def test_export_restore_and_integrity(client,tmp_path):
    login(client);sid=start(client);j=draft(client,sid);accept(client,sid,j['id'])
    exported=client.post(f'/api/v1/sessions/{sid}/exports',json={}).json();assert exported['state']=='local_only'
    content=client.get('/api/v1/exports/'+exported['id']+'/download').content
    assert sha(content)==exported['sha256']
    files=verify_bundle(content)
    assert PASSWORD.encode() not in content and b'csrf' not in files['session.json']
    assert b'actor' not in files['session.json'] and b'TEMPLATE-BASED' in files['briefing.md']
    fresh=Store(tmp_path/'restored');fresh.seed(ROOT/'seeds');new=restore_bundle(fresh,content,'owner')
    sess=session(fresh,new,'owner');records=selected(fresh,sess)
    assert len(records)==5 and sess['mode']=='RECORDED_REPLAY'
    assert assessment_for_session(fresh,sess,records)['revision']==1
    assert json.loads(fresh.one('SELECT audit FROM snapshots')['audit'])
    assert fresh.one('SELECT revision FROM assessments')['revision']==0 # restore never overwrites shared acceptance
    newer=make_export(fresh,'owner',new);newfiles=verify_bundle(Path(fresh.one('SELECT path FROM exports WHERE id=?',(newer['id'],))['path']).read_bytes())
    assert 'prior-audit.json' in newfiles
    # Corrupt a manifest-protected file while retaining the manifest.
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        for name,data in files.items():z.writestr(name,data+b'corruption' if name=='briefing.md' else data)
    with pytest.raises(AppError,match='ARCHIVE_HASH_MISMATCH'):verify_bundle(buffer.getvalue())
    assert client.post('/api/v1/exports/'+exported['id']+'/sync',json={}).json()['error']=='DRIVE_NOT_CONNECTED'

@pytest.mark.parametrize('name',['../escape','/absolute','evil\\path'])
def test_zip_traversal_denied(name):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr(name,'bad')
    with pytest.raises(AppError):verify_bundle(b.getvalue())

def test_restart_retains_sessions_jobs_and_approvals(tmp_path):
    cfg=lambda: Settings(data_dir=tmp_path,owner_password=PASSWORD,start_worker=True)
    with TestClient(create_app(cfg()),base_url=ORIGIN) as c:
        c.headers['origin']=ORIGIN;login(c);sid=start(c);j=draft(c,sid);accept(c,sid,j['id'])
    with TestClient(create_app(cfg()),base_url=ORIGIN) as c:
        c.headers['origin']=ORIGIN;login(c)
        assert ws(c,sid)['assessment']['revision']==1
        assert c.get('/api/v1/jobs/'+j['id']).json()['state']=='completed'
        assert c.get(f'/api/v1/sessions/{sid}/jobs').json()[0]['id']==j['id']

def test_atomic_budget_reservations(store):
    def attempt(i):
        try:store.reserve('run'+str(i),'owner','s','j',.6,1,1);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(attempt,range(4)))
    assert sum(result)==1
    assert store.one('SELECT SUM(reservation) AS total FROM budget')['total']==.6

@pytest.mark.parametrize('amount',[float('nan'),float('inf'),-1,1001])
def test_invalid_budget_reservation(store,amount):
    with pytest.raises(ValueError):store.reserve('bad','owner','s','j',amount,5,20)

def fixture_html(record,extra=''):
    return ('<html><header>dynamic cookie '+extra+'</header><main>'+''.join('<p>'+s['text']+'</p>' for s in record['segments'])+'</main></html>').encode()

def test_collector_fixture_capture_change_and_failure(store,monkeypatch):
    """Synthetic HTML assembled from real extracts; NOT a live capture test."""
    sid=create_session(store,'owner','CURRENT_INVESTIGATION',None,ROOT/'seeds')
    seed=store.version('FTS-TENDER-seed-extract-v1');raw=[fixture_html(seed)]
    def fake_capture(rule,path):
        body=raw[0];name=sha(body)+'.html';(path/name).write_bytes(body)
        return {'raw_file':name,'http_status':200,'upstream_body_sha256':sha(body),'acquired_at':now()}
    monkeypatch.setattr('osint.collector.capture',fake_capture)
    job={'id':'fixture-job','actor':'owner','session_id':sid,'payload':dump({'source_ids':['FTS-TENDER']})}
    first=refresh(store,job,ROOT/'seeds');assert first['sources'][0]['state']=='historical_record_captured'
    old=selected(store,session(store,sid,'owner'))
    store.execute('UPDATE assessments SET body=?',(dump({'source_versions':[r['version_id'] for r in old]}),))
    raw[0]=fixture_html(seed,'new banner');second=refresh(store,job,ROOT/'seeds')
    assert second['sources'][0]['state']=='unchanged'
    assert first['sources'][0]['version_id']==second['sources'][0]['version_id']
    raw[0]=fixture_html(seed).replace(b'1st April 2025',b'1st June 2025')
    changed=refresh(store,job,ROOT/'seeds');assert changed['sources'][0]['state']=='selected_evidence_changed'
    assert store.one('SELECT stale FROM assessments')['stale']==1
    assert changed['sources'][0]['version_id']!=first['sources'][0]['version_id']
    current=selected(store,session(store,sid,'owner'));brief=baseline(current)
    assert not any('target in the tender' in s['text'] for s in brief['statements'])
    raw[0]=b'<html><main>different layout</main></html>'
    failed=refresh(store,job,ROOT/'seeds');assert failed['sources'][0]['error']=='PARSER_FAILED'
    assert len(list((store.root/'captures').glob('*.html')))==4
    assert [r['version_id'] for r in selected(store,session(store,sid,'owner'))]==[r['version_id'] for r in current]

def test_network_failure_keeps_prior(store,monkeypatch):
    sid=create_session(store,'owner','CURRENT_INVESTIGATION',None,ROOT/'seeds')
    def fail(*args):raise OSError('unavailable')
    monkeypatch.setattr('osint.collector.capture',fail)
    job={'id':'fixture','actor':'owner','session_id':sid,'payload':dump({'source_ids':['FTS-PIN']})}
    result=refresh(store,job,ROOT/'seeds');assert result['success_count']==0
    assert len(selected(store,session(store,sid,'owner')))==5
    assert store.one('SELECT revision,stale FROM assessments')=={'revision':0,'stale':0}

def test_body_change_outside_segments_gets_new_version(store,monkeypatch):
    sid=create_session(store,'owner','CURRENT_INVESTIGATION',None,ROOT/'seeds');seed=store.version('FTS-TENDER-seed-extract-v1')
    raw=[fixture_html(seed)]
    def cap(rule,path):
        body=raw[0];name=sha(body)+'.html';(path/name).write_bytes(body)
        return {'raw_file':name,'http_status':200,'upstream_body_sha256':sha(body),'acquired_at':now()}
    monkeypatch.setattr('osint.collector.capture',cap);j={'id':'j','actor':'owner','session_id':sid,'payload':dump({'source_ids':['FTS-TENDER']})}
    a=refresh(store,j,ROOT/'seeds')['sources'][0]
    raw[0]=raw[0].replace(b'</main>',b'<p>A new substantive passage outside the selected segments.</p></main>')
    b=refresh(store,j,ROOT/'seeds')['sources'][0]
    assert b['state']=='document_changed_review_required' and a['version_id']!=b['version_id']

@pytest.mark.parametrize('bad',['no main','<main>tiny</main>','<main><script>'+('x'*100)+'</script></main>'])
def test_parser_fail_closed(store,bad):
    with pytest.raises(AppError):parse_notice(bad.encode(),store.version('FTS-TENDER-seed-extract-v1'))

def test_quote_checks_do_not_claim_entailment(store):
    records=[store.version('CF-AWARD-seed-extract-v1')];answer=baseline(records)
    checks=validate_answer(answer,{r['version_id']:r for r in records},{r['version_id'] for r in records})
    assert checks and all(not x.semantic_support_reviewed for x in checks)
    answer['statements'][0]['citations'][0]['quote']='invented sentence'
    with pytest.raises(ValueError):validate_answer(answer,{r['version_id']:r for r in records},{r['version_id'] for r in records})

@pytest.mark.parametrize('metadata',[
 {},{'data':{'endpoints':[]}},
 {'data':{'endpoints':[{'provider_name':'Approved','supported_parameters':[],'pricing':{'prompt':'0','completion':'0'}}]}},
 {'data':{'endpoints':[{'provider_name':'Other','supported_parameters':['structured_outputs'],'pricing':{'prompt':'0','completion':'0'}}]}},
 {'data':{'endpoints':[{'provider_name':'Approved','supported_parameters':['structured_outputs'],'pricing':{'prompt':'NaN','completion':'0'}}]}},
 {'data':{'endpoints':[{'provider_name':'Approved','supported_parameters':['structured_outputs'],'pricing':{'prompt':'0','completion':'0','unknown':'1'}}]}},
])
def test_unknown_or_unsupported_model_fails_closed(metadata):
    with pytest.raises(AppError):approved_price(metadata,['Approved'],{'max_tokens':100})

def test_price_bound_is_numeric():
    meta={'data':{'endpoints':[{'provider_name':'Approved','supported_parameters':['structured_outputs'],'pricing':{'prompt':'.000001','completion':'.000002'}}]}}
    assert 0<approved_price(meta,['Approved'],{'max_tokens':1600})<.25

def test_mock_inference_and_invalid_quote(store,monkeypatch):
    """Mock provider test, not a real model run."""
    cfg=Settings(data_dir=store.root,owner_password=PASSWORD,ai_provider='openrouter',ai_key='TEST-NOT-A-REAL-KEY',ai_model='vendor/test-model',ai_providers='Approved',allow_paid=True)
    sid=create_session(store,'owner','CURRENT_INVESTIGATION',None,ROOT/'seeds')
    records=selected(store,session(store,sid,'owner'));answer=baseline(records)
    job={'id':'mock-job','actor':'owner','session_id':sid}
    meta={'data':{'endpoints':[{'provider_name':'Approved','supported_parameters':['structured_outputs'],'pricing':{'prompt':'0.000001','completion':'0.000001'}}]}}
    def response(client,method,url,**kwargs):
        if method=='GET':return meta,{'http_status':200}
        assert kwargs['headers']['Authorization'].endswith('TEST-NOT-A-REAL-KEY')
        assert kwargs['json']['provider']['require_parameters'] is True
        return {'id':'mock-response','model':'vendor/test-model','provider':'Approved','usage':{'cost':.002},'choices':[{'message':{'content':dump(answer)}}]}, {'http_status':200}
    monkeypatch.setattr('osint.model.bounded_json',response)
    r=inference(store,cfg,job,records,'Test question','answer')
    assert r['state']=='draft_quote_checked' and r['cost']==.002
    assert r['semantic_support_reviewed'] is False
    assert 'TEST-NOT-A-REAL-KEY' not in store.one('SELECT body FROM model_runs')['body']
    answer['statements'][0]['citations'][0]['quote']='not a real quotation'
    with pytest.raises(AppError):inference(store,cfg,job,records,'Test question','answer')
    assert len(store.all('SELECT * FROM model_runs'))==2
    assert sum(x['actual'] for x in store.all('SELECT actual FROM budget'))==.004

def test_drive_token_encryption_state_and_wrong_actor(store):
    cfg=Settings(data_dir=store.root,google_client_id='fixture-id',google_client_secret='fixture-secret',encryption_key=Fernet.generate_key().decode())
    d=Drive(cfg,store);assert d.status=='DRIVE_NOT_CONNECTED'
    token={'access_token':'fixture-access','refresh_token':'fixture-refresh','folder_id':'fixture-folder-id','expires_at':time.time()+3600}
    d.save(token);assert b'fixture-access' not in d.path.read_bytes() and d.load()==token
    assert d.path.stat().st_mode&0o777==0o600
    params=parse_qs(urlparse(d.begin('owner')).query)
    assert params['scope']==[SCOPE] and params['code_challenge_method']==['S256']
    state=params['state'][0]
    with pytest.raises(AppError,match='OAUTH_STATE_INVALID'):d.callback('other',state,'fake')
    store.execute('UPDATE oauth_states SET expires=0')
    with pytest.raises(AppError,match='OAUTH_STATE_INVALID'):d.callback('owner',state,'fake')

def test_drive_mock_upload_readback_and_dedup(store,monkeypatch):
    cfg=Settings(data_dir=store.root,google_client_id='fixture-id',google_client_secret='fixture-secret',encryption_key=Fernet.generate_key().decode())
    d=Drive(cfg,store);d.save({'access_token':'fixture-token','folder_id':'folder-id-123456','expires_at':time.time()+3600})
    content=b'fixture audit bytes';state={'uploaded':False,'uploads':0,'bad':False}
    def handler(request):
        assert request.headers['authorization']=='Bearer fixture-token'
        if request.method=='POST':
            state['uploads']+=1;state['uploaded']=True;assert content in request.content
            return httpx.Response(200,json={'id':'object-id-12345'})
        if 'alt=media' in str(request.url):return httpx.Response(200,content=b'WRONG' if state['bad'] else content)
        return httpx.Response(200,json={'files':[{'id':'object-id-12345'}] if state['uploaded'] else []})
    original=httpx.Client
    monkeypatch.setattr('osint.drive.httpx.Client',lambda **kwargs:original(transport=httpx.MockTransport(handler)))
    a=d.put_verified(content,'audit.zip','export');b=d.put_verified(content,'audit.zip','export')
    assert a==b and state['uploads']==1
    state['bad']=True
    with pytest.raises(AppError,match='ARCHIVE_HASH_MISMATCH'):d.put_verified(content,'audit.zip','export')

def test_drive_manifest_last_and_failure_pending(store):
    sid=create_session(store,'owner','CURRENT_INVESTIGATION',None,ROOT/'seeds');e=make_export(store,'owner',sid)
    job={'id':'sync-fixture','actor':'owner','session_id':sid,'payload':dump({'export_id':e['id']})}
    class FakeDrive:
        status='CONNECTED_NOT_LIVE_VERIFIED'
        def __init__(self):self.kinds=[];self.fail=True
        def put_verified(self,content,name,kind):
            self.kinds.append(kind)
            if self.fail:raise AppError('ARCHIVE_HASH_MISMATCH')
            return {'file_id':'fixture-file-'+kind,'sha256':sha(content),'size':len(content)}
    d=FakeDrive()
    with pytest.raises(AppError):sync_export(store,d,job)
    assert d.kinds==['export'] and store.one('SELECT state FROM exports')['state']=='pending'
    d.fail=False;sync_export(store,d,job)
    assert d.kinds==['export','export','manifest'] and store.one('SELECT state FROM exports')['state']=='verified'
    sync_export(store,d,job);assert len(d.kinds)==3
