"""Official outbound adapters. Invoked only by approved, immutable jobs."""
import json
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from urllib.parse import urlparse
import httpx
from .core.runway import public_https


def api(method, url, **kwargs):
    try:
        with httpx.Client(timeout=90, follow_redirects=False, trust_env=False) as client:
            r=client.request(method,url,**kwargs)
        if r.status_code >= 400:
            raise RuntimeError(f'Anbieter meldet HTTP {r.status_code}. Zugang, Kontingent und Auftragsstatus prüfen.')
        return r
    except httpx.HTTPError:
        raise RuntimeError('Verbindung unterbrochen. Ergebnis beim Anbieter prüfen; keine automatische Wiederholung.') from None


def allowed_upload(url, suffixes):
    parsed=urlparse(url)
    host=parsed.hostname or ''
    if parsed.scheme!='https' or parsed.username or not any(host==s or host.endswith('.'+s) for s in suffixes):
        raise ValueError('Unerwartete Upload-Adresse.')
    return url


class Connectors:
    def __init__(self,state,projects):self.state=state;self.projects=projects
    def account(self,ident):
        account=self.state.record('account',ident)
        account['token']=self.state.secret('account:'+ident)
        return account

    def video(self,project):
        path=self.projects.folder(project)/'export'/'final.mp4'
        if not path.is_file():raise ValueError('Zuerst ein fertiges Video exportieren.')
        if path.stat().st_size>50_000_000:raise ValueError('Diese Ausbaustufe unterstützt Uploads bis 50 MB.')
        return path

    def creator(self,ident):
        a=self.account(ident)
        if a['platform']!='tiktok':raise ValueError('Kein TikTok-Konto.')
        result=api('POST','https://open.tiktokapis.com/v2/post/publish/creator_info/query/',headers={'Authorization':'Bearer '+a['token']},json={}).json()
        if result.get('error',{}).get('code')!='ok':raise ValueError('TikTok-Kontoinformationen konnten nicht abgefragt werden.')
        return result['data']

    def send_message(self,p):
        a=self.account(p['account'])
        if a['platform']=='telegram':
            result=api('POST','https://api.telegram.org/bot'+a['token']+'/sendMessage',json={'chat_id':p['recipient'],'text':p['text']}).json()
            if not result.get('ok'):raise ValueError('Telegram hat die Nachricht nicht bestätigt.')
            return 'Telegram bestätigt Nachricht '+str(result['result']['message_id'])
        if a['platform']=='email':
            if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',p['recipient']):raise ValueError('Ungültige Empfängeradresse.')
            message=EmailMessage();message['From']=a['identity'];message['To']=p['recipient'];message['Subject']=p.get('subject','Nachricht von JARVIS')
            message.set_content(p['text'])
            with smtplib.SMTP_SSL(a['host'],int(a.get('port',465)),context=ssl.create_default_context(),timeout=45) as smtp:
                smtp.login(a['identity'],a['token']);refused=smtp.send_message(message)
            if refused:raise RuntimeError('SMTP hat Empfänger zurückgewiesen.')
            return 'SMTP-Server hat die Nachricht angenommen; Zustellung nicht separat bestätigt.'
        raise ValueError('Konto unterstützt keinen Nachrichtenversand.')

    def publish(self,p,job):
        a=self.account(p['account']);file=self.video(p['project'])
        token=a['token'];headers={'Authorization':'Bearer '+token}
        platform=a['platform']
        if platform=='youtube':
            if p['privacy'] not in ('private','unlisted','public'):raise ValueError('YouTube-Sichtbarkeit fehlt.')
            result=api('POST','https://www.googleapis.com/upload/youtube/v3/videos',params={'uploadType':'resumable','part':'snippet,status'},
                headers=headers|{'X-Upload-Content-Length':str(file.stat().st_size),'X-Upload-Content-Type':'video/mp4'},
                json={'snippet':{'title':p['title'][:100],'description':p['caption'][:5000]},
                      'status':{'privacyStatus':p['privacy'],'selfDeclaredMadeForKids':bool(p.get('made_for_kids',False)),
                                'containsSyntheticMedia':True}})
            upload=allowed_upload(result.headers['Location'],['googleapis.com'])
            self.state.set('upload:'+job,{'platform':'youtube','url':upload})
            with file.open('rb') as f:
                data=api('PUT',upload,headers=headers|{'Content-Type':'video/mp4','Content-Length':str(file.stat().st_size)},content=f).json()
            return 'YouTube hat den Upload bestätigt: https://www.youtube.com/watch?v='+str(data['id'])+' (Verarbeitung ggf. noch aktiv).'
        if platform=='tiktok':
            info=self.creator(p['account'])
            if p['privacy'] not in info.get('privacy_level_options',[]):raise ValueError('TikTok-Sichtbarkeit ist nicht mehr verfügbar.')
            meta=file.parent/'render_info.json'
            if not meta.exists():raise ValueError('Video bitte mit dieser Version erneut exportieren.')
            seconds=json.loads(meta.read_text())['duration']
            if seconds>info['max_video_post_duration_sec']:raise ValueError('Video übersteigt die aktuelle TikTok-Dauergrenze.')
            size=file.stat().st_size
            result=api('POST','https://open.tiktokapis.com/v2/post/publish/video/init/',headers=headers,json={
                'post_info':{'title':p['caption'][:2200],'privacy_level':p['privacy'],
                    'disable_comment':True,'disable_duet':True,'disable_stitch':True,'is_aigc':True,
                    'brand_content_toggle':bool(p.get('brand_content_toggle',False)),'brand_organic_toggle':bool(p.get('brand_organic_toggle',False))},
                'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':size,'total_chunk_count':1}}).json()
            if result.get('error',{}).get('code')!='ok':raise ValueError('TikTok hat den Upload nicht angenommen: '+str(result.get('error',{}).get('code')))
            data=result['data'];upload=allowed_upload(data['upload_url'],['tiktokapis.com'])
            self.state.set('upload:'+job,{'platform':'tiktok','publish_id':data['publish_id']})
            with file.open('rb') as f:
                api('PUT',upload,headers={'Content-Type':'video/mp4','Content-Length':str(size),'Content-Range':f'bytes 0-{size-1}/{size}'},content=f)
            return 'TikTok hat die Datei angenommen. Veröffentlichung noch nicht bestätigt. Publish-ID: '+data['publish_id']
        if platform=='instagram':
            url=public_https(p['public_url'])
            version=a.get('version','')
            if not re.fullmatch(r'v\d+\.\d+',version) or not a['identity'].isdigit():raise ValueError('Instagram-ID/API-Version fehlt.')
            base='https://graph.instagram.com/'+version
            data=api('POST',base+'/'+a['identity']+'/media',headers=headers,data={'media_type':'REELS','video_url':url,'caption':p['caption'][:2200]}).json()
            container=str(data['id']);self.state.set('upload:'+job,{'platform':'instagram','container':container})
            for _ in range(40):
                status=api('GET',base+'/'+container,headers=headers,params={'fields':'status_code'}).json()['status_code']
                if status=='FINISHED':break
                if status in ('ERROR','EXPIRED'):raise RuntimeError('Instagram-Container: '+status)
                time.sleep(5)
            else:raise RuntimeError('Instagram verarbeitet noch. Container gespeichert; im Konto prüfen, nicht neu hochladen.')
            result=api('POST',base+'/'+a['identity']+'/media_publish',headers=headers,data={'creation_id':container}).json()
            return 'Instagram bestätigt Veröffentlichung: '+str(result['id'])
        raise ValueError('Dieses Konto unterstützt keinen Video-Upload.')

    def publish_status(self,job,account):
        a=self.account(account);saved=self.state.get('upload:'+job,{})
        if saved.get('platform')=='tiktok':
            return api('POST','https://open.tiktokapis.com/v2/post/publish/status/fetch/',
                headers={'Authorization':'Bearer '+a['token']},json={'publish_id':saved['publish_id']}).json()
        if saved.get('platform')=='instagram':
            return api('GET','https://graph.instagram.com/'+a['version']+'/'+saved['container'],
                headers={'Authorization':'Bearer '+a['token']},params={'fields':'status_code'}).json()
        raise ValueError('Status separat im Anbieterkonto prüfen.')
