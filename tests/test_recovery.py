from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.recovery import CrashRecovery


class CrashRecoveryTests(unittest.TestCase):
    def recovery(self, root: Path, now: list[float]) -> CrashRecovery:
        return CrashRecovery(
            root / "session_recovery.json",
            root / "logs" / "crashes",
            version="0.2.0",
            clock=lambda: now[0],
        )

    def test_clean_exit_resets_crash_streak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [100.0]
            recovery = self.recovery(root, now)

            status = recovery.begin()
            now[0] = 115.0
            recovery.heartbeat()
            recovery.finish()

            marker = json.loads((root / "session_recovery.json").read_text(encoding="utf-8"))
            self.assertFalse(status.unclean_exit)
            self.assertFalse(marker["active"])
            self.assertEqual(marker["last_heartbeat"], 115.0)
            self.assertEqual(marker["consecutive_crashes"], 0)

    def test_two_consecutive_unclean_sessions_enable_safe_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [100.0]
            first = self.recovery(root, now)
            first.begin()

            now[0] = 200.0
            second = self.recovery(root, now)
            second_status = second.begin()

            now[0] = 300.0
            third = self.recovery(root, now)
            third_status = third.begin()

            self.assertTrue(second_status.unclean_exit)
            self.assertEqual(second_status.consecutive_crashes, 1)
            self.assertFalse(second_status.safe_mode)
            self.assertEqual(third_status.consecutive_crashes, 2)
            self.assertTrue(third_status.safe_mode)

    def test_exception_writes_diagnostic_and_preserves_active_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [100.0]
            recovery = self.recovery(root, now)
            recovery.begin()
            try:
                raise RuntimeError("test crash")
            except RuntimeError as error:
                report = recovery.record_exception(type(error), error, error.__traceback__)
            recovery.finish()

            marker = json.loads((root / "session_recovery.json").read_text(encoding="utf-8"))
            self.assertTrue(report.is_file())
            self.assertIn("RuntimeError: test crash", report.read_text(encoding="utf-8"))
            self.assertTrue(marker["active"])
            self.assertIn("RuntimeError: test crash", marker["last_error"])

    def test_healthy_long_sessions_killed_by_os_do_not_trigger_safe_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [100.0]

            # Session 1 runs stably for 90s with heartbeats, then gets force-killed (no finish())
            first = self.recovery(root, now)
            first.begin()
            now[0] = 190.0
            first.heartbeat()

            # Session 2 launches: sees unclean exit, but NOT a crash loop; runs stably 120s and gets killed again
            now[0] = 250.0
            second = self.recovery(root, now)
            s2 = second.begin()
            self.assertTrue(s2.unclean_exit)
            self.assertEqual(s2.consecutive_crashes, 0)
            self.assertFalse(s2.safe_mode)
            now[0] = 370.0
            second.heartbeat()

            # Session 3 launches: STILL not safe_mode!
            now[0] = 400.0
            third = self.recovery(root, now)
            s3 = third.begin()
            self.assertTrue(s3.unclean_exit)
            self.assertEqual(s3.consecutive_crashes, 0)
            self.assertFalse(s3.safe_mode)

    def test_real_exception_after_long_run_still_counts_and_stable_heartbeat_clears_streak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [100.0]

            # Two real crashes (even after running > 60s) still activate safe_mode
            for i in range(2):
                rec = self.recovery(root, now)
                rec.begin()
                now[0] += 120.0
                rec.heartbeat()
                try:
                    raise RuntimeError(f"boom {i}")
                except RuntimeError as err:
                    rec.record_exception(type(err), err, err.__traceback__)
                now[0] += 10.0

            safe = self.recovery(root, now)
            status = safe.begin()
            self.assertEqual(status.consecutive_crashes, 2)
            self.assertTrue(status.safe_mode)

            # Once safe-mode session runs stably past 60s, heartbeat clears stale crash streak
            now[0] += 70.0
            safe.heartbeat()
            marker = json.loads((root / "session_recovery.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["consecutive_crashes"], 0)
            self.assertFalse(marker["safe_mode"])


if __name__ == "__main__":
    unittest.main()
