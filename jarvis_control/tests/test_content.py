import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from jarvis_control.core.content import Projects, Pipeline, Paused, validate_plan, plan_local
from jarvis_control.core.runway import Runway, public_https
from jarvis_control.core.media import subtitle_ass
from jarvis_control.core.instance import Instance

PLAN={'title':'Testprojekt','caption':'Ein Test.', 'scenes':[
    {'duration':5,'narration':'Eine Idee wird zum Video.','visual':'A cinematic dark desk with turquoise lighting.'},
    {'duration':5,'narration':'Du entscheidest über den nächsten Schritt.','visual':'A glowing turquoise circle slowly rotates in darkness.'}]}


class FakeProvider:
    def __init__(self):self.calls=0;self.gets=0;self.fail_submit=False;self.failed=False
    def submit(self,scene):
        self.calls+=1
        if self.fail_submit:raise TimeoutError('Lost response')
        return f'test-task-{self.calls}'
    def get(self,task):
        self.gets+=1
        return {'status':'FAILED','failureCode':'TEST.FAILURE'} if self.failed else {'status':'SUCCEEDED','output':['https://example.org/a.mp4']}
    def download(self,url,path):Path(path).write_bytes(b'test-video')


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.projects=Projects(self.root);self.ident=self.projects.create(PLAN)
        self.provider=FakeProvider();self.stop=threading.Event()
    def tearDown(self):self.temp.cleanup()
    def run_pipeline(self,limit=2):
        return Pipeline(self.projects,self.provider).run(self.ident,limit,self.projects.fingerprint(self.ident),self.stop,poll_seconds=0)

    def test_plan_validation(self):
        invalid=copy.deepcopy(PLAN);invalid['scenes'][0]['duration']=10
        with self.assertRaises(ValueError):validate_plan(invalid)
        invalid=copy.deepcopy(PLAN);invalid['scenes'][0]['narration']='word '*14
        with self.assertRaises(ValueError):validate_plan(invalid)
        invalid=copy.deepcopy(PLAN);invalid['scenes'][0]['visual']='😀'*501
        with self.assertRaises(ValueError):validate_plan(invalid)

    def test_generate_and_resume_without_new_charges(self):
        self.run_pipeline();self.assertEqual(self.provider.calls,2)
        self.run_pipeline();self.assertEqual(self.provider.calls,2)
        self.assertTrue(all(r['state']=='complete' for r in self.projects.states(self.ident)))
        (self.projects.folder(self.ident)/'clip_00.mp4').unlink()
        self.run_pipeline();self.assertEqual(self.provider.calls,2)

    def test_budget_before_network(self):
        with self.assertRaises(ValueError):self.run_pipeline(limit=0.5)
        self.assertEqual(self.provider.calls,0)

    def test_ambiguous_submission_never_retried(self):
        self.provider.fail_submit=True
        with self.assertRaises(RuntimeError):self.run_pipeline()
        self.assertEqual(self.projects.states(self.ident)[0]['state'],'uncertain')
        with self.assertRaises(ValueError):self.run_pipeline()
        self.assertEqual(self.provider.calls,1)

    def test_failed_task_not_reordered(self):
        self.provider.failed=True
        with self.assertRaises(RuntimeError):self.run_pipeline()
        with self.assertRaises(ValueError):self.run_pipeline()
        self.assertEqual(self.provider.calls,1)

    def test_stop_before_spending(self):
        self.stop.set()
        with self.assertRaises(Paused):self.run_pipeline()
        self.assertEqual(self.provider.calls,0)

    def test_inflight_persistence_after_restart(self):
        self.projects.reserve(self.ident,0,2,self.projects.fingerprint(self.ident))
        self.projects.update(self.ident,0,'pending','existing-task')
        self.projects=Projects(self.root)
        self.run_pipeline()
        self.assertEqual(self.provider.calls,1)
        self.assertEqual(self.provider.gets,2)

    def test_approval_and_edit_lock(self):
        old=self.projects.fingerprint(self.ident)
        plan=copy.deepcopy(PLAN);plan['scenes'][0]['visual']='Different visual'
        self.projects.save(self.ident,plan)
        with self.assertRaises(ValueError):
            Pipeline(self.projects,self.provider).run(self.ident,2,old,self.stop)
        self.assertEqual(self.provider.calls,0)
        self.projects.reserve(self.ident,0,2,self.projects.fingerprint(self.ident))
        with self.assertRaises(ValueError):self.projects.save(self.ident,PLAN)

    def test_reservation_prevents_duplicate_submit(self):
        self.projects.reserve(self.ident,0,2,self.projects.fingerprint(self.ident))
        with self.assertRaises(ValueError):self.projects.reserve(self.ident,0,2,self.projects.fingerprint(self.ident))

    def test_private_asset_blocked(self):
        with self.assertRaises(ValueError):public_https('http://example.com/a.mp4')
        with patch('socket.getaddrinfo',return_value=[(0,0,0,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):public_https('https://example.com/a.mp4')

    def test_exact_runway_wire_request(self):
        client=Runway('test-secret')
        with patch.object(client,'request',return_value={'id':'12345678-task'}) as request:
            self.assertEqual(client.submit(PLAN['scenes'][0]),'12345678-task')
            route,payload=request.call_args.args
            self.assertEqual(route,'image_to_video')
            self.assertEqual(payload['model'],'gen4.5')
            self.assertEqual(payload['ratio'],'720:1280')
            self.assertNotIn('promptImage',payload)

    def test_structured_local_script(self):
        class AI:
            def ensure_local(self,model):pass
            def request(self,route,payload,timeout):
                self.payload=payload
                return {'message':{'content':json.dumps(PLAN)}}
        ai=AI();self.assertEqual(plan_local(ai,'local:3b','Topic','Audience','Tone',2),PLAN)
        self.assertEqual(ai.payload['format'],'json')

    def test_subtitle_controls_escaped(self):
        text=subtitle_ass('{\\pos(0,0)} Hallo',5)
        self.assertNotIn('{\\pos',text)
        self.assertIn('0:00:05.00',text)

    def test_single_instance(self):
        first=Instance(self.root/'test.lock')
        try:
            with self.assertRaises(RuntimeError):Instance(self.root/'test.lock')
        finally:first.close()

if __name__=='__main__':unittest.main()
