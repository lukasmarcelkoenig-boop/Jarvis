"""Windows terminal bridge. Real and contest accounts cannot send orders."""
import math
import threading
import time
from .strategy import number,size_volume
MAGIC=26092351

class MT5Gateway:
    def __init__(self,module=None):self.mt5=module;self.lock=threading.RLock();self.path=''
    def connect(self,path=''):
        with self.lock:
            if self.mt5 is None:
                try:import MetaTrader5 as mt5
                except ImportError:raise ValueError('MT5-Modul fehlt. Unter Windows EINRICHTEN_TRADING.bat starten.') from None
                self.mt5=mt5
            if path!=self.path:
                self.mt5.shutdown();self.path=path
            ok=self.mt5.initialize(path=path,timeout=15000) if path else self.mt5.initialize(timeout=15000)
            if not ok:raise ValueError('MT5-Verbindung fehlt. Terminal öffnen und im Demokonto anmelden.')
            return self.account()
    def account(self):
        a=self.mt5.account_info()
        if a is None:raise ValueError('MT5 meldet kein Konto.')
        if a.trade_mode!=self.mt5.ACCOUNT_TRADE_MODE_DEMO:raise ValueError('Nur MT5-Demokonten erlaubt. Echtgeld-/Contest-Konto gesperrt.')
        for key in ('equity','balance','margin_free'):
            if number(getattr(a,key),key)<0:raise ValueError('Ungültiger Kontostand.')
        return a
    def identity(self,a):return str(a.login)+'@'+a.server
    def snapshot(self,a):
        return {k:getattr(a,k) for k in ('login','server','currency','balance','equity','margin_free') }|{'mode':'DEMO'}
    def positions(self):
        positions=self.mt5.positions_get()
        if positions is None:raise ValueError('Positionen nicht abrufbar; Handel gesperrt.')
        return positions
    def bars(self,symbol,count=300):
        if not self.mt5.symbol_select(symbol,True):raise ValueError('Broker-Symbol nicht gefunden: '+symbol)
        raw=self.mt5.copy_rates_from_pos(symbol,self.mt5.TIMEFRAME_M15,1,count)
        if raw is None or len(raw)<100:raise ValueError('Zu wenig M15-Historie für '+symbol+'. Chart im MT5-Terminal öffnen.')
        return [{k:(int(r[k]) if k=='time' else float(r[k])) for k in ('time','open','high','low','close')} for r in raw]
    def preview_order(self,symbol,signal,config,identity,baseline):
        m=self.mt5;a=self.account()
        if self.identity(a)!=identity:raise ValueError('MT5-Konto gewechselt. Agent gestoppt.')
        if not a.trade_allowed or not a.trade_expert:raise ValueError('Demokonto erlaubt keinen automatischen Handel.')
        terminal=m.terminal_info()
        if terminal is None or not terminal.connected or not terminal.trade_allowed or getattr(terminal,'tradeapi_disabled',True):raise ValueError('Algo-Trading / externe Python-API im MT5-Terminal nicht freigegeben.')
        if a.equity<=0 or baseline<=0:raise ValueError('Kein positives Demo-Eigenkapital.')
        if a.equity<=baseline*(1-config['daily_loss_pct']/100):raise ValueError('Tagesverlustgrenze erreicht.')
        positions=self.positions()
        if len(positions)>=2 or any(p.symbol==symbol for p in positions):raise ValueError('Positionsgrenze erreicht oder Symbol bereits belegt.')
        pending=m.orders_get()
        if pending is None or len(pending):raise ValueError('Offene/unklare Pending Orders vorhanden; keine neue Order.')
        # Other strategies cannot share the account safely with this risk ledger.
        if any(p.magic!=MAGIC for p in positions):raise ValueError('Fremde Position im Demokonto. Separates Konto verwenden.')
        info=m.symbol_info(symbol);tick=m.symbol_info_tick(symbol)
        if info is None or tick is None:raise ValueError('Symbol oder Tick fehlt.')
        now=time.time()
        if not -5<=now-tick.time<=90:raise ValueError('Tick veraltet oder Uhrzeit falsch.')
        if not 900<=now-signal['bar']<=2100:raise ValueError('M15-Signal veraltet oder Kerze nicht abgeschlossen.')
        bid=number(tick.bid);ask=number(tick.ask);atr=number(signal['atr'])
        if bid<=0 or ask<bid or ask-bid>atr*.15:raise ValueError('Spread zu hoch oder Kurs ungültig.')
        if signal['side'] not in ('BUY','SELL'):raise ValueError('Kein Handelssignal.')
        sign=1 if signal['side']=='BUY' else -1;entry=ask if sign==1 else bid
        if abs(entry-signal['close'])>atr:raise ValueError('Kurs zu weit vom Signal entfernt.')
        step=number(info.trade_tick_size)
        if step<=0:raise ValueError('Tick-Größe fehlt.')
        minimum=info.trade_stops_level*info.point+(ask-bid)+2*step
        distance=max(2*atr,minimum)
        sl=round((math.floor((entry-distance)/step)*step if sign==1 else math.ceil((entry+distance)/step)*step),info.digits)
        tp=round((math.ceil((entry+2*distance)/step)*step if sign==1 else math.floor((entry-2*distance)/step)*step),info.digits)
        if sl<=0 or tp<=0:raise ValueError('Ungültige Stop-Preise.')
        order_type=m.ORDER_TYPE_BUY if sign==1 else m.ORDER_TYPE_SELL
        per_lot=m.order_calc_profit(order_type,symbol,1.0,entry,sl)
        if per_lot is None or number(per_lot)>=0:raise ValueError('Stop-Risiko nicht berechenbar.')
        existing=0
        for p in positions:
            if p.sl<=0:raise ValueError('Offene Position ohne Stop. Agent gestoppt.')
            loss=m.order_calc_profit(p.type,p.symbol,p.volume,p.price_open,p.sl)
            if loss is None:raise ValueError('Offenes Risiko nicht berechenbar.')
            existing+=max(0,-number(loss))
        daily_headroom=max(0,a.equity-baseline*(1-config['daily_loss_pct']/100))
        # Reserve 20% for execution costs; real gaps can still exceed limits.
        budget=min(a.equity*config['risk_pct']/100,a.equity*.01-existing,daily_headroom-existing)*.8
        volume=size_volume(budget,abs(per_lot),info.volume_min,info.volume_max,info.volume_step)
        margin=m.order_calc_margin(order_type,symbol,volume,entry)
        if margin is None or number(margin)>a.margin_free*.8:raise ValueError('Unzureichende freie Margin.')
        filling=m.ORDER_FILLING_IOC if info.filling_mode&2 else m.ORDER_FILLING_FOK if info.filling_mode&1 else None
        if filling is None:raise ValueError('Kein unterstützter IOC/FOK-Ausführungsmodus.')
        request={'action':m.TRADE_ACTION_DEAL,'symbol':symbol,'volume':volume,'type':order_type,'price':entry,'sl':sl,'tp':tp,
            'deviation':20,'magic':MAGIC,'comment':'JARVIS DEMO M15','type_time':m.ORDER_TIME_GTC,'type_filling':filling}
        checked=m.order_check(request)
        if checked is None or checked.retcode!=0:raise ValueError('Broker-Prüfung fehlgeschlagen. Keine Order gesendet.')
        return request,{'risk_amount':round(volume*abs(per_lot),2),'currency':a.currency,'equity':a.equity,'identity':identity}
    def send(self,request,identity):
        # Must be called with gateway lock; account is checked again immediately before send.
        if self.identity(self.account())!=identity:raise ValueError('Konto vor Versand geändert.')
        result=self.mt5.order_send(request)
        if result is None:raise RuntimeError('Order-Ergebnis unklar. Im MT5-Terminal prüfen; keine Wiederholung.')
        allowed=(self.mt5.TRADE_RETCODE_DONE,self.mt5.TRADE_RETCODE_DONE_PARTIAL)
        if result.retcode not in allowed:raise RuntimeError('MT5-Rückgabe '+str(result.retcode)+'. Agent pausiert; Terminal prüfen.')
        return {k:getattr(result,k) for k in ('retcode','deal','order','volume','price')}
