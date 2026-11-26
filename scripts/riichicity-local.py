"""Manage the opt-in, reversible native RiichiCity cosmetic patch."""
import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/riichicity_local'
spec = importlib.util.spec_from_file_location('local_cosmetics_install', PLUGIN / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
JOURNAL = ROOT / '.local/riichicity-local-install.json'


def game_folder():
    config = ROOT / '.local/config.toml'
    client = ''
    if config.is_file():
        with config.open('rb') as source:
            client = tomllib.load(source).get('proxy', {}).get('riichicity_unlock', {}).get('client_path', '')
    return Path(client).parent if client else Path(os.environ['APPDATA']) / 'RiichicityLauncher/Game'


def asset_python():
    setting = ROOT / '.local/riichicity-local-python.txt'
    if setting.is_file():
        candidate = Path(setting.read_text(encoding='utf-8-sig').strip())
        if candidate.is_absolute() and candidate.is_file():
            return str(candidate)
        raise ValueError('The configured asset Python environment no longer exists.')
    return sys.executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'restore', 'status'], default='status', nargs='?')
    parser.add_argument('--game', type=Path, help='Game folder containing Mahjong-JP.exe')
    parser.add_argument('--json', action='store_true', help='Machine-readable GUI result')
    parser.add_argument('--state-dir', type=Path, help='Shared backup/journal directory')
    args = parser.parse_args()
    journal = args.state_dir / 'install.json' if args.state_dir else JOURNAL
    backup_dir = args.state_dir / 'backups' if args.state_dir else ROOT / '.local/backups/riichicity-local'
    staged = (args.state_dir or ROOT / '.local/riichicity-local') / 'staged-lua_network'
    def report(status, message, available_version=None):
        result = {'status': status, 'message': message, 'available_version': available_version}
        print(json.dumps(result, ensure_ascii=True) if args.json else message)
    try:
        payload = (PLUGIN / 'local_cosmetics.lua').read_text(encoding='utf-8-sig')
        matched_version = re.search(r'^local A = \{version = (\d+),', payload, re.M)
        version = int(matched_version.group(1)) if matched_version else None
        game = args.game or game_folder()
        target = installer.target_for(game)
        current = installer.digest(target.read_bytes())
        # Adopt this checkout's verified older recovery record once; never copy personal choices.
        if not journal.is_file() and args.state_dir and JOURNAL.is_file():
            previous = json.loads(JOURNAL.read_text(encoding='utf8'))
            if Path(previous['target']).resolve() == target and current in (previous['patched_sha256'], previous['original_sha256']):
                original = Path(previous['backup']).read_bytes()
                if installer.digest(original) != previous['original_sha256']: raise ValueError('Original backup checksum mismatch')
                backup = backup_dir.resolve() / previous['original_sha256'] / 'lua_network.original'
                installer.atomic(backup, original)
                previous['backup'] = str(backup)
                installer.atomic(journal, json.dumps(previous, indent=2).encode())
        if args.action == 'status':
            record = json.loads(journal.read_text(encoding='utf-8')) if journal.is_file() else {}
            same_target = Path(record.get('target', '')).resolve() == target
            patched = same_target and current == record.get('patched_sha256')
            if patched and record.get('payload_sha256') != installer.digest(payload.encode('utf-8')):
                report('update_available', '游戏仍安装着旧补丁，请退出游戏后安装新版。', version)
            elif patched:
                report('installed', '本地装扮已安装。', version)
            else:
                report('not_installed', '未安装或客户端已更新。', version)
            return 0
        if args.action == 'restore':
            installer.restore(game, journal)
            report('restored', '已还原游戏文件，保留本地装扮选择。')
            return 0
        installer.ensure_closed()
        source = target
        if journal.is_file():
            record = json.loads(journal.read_text(encoding='utf-8'))
            if Path(record['target']).resolve() == target and current == record['patched_sha256']:
                source = Path(record['backup'])
                if installer.digest(source.read_bytes()) != record['original_sha256']:
                    raise ValueError('Backup checksum mismatch; do not reinstall or delete the backup.')
        subprocess.run([asset_python(), str(PLUGIN / 'build.py'), str(source), '--output', str(staged)], check=True, cwd=ROOT, capture_output=True, text=True)
        if installer.digest(staged.read_bytes()) == current:
            report('installed', '当前本地装扮已是最新。', version)
            return 0
        installer.install(game, staged, backup_dir, journal)
        report('installed', '本地装扮已安装，原文件已备份。重新启动游戏后生效。', version)
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f'补丁操作失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
