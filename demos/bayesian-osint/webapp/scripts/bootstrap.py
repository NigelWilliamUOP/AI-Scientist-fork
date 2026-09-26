"""Create an isolated Python environment and start the application.

First run downloads the pinned public dependencies. This makes no model calls,
creates no paid hosting, and does not authorise Google Drive.
"""
import hashlib,os,subprocess,sys,venv,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if sys.version_info<(3,11):raise SystemExit('Install Python 3.11 or later, then run this launcher again.')
if not (ROOT/'frontend/public/app.js').exists():
    npm=shutil.which('npm')
    if not npm:raise SystemExit('This is a source checkout: install Node 22 and run npm ci / npm run build in frontend, or use the ready-to-run release ZIP.')
    subprocess.run([npm,'ci','--ignore-scripts'],cwd=ROOT/'frontend',check=True)
    subprocess.run([npm,'run','build'],cwd=ROOT/'frontend',check=True)
env=ROOT/'.venv';python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
if not python.exists():
    print('Creating isolated Python environment…',flush=True)
    venv.EnvBuilder(with_pip=True).create(env)
requirements=ROOT/'requirements.txt';digest=hashlib.sha256(requirements.read_bytes()).hexdigest();stamp=env/'osint-requirements.sha256'
if not stamp.exists() or stamp.read_text().strip()!=digest:
    print('Installing pinned runtime dependencies; an internet connection is needed.',flush=True)
    try:subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],cwd=ROOT,check=True)
    except subprocess.CalledProcessError:raise SystemExit('Dependency installation failed. Check internet/proxy access; the existing data has not been deleted.')
    stamp.write_text(digest+'\n')
raise SystemExit(subprocess.call([str(python),str(ROOT/'scripts/run.py')],cwd=ROOT))
