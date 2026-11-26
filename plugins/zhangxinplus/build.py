"""Build a verified Zhangxin local patch; no installed files are written."""
import argparse, hashlib, io, json, re
from pathlib import Path
import UnityPy

RESOURCE_VERSIONS = ('92217', '92318')
LEGACY_BASELINE = {
    'df6b54478d440170373e336b88ffe419': 'a6da50485d36c4e50cd5e26dcc82a05ac88d1c85cfbf44226b9f4034e5bbbbed',
    '6356fb4c08102b577abf1dead61d6444': '26914c132413a75eba62b07c62c74ed17dbda15d8d2a0ea5e68e3b88839f28e3',
}
PROFILE_BUNDLE = 'f77ab875fc09a414ea3a55e68c867d48'
BASELINE = {
    **LEGACY_BASELINE,
    PROFILE_BUNDLE: 'd60878258780c61dece57df871b61c9124c9179107dd34070a9e0e4dc949bb5e',
}
VOICE_VIEWS = {'f6b59388299f8c5359f4a6ac3c505ef1.lua', 'dff0f0c82e409d273f71db7c32217b92.lua'}
EMOJI_VIEWS = {'804b208063e8ac3203610e589daadab5.lua', 'c90a4c2d06ed726bb153c57deade146b.lua'}
AWAKE = 'self.role_info.cultivateStatus'
FINISHED = 'EnumDefine.CultivateStatus.FinishedAwaken'
PREVIEW = '(ZhangxinPlus and ZhangxinPlus.canPreviewAwakening(self.role_info))'

def patch_profile(name, source):
    if name in VOICE_VIEWS:
        # The same predicate controls the lock icon and the playback click.
        target = f'if {AWAKE} >= {FINISHED} then'
        replacement = f'if {PREVIEW} or {AWAKE} >= {FINISHED} then'
    else:
        target = f'data.anim_info.is_awake == EnumDefine.ExpressionType.Awake and {AWAKE} < {FINISHED}'
        replacement = f'{target} and not {PREVIEW}'
    if source.count(target) != 1:
        raise ValueError(f'Unexpected profile awakening check in {name}')
    return source.replace(target, replacement)

def resource_version(source):
    version=(source/'version_num.txt').read_text().strip()
    if version not in RESOURCE_VERSIONS:
        raise ValueError('当前掌心资源 '+version+' 未适配，支持 '+', '.join(RESOURCE_VERSIONS)+'。请更新 ZhangxinPlus。')
    return version

def bundle_names(version, baseline):
    return tuple(name for name in baseline if version == '92318' or name != PROFILE_BUNDLE)

def digest(b): return hashlib.sha256(b).hexdigest()
def scripts(b):
    at=b.index(b'UnityFS\0')
    if at!=28: raise ValueError('Unreviewed bundle prefix')
    return at,UnityPy.load(io.BytesIO(b[at:]))
def build(raw,name,payload):
    if digest(raw)!=BASELINE[name]: raise ValueError('Unsupported Zhangxin client update')
    at,env=scripts(raw);before={};changed=[]
    for obj in env.objects:
        if obj.type.name!='TextAsset': continue
        data=obj.parse_as_object();source=data.m_Script;before[data.m_Name]=source
        if name.startswith('df6b') and 'function this.MjGamePost(' in source:
            m=re.search(r'\breturn\s*$',source)
            if not m: raise ValueError('HTTP module shape changed')
            source=source[:m.start()]+'\nlocal __ap=(function()\n'+payload+'\nend)()\n__ap.install(this)\n'+source[m.start():]
        elif name.startswith('6356') and 'local function OnRecvMsg(wpacket)' in source:
            target='data = Json.decode(bodyStr)'
            if source.count(target)!=1: raise ValueError('Ambiguous decoded message ingress')
            source=source.replace(target,target+'\n            if ZhangxinPlus then pcall(ZhangxinPlus.onMessage,data) end')
        elif name == PROFILE_BUNDLE and data.m_Name in VOICE_VIEWS | EMOJI_VIEWS:
            source = patch_profile(data.m_Name, source)
        else: continue
        data.m_Script=source;obj.patch(data);changed.append(data.m_Name)
    if name == PROFILE_BUNDLE:
        if len(changed) != 4 or set(changed) != VOICE_VIEWS | EMOJI_VIEWS:
            raise ValueError('Expected four known profile modules')
    elif len(changed) != 1:
        raise ValueError('Expected exactly one known module per bundle')
    patched=raw[:at]+env.file.save(packer='lz4')
    _,check=scripts(patched)
    after={o.parse_as_object().m_Name:o.parse_as_object().m_Script for o in check.objects if o.type.name=='TextAsset'}
    if set(before)!=set(after) or any(before[k]!=after[k] for k in before if k not in changed):
        raise ValueError('Unrelated script changed during serialization')
    return patched,changed

def prepare(game,out):
    game=game.resolve();out=out.resolve()
    if not (game/'zhangxinmj.exe').is_file(): raise ValueError('Expected Zhangxin installation folder')
    if out==game or game in out.parents: raise ValueError('Staging must be outside the game')
    source=game/'zhangxinmj_Data/_Data/Mahjong'
    version=resource_version(source)
    payload=Path(__file__).with_name('local_cosmetics.lua').read_text('utf-8')
    records=[];out.mkdir(parents=True,exist_ok=True)
    for name in bundle_names(version, BASELINE):
        raw=(source/name).read_bytes();patched,changed=build(raw,name,payload)
        (out/name).write_bytes(patched)
        records.append(dict(name=name,original_sha256=digest(raw),patched_sha256=digest(patched),changed=changed))
    manifest=dict(schema=1,resource_version=version,payload_sha256=digest(payload.encode()),bundles=records)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('game',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    print(json.dumps(prepare(args.game,args.output)))
