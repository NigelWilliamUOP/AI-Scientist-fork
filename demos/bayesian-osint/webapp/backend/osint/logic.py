"""Evidence selection, deterministic briefs and source-linked graph construction."""
from __future__ import annotations
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from osint_core.evidence import admitted_at_cutoff, timestamp
from osint_core.grounding import validate_answer
from .store import Store, dump, now, sha, uid

MODES = ('CURRENT_INVESTIGATION', 'HISTORICAL_RECONSTRUCTION', 'RECORDED_REPLAY')

class AppError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


def session(store: Store, identity: str, actor: str) -> dict:
    row = store.one('SELECT * FROM sessions WHERE id=? AND actor=?', (identity,actor))
    if not row:
        raise AppError('SESSION_NOT_FOUND',404)
    row['selection'] = json.loads(row['selection'])
    row['exclusions'] = json.loads(row['exclusions'])
    return row


def selected(store: Store, sess: dict, include_excluded: bool = False) -> list[dict]:
    records = [store.version(v) for source,v in sess['selection'].items()
               if include_excluded or source not in sess['exclusions']]
    if sess['mode'] == 'HISTORICAL_RECONSTRUCTION':
        records = admitted_at_cutoff(records, sess['cutoff'])
    return sorted(records,key=lambda r:r.get('publisher_timestamp') or r.get('publisher_date') or '9999')


def create_session(store: Store, actor: str, mode: str, cutoff: str | None, seed_dir: Path) -> str:
    if mode not in MODES:
        raise AppError('INVALID_MODE')
    if mode == 'HISTORICAL_RECONSTRUCTION':
        if not cutoff:
            raise AppError('CUTOFF_REQUIRED')
        try:
            timestamp(cutoff)
        except (ValueError,TypeError):
            raise AppError('INVALID_CUTOFF')
    elif cutoff:
        raise AppError('CUTOFF_ONLY_FOR_RECONSTRUCTION')
    sources = json.loads((seed_dir/'sources.json').read_text())['sources']
    choice = {}
    for source in sources:
        # A current web page is not a valid historical vintage. Reconstruction is
        # intentionally restricted to bounded, inspected source extracts.
        if mode == 'HISTORICAL_RECONSTRUCTION':
            r = store.version(source['id']+'-seed-extract-v1')
            if not admitted_at_cutoff([r],cutoff):
                continue
        else:
            row = store.one('SELECT body FROM versions WHERE source_id=? ORDER BY created_at DESC LIMIT 1', (source['id'],))
            r = json.loads(row['body'])
        choice[source['id']] = r['version_id']
    identity = uid('case-')
    store.execute('INSERT INTO sessions(id,actor,mode,cutoff,selection,created_at) VALUES (?,?,?,?,?,?)',
                  (identity, actor,mode,cutoff,dump(choice),now()))
    store.event('session_created', {'mode':mode, 'cutoff':cutoff,'admitted_versions':list(choice.values())}, identity)
    return identity


def assessment_for_session(store: Store, sess: dict, records: list[dict]) -> dict:
    if sess['mode']=='RECORDED_REPLAY':
        snapshot=store.one('SELECT assessment FROM snapshots WHERE session_id=?',(sess['id'],))
        assessment=json.loads(snapshot['assessment']) if snapshot else None
    elif sess['mode']=='HISTORICAL_RECONSTRUCTION':
        assessment=None
    else:
        assessment=store.one("SELECT * FROM assessments WHERE case_id='SEA-CHANGE'")
    if assessment and isinstance(assessment.get('body'),str):
        assessment['body']=json.loads(assessment['body'])
    allowed={r['version_id'] for r in records}
    if not assessment or not set(assessment.get('body',{}).get('source_versions',[]))<=allowed:
        return {'revision':assessment['revision'] if assessment and sess['mode']=='CURRENT_INVESTIGATION' else 0,
                'body':{'status':'ASSESSMENT_OUTSIDE_SCENARIO','statements':[],'source_versions':[]},'stale':False}
    return assessment


def cite(record: dict, segment_id: str) -> dict:
    seg = next(s for s in record['segments'] if s['id'] == segment_id)
    return {'source_version_id':record['version_id'],'segment_id':segment_id,'quote':seg['text']}


