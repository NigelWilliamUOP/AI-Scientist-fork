"""Readiness report. Configuration presence is not live verification."""
import json,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from run import load_env
load_env()
from osint.settings import Settings
s=Settings()
checks={'python':sys.version.split()[0],'frontend_compiled':(ROOT/'frontend/public/app.js').is_file(),
 'source_records':len(list((ROOT/'seeds').glob('FTS-*.json')))+2,'ai_status':s.ai_status,
 'google_oauth_app_configured':bool(s.google_client_id and s.google_client_secret and s.encryption_key),
 'data_directory':str(s.data_dir),'production':s.production,'docker_available':bool(shutil.which('docker')),
 'live_model_verified':False,'live_drive_verified':False,'external_capture_verified':False,
 'next':'Use the actual UI workflows and record successful external transactions separately. This doctor does not call providers.'}
print(json.dumps(checks,indent=2))
