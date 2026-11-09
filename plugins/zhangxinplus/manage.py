"""Install/status/restore a verified Zhangxin patch. Never kills a game process."""
import argparse, json, os, subprocess, tempfile
from pathlib import Path
from build import BASELINE, digest, build

def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.akagiplus-',dir=path.parent,delete=False) as f:
        tmp=Path(f.name);f.write(data);f.flush();os.fsync(f.fileno())
    try: os.replace(tmp,path)
    finally: tmp.unlink(missing_ok=True)

def closed():
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',"@(Get-Process -Name zhangxinmj -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if r.stdout.strip()!='0': raise ValueError('Close Zhangxin before changing its bundles')

def paths(game):
    game=game.resolve()
    if not (game/'zhangxinmj.exe').is_file(): raise ValueError('Wrong game installation')
    root=game/'zhangxinmj_Data'
    hot=root/'_Data/Mahjong'
    if not (hot/'version_num.txt').is_file(): raise ValueError('请先启动掌心，完成官方资源更新后退出游戏。')
    if (hot/'version_num.txt').read_text().strip()!='92217': raise ValueError('当前掌心资源版本未适配，请等待 ZhangxinPlus 更新。')
    result={f'_Data/Mahjong/{name}':hot/name for name in BASELINE}
    if not all(p.is_file() for p in result.values()): raise ValueError('官方资源尚未下载完整，请先正常启动并更新掌心。')
    return result

def validate_journal(game,journal):
    r=json.loads(journal.read_text('utf-8'))
    if r.get('schema')!=1 or Path(r['game']).resolve()!=game.resolve(): raise ValueError('Recovery belongs to another installation')
    root=game.resolve()/'zhangxinmj_Data'
    allowed={f'{folder}/{name}' for folder in ('_Data/Mahjong',) for name in BASELINE}
    seen=set()
    for item in r['files']:
        rel=item['relative']
        if rel not in allowed or rel in seen: raise ValueError('Unexpected recovery target')
        seen.add(rel)
        target=(root/rel).resolve()
        if root.resolve() not in target.parents: raise ValueError('Recovery target escaped game folder')
        original=Path(item['backup']).read_bytes()
        if digest(original)!=BASELINE[Path(rel).name] or digest(original)!=item['original_sha256']: raise ValueError('Original backup checksum mismatch')
        if digest(target.read_bytes()) not in (item['original_sha256'],item['patched_sha256']): raise ValueError('Game updated or changed; refusing to overwrite')
    if len(seen)!=len(BASELINE): raise ValueError('Incomplete recovery record')
    return r

def install(game,staged,journal,guard=closed):
    guard();game=game.resolve();journal=journal.resolve()
    if journal==game or game in journal.parents: raise ValueError('Recovery must be stored outside game folder')
    m=json.loads((staged/'manifest.json').read_text('utf-8'))
    if m.get('schema')!=1 or {b['name'] for b in m['bundles']}!=set(BASELINE) or len(m['bundles'])!=len(BASELINE): raise ValueError('Incomplete staging manifest')
    previous=validate_journal(game,journal) if journal.is_file() else None
    previous_files={x['relative']:x for x in previous['files']} if previous else {}
    records=[];plan=[]
    for rel,target in paths(game).items():
        name=target.name;record=next(x for x in m['bundles'] if x['name']==name)
        if record['original_sha256']!=BASELINE[name]: raise ValueError('Unreviewed original')
        patched=(staged/name).read_bytes()
        if digest(patched)!=record['patched_sha256']: raise ValueError('Staged patch checksum mismatch')
        current=target.read_bytes();original=current
        if digest(current)!=BASELINE[name]:
            old=previous_files.get(rel)
            if not old or digest(current)!=old['patched_sha256']: raise ValueError('Unreviewed active client bundle')
            original=Path(old['backup']).read_bytes()
        backup=journal.parent/'originals'/BASELINE[name]/name
        if backup.exists():
            if digest(backup.read_bytes())!=BASELINE[name]: raise ValueError('Backup checksum mismatch')
        else: atomic(backup,original)
        records.append(dict(relative=rel,backup=str(backup),original_sha256=BASELINE[name],patched_sha256=digest(patched)))
        plan.append((target,current,patched))
    r=dict(schema=1,game=str(game),phase='prepared',payload_sha256=m.get('payload_sha256'),files=records)
    atomic(journal,json.dumps(r,indent=2).encode())
    for target,current,patched in plan:
        guard()
        if target.read_bytes()!=current: raise ValueError('Game files changed while preparing')
        atomic(target,patched)
        if digest(target.read_bytes())!=digest(patched): raise ValueError('Installed checksum mismatch')
    r['phase']='installed';atomic(journal,json.dumps(r,indent=2).encode());return r

