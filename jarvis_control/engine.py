import hashlib
import json
import os
import platform
import shutil
import subprocess
import threading
import time
import httpx
from .core.local_ai import LocalAI
from .core.content import Projects, Pipeline, plan_local
from .core.runway import Runway
from .core.media import render
from .connectors import Connectors
from .browser import inspect_page


class Engine:
    def __init__(self,state):
        self.state=state;self.projects=Projects(state.root/'content');self.ai=LocalAI()
        self.connectors=Connectors(state,self.projects)
        self.stop=threading.Event();self.thread=None
        self.processes={}

    def start(self):
        self.state.recover()
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()

    def loop(self):
        while not self.stop.is_set():
            job=self.state.claim()
            if not job:self.stop.wait(0.5);continue
            try:
                result=self.execute(job)
                self.state.finish(job['id'],'done',result if isinstance(result,str) else json.dumps(result,ensure_ascii=False))
            except Exception as exc:
                # Outbound jobs are never auto-retried, including after restart.
                status='review' if job['kind'] in ('publish','message','generate') else 'failed'
                self.state.finish(job['id'],status,str(exc))

    def notify(self,job,text):
        with self.state.connect() as c:c.execute('UPDATE jobs SET result=?,updated=? WHERE id=?',(text,time.time(),job))

    def chat(self,p):
        history=list(reversed(self.state.records('chat',8)))
        text=p['text'];provider=p.get('provider','local')
        context=json.dumps({'memory':self.state.records('memory',20),'tasks':self.state.records('task',15)},ensure_ascii=False)[:10000]
        if provider=='openai':
            key=self.state.secret('openai')
            if not key:raise ValueError('OpenAI-API-Schlüssel fehlt.')
            with self.state.connect() as c:
                n=c.execute("SELECT COUNT(*) FROM jobs WHERE kind='chat' AND created>? AND json_extract(payload,'$.provider')='openai'",(time.time()-86400,)).fetchone()[0]
            if n>int(self.state.get('cloud_daily_limit',10)):raise ValueError('Tagesgrenze für Cloud-Anfragen erreicht.')
            model=self.state.get('cloud_model','gpt-4.1-mini')
            messages=[{'role':r['role'],'content':r['text'][:2000]} for r in history]
            messages.append({'role':'user','content':text})
            with httpx.Client(timeout=180,trust_env=False) as client:
                r=client.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key},json={
                    'model':model,'store':False,'max_output_tokens':1200,
                    'instructions':'Du bist JARVIS. Antworte auf Deutsch. Du hast in diesem Chat keine ausführbaren Tools. Behaupte keine ausgeführten Aktionen. Verweise auf Studio, Werkzeuge und Freigaben. Kontextdaten: '+context,
                    'input':messages})
            if r.status_code>=400:raise RuntimeError('OpenAI HTTP '+str(r.status_code)+': API-Guthaben, Schlüssel und Modell prüfen.')
            result=r.json();answer='\n'.join(t.get('text','') for o in result.get('output',[]) for t in o.get('content',[]) if t.get('type')=='output_text')
        else:
            answer=self.ai.chat(self.state.get('model','qwen2.5:3b'),history,context,text)
        if not answer:raise RuntimeError('Keine Textantwort erhalten.')
        self.state.add('chat',{'role':'user','text':text})
        self.state.add('chat',{'role':'assistant','text':answer})
        return answer

    def execute(self,job):
        p=job['payload'];kind=job['kind'];ident=job['id']
        if kind=='chat':return self.chat(p)
        if kind=='plan':
            answer=self.ai.chat(self.state.get('model','qwen2.5:3b'),[], '',
                'Erstelle einen konkreten Arbeitsplan auf Deutsch. Markiere externe Aktionen als Freigabe erforderlich. Ziel: '+p['goal'])
            self.state.add('plan',{'goal':p['goal'],'text':answer});return answer
        if kind=='script':
            plan=plan_local(self.ai,self.state.get('model','qwen2.5:3b'),p['topic'],p.get('audience',''),p.get('tone',''),p['count'])
            project=self.projects.create(plan)
            return {'project':project,'title':plan['title']}
        if kind=='generate':
            if p['fingerprint']!=self.projects.fingerprint(p['project']):raise ValueError('Plan nach Freigabe geändert.')
            Pipeline(self.projects,Runway(self.state.secret('runway'))).run(p['project'],p['limit'],p['fingerprint'],self.stop,lambda t:self.notify(ident,t))
            return 'Alle Video-Szenen heruntergeladen. Bereit für Export.'
        if kind=='render':
            music=None
            if p.get('music'):
                music=self.file_path(p['music'])
            result=render(self.projects,p['project'],p.get('preview',False),p.get('voice',os.name=='nt'),music,lambda t:self.notify(ident,t))
            return {'project':p['project'],'preview':p.get('preview',False),'file':result.name}
        if kind in ('publish','message'):
            account=self.state.record('account',p['account'])
            if account!=p['account_snapshot']:raise ValueError('Konto nach Entwurf geändert. Auftrag neu erstellen.')
            if kind=='publish':
                video=self.connectors.video(p['project'])
                if hashlib.sha256(video.read_bytes()).hexdigest()!=p['video_hash']:raise ValueError('Video nach Freigabe verändert.')
                return self.connectors.publish(p,ident)
            return self.connectors.send_message(p)
        if kind=='web':
            folder=self.state.root/'screenshots';folder.mkdir(exist_ok=True)
            result=inspect_page(p['url'],folder/(ident+'.png'))
            return result
        if kind=='file.write':
            path=self.file_path(p['name']);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('x',encoding='utf-8') as f:f.write(p['text'])
            return 'Datei gespeichert: '+p['name']
        if kind=='bot.start':
            bot=self.state.record('bot',p['bot'])
            if bot!=p['snapshot']:raise ValueError('Bot-Konfiguration geändert.')
            if p['bot'] in self.processes and self.processes[p['bot']].poll() is None:raise ValueError('Bot läuft bereits.')
            script=self.file_path(bot['script'])
            if hashlib.sha256(script.read_bytes()).hexdigest()!=bot['sha256']:raise ValueError('Bot-Skript verändert. Neu registrieren und freigeben.')
            if script.suffix!='.py':raise ValueError('Nur registrierte Python-Skripte im Arbeitsordner.')
            import sys
            logs=self.state.root/'bot-logs';logs.mkdir(exist_ok=True)
            with (logs/(p['bot']+'.log')).open('ab') as f:
                process=subprocess.Popen([sys.executable,str(script)],cwd=script.parent,stdout=f,stderr=f)
            self.processes[p['bot']]=process
            return 'Bot gestartet, PID '+str(process.pid)
        if kind=='bot.stop':
            process=self.processes.get(p['bot'])
            if process is None or process.poll() is not None:raise ValueError('Kein von diesem JARVIS gestarteter laufender Prozess.')
            process.terminate();return 'Beenden angefordert.'
        if kind=='reminder':
            self.state.add('notification',{'text':p['text']});return 'Erinnerung im Control Center angezeigt.'
        raise ValueError('Unbekannter Auftrag.')

    def file_path(self,name):
        root=self.state.root/'workspace';root.mkdir(exist_ok=True)
        path=(root/name).resolve()
        if not path.is_relative_to(root.resolve()) or path==root.resolve():raise ValueError('Datei außerhalb des Arbeitsordners.')
        if path.suffix.lower() not in ('.txt','.md','.json','.csv','.py','.wav','.mp3','.m4a','.ogg'):
            raise ValueError('Dateiformat nicht freigegeben.')
        return path
