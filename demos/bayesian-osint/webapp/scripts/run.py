"""Run one local process. Credentials remain on the server, never in the page."""
import os,sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))

def load_env():
    path=ROOT/'.env'
    if not path.is_file():return
    for number,line in enumerate(path.read_text().splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):continue
        if '=' not in line:raise ValueError(f'Invalid .env line {number}; use KEY=value')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not key.replace('_','').isalnum():raise ValueError(f'Invalid .env key at line {number}')
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
        os.environ.setdefault(key,value)

if __name__=='__main__':
    load_env()
    import uvicorn
    from osint.main import app
    cfg=app.state.settings;url=urlparse(cfg.public_url)
    if cfg.production:raise SystemExit('Use the container/production command behind HTTPS, not the local launcher.')
    print('\nOSINT Bayes / local evidence observatory')
    print('Open:',cfg.public_url)
    if not os.getenv('APP_OWNER_PASSWORD'):
        print('Owner access password is in:',cfg.data_dir/'secrets/owner-password.txt')
        print('Keep this file private. No password or key is embedded in the browser.')
    print('AI:',cfg.ai_status,'| Drive:',app.state.drive.status)
    print('Stop with Ctrl+C. Your local evidence and review state will be retained.\n')
    uvicorn.run(app,host=url.hostname or '127.0.0.1',port=url.port or 8000,workers=1,access_log=False,proxy_headers=False)
