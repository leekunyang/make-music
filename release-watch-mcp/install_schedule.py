"""Prepare or install a macOS 08:00 local-time LaunchAgent."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import core

LABEL = 'com.djfat.release-watch'


def install(enable=False):
    config = core.settings()
    clock = config.get('check_time', '08:00').split(':')
    hour, minute = map(int, clock)
    if config.get('timezone') != 'Asia/Taipei' or config.get('frequency') != 'daily':
        raise core.WatchError('此排程安裝程式只支援 Asia/Taipei 每日排程。')
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise core.WatchError('check_time 不合法。')
    core.LOCAL.mkdir(parents=True, exist_ok=True)
    payload = {
        'Label': LABEL,
        'ProgramArguments': [sys.executable, str(core.ROOT / 'server.py'), '--notify'],
        'WorkingDirectory': str(core.ROOT),
        'StartCalendarInterval': {'Hour': hour, 'Minute': minute},
        'StandardOutPath': str(core.LOCAL / 'schedule.log'),
        'StandardErrorPath': str(core.LOCAL / 'schedule-error.log')
    }
    preview = core.LOCAL / (LABEL + '.plist')
    preview.write_bytes(plistlib.dumps(payload))
    if not enable:
        print(f'排程檔已準備，尚未啟用：{preview}')
        return
    status = core.status()
    if not status['spotify_credentials_present'] or not status['gmail_authorized']:
        raise core.WatchError('Spotify 憑證及 Gmail 授權完成後才能啟用排程。')
    zone = str(Path('/etc/localtime').resolve())
    if not zone.endswith('/Asia/Taipei'):
        raise core.WatchError('LaunchAgent 使用電腦本機時區；請確認 macOS 時區為 Asia/Taipei。')
    target = Path.home() / 'Library' / 'LaunchAgents' / preview.name
    domain = f'gui/{os.getuid()}'
    existing = subprocess.run(['launchctl', 'print', domain + '/' + LABEL], capture_output=True)
    if existing.returncode == 0:
        print('排程已存在，未重複安裝。')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(preview.read_bytes())
    subprocess.run(['launchctl', 'bootstrap', domain, str(target)], check=True)
    subprocess.run(['launchctl', 'print', domain + '/' + LABEL], check=True, stdout=subprocess.DEVNULL)
    config['status'] = 'scheduled'
    config['schedule_created'] = True
    core.save_json(core.CONFIG, config)
    print(f'已啟用每日 {hour:02}:{minute:02} 本機排程。電腦須保持開機並登入。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--enable', action='store_true')
    try:
        install(parser.parse_args().enable)
    except (core.WatchError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error) if isinstance(error, core.WatchError) else '排程安裝失敗，請檢查 macOS 時區與 launchctl。')
