"""Install/restore a prepared local bundle with verified backups. No game process is killed."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path

def digest(data):return hashlib.sha256(data).hexdigest()
def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.akagiplus-',dir=path.parent,delete=False) as f:
        temp=Path(f.name);f.write(data);f.flush();os.fsync(f.fileno())
    try:os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
def ensure_closed():
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',"@(Get-Process -Name Mahjong-JP -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.stdout.strip()!='0':raise ValueError('Close RiichiCity before installing or restoring the local bundle.')
def target_for(game):
    game=game.resolve()
    if not (game/'Mahjong-JP.exe').is_file():raise ValueError('Expected the native Game folder containing Mahjong-JP.exe')
    hot=game/'Mahjong-JP_Data/_Data/Mahjong/Base/lua_network'
    if hot.exists():raise ValueError('A hot-update network bundle exists; review that client version before patching.')
    return game/'Mahjong-JP_Data/StreamingAssets/Base/lua_network'
def install(game,staged,backup_dir,journal,guard=ensure_closed):
    guard();target=target_for(game);report=json.loads(staged.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    current=target.read_bytes();original=current;patched=staged.read_bytes()
    if digest(original)!=report['source_sha256']:
        previous=json.loads(journal.read_text(encoding='utf-8')) if journal.is_file() else {}
        if (Path(previous.get('target','')).resolve()!=target or digest(current)!=previous.get('patched_sha256') or previous.get('original_sha256')!=report['source_sha256']):
            raise ValueError('Client file changed since preparation; never overwrite an unknown client update.')
        original=Path(previous['backup']).read_bytes()
        if digest(original)!=report['source_sha256']:raise ValueError('Original backup checksum mismatch')
    if digest(patched)!=report['patched_sha256']:raise ValueError('Staged patch checksum mismatch')
    backup=backup_dir.resolve()/digest(original)/'lua_network.original';backup.parent.mkdir(parents=True,exist_ok=True)
    if backup.exists():
        if digest(backup.read_bytes())!=digest(original):raise ValueError('Original backup checksum mismatch')
    else:
        with backup.open('xb') as f:f.write(original)
    record={'schema':1,'phase':'prepared','target':str(target),'backup':str(backup),'original_sha256':digest(original),'patched_sha256':digest(patched),'previous_sha256':digest(current),'payload_sha256':report.get('payload_sha256')}
    atomic(journal,json.dumps(record,indent=2).encode())
    if target.read_bytes()!=current:raise ValueError('Client changed during preparation; nothing overwritten')
    atomic(target,patched);assert digest(target.read_bytes())==record['patched_sha256']
    record['phase']='installed';atomic(journal,json.dumps(record,indent=2).encode());return record

def restore(game,journal,guard=ensure_closed):
    guard();target=target_for(game);record=json.loads(journal.read_text(encoding='utf-8'))
    if Path(record['target']).resolve()!=target:raise ValueError('Recovery target does not match this game installation')
    original=Path(record['backup']).read_bytes()
    if digest(original)!=record['original_sha256']:raise ValueError('Original backup checksum mismatch')
    current=digest(target.read_bytes())
    if current not in (record['original_sha256'],record['patched_sha256'],record.get('previous_sha256')):raise ValueError('Game updated or changed; refusing to overwrite it with an older backup')
    if current!=record['original_sha256']:atomic(target,original)
    record['phase']='restored';atomic(journal,json.dumps(record,indent=2).encode());return record

