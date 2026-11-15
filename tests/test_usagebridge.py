import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
try:
    import kittymux_usagebridge as B
except ImportError:
    B = None


class UsageBridgeTests(unittest.TestCase):
    def test_retained_local_provider_keeps_its_cache_age_and_live_map(self):
        local = {'ts': 100000 - 86400, 'providers': [{'name': 'claude', 'rows': [{'pct': 30}]}],
                 'live': {'claude': {'error': 'unavailable', 'ts': 99900}}}
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'rice' / 'usage-t3.json'
            cache.parent.mkdir()
            cache.write_text(json.dumps(self.sample()))
            result = B.shared(Path(tmp) / 'kittymux', local, now=100000)
        self.assertEqual(result['live'], local['live'])
        provider = next(p for p in result['providers'] if p['name'] == 'claude')
        self.assertEqual(provider['cache_ts'], local['ts'])
        self.assertNotIn('cache_ts', local['providers'][0])
    def sample(self):
        return {'cachedAt': 100000000, 'providers': [{'driver': 'codex', 'label': 'Codex', 'accounts': [
            {'name': 'Personal', 'email': 'never-display@example.invalid', 'checkedAt': 100000000, 'windows': [
                {'id': 'session', 'label': '5 hour', 'used': 30, 'resetsAt': 109000000, 'durationMins': 300}]},
            {'name': 'Work', 'windows': [{'id': 'session', 'label': '5 hour', 'used': 100, 'resetsAt': 109000000, 'durationMins': 300}]}]}]}

    def test_account_percentages_and_reset_units_are_preserved_without_personal_fields(self):
        self.assertIsNotNone(B, 'shared usage adapter is missing')
        result = B.adapt(self.sample(), now=100000)
        p = result['providers'][0]
        self.assertEqual([a['label'] for a in p['accounts']], ['Personal', 'Work'])
        self.assertEqual([a['rows'][0]['pct'] for a in p['accounts']], [30, 100])
        self.assertEqual(p['accounts'][0]['rows'][0]['rem_s'], 9000)
        self.assertEqual(p['accounts'][0]['rows'][0]['window_s'], 18000)
        self.assertNotIn('email', repr(result))
        self.assertEqual(result['source'], 't3-cached')

    def test_expired_or_unknown_quota_is_not_presented_as_fresh_capacity(self):
        self.assertIsNotNone(B, 'shared usage adapter is missing')
        sample = self.sample()
        sample['providers'][0]['accounts'][0]['windows'][0]['resetsAt'] = 99000000
        sample['providers'][0]['accounts'][1]['windows'][0]['used'] = None
        rows = B.adapt(sample, now=100000)['providers'][0]['rows']
        self.assertTrue(all('pct' not in r for r in rows))
        self.assertIn('awaiting', rows[0]['text'])
        self.assertIn('unknown', rows[1]['text'])

    def test_missing_stale_or_invalid_shared_cache_keeps_the_local_data(self):
        self.assertIsNotNone(B, 'shared usage adapter is missing')
        local = {'providers': [{'name': 'claude', 'rows': []}]}
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'kittymux'
            self.assertEqual(B.shared(state, local, now=100000), local)

            cache = Path(tmp) / 'rice' / 'usage-t3.json'
            cache.parent.mkdir()
            cache.write_text(json.dumps(self.sample()))
            self.assertEqual(B.shared(state, local, now=100000)['providers'][0]['name'], 'codex')
            self.assertEqual(B.shared(state, local, now=100000 + 8 * 86400), local)
            cache.write_text('{broken')
            self.assertEqual(B.shared(state, local, now=100000), local)

    def test_missing_or_future_account_sample_is_not_replaced_with_cache_time(self):
        for stamp in (None, 101000000):
            sample = self.sample()
            sample['providers'][0]['accounts'][0]['checkedAt'] = stamp
            provider = B.adapt(sample, now=100000)['providers'][0]
            self.assertIsNone(provider['sample_ts'])
            self.assertTrue(provider['sample_age_unknown'])
