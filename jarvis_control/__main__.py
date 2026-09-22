import os
import uvicorn
from .server import create_app
from .core.instance import Instance
if __name__=='__main__':
    app=create_app()
    lock=Instance(app.state.store.root/'server.lock')
    print('JARVIS: http://127.0.0.1:8765')
    print('Dein privater Anmeldecode steht in: '+str(app.state.store.token_file))
    uvicorn.run(app,host='127.0.0.1',port=8765,proxy_headers=True,forwarded_allow_ips='127.0.0.1')
