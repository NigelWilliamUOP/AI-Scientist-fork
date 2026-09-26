from __future__ import annotations
import json
from pathlib import Path
from osint_core.transport import capture
from .logic import AppError, normal, parse_notice, session
from .store import Store, dump, now, sha, uid


def refresh(store: Store, job: dict, seed_dir: Path) -> dict:
    payload=json.loads(job['payload'])
    sess=session(store,job['session_id'],job['actor'])
    if sess['mode']!='CURRENT_INVESTIGATION':
        raise AppError('REFRESH_DISABLED_IN_REPLAY')
    registry={s['id']:s for s in json.loads((seed_dir/'sources.json').read_text())['sources']}
    results=[]
    for source_id in payload['source_ids']:
        rule=registry.get(source_id)
        if not rule or not rule.get('enabled_for_live_fetch'):
            raise AppError('SOURCE_NOT_ALLOWED')
        store.event('fetching',{'source_id':source_id},sess['id'],job['id'])
        meta={}
        identity=uid('capture-')
        try:
            meta=capture(rule,store.root/'captures')
            store.event('captured',{'source_id':source_id,'http_status':meta['http_status'],'sha256':meta['upstream_body_sha256']},sess['id'],job['id'])
            raw=(store.root/'captures'/meta['raw_file']).read_bytes()
            seed=json.loads((seed_dir/(source_id+'.json')).read_text())
            store.event('parsing',{'source_id':source_id},sess['id'],job['id'])
            segments,document_hash=parse_notice(raw,seed)
            content_hash=sha(dump([{ 'id':s['id'], 'text':normal(s['text'])} for s in segments]))
            prior=store.one("SELECT * FROM captures WHERE source_id=? AND state='captured' ORDER BY at DESC LIMIT 1",(source_id,))
            prior_meta=json.loads(prior['metadata']) if prior else {}
            change='historical_record_captured'
            if prior:
                change='unchanged' if content_hash==prior_meta.get('content_sha256') else 'selected_evidence_changed'
                if change=='unchanged' and document_hash!=prior_meta.get('document_sha256'):
                    change='document_changed_review_required'
            version_id=source_id+'-http-'+sha(content_hash+'|'+document_hash)[:20]
            record={**seed,'version_id':version_id,'segments':segments,'representation':'original_http_capture',
                    'review_method':'Server HTTP capture; bounded segment parser','parser_version':'bounded-notice-0.4.1',
                    'coverage':'Original HTML retained; selected passages parsed',
                    'acquired_at':meta['acquired_at'],'upstream_http_status':meta['http_status'],
                    'upstream_body_sha256':meta['upstream_body_sha256'], 'raw_file':meta['raw_file'],
                    'publisher_metadata_origin':'Curated notice registry; not inferred from retrieval time'}
            meta.update({'content_sha256':content_hash,'document_sha256':document_hash,'change':change,'parser_status':'parsed','version_id':version_id})
            with store.connect(write=True) as db:
                db.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?,?,?)',(version_id,source_id,content_hash,dump(record),now()))
                db.execute('INSERT INTO captures VALUES (?,?,?,?,?,?)',(identity,source_id,version_id,'captured',dump(meta),now()))
                current=db.execute('SELECT selection FROM sessions WHERE id=?',(sess['id'],)).fetchone()
                selection=json.loads(current['selection']); selection[source_id]=version_id
                db.execute('UPDATE sessions SET selection=?,scope_revision=scope_revision+1 WHERE id=?',(dump(selection),sess['id']))
                if change in ('selected_evidence_changed','document_changed_review_required'):
                    accepted=db.execute("SELECT body FROM assessments WHERE case_id='SEA-CHANGE'").fetchone()
                    refs=json.loads(accepted['body']).get('source_versions',[])
                    if any(v.startswith(source_id+'-') for v in refs):
                        db.execute("UPDATE assessments SET stale=1 WHERE case_id='SEA-CHANGE'")
            store.event(change,{'source_id':source_id,'version_id':version_id},sess['id'],job['id'])
            results.append({'source_id':source_id,'state':change,'capture_id':identity,'version_id':version_id})
        except Exception as exc:
            code=exc.code if isinstance(exc,AppError) else 'SOURCE_UNAVAILABLE'
            meta.update({'source_id':source_id,'error':code,'attempted_at':now()})
            store.execute('INSERT INTO captures VALUES (?,?,?,?,?,?)',(identity,source_id,None,'failed',dump(meta),now()))
            store.event('source_failed',{'source_id':source_id,'error':code,'previous_evidence_preserved':True},sess['id'],job['id'])
            results.append({'source_id':source_id,'state':'failed','error':code})
    return {'kind':'refresh','sources':results,'success_count':sum(x['state']!='failed' for x in results),
            'live_claim':'Only successful original HTTP captures are live acquisitions; publication dates are unchanged.'}
