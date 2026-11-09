# SPDX-License-Identifier: GPL-3.0-only
"""AkagiPlus MajsoulMax JSONL worker. No listener, shell, game launch or AI connection."""
import base64
import hashlib
import json
import logging
import sys
from struct import unpack
from types import SimpleNamespace
from majsoulmax.paths import DATA, PROTO
from majsoulmax.wire import LiqiProto
from majsoulmax.plugin.mod import mod

MAX_LINE = 12 * 1024 * 1024

def verify_snapshot():
    manifest = json.loads((DATA / 'data_version.json').read_text(encoding='utf-8'))
    for name, path in [('max_data.yaml', DATA / 'max_data.yaml'), ('liqi.desc', PROTO / 'liqi.desc')]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256'][name]:
            raise ValueError('snapshot integrity check failed: ' + name)
    return manifest

class Worker:
    def __init__(self):
        self.manifest = verify_snapshot()
        self.plugin = mod('AkagiPlus prototype')
        self.flows = {}

    def handle(self, request):
        flow = request['flow']
        if not isinstance(flow, str) or len(flow) > 128:
            raise ValueError('invalid flow id')
        if request['op'] == 'close':
            self.flows.pop(flow, None)
            return {'closed': True}
        if request['op'] != 'frame' or type(request['from_client']) is not bool:
            raise ValueError('invalid command')
        original = base64.b64decode(request['data'], validate=True)
        unchanged = {'data': request['data'], 'drop': False, 'inject_client': []}
        if not original or original[0] not in (1, 2, 3):
            return unchanged
        if flow not in self.flows:
            if len(self.flows) >= 32:
                raise ValueError('too many flows')
            self.flows[flow] = LiqiProto()
        parser = self.flows[flow]
        # Unknown responses cannot be safely rewritten; preserve their bytes.
        if original[0] == 3 and len(original) >= 3 and unpack('<H', original[1:3])[0] not in parser.res_type:
            return unchanged
        message = SimpleNamespace(content=original, from_client=request['from_client'])
        modify, drop, content, inject, injected = self.plugin.main(message, parser)
        if modify:
            message.content = content
        if not drop:
            parser.parse(message)
        return {'data': base64.b64encode(message.content).decode('ascii'), 'drop': bool(drop),
                'inject_client': [base64.b64encode(injected).decode('ascii')] if inject else []}

def main():
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format='MajsoulMax %(levelname)s: %(message)s')
    try:
        worker = Worker()
    except Exception as exc:
        print(json.dumps({'ready': False, 'error': type(exc).__name__}), flush=True)
        return 1
    print(json.dumps({'ready': True, 'protocol': 1, 'snapshot': worker.manifest['version']}), flush=True)
    while True:
        line = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not line:
            return 0
        if len(line) > MAX_LINE:
            return 2
        try:
            result = worker.handle(json.loads(line))
        except Exception as exc:
            # Never print frames, account IDs, credentials or exception payloads.
            result = {'error': type(exc).__name__}
        print(json.dumps(result, separators=(',', ':')), flush=True)

if __name__ == '__main__':
    raise SystemExit(main())
