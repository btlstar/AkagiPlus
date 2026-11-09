"""Known LZ4 vectors and a synthetic prefixed UnityFS container; no game assets."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inspect_zhangxin',ROOT/'scripts/inspect-zhangxin.py')
inspector=importlib.util.module_from_spec(spec);spec.loader.exec_module(inspector)
class InspectorTests(unittest.TestCase):
    def test_literal_and_overlapping_match(self):
        self.assertEqual(inspector.lz4_block(b'\x50hello',5),b'hello')
        self.assertEqual(inspector.lz4_block(b'\x14A\x01\x00',9),b'A'*9)
    def test_invalid_distance_and_size_are_rejected(self):
        for data,size in [(b'\x00\x00\x00',4),(b'\x50hello',4)]:
            with self.assertRaises(ValueError):inspector.lz4_block(data,size)
    def test_prefixed_bundle_is_read_without_modification(self):
        body=b'assets/fixture/skin.lua.bytes\0'
        info=bytes(16)+struct.pack('>I',1)+struct.pack('>IIH',len(body),len(body),0)+struct.pack('>I',0)
        fixed=b'UnityFS\0'+struct.pack('>I',8)+b'5.x.x\0'+b'2021.3.33f1\0'
        header_size=len(fixed)+20
        info_start=(header_size+15)//16*16
        body_start=(info_start+len(info)+15)//16*16
        header=fixed+struct.pack('>QIII',body_start+len(body),len(info),len(info),0x240)
        bundle=b'X'*28+header+bytes(info_start-len(header))+info+bytes(body_start-info_start-len(info))+body
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture';path.write_bytes(bundle)
            result=inspector.inspect_bundle(path)
            self.assertEqual(result['prefix_bytes'],28)
            self.assertEqual(result['paths'],['assets/fixture/skin.lua.bytes'])
            self.assertEqual(path.read_bytes(),bundle)
if __name__=='__main__':unittest.main()
