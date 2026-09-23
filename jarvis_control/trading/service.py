import json
import math
import threading
import time
from datetime import datetime,timezone,timedelta
from .strategy import analyze,backtest,number
from .mt5_gateway import MT5Gateway,MAGIC

DEFAULT={'gold':'XAUUSD','bitcoin':'BTCUSD','terminal_path':'','risk_pct':0.25,'daily_loss_pct':2.0,'max_daily_trades':3,'weekdays_only':True}

class Trading:
    def __init__(self,state,gateway=None):
        self.state=state;self.gateway=gateway or MT5Gateway();self.stop=threading.Event();self.thread=None
        self.armed=False;self.identity=None;self.status={'connected':False,'armed':False,'message':'MT5-Demokonto verbinden.','signals':{},'positions':[]}
        with state.connect() as c:
            c.execute('CREATE INDEX IF NOT EXISTS records_kind_created ON records(kind,created)')
            c.execute('CREATE TABLE IF NOT EXISTS trading_attempts(identity TEXT,symbol TEXT,bar INTEGER,day TEXT,state TEXT,body TEXT,PRIMARY KEY(identity,symbol,bar))')
            pending=c.execute("SELECT COUNT(*) FROM trading_attempts WHERE state='sending'").fetchone()[0]
            if pending:
                c.execute("UPDATE trading_attempts SET state='review' WHERE state='sending'")
                self.status['message']='Unterbrochene Orders im MT5-Terminal prüfen; Neustart ist pausiert.'
    def config(self):return DEFAULT|self.state.get('trading_config',{})
    def configure(self,p):
        with self.gateway.lock:
            if self.armed:raise ValueError('Agent zuerst pausieren.')
            c=self.config()
            for key in ('gold','bitcoin','terminal_path'):
                if key in p:c[key]=str(p[key]).strip()
            if not c['gold'] or not c['bitcoin'] or c['gold']==c['bitcoin'] or max(len(c['gold']),len(c['bitcoin']))>64:raise ValueError('Zwei unterschiedliche Broker-Symbole eingeben.')
            if len(c['terminal_path'])>500:raise ValueError('Terminalpfad zu lang.')
            for key,low,high in [('risk_pct',.05,1),('daily_loss_pct',.5,5)]:
                c[key]=number(p.get(key,c[key]))
                if not low<=c[key]<=high:raise ValueError(f'{key}: {low} bis {high}.')
            n=number(p.get('max_daily_trades',c['max_daily_trades']))
            if not n.is_integer() or not 1<=n<=10:raise ValueError('1 bis 10 Demo-Orderversuche pro UTC-Tag.')
            c['max_daily_trades']=int(n)
            if 'weekdays_only' in p:
                if type(p['weekdays_only']) is not bool:raise ValueError('Wochentagsoption muss boolesch sein.')
                c['weekdays_only']=p['weekdays_only']
            self.state.set('trading_config',c);return c
    def connect(self):
        with self.gateway.lock:
            try:a=self.gateway.connect(self.config()['terminal_path'])
            except Exception as exc:
                self.status.update(connected=False,message=str(exc));raise
            if self.armed and self.identity!=self.gateway.identity(a):self.armed=False
            self.status.update(connected=True,account=self.gateway.snapshot(a),message='MT5-Demokonto verbunden.',armed=self.armed)
            self.inspect(a,send=False)
            return self.snapshot()
    def start_thread(self):
        self.thread=threading.Thread(target=self.loop,daemon=True,name='jarvis-trading');self.thread.start()
    def arm(self,consent):
        if consent is not True:raise ValueError('Automatische Orders im Demokonto ausdrücklich bestätigen.')
        with self.gateway.lock:
            a=self.gateway.connect(self.config()['terminal_path'])
            with self.state.connect() as c:
                unresolved=c.execute("SELECT COUNT(*) FROM trading_attempts WHERE identity=? AND state IN ('review','sending')",(self.gateway.identity(a),)).fetchone()[0]
            if unresolved:raise ValueError('Unklare frühere Order zuerst mit MT5 abgleichen und im Journal bestätigen.')
            self.identity=self.gateway.identity(a);self.armed=True
            self.status.update(armed=True,connected=True,account=self.gateway.snapshot(a),message='Demo-Agent aktiv. Prüft alle 30 Sekunden abgeschlossene M15-Kerzen.')
            self.state.add('trading_journal',{'event':'agent_start','identity':self.identity,'config':self.config()})
    def pause(self,message='Pausiert. Offene Positionen bleiben mit ihren Stops bestehen.'):
        with self.gateway.lock:
            self.armed=False;self.status.update(armed=False,message=message)
    def loop(self):
        while not self.stop.is_set():
            if self.armed:
                try:
                    with self.gateway.lock:
                        if self.armed:
                            a=self.gateway.connect(self.config()['terminal_path'])
                            if self.gateway.identity(a)!=self.identity:raise ValueError('Kontowechsel erkannt.')
                            self.inspect(a,send=True)
                except Exception as exc:self.pause('Agent pausiert: '+self.state.redact(str(exc)))
            self.stop.wait(30)
    def baseline(self,a):
        day=datetime.now(timezone.utc).date().isoformat();key='trading_day:'+self.gateway.identity(a)+':'+day
        base=self.state.get(key)
        if base is None:
            base={'equity':number(a.equity),'observed':time.time()};self.state.set(key,base)
        return day,base['equity']
    def sync_deals(self,a):
        m=self.gateway.mt5;now=datetime.now(timezone.utc)
        deals=m.history_deals_get(now-timedelta(days=90),now)
        if deals is None:raise ValueError('Trade-Historie nicht abrufbar; Journal unvollständig.')
        identity=self.gateway.identity(a)
        with self.state.connect() as c:
            for d in deals:
                if d.magic!=MAGIC:continue
                body={k:getattr(d,k) for k in ('ticket','order','time','type','entry','position_id','volume','price','commission','swap','profit','fee','symbol')}
                body['identity']=identity
                key='deal:'+identity+':'+str(d.ticket)
                c.execute('INSERT OR IGNORE INTO records VALUES (?,?,?,?)',(key,'trading_deal',json.dumps(body),float(d.time)))
    def inspect(self,a,send=False):
        cfg=self.config();day,base=self.baseline(a)
        self.sync_deals(a)
        positions=self.gateway.positions()
        self.status.update(connected=True,account=self.gateway.snapshot(a),checked=time.time(),baseline=base,
            drawdown_pct=round(max(0,(base-a.equity)/base*100),3) if base>0 else None,
            positions=[{k:getattr(p,k) for k in ('ticket','symbol','type','volume','price_open','sl','tp','profit','magic')} for p in positions])
        if send and a.equity<=base*(1-cfg['daily_loss_pct']/100):raise ValueError('Tagesverlustgrenze erreicht; keine neuen Trades.')
        for symbol in (cfg['gold'],cfg['bitcoin']):
            try:
                bars=self.gateway.bars(symbol);signal=analyze(bars)
                self.status['signals'][symbol]=signal|{'checked':time.time()}
                seen='observed:'+self.gateway.identity(a)+':'+symbol
                if self.state.get(seen)!=signal['bar']:
                    self.state.add('trading_journal',{'event':'analysis','symbol':symbol,'identity':self.gateway.identity(a),'signal':signal})
                    self.state.set(seen,signal['bar'])
                if not send or signal['side']=='WAIT':continue
                if cfg['weekdays_only'] and datetime.now(timezone.utc).weekday()>=5:
                    self.status['signals'][symbol]['blocked']='Wochenendpause (UTC).';continue
                with self.state.connect() as c:
                    n=c.execute('SELECT COUNT(*) FROM trading_attempts WHERE identity=? AND day=?',(self.identity,day)).fetchone()[0]
                    duplicate=c.execute('SELECT 1 FROM trading_attempts WHERE identity=? AND symbol=? AND bar=?',(self.identity,symbol,signal['bar'])).fetchone()
                if duplicate:continue
                if n>=cfg['max_daily_trades']:self.status['signals'][symbol]['blocked']='Tagesanzahl erreicht.';continue
                try:request,risk=self.gateway.preview_order(symbol,signal,cfg,self.identity,base)
                except ValueError as exc:
                    self.status['signals'][symbol]['blocked']=str(exc);continue
                body={'request':request,'risk':risk,'signal':signal,'created':time.time()}
                # Reserve before sending; an unknown outcome is NEVER retried.
                with self.state.connect() as c:
                    inserted=c.execute('INSERT OR IGNORE INTO trading_attempts VALUES (?,?,?,?,?,?)',(self.identity,symbol,signal['bar'],day,'sending',json.dumps(body))).rowcount
                if not inserted:continue
                try:
                    if not self.armed or self.stop.is_set():raise RuntimeError('Agent vor Versand gestoppt; Reservierung bitte prüfen.')
                    result=self.gateway.send(request,self.identity);body['result']=result;status='sent'
                except Exception as exc:
                    status='review';body['error']=self.state.redact(str(exc))
                    with self.state.connect() as c:c.execute('UPDATE trading_attempts SET state=?,body=? WHERE identity=? AND symbol=? AND bar=?',(status,json.dumps(body),self.identity,symbol,signal['bar']))
                    raise
                with self.state.connect() as c:c.execute('UPDATE trading_attempts SET state=?,body=? WHERE identity=? AND symbol=? AND bar=?',(status,json.dumps(body),self.identity,symbol,signal['bar']))
                self.state.add('trading_journal',{'event':'demo_order','identity':self.identity,'symbol':symbol,**body})
                self.status['message']='Demo-Order vom Broker bestätigt; Position im Terminal prüfen.'
            except Exception as exc:
                self.status['signals'][symbol]={'side':'ERROR','reason':self.state.redact(str(exc)),'checked':time.time()}
                if send:raise
        self.status['armed']=self.armed
    def acknowledge(self,p):
        if p.get('checked_in_mt5') is not True:raise ValueError('Ergebnis zuerst im MT5-Terminal prüfen.')
        with self.gateway.lock:
            if self.armed:raise ValueError('Zuerst pausieren.')
            with self.state.connect() as c:
                changed=c.execute("UPDATE trading_attempts SET state='reviewed' WHERE identity=? AND symbol=? AND bar=? AND state='review'",(p.get('identity'),p.get('symbol'),p.get('bar'))).rowcount
            if not changed:raise ValueError('Kein ungeklärter Auftrag gefunden.')
            self.state.add('trading_journal',{'event':'manual_reconciliation','identity':p['identity'],'symbol':p['symbol'],'bar':p['bar']})
    def snapshot(self):
        # Snapshot is JSON-copied so HTTP serialization cannot race with nested updates.
        with self.gateway.lock:
            with self.state.connect() as c:
                attempts=[dict(r)|{'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM trading_attempts ORDER BY day DESC,bar DESC LIMIT 50')]
            deals=self.state.records('trading_deal',500)
            account=self.status.get('account',{});identity=str(account.get('login',''))+'@'+account.get('server','')
            current=[d for d in deals if d['identity']==identity]
            net=sum(d['profit']+d['swap']+d['commission']+d['fee'] for d in current)
            return json.loads(json.dumps({'config':self.config(),'status':self.status,'attempts':attempts,'journal':self.state.records('trading_journal',40),
                'deals':current[:80],'metrics':{'net_recorded':round(net,2),'deal_count':len(current),'scope':'Letzte höchstens 500 gespeicherte Deals, Konto gefiltert; keine vollständige Performance-Historie.'}}))
    def run_backtest(self,symbol):
        with self.gateway.lock:
            if symbol not in (self.config()['gold'],self.config()['bitcoin']):raise ValueError('Unbekanntes Symbol.')
            self.gateway.connect(self.config()['terminal_path']);bars=self.gateway.bars(symbol,3000)
            tick=self.gateway.mt5.symbol_info_tick(symbol)
            if tick is None:raise ValueError('Aktueller Spread fehlt.')
            cost=number(tick.ask)-number(tick.bid)
            result=backtest(bars,cost)
            result.update(symbol=symbol,cost_price=cost,method='Fester heutiger Spread auf Historie; kein historisches Tick-Backtesting.')
            self.state.add('trading_backtest',result);return result
    def context(self):
        # Bounded evidence for the LLM. No access to order_send or configuration.
        return {'status':self.status,'recent_decisions':self.state.records('trading_journal',5),'recent_deals':self.state.records('trading_deal',10),
            'research':self.state.records('research',6),'briefing':self.state.records('research_brief',1),
            'warning':'DEMO. Strategieregeln sind experimentell. Research ist keine Echtzeit-Kursquelle; keine automatischen Modellgewichtsänderungen.'}
