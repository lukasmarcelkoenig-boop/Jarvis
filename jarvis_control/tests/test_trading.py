import copy
import json
import tempfile
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from jarvis_control.state import State
from jarvis_control.trading.strategy import size_volume,analyze,backtest
from jarvis_control.trading.mt5_gateway import MT5Gateway,MAGIC
from jarvis_control.trading.service import Trading
from jarvis_control.trading.research import parse_feed,SOURCES,Research


def bars(n=120):
    start=int(time.time())//900*900-n*900
    return [{'time':start+i*900,'open':2000+i*.1,'close':2000+i*.1,'high':2002+i*.1,'low':1998+i*.1} for i in range(n)]

def signal():return {'side':'BUY','bar':int(time.time())//900*900-900,'close':2000.,'atr':10.,'reason':'Test','strategy':'test'}

class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO=0;ORDER_TYPE_BUY=0;ORDER_TYPE_SELL=1;TIMEFRAME_M15=15
    TRADE_ACTION_DEAL=1;ORDER_TIME_GTC=0;ORDER_FILLING_IOC=1;ORDER_FILLING_FOK=0
    TRADE_RETCODE_DONE=10009;TRADE_RETCODE_DONE_PARTIAL=10010
    def __init__(self):
        self.a=NS(trade_mode=0,login=123,server='Demo',equity=10000.,balance=10000.,margin_free=10000.,trade_allowed=True,trade_expert=True,currency='EUR')
        self.info=NS(trade_tick_size=.01,point=.01,trade_stops_level=10,digits=2,volume_min=.01,volume_max=100,volume_step=.01,filling_mode=2)
        self.tick=NS(time=int(time.time()),bid=1999.9,ask=2000.)
        self.sent=[];self.none_result=False;self.pos=[];self.pending=[];self.deals=[];self.margin=20.
    def initialize(self,**kwargs):return True
    def shutdown(self):pass
    def account_info(self):return self.a
    def terminal_info(self):return NS(connected=True,trade_allowed=True,tradeapi_disabled=False)
    def positions_get(self):return self.pos
    def orders_get(self):return self.pending
    def symbol_select(self,*args):return True
    def symbol_info(self,s):return self.info
    def symbol_info_tick(self,s):return self.tick
    def copy_rates_from_pos(self,*args):return bars()
    def order_calc_profit(self,kind,symbol,volume,entry,stop):return (stop-entry)*(1 if kind==0 else -1)*volume*100
    def order_calc_margin(self,*args):return self.margin
    def order_check(self,r):return NS(retcode=0)
    def order_send(self,r):
        self.sent.append(r)
        if self.none_result:return None
        return NS(retcode=10009,deal=1,order=2,volume=r['volume'],price=r['price'])
    def history_deals_get(self,*args):return self.deals

class TradingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=State(self.tmp.name);self.m=FakeMT5();self.g=MT5Gateway(self.m);self.t=Trading(self.s,self.g)
    def tearDown(self):self.tmp.cleanup()
    def preview(self):return self.g.preview_order('XAUUSD',signal(),self.t.config(),'123@Demo',10000)
    def test_real_and_contest_accounts_rejected(self):
        for mode in (1,2):
            self.m.a.trade_mode=mode
            with self.assertRaisesRegex(ValueError,'Demokonten'):self.g.connect()
        self.assertEqual(self.m.sent,[])
    def test_explicit_demo_consent(self):
        with self.assertRaises(ValueError):self.t.arm(False)
        self.assertFalse(self.t.armed)
    def test_lot_never_rounded_up_to_broker_minimum(self):
        with self.assertRaises(ValueError):size_volume(10,1000,.1,5,.01)
        self.assertEqual(size_volume(25,1200,.01,5,.01),.02)
    def test_nonfinite_config_rejected(self):
        for v in ('nan','inf','-inf'):
            with self.assertRaises(ValueError):self.t.configure({'risk_pct':v})
    def test_valid_order_has_protective_stops_and_magic(self):
        request,risk=self.preview()
        self.assertLess(request['sl'],request['price']);self.assertGreater(request['tp'],request['price'])
        self.assertLessEqual(risk['risk_amount'],20);self.assertEqual(request['magic'],MAGIC)
    def test_stale_tick_and_signal_rejected(self):
        self.m.tick.time-=200
        with self.assertRaisesRegex(ValueError,'Tick'):self.preview()
        self.m.tick.time=int(time.time());s=signal();s['bar']-=7200
        with self.assertRaisesRegex(ValueError,'Signal'):self.g.preview_order('XAUUSD',s,self.t.config(),'123@Demo',10000)
    def test_account_changed_before_send(self):
        req,_=self.preview();self.m.a.login=999
        with self.assertRaises(ValueError):self.g.send(req,'123@Demo')
        self.assertFalse(self.m.sent)
    def test_account_switched_to_real_before_send(self):
        req,_=self.preview();self.m.a.trade_mode=2
        with self.assertRaises(ValueError):self.g.send(req,'123@Demo')
        self.assertFalse(self.m.sent)
    def test_daily_loss_blocks(self):
        self.m.a.equity=9700
        with self.assertRaisesRegex(ValueError,'Tagesverlust'):self.preview()
    def test_pending_orders_and_unknown_positions_fail_closed(self):
        self.m.pending=[NS()]
        with self.assertRaisesRegex(ValueError,'Pending'):self.preview()
        self.m.pending=[];self.m.pos=None
        with self.assertRaisesRegex(ValueError,'Positionen'):self.preview()
    def test_no_stop_or_foreign_position_blocks(self):
        self.m.pos=[NS(symbol='BTCUSD',magic=MAGIC,sl=0)]
        with self.assertRaisesRegex(ValueError,'ohne Stop'):self.preview()
        self.m.pos=[NS(symbol='BTCUSD',magic=123)]
        with self.assertRaisesRegex(ValueError,'Fremde'):self.preview()
    def test_margin_and_spread_block(self):
        self.m.margin=9000
        with self.assertRaisesRegex(ValueError,'Margin'):self.preview()
        self.m.margin=10;self.m.tick.ask=2005
        with self.assertRaisesRegex(ValueError,'Spread'):self.preview()
    @patch('jarvis_control.trading.service.analyze')
    def test_signal_sent_once_and_no_replay_after_restart(self,analysis):
        self.t.arm(True);analysis.return_value=signal()
        self.t.inspect(self.m.a,send=True);self.t.inspect(self.m.a,send=True)
        self.assertEqual(len(self.m.sent),2)  # once per configured symbol
        fresh=Trading(self.s,self.g);self.assertFalse(fresh.armed)
        fresh.arm(True);fresh.inspect(self.m.a,send=True);self.assertEqual(len(self.m.sent),2)
    @patch('jarvis_control.trading.service.analyze')
    def test_unknown_order_is_reserved_and_blocks_restart(self,analysis):
        self.t.arm(True);analysis.return_value=signal();self.m.none_result=True
        with self.assertRaisesRegex(RuntimeError,'unklar'):self.t.inspect(self.m.a,send=True)
        fresh=Trading(self.s,self.g)
        with self.assertRaisesRegex(ValueError,'Unklare'):fresh.arm(True)
        self.assertEqual(len(self.m.sent),1)
    def test_utc_day_baseline_persists(self):
        _,first=self.t.baseline(self.m.a);self.m.a.equity=9990
        _,second=self.t.baseline(self.m.a);self.assertEqual(first,second)
    def test_duplicate_or_invalid_bars_rejected(self):
        b=bars();b[-1]['time']=b[-2]['time']
        with self.assertRaises(ValueError):analyze(b)
        b=bars();b[-1]['close']=float('nan')
        with self.assertRaises(ValueError):analyze(b)
    def test_future_data_does_not_change_earlier_signals(self):
        b=bars(150);before=analyze(b[:120]);b[-1]['close']=100000
        self.assertEqual(before,analyze(b[:120]))
    @patch('jarvis_control.trading.strategy.analyze')
    def test_backtest_next_open_and_stop_first(self,analysis):
        b=bars(102);b[-1].update(open=2000,high=2030,low=1970,close=2000)
        analysis.return_value={'side':'BUY','atr':5}
        r=backtest(b,0)
        self.assertEqual(r['trades'],1);self.assertEqual(r['history'][0]['opened'],b[-1]['time']);self.assertEqual(r['history'][0]['r'],-1)

class ResearchTests(unittest.TestCase):
    def test_feed_date_source_and_html_removed(self):
        raw=b'<rss><channel><item><title>Policy &amp; rates</title><link>https://www.federalreserve.gov/newsevents/x.htm</link><description>&lt;b&gt;Facts&lt;/b&gt;</description><pubDate>Wed, 23 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>'
        item=parse_feed(raw,SOURCES[0],1790164800)[0]
        self.assertEqual(item['excerpt'],'Facts');self.assertEqual(item['title'],'Policy & rates');self.assertIsNotNone(item['published'])
    def test_external_entity_rejected(self):
        with self.assertRaises(ValueError):parse_feed(b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///secret">]><rss/>',SOURCES[0])
    def test_foreign_or_javascript_links_rejected(self):
        for link in ('https://evil.example/x','javascript:alert(1)','http://www.federalreserve.gov/x'):
            with self.assertRaises(ValueError):parse_feed(f'<rss><item><title>X</title><link>{link}</link></item></rss>'.encode(),SOURCES[0])
    def test_undated_old_sources_not_live(self):
        raw=b'<rss><item><title>Old</title><link>https://bitcoincore.org/en/x</link></item></rss>'
        self.assertTrue(parse_feed(raw,SOURCES[2])[0]['date_uncertain'])
    @patch('jarvis_control.trading.research.httpx.Client')
    def test_repeated_research_deduplicates_and_persists(self,client):
        from unittest.mock import MagicMock
        response=MagicMock();response.status_code=200;response.headers={}
        response.iter_bytes.return_value=[b'<rss><item><title>Test</title><link>https://www.federalreserve.gov/news/test</link></item></rss>']
        stream=client.return_value.__enter__.return_value.stream.return_value
        stream.__enter__.return_value=response
        with tempfile.TemporaryDirectory() as folder:
            state=State(folder);research=Research(state,None)
            with patch('jarvis_control.trading.research.SOURCES',[SOURCES[0]]):
                research.run({'summarize':False});research.run({'summarize':False})
            self.assertEqual(len(state.records('research')),1)
            self.assertEqual(state.get('research_status')['added'],0)
            self.assertTrue(state.get('research_status')['sources'][0]['ok'])
            self.assertFalse(state.get('research_status')['running'])

    def test_periodic_scheduler_runs_once_until_interval_due(self):
        class Stop:
            def __init__(self):self.n=0
            def is_set(self):return self.n>=2
            def wait(self,seconds):self.n+=1
        with tempfile.TemporaryDirectory() as folder:
            state=State(folder);research=Research(state,None);research.stop=Stop();calls=[]
            def run(cfg):
                calls.append(cfg);state.set('research_status',{'finished':time.time()})
            research.run=run;research.loop()
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['minutes'],60)

    def test_research_has_no_order_or_strategy_write_interface(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Research(State(folder),None)
            self.assertFalse(hasattr(r,'gateway'));self.assertFalse(hasattr(r,'order_send'))

if __name__=='__main__':unittest.main()
