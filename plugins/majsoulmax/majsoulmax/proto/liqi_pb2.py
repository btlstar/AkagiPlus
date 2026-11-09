"""Dynamic message classes, compatible with the Copilot pb.Message API."""
from majsoulmax.paths import PROTO
from .protocol import build_protocol


def reload_protocol():
    global pool, RPC_METHODS
    pool, classes, RPC_METHODS = build_protocol((PROTO / 'liqi.desc').read_bytes())
    globals().update(classes)


reload_protocol()
