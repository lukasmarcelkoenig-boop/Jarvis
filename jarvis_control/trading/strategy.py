"""Deterministic, experimental M15 baseline. No profitability claim or LLM orders."""
import math
from decimal import Decimal, ROUND_FLOOR


def number(value, name='Wert'):
    result=float(value)
    if not math.isfinite(result):raise ValueError(name+' ist nicht endlich.')
    return result


def ema(values,period):
    out=[values[0]];alpha=2/(period+1)
    for x in values[1:]:out.append(alpha*x+(1-alpha)*out[-1])
    return out


def analyze(bars):
    if len(bars)<100:raise ValueError('Mindestens 100 abgeschlossene M15-Kerzen erforderlich.')
    times=[int(b['time']) for b in bars]
    if any(a>=b for a,b in zip(times,times[1:])):raise ValueError('Kerzenzeiten sind nicht eindeutig aufsteigend.')
    closes=[number(b['close']) for b in bars]
    if min(closes)<=0:raise ValueError('Ungültige Kurse.')
    fast=ema(closes,20);slow=ema(closes,50)
    ranges=[]
    for i in range(len(bars)-14,len(bars)):
        high=number(bars[i]['high']);low=number(bars[i]['low'])
        if low<=0 or high<low or not low<=closes[i]<=high:raise ValueError('Ungültige OHLC-Kerze.')
        ranges.append(max(high-low,abs(high-closes[i-1]),abs(low-closes[i-1])))
    atr=sum(ranges)/14
    if atr<=0:raise ValueError('Keine messbare Schwankung.')
    side='WAIT'
    if fast[-2]<=slow[-2] and fast[-1]>slow[-1]:side='BUY'
    if fast[-2]>=slow[-2] and fast[-1]<slow[-1]:side='SELL'
    return {'side':side,'bar':times[-1],'close':closes[-1],'ema20':fast[-1],'ema50':slow[-1],'atr':atr,
        'reason':'Neues EMA20/50-Kreuz auf abgeschlossener M15-Kerze.' if side!='WAIT' else 'Kein neues EMA20/50-Kreuz. Abwarten.',
        'strategy':'ema20-50-atr14-m15-v1','confidence':None}


def size_volume(budget,loss_per_lot,minimum,maximum,step):
    budget=number(budget);loss_per_lot=number(loss_per_lot);step=number(step)
    minimum=number(minimum);maximum=number(maximum)
    if budget<=0 or loss_per_lot<=0 or step<=0 or minimum<=0 or maximum<minimum:raise ValueError('Ungültige Risikoparameter.')
    raw=min(budget/loss_per_lot,maximum)
    volume=float((Decimal(str(raw))/Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)*Decimal(str(step)))
    if volume<minimum or volume*loss_per_lot>budget+1e-8:raise ValueError('Broker-Mindestlot überschreitet Risikobudget. Kein Trade.')
    return volume


def backtest(bars,cost_price=0):
    """Chronological OHLC check, next-open fills, pessimistic same-bar SL before TP."""
    cost=number(cost_price)
    if cost<0:raise ValueError('Kosten dürfen nicht negativ sein.')
    trades=[];position=None;pending=None;last_signal=None
    for i in range(100,len(bars)):
        b=bars[i]
        if pending and position is None:
            sign=1 if pending['side']=='BUY' else -1
            entry=number(b['open'])+sign*cost/2
            distance=2*pending['atr']
            position={'entry':entry,'sl':entry-sign*distance,'tp':entry+sign*2*distance,'sign':sign,'distance':distance,'opened':int(b['time'])}
            pending=None
        if position:
            s=position['sign'];stop=b['low']<=position['sl'] if s==1 else b['high']>=position['sl']
            take=b['high']>=position['tp'] if s==1 else b['low']<=position['tp']
            if stop or take:
                exit_price=position['sl'] if stop else position['tp']
                if stop:exit_price=min(exit_price,b['open']) if s==1 else max(exit_price,b['open'])
                result=(s*(exit_price-position['entry'])-cost/2)/position['distance']
                trades.append({'opened':position['opened'],'closed':int(b['time']),'r':round(result,4),'exit':'SL' if stop else 'TP'})
                position=None
        signal=analyze(bars[max(0,i-299):i+1])
        if position is None and signal['side']!='WAIT':pending=signal
        last_signal=signal
    total=sum(t['r'] for t in trades);peak=0;running=0;drawdown=0
    for t in trades:
        running+=t['r'];peak=max(peak,running);drawdown=max(drawdown,peak-running)
    return {'trades':len(trades),'wins':sum(t['r']>0 for t in trades),'net_r':round(total,3),'max_drawdown_r':round(drawdown,3),
        'open_position_excluded':position is not None,'pending_signal':pending is not None,'history':trades[-50:],
        'bars':len(bars),'from':int(bars[0]['time']),'to':int(bars[-1]['time']),
        'limitations':'OHLC-Simulation mit festem Spread/Kostenansatz, ohne Swap und variable Slippage; keine Prognose. Kein automatisches Optimieren.'}
