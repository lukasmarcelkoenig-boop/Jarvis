"""Run locally with JARVIS stopped to revoke sessions and rotate owner access."""
import hashlib
import os
import secrets
from .state import State
from .core.instance import Instance
if __name__=='__main__':
    state=State(os.environ.get('JARVIS_DATA','.jarvis-data'))
    lock=Instance(state.root/'server.lock')
    token=secrets.token_urlsafe(24)
    state.set('login_hash',hashlib.sha256(token.encode()).hexdigest())
    state.token_file.write_text(token,encoding='utf-8');os.chmod(state.token_file,0o600)
    with state.connect() as c:c.execute('DELETE FROM sessions')
    print('Neuer Code gespeichert: '+str(state.token_file))
