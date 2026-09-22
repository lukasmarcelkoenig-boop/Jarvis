import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jarvis_control.state import State
from jarvis_control.core.content import Projects
from jarvis_control.connectors import Connectors,allowed_upload
from jarvis_control.tests.test_content import PLAN

class Response:
    def __init__(self,data,headers=None):self.data=data;self.headers=headers or {}
    def json(self):return self.data

class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=State(self.tmp.name);self.projects=Projects(Path(self.tmp.name)/'content')
        self.p=self.projects.create(PLAN);self.folder=self.projects.folder(self.p)/'export';self.folder.mkdir()
        (self.folder/'final.mp4').write_bytes(b'fake_video_for_wire_test')
        (self.folder/'render_info.json').write_text('{"duration":10}')
        self.c=Connectors(self.s,self.projects)
    def tearDown(self):self.tmp.cleanup()
    def account(self,platform):
        a=self.s.add('account',{'name':'Wire test','platform':platform});self.s.secret('account:'+a,'TEST_TOKEN_NOT_REAL');return a
    def test_upload_host_restriction(self):
        for url in ['http://upload.googleapis.com','https://googleapis.com.evil.example','https://evil.example']:
            with self.assertRaises(ValueError):allowed_upload(url,['googleapis.com'])
    @patch('jarvis_control.connectors.api')
    def test_telegram_recipient_and_text(self,api):
        api.return_value=Response({'ok':True,'result':{'message_id':42}})
        self.c.send_message({'account':self.account('telegram'),'recipient':'1234','text':'Hallo'})
        self.assertEqual(api.call_args.kwargs['json'],{'chat_id':'1234','text':'Hallo'})
    @patch('jarvis_control.connectors.api')
    def test_youtube_visibility_and_two_phase_upload(self,api):
        api.side_effect=[Response({}, {'Location':'https://www.googleapis.com/upload/session'}),Response({'id':'video123'})]
        result=self.c.publish({'account':self.account('youtube'),'project':self.p,'privacy':'private','title':'Titel','caption':'Text'},'j1')
        self.assertIn('video123',result)
        payload=api.call_args_list[0].kwargs['json']
        self.assertEqual(payload['status']['privacyStatus'],'private');self.assertTrue(payload['status']['containsSyntheticMedia'])
        self.assertEqual(api.call_args_list[1].args[0],'PUT')
    @patch('jarvis_control.connectors.api')
    def test_tiktok_disclosures_and_creator_privacy(self,api):
        api.side_effect=[Response({'error':{'code':'ok'},'data':{'privacy_level_options':['SELF_ONLY'],'max_video_post_duration_sec':60}}),
            Response({'error':{'code':'ok'},'data':{'upload_url':'https://open-upload.tiktokapis.com/upload','publish_id':'p1'}}),Response({})]
        self.c.publish({'account':self.account('tiktok'),'project':self.p,'privacy':'SELF_ONLY','caption':'Test','brand_content_toggle':True,'brand_organic_toggle':False},'j2')
        post=api.call_args_list[1].kwargs['json']['post_info']
        self.assertTrue(post['is_aigc']);self.assertTrue(post['brand_content_toggle']);self.assertTrue(post['disable_comment'])
        self.assertNotIn('Authorization',api.call_args_list[2].kwargs['headers'])
        self.assertEqual(self.s.get('upload:j2')['publish_id'],'p1')
