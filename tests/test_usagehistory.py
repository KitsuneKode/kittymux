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

class LabelTests(unittest.TestCase):
    def samples(self, d):
        return json.loads(Path(d, 'agent-usage-trends.json').read_text())['samples']

    def test_a_quota_is_followed_by_its_label_not_its_row_position(self):
        with tempfile.TemporaryDirectory() as d:
            H.record(d, [{'name': 'codex', 'rows': [{'label': '5h', 'pct': 10}, {'label': 'wk', 'pct': 60}]}], now=3600)
            # the collector now lists the weekly row first: position 0 is a different metric
            H.record(d, [{'name': 'codex', 'rows': [{'label': 'wk', 'pct': 61}, {'label': '5h', 'pct': 20}]}], now=7200)
            by = {}
            for s in self.samples(d):
                by.setdefault(s['label'], []).append(s['pct'])
            self.assertEqual(by, {'5h': [10, 20], 'wk': [60, 61]})

    def test_a_new_sample_in_the_same_hour_replaces_its_own_quota_only(self):
        with tempfile.TemporaryDirectory() as d:
            H.record(d, [{'name': 'codex', 'rows': [{'label': '5h', 'pct': 10}, {'label': 'wk', 'pct': 60}]}], now=7200)
            H.record(d, [{'name': 'codex', 'rows': [{'label': '5h', 'pct': 11}, {'label': 'wk', 'pct': 62}]}], now=7300)
            self.assertEqual(sorted((s['label'], s['pct']) for s in self.samples(d)), [('5h', 11), ('wk', 62)])

    def test_a_re_read_old_snapshot_is_recorded_at_its_own_time(self):
        with tempfile.TemporaryDirectory() as d:
            now = 20 * 3600
            H.record(d, [{'name': 'codex', 'sample_ts': now - 5 * 3600, 'rows': [{'label': '5h', 'pct': 90}]}], now=now)
            self.assertEqual([s['at'] for s in self.samples(d)], [15 * 3600])           # five hours ago, not this hour
            H.record(d, [{'name': 'codex', 'sample_ts': now - 60 * 3600, 'rows': [{'label': '5h', 'pct': 91}]}], now=now)
            self.assertEqual(len(self.samples(d)), 1)                                   # older than the 48 h kept: not recorded at all
            H.record(d, [{'name': 'codex', 'sample_ts': 'x', 'rows': [{'label': 'wk', 'pct': 5}]}], now=now)
            H.record(d, [{'name': 'codex', 'sample_ts': float('nan'), 'rows': [{'label': 'wk', 'pct': 6}]}], now=now)
            self.assertEqual(len(self.samples(d)), 1)                                   # an unreadable time records nothing rather than guessing

    def test_a_label_that_could_carry_something_is_not_stored(self):
        with tempfile.TemporaryDirectory() as d:
            private = 'sbp_' + 'x' * 24
            for label in (private, 'Account Name', 'ünï', 'x' * 7, '', None, 5, ['5h']):
                H.record(d, [{'name': 'codex', 'rows': [{'label': label, 'pct': 10}]}], now=3600)
            for s in self.samples(d):
                self.assertNotIn('label', s)
            self.assertNotIn(private[:8], Path(d, 'agent-usage-trends.json').read_text())

    def test_old_samples_without_a_label_still_draw_and_the_best_documented_quota_wins(self):
        end = 20 * 3600
        old = [{'provider': 'codex', 'row': 0, 'at': end - 3600 * h, 'pct': 10 + h} for h in (5, 4, 3, 2)]
        got = U.trend_lines({'samples': old}, 20, now=end)
        self.assertIn('codex', got)
        self.assertIn('first quota', got['codex'][1][0])
        mixed = old + [{'provider': 'codex', 'row': 1, 'label': 'wk', 'at': end - 3600 * h, 'pct': 50} for h in (30, 20, 10, 9, 8, 7, 6)]
        pick = U.trend_lines({'samples': mixed}, 20, now=end)['codex']
        self.assertIn('wk', pick[1][0])                                              # the quota with the most hours on record, named

    def test_a_hostile_label_in_the_file_is_ignored_when_drawing(self):
        bad = [{'provider': 'codex', 'row': 0, 'label': '\x1b[31m', 'at': 3600 * h, 'pct': 10} for h in (1, 2, 3)]
        got = U.trend_lines({'samples': bad}, 20, now=3 * 3600)
        self.assertTrue(all('\x1b' not in t for t, _ in got.get('codex', [])))


if __name__=='__main__':unittest.main()
