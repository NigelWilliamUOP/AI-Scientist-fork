"""Browser acceptance checks against the real application.

Default: native HTTP (start scripts/run.py first; set BROWSER_TEST_PASSWORD).
--asgi-bridge: Chromium cannot navigate to local addresses in some sandboxes.
The unchanged JS is then loaded into about:blank; fetch delegates to the actual
ASGI application. This verifies DOM/API behaviour but NOT browser HTTP/cookies,
TLS, public hosting, remote map tiles, or external integrations.
"""
import argparse,json,os,sys,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from contextlib import ExitStack


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--asgi-bridge',action='store_true');parser.add_argument('--url',default='http://127.0.0.1:8000');parser.add_argument('--chromium');args=parser.parse_args()
    password='browser-fixture-password' if args.asgi_bridge else os.environ['BROWSER_TEST_PASSWORD']
    out=ROOT/'reports';out.mkdir(exist_ok=True);checks=[];errors=[]
    def check(name,condition=True):
        checks.append({'name':name,'passed':bool(condition)})
        assert condition,name
    with ExitStack() as stack:
        if args.asgi_bridge:
            from osint.main import create_app
            from osint.settings import Settings
            from fastapi.testclient import TestClient
            data=Path(stack.enter_context(tempfile.TemporaryDirectory()))
            app=create_app(Settings(data_dir=data,owner_password=password,start_worker=True))
            client=stack.enter_context(TestClient(app,base_url=args.url))
        p=stack.enter_context(sync_playwright())
        options={'headless':True,'args':['--no-sandbox']}
        if args.chromium:options['executable_path']=args.chromium
        browser=p.chromium.launch(**options);stack.callback(browser.close)
        page=browser.new_page(viewport={'width':1600,'height':1120},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        if args.asgi_bridge:
            def bridge(data):
                r=client.request(data.get('method','GET'),data['url'],headers={**data.get('headers',{}),'origin':args.url},content=data.get('body',''))
                return {'status':r.status_code,'body':r.text,'headers':dict(r.headers)}
            page.expose_function('__asgiBridge',bridge)
            page.set_content('<html lang="en-GB"><head><title>OSINT Bayes | Evidence observatory</title></head><body><a class="skip-link" href="#main">Skip to investigation</a><div id="app"></div><div id="toast" role="status"></div><dialog id="modal"></dialog></body></html>')
            page.add_style_tag(content=(ROOT/'frontend/public/styles.css').read_text())
            page.evaluate('''() => {const values={};Object.defineProperty(window,'localStorage',{value:{getItem:k=>values[k]||null,setItem:(k,v)=>values[k]=String(v),removeItem:k=>delete values[k]}});window.fetch=async(url,options={})=>{const r=await window.__asgiBridge({url,method:options.method||'GET',headers:options.headers||{},body:options.body||''});return new Response(r.body,{status:r.status,headers:r.headers});};}''')
            page.add_script_tag(content=(ROOT/'frontend/public/app.js').read_text())
        else:page.goto(args.url)
        page.locator('#password').wait_for();check('Login interface visible')
        page.screenshot(path=str(out/'app-login.png'))
        page.locator('#password').fill(password);page.locator('#login-form button').click()
        page.locator('#evidence-graph').wait_for();check('Authenticated workspace opens')
        check('Five real extract source cards',page.locator('.source-card').count()==5)
        check('No original captures falsely reported','0 original HTTP captures' in page.locator('.mode-strip').inner_text())
        check('AI disabled without configuration',page.locator('[data-action="ask"]').is_disabled())
        check('No browser secret fields',page.locator('input[type="password"]').count()==0)
        check('Graph has five selectable documents',page.locator('.graph-node.document').count()==5)
        check('No desktop horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        page.screenshot(path=str(out/'app-network.png'),full_page=True)
        page.locator('#source-filter').fill('FTS-TENDER');check('Source filter works',page.locator('.source-card').count()==1)
        page.locator('#source-filter').fill('');check('Source filter clears',page.locator('.source-card').count()==5)
        page.locator('.graph-node[data-id="FTS-CORRECTION"]').focus();page.keyboard.press('Enter')
        expect(page.locator('.evidence-panel h2')).to_have_text('Title correction');check('Keyboard-select graph node')
        check('Correction passage visible',page.locator('.segment blockquote').first.inner_text().endswith('Por'))
        check('Evidence version visible','FTS-CORRECTION-seed-extract-v1' in page.locator('.drawer-foot').inner_text())
        check('Original source link retains HTTPS',page.locator('.source-link').get_attribute('href').startswith('https://'))
        page.locator('[data-tab="timeline"]').click();expect(page.locator('.timeline-item')).to_have_count(5);check('Publication timeline populated')
        page.locator('[data-action="before"]').click();expect(page.locator('.source-card')).to_have_count(3);check('Before-cutoff three records')
        check('Undated statement withheld','Reported shore-power use' not in page.locator('#source-list').inner_text())
        check('Later correction withheld','Title correction' not in page.locator('#source-list').inner_text())
        page.locator('[data-tab="network"]').click();check('No future correction edge',page.locator('.edge.correction').count()==0)
        check('Declared-origin note uses admitted count','2 admitted operations notice' in page.locator('.insight-strip').inner_text())
        page.locator('[data-tab="map"]').click();check('Current location withheld historically','Current-location layer withheld' in page.locator('#canvas').inner_text())
        page.locator('[data-tab="timeline"]').click();page.locator('[data-action="after"]').click();expect(page.locator('.source-card')).to_have_count(4);check('After-cutoff four records')
        page.screenshot(path=str(out/'app-historical.png'),full_page=True)
        page.locator('[data-action="current"]').click();expect(page.locator('.source-card')).to_have_count(5)
        page.locator('[data-tab="map"]').click();check('Sourced directions coordinate shown','50.811823' in page.locator('.coordinates').inner_text())
        check('Tiles do not load without action',page.locator('.tile-layer img').count()==0)
        page.screenshot(path=str(out/'app-map.png'),full_page=True)
        page.locator('[data-tab="network"]').click()
        page.locator('[data-action="exclude"][data-id="CF-AWARD"]').click();expect(page.locator('.source-card.excluded')).to_have_count(1)
        check('Withdrawal removes graph node',page.locator('.graph-node[data-id="CF-AWARD"]').count()==0)
        page.locator('[data-action="compile"]').click();page.locator('#draft-panel').wait_for();check('Actual backend template job completed')
        check('Withdrawal removes zero-value claim','£0' not in page.locator('#draft-panel').inner_text())
        check('Template distinguished from AI','ZERO MODEL CALLS' in page.locator('#draft-panel').inner_text())
        page.locator('[data-action="exclude"][data-id="CF-AWARD"]').click();expect(page.locator('.source-card.excluded')).to_have_count(0)
        page.locator('[data-action="compile"]').click();page.locator('#draft-panel').wait_for()
        check('Reinstatement restores grounded claim','£0' in page.locator('#draft-panel').inner_text())
        page.locator('[data-action="review"]').click();expect(page.locator('#modal')).to_be_visible()
        page.locator('[data-action="accept-review"]').click();check('Review needs a rationale and explicit checkbox',page.locator('#modal').is_visible())
        page.locator('#review-note').fill('Reviewed the exact passages and checked the limitations in each statement.')
        page.locator('#support-checked').check();page.locator('[data-action="accept-review"]').click();expect(page.locator('#modal')).not_to_be_visible()
        expect(page.locator('.metrics')).to_contain_text('Human reviewed');check('Reviewed assessment persisted')
        page.screenshot(path=str(out/'app-reviewed.png'),full_page=True)
        page.locator('[data-action="export"]').click();expect(page.locator('#modal h2')).to_have_text('Local archive created');check('Actual audit export created')
        check('Export displays SHA-256','SHA-256' in page.locator('#modal').inner_text())
        check('Archive not falsely labelled Drive verified','Not saved to Drive' in page.locator('#modal').inner_text())
        check('Unconfigured Drive sync disabled',page.locator('[data-action="sync-export"]').is_disabled())
        check('Archive download points to protected endpoint','/api/v1/exports/' in page.locator('#modal a[download]').get_attribute('href'))
        page.keyboard.press('Escape');expect(page.locator('#modal')).not_to_be_visible();check('Escape closes dialogue')
        page.locator('[data-tab="training"]').click();page.locator('[data-action="calculate"]').click()
        expect(page.locator('#sensitivity-output')).to_contain_text('33.3%');check('Corrected factor replaces prior evidence')
        check('Duplicate evidence has no extra numerical weight',page.locator('.sensitivity-cards article').nth(1).inner_text().endswith('75.0%') and page.locator('.sensitivity-cards article').nth(2).inner_text().endswith('75.0%'))
        check('Training visibly separate','SYNTHETIC TRAINING ONLY' in page.locator('.training-banner').inner_text())
        page.locator('[data-tab="network"]').click();page.locator('[data-action="tour"]').click();expect(page.locator('.tour-panel')).to_be_visible();check('Guided demonstration visible',page.locator('.tour-panel').is_visible())
        page.locator('[data-action="tour-next"]').click();check('Guided step switches timeline',page.locator('.timeline-list').is_visible())
        page.locator('[data-action="tour-close"]').click();check('Guided sequence dismisses',page.locator('.tour-panel').count()==0)
        page.locator('[data-action="mode"]').click();page.locator('[data-action="frozen"]').click();expect(page.locator('.mode-strip')).to_contain_text('FROZEN EVIDENCE REPLAY')
        check('Frozen snapshot keeps reviewed revision','Human reviewed' in page.locator('.metrics').inner_text())
        check('Frozen refresh disabled',page.locator('[data-action="refresh"]').is_disabled())
        check('Frozen drafting disabled',page.locator('[data-action="compile"]').is_disabled())
        page.set_viewport_size({'width':390,'height':844});page.locator('[data-tab="network"]').click()
        check('No mobile horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        page.screenshot(path=str(out/'app-mobile.png'),full_page=True)
        check('Mobile source explorer retained',page.locator('.source-card').count()==5)
        check('No JavaScript exceptions',len(errors)==0)
    report={'browser':'Chromium','method':'DOM with in-process actual ASGI bridge; no mocked business data' if args.asgi_bridge else 'native HTTP',
        'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'page_errors':errors,
        'not_verified':['External acquisition','Live model calls','Live Google Drive','Public hosting','Browser HTTP transport/TLS/cookies'] if args.asgi_bridge else ['External integrations','Public deployment']}
    (out/'browser-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failed':report['failed'],'method':report['method']}))

if __name__=='__main__':run()
