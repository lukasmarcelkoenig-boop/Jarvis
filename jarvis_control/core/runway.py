import ipaddress
import json
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


def public_https(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (443, None):
        raise ValueError('Video-Download erfordert eine öffentliche HTTPS-Adresse.')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Interne Download-Adresse blockiert.')
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Unerwartete API-Weiterleitung blockiert.')


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Runway:
    def __init__(self, key):
        if not key.strip():
            raise ValueError('Runway-API-Schlüssel fehlt. Unter Einrichtung hinterlegen.')
        self.key = key.strip()
        self.http = build_opener(NoRedirect())

    def request(self, route, data=None):
        # No automatic POST retries: an ambiguous result can already have charged credits.
        request = Request('https://api.dev.runwayml.com/v1/' + route,
            data=json.dumps(data).encode('utf-8') if data is not None else None,
            headers={'Authorization': 'Bearer ' + self.key, 'X-Runway-Version': '2024-11-06',
                     'Content-Type': 'application/json', 'User-Agent': 'JarvisLocal/0.3'})
        try:
            with self.http.open(request, timeout=60) as response:
                return json.loads(response.read(2_000_000))
        except HTTPError as exc:
            messages = {401: 'Schlüssel ungültig', 402: 'Guthaben fehlt', 403: 'Zugriff verweigert',
                        404: 'Auftrag oder Endpunkt nicht gefunden', 429: 'Limit erreicht'}
            raise RuntimeError(f'Runway HTTP {exc.code}: {messages.get(exc.code, "Anfrage fehlgeschlagen")}. Im Entwicklerkonto prüfen.') from None
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError('Runway-Verbindung unterbrochen. Auftragsstatus prüfen, bevor erneut beauftragt wird.') from None

    def submit(self, scene):
        result = self.request('image_to_video', {'model': 'gen4.5', 'promptText': scene['visual'],
                              'ratio': '720:1280', 'duration': scene['duration']})
        task_id = result.get('id')
        if not isinstance(task_id, str) or not re.fullmatch('[A-Za-z0-9_-]{8,100}', task_id):
            raise RuntimeError('Keine gültige Task-ID erhalten; Status im Runway-Konto prüfen.')
        return task_id

    def get(self, task_id):
        if not re.fullmatch('[A-Za-z0-9_-]{8,100}', task_id):
            raise ValueError('Ungültige Task-ID.')
        return self.request('tasks/' + task_id)

    def download(self, url, path):
        public_https(url)
        path = Path(path)
        temp = path.with_suffix('.download')
        http = build_opener(PublicRedirect())
        total = 0
        try:
            # Separate opener/request: no Authorization header is sent to asset hosts.
            with http.open(Request(url, headers={'User-Agent': 'JarvisLocal/0.3'}), timeout=90) as response, temp.open('wb') as out:
                while True:
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 500_000_000:
                        raise ValueError('Videodatei überschreitet 500 MB.')
                    out.write(chunk)
            with temp.open('rb') as src:
                head = src.read(4096)
            if total < 32 or b'ftyp' not in head:
                raise ValueError('Heruntergeladene Datei ist kein erkennbares MP4.')
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()


def protect_key(text):
    """Windows DPAPI bound to the current Windows user; key stays out of settings/logs."""
    return _crypt(text.encode('utf-8'), False)


def unprotect_key(data):
    return _crypt(data, True).decode('utf-8')


def _crypt(data, decrypt):
    if os.name != 'nt':
        raise RuntimeError('Dauerhafte Schlüsselspeicherung ist nur unter Windows verfügbar.')
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    function = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel.LocalFree(target.pbData)