def restore(game,journal,guard=closed):
    guard();r=validate_journal(game,journal)
    for item in r['files']:
        guard();target=game.resolve()/'zhangxinmj_Data'/item['relative']
        if digest(target.read_bytes()) not in (item['original_sha256'],item['patched_sha256']): raise ValueError('Game changed during restore')
        atomic(target,Path(item['backup']).read_bytes())
    r['phase']='restored';atomic(journal,json.dumps(r,indent=2).encode());return r

def prepare_install(game,staged,journal):
    closed();targets=paths(game)
    previous=validate_journal(game,journal) if journal.is_file() else None
    old={x['relative']:x for x in previous['files']} if previous else {}
    payload=Path(__file__).with_name('local_cosmetics.lua').read_text('utf-8')
    staged.mkdir(parents=True,exist_ok=True);records=[]
    for rel,target in targets.items():
        raw=target.read_bytes();name=target.name
        if digest(raw)!=BASELINE[name]:
            entry=old.get(rel)
            if not entry or digest(raw)!=entry['patched_sha256']: raise ValueError('游戏资源已变化，不能覆盖未知文件。')
            raw=Path(entry['backup']).read_bytes()
        patched,changed=build(raw,name,payload)
        atomic(staged/name,patched)
        records.append(dict(name=name,original_sha256=digest(raw),patched_sha256=digest(patched),changed=changed))
    atomic(staged/'manifest.json',json.dumps(dict(schema=1,resource_version='92217',payload_sha256=digest(payload.encode()),bundles=records)).encode())
    return install(game,staged,journal)

def status(game,journal):
    targets=paths(game)
    if not journal.is_file():
        supported=all(digest(p.read_bytes())==BASELINE[p.name] for p in targets.values())
        return dict(status='not_installed' if supported else 'unsupported',message='未安装 ZhangxinPlus' if supported else '游戏文件版本未适配，请等待插件更新。')
    try:r=validate_journal(game,journal)
    except ValueError as e:return dict(status='needs_attention',message=str(e))
    installed=all(digest((game.resolve()/'zhangxinmj_Data'/x['relative']).read_bytes())==x['patched_sha256'] for x in r['files'])
    if not installed:return dict(status='not_installed',message='未安装或已还原 ZhangxinPlus')
    current=digest(Path(__file__).with_name('local_cosmetics.lua').read_text('utf-8').encode())
    if r.get('payload_sha256')!=current:return dict(status='update_available',message='ZhangxinPlus 已安装，插件代码有更新。')
    result=dict(status='installed',message='ZhangxinPlus 已安装 · 资源 92217')
    heartbeat=game/'zhangxinmj_Data/_Data/Mahjong/zhangxinplus-status.json'
    if heartbeat.is_file():
        try:
            value=json.loads(heartbeat.read_text('utf-8-sig'))
            if value.get('plugin')=='ZhangxinPlus' and value.get('version')=='0.1.5':
                result['message']+=' · 游戏曾加载';result['runtime']={k:value.get(k) for k in ('reads','writes','last_route','ai_frames','ai_error','last_error','scheme_id_type')}
        except (ValueError,OSError):pass
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['install','restore','status']);p.add_argument('game',type=Path)
    p.add_argument('--state-dir',type=Path,default=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ZhangxinPlus')
    p.add_argument('--json',action='store_true');args=p.parse_args()
    journal=args.state_dir/'install.json'
    try:
        if args.action=='status':result=status(args.game,journal)
        elif args.action=='restore':
            restore(args.game,journal);result=dict(status='restored',message='已还原掌心游戏文件，保留本地装扮选择。')
        else:
            prepare_install(args.game,args.state_dir/'staged',journal)
            result=dict(status='installed',message='ZhangxinPlus 已安装，原文件已备份。请重新启动掌心。')
        print(json.dumps(result,ensure_ascii=True) if args.json else result['message'])
        return 0
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as e:
        import sys
        print('ZhangxinPlus: '+str(e),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
