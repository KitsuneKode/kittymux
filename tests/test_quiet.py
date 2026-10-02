import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import kittymux_quiet as Q  # noqa: E402

NOW = 1_000_000.0


class MuteTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_mute_roundtrip_is_private_and_expires(self):
        until = Q.set_mute(self.d, 3600, NOW)
        self.assertEqual(until, NOW + 3600)
        self.assertEqual(stat.S_IMODE(os.stat(Q.mute_path(self.d)).st_mode), 0o600)
        self.assertEqual(Q.mute_until(self.d, NOW + 10), until)
        self.assertIsNone(Q.mute_until(self.d, NOW + 3601))                       # over
        Q.clear_mute(self.d)
        self.assertIsNone(Q.mute_until(self.d, NOW))
        Q.clear_mute(self.d)                                                       # clearing twice is fine

    def test_a_span_is_capped_and_garbage_or_absurd_values_never_silence_anything(self):
        self.assertEqual(Q.set_mute(self.d, 10 ** 9, NOW), NOW + Q.MAX_SPAN_S)
        for bad in ("tomorrow", "", "nan", "inf", str(NOW + 10 ** 12), str(NOW - 5), "-1"):
            with open(Q.mute_path(self.d), "w") as f:
                f.write(bad)
            self.assertIsNone(Q.mute_until(self.d, NOW), bad)


class SnoozeTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_a_snooze_is_per_window_and_per_kitty_and_can_be_cleared(self):
        Q.set_snooze(self.d, 100, 7, 600, NOW)
        Q.set_snooze(self.d, 100, 8, 60, NOW)
        self.assertEqual(set(Q.load_snoozes(self.d, 100, NOW)), {"7", "8"})
        self.assertEqual(Q.load_snoozes(self.d, 101, NOW), {})                     # another kitty's windows are another file
        self.assertEqual(set(Q.load_snoozes(self.d, 100, NOW + 100)), {"7"})       # 8 ran out
        Q.clear_snooze(self.d, 100, 7, NOW)
        self.assertEqual(Q.load_snoozes(self.d, 100, NOW), {"8": NOW + 60})
        self.assertEqual(stat.S_IMODE(os.stat(Q.snooze_path(self.d, 100)).st_mode), 0o600)

    def test_a_forged_or_corrupt_file_cannot_snooze_forever(self):
        with open(Q.snooze_path(self.d, 100), "w") as f:
            json.dump({"7": NOW + 10 ** 12, "x": NOW + 60, "8": "never", "9": NOW + 60}, f)
        self.assertEqual(set(Q.load_snoozes(self.d, 100, NOW)), {"9"})            # absurd end, non-numeric id and non-number are dropped
        for junk in ("{broken", "[]", "null", "5"):
            with open(Q.snooze_path(self.d, 100), "w") as f:
                f.write(junk)
            self.assertEqual(Q.load_snoozes(self.d, 100, NOW), {}, junk)

    def test_quiet_reason_is_static_text_for_mute_and_snooze(self):
        self.assertIsNone(Q.quiet_reason(self.d, 100, 7, NOW))
        Q.set_snooze(self.d, 100, 7, 600, NOW)
        self.assertTrue(Q.quiet_reason(self.d, 100, 7, NOW).startswith("suppressed: this window is snoozed"))
        self.assertIsNone(Q.quiet_reason(self.d, 100, 8, NOW))
        Q.set_mute(self.d, 600, NOW)
        self.assertTrue(Q.quiet_reason(self.d, 100, 8, NOW).startswith("suppressed: muted"))
        for t in (NOW, NOW + 5):
            self.assertEqual(Q.quiet_reason(self.d, 100, 8, t), Q.quiet_reason(self.d, 100, 8, NOW))      # the reason never carries a clock

    def test_a_program_in_the_window_cannot_snooze_itself_through_its_own_user_variable(self):
        class W:                        # what kitty shows for a window whose program ran `printf '\\e]1337;SetUserVar=kittymux_snooze_until=...'`
            id = 7
            user_vars = {"kittymux_snooze_until": str(NOW + 600)}
        self.assertIsNone(Q.quiet_reason(self.d, 100, W.id, NOW))


if __name__ == "__main__":
    unittest.main()
