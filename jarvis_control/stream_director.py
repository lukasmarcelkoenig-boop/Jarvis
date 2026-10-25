"""JARVIS Stream Director: local OBS replay capture, scoring and short-video export.

Keeps rendering off the main JARVIS job queue. All external actions require an
owner-enabled configuration; no cloud inference or upload happens by default.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from array import array
from collections import deque
from pathlib import Path

import httpx
from .core.media import ffmpeg_path

DEFAULTS = {
    "enabled": False, "channel": "", "client_id": "",
    "obs_host": "127.0.0.1", "obs_port": 4455,
    "capture_interval": 55, "short_seconds": 40,
    "min_score": 75, "max_shorts": 3,
    "resolution": 720, "captions": False, "auto_publish": False,
    "publish_account": "", "publish_privacy": "private",
    "output_dir": "", "keep_obs_replays": True
}
ALLOWED_PRIVACY = ("private", "unlisted", "public")
ID_PATTERN = re.compile(r"^[0-9a-f]{24}$")


def audio_features(path, max_seconds=180):
    """Read audio as 1-second PCM windows. Returns score and peak time in seconds.

    This is an acoustic *heuristic*, not gameplay/visual understanding.
    """
    command = [ffmpeg_path(), "-hide_banner", "-loglevel", "error",
               "-nostdin", "-i", str(path), "-vn", "-t", str(max_seconds),
               "-ar", "8000", "-ac", "1", "-f", "s16le", "pipe:1"]
    completed = subprocess.run(command, capture_output=True, timeout=90,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        raise RuntimeError("OBS-Audio konnte nicht ausgewertet werden.")
    samples = array("h")
    samples.frombytes(completed.stdout[:len(completed.stdout) // 2 * 2])
    if len(samples) < 8000:
        return 0, 0.0, 0.0
    levels = []
    for start in range(0, len(samples) - 8000 + 1, 8000):
        second = samples[start:start + 8000]
        rms = math.sqrt(sum(n * n for n in second) / len(second))
        levels.append(20 * math.log10(max(1, rms) / 32768))
    ordered = sorted(levels)
    baseline = ordered[len(ordered) // 2]
    index = max(range(len(levels)), key=lambda i: levels[i])
    peak = levels[index]
    rise = max(0.0, peak - baseline)
    score = max(0, min(100, round(26 + rise * 6.5 + max(0, peak + 30) * 0.8)))
    return score, float(index), float(len(levels))


def clip_start(peak_second, duration, requested_seconds):
    return max(0.0, min(max(0.0, duration - requested_seconds),
                         peak_second - requested_seconds * .58))


def render_vertical(source, destination, start, seconds, resolution=720):
    """Render the full 16:9 gameplay inside a blurred portrait backdrop."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    height = int(resolution * 16 / 9)
    width = int(resolution)
    # Preserve the entire gameplay image. Facecam from OBS remains visible.
    vf = (f"[0:v]split=2[base][game];"
          f"[base]scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height},boxblur=20:2[bg];"
          f"[game]scale={width}:-2:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,"
          f"fps=30,format=yuv420p[out]")
    temp = destination.with_name("working_" + destination.name)
    args = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-y", "-ss", str(round(start, 2)), "-i", str(source),
            "-t", str(int(seconds)), "-filter_complex", vf,
            "-map", "[out]", "-map", "0:a:0?", "-c:v", "libx264",
            "-preset", "veryfast", "-threads", "2", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", str(temp)]
    try:
        result = subprocess.run(args, capture_output=True, timeout=1200,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("FFmpeg: " + result.stderr.decode(errors="replace")[-700:])
        if not temp.exists() or not temp.stat().st_size:
            raise RuntimeError("FFmpeg hat kein Video erstellt.")
        temp.replace(destination)
    finally:
        if temp.exists():
            temp.unlink()
    return destination


class TwitchSignals:
    """Optional Twitch Helix live status + official EventSub chat activity."""

    def __init__(self, state, config, stop):
        self.state, self.config, self.stop = state, config, stop
        self.events = deque(maxlen=500)
        self.lock = threading.Lock()
        self.thread = None
        self.socket = None
        self.last_error = ""
        self.game = ""
        self.live_title = ""
        self.broadcaster_id = ""
        self.user_id = ""
        self.last_poll = 0
        self.last_live = None

    def headers(self):
        token = self.state.secret("stream_twitch_token")
        return {"Authorization": "Bearer " + token, "Client-Id": self.config["client_id"]}

    def ready(self):
        return bool(self.config["channel"] and self.config["client_id"]
                    and self.state.secret("stream_twitch_token"))

    def live(self):
        if not self.ready():
            return None
        if time.time() - self.last_poll < 30:
            return self.last_live
        with httpx.Client(timeout=8, trust_env=False) as client:
            r = client.get("https://api.twitch.tv/helix/streams",
                           params={"user_login": self.config["channel"]},
                           headers=self.headers())
            r.raise_for_status()
            data = r.json().get("data", [])
        if data:
            self.game = data[0].get("game_name", "")
            self.live_title = data[0].get("title", "")
        self.last_poll = time.time()
        self.last_live = bool(data)
        return self.last_live

    def recent(self, seconds=100):
        cutoff = time.time() - seconds
        with self.lock:
            return [t for t, _ in self.events if t >= cutoff]

    def watch_chat(self):
        if not self.ready():
            return
        try:
            import websocket
        except ImportError:
            self.last_error = "Für Twitch-Chat fehlt websocket-client."
            return
        try:
            with httpx.Client(timeout=8, trust_env=False) as client:
                r = client.get("https://id.twitch.tv/oauth2/validate",
                               headers={"Authorization": "OAuth " + self.state.secret("stream_twitch_token")})
                r.raise_for_status()
                info = r.json()
                if info.get("client_id") != self.config["client_id"]:
                    raise ValueError("Twitch Client-ID und Token passen nicht zusammen.")
                if "user:read:chat" not in info.get("scopes", []):
                    raise ValueError("Twitch-Chat benötigt Token-Scope user:read:chat.")
                self.user_id = info["user_id"]
                r = client.get("https://api.twitch.tv/helix/users",
                               params={"login": self.config["channel"]}, headers=self.headers())
                r.raise_for_status()
                users = r.json().get("data", [])
                if not users:
                    raise ValueError("Twitch-Kanal nicht gefunden.")
                self.broadcaster_id = users[0]["id"]
        except Exception as exc:
            self.last_error = str(exc)[:220]
            return

        def on_message(ws, raw):
            try:
                item = json.loads(raw)
                msg = item.get("metadata", {}).get("message_type", "")
                data = item.get("payload", {})
                if msg == "session_welcome":
                    session_id = data["session"]["id"]
                    payload = {
                        "type": "channel.chat.message", "version": "1",
                        "condition": {"broadcaster_user_id": self.broadcaster_id,
                                      "user_id": self.user_id},
                        "transport": {"method": "websocket", "session_id": session_id}
                    }
                    with httpx.Client(timeout=10, trust_env=False) as client:
                        resp = client.post("https://api.twitch.tv/helix/eventsub/subscriptions",
                                           headers=self.headers(), json=payload)
                        resp.raise_for_status()
                elif msg == "notification":
                    event = data.get("event", {})
                    if event.get("message_id"):
                        with self.lock:
                            self.events.append((time.time(), "chat"))
                elif msg == "session_reconnect":
                    ws.close()
            except Exception as exc:
                self.last_error = str(exc)[:220]

        def loop():
            while not self.stop.is_set() and self.ready():
                try:
                    socket = websocket.WebSocketApp(
                        "wss://eventsub.wss.twitch.tv/ws",
                        on_message=on_message,
                        on_error=lambda ws, err: setattr(self, "last_error", str(err)[:220]))
                    self.socket = socket
                    socket.run_forever(ping_interval=30, ping_timeout=10)
                except Exception as exc:
                    self.last_error = str(exc)[:220]
                self.stop.wait(10)
        self.thread = threading.Thread(target=loop, daemon=True, name="jarvis-twitch-chat")
        self.thread.start()


class StreamDirector:
    def __init__(self, state):
        self.state = state
        self.stop = threading.Event()
        self.monitor = None
        self.editor = None
        self.q = queue.Queue(maxsize=5)
        self.lock = threading.RLock()
        self.active = False
        self.online = False
        self.last_error = ""
        self.last_capture = 0
        self.last_highlight_at = 0
        self.stream_clips = 0
        self.capture_lock = threading.Lock()
        self.signals = None

    def config(self):
        return DEFAULTS | self.state.get("stream_config", {})

    def output_root(self):
        p = self.config()["output_dir"] or str(self.state.root / "stream-director")
        return Path(p).expanduser().resolve()

    def configure(self, p):
        current = self.config()
        next_cfg = dict(current)
        for key in ("channel", "client_id", "obs_host", "output_dir", "publish_account", "publish_privacy"):
            if key in p:
                next_cfg[key] = str(p[key]).strip()[:300]
        for key, low, high in (("obs_port", 1, 65535), ("capture_interval", 35, 180),
                               ("short_seconds", 15, 60), ("min_score", 30, 100),
                               ("max_shorts", 1, 20)):
            if key in p:
                value = int(p[key])
                if not low <= value <= high:
                    raise ValueError(f"{key}: Erlaubter Bereich {low} bis {high}.")
                next_cfg[key] = value
        if "resolution" in p:
            if int(p["resolution"]) not in (720, 1080):
                raise ValueError("Auflösung muss 720 oder 1080 sein.")
            next_cfg["resolution"] = int(p["resolution"])
        for key in ("keep_obs_replays", "captions"):
            if key in p:
                if type(p[key]) is not bool:
                    raise ValueError(key + " muss wahr oder falsch sein.")
                next_cfg[key] = p[key]
        if next_cfg["channel"] and not re.fullmatch(r"[A-Za-z0-9_]{3,25}", next_cfg["channel"]):
            raise ValueError("Ungültiger Twitch-Kanalname.")
        if next_cfg["obs_host"] not in ("127.0.0.1", "localhost"):
            raise ValueError("OBS-WebSocket darf nur lokal verbunden werden.")
        if next_cfg["client_id"] and not re.fullmatch(r"[A-Za-z0-9]{10,80}", next_cfg["client_id"]):
            raise ValueError("Ungültige Twitch Client-ID.")
        if next_cfg["publish_privacy"] not in ALLOWED_PRIVACY:
            raise ValueError("Unbekannte YouTube-Sichtbarkeit.")
        if next_cfg["output_dir"] and not Path(next_cfg["output_dir"]).is_absolute():
            raise ValueError("Ausgabeordner muss ein absoluter Pfad sein.")
        if "obs_password" in p and p["obs_password"]:
            self.state.secret("stream_obs_password", str(p["obs_password"])[:1000])
        if "twitch_token" in p and p["twitch_token"]:
            self.state.secret("stream_twitch_token", str(p["twitch_token"])[:4000].removeprefix("oauth:"))
        # Publishing can only be armed by an explicit action, not this settings form.
        next_cfg["auto_publish"] = current["auto_publish"]
        next_cfg["enabled"] = current["enabled"]
        if self.active and any(next_cfg.get(k) != current.get(k) for k in
                               ("channel", "client_id", "obs_host", "obs_port", "output_dir")):
            raise ValueError("Stream Director vor Änderung der Verbindung pausieren.")
        if next_cfg["publish_account"]:
            account = self.state.record("account", next_cfg["publish_account"])
            if account["platform"] != "youtube":
                raise ValueError("Vollautomatischer Upload zunächst nur für YouTube verfügbar.")
        self.state.set("stream_config", next_cfg)
        return {"ok": True}

    def obs(self):
        try:
            import obsws_python
        except ImportError:
            raise RuntimeError("OBS-WebSocket-Paket fehlt. EINRICHTEN_STREAM.bat ausführen.") from None
        c = self.config()
        return obsws_python.ReqClient(host=c["obs_host"], port=c["obs_port"],
                                      password=self.state.secret("stream_obs_password"), timeout=5)

    def check_obs(self):
        client = self.obs()
        return {"streaming": bool(client.get_stream_status().output_active),
                "replay": bool(client.get_replay_buffer_status().output_active)}

    def start(self):
        if self.monitor and self.monitor.is_alive():
            if self.stop.is_set():
                raise ValueError('Vorherige Stream-Überwachung beendet sich noch. Erneut starten.')
            return
        if self.editor and self.editor.is_alive():
            raise ValueError('Vorheriger Videoschnitt läuft noch. Nach Abschluss erneut starten.')
        self.stop.clear()
        self.monitor = threading.Thread(target=self.capture_loop, daemon=True, name="jarvis-obs-capture")
        self.editor = threading.Thread(target=self.render_loop, daemon=True, name="jarvis-short-editor")
        self.monitor.start()
        self.editor.start()

    def arm(self):
        self.obs()  # Fast-fail if OBS cannot be reached.
        if self.monitor and self.monitor.is_alive() and self.stop.is_set():
            raise ValueError("Vorherige Stream-Überwachung beendet sich noch.")
        if self.editor and self.editor.is_alive() and self.stop.is_set():
            raise ValueError("Vorheriger Videoschnitt beendet sich noch.")
        config = self.config()
        config["enabled"] = True
        self.state.set("stream_config", config)
        self.start()
        return {"ok": True}

    def pause(self):
        config = self.config()
        config["enabled"] = False
        config["auto_publish"] = False
        self.state.set("stream_config", config)
        self.stop.set()
        if self.signals and self.signals.socket:
            self.signals.socket.close()
        return {"ok": True}

    def arm_publish(self, confirmation):
        if confirmation != "AUTO_PUBLISH_YOUTUBE":
            raise ValueError("Automatisches Hochladen ausdrücklich bestätigen.")
        cfg = self.config()
        if not cfg["publish_account"]:
            raise ValueError("Zuerst ein YouTube-Konto auswählen.")
        account = self.state.record("account", cfg["publish_account"])
        if account["platform"] != "youtube" or not self.state.secret("account:" + cfg["publish_account"]):
            raise ValueError("Verbundenes YouTube-Konto mit Zugangstoken erforderlich.")
        cfg["auto_publish"] = True
        self.state.set("stream_config", cfg)
        return {"ok": True}

    def disarm_publish(self):
        cfg = self.config()
        cfg["auto_publish"] = False
        self.state.set("stream_config", cfg)
        return {"ok": True}

    def snapshot(self):
        cfg = self.config()
        return {"config": cfg, "running": self.active, "online": self.online,
                "last_error": self.last_error, "last_capture": self.last_capture,
                "queue": self.q.qsize(), "created_this_stream": self.stream_clips,
                "obs_password_set": bool(self.state.secret("stream_obs_password")),
                "twitch_token_set": bool(self.state.secret("stream_twitch_token")),
                "twitch_error": self.signals.last_error if self.signals else "",
                "clips": self.state.records("streamclip", 30)}

    def capture_loop(self):
        self.active = True
        signals = TwitchSignals(self.state, self.config(), self.stop)
        self.signals = signals
        signals.watch_chat()
        previous_online = False
        try:
            while not self.stop.is_set() and self.config()["enabled"]:
                cfg = self.config()
                try:
                    client = self.obs()
                    obs_live = bool(client.get_stream_status().output_active)
                    online = obs_live
                    # OBS is the authoritative local video source. Twitch is advisory.
                    if signals.ready():
                        try:
                            remote_live = signals.live()
                            if remote_live is False and not obs_live:
                                online = False
                        except Exception as exc:
                            signals.last_error = str(exc)[:220]
                    self.online = online
                    if online and not previous_online:
                        self.stream_clips = 0
                        self.last_highlight_at = 0
                    previous_online = online
                    if not online:
                        self.stop.wait(8)
                        continue
                    replay_active = bool(client.get_replay_buffer_status().output_active)
                    if not replay_active:
                        client.start_replay_buffer()
                        self.stop.wait(4)
                        continue
                    now = time.time()
                    if now - self.last_capture >= cfg["capture_interval"]:
                        self.capture(client, forced=False)
                    self.last_error = ""
                except Exception as exc:
                    self.last_error = str(exc)[:300]
                self.stop.wait(5)
        finally:
            self.active = False
            self.online = False

    def capture(self, client=None, forced=False):
        if not self.capture_lock.acquire(blocking=False):
            raise ValueError('Replay-Aufnahme läuft bereits.')
        try:
            return self._capture_locked(client, forced)
        finally:
            self.capture_lock.release()

    def _capture_locked(self, client=None, forced=False):
        cfg = self.config()
        if not forced and self.stream_clips >= cfg["max_shorts"]:
            self.last_capture = time.time()
            return None
        client = client or self.obs()
        before = ""
        try:
            before = client.get_last_replay_buffer_replay().saved_replay_path
        except Exception:
            pass
        client.save_replay_buffer()
        source = None
        for _ in range(24):
            if self.stop.wait(.5):
                return None
            try:
                current = Path(client.get_last_replay_buffer_replay().saved_replay_path)
                if str(current) != before and current.is_file() and current.stat().st_size > 10000:
                    time.sleep(.5)
                    size = current.stat().st_size
                    time.sleep(.5)
                    if current.stat().st_size == size:
                        source = current
                        break
            except Exception:
                pass
        self.last_capture = time.time()
        if source is None:
            raise RuntimeError("OBS hat keinen neuen Replay-Pfad gemeldet. Replay Buffer prüfen.")
        score, peak, duration = audio_features(source)
        recent = len(self.signals.recent()) if self.signals else 0
        score = min(100, score + (18 if recent >= 25 else 10 if recent >= 12 else 0))
        moment = self.last_capture - max(0, duration - peak)
        if not forced and (score < cfg["min_score"] or abs(moment - self.last_highlight_at) < 80):
            if not cfg['keep_obs_replays']:
                try:source.unlink(missing_ok=True)
                except OSError:pass
            return {"score": score, "accepted": False}
        if self.q.full():
            raise RuntimeError("Video-Warteschlange voll. Aufnahme wird nicht überschrieben.")
        item = {
            "source": str(source), "score": score, "peak": peak, "duration": duration,
            "seconds": cfg["short_seconds"], "resolution": cfg["resolution"],
            "captions": cfg["captions"],
            "game": self.signals.game if self.signals else "",
            "title": self.signals.live_title if self.signals else "",
            "forced": forced, "created": time.time()
        }
        ident = self.state.add("streamclip", {"status": "queued", "score": score,
                      "title": item["title"] or "Gaming Highlight", "game": item["game"],
                      "error": "", "published_job": ""})
        item["id"] = ident
        self.q.put_nowait(item)
        self.last_highlight_at = moment
        if not forced:
            self.stream_clips += 1
        return {"id": ident, "score": score, "accepted": True}

    def manual_clip(self):
        if not self.active or not self.online:
            raise ValueError("OBS-Streamüberwachung muss aktiv und live sein.")
        return self.capture(forced=True)

    def render_loop(self):
        while not self.stop.is_set() or not self.q.empty():
            try:
                item = self.q.get(timeout=1)
            except queue.Empty:
                continue
            ident = item["id"]
            rendered = False
            try:
                self.update(ident, status="rendering")
                folder = self.output_root() / "shorts" / ident
                folder.mkdir(parents=True, exist_ok=True)
                seconds = min(item["seconds"], max(1, item["duration"]))
                start = clip_start(item["peak"], item["duration"], seconds)
                video = render_vertical(item["source"], folder / "final.mp4", start,
                                        seconds, item["resolution"])
                rendered = True
                caption_error = ""
                if item['captions']:
                    try:
                        from .stream_captions import caption_video
                        caption_video(video, item['resolution'])
                    except Exception as exc:
                        caption_error = str(exc)[:240]
                caption = "#HOLLESTAR #Gaming #Twitch #Shorts"
                title = (item["title"] or (item["game"] + " Highlight") or "Gaming Highlight")[:95]
                (folder / "render_info.json").write_text(
                    json.dumps({"duration": seconds, "source": "OBS Replay Buffer"}), encoding="utf-8")
                self.update(ident, status="caption_review" if caption_error else "ready",
                            title=title, caption=caption, caption_error=caption_error,
                            filename=video.name, seconds=seconds)
                if not caption_error:
                    self.maybe_publish(ident, video, title, caption)
            except Exception as exc:
                self.update(ident, status="failed", error=str(exc)[:500])
            finally:
                if rendered and not self.config()['keep_obs_replays']:
                    try:Path(item['source']).unlink(missing_ok=True)
                    except OSError:pass
                self.q.task_done()

    def update(self, ident, **changes):
        if not ID_PATTERN.fullmatch(ident):
            raise ValueError("Ungültige Clip-ID.")
        clip = self.state.record("streamclip", ident)
        clip.update(changes)
        self.state.update_record("streamclip", ident, clip)

    def video(self, ident):
        if not ID_PATTERN.fullmatch(ident):
            raise ValueError("Ungültige Clip-ID.")
        self.state.record("streamclip", ident)
        path = self.output_root() / "shorts" / ident / "final.mp4"
        if not path.is_file():
            raise ValueError("Fertiger Short fehlt.")
        return path

    def maybe_publish(self, ident, video, title, caption):
        cfg = self.config()
        if not cfg["auto_publish"] or not cfg["publish_account"]:
            return
        account = self.state.record("account", cfg["publish_account"])
        if account["platform"] != "youtube":
            return
        checksum = hashlib.sha256()
        with video.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                checksum.update(block)
        payload = {"project": ident, "account": cfg["publish_account"],
                   "account_snapshot": account, "video_hash": checksum.hexdigest(),
                   "title": title, "caption": caption, "privacy": cfg["publish_privacy"],
                   "public_url": "", "made_for_kids": False,
                   "brand_content_toggle": False, "brand_organic_toggle": False}
        job = self.state.propose("publish", payload, immediate=True)
        self.update(ident, published_job=job, status="upload_queued")
