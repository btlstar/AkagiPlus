"""Use the installed game's Lua runtime, with isolated synthetic local data."""
import argparse,importlib.util,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('game',type=Path);p.add_argument('--staged',type=Path,required=True);args=p.parse_args()
    helper=Path(__file__).parents[1]/'riichicity_local/test_lua.py'
    spec=importlib.util.spec_from_file_location('lua_test_runtime',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    runtime=module.Lua(args.game/'zhangxinmj_Data/Plugins/x86_64')
    try:
        import UnityPy
        compiled=0
        for file in args.staged.iterdir():
            if file.suffix:continue
            b=file.read_bytes();env=UnityPy.load(b[b.index(b'UnityFS\0'):])
            for o in env.objects:
                if o.type.name=='TextAsset':runtime.run(o.read().m_Script,execute=False);compiled+=1
        # Exercise the installed client's own scheme request/response callbacks.
        native=args.game/'zhangxinmj_Data/_Data/Mahjong/703145a6b5c1ec69d3ef0cdc7f1d05a9'
        if not native.is_file():native=args.game/'zhangxinmj_Data/StreamingAssets/703145a6b5c1ec69d3ef0cdc7f1d05a9'
        raw=native.read_bytes();env=UnityPy.load(raw[raw.index(b'UnityFS\0'):])
        model=next(o.read().m_Script for o in env.objects if o.type.name=='TextAsset' and o.read().m_Name=='deb5dcc9fd4a506bd0764cf07782ecff.lua')
        native_view=args.game/'zhangxinmj_Data/_Data/Mahjong/07d2773d59ea1a821b15d5d4a4fa5fc2'
        if not native_view.is_file():native_view=args.game/'zhangxinmj_Data/StreamingAssets/07d2773d59ea1a821b15d5d4a4fa5fc2'
        raw=native_view.read_bytes();env=UnityPy.load(raw[raw.index(b'UnityFS\0'):])
        view=next(o.read().m_Script for o in env.objects if o.type.name=='TextAsset' and o.read().m_Name=='f3c87572ca668fbd80365775038f91ad.lua')
        factories='NATIVE_SCHEME_FACTORY=function()\n'+model+'\nend\n'
        factories+='NATIVE_SCHEME_VIEW_FACTORY=function()\nlocal require=function()return {}end\nlocal Vector3={New=function()return {}end}\n'+view+'\nend\n'
        factories='NATIVE_JSON=assert(package.loadlib('+json.dumps((args.game/'zhangxinmj_Data/Plugins/x86_64/tolua.dll').resolve().as_posix())+",'luaopen_cjson'))()\n"+factories
        runtime.run(factories+'PAYLOAD='+json.dumps(Path(__file__).with_name('local_cosmetics.lua').resolve().as_posix())+'\n'+Path(__file__).with_name('test_local.lua').read_text('utf-8'))
        print(json.dumps(dict(compiled_scripts=compiled,local_selection_persistence_isolation='passed',game_network_requests=0,native_scheme_callbacks='passed',native_scheme_use_click='passed')))
    finally:runtime.close()

if __name__=='__main__':main()
