"""Authenticated Stream Director routes and secret protection."""
import tempfile
import unittest

from fastapi.testclient import TestClient
from jarvis_control.server import create_app


class StreamAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name, worker=False)
        self.client = TestClient(self.app, base_url="http://localhost")
        self.client.headers["X-Jarvis"] = "1"

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def login(self):
        store = self.app.state.store
        result = self.client.post("/api/login",
                                  json={"token": store.token_file.read_text()})
        self.assertEqual(result.status_code, 200)

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/stream").status_code, 401)
        self.assertEqual(self.client.post("/api/stream/start", json={}).status_code, 401)

    def test_configuration_and_secrets(self):
        self.login()
        self.assertEqual(self.client.get("/api/stream").status_code, 200)
        result = self.client.post("/api/stream/configure", json={
            "channel": "holle_stream", "min_score": 85, "obs_port": 4455,
            "obs_password": "JARVIS_PRIVATE_OBS_PASSWORD_12345"
        })
        self.assertEqual(result.status_code, 200, result.text)
        result = self.client.get("/api/stream")
        self.assertEqual(result.json()["config"]["min_score"], 85)
        self.assertTrue(result.json()["obs_password_set"])
        self.assertNotIn("JARVIS_PRIVATE_OBS_PASSWORD_12345", result.text)

    def test_actions_reject_unsafe_settings(self):
        self.login()
        self.assertEqual(self.client.post("/api/stream/configure",
                        json={"obs_host": "203.0.113.5"}).status_code, 400)
        self.assertEqual(self.client.post("/api/stream/auto-publish",
                        json={"enable": True}).status_code, 400)
        self.assertEqual(self.client.post("/api/stream/clip",json={}).status_code, 400)
        self.assertEqual(self.client.get("/api/stream/clips/bad/video").status_code, 404)
        self.assertEqual(self.client.post("/api/stream/pause",json={}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
