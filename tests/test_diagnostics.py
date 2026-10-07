import sys,tempfile,json,tarfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import kittymux_diagnostics as D
import kittymux_files as F

class DiagnosticsTests(unittest.TestCase):
    def test_only_allowlisted_generated_facts_reach_archive(self):
        with tempfile.TemporaryDirectory() as d:
            private='sbp_'+'x'*24
            Path(d,'scan-123.json').write_text(json.dumps({'7':{'state':'limited','title':private,'why':private,'cwd':private,'argv':[private]},'8':{'state':[]}}))
            facts=D.summary(d,'0.0.test','kitty 0.49.2 '+private,{'folder':True,'unknown':private},env={'WAYLAND_DISPLAY':private})
            path=D.bundle(d,facts)
            self.assertEqual(Path(path).stat().st_mode&0o777,0o600)
            with tarfile.open(path) as t:
                self.assertEqual(t.getnames(),['MANIFEST.txt','diagnostics.json'])
                payload=b''.join(t.extractfile(n).read() for n in t.getnames())
            self.assertNotIn(private.encode(),payload)
            self.assertEqual(facts['published_state']['states']['limited'],1)
            self.assertLess(len(payload),10000)
    def test_json_boundary_rejects_oversize_wrong_roots_and_boolean_ids(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d,'file.json');p.write_text('[]')
            self.assertEqual(F.read_json(p,{}),{})
            p.write_text('{"a":"'+'x'*100+'"}')
            self.assertEqual(F.read_json(p,{},limit=30),{})
            self.assertFalse(F.positive_id(True));self.assertFalse(F.positive_id(-1));self.assertTrue(F.positive_id(7))

    def test_cli_dispatch_creates_generated_bundle(self):
        import importlib.machinery, importlib.util
        from unittest import mock
        path=Path(__file__).resolve().parents[1]/'bin/kittymux'
        loader=importlib.machinery.SourceFileLoader('diagnostic_cli',str(path))
        spec=importlib.util.spec_from_loader('diagnostic_cli',loader)
        module=importlib.util.module_from_spec(spec);loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(module.kittymux_layout,'state_dir',return_value=d), mock.patch.object(module,'_run',return_value=(0,'kitty 0.49.2')), mock.patch('builtins.print'):
            self.assertEqual(module.main(['doctor','--bundle',d]),0)
            self.assertEqual(len(list(Path(d).glob('*.tar.gz'))),1)
