from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
def records():
    m=json.loads((ROOT/'seeds/manifest.json').read_text())
    return [json.loads((ROOT/r['path']).read_text()) for r in m['records']]
def record(id):
    return next(r for r in records() if r['id']==id)
