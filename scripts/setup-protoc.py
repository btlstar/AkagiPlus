"""Install a pinned, verified portable protoc; no system/PATH changes."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--direct', action='store_true', help='Ignore HTTP proxy environment for this download')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This helper installs Windows x64 protoc. On other systems install protobuf-compiler/protobuf.')
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/'scripts/protoc-windows.json').read_text(encoding='utf-8'))
    target = (args.destination or root/'.local/tools/protoc').resolve()
    exe = target/'bin/protoc.exe'
    expected = 'libprotoc ' + manifest['version']
    if exe.is_file():
        result = subprocess.run([str(exe), '--version'], capture_output=True, text=True, check=True)
        if result.stdout.strip() == expected:
            print(expected + ' already installed: ' + str(exe)); return
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if args.direct else urllib.request.build_opener()
    print('Downloading official protoc ' + manifest['version'] + ' (about 3.3 MB)', flush=True)
    blob = None
    urls = [manifest['url']]
    if manifest.get('api_url'):
        import time
        urls.append(manifest['api_url'] + '?download=' + str(int(time.time())))
    for url in urls:
        request = urllib.request.Request(url, headers={'User-Agent':'AkagiPlus-build-setup', 'Accept':'application/octet-stream'})
        try:
            with opener.open(request, timeout=30) as response:
                blob = response.read(8 * 1024 * 1024)
            if hashlib.sha256(blob).hexdigest() == manifest['sha256']:
                break
            blob = None
        except (OSError, urllib.error.HTTPError) as exc:
            print('Official endpoint unavailable: ' + type(exc).__name__, flush=True)
    if blob is None:
        raise RuntimeError('Cannot download verified protoc from official endpoints; try again with --direct or check your proxy.')
    if hashlib.sha256(blob).hexdigest() != manifest['sha256']:
        raise RuntimeError('protoc archive SHA256 verification failed; no files installed')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='protoc-setup-', dir=target.parent) as work:
        staged = Path(work)
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            for member in archive.infolist():
                if not (staged/member.filename).resolve().is_relative_to(staged.resolve()):
                    raise RuntimeError('Unsafe archive member')
            archive.extractall(staged)
        version = subprocess.run([str(staged/'bin/protoc.exe'), '--version'], capture_output=True, text=True, check=True)
        if version.stdout.strip() != expected:
            raise RuntimeError('Unexpected protoc binary version')
        shutil.copytree(staged, target, dirs_exist_ok=True)
    print(expected + ' installed: ' + str(exe))


if __name__ == '__main__':
    main()
