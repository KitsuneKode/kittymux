import sys,unittest,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_changes import RepoCase,GIT
import kittymux_changes as C

class PatchTests(RepoCase):
    def git(self,*args):
        return subprocess.run(GIT+list(args),cwd=self.repo,check=True,capture_output=True,text=True).stdout
    def test_patch_uses_run_baseline_and_does_not_write_repository(self):
        self.write('a.txt','before\n');self.git('add','.');self.git('commit','-qm','baseline')
        self.write('a.txt','dirty before\n');C.start(self.state,123,7,self.repo)
        self.write('a.txt','agent edit\n');C.finish(self.state,123,7,self.repo)
        entry=C.load(self.state,123)['7'];before=self.git('status','--porcelain')
        result=C.patch(entry,self.state)
        self.assertIn('-dirty before',result['text']);self.assertIn('+agent edit',result['text'])
        self.assertEqual(before,self.git('status','--porcelain'))
    def test_patch_is_bounded_and_rejects_invalid_tree_arguments(self):
        self.write('large.txt','before\n');self.git('add','.');self.git('commit','-qm','baseline')
        C.start(self.state,123,7,self.repo);self.write('large.txt','line\n'*10000);C.finish(self.state,123,7,self.repo)
        result=C.patch(C.load(self.state,123)['7'],self.state,max_bytes=1024,max_lines=20)
        self.assertTrue(result['truncated']);self.assertLessEqual(len(result['text'].encode()),1024)
        self.assertIsNone(C.patch({'top':self.repo,'base_tree':'--help','current_tree':'--help'},self.state))

    def test_patch_disables_repository_diff_commands_and_handles_binary_files(self):
        import shlex
        marker = Path(self.repo, 'driver-ran')
        command = 'touch ' + shlex.quote(str(marker))
        self.git('config', 'diff.external', command)
        self.git('config', 'diff.synthetic.textconv', command)
        self.write('.gitattributes', 'a.txt diff=synthetic\n')
        self.write('a.txt', 'before\n')
        Path(self.repo, 'binary.dat').write_bytes(bytes([0, 1, 2]))
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        C.start(self.state, 123, 7, self.repo)
        self.write('a.txt', 'after\n')
        Path(self.repo, 'binary.dat').write_bytes(bytes([0, 3, 4]))
        C.finish(self.state, 123, 7, self.repo)
        git_dir = Path(self.repo, '.git')
        index = (git_dir / 'index').read_bytes()
        objects = sorted(str(p.relative_to(git_dir)) for p in (git_dir / 'objects').rglob('*'))
        result = C.patch(C.load(self.state, 123)['7'], self.state)
        self.assertIn('+after', result['text'])
        self.assertIn('Binary files', result['text'])
        self.assertFalse(marker.exists())
        self.assertEqual(index, (git_dir / 'index').read_bytes())
        self.assertEqual(objects, sorted(str(p.relative_to(git_dir)) for p in (git_dir / 'objects').rglob('*')))
