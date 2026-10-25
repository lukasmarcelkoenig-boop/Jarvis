'use strict';
// Stream Director UI. Uses the same authenticated /api/* transport as JARVIS.
(function () {
  const h = value => String(value ?? '').replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const opts = (values, selected) => values.map(([value,label]) =>
    '<option value="'+h(value)+'"'+(String(selected)===String(value)?' selected':'')+'>'+h(label)+'</option>').join('');
  const field = (name, label, value, type='text') =>
    '<label>'+h(label)+'<input name="'+name+'" type="'+type+'" value="'+h(value ?? '')+'"></label>';
  const number = (name, label, value, min, max) =>
    '<label>'+h(label)+'<input name="'+name+'" type="number" min="'+min+'" max="'+max+'" value="'+h(value)+'" required></label>';

  window.streamDirectorView = function (snapshot, accounts) {
    if (!snapshot) return '<div class="card">Stream Director noch nicht erreichbar. Starte JARVIS nach dem Update neu.</div>';
    const c = snapshot.config, clips = snapshot.clips || [];
    const youtube = (accounts || []).filter(a => a.platform === 'youtube');
    const accountOpts = [['','Ohne Upload / nur lokal'], ...youtube.map(a => [a.id,a.name])];
    return '<div class="hero card stream-hero"><p class="eyebrow">HOLLESTAR · CREATOR AUTOMATION</p>'+
      '<h1>JARVIS <span>Stream Director</span></h1>'+
      '<p>OBS-Replays automatisch auswerten, echte Stream-Highlights erkennen und fertige 9:16-Shorts lokal exportieren.</p>'+
      '<div class="row">'+
        '<span class="badge '+(snapshot.online?'':'warn')+'">'+(snapshot.online?'● Twitch / OBS live':'● OBS derzeit offline')+'</span>'+
        '<span class="badge">'+(snapshot.running?'Überwachung aktiv':'Überwachung pausiert')+'</span>'+
      '</div><div class="row">'+
        '<button type="button" data-stream-action="start">▶ Stream Director starten</button>'+
        '<button type="button" class="quiet" data-stream-action="pause">■ Pausieren</button>'+
        '<button type="button" class="quiet" data-stream-action="check-obs">OBS testen</button>'+
        '<button type="button" class="quiet" data-stream-action="clip">Jetzt Clip sichern</button>'+
      '</div></div>'+
      '<div class="cards">'+
        '<div class="card"><span class="stat">'+h(snapshot.created_this_stream)+'</span><p>Clips dieser Streamsession</p></div>'+
        '<div class="card"><span class="stat">'+h(clips.filter(x=>x.status==='ready'||x.status==='uploaded'||x.status==='upload_queued').length)+'</span><p>Fertige Shorts</p></div>'+
        '<div class="card"><span class="stat">'+h(snapshot.queue)+'</span><p>In Schnitt-Warteschlange</p></div>'+
      '</div>'+
      (snapshot.last_error?'<div class="card stream-alert"><strong>OBS-Hinweis:</strong> '+h(snapshot.last_error)+'</div>':'')+
      (snapshot.twitch_error?'<div class="card stream-alert"><strong>Twitch-Hinweis:</strong> '+h(snapshot.twitch_error)+'</div>':'')+
      '<div class="grid"><div class="card"><h3>OBS + Twitch einrichten</h3>'+
        '<p>OBS 30 oder neuer: Werkzeuge → WebSocket-Servereinstellungen. Replay Buffer im OBS-Ausgabe-Menü aktivieren und Dauer mindestens 120 Sekunden einstellen.</p>'+
        '<form data-form="stream-config" class="stack">'+
          field('channel','Twitch-Kanal (Login, ohne twitch.tv/) ',c.channel)+
          field('client_id','Twitch Client-ID',c.client_id)+
          field('twitch_token','Twitch User Access Token ('+(snapshot.twitch_token_set?'bereits hinterlegt':'fehlt')+')','', 'password')+
          field('obs_host','OBS-WebSocket-Host',c.obs_host)+
          number('obs_port','OBS-Port',c.obs_port,1,65535)+
          field('obs_password','OBS-WebSocket-Passwort ('+(snapshot.obs_password_set?'hinterlegt':'optional')+')','', 'password')+
          field('output_dir','Shorts-Ordner (absoluter Pfad, z. B. D:\\JARVIS-Shorts)',c.output_dir)+
          '<hr><h3>Highlight-Erkennung & Schnitt</h3>'+
          number('capture_interval','Prüfintervall (Sekunden)',c.capture_interval,35,180)+
          number('short_seconds','Short-Dauer (Sekunden)',c.short_seconds,15,60)+
          number('min_score','Highlight-Mindestscore (30–100)',c.min_score,30,100)+
          number('max_shorts','Maximale Shorts pro Stream',c.max_shorts,1,20)+
          '<label>Videoauflösung<select name="resolution">'+opts([[720,'720 × 1280 (geringere PC-Last)'],[1080,'1080 × 1920 (Full HD)']],c.resolution)+'</select></label>'+
          '<label class="check"><input type="checkbox" name="keep_obs_replays" '+(c.keep_obs_replays?'checked':'')+'>OBS-Originale unverändert behalten</label>'+
          '<hr><h3>Optionaler automatischer YouTube-Upload</h3>'+
          '<label>YouTube-Konto<select name="publish_account">'+opts(accountOpts,c.publish_account)+'</select></label>'+
          '<label>Uploads als<select name="publish_privacy">'+opts([['private','Privat'],['unlisted','Nicht gelistet'],['public','Öffentlich']],c.publish_privacy)+'</select></label>'+
          '<button type="submit">Einstellungen speichern</button>'+
        '</form></div>'+
        '<div class="card"><h3>Veröffentlichung</h3>'+
          '<p>Automatischer Upload ist '+(c.auto_publish?'<strong>AKTIV</strong>':'<strong>deaktiviert</strong>')+
          '. Erst nach gesonderter Bestätigung werden fertige Shorts in die bestehende YouTube-Auftragswarteschlange gestellt.</p>'+
          '<div class="row"><button type="button" data-stream-action="enable-publish">Automatischen YouTube-Upload aktivieren</button>'+
          '<button type="button" class="quiet" data-stream-action="disable-publish">Upload-Automatik aus</button></div>'+
          '<hr><h3>Was wird erkannt?</h3><p>Akustische Lautstärkesprünge und optional Twitch-Chat-Spitzen. Die Analyse läuft lokal und priorisiert mögliche spannende Momente.</p>'+
          '<p><small>Dies ist eine erste automatische Heuristik, noch keine zuverlässige visuelle Bosskill- oder Mimik-Erkennung. Für Chat-Events benötigt das Twitch-Token die Berechtigung <code>user:read:chat</code>. Token nicht im GitHub-Code speichern.</small></p>'+
          '<p><small>Aktuelle Ausgabe: '+h(c.output_dir || 'JARVIS-Datenordner / stream-director')+'</small></p>'+
        '</div></div>'+
        '<div class="card"><div class="row between"><h3>Deine Shorts</h3><span class="badge">'+h(clips.length)+' Clips</span></div>'+
        (clips.length?'<div class="stream-clips">'+clips.map(clip=>{
          const ready=['ready','uploaded','upload_queued','upload_review'].includes(clip.status);
          return '<article class="item"><div class="row between"><strong>'+h(clip.title || 'Gaming Highlight')+'</strong>'+
            '<span class="badge '+(clip.status==='failed'?'warn':'')+'">'+h(clip.status)+'</span></div>'+
            '<small>Highlight-Score: '+h(clip.score)+'/100 · '+h(clip.game||'Gaming')+'</small>'+
            (clip.error?'<p>'+h(clip.error)+'</p>':'')+
            (ready?'<video controls preload="none" src="/api/stream/clips/'+h(clip.id)+'/video"></video>'+
              '<p><a download="HOLLESTAR_'+h(clip.id)+'.mp4" href="/api/stream/clips/'+h(clip.id)+'/video">MP4 öffnen / speichern</a></p>':'')+
            '</article>';
        }).join('')+'</div>':'<p>Noch keine Clips. Starte OBS und die Stream-Überwachung.</p>')+
        '</div>';
  };

  async function call(path, body) {
    const response = await fetch('/api/stream/'+path, {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json','X-Jarvis':'1'},
      body: JSON.stringify(body || {})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Stream-Director-Aktion fehlgeschlagen.');
    return result;
  }
  async function apply(fn) {
    try { await fn(); window.jarvisNotice('Stream-Director-Aktion ausgeführt.'); await window.jarvisRefresh(); }
    catch (error) { window.jarvisNotice(error.message); }
  }
  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (form.dataset.form !== 'stream-config') return;
    event.preventDefault();event.stopImmediatePropagation();
    apply(async () => {
      const p = Object.fromEntries(new FormData(form));
      for(const key of ['obs_port','capture_interval','short_seconds','min_score','max_shorts','resolution'])
        p[key] = Number(p[key]);
      p.keep_obs_replays = !!form.elements.keep_obs_replays.checked;
      await call('configure',p);
    });
  }, true);
  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-stream-action]');
    if (!button) return;
    event.preventDefault();event.stopImmediatePropagation();
    const action=button.dataset.streamAction;
    apply(async () => {
      if(action==='enable-publish') {
        if(!confirm('Automatische YouTube-Uploads aktivieren? Fertige Shorts können entsprechend der eingestellten Sichtbarkeit auch öffentlich erscheinen.'))return;
        await call('auto-publish',{enable:true,confirmation:'AUTO_PUBLISH_YOUTUBE'});
      } else if(action==='disable-publish') {
        await call('auto-publish',{enable:false});
      } else {
        const result=await call(action,{});
        if(action==='check-obs')window.jarvisNotice('OBS: Streaming '+(result.streaming?'ja':'nein')+', Replay Buffer '+(result.replay?'an':'aus'));
      }
    });
  }, true);
})();