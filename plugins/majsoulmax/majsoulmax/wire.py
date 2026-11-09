# SPDX-License-Identifier: Apache-2.0
"""Only correlate RPCs. Gameplay parsing belongs to Akagi's original bridge."""
from enum import IntEnum
from struct import unpack
from majsoulmax.proto import basic_pb2, liqi_pb2 as pb

class MsgType(IntEnum):
    NOTIFY = 1
    REQ = 2
    RES = 3

class LiqiProto:
    def __init__(self):
        self.res_type = {}

    def parse(self, message):
        buf = message.content
        if buf[0] == MsgType.NOTIFY:
            return
        msg_id = unpack('<H', buf[1:3])[0]
        if buf[0] == MsgType.REQ:
            envelope = basic_pb2.BaseMessage.FromString(buf[3:])
            method = pb.RPC_METHODS.get(envelope.method_name)
            if method:
                if len(self.res_type) >= 2048:
                    raise ValueError('too many pending RPCs')
                cls = getattr(pb, method['resp'].rsplit('.', 1)[-1])
                self.res_type[msg_id] = (envelope.method_name, cls)
        elif buf[0] == MsgType.RES:
            self.res_type.pop(msg_id, None)
