import sys,tempfile,json,unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import kittymux_usageview as U

class DashboardTests(unittest.TestCase):
    def test_meter_distinguishes_filled_from_remaining_and_keeps_reset(self):
        data={'ts':1000,'providers':[{'name':'codex','rows':[{'label':'5h','pct':63,'reset':'resets in 3h 50m'}]}]}
        lines=U.dashboard(data,32,now=1013)
        self.assertTrue(any(any(r=='track' for _,r in line.runs) and any(r=='accent' for _,r in line.runs) for line in lines))
        text='\n'.join(''.join(t for t,_ in line.runs) for line in lines)
        self.assertIn('37% left',text);self.assertIn('3h 50m',text)
        self.assertTrue(all(len(''.join(t for t,_ in l.runs))<=32 for l in lines))
    def test_missing_history_is_not_zero_and_elapsed_is_not_quota(self):
        data={'providers':[{'name':'claude','rows':[{'label':'5h','pct':50,'clock':True}]}]}
        text='\n'.join(''.join(t for t,_ in l.runs) for l in U.dashboard(data,16,now=1000))
        self.assertIn('elapsed',text);self.assertNotIn('% left',text)
        self.assertIn('No trend yet',text)
    def test_word_wrap_keeps_numeric_groups_and_controls_out(self):
        out=U.words('12 sessions · safe\x1b[31m text',16)
        self.assertTrue(any('12 sessions' in line for line in out));self.assertNotIn('\x1b',''.join(out))
    def test_recorded_daily_graph_preserves_gaps(self):
        hist={'2026-10-06':{'_daily_version':2,'claude_fresh':100},'2026-10-07':{'_daily_version':2,'claude_fresh':0}}
        lines=U.activity(hist,'claude',24,today=date(2026,10,7))
        text='\n'.join(t for t,_ in lines)
        self.assertIn('·',text);self.assertIn('100',text)
        self.assertIn('tokens',text)

    def test_large_cached_fields_have_a_bounded_render_budget(self):
        data={'providers':[{'name':'codex','rows':[{'label':'note','text':'x'*200000}]*64}]}
        result=U.dashboard(data,16,now=1000)
        self.assertLessEqual(len(result),513)
        self.assertIn('omitted',' '.join(t for line in result for t,_ in line.runs))

    def test_live_failure_and_stale_age_remain_visible_in_overview(self):
        data={'ts':10000,'live':{'claude':{'ts':1000,'rows':[{'pct':80}],'error':'offline'}},
              'providers':[{'name':'claude','rows':[{'label':'5h','pct':80}], 'live_error':'live unavailable: offline'}]}
        result=U.dashboard(data,32,now=10013)
        text=' '.join(t for line in result for t,_ in line.runs)
        self.assertIn('offline',text);self.assertIn('Live stale',text);self.assertIn('9013s',text)

if __name__=='__main__':unittest.main()