def baseline(records: list[dict]) -> dict:
    by_id = {r['id']:r for r in records}
    statements: list[dict] = []
    def add(source: str, segments: list[str], kind: str, text: str) -> None:
        r = by_id.get(source)
        if r and all(any(s['id']==sid for s in r['segments']) for sid in segments):
            statements.append({'text':text,'kind':kind,'citations':[cite(r,sid) for sid in segments]})
    # Templates interpret only the exact original strings: changed live passages
    # must be reviewed, not silently fed into yesterday's conclusions.
    def exact(source: str, segment: str, expected: str) -> bool:
        r = by_id.get(source,{})
        return any(s['id']==segment and normal(s['text'])==normal(expected) for s in r.get('segments',[]))
    if exact('CF-AWARD','value','Value of contract\n£0') and exact('CF-AWARD','range','Value range of £12 - £14m.'):
        add('CF-AWARD',['value','range'],'data_quality_issue',
            'The equipment record has a structured £0 field and a £12–14 million descriptive range. The final amount paid is not established by these conflicting fields.')
    if exact('FTS-TENDER','planned-live','The system is targeted to enter operation on 1st April 2025'):
        add('FTS-TENDER',['planned-live'],'plan',
            'The operating date of 1 April 2025 is a target in the tender, not evidence that operation began on that date.')
    if exact('FTS-PIN','indicative-return','24th October 2024'):
        add('FTS-PIN',['indicative-return'],'plan','The prior information notice gives 24 October 2024 as an indicative tender-submission date. It is not a physical completion deadline.')
    if exact('FTS-TENDER','published-return','4th November 2024 14:00'):
        add('FTS-TENDER',['published-return'],'plan','The tender gives a return deadline of 4 November 2024 at 14:00. This is a procurement deadline, not a completion date.')
    if exact('FTS-CORRECTION','before','Shore Power HV Operations Management - Portsmouth International Por') and exact('FTS-CORRECTION','after','Shore Power HV Operations Management - Portsmouth International Port'):
        add('FTS-CORRECTION',['before','after'],'reported_observation','The correction repairs the title from “Por” to “Port”. It supplies no change to the operating target.')
    if exact('PORT-STATEMENT','reported-use','now plugging into Portsmouth International Port’s shore power system'):
        add('PORT-STATEMENT',['reported-use','future-capability'],'reported_observation',
            'The port reports use of shore power and describes simultaneous connection of three ships as a further expected capability. The extract has no verified publication date.')
    covered = {c['source_version_id'] for x in statements for c in x['citations']}
    # Every otherwise uncovered record can still provide a truthful quotation.
    for r in records:
        if r['version_id'] not in covered and r['segments']:
            s=r['segments'][0]
            statements.append({'text':'The retained passage states: '+s['text'], 'kind':'reported_observation','citations':[cite(r,s['id'])]})
    answer = {'statements':statements[:12],
              'uncertainties':['Selected passages are not the complete source corpus. A matching quotation does not prove an interpretation.','These materials do not establish every commissioned capability or the exact final price.'],
              'next_evidence':['Obtain an openly published acceptance or commissioning record with dates and scope.','Locate a reconciled final contract-value record.']}
    if not records:
        answer = {'statements':[], 'uncertainties':['No admitted evidence remains in this scenario.'], 'next_evidence':['Reinstate an appropriate source before drawing a conclusion.']}
    validate_answer(answer,{r['version_id']:r for r in records},{r['version_id'] for r in records})
    return answer


def graph(records: list[dict]) -> dict:
    nodes, edges = [], []
    if not records:
        return {'nodes':nodes,'edges':edges}
    nodes.append({'id':'programme','label':'Sea Change','kind':'case','description':'Analyst-defined investigation grouping, not an inferred delivery relationship'})
    groups: set[str] = set()
    for r in records:
        group=r['origin_group']
        if group not in groups:
            groups.add(group)
            label = 'HV operations procurement' if 'OPERATIONS' in group else 'Equipment procurement' if 'EQUIPMENT' in group else 'Port statement'
            nodes.append({'id':group,'label':label,'kind':'origin'})
            edges.append({'source':'programme','target':group,'kind':'case_grouping','source_version_id':r['version_id'],'locator':'Analyst grouping; separate origin retained'})
        nodes.append({'id':r['id'],'label':r['display_title'],'kind':'document','source_version_id':r['version_id']})
        edges.append({'source':group,'target':r['id'],'kind':'shared_origin','source_version_id':r['version_id'],'locator':'OCID / declared publication origin','origin_group':group})
    ids={r['id'] for r in records}
    if {'FTS-TENDER','FTS-CORRECTION'} <= ids:
        correction=next(r for r in records if r['id']=='FTS-CORRECTION')
        edges.append({'source':'FTS-TENDER','target':'FTS-CORRECTION','kind':'title_correction','source_version_id':correction['version_id'],'locator':'VII.1.2, title: Instead of / Read'})
    return {'nodes':nodes,'edges':edges}


def normal(text: str) -> str:
    return re.sub(r'\s+',' ',text).strip()


def parse_notice(raw: bytes, seed: dict) -> tuple[list[dict], str]:
    soup=BeautifulSoup(raw,'html.parser')
    for tag in soup.select('script,style,nav,header,footer,.govuk-cookie-banner,.gem-c-related-navigation,.related-notices'):
        tag.decompose()
    main=soup.select_one('#main-content') or soup.find('main')
    if main is None:
        raise AppError('PARSER_FAILED')
    text=normal(main.get_text(' ',strip=True))
    if len(text)<60:
        raise AppError('PARSER_FAILED')
    patterns={
        'planned-live':r'The system is targeted to enter operation on [^.;]{1,70}',
        'value':r'Value of contract\s*£[\d,\.]+',
        'range':r'Value range of £[\d\s,.–\-£]+m\.',
        'before':r'(Shore Power HV Operations Management - Portsmouth International Por)\b',
        'after':r'(Shore Power HV Operations Management - Portsmouth International Port)\b',
    }
    segments=[]
    for old in seed['segments']:
        needle=normal(old['text'])
        found=needle if needle in text else None
        if found is None and old['id'] in patterns:
            match=re.search(patterns[old['id']],text,re.I)
            found=match.group(0) if match else None
        if found:
            segments.append({'id':old['id'],'locator':old['locator'], 'text':found,'sha256':sha(found)})
    # Fail closed for unfamiliar changed layouts. Original bytes are still kept.
    if len(segments)!=len(seed['segments']):
        raise AppError('PARSER_FAILED')
    return segments,sha(text)
