from __future__ import annotations
import io
import json
import os
from pathlib import Path, PurePosixPath
import zipfile
from .drive import Drive
from .logic import AppError, assessment_for_session, baseline, selected, session
from .store import Store, dump, now, sha, uid


def make_export(store: Store, actor: str, session_id: str) -> dict:
    sess=session(store,session_id,actor); records=selected(store,sess)
    allowed={r['version_id'] for r in records}
    assessment=assessment_for_session(store,sess,records)
    files={}
    def add(name: str, value: dict | list):
        files[name]=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    clean_session={k:sess[k] for k in ('id','mode','cutoff','scope_revision','selection','exclusions','created_at')}
    clean_session['selection']={r['id']:r['version_id'] for r in records}
    clean_session['exclusions']=[]
    add('session.json',clean_session)
    add('assessment.json',assessment or {'status':'NO_ADMISSIBLE_SHARED_ASSESSMENT'})
    events=store.all('SELECT id,kind,detail,at FROM events WHERE session_id=? ORDER BY id',(session_id,))
    frozen=store.one('SELECT audit,context FROM snapshots WHERE session_id=?',(session_id,))
    if frozen:
        add('prior-audit.json',json.loads(frozen['audit']))
        add('replay-context.json',json.loads(frozen['context']))
    add('audit.json',events)
    for r in records:
        add('evidence/'+r['version_id']+'.json',r)
        if r.get('representation')=='original_http_capture' and r.get('raw_file'):
            p=store.root/'captures'/r['raw_file']
            if p.is_file() and p.parent==store.root/'captures' and sha(p.read_bytes())==r['upstream_body_sha256']:
                files['captures/'+r['raw_file']]=p.read_bytes()
    runs=[]
    for row in store.all('SELECT body FROM model_runs WHERE session_id=?',(session_id,)):
        run=json.loads(row['body'])
        if set(run.get('evidence_versions',[]))<=allowed:
            runs.append(run); add('model-runs/'+run['id']+'.json',run)
    brief=baseline(records)
    lines=['# Portsmouth shore power: evidence briefing','',
           'TEMPLATE-BASED BRIEF. No model call was used to write this document.',
           'Mode: '+sess['mode']+'; cutoff: '+str(sess['cutoff']),
           'Generated: '+now(),'',
           'Real public-source extracts/captures are identified individually. Retrospective reconstruction is not historical observation.','']
    for statement in brief['statements']:
        lines.extend([statement['text'],''])
        for citation in statement['citations']:
            r=next(x for x in records if x['version_id']==citation['source_version_id'])
            lines.extend(['Source: '+r['url'],'Version: '+r['version_id']+'; segment: '+citation['segment_id'],
                          '> '+citation['quote'].replace('\n',' '),''])
    lines+=['## Limits']+brief['uncertainties']+['','## Next evidence']+brief['next_evidence']
    lines+=['','## AI records',f'{len(runs)} run record(s) included separately. Matching quotations are not automatic semantic validation.']
    files['briefing.md']='\n'.join(lines).encode()
    manifest={'schema':'osint-export-0.4.1','case_id':'SEA-CHANGE','namespace':'real','generated_at':now(),
              'files':[{ 'path':name,'sha256':sha(body),'size':len(body)} for name,body in sorted(files.items())]}
    add('manifest.json',manifest)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,body in sorted(files.items()):
            z.writestr(name,body)
    content=buffer.getvalue()
    if len(content)>4_500_000:
        raise AppError('EXPORT_TOO_LARGE_FOR_MVP')
    identity=uid('export-'); path=store.root/'exports'/(identity+'.zip')
    temp=path.with_suffix('.tmp')
    with open(temp,'wb') as handle:
        handle.write(content); handle.flush(); os.fsync(handle.fileno())
    os.replace(temp,path)
    store.execute('INSERT INTO exports VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (identity,session_id,actor,str(path),sha(content),len(content),'local_only',None,None,None,now(),None))
    store.event('local_archive_created',{'export_id':identity,'sha256':sha(content),'drive_verified':False},session_id)
    return {'id':identity,'sha256':sha(content),'size':len(content),'state':'local_only'}


def sync_export(store: Store, drive: Drive, job: dict) -> dict:
    p=json.loads(job['payload']); row=store.one('SELECT * FROM exports WHERE id=? AND actor=?',(p['export_id'],job['actor']))
    if not row:
        raise AppError('EXPORT_NOT_FOUND',404)
    if row['state']=='verified':
        return {'kind':'archive','export_id':row['id'],'state':'verified','drive_file_id':row['remote_id']}
    if drive.status=='DRIVE_NOT_CONNECTED':
        raise AppError('DRIVE_NOT_CONNECTED',409)
    content=Path(row['path']).read_bytes()
    if sha(content)!=row['sha256'] or len(content)!=row['size']:
        raise AppError('LOCAL_ARCHIVE_HASH_MISMATCH')
    store.execute("UPDATE exports SET state='uploading',error=NULL WHERE id=?",(row['id'],))
    store.event('archiving',{'export_id':row['id']},job['session_id'],job['id'])
    try:
        obj=drive.put_verified(content,row['id']+'-'+row['sha256'][:12]+'.zip','export')
        # A manifest is sent only after the content has passed byte readback.
        receipt={'schema':'osint-drive-manifest-0.4.1','case_id':'SEA-CHANGE','export_id':row['id'],
                 'objects':[obj],'verified_at':now()}
        manifest=drive.put_verified(dump(receipt).encode(),row['id']+'-manifest.json','manifest')
        store.execute("UPDATE exports SET state='verified',remote_id=?,manifest_id=?,verified_at=?,error=NULL WHERE id=?",
            (obj['file_id'],manifest['file_id'],now(),row['id']))
        store.event('drive_verified',{'export_id':row['id'],'file_id':obj['file_id'],'sha256':obj['sha256']},job['session_id'],job['id'])
        return {'kind':'archive','export_id':row['id'],'state':'verified','drive_file_id':obj['file_id']}
    except Exception as exc:
        code=exc.code if isinstance(exc,AppError) else 'DRIVE_UPLOAD_FAILED'
        store.execute("UPDATE exports SET state='pending',error=? WHERE id=?",(code,row['id']))
        raise AppError(code,502)


def verify_bundle(content: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            names=z.namelist()
            if len(names)>150 or len(names)!=len(set(names)):
                raise AppError('INVALID_ARCHIVE')
            for info in z.infolist():
                p=PurePosixPath(info.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in info.filename or info.file_size>3_500_000:
                    raise AppError('INVALID_ARCHIVE')
            if sum(x.file_size for x in z.infolist())>25_000_000:
                raise AppError('INVALID_ARCHIVE')
            manifest=json.loads(z.read('manifest.json'))
            if manifest['case_id']!='SEA-CHANGE' or manifest['namespace']!='real' or manifest['schema']!='osint-export-0.4.1':
                raise AppError('WRONG_CASE_ARCHIVE')
            expected={r['path'] for r in manifest['files']}
            if expected|{'manifest.json'}!=set(names):
                raise AppError('ARCHIVE_MANIFEST_MISMATCH')
            for record in manifest['files']:
                data=z.read(record['path'])
                if sha(data)!=record['sha256'] or len(data)!=record['size']:
                    raise AppError('ARCHIVE_HASH_MISMATCH')
            return {name:z.read(name) for name in names}
    except AppError:
        raise
    except Exception:
        raise AppError('INVALID_ARCHIVE')


def restore_bundle(store: Store, content: bytes, actor: str) -> str:
    files=verify_bundle(content); old=json.loads(files['session.json'])
    identity=uid('restored-'); choice={}
    with store.connect(write=True) as db:
        for name,body in files.items():
            if name.startswith('evidence/'):
                r=json.loads(body)
                for seg in r['segments']:
                    if sha(seg['text'])!=seg['sha256']:
                        raise AppError('ARCHIVE_HASH_MISMATCH')
                existing=db.execute('SELECT body FROM versions WHERE id=?',(r['version_id'],)).fetchone()
                if existing and json.loads(existing['body'])!=r:
                    raise AppError('IMMUTABLE_VERSION_CONFLICT')
                db.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?,?,?)',(r['version_id'],r['id'],sha(dump(r['segments'])),dump(r),now()))
                choice[r['id']]=r['version_id']
        db.execute('INSERT INTO sessions(id,actor,mode,cutoff,scope_revision,selection,exclusions,created_at) VALUES (?,?,?,?,?,?,?,?)',
            (identity,actor,'RECORDED_REPLAY',None,old['scope_revision'],dump(choice),'[]',now()))
        assessed=json.loads(files['assessment.json'])
        if isinstance(assessed.get('body'),str): assessed['body']=json.loads(assessed['body'])
        old_audit=json.loads(files.get('prior-audit.json',b'[]'))+json.loads(files['audit.json'])
        db.execute('INSERT INTO snapshots VALUES (?,?,?,?)',(identity,dump(assessed),dump(old_audit),
            dump({'original_session':old['id'],'original_mode':old['mode'],'original_cutoff':old['cutoff'],'bundle_sha256':sha(content)})))
    for name,body in files.items():
        if name.startswith('captures/'):
            (store.root/'captures'/PurePosixPath(name).name).write_bytes(body)
        if name.startswith('model-runs/'):
            run=json.loads(body); run['restored_from']=run['id']; run['id']=uid('restored-run-')
            store.execute('INSERT INTO model_runs VALUES (?,?,?,?)',(run['id'],'restored',identity,dump(run)))
    store.event('restored_bundle',{'original_session':old['id'],'original_mode':old['mode'],'original_cutoff':old['cutoff'],'bundle_sha256':sha(content)},identity)
    return identity
