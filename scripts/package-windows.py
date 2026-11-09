"""Stage an allowlisted Windows portable release; never copy a working profile."""
import argparse, hashlib, json, shutil, zipfile, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
TRIPLE = 'x86_64-pc-windows-msvc'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def copy_tree(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'settings*.yaml', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', '__phello__', 'Scripts', '*.pdb'), dirs_exist_ok=True)
def main():
    p = argparse.ArgumentParser(); p.add_argument('--exe', type=Path, default=ROOT/'target/release/akagi.exe'); a = p.parse_args()
    import tomllib
    version = tomllib.loads((ROOT/'Cargo.toml').read_text(encoding='utf8'))['package']['version']
    name = f'AkagiPlus-{version}-windows-x64'
    stage = ROOT/'dist/staging'/name
    if stage.exists(): raise ValueError('Staging directory already exists; review it before rebuilding or choose a fresh release version.')
    runtime = ROOT/'runtime/python'/TRIPLE
    if not (runtime/'python.exe').is_file(): raise ValueError('Portable Python runtime is missing')
    stage.mkdir(parents=True)
    shutil.copy2(a.exe, stage/'AkagiPlus.exe')
    for file in ['LICENSE.txt', 'NOTICE']:
        shutil.copy2(ROOT/file, stage/file)
    copy_tree(ROOT/'LICENSES', stage/'LICENSES')
    copy_tree(ROOT/'plugins/majsoulmax', stage/'plugins/majsoulmax')
    for file in ['local_cosmetics.lua', 'build.py', 'install.py', 'README.md', 'requirements.txt']:
        dst=stage/'plugins/riichicity_local'/file; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/'plugins/riichicity_local'/file,dst)
    for file in ['local_cosmetics.lua', 'build.py', 'manage.py', 'README.md', 'requirements.txt', 'plugin.toml', 'LICENSE.txt']:
        dst=stage/'plugins/zhangxinplus'/file; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(ROOT/'plugins/zhangxinplus'/file,dst)
    (stage/'scripts').mkdir()
    shutil.copy2(ROOT/'scripts/riichicity-local.py', stage/'scripts/riichicity-local.py')
    copy_tree(runtime, stage/'runtime/python'/TRIPLE)
    uv = ROOT/'runtime/uv'/TRIPLE
    if not (uv/'uv.exe').is_file(): raise ValueError('Portable uv runtime is missing')
    copy_tree(uv, stage/'runtime/uv'/TRIPLE)
    copy_tree(ROOT/'docs/runtime-licenses', stage/'LICENSES/runtime')
    shutil.copy2(ROOT/'docs/runtime-lock.json',stage/'runtime/versions.json')
    (stage/'configs').mkdir()
    # Intentional fresh config, NOT derived from the developer's settings.
    (stage/'configs/config.toml').write_text('''[general]
first_run_completed = false
developer_mode = false
[platform]
kind = "Majsoul"
[proxy]
enabled = true
addr = "127.0.0.1:23410"
ca_dir = "./ca"
[proxy.majsoulmax]
enabled = false
python = "runtime/python/x86_64-pc-windows-msvc/python.exe"
worker = "plugins/majsoulmax/worker.py"
data_dir = ".local/majsoulmax"
[proxy.riichicity_unlock]
enabled = false
executable = ""
ca_path = ""
client_path = ""
injector_path = ""
[bot]
enabled = true
[bot.api]
enabled = false
key = ""
model_4p = ""
model_3p = ""
[autoplay]
enabled = false
''',encoding='utf8')
    shutil.copy2(ROOT/'docs/RELEASE_README.txt',stage/'README.txt')
    # Hash every shipped file before any local smoke-test creates profiles/logs.
    files={str(f.relative_to(stage)).replace('\\','/'):digest(f) for f in sorted(stage.rglob('*')) if f.is_file()}
    forbidden = [s for s in files if any(x in Path(s).parts for x in ['.local','.git','logs','ca','history']) or s.endswith(('.key','.pyc')) or (s.endswith('.bat') and not s.startswith('runtime/'))]
    assert not forbidden, forbidden
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    plugin_version=tomllib.loads((ROOT/'plugins/zhangxinplus/plugin.toml').read_text('utf8'))['version']
    manifest={'version':version,'source_commit':commit,'upstream':'shinkuan/Akagi@63cea4b5d23d83bbee8d56bc3b9d547cca2046c3','plugins':{'ZhangxinPlus':plugin_version},'files':files}
    (stage/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    archive=ROOT/'dist'/f'{name}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(stage.rglob('*')):
            if f.is_file():z.write(f,Path(name)/f.relative_to(stage))
    (archive.with_suffix('.zip.sha256')).write_text(digest(archive)+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'files':len(files),'sha256':digest(archive)},indent=2))
if __name__=='__main__':main()
