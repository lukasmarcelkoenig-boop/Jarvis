"""Authenticated single-owner control center. No public deployment by default."""
import hashlib
import json
import math
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .state import State
from .engine import Engine


def create_app(root=None, worker=True):
    state=State(root or os.environ.get('JARVIS_DATA','.jarvis-data'))
    engine=Engine(state)
    @asynccontextmanager
    async def lifespan(app):
        if worker:engine.start()
        yield
        engine.stop.set()
        if engine.thread:engine.thread.join(timeout=3)
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.store=state;app.state.engine=engine
    attempts={}

    @app.middleware('http')
    async def guard(request,call_next):
        origin=state.get('public_url','').rstrip('/')
        allowed={'127.0.0.1','localhost'}
        if origin:allowed.add(urlparse(origin).hostname)
        if request.url.hostname not in allowed:return JSONResponse({'detail':'Host nicht freigegeben.'},400)
        if request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('x-jarvis')!='1':return JSONResponse({'detail':'Anfrage nicht aus Control Center.'},403)
            incoming=request.headers.get('origin')
            if incoming and incoming not in (str(request.base_url).rstrip('/'),origin):return JSONResponse({'detail':'Fremder Ursprung.'},403)
            if int(request.headers.get('content-length','0'))>100000:return JSONResponse({'detail':'Anfrage zu groß.'},413)
        if request.url.path.startswith('/api/') and request.url.path!='/api/login':
            if not state.session_ok(request.cookies.get('jarvis','')):return JSONResponse({'detail':'Bitte anmelden.'},401)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api/') else 'no-cache'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request,exc):return JSONResponse({'detail':state.redact(str(exc))},400)

    @app.post('/api/login')
    def login(p:dict,request:Request):
        address=request.client.host;now=time.time()
        attempts[address]=[t for t in attempts.get(address,[]) if now-t<300]
        if len(attempts[address])>=10:raise HTTPException(429,'Zu viele Versuche. Fünf Minuten warten.')
        token=state.login(str(p.get('token','')))
        if not token:attempts[address].append(now);raise HTTPException(401,'Anmeldecode stimmt nicht.')
        attempts.pop(address,None)
        r=JSONResponse({'ok':True});r.set_cookie('jarvis',token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=43200)
        return r

    @app.post('/api/logout')
    def logout(request:Request):
        state.logout(request.cookies.get('jarvis',''));r=JSONResponse({'ok':True});r.delete_cookie('jarvis');return r

    @app.get('/api/state')
    def status():
        projects=[]
        for r in engine.projects.query('SELECT id,created FROM projects ORDER BY created DESC LIMIT 40'):
            ident=r['id'];projects.append(r|{'plan':engine.projects.load(ident),'estimate':engine.projects.estimate(ident),'scenes':engine.projects.states(ident),
                'preview':(engine.projects.folder(ident)/'vorschau'/'final.mp4').exists(),'export':(engine.projects.folder(ident)/'export'/'final.mp4').exists()})
        return {'version':'2.0.0-dev.1','jobs':state.jobs(),'projects':projects,
            'records':{kind:state.records(kind) for kind in ('chat','task','memory','plan','account','bot','notification')},
            'settings':{k:state.get(k,v) for k,v in {'model':'qwen2.5:3b','cloud_model':'gpt-4.1-mini','cloud_daily_limit':10,'public_url':''}.items()},
            'connected':{k:bool(state.secret(k)) for k in ('openai','runway')},'windows':os.name=='nt',
            'bots':{k:p.poll() is None for k,p in engine.processes.items()}}

    @app.get('/api/models')
    def models():
        try:return {'models':engine.ai.models()}
        except Exception as exc:raise ValueError(str(exc)) from exc

    @app.post('/api/settings')
    def settings(p:dict):
        for k in ('model','cloud_model'):
            if k in p:state.set(k,required(p,k,120))
        if 'cloud_daily_limit' in p:
            n=int(p['cloud_daily_limit'])
            if not 0<=n<=1000:raise ValueError('Tagesgrenze 0 bis 1000.')
            state.set('cloud_daily_limit',n)
        if 'public_url' in p:
            u=str(p['public_url']).rstrip('/');v=urlparse(u)
            if u and (v.scheme!='https' or not v.hostname or v.path or v.username or v.query or v.fragment):raise ValueError('Vollständige HTTPS-Adresse ohne Pfad eingeben.')
            state.set('public_url',u)
        for key in ('openai','runway'):
            if p.get(key):state.secret(key,required(p,key,1000))
        return {'ok':True}

    @app.post('/api/records/{kind}')
    def add(kind:str,p:dict):
        if kind in ('task','memory'):body={'text':required(p,'text',5000),'done':False}
        elif kind=='bot':
            script=engine.file_path(required(p,'script',200))
            if script.suffix!='.py' or not script.is_file():raise ValueError('Eigenes geprüftes Python-Skript zuerst in .jarvis-data/workspace ablegen.')
            body={'name':required(p,'name',100),'script':p['script'],'sha256':hashlib.sha256(script.read_bytes()).hexdigest()}
        elif kind=='account':
            if p.get('platform') not in ('telegram','email','youtube','tiktok','instagram'):raise ValueError('Unbekannter Dienst.')
            body={k:str(p.get(k,''))[:300] for k in ('platform','name','identity','host','version')}
            body['name']=required(p,'name',100);body['port']=465
            token=required(p,'token',4000)
            ident=state.add(kind,body);state.secret('account:'+ident,token);return {'id':ident}
        else:raise ValueError('Eintragstyp nicht freigegeben.')
        return {'id':state.add(kind,body)}

    @app.post('/api/tasks/{ident}/done')
    def done(ident:str):
        p=state.record('task',ident);p['done']=not p.get('done',False);state.update_record('task',ident,p);return {'ok':True}

    @app.post('/api/records/{kind}/{ident}/delete')
    def delete(kind:str,ident:str):
        if kind not in ('task','memory','bot','account'):raise ValueError('Nicht löschbar.')
        state.delete(kind,ident)
        if kind=='account':state.secret('account:'+ident,'')
        return {'ok':True}

    @app.post('/api/projects')
    def project(p:dict):return {'id':engine.projects.create(p)}

    @app.post('/api/projects/{ident}')
    def edit_project(ident:str,p:dict):engine.projects.save(ident,p);return {'ok':True}

    @app.get('/api/creator/{ident}')
    def creator(ident:str):return engine.connectors.creator(ident)

    @app.post('/api/jobs')
    def propose(p:dict):
        kind=p.get('kind');body={};immediate=False
        if kind in ('chat','plan','script'):
            immediate=True
            if kind=='chat':
                provider=p.get('provider','local')
                if provider not in ('local','openai'):raise ValueError('Unbekannter KI-Anbieter.')
                if provider=='openai' and p.get('cost_consent') is not True:raise ValueError('Kostenpflichtige Cloud-Nutzung bestätigen.')
                body={'text':required(p,'text',8000),'provider':provider}
            elif kind=='plan':body={'goal':required(p,'goal',4000)}
            else:
                count=int(p.get('count',4))
                if not 2<=count<=6:raise ValueError('2 bis 6 Szenen auswählen.')
                body={'topic':required(p,'topic',1500),'audience':str(p.get('audience',''))[:300],'tone':str(p.get('tone',''))[:300],'count':count}
        elif kind in ('generate','render','publish'):
            ident=required(p,'project',32);plan=engine.projects.load(ident);body={'project':ident}
            if kind=='generate':
                limit=float(p.get('limit',0))
                if not math.isfinite(limit) or not engine.projects.estimate(ident)<=limit<=100:raise ValueError('Projektlimit muss Schätzung decken und höchstens 100 USD betragen.')
                body.update(limit=limit,fingerprint=engine.projects.fingerprint(ident),estimated_usd=engine.projects.estimate(ident),title=plan['title'])
            elif kind=='render':body.update(preview=bool(p.get('preview',False)),voice=bool(p.get('voice',False)),music=str(p.get('music',''))[:200])
            else:
                account=state.record('account',required(p,'account',24))
                if account['platform'] not in ('youtube','tiktok','instagram'):raise ValueError('Kein Publishing-Konto.')
                body.update(account=p['account'],account_snapshot=account,video_hash=hashlib.sha256(engine.connectors.video(ident).read_bytes()).hexdigest(),
                    title=plan['title'],caption=plan['caption'],privacy=required(p,'privacy',80),public_url=str(p.get('public_url',''))[:2000],made_for_kids=bool(p.get('made_for_kids',False)),brand_content_toggle=bool(p.get('brand_content_toggle',False)),brand_organic_toggle=bool(p.get('brand_organic_toggle',False)))
        elif kind=='message':
            account=state.record('account',required(p,'account',24))
            if account['platform'] not in ('telegram','email'):raise ValueError('Kein Nachrichtenkonto.')
            body={'account':p['account'],'account_snapshot':account,'recipient':required(p,'recipient',200),'text':required(p,'text',4000),'subject':str(p.get('subject','Nachricht von JARVIS'))[:200]}
        elif kind=='web':body={'url':required(p,'url',2000)}
        elif kind=='file.write':
            name=required(p,'name',200)
            if engine.file_path(name).suffix not in ('.txt','.md','.json','.csv'):raise ValueError('Über das Web nur Textdateien anlegen.')
            body={'name':name,'text':required(p,'text',50000)}
        elif kind in ('bot.start','bot.stop'):
            bot=required(p,'bot',24);body={'bot':bot,'snapshot':state.record('bot',bot)}
        elif kind=='reminder':body={'text':required(p,'text',2000)}
        else:raise ValueError('Unbekannte Aktion.')
        return {'id':state.propose(kind,body,immediate)}

    @app.post('/api/jobs/{ident}/{action}')
    def approval(ident:str,action:str,p:dict):
        if action=='approve':
            due=p.get('due')
            if due is not None and (not math.isfinite(float(due)) or not time.time()-60<=float(due)<=time.time()+31536000):raise ValueError('Termin muss innerhalb des nächsten Jahres liegen.')
            state.approve(ident,due)
        elif action=='cancel':state.cancel(ident)
        else:raise ValueError('Unbekannte Aktion.')
        return {'ok':True}

    @app.get('/api/media/{ident}/{variant}')
    def media(ident:str,variant:str):
        if variant not in ('vorschau','export'):raise ValueError('Ungültige Variante.')
        path=engine.projects.folder(ident)/variant/'final.mp4'
        if not path.exists():raise HTTPException(404)
        return FileResponse(path,media_type='video/mp4')

    @app.get('/api/screenshot/{ident}')
    def screenshot(ident:str):
        import re
        if not re.fullmatch('[0-9a-f]{24}',ident):raise HTTPException(404)
        path=state.root/'screenshots'/(ident+'.png')
        if not path.exists():raise HTTPException(404)
        return FileResponse(path)

    app.mount('/',StaticFiles(directory=Path(__file__).parent/'static',html=True),name='static')
    return app


def required(p,key,limit):
    value=p.get(key)
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError(f'{key}: Text mit 1 bis {limit} Zeichen erforderlich.')
    return value.strip()
