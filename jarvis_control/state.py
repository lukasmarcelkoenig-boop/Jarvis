"""Single-owner state, sessions, secrets and durable jobs."""
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from .core.runway import _crypt


class State:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'control.db'
        self.lock = threading.RLock()
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, kind TEXT, body TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT, payload TEXT, state TEXT,
                result TEXT DEFAULT '', created REAL, due REAL, updated REAL);
            CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, expires REAL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            ''')
        self.token_file = self.root / 'LOGIN_CODE.txt'
        if not self.get('login_hash'):
            token = secrets.token_urlsafe(24)
            self.set('login_hash', hashlib.sha256(token.encode()).hexdigest())
            self.token_file.write_text(token, encoding='utf-8')
            os.chmod(self.token_file, 0o600)
        self.vault_path = self.root / 'secrets.dat'
        self.vault = {}
        if self.vault_path.exists():
            raw = self.vault_path.read_bytes()
            raw = _crypt(raw, True) if os.name == 'nt' else raw
            self.vault = json.loads(raw)

    @contextmanager
    def connect(self):
        with self.lock:
            c = sqlite3.connect(self.db, timeout=20)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise
            finally:
                c.close()

    def get(self, key, default=None):
        with self.connect() as c:
            r = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return json.loads(r['value']) if r else default

    def set(self, key, value):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

    def secret(self, key, value=None):
        with self.lock:
            if value is not None:
                self.vault[key] = value
                raw = json.dumps(self.vault).encode()
                if os.name == 'nt': raw = _crypt(raw, False)
                tmp = self.vault_path.with_suffix('.tmp')
                tmp.write_bytes(raw)
                os.chmod(tmp, 0o600)
                tmp.replace(self.vault_path)
            return self.vault.get(key, '')

    def redact(self, text):
        with self.lock:
            for value in self.vault.values():
                if isinstance(value, str) and len(value) > 5: text = text.replace(value, '[geschützt]')
        return text[:30000]

    def login(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not secrets.compare_digest(digest, self.get('login_hash', '')): return None
        session = secrets.token_urlsafe(32)
        with self.connect() as c:
            c.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
            c.execute('INSERT INTO sessions VALUES (?,?)', (hashlib.sha256(session.encode()).hexdigest(), time.time()+43200))
        return session

    def session_ok(self, token):
        with self.connect() as c:
            return bool(c.execute('SELECT 1 FROM sessions WHERE hash=? AND expires>?',
                (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone())

    def logout(self, token):
        with self.connect() as c:
            c.execute('DELETE FROM sessions WHERE hash=?', (hashlib.sha256(token.encode()).hexdigest(),))

    def add(self, kind, body):
        ident = secrets.token_hex(12)
        with self.connect() as c:
            c.execute('INSERT INTO records VALUES (?,?,?,?)', (ident, kind, json.dumps(body, ensure_ascii=False), time.time()))
        return ident

    def records(self, kind, limit=100):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM records WHERE kind=? ORDER BY created DESC LIMIT ?', (kind, limit)).fetchall()
            return [dict(id=r['id'],created=r['created'],**json.loads(r['body'])) for r in rows]

    def record(self, kind, ident):
        with self.connect() as c:
            r = c.execute('SELECT * FROM records WHERE id=? AND kind=?', (ident,kind)).fetchone()
            if not r: raise ValueError('Eintrag nicht gefunden.')
            return json.loads(r['body'])

    def update_record(self, kind, ident, body):
        with self.connect() as c:
            c.execute('UPDATE records SET body=? WHERE id=? AND kind=?', (json.dumps(body,ensure_ascii=False),ident,kind))

    def delete(self, kind, ident):
        with self.connect() as c: c.execute('DELETE FROM records WHERE id=? AND kind=?',(ident,kind))

    def propose(self, kind, payload, immediate=False):
        ident = secrets.token_hex(12)
        now = time.time()
        with self.connect() as c:
            c.execute('INSERT INTO jobs(id,kind,payload,state,created,due,updated) VALUES (?,?,?,?,?,?,?)',
                (ident,kind,json.dumps(payload,ensure_ascii=False),'approved' if immediate else 'draft',now,now,now))
        return ident

    def jobs(self, limit=60):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT ?', (limit,)).fetchall()
            return [dict(r)|{'payload':json.loads(r['payload'])} for r in rows]

    def approve(self, ident, due=None):
        due = time.time() if due is None else float(due)
        with self.connect() as c:
            count = c.execute("UPDATE jobs SET state='approved',due=?,updated=? WHERE id=? AND state='draft'", (due,time.time(),ident)).rowcount
            if not count: raise ValueError('Auftrag wurde bereits freigegeben oder ausgeführt.')

    def cancel(self, ident):
        with self.connect() as c:
            count=c.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=? AND state IN ('draft','approved')",(time.time(),ident)).rowcount
            if not count:raise ValueError('Laufende Aufträge können nicht zurückgenommen werden.')

    def claim(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute("SELECT * FROM jobs WHERE state='approved' AND due<=? ORDER BY due LIMIT 1",(time.time(),)).fetchone()
            if not r:return None
            c.execute("UPDATE jobs SET state='running',updated=? WHERE id=?",(time.time(),r['id']))
            return dict(r)|{'payload':json.loads(r['payload'])}

    def finish(self, ident, state, result):
        with self.connect() as c:
            c.execute('UPDATE jobs SET state=?,result=?,updated=? WHERE id=?',(state,self.redact(str(result)),time.time(),ident))

    def recover(self):
        with self.connect() as c:
            c.execute("UPDATE jobs SET state='review',result='Beim letzten Start unterbrochen. Ergebnis beim Anbieter prüfen; keine automatische Wiederholung.' WHERE state='running'")
