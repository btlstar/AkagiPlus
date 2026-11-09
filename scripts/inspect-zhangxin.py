"""Read-only static inventory for the installed Zhangxin PC client.

Writes names/metadata only. Never launches the game, patches its files, sends
network traffic, or extracts reusable artwork/script contents.
"""
import argparse
import json
from pathlib import Path
import re
import struct

MAX_BLOCK = 16 * 1024 * 1024

def lz4_block(data, expected):
    if expected > MAX_BLOCK:
        raise ValueError('LZ4 block exceeds inspection cap')
    out = bytearray()
    offset = 0
    def length(value):
        nonlocal offset
        if value == 15:
            while True:
                value2 = data[offset]; offset += 1; value += value2
                if value2 != 255:
                    break
        return value
    while offset < len(data):
        token = data[offset]; offset += 1
        literal = length(token >> 4)
        if offset + literal > len(data) or len(out) + literal > expected:
            raise ValueError('Invalid literal length')
        out.extend(data[offset:offset + literal]); offset += literal
        if offset == len(data):
            break
        distance = int.from_bytes(data[offset:offset + 2], 'little'); offset += 2
        if not distance or distance > len(out):
            raise ValueError('Invalid LZ4 distance')
        count = length(token & 15) + 4
        if len(out) + count > expected:
            raise ValueError('Invalid match length')
        pattern = bytes(out[-distance:][:count])
        out.extend((pattern * ((count + len(pattern) - 1) // len(pattern)))[:count])
    if len(out) != expected:
        raise ValueError('Unexpected decompressed size')
    return bytes(out)

def decompress(data, expected, flags):
    method = flags & 63
    if method == 0:
        if len(data) != expected:
            raise ValueError('Unexpected stored size')
        return data
    if method in (2, 3):
        return lz4_block(data, expected)
    raise ValueError(f'Unsupported compression {method}')

def inspect_bundle(path):
    with path.open('rb') as source:
        head = source.read(256)
        prefix = head.find(b'UnityFS\0')
        if prefix < 0:
            raise ValueError('No UnityFS header')
        header = head[prefix:]
        version = struct.unpack_from('>I', header, 8)[0]
        offset = 12
        strings = []
        for _ in range(2):
            end = header.index(0, offset)
            strings.append(header[offset:end].decode('ascii'))
            offset = end + 1
        size, compressed, uncompressed, flags = struct.unpack_from('>QIII', header, offset)
        offset += 20
        if version >= 7:
            offset = (offset + 15) // 16 * 16
        info_offset = size - compressed if flags & 128 else offset
        source.seek(prefix + info_offset)
        info = decompress(source.read(compressed), uncompressed, flags)
        count = struct.unpack_from('>I', info, 16)[0]
        if count > 100000:
            raise ValueError('Invalid block count')
        blocks = [struct.unpack_from('>IIH', info, 20 + i * 10) for i in range(count)]
        offset = offset if flags & 128 else offset + compressed
        if flags & 512:
            offset = (offset + 15) // 16 * 16
        source.seek(prefix + offset)
        # Object names/containers normally sit in the first serialized block.
        # Partial inspection deliberately does not promise a complete asset list.
        first_size, first_compressed, first_flags = blocks[0]
        first = decompress(source.read(first_compressed), first_size, first_flags)
    paths = sorted(set(x.decode('ascii') for x in re.findall(rb'assets/[A-Za-z0-9_./@+() -]{3,300}', first)))
    return {'file': path.name, 'prefix_bytes': prefix, 'unity': strings[1],
            'paths': paths, 'inspected_bytes': len(first), 'total_blocks': len(blocks)}

def metadata_names(path):
    data = path.read_bytes()
    header = struct.unpack_from('<8I', data)
    if header[0] != 0xFAB11BAF or header[6] + header[7] > len(data):
        raise ValueError('Unknown metadata header')
    names = data[header[6]:header[6] + header[7]].decode('utf-8', errors='replace').split('\0')
    candidates = ['LuaManager', 'LuaState', 'LuaInterface', 'ToLua', 'NetworkManager',
                  'Protobuff', 'WebSocketChannel', 'AssetBundleManager', 'LuaLoadBuffer']
    return {'version': header[1], 'symbols': [x for x in candidates if any(x in n for n in names)]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('install', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=0, help='0 inspects all bundle headers/first blocks')
    args = parser.parse_args()
    folder = args.install / 'zhangxinmj_Data'
    assets = folder / 'StreamingAssets'
    files = sorted(x for x in assets.iterdir() if x.is_file() and not x.suffix)
    config = json.loads((assets / 'config.txt').read_text(encoding='utf-8-sig'))
    result = {'read_only': True, 'inventory_complete': False,
              'limitation': 'Only first decompressed block per bundle; names do not prove ownership or loadability.',
              'resource_version': (assets / 'version_num.txt').read_text().strip(),
              'game_address': config.get('GameAddress'),
              'metadata': metadata_names(folder / 'il2cpp_data/Metadata/global-metadata.dat'),
              'bundle_count': len(files), 'bundles': [], 'errors': []}
    for index, file in enumerate(files[:args.limit or None], 1):
        try:
            result['bundles'].append(inspect_bundle(file))
        except (ValueError, IndexError, struct.error, OSError) as error:
            result['errors'].append({'file': file.name, 'error': str(error)})
        if index % 250 == 0:
            print(f'Inspected {index}/{len(files)} bundle first blocks', flush=True)
    all_paths = [p for b in result['bundles'] for p in b['paths']]
    categories = {'lua': r'\.lua(?:\.bytes)?$', 'protocol': r'proto|protocol|message',
                  'config': r'config|datatable|excel|csv', 'cosmetics': r'skin|costume|dress|decorate|character|role|avatar|huan|paibei|zhuobu'}
    result['candidates'] = {key: sorted(set(p for p in all_paths if re.search(pattern, p, re.I))) for key, pattern in categories.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'inspected': len(result['bundles']), 'errors': len(result['errors']),
                      'paths': len(set(all_paths)), 'candidate_counts': {k: len(v) for k, v in result['candidates'].items()}}))

if __name__ == '__main__':
    main()
