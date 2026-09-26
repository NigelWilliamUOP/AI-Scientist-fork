"""Owner OAuth and immutable app-folder uploads. No broad Drive listing."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet
from .logic import AppError
from .settings import Settings
from .store import Store, dump, sha

SCOPE='https://www.googleapis.com/auth/drive.file'
API='https://www.googleapis.com/drive/v3/files'
TOKEN='https://oauth2.googleapis.com/token'

class Drive:
    def __init__(self, settings: Settings, store: Store):
        self.settings=settings; self.store=store
        self.path=store.root/'secrets'/'drive.enc'

    @property
    def configured(self) -> bool:
        return bool(self.settings.google_client_id and self.settings.google_client_secret and self.settings.encryption_key)

    @property
    def status(self) -> str:
        return 'CONNECTED_NOT_LIVE_VERIFIED' if self.configured and self.path.exists() else 'DRIVE_NOT_CONNECTED'

    def save(self, value: dict) -> None:
        try:
            body=Fernet(self.settings.encryption_key.encode()).encrypt(dump(value).encode())
        except Exception:
            raise AppError('TOKEN_ENCRYPTION_NOT_CONFIGURED',409)
        temp=self.path.with_suffix('.tmp')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as handle:
            handle.write(body); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp,self.path)

    def load(self) -> dict:
        if not self.configured or not self.path.exists():
            raise AppError('DRIVE_NOT_CONNECTED',409)
        try:
            return json.loads(Fernet(self.settings.encryption_key.encode()).decrypt(self.path.read_bytes()))
        except Exception:
            raise AppError('DRIVE_TOKEN_UNREADABLE',409)

    def begin(self, actor: str) -> str:
        if not self.configured:
            raise AppError('GOOGLE_OAUTH_APP_NOT_CONFIGURED',409)
        state=secrets.token_urlsafe(40); verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        self.store.execute('INSERT INTO oauth_states VALUES (?,?,?,?)',(sha(state),actor,verifier,time.time()+600))
        return 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
            'client_id':self.settings.google_client_id,'redirect_uri':self.settings.public_url+'/api/v1/owner/drive/callback',
            'response_type':'code','scope':SCOPE,'access_type':'offline','prompt':'consent','state':state,
            'code_challenge':challenge,'code_challenge_method':'S256'})

    def callback(self, actor: str, state: str, code: str) -> None:
        with self.store.connect(write=True) as db:
            row=db.execute('SELECT * FROM oauth_states WHERE id=? AND actor=?',(sha(state),actor)).fetchone()
            if not row or row['expires']<time.time():
                raise AppError('OAUTH_STATE_INVALID',403)
            db.execute('DELETE FROM oauth_states WHERE id=?',(sha(state),))
        with httpx.Client(timeout=25,follow_redirects=False,trust_env=False) as client:
            response=client.post(TOKEN,data={'client_id':self.settings.google_client_id,
                'client_secret':self.settings.google_client_secret,'code':code,'grant_type':'authorization_code',
                'redirect_uri':self.settings.public_url+'/api/v1/owner/drive/callback','code_verifier':row['verifier']})
            if response.status_code!=200:
                raise AppError('GOOGLE_OAUTH_FAILED',502)
            token=response.json()
            if not token.get('refresh_token') or SCOPE not in token.get('scope',''):
                raise AppError('GOOGLE_REFRESH_OR_SCOPE_MISSING',409)
            # Each authorisation owns an isolated folder. No scan of existing Drive.
            response=client.post(API,headers={'Authorization':'Bearer '+token['access_token']},
                json={'name':'OSINT_Bayes_HEIF','mimeType':'application/vnd.google-apps.folder',
                      'appProperties':{'osint_app':'heif-v0-4','case_id':'SEA-CHANGE'}},params={'fields':'id'})
            if response.status_code not in (200,201):
                raise AppError('DRIVE_FOLDER_CREATION_FAILED',502)
            token['folder_id']=response.json()['id']; token['expires_at']=time.time()+token.get('expires_in',3600)-60
            self.save(token)

    def credentials(self, client: httpx.Client) -> tuple[dict,str]:
        token=self.load()
        if time.time()>=token.get('expires_at',0):
            r=client.post(TOKEN,data={'client_id':self.settings.google_client_id,
                'client_secret':self.settings.google_client_secret,'refresh_token':token['refresh_token'],'grant_type':'refresh_token'})
            if r.status_code!=200:
                raise AppError('DRIVE_REAUTHORISATION_REQUIRED',409)
            new=r.json(); token['access_token']=new['access_token']; token['expires_at']=time.time()+new.get('expires_in',3600)-60
            self.save(token)
        folder=token.get('folder_id','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',folder):
            raise AppError('DRIVE_FOLDER_INVALID',409)
        return {'Authorization':'Bearer '+token['access_token']},folder

    def put_verified(self, content: bytes, name: str, kind: str) -> dict:
        if len(content)>4_500_000:
            raise AppError('ARCHIVE_TOO_LARGE_FOR_MVP')
        digest=sha(content)
        with httpx.Client(timeout=45,follow_redirects=False,trust_env=False) as client:
            headers,folder=self.credentials(client)
            # Destination comes only from encrypted owner configuration.
            query=f"'{folder}' in parents and trashed=false and appProperties has {{ key='sha256' and value='{digest}' }} and appProperties has {{ key='case_id' and value='SEA-CHANGE' }}"
            r=client.get(API,headers=headers,params={'q':query,'fields':'files(id)','pageSize':10})
            if r.status_code!=200:
                raise AppError('DRIVE_LOOKUP_FAILED',502)
            found=r.json().get('files',[])
            if len(found)>1:
                raise AppError('DRIVE_DUPLICATE_OBJECTS',409)
            if found:
                identity=found[0]['id']
            else:
                boundary='osint-'+secrets.token_hex(12)
                metadata={'name':name,'parents':[folder], 'appProperties':{'osint_app':'heif-v0-4','case_id':'SEA-CHANGE','sha256':digest,'kind':kind}}
                body=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()+dump(metadata).encode()+
                      f'\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+content+f'\r\n--{boundary}--\r\n'.encode())
                r=client.post('https://www.googleapis.com/upload/drive/v3/files',
                    params={'uploadType':'multipart','fields':'id'},headers={**headers,'Content-Type':'multipart/related; boundary='+boundary},content=body)
                if r.status_code not in (200,201):
                    raise AppError('DRIVE_UPLOAD_FAILED',502)
                identity=r.json()['id']
            if not re.fullmatch(r'[A-Za-z0-9_-]{5,200}',identity):
                raise AppError('DRIVE_INVALID_RESPONSE',502)
            result=bytearray()
            with client.stream('GET',API+'/'+identity,headers=headers,params={'alt':'media'}) as r:
                if r.status_code!=200:
                    raise AppError('DRIVE_READBACK_FAILED',502)
                for chunk in r.iter_bytes():
                    result.extend(chunk)
                    if len(result)>len(content):
                        raise AppError('ARCHIVE_HASH_MISMATCH',502)
            if len(result)!=len(content) or sha(bytes(result))!=digest:
                raise AppError('ARCHIVE_HASH_MISMATCH',502)
        return {'file_id':identity,'sha256':digest,'size':len(content)}
