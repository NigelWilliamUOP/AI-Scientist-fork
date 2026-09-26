from __future__ import annotations
from dataclasses import asdict
import json
import math
import time
from urllib.parse import quote
import httpx
from osint_core.grounding import validate_answer
from osint_core.provider import answer_request, ENDPOINT
from .logic import AppError, baseline, selected, session
from .settings import ROOT, Settings
from .store import Store, dump, now, sha, uid

MAX_RESPONSE=150000

def bounded_json(client: httpx.Client, method: str, url: str, **kwargs) -> tuple[dict,dict]:
    with client.stream(method,url,**kwargs) as r:
        if r.status_code!=200:
            raise AppError('PROVIDER_RATE_LIMIT' if r.status_code==429 else 'PROVIDER_REQUEST_FAILED',502)
        chunks=[]; size=0
        for chunk in r.iter_bytes():
            size+=len(chunk)
            if size>MAX_RESPONSE:
                raise AppError('PROVIDER_RESPONSE_TOO_LARGE',502)
            chunks.append(chunk)
        try:
            return json.loads(b''.join(chunks)),{'http_status':r.status_code,'request_id':r.headers.get('x-request-id')}
        except (json.JSONDecodeError,UnicodeDecodeError):
            raise AppError('OUTPUT_SCHEMA_INVALID',502)


def approved_price(metadata: dict, providers: list[str], payload: dict) -> float:
    """Conservative UTF-8-byte input bound, worst permitted endpoint price.

    All non-zero unsupported charge classes fail closed. Provider-side credit
    limits remain necessary: this is not a guarantee against billing mistakes.
    """
    endpoints=metadata.get('data',{}).get('endpoints',[])
    prices=[]
    for ep in endpoints:
        identifiers={ep.get('provider_name'),ep.get('name'),ep.get('tag')}
        if not identifiers.intersection(providers):
            continue
        if 'structured_outputs' not in ep.get('supported_parameters',[]):
            continue
        p=ep.get('pricing',{})
        if not all(k in p for k in ('prompt','completion')):
            continue
        try:
            numbers={k:float(v) for k,v in p.items() if v is not None}
            if any(not math.isfinite(v) or v<0 for v in numbers.values()):
                continue
            unsupported=set(numbers)-{'prompt','completion','request','input_cache_read','input_cache_write','internal_reasoning'}
            if any(numbers[k]>0 for k in unsupported):
                continue
            # A cache write may be priced above plain input; use the greater rate.
            inp=max(numbers['prompt'],numbers.get('input_cache_write',0),numbers.get('input_cache_read',0))
            out=max(numbers['completion'],numbers.get('internal_reasoning',0))
            input_bound=len(dump(payload).encode())+1024
            prices.append((input_bound*inp+payload['max_tokens']*out+numbers.get('request',0))*1.10)
        except (ValueError,TypeError):
            continue
    if not prices:
        raise AppError('MODEL_UNSUPPORTED_OR_PRICING_UNKNOWN',409)
    return max(prices)


