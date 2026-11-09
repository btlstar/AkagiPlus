"""Build a private, reversible local-cosmetics bundle; never modify installed files here."""
import argparse
from pathlib import Path
import hashlib,io,json,re
import UnityPy
MARKER='[AkagiPlus LocalCosmetics]'

def build(original,payload):
    if hashlib.sha256(original).hexdigest() != '487f9f573f323089f6339bf1bb257105d2e7cd376f1b67ade8b2a0988d757990':
        raise ValueError('This client Lua bundle has not been reviewed; do not patch an unknown game update.')
    at=original.find(b'UnityFS\0')
    if not 0<=at<=64: raise ValueError('Unrecognized bundle prefix')
    env=UnityPy.load(io.BytesIO(original[at:])); changed=[]
    before={}
    for obj in env.objects:
        if obj.type.name!='TextAsset':continue
        data=obj.parse_as_object();source=data.m_Script
        before[data.m_Name]=source
        if MARKER in source:raise ValueError('Already patched; use the verified original backup')
        if 'function this.MjGamePost(' in source:
            match=re.search(r'\breturn\s*$',source)
            if not match:raise ValueError('HTTP module return structure changed')
            insertion='\nlocal __ap = (function()\n'+payload+'\nend)()\n__ap.install(this)\n'
            data.m_Script=source[:match.start()]+insertion+source[match.start():];obj.patch(data);changed.append(data.m_Name)
        elif 'local function BroadcastHandle(data)' in source:
            target='data = Json.decode(bodyStr)'
            if source.count(target)!=1:raise ValueError('Ambiguous decoded message ingress')
            insertion=target+'\n            if AkagiPlusLocalCosmetics then pcall(AkagiPlusLocalCosmetics.onMessage,data) end'
            data.m_Script=source.replace(target,insertion);obj.patch(data);changed.append(data.m_Name)
    if len(changed)!=2:raise ValueError('Expected both known HTTP and broadcast modules')
    patched=original[:at]+env.file.save(packer='none')
    check=UnityPy.load(io.BytesIO(patched[at:]));after={o.parse_as_object().m_Name:o.parse_as_object().m_Script for o in check.objects if o.type.name=='TextAsset'}
    assert set(before)==set(after)
    assert all(before[k]==after[k] for k in before if k not in changed)
    assert MARKER in ''.join(after[k] for k in changed)
    return patched,changed

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.bundle.resolve()==args.output.resolve():raise ValueError('Build only into a separate staging file')
    original=args.bundle.read_bytes();payload=Path(__file__).with_name('local_cosmetics.lua').read_text(encoding='utf-8-sig')
    patched,changed=build(original,payload)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(patched)
    report={'schema':1,'payload_sha256':hashlib.sha256(payload.encode('utf-8')).hexdigest(),'source_sha256':hashlib.sha256(original).hexdigest(),'patched_sha256':hashlib.sha256(patched).hexdigest(),'changed_textassets':changed,'source_bytes':len(original),'patched_bytes':len(patched),'installed':False,'unitypy_version':UnityPy.__version__}
    args.output.with_suffix('.manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
