"""Authorize Gmail send-only access with a Google Desktop OAuth client."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import time
import urllib.parse
import webbrowser
import core


def authorize():
    path = core.LOCAL / 'google-client.json'
    if not path.exists():
        raise core.WatchError('請先將 Google Desktop OAuth 用戶端 JSON 存為 .local/google-client.json。')
    client = core.read_json(path).get('installed')
    if not client:
        raise core.WatchError('需要 Desktop app 類型的 OAuth 用戶端 JSON。')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path != '/callback' or query.get('state', [''])[0] != state:
                self.send_error(400)
                return
            result.update(query)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('授權回應已收到，請回到終端機查看結果。'.encode())

        def log_message(self, *args):
            pass  # OAuth codes must not appear in request logs.

    with HTTPServer(('127.0.0.1', 0), Callback) as server:
        server.timeout = 1
        redirect = f'http://127.0.0.1:{server.server_port}/callback'
        query = urllib.parse.urlencode({
            'client_id': client['client_id'], 'redirect_uri': redirect,
            'response_type': 'code', 'scope': 'https://www.googleapis.com/auth/gmail.send',
            'access_type': 'offline', 'prompt': 'consent', 'state': state,
            'code_challenge': challenge, 'code_challenge_method': 'S256'
        })
        url = 'https://accounts.google.com/o/oauth2/v2/auth?' + query
        print('請在瀏覽器登入要用來寄信的 Google 帳號，並授權 Gmail 寄信。')
        if not webbrowser.open(url):
            print('請開啟此授權網址：' + url)
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if result.get('error'):
        raise core.WatchError('Google 授權未完成。')
    if not result.get('code'):
        raise core.WatchError('等待授權逾時，請重新執行。')
    token = core.request_json('https://oauth2.googleapis.com/token', form={
        'client_id': client['client_id'], 'client_secret': client['client_secret'],
        'code': result['code'][0], 'code_verifier': verifier,
        'redirect_uri': redirect, 'grant_type': 'authorization_code'
    })
    if not token.get('refresh_token'):
        raise core.WatchError('未取得 refresh token，請重新授權。')
    core.save_json(core.LOCAL / 'gmail-token.json', {
        'client_id': client['client_id'], 'client_secret': client['client_secret'],
        'refresh_token': token['refresh_token']
    })
    print('Gmail 寄信授權已保存。尚未寄送郵件。')


if __name__ == '__main__':
    try:
        authorize()
    except core.WatchError as error:
        raise SystemExit(str(error))
