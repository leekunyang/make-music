"""Spotify release lookup and Gmail notifications, using Python standard library."""
import base64
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / '.local'
CONFIG = LOCAL / 'watch-config.json' if (LOCAL / 'watch-config.json').exists() else ROOT.parent / 'release-watch.json'


class WatchError(Exception):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def settings(require_recipient=True):
    config = read_json(CONFIG)
    email = config.get('recipient_email', '')
    if require_recipient and (not isinstance(email, str) or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email)):
        raise WatchError('請在 release-watch.json 設定有效的 recipient_email。')
    ZoneInfo(config['timezone'])
    return config


def secrets():
    path = LOCAL / 'secrets.json'
    if not path.exists():
        raise WatchError('尚未設定 Spotify 憑證；請建立 .local/secrets.json。')
    data = read_json(path)
    for key in ('spotify_client_id', 'spotify_client_secret'):
        if not data.get(key):
            raise WatchError('Spotify Client ID 與 Client Secret 尚未設定。')
    return data


def request_json(url, headers=None, form=None, body=None):
    headers = dict(headers or {})
    payload = None
    if form is not None:
        payload = urllib.parse.urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if body is not None:
        payload = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=payload, headers=headers), timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Do not expose response bodies that may contain token or account details.
        hint = '；請稍後重試' if error.code == 429 else '；請檢查憑證、授權與 API 權限'
        raise WatchError(f'{urllib.parse.urlparse(url).hostname} 回傳 HTTP {error.code}{hint}。') from None
    except urllib.error.URLError:
        raise WatchError('API 連線失敗；請檢查網路後重試。') from None


def today(config):
    return dt.datetime.now(ZoneInfo(config['timezone'])).date()


def date_window(config, since=None, through=None):
    end = dt.date.fromisoformat(through) if through else today(config)
    start = dt.date.fromisoformat(since) if since else end - dt.timedelta(days=1)
    if start > end:
        raise WatchError('起始日期不得晚於結束日期。')
    return start, end


def check_releases(since=None, through=None):
    config = settings(require_recipient=False)
    start, end = date_window(config, since, through)
    secret = secrets()
    basic = base64.b64encode(f"{secret['spotify_client_id']}:{secret['spotify_client_secret']}".encode()).decode()
    token = request_json('https://accounts.spotify.com/api/token', headers={'Authorization': 'Basic ' + basic}, form={'grant_type': 'client_credentials'})['access_token']
    headers = {'Authorization': 'Bearer ' + token}
    artist_id = config.get('spotify_artist_id')
    if not artist_id:
        query = urllib.parse.urlencode({'q': 'artist:' + config['artist'], 'type': 'artist', 'limit': 10})
        candidates = request_json('https://api.spotify.com/v1/search?' + query, headers=headers)['artists']['items']
        candidates = [item for item in candidates if item['name'].casefold() == config['artist'].casefold()]
        if len(candidates) != 1:
            raise WatchError('無法唯一確認藝人；請在 release-watch.json 加上 spotify_artist_id。')
        artist_id = candidates[0]['id']
    if not re.fullmatch(r'[A-Za-z0-9]{22}', artist_id):
        raise WatchError('spotify_artist_id 必須是 Spotify 的 22 字元藝人 ID。')
    artist = request_json('https://api.spotify.com/v1/artists/' + artist_id, headers=headers)
    if artist['name'].casefold() != config['artist'].casefold():
        raise WatchError('Spotify 藝人 ID 與設定的藝人名稱不一致。')
    query = urllib.parse.urlencode({'include_groups': 'album,single,appears_on', 'market': 'TW', 'limit': 50})
    url = f'https://api.spotify.com/v1/artists/{artist_id}/albums?{query}'
    found = {}
    skipped = 0
    visited = set()
    while url:
        if url in visited or not url.startswith('https://api.spotify.com/v1/'):
            raise WatchError('Spotify 分頁回應異常，已停止查詢。')
        visited.add(url)
        page = request_json(url, headers=headers)
        for album in page['items']:
            if album.get('release_date_precision') != 'day':
                skipped += 1
                continue
            release_date = dt.date.fromisoformat(album['release_date'])
            if start <= release_date <= end:
                found[album['id']] = {
                    'id': album['id'], 'artist': config['artist'],
                    'release_title': album['name'], 'release_date': album['release_date'],
                    'release_type': album['album_type'], 'spotify_url': album['external_urls']['spotify']
                }
        url = page.get('next')
    return {'artist': config['artist'], 'since': start.isoformat(), 'through': end.isoformat(),
            'releases': sorted(found.values(), key=lambda item: (item['release_date'], item['release_title'])),
            'skipped_imprecise_dates': skipped}


