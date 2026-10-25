"""Isolated Stream Director contract checks; no live OBS or Twitch required."""
import math
import tempfile
import unittest
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jarvis_control.state import State
from jarvis_control.stream_director import (
    StreamDirector, audio_features, clip_start, render_vertical)


class AudioTests(unittest.TestCase):
    def test_peak_detects_loud_interval(self):
        one_sec = array("h", [100] * 8000)
        loud = array("h", [4000] * 8000)
        pcm = (one_sec * 3 + loud + one_sec * 3).tobytes()
        with patch("jarvis_control.stream_director.subprocess.run",
                   return_value=SimpleNamespace(returncode=0, stdout=pcm, stderr=b"")):
            score, peak, duration = audio_features("fake.mp4")
        self.assertGreater(score, 75)
        self.assertEqual(peak, 3)
        self.assertEqual(duration, 7)

    def test_cut_respects_file_bounds(self):
        self.assertEqual(clip_start(2, 100, 40), 0)
        self.assertAlmostEqual(clip_start(98, 100, 40), 60)
        self.assertEqual(clip_start(0, 15, 40), 0)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = StreamDirector(State(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_defaults_are_safe(self):
        snapshot = self.service.snapshot()
        self.assertFalse(snapshot["running"])
        self.assertFalse(snapshot["config"]["auto_publish"])
        self.assertFalse(snapshot["config"]["enabled"])

    def test_configuration_is_persistent(self):
        self.service.configure({"channel": "holle_stream", "obs_port": 4455,
                                "output_dir": str(Path(self.temp.name) / "shorts"),
                                "min_score": 80})
        self.assertEqual(self.service.config()["min_score"], 80)
        self.assertEqual(self.service.config()["channel"], "holle_stream")

    def test_reject_remote_obs(self):
        with self.assertRaises(ValueError):
            self.service.configure({"obs_host": "192.168.1.1"})

    def test_reject_unconsented_upload(self):
        with self.assertRaises(ValueError):
            self.service.arm_publish(None)

    def test_reject_invalid_clip_path(self):
        with self.assertRaises(ValueError):
            self.service.video("../../etc/passwd")

    def test_manual_clip_needs_live_stream(self):
        with self.assertRaises(ValueError):
            self.service.manual_clip()

    def test_short_record_serializes(self):
        ident = self.service.state.add("streamclip", {"title": "test", "status": "ready"})
        self.assertEqual(self.service.snapshot()["clips"][0]["id"], ident)
        self.service.update(ident, status="failed")
        self.assertEqual(self.service.snapshot()["clips"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
