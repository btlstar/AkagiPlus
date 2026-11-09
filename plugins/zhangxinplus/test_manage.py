"""Focused failure-path checks for the two-file recovery transaction."""
import json,tempfile,unittest
from pathlib import Path
import manage

class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.game=self.root/'game';self.game.mkdir();(self.game/'zhangxinmj.exe').touch()
        self.stage=self.root/'stage';self.stage.mkdir();self.journal=self.root/'private/install.json'
        hot=self.game/'zhangxinmj_Data/_Data/Mahjong';hot.mkdir(parents=True);(hot/'version_num.txt').write_text('92217')
        self.old=manage.BASELINE;manage.BASELINE={n:manage.digest(n.encode()) for n in ['first','second']}
        records=[]
        for n,h in manage.BASELINE.items():
            f=self.game/'zhangxinmj_Data/_Data/Mahjong'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(n.encode())
            patch=(n+'-patched').encode();(self.stage/n).write_bytes(patch)
            records.append(dict(name=n,original_sha256=h,patched_sha256=manage.digest(patch)))
        (self.stage/'manifest.json').write_text(json.dumps(dict(schema=1,bundles=records)))
    def tearDown(self):
        manage.BASELINE=self.old;self.tmp.cleanup()
    def test_interrupted_install_can_restore_both_files(self):
        calls=0
        def guard():
            nonlocal calls
            calls+=1
            if calls==3:raise ValueError('simulated interruption')
        with self.assertRaises(ValueError):manage.install(self.game,self.stage,self.journal,guard)
        manage.restore(self.game,self.journal,lambda:None)
        for n in manage.BASELINE:self.assertEqual((self.game/'zhangxinmj_Data/_Data/Mahjong'/n).read_bytes(),n.encode())
    def test_update_prevents_restore_without_overwriting_it(self):
        manage.install(self.game,self.stage,self.journal,lambda:None)
        f=self.game/'zhangxinmj_Data/_Data/Mahjong/first';f.write_bytes(b'new official update')
        with self.assertRaises(ValueError):manage.restore(self.game,self.journal,lambda:None)
        self.assertEqual(f.read_bytes(),b'new official update')
    def test_corrupt_backup_is_rejected_before_any_restore(self):
        r=manage.install(self.game,self.stage,self.journal,lambda:None)
        Path(r['files'][1]['backup']).write_bytes(b'bad backup')
        with self.assertRaises(ValueError):manage.restore(self.game,self.journal,lambda:None)
        self.assertEqual((self.game/'zhangxinmj_Data/_Data/Mahjong/first').read_bytes(),b'first-patched')
if __name__=='__main__':unittest.main()