def notification_preview(result):
    config = settings()
    releases = result['releases']
    lines = [f"{config['artist']} 新作品通知", f"檢查範圍：{result['since']} 至 {result['through']}（台灣日期）", '']
    for release in releases:
        lines.extend([release['release_title'], '發行日期：' + release['release_date'], release['spotify_url'], ''])
    if not releases:
        lines.append('這段期間沒有查到新作品。')
    return {'to': config['recipient_email'], 'subject': f"{config['artist']} 新作品通知 — {result['through']}", 'body': '\n'.join(lines)}


def gmail_send(preview):
    token_path = LOCAL / 'gmail-token.json'
    if not token_path.exists():
        raise WatchError('Gmail 尚未授權；請先執行 authorize_gmail.py。')
    credentials = read_json(token_path)
    token = request_json('https://oauth2.googleapis.com/token', form={
        'client_id': credentials['client_id'], 'client_secret': credentials['client_secret'],
        'refresh_token': credentials['refresh_token'], 'grant_type': 'refresh_token'
    })['access_token']
    message = EmailMessage()
    message['To'] = preview['to']
    message['Subject'] = preview['subject']
    message.set_content(preview['body'])
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return request_json('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', headers={'Authorization': 'Bearer ' + token}, body={'raw': raw})


def notify(since=None, through=None):
    LOCAL.mkdir(parents=True, exist_ok=True)
    # Serialize scheduled and MCP sends sharing the same state.
    with (LOCAL / 'send.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = LOCAL / 'state.json'
        state = read_json(state_path) if state_path.exists() else {'deliveries': {}}
        config = settings()
        if since is None and state.get('last_successful_check'):
            since = state['last_successful_check']
        result = check_releases(since, through)
        recipient = config['recipient_email']
        delivered = set(state['deliveries'].get(recipient, []))
        pending = [item for item in result['releases'] if item['id'] not in delivered]
        if state.get('pending_send'):
            raise WatchError('上次寄信結果未確認。請先核對 Gmail 寄件備份，再處理 .local/state.json 的 pending_send，避免重複寄送。')
        if not pending:
            state['last_successful_check'] = result['through']
            save_json(state_path, state)
            return {'status': 'no_new_releases', 'sent': 0}
        result['releases'] = pending
        if not (LOCAL / 'gmail-token.json').exists():
            raise WatchError('Gmail 尚未授權；請先執行 authorize_gmail.py。')
        # Preserve an intent before sending; ambiguous timeouts require manual reconciliation.
        state['pending_send'] = {'recipient': recipient, 'release_ids': [item['id'] for item in pending]}
        save_json(state_path, state)
        response = gmail_send(notification_preview(result))
        if not response.get('id'):
            raise WatchError('Gmail 未回傳郵件 ID；請核對寄件備份。')
        state['deliveries'][recipient] = sorted(delivered | {item['id'] for item in pending})
        state['last_successful_check'] = result['through']
        state.pop('pending_send', None)
        save_json(state_path, state)
        return {'status': 'sent', 'sent': len(pending), 'message_id': response['id']}


def status():
    config = settings(require_recipient=False)
    path = LOCAL / 'secrets.json'
    secret = read_json(path) if path.exists() else {}
    return {'config': config,
            'spotify_credentials_present': bool(secret.get('spotify_client_id') and secret.get('spotify_client_secret')),
            'gmail_authorized': (LOCAL / 'gmail-token.json').exists(),
            'pending_send': (read_json(LOCAL / 'state.json').get('pending_send') if (LOCAL / 'state.json').exists() else None),
            'note': 'MCP 連線本身不會啟動排程；Gmail 插件授權也不會自動授權此服務。'}
