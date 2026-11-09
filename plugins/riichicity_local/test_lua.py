"""Compile generated scripts and test the decoded ingress using isolated synthetic packets."""
from pathlib import Path
import ctypes,os,io,json,argparse,re
class Lua:
    def __init__(self,plugins):
        self.directory=os.add_dll_directory(str(plugins))
        self.lib=ctypes.CDLL(str(plugins/'tolua.dll'))
        L=self.lib
        L.luaL_newstate.restype=ctypes.c_void_p
        L.luaL_openlibs.argtypes=[ctypes.c_void_p]
        L.luaL_loadbufferx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.c_char_p];L.luaL_loadbufferx.restype=ctypes.c_int
        L.lua_pcallk.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ssize_t,ctypes.c_void_p];L.lua_pcallk.restype=ctypes.c_int
        L.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.POINTER(ctypes.c_size_t)];L.lua_tolstring.restype=ctypes.c_void_p
        L.lua_settop.argtypes=[ctypes.c_void_p,ctypes.c_int];L.lua_close.argtypes=[ctypes.c_void_p]
        self.state=L.luaL_newstate();assert self.state;L.luaL_openlibs(self.state)
    def run(self,source,execute=True):
        b=source.encode('utf-8');buf=ctypes.create_string_buffer(b)
        rc=self.lib.luaL_loadbufferx(self.state,buf,len(b),b'@AkagiPlus-local-test',b't')
        if rc==0 and execute:rc=self.lib.lua_pcallk(self.state,0,0,0,0,None)
        if rc:
            n=ctypes.c_size_t();ptr=self.lib.lua_tolstring(self.state,-1,ctypes.byref(n));msg=ctypes.string_at(ptr,n.value).decode('utf-8',errors='replace')
            raise AssertionError(msg)
        self.lib.lua_settop(self.state,0)
    def close(self):self.lib.lua_close(self.state);self.directory.close()

def main():
    import UnityPy
    p=argparse.ArgumentParser();p.add_argument('game',type=Path);p.add_argument('--bundle',type=Path,required=True);args=p.parse_args()
    runtime=Lua(args.game/'Mahjong-JP_Data/Plugins/x86_64')
    try:
        b=args.bundle.read_bytes();start=b.index(b'UnityFS\0');env=UnityPy.load(io.BytesIO(b[start:]));compiled=0;ingress=None
        for obj in env.objects:
            if obj.type.name=='TextAsset':
                source=obj.parse_as_object().m_Script;runtime.run(source,execute=False);compiled+=1
                if 'local function OnRecvMsg(wpacket)' in source:
                    ingress=source[source.index('local function OnRecvMsg(wpacket)'):source.index('local function PlayingHandle(data)')]
                    assert ingress.count('AkagiPlusLocalCosmetics.onMessage')==1, 'Hook must run at decoded ingress'
                    ingress=ingress.replace('local function OnRecvMsg(wpacket)','function APIngress(wpacket)',1)
        prefix='PAYLOAD='+json.dumps(str(Path(__file__).with_name('local_cosmetics.lua').resolve().as_posix()))+'\n'
        runtime.run(prefix+Path(__file__).with_name('test_local.lua').read_text(encoding='utf-8-sig'))
        assert ingress, 'Missing generated dispatcher'
        runtime.run(ingress)
        runtime.run('AP_TEST_PACKET(3);AP_TEST_PACKET(5);AP_TEST_PACKET(7)')
        # Exercise the installed client's actual avatar decoder, with a fake sprite loader.
        helper=args.game/'Mahjong-JP_Data/_Data/Mahjong/Base/lua_helper'
        if not helper.exists():helper=args.game/'Mahjong-JP_Data/StreamingAssets/Base/lua_helper'
        hb=helper.read_bytes();he=UnityPy.load(io.BytesIO(hb[hb.index(b'UnityFS\0'):]))
        renderer=None
        for obj in he.objects:
            if obj.type.name!='TextAsset':continue
            source=obj.parse_as_object().m_Script
            start=source.find('function M.LoadCustomHead(')
            if start<0:continue
            block=source[start:];end=re.search(r'^end\s*$',block,re.M)
            assert end,'Native head renderer structure changed'
            renderer=block[:end.end()].replace('function M.LoadCustomHead(','function AP_NATIVE_HEAD(',1)
            break
        assert renderer,'Native head renderer missing'
        runtime.run(renderer)
        runtime.run("""
GetRoleResName=function(role,skin,model) return {role,skin,model} end
EResType={Icon_SimpleHead=1}
local sprite=AP_NATIVE_HEAD(AP_TEST_FOLLOW_HEAD,10022,0,0,{LoadSprite=function(_,_,value)return value end})
assert(sprite[1]==10069 and sprite[2]==1006902 and sprite[3]==1,'native decoder must use the locally selected portrait')
""")
        print(json.dumps({'native_head_renderer':'passed','ingress_categories_tested':3,'patched_scripts_compile':compiled,'synthetic_lua_suite':'passed','game_started':False,'network_requests':0}))
    finally:runtime.close()
if __name__=='__main__':main()
