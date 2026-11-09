# Modified for MahjongCopilotPlus on 2026-11-03; see NOTICE.md.
"""MajsoulData descriptor loader; keep lq types out of the global protobuf pool."""
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory


def build_protocol(blob):
    fds = descriptor_pb2.FileDescriptorSet.FromString(blob)
    pool = descriptor_pool.DescriptorPool()
    pending = list(fds.file)
    while pending:
        remaining = []
        for file in pending:
            try:
                pool.AddSerializedFile(file.SerializeToString())
            except (TypeError, KeyError):
                remaining.append(file)
        if len(remaining) == len(pending):
            raise ValueError('协议描述的依赖缺失或无效: ' + ', '.join(f.name for f in remaining))
        pending = remaining
    factory = message_factory.MessageFactory(pool)
    classes = {}
    methods = {}
    for file in fds.file:
        if file.package != 'lq':
            continue
        for message in file.message_type:
            descriptor = pool.FindMessageTypeByName(f'lq.{message.name}')
            if hasattr(message_factory, 'GetMessageClass'):
                classes[message.name] = message_factory.GetMessageClass(descriptor)
            else:
                classes[message.name] = factory.GetPrototype(descriptor)
        for service in file.service:
            for method in service.method:
                methods[f'.lq.{service.name}.{method.name}'] = {
                    'req': method.input_type, 'resp': method.output_type,
                }
    if 'ResLogin' not in classes or '.lq.FastTest.authGame' not in methods:
        raise ValueError('协议描述缺少雀魂登录或对局消息')
    return pool, classes, methods
