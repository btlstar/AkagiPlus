import unittest,tempfile,json
from pathlib import Path
from install import install,restore,digest
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.game=self.root/'Game';self.game.mkdir();(self.game/'Mahjong-JP.exe').write_bytes(b'fixture')
        self.target=self.game/'Mahjong-JP_Data/StreamingAssets/Base/lua_network';self.target.parent.mkdir(parents=True);self.target.write_bytes(b'official fixture')
        self.patch=self.root/'staged';self.patch.write_bytes(b'local fixture');self.patch.with_suffix('.manifest.json').write_text(json.dumps({'source_sha256':digest(b'official fixture'),'patched_sha256':digest(b'local fixture')}))
        self.backups=self.root/'backups';self.journal=self.root/'journal.json';self.guard=lambda:None
    def tearDown(self):self.temp.cleanup()
    def apply(self):return install(self.game,self.patch,self.backups,self.journal,guard=self.guard)
    def test_install_restore_preserve_exact_bytes(self):
        self.apply();self.assertEqual(self.target.read_bytes(),b'local fixture');restore(self.game,self.journal,guard=self.guard);self.assertEqual(self.target.read_bytes(),b'official fixture')
    def test_never_overwrite_updated_client(self):
        self.apply();self.target.write_bytes(b'new official version')
        with self.assertRaises(ValueError):restore(self.game,self.journal,guard=self.guard)
        self.assertEqual(self.target.read_bytes(),b'new official version')
    def test_never_install_stale_preparation(self):
        self.target.write_bytes(b'new official version')
        with self.assertRaises(ValueError):self.apply()
    def test_tampered_staging_rejected(self):
        self.patch.write_bytes(b'bad patch')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.target.read_bytes(),b'official fixture')
    def test_corrupt_backup_rejected(self):
        r=self.apply();Path(r['backup']).write_bytes(b'bad backup')
        with self.assertRaises(ValueError):restore(self.game,self.journal,guard=self.guard)
    def test_running_game_guard_precedes_write(self):
        def running():raise ValueError('running')
        with self.assertRaises(ValueError):install(self.game,self.patch,self.backups,self.journal,guard=running)
        self.assertEqual(self.target.read_bytes(),b'official fixture')
    def test_hot_update_prevents_install(self):
        hot=self.game/'Mahjong-JP_Data/_Data/Mahjong/Base/lua_network';hot.parent.mkdir(parents=True);hot.write_bytes(b'new hot update')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.target.read_bytes(),b'official fixture')
    def test_verified_upgrade_keeps_official_backup(self):
        first=self.apply();self.patch.write_bytes(b'local fixture v2')
        self.patch.with_suffix('.manifest.json').write_text(json.dumps({'source_sha256':first['original_sha256'],'patched_sha256':digest(b'local fixture v2')}))
        upgraded=self.apply();self.assertEqual(self.target.read_bytes(),b'local fixture v2')
        self.assertEqual(Path(upgraded['backup']).read_bytes(),b'official fixture')
        restore(self.game,self.journal,guard=self.guard);self.assertEqual(self.target.read_bytes(),b'official fixture')
    def test_upgrade_rejects_unknown_current_file(self):
        first=self.apply();self.target.write_bytes(b'unknown update')
        self.patch.write_bytes(b'local fixture v2')
        self.patch.with_suffix('.manifest.json').write_text(json.dumps({'source_sha256':first['original_sha256'],'patched_sha256':digest(b'local fixture v2')}))
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.target.read_bytes(),b'unknown update')
    def test_interrupted_upgrade_can_restore_previous_patch(self):
        first=self.apply();self.patch.write_bytes(b'local fixture v2')
        self.patch.with_suffix('.manifest.json').write_text(json.dumps({'source_sha256':first['original_sha256'],'patched_sha256':digest(b'local fixture v2')}))
        upgraded=self.apply();self.target.write_bytes(b'local fixture')
        record=json.loads(self.journal.read_text());record['phase']='prepared';self.journal.write_text(json.dumps(record))
        restore(self.game,self.journal,guard=self.guard);self.assertEqual(self.target.read_bytes(),b'official fixture')
if __name__=='__main__':unittest.main()

