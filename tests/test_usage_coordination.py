"""Concurrent CLI/HUD collection and publication, with isolated fake sources."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('usage_coordination',ROOT/'bin/mux-usage.py')
usage=importlib.util.module_from_spec(spec)
with patch.dict(os.environ,KITTYMUX_HOME=str(ROOT),KITTY_LISTEN_ON=''):
    spec.loader.exec_module(usage)


class Coordination(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.addCleanup(self.tmp.cleanup)
        state=Path(self.tmp.name)
        for key,value in [('STATE_DIR',state),('CACHE',state/'cache.json'),('HIST',state/'history.json')]:
            p=patch.object(usage.C,key,value);p.start();self.addCleanup(p.stop)

    def test_independent_processes_share_local_source_ownership(self):
        state=usage.C.STATE_DIR
        script='''
import importlib.util,json,os,sys,time
from pathlib import Path
root,state,started=Path(sys.argv[1]),Path(sys.argv[2]),float(sys.argv[3])
os.environ['KITTYMUX_HOME']=str(root)
os.environ['KITTYMUX_STATE']=str(state)
os.environ.pop('KITTY_LISTEN_ON',None)
spec=importlib.util.spec_from_file_location('worker_usage',root/'bin/mux-usage.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
(state/('ready-'+str(os.getpid()))).touch()
def source():
    with (state/'calls').open('a') as f:f.write('collect\\n')
    deadline=time.monotonic()+4
    while not (state/'release').exists():
        if time.monotonic()>deadline:raise RuntimeError('test release timed out')
        time.sleep(.005)
    return {'name':'example','rows':[{'label':'wk','pct':42}]}
print(json.dumps(u._collect_local('example',source,started)))
'''
        started=time.time()
        workers=[subprocess.Popen([sys.executable,'-c',script,str(ROOT),str(state),str(started)],
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(3)]
        try:
            deadline=time.monotonic()+4
            while len(list(state.glob('ready-*')))<3:
                self.assertLess(time.monotonic(),deadline)
                time.sleep(.005)
            (state/'release').touch()
            results=[]
            for worker in workers:
                out,err=worker.communicate(timeout=5)
                self.assertEqual(worker.returncode,0,err)
                results.append(json.loads(out))
            self.assertEqual((state/'calls').read_text().splitlines(),['collect'])
            self.assertTrue(all(r==results[0] for r in results))
        finally:
            for worker in workers:
                if worker.poll() is None:worker.kill()
                worker.communicate()

    def test_overlapping_local_calls_collect_once(self):
        entered,release,second=threading.Event(),threading.Event(),threading.Event()
        calls=[];results=[]
        def source():
            calls.append(1);entered.set();self.assertTrue(release.wait(2))
            return {'name':'example','rows':[{'label':'wk','pct':40}]}
        start=time.time()
        first=threading.Thread(target=lambda:results.append(usage._collect_local('example',source,start)))
        first.start();self.assertTrue(entered.wait(1))
        def other():
            second.set();results.append(usage._collect_local('example',source,start))
        other_thread=threading.Thread(target=other);other_thread.start();self.assertTrue(second.wait(1))
        release.set();first.join(2);other_thread.join(2)
        self.assertFalse(first.is_alive() or other_thread.is_alive())
        self.assertEqual(len(calls),1)
        self.assertEqual(results[0],results[1])

    def test_sequential_forced_calls_can_collect_new_values(self):
        calls=[]
        def source():
            calls.append(1);return {'name':'example','rows':[]}
        usage._collect_local('example',source,time.time())
        usage._collect_local('example',source,time.time())
        self.assertEqual(len(calls),2)

    def test_concurrent_live_call_reuses_last_success_or_failed_attempt(self):
        entered,release=threading.Event(),threading.Event()
        calls=[];results=[]
        def source(cached):
            calls.append(1);entered.set();self.assertTrue(release.wait(2))
            return usage.C.live_failure(cached,'temporary failure')
        threads=[threading.Thread(target=lambda:results.append(usage._fetch_live(source,{},'example'))) for _ in range(2)]
        threads[0].start();self.assertTrue(entered.wait(1));threads[1].start();release.set()
        for thread in threads:thread.join(2)
        self.assertEqual(len(calls),1)
        self.assertEqual(results[0],results[1])

    def test_old_publication_cannot_replace_new_provider_or_live_rows(self):
        newer={'ts':300,'providers':[{'name':'example','collected_at':300,'rows':[{'label':'local','text':'new'}]}],
               'live':{'example':{'ts':290,'attempt_ts':290,'rows':[{'label':'wk','pct':80}]}}}
        older={'ts':200,'providers':[{'name':'example','collected_at':200,'rows':[{'label':'local','text':'old'}]}],
               'live':{'example':{'ts':190,'attempt_ts':190,'rows':[{'label':'wk','pct':20}]}}}
        with patch.object(usage,'_record_history'):
            usage._publish(copy.deepcopy(newer));result=usage._publish(copy.deepcopy(older))
        rows=result['providers'][0]['rows']
        self.assertIn({'label':'local','text':'new'},rows)
        self.assertEqual([r['pct'] for r in rows if r['label']=='wk'],[80])
        self.assertEqual(result['ts'],300)
        self.assertEqual(json.loads(usage.C.CACHE.read_text())['live']['example']['ts'],290)

    def test_local_only_writer_preserves_latest_live_data_without_duplicates(self):
        initial={'ts':100,'providers':[{'name':'example','collected_at':100,'rows':[]}],
                 'live':{'example':{'ts':100,'attempt_ts':100,'rows':[{'label':'wk','pct':10}]}}}
        fresh={'ts':200,'providers':[{'name':'example','collected_at':200,'rows':[{'label':'local','text':'updated'}]}],'live':{}}
        with patch.object(usage,'_record_history'):
            usage._publish(initial)
            result=usage._publish(fresh)
            result=usage._publish(copy.deepcopy(result))
        self.assertEqual(len([r for r in result['providers'][0]['rows'] if r['label']=='wk']),1)
        self.assertEqual(result['live']['example']['rows'][0]['pct'],10)

    def test_live_opt_out_keeps_fresh_local_rows_and_clears_live_overlay(self):
        old={'ts':100,'providers':[{'name':'example','collected_at':100,'rows':[]}],
             'live':{'example':{'ts':100,'attempt_ts':100,'rows':[{'label':'wk','pct':97}]}}}
        new={'ts':200,'providers':[{'name':'example','collected_at':200,'rows':[{'label':'5h','pct':10}]}],'live':{}}
        with patch.object(usage,'_record_history'):
            usage._publish(old)
            result=usage._publish(new,live_enabled=False)
        self.assertEqual(result['live'],{})
        self.assertEqual(result['providers'][0]['rows'],[{'label':'5h','pct':10}])

    def test_malformed_old_live_entry_does_not_crash_publication(self):
        usage.C.CACHE.write_text(json.dumps({'ts':1,'live':{'example':None},'providers':[]}))
        with patch.object(usage,'_record_history'):
            result=usage._publish({'ts':2,'live':{},'providers':[]})
        self.assertEqual(result['live'],{})

    def test_foreign_local_holder_has_bounded_wait_and_cached_fallback(self):
        memo=usage.C.usage_memo('local','example')
        provider={'name':'example','rows':[{'label':'wk','pct':17}],'collected_at':1}
        usage.C.write_private(memo,json.dumps({'collected_at':1,'provider':provider}))
        real_lock=usage.C.usage_lock
        result=[]
        def worker():
            with patch.object(usage.C,'usage_lock',lambda kind,name:real_lock(kind,name,timeout=.05)):
                result.append(usage._collect_local('example',lambda:self.fail('must not duplicate hung source'),time.time()))
        with real_lock('local','example'):
            thread=threading.Thread(target=worker);start=time.monotonic();thread.start();thread.join(1)
            self.assertFalse(thread.is_alive(),'wait must be bounded')
            self.assertLess(time.monotonic()-start,.5)
        self.assertEqual(result,[provider])

    def test_live_lock_timeout_does_not_invent_a_new_attempt(self):
        real_lock=usage.C.usage_lock
        old={'ts':1,'attempt_ts':1,'rows':[{'label':'wk','pct':18}]}
        result=[]
        def worker():
            with patch.object(usage.C,'usage_lock',lambda kind,name:real_lock(kind,name,timeout=.05)):
                result.append(usage._fetch_live(lambda c:self.fail('must not issue another request'),old,'example'))
        with real_lock('live','example'):
            thread=threading.Thread(target=worker);thread.start();thread.join(1)
            self.assertFalse(thread.is_alive(),'wait must be bounded')
        self.assertEqual(result,[old])

    def test_collector_timeout_is_not_misreported_as_an_owned_lock(self):
        def source():raise TimeoutError('source timed out')
        with self.assertRaises(TimeoutError):
            usage._collect_local('example',source,time.time())

    def test_lock_io_failures_keep_cached_local_and_live_samples(self):
        provider={'name':'example','rows':[{'label':'wk','pct':17}],'collected_at':1}
        live={'ts':1,'attempt_ts':1,'rows':[{'label':'wk','pct':18}]}
        usage.C.write_private(usage.C.usage_memo('local','example'),
                              json.dumps({'collected_at':1,'provider':provider}))
        usage.C.write_private(usage.C.usage_memo('live','example'),json.dumps(live))
        for target in ('pathlib.Path.mkdir','os.open','fcntl.flock'):
            with self.subTest(target=target),patch(target,side_effect=PermissionError('unavailable')):
                self.assertEqual(usage._collect_local('example',
                    lambda:self.fail('must not collect without ownership'),time.time()),provider)
                self.assertEqual(usage._fetch_live(
                    lambda cached:self.fail('must not request without ownership'),{},'example'),live)

    def test_local_collector_oserror_is_not_reported_as_lock_contention(self):
        def source():raise OSError('source read failed')
        with self.assertRaisesRegex(OSError,'source read failed'):
            usage._collect_local('example',source,time.time())

    def test_live_collector_oserror_remains_a_collector_error(self):
        def source(cached):raise OSError('source read failed')
        result=usage._fetch_live(source,{'ts':1,'rows':[]},'example')
        self.assertEqual(result['error'],'collector error (OSError)')
        self.assertGreater(result['attempt_ts'],1)

    def test_hud_retries_busy_publication_without_waiting_on_ui_thread(self):
        loader=usage.Loader([])
        data={'ts':0,'providers':[{'name':'example','rows':[],'pending':True}],'live':{}}
        loader.q.put(('local','example',{'name':'example','rows':[],'collected_at':time.time()}))
        with usage.C.usage_lock('publish'),patch.object(usage,'_record_history'):
            started=time.monotonic();usage._drain(loader,data)
            self.assertLess(time.monotonic()-started,.1)
            self.assertTrue(loader.publish_pending)
        with patch.object(usage,'_record_history'):
            usage._drain(loader,data)
        self.assertFalse(loader.publish_pending)
        self.assertTrue(usage.C.CACHE.exists())


if __name__=='__main__':unittest.main()
