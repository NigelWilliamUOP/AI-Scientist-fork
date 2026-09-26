"""Verify or restore an owner-exported ZIP. No remote access; no credentials."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from osint.archive import restore_bundle,verify_bundle
from osint.store import Store
parser=argparse.ArgumentParser();parser.add_argument('action',choices=['verify','restore']);parser.add_argument('archive',type=Path);parser.add_argument('--data-dir',type=Path,default=ROOT/'.runtime');args=parser.parse_args()
content=args.archive.read_bytes();files=verify_bundle(content)
if args.action=='verify':print(json.dumps({'verified':True,'files':len(files),'meaning':'Internal byte integrity, not a digital signature or source-authenticity guarantee.'},indent=2))
else:
    store=Store(args.data_dir);store.seed(ROOT/'seeds');sid=restore_bundle(store,content,'owner')
    print(json.dumps({'restored_session':sid,'mode':'RECORDED_REPLAY','data_dir':str(store.root),'next':'Restart the app; the most recent owner session is the restored read-only snapshot.'},indent=2))