def inference(store: Store, settings: Settings, job: dict, records: list[dict], question: str, phase: str) -> dict:
    if settings.ai_status!='CONFIGURED_NOT_LIVE_VERIFIED':
        raise AppError(settings.ai_status,409)
    sess=session(store,job['session_id'],job['actor'])
    providers=[x.strip() for x in settings.ai_providers.split(',') if x.strip()]
    system=(ROOT/'seeds'/('challenge.txt' if phase=='challenge' else 'answer.txt')).read_text()
    payload=answer_request(model=settings.ai_model,system_prompt=system,question=question,
        evidence=[{k:v for k,v in r.items() if k in ('id','version_id','publisher_date','publisher_timestamp','date_precision','segments','representation','origin_group','coverage')} for r in records],
        schema=json.loads((ROOT/'seeds/answer.schema.json').read_text()),mode=sess['mode'],cutoff=sess['cutoff'],approved_providers=tuple(providers))
    model_path='/'.join(quote(x,safe='') for x in settings.ai_model.split('/'))
    run_id=uid('run-'); started=now(); t0=time.monotonic()
    record={'id':run_id,'phase':phase,'inference':True,'state':'preflight','started_at':started,
            'requested_model':settings.ai_model,'evidence_versions':[r['version_id'] for r in records],
            'evidence_hash':sha(dump(records)),'prompt_hash':sha(dump(payload)),
            'mode':sess['mode'],'cutoff':sess['cutoff'],'cost':None,'cost_status':'not_submitted',
            'semantic_support_reviewed':False}
    submitted=False
    try:
        with httpx.Client(timeout=httpx.Timeout(50,connect=10),follow_redirects=False,trust_env=False) as client:
            meta,_=bounded_json(client,'GET','https://openrouter.ai/api/v1/models/'+model_path+'/endpoints')
            reserve=approved_price(meta,providers,payload)
            if reserve>settings.call_ceiling:
                raise AppError('CALL_CEILING_EXCEEDED',409)
            store.reserve(run_id,job['actor'],job['session_id'],job['id'],reserve,settings.session_budget,settings.daily_budget)
            record['reservation_usd']=reserve
            store.event('drafting' if phase=='answer' else 'challenging',{'run_id':run_id,'phase':phase},job['session_id'],job['id'])
            submitted=True; record['cost_status']='unknown_reserved'
            response,http_meta=bounded_json(client,'POST',ENDPOINT,
                headers={'Authorization':'Bearer '+settings.ai_key,'Content-Type':'application/json'},json=payload)
        record.update({'request_id':response.get('id') or http_meta.get('request_id'),
                       'returned_model':response.get('model'),'returned_provider':response.get('provider'),
                       'usage':response.get('usage',{}),'http_status':http_meta['http_status']})
        cost=response.get('usage',{}).get('cost')
        if isinstance(cost,(int,float)) and not isinstance(cost,bool) and math.isfinite(cost) and cost>=0:
            record.update({'cost':cost,'cost_status':'reported_by_provider'})
            store.execute("UPDATE budget SET actual=?,state='reported' WHERE id=?",(cost,run_id))
        answer=json.loads(response['choices'][0]['message']['content'])
        located=validate_answer(answer,{r['version_id']:r for r in records},set(record['evidence_versions']))
        record.update({'answer':answer,'citation_checks':[asdict(c) for c in located],
                       'state':'draft_quote_checked','output_hash':sha(dump(answer)),
                       'label':'FRESH MODEL INFERENCE OVER RETAINED EVIDENCE; HUMAN REVIEW REQUIRED'})
        store.event('review_required',{'run_id':run_id,'mechanical_citations':len(located)},job['session_id'],job['id'])
    except Exception as exc:
        code=exc.code if isinstance(exc,AppError) else 'PROVIDER_TIMEOUT' if isinstance(exc,httpx.TimeoutException) else 'OUTPUT_OR_PROVIDER_FAILED'
        record.update({'state':'failed','error':code,'submitted':submitted})
        raise AppError(code,502) from None
    finally:
        record.update({'finished_at':now(),'latency_ms':round((time.monotonic()-t0)*1000)})
        store.execute('INSERT INTO model_runs VALUES (?,?,?,?)',(run_id,job['id'],job['session_id'],dump(record)))
    return record


def answer_job(store: Store, settings: Settings, job: dict) -> dict:
    p=json.loads(job['payload']); sess=session(store,job['session_id'],job['actor'])
    if sess['scope_revision']!=p['scope_revision']:
        raise AppError('SCOPE_CHANGED_RETRY')
    records=selected(store,sess)
    if p.get('source_ids'):
        records=[r for r in records if r['id'] in p['source_ids']]
    if not records:
        raise AppError('NO_ADMITTED_EVIDENCE')
    if p['use_ai']:
        first=inference(store,settings,job,records,p['question'],'answer')
        result={'kind':'answer','inference':True,'answer':first['answer'],'runs':[first],
                'source_versions':[r['version_id'] for r in records], 'scope_revision':p['scope_revision']}
        if p.get('challenge'):
            challenge_question=p['question']+'\nReview this first-pass draft against the same evidence. Draft (untrusted):\n'+dump(first['answer'])
            try:
                result['challenge']=inference(store,settings,job,records,challenge_question[:3900],'challenge')
                result['runs'].append(result['challenge'])
            except AppError as exc:
                result['challenge_error']=exc.code
        return result
    store.event('compiling_template',{'model_calls':0},job['session_id'],job['id'])
    return {'kind':'answer','inference':False,'answer':baseline(records),'runs':[],
            'label':'TEMPLATE-BASED BRIEF; NO MODEL CALL','source_versions':[r['version_id'] for r in records],
            'scope_revision':p['scope_revision'],'question_handling':'Template covers the selected corpus; it does not answer arbitrary questions.'}
