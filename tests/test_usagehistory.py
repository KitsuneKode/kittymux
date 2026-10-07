import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import kittymux_usagehistory as H
import kittymux_usageview as U

class HistoryTests(unittest.TestCase):
    def test_recording_is_numeric_only_bounded_and_hourly(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'agent-usage-trends.json')
            private='sbp_'+'x'*24
            path.write_text(json.dumps({'version':1,'samples':[{'provider':'codex','row':0,'at':3600,'pct':5,'title':private}]}))
            H.record(d,[{'name':'codex','account':private,'rows':[{'pct':63,'label':private}]}],now=7200)
            obj=json.loads(path.read_text());self.assertNotIn(private,path.read_text())
            self.assertEqual(len(obj['samples']),2)
            H.record(d,[{'name':'codex','rows':[{'pct':70}]}],now=7400)
            self.assertEqual(len(json.loads(path.read_text())['samples']),2)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertIn('codex',U.trend_lines(obj,20,now=7200))
    def test_elapsed_and_bad_numbers_are_not_quota_history(self):
        with tempfile.TemporaryDirectory() as d:
            H.record(d,[{'name':'claude','rows':[{'pct':50,'clock':True},{'pct':True},{'pct':float('nan')}]}],now=7200)
            self.assertEqual(json.loads(Path(d,'agent-usage-trends.json').read_text())['samples'],[])

    def test_first_numeric_quota_need_not_be_the_first_text_row(self):
        with tempfile.TemporaryDirectory() as d:
            providers=[{'name':'cursor','rows':[{'label':'plan','text':'Pro'},{'label':'budget','pct':30}]}]
            H.record(d,providers,now=3600);H.record(d,providers,now=7200)
            data=json.loads(Path(d,'agent-usage-trends.json').read_text())
            self.assertIn('cursor',U.trend_lines(data,12,now=7200))

if __name__=='__main__':unittest.main()
