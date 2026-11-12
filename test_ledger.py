import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import ledger
from propose import prompt

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); (self.root/'a.txt').write_text('old\n')
    def plan(self,name='a.txt',content='new\n',sha='auto'):
        return {'version':1,'changes':[{'path':name,'content':content,'expected_sha256':ledger.digest(ledger.read(self.root/name)) if sha=='auto' else sha}]}
    def test_preview_no_write(self):
        self.assertIn('+new',ledger.preview(self.root,self.plan())); self.assertEqual((self.root/'a.txt').read_text(),'old\n'); self.assertFalse((self.root/'.ledger').exists())
    def test_apply_undo(self):
        j=ledger.apply(self.root,self.plan()); self.assertEqual((self.root/'a.txt').read_text(),'new\n'); ledger.undo(self.root,j); self.assertEqual((self.root/'a.txt').read_text(),'old\n')
    def test_create_undo(self):
        j=ledger.apply(self.root,self.plan('dir/b.txt')); ledger.undo(self.root,j); self.assertFalse((self.root/'dir/b.txt').exists())
    def test_delete_undo(self):
        j=ledger.apply(self.root,self.plan(content=None)); self.assertFalse((self.root/'a.txt').exists()); ledger.undo(self.root,j); self.assertEqual((self.root/'a.txt').read_text(),'old\n')
    def test_stale(self):
        with self.assertRaises(ledger.Conflict): ledger.apply(self.root,self.plan(sha='bad'))
    def test_undo_human_edit(self):
        j=ledger.apply(self.root,self.plan()); (self.root/'a.txt').write_text('human')
        with self.assertRaises(ledger.Conflict): ledger.undo(self.root,j)
        self.assertEqual((self.root/'a.txt').read_text(),'human')
    def test_paths(self):
        for name in ['../escape','/tmp/escape','.ledger/secret']:
            with self.subTest(name=name), self.assertRaises(ledger.Conflict): ledger.inspect(self.root,self.plan(name,sha=None))
    def test_symlink(self):
        (self.root/'link').symlink_to(self.root/'a.txt')
        with self.assertRaises(ledger.Conflict): ledger.inspect(self.root,self.plan('link'))
    def test_symlink_directory(self):
        (self.root/'link').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ledger.Conflict): ledger.inspect(self.root,self.plan('link/a.txt'))
    def test_journal_symlink(self):
        (self.root/'.ledger').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ledger.Conflict): ledger.apply(self.root,self.plan())
    def test_duplicate(self):
        p=self.plan(); p['changes']*=2
        with self.assertRaises(ledger.Conflict): ledger.inspect(self.root,p)
    def test_missing_content(self):
        p=self.plan(); del p['changes'][0]['content']
        with self.assertRaises(ledger.Conflict): ledger.inspect(self.root,p)
    def test_bad_version(self):
        p=self.plan(); p['version']=2
        with self.assertRaises(ledger.Conflict): ledger.inspect(self.root,p)
    def test_large(self):
        with self.assertRaises(ledger.Conflict): ledger.inspect(self.root,self.plan(content='a'*1000001))
    def test_binary(self):
        (self.root/'a.txt').write_bytes(b'\xff')
        with self.assertRaises(ledger.Conflict): ledger.inspect(self.root,self.plan())
    def test_lock(self):
        (self.root/'.ledger').mkdir(); (self.root/'.ledger/lock').touch()
        with self.assertRaises(ledger.Conflict): ledger.apply(self.root,self.plan())
    def test_batch_preflight(self):
        p=self.plan(); p['changes']+=self.plan('b.txt',sha='bad')['changes']
        with self.assertRaises(ledger.Conflict): ledger.apply(self.root,p)
        self.assertEqual((self.root/'a.txt').read_text(),'old\n')
    def test_rollback_on_failure(self):
        p=self.plan(); p['changes']+=self.plan('b.txt')['changes']; orig=ledger.atomic
        def fault(path,content):
            if path.name=='b.txt': raise OSError('simulated disk failure')
            return orig(path,content)
        with patch('ledger.atomic',side_effect=fault), self.assertRaises(OSError): ledger.apply(self.root,p)
        self.assertEqual((self.root/'a.txt').read_text(),'old\n')
    def test_prompt_explicit_files(self):
        (self.root/'private.txt').write_text('not included')
        text=prompt(self.root,['a.txt'],'Rewrite')
        self.assertNotIn('not included',text); self.assertIn(ledger.digest(b'old\n'),text)
    def test_foreign_journal(self):
        with self.assertRaises(ledger.Conflict): ledger.undo(self.root,self.root/'outside.json')
    def test_double_undo(self):
        j=ledger.apply(self.root,self.plan()); ledger.undo(self.root,j)
        with self.assertRaises(ledger.Conflict): ledger.undo(self.root,j)

if __name__=='__main__': unittest.main()
