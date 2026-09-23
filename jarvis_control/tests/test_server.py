import tempfile
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from jarvis_control.server import create_app
from jarvis_control.tests.test_content import PLAN

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=create_app(self.tmp.name,worker=False)
        self.s=self.app.state.store;self.e=self.app.state.engine
        self.c=TestClient(self.app,base_url='http://localhost');self.c.headers['X-Jarvis']='1'
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def login(self):return self.c.post('/api/login',json={'token':self.s.token_file.read_text()})
    def job(self,**p):return self.c.post('/api/jobs',json=p)
    def test_trading_api_auth_config_and_demo_consent(self):
        self.assertEqual(self.c.get('/api/trading').status_code,401)
        self.login()
        self.assertEqual(self.c.get('/api/trading').status_code,200)
        self.assertEqual(self.c.post('/api/trading/start',json={'demo_consent':False}).status_code,400)
        self.assertEqual(self.c.post('/api/trading/configure',json={'risk_pct':100}).status_code,400)
        self.assertEqual(self.c.post('/api/trading/research-config',json={'enabled':True,'summarize':False,'minutes':1}).status_code,400)
        self.assertEqual(self.c.post('/api/trading/research-config',json={'enabled':True,'summarize':False,'minutes':30}).status_code,200)
        self.assertEqual(self.c.get('/api/trading').json()['research_config']['minutes'],30)
        self.assertFalse(self.app.state.engine.trading.armed)

    def test_auth_and_logout(self):
        self.assertEqual(self.c.get('/api/state').status_code,401)
        self.assertEqual(self.login().status_code,200)
        self.assertIn('HttpOnly',self.login().headers['set-cookie'])
        self.assertEqual(self.c.get('/api/state').status_code,200)
        self.c.post('/api/logout',json={});self.assertEqual(self.c.get('/api/state').status_code,401)
    def test_csrf_and_host(self):
        self.login()
        self.assertEqual(self.c.post('/api/settings',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.c.post('/api/settings',json={},headers={'X-Jarvis':''}).status_code,403)
        self.assertEqual(self.c.get('/api/state',headers={'Host':'evil.example'}).status_code,400)
    def test_cloud_requires_explicit_cost_consent(self):
        self.login();self.assertEqual(self.job(kind='chat',text='Hi',provider='openai').status_code,400)
        self.assertEqual(self.job(kind='chat',text='Hi',provider='local').status_code,200)
        self.assertEqual(self.s.claim()['payload']['provider'],'local')
    def test_draft_no_execution_and_exactly_once_claim(self):
        self.login();ident=self.job(kind='reminder',text='Test').json()['id']
        self.assertIsNone(self.s.claim())
        self.assertEqual(self.c.post(f'/api/jobs/{ident}/approve',json={}).status_code,200)
        self.assertEqual(self.c.post(f'/api/jobs/{ident}/approve',json={}).status_code,400)
        self.assertEqual(self.s.claim()['id'],ident);self.assertIsNone(self.s.claim())
    def test_future_schedule_and_restart_recovery(self):
        self.login();ident=self.job(kind='reminder',text='Test').json()['id']
        self.s.approve(ident,time.time()+60);self.assertIsNone(self.s.claim())
        with self.s.connect() as c:c.execute("UPDATE jobs SET state='running' WHERE id=?",(ident,))
        self.s.recover();self.assertEqual(self.s.jobs()[0]['state'],'review');self.assertIsNone(self.s.claim())
    def test_path_and_executable_write_rejected(self):
        self.login()
        for name in ('../outside.txt','/tmp/outside.txt','bot.py'):
            self.assertEqual(self.job(kind='file.write',name=name,text='x').status_code,400)
    def test_secrets_never_returned(self):
        self.login();secret='TEST_PRIVATE_API_VALUE_NOT_REAL'
        self.c.post('/api/settings',json={'openai':secret})
        self.assertNotIn(secret,self.c.get('/api/state').text)
        self.assertEqual(self.s.redact(secret),'[geschützt]')
    def test_modified_project_invalidates_generation(self):
        self.login();ident=self.e.projects.create(PLAN)
        j=self.job(kind='generate',project=ident,limit=2).json()['id']
        changed=dict(PLAN,title='Changed');self.e.projects.save(ident,changed)
        self.s.approve(j)
        with self.assertRaisesRegex(ValueError,'geändert'):self.e.execute(self.s.claim())
    def test_modified_bot_invalidates_execution(self):
        self.login();script=self.e.file_path('bot.py');script.write_text('print(1)')
        bot=self.c.post('/api/records/bot',json={'name':'Test','script':'bot.py'}).json()['id']
        ident=self.job(kind='bot.start',bot=bot).json()['id'];script.write_text('print(2)');self.s.approve(ident)
        with self.assertRaisesRegex(ValueError,'verändert'):self.e.execute(self.s.claim())
    def test_account_snapshot_and_recipient_visible(self):
        self.login();a=self.c.post('/api/records/account',json={'name':'Test','platform':'telegram','token':'TEST_NOT_REAL'}).json()['id']
        r=self.job(kind='message',account=a,recipient='1234',text='Hallo')
        self.assertEqual(r.status_code,200);job=self.s.jobs()[0]
        self.assertEqual(job['payload']['recipient'],'1234');self.assertNotIn('token',job['payload']['account_snapshot'])
        self.s.update_record('account',a,{'name':'Changed'});self.s.approve(job['id'])
        with self.assertRaisesRegex(ValueError,'Konto'):self.e.execute(self.s.claim())

if __name__=='__main__':unittest.main()
