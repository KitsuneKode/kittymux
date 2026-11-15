"""Pixel Usage/Inbox contracts; GUI dependencies remain optional."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))
try:
    import kittymux_deckpx as dp
except (ImportError, ValueError):
    dp = None
if dp is not None:
    import kittymux_panelpx as px
import kittymux_theme as th


@unittest.skipIf(dp is None, 'cairo/Pango/rsvg not installed')
class PanelTests(unittest.TestCase):
    def setUp(self):
        self.pal = th.from_colors({})
        self.now = 100000.0

    def provider(self, **extra):
        return dict({'name': 'codex', 'note': 'plus', 'rows': [
            {'label': '5h', 'pct': 30, 'rem_s': 9000, 'window_s': 18000}]}, **extra)

    def event(self, id='calm-otter', **extra):
        return dict({'id': id, 'agent': 'codex', 'tab': 'project', 'kind': 'error',
                     'title': 'Build failed', 'body': 'The compiler reported an invalid import.',
                     'status': 'unread', 'severity': 'error', 't': self.now - 80}, **extra)

    def capture(self, function, *args, **kwargs):
        drawn = []
        original = dp.Painter.layout
        def layout(painter, text, *a, **kw):
            drawn.append(text)
            return original(painter, text, *a, **kw)
        with patch.object(dp.Painter, 'layout', layout):
            result = function(*args, **kwargs)
        return result, '\n'.join(drawn)

    def assert_hits(self, result, width, height):
        for kind, value, x, y, w, h in result.hits:
            self.assertIn(kind, ('provider', 'filter', 'select', 'expand', 'jump', 'dismiss', 'key'))
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)
            self.assertLessEqual(x + w, width + .01)
            self.assertLessEqual(y + h, height + .01)
        for i, a in enumerate(result.hits):
            for b in result.hits[i + 1:]:
                overlap = (min(a[2] + a[4], b[2] + b[4]) - max(a[2], b[2]) > .01 and
                           min(a[3] + a[5], b[3] + b[5]) - max(a[3], b[3]) > .01)
                self.assertFalse(overlap, (a, b))

    def test_quota_is_remaining_with_reset_and_pace(self):
        result, text = self.capture(px.usage, {'providers': [self.provider()], 'ts': self.now}, {}, 0,
                                    self.pal, 260, 600, now=self.now)
        self.assertIn('70%', text)
        self.assertIn('remaining', text)
        self.assertIn('resets', text)
        self.assertIn('pace', text.lower())
        self.assertNotIn('30% remaining', text)
        self.assertIsNotNone(result.selected_bounds)
        self.assert_hits(result, 260, 600)

    def test_multiple_accounts_keep_separate_quota_segments_and_partial_exhaustion(self):
        provider = self.provider(accounts=[
            {'label': 'Personal', 'rows': [{'label': '5h', 'pct': 30}]},
            {'label': 'Work', 'rows': [{'label': '5h', 'pct': 100}]}])
        _, text = self.capture(px.usage, {'providers': [provider]}, {}, 0, self.pal, 260, 600, now=self.now)
        for expected in ('Personal', 'Work', '70%', '0%', '1 of 2 accounts out'):
            self.assertIn(expected, text)
        self.assertNotIn('100% remaining', text)

    def test_counters_unknown_and_clock_are_not_quotas(self):
        provider = self.provider(rows=[{'label': 'today', 'text': '42000 tok', 'tok': 42000},
                                       {'label': 'window', 'pct': 40, 'clock': True}])
        _, text = self.capture(px.usage, {'providers': [provider]}, {}, 0, self.pal, 260, 600, now=self.now)
        self.assertIn('42k', text)
        self.assertIn('tok', text)
        self.assertNotIn('remaining', text)
        self.assertIn('of window', text)
        self.assertIn('age unknown', text)

    def test_freshness_errors_and_details_are_explicit(self):
        p = self.provider(sample_ts=self.now - 7200, live_error='network unavailable', note='Local session totals')
        _, text = self.capture(px.usage, {'providers': [p], 'ts': self.now - 600}, {}, 0,
                               self.pal, 260, 800, now=self.now, details=True)
        self.assertIn('stale', text.lower())
        self.assertIn('sample', text.lower())
        self.assertIn('network unavailable', text)
        self.assertIn('Local session totals', text)
        _, text = self.capture(px.usage, {'providers': [self.provider(err='collector failed')]}, {}, 0,
                               self.pal, 260, 600, now=self.now)
        self.assertIn('collector failed', text)
        self.assertNotIn('remaining', text)

    def test_unknown_account_sample_age_is_not_presented_as_a_fresh_sample(self):
        provider = self.provider(sample_age_unknown=True)
        _, text = self.capture(px.usage, {'providers': [provider], 'ts': self.now}, {}, 0,
                               self.pal, 260, 600, now=self.now)
        self.assertIn('sample age unknown', text)
        self.assertNotIn('sample just now', text)

    def test_expansion_shows_error_body_and_id_actions_without_mutation(self):
        events = [self.event()]
        before = repr(events)
        result, text = self.capture(px.inbox, events, 'all', 'calm-otter', self.pal, 260, 600,
                                   now=self.now, expanded='calm-otter', undo=True)
        self.assertIn('The compiler reported an invalid import.', text)
        self.assertIn('Undo', text)
        self.assertEqual(repr(events), before)
        for kind in ('select', 'expand', 'jump', 'dismiss'):
            self.assertIn((kind, 'calm-otter'), [(h[0], h[1]) for h in result.hits])
        self.assert_hits(result, 260, 600)

    def test_undo_uses_the_existing_inbox_undo_key_not_usage_navigation(self):
        result = px.inbox([self.event()], 'all', 'calm-otter', self.pal, 260, 600, undo=True)
        self.assertIn(('key', 'Z'), [(h[0], h[1]) for h in result.hits])
        self.assertNotIn(('key', 'U'), [(h[0], h[1]) for h in result.hits])

    def test_long_unbroken_body_scrolls_and_actions_remain_reachable(self):
        events = [self.event(body='longword' * 100)]
        first = px.inbox(events, 'all', 'calm-otter', self.pal, 260, 230, expanded='calm-otter', now=self.now)
        last = px.inbox(events, 'all', 'calm-otter', self.pal, 260, 230, expanded='calm-otter', now=self.now, scroll=100000)
        self.assertGreater(first.content_height, 230)
        self.assertEqual(first.selected_bounds, last.selected_bounds)
        self.assertNotIn('jump', [h[0] for h in first.hits])
        self.assertIn('jump', [h[0] for h in last.hits])
        self.assertIn('dismiss', [h[0] for h in last.hits])
        self.assert_hits(first, 260, 230)
        self.assert_hits(last, 260, 230)

    def test_collapsed_filter_and_identity(self):
        events = [self.event('old', t=self.now - 500), self.event('new', t=self.now)]
        result = px.inbox(events, 'all', 'old', self.pal, 260, 600, now=self.now)
        self.assertNotIn('jump', [h[0] for h in result.hits])
        self.assertEqual([h[1] for h in result.hits if h[0] == 'filter'], ['all', 'needs', 'done', 'limits'])
        self.assertGreater(result.selected_bounds[0], 0)
        empty, text = self.capture(px.inbox, events, 'limits', 'old', self.pal, 260, 600, now=self.now)
        self.assertIn('All clear', text)
        self.assertIsNone(empty.selected_bounds)

    def test_dark_light_narrow_wide_empty_and_bounded_resources(self):
        resources = dp.Resources(limit=16)
        for width in (90, 260, 380):
            for bg, fg in ((0x101014, 0xeeeeee), (0xf3f1ed, 0x18181b)):
                pal = th.from_colors({'background': bg, 'foreground': fg})
                for result in (px.usage({}, {}, 0, pal, width, 180, now=self.now, resources=resources),
                               px.usage({'providers': [self.provider()] * 18}, {}, 17, pal, width, 180, resources=resources),
                               px.inbox([], 'all', None, pal, width, 180, resources=resources),
                               px.inbox([self.event()], 'all', 'calm-otter', pal, width, 180, expanded='calm-otter', resources=resources)):
                    self.assertEqual((result.surface.get_width(), result.surface.get_height()), (width, 180))
                    self.assert_hits(result, width, 180)
        self.assertLessEqual(len(resources.layouts), 16)

    def test_untrusted_strings_are_cleaned_before_pango(self):
        dirty = 'Unsafe\x1b\x00\r\nvalue'
        _, text = self.capture(px.inbox, [self.event(agent=dirty, tab=dirty, title=dirty, body=dirty)],
                               'all', 'calm-otter', self.pal, 260, 600, expanded='calm-otter')
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\x00', text)
        _, text = self.capture(px.usage, {'providers': [self.provider(name=dirty, note=dirty, live_error=dirty)]},
                               {}, 0, self.pal, 260, 600, details=True)
        self.assertNotIn('\x1b', text)
        self.assertNotIn('\x00', text)


if __name__ == '__main__':
    unittest.main()
