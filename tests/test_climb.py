import tempfile
import time
import unittest
from pathlib import Path

from pet.climb import CLIMB_SPEED, ClimbController, Rect, is_exposed, plan_climb

WORK = Rect(0, 0, 1920, 1040)
# Widget 200x380; feet 11 px above its bottom -> feet at y=1029 when y=660.
PET = dict(widget_y=660.0, widget_width=200.0, widget_height=380.0, feet_offset=11.0,
           sprite_width=180.0, sprite_height=306.0)


def plan(window, x=900.0, **extra):
    return plan_climb(handle=7, window=window, work_area=WORK, widget_x=x, **{**PET, **extra})


class PlanClimbTests(unittest.TestCase):
    def test_picks_the_nearer_edge_and_faces_the_wall(self):
        window = Rect(1200, 500, 1700, 1040)
        result = plan(window, x=900.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.side, "left")
        self.assertEqual(result.facing, "right")
        self.assertLess(result.climb_x + 100, window.left)  # stands just outside the wall
        result = plan(Rect(300, 500, 800, 1040), x=900.0)
        self.assertEqual(result.side, "right")
        self.assertEqual(result.facing, "left")

    def test_stops_with_hands_at_the_top_edge(self):
        result = plan(Rect(1200, 500, 1700, 1040))
        feet_at_top = result.top_y + 380.0 - 11.0
        self.assertGreater(feet_at_top, 500)  # feet still below the edge
        self.assertLess(feet_at_top - 500, 306)  # but the body reaches over it

    def test_refuses_unclimbable_windows(self):
        self.assertIsNone(plan(Rect(1200, 300, 1700, 700)))  # floating: hop instead
        self.assertIsNone(plan(Rect(1200, 100, 1700, 1040)))  # no room on top for her
        self.assertIsNone(plan(Rect(0, 500, 1920, 1040)))  # full width: no side to climb
        self.assertIsNone(plan(Rect(1200, 1000, 1700, 1040)))  # barely taller than a step
        self.assertIsNone(plan(Rect(1700, 500, 1900, 1040), x=100.0))  # too far away


class ExposedTests(unittest.TestCase):
    def test_a_window_on_top_hides_the_climbing_side_or_the_top_edge(self):
        window = Rect(1200, 500, 1700, 1040)
        result = plan(window)  # climbs the left side
        self.assertTrue(is_exposed(result, window, []))
        self.assertFalse(is_exposed(result, window, [Rect(1000, 400, 1400, 1040)]))  # over the left side
        self.assertFalse(is_exposed(result, window, [Rect(1250, 300, 1700, 700)]))  # over the top edge
        self.assertTrue(is_exposed(result, window, [Rect(1500, 700, 1900, 1040)]))  # only the far corner


class ClimbControllerTests(unittest.TestCase):
    def setUp(self):
        self.window = Rect(1200, 500, 1700, 1040)
        self.plan = plan(self.window)
        self.climb = ClimbController()
        self.climb.start(self.plan, sit_after=True)

    def run_until(self, phase, limit=2000):
        x, y = 900.0, 660.0
        for _ in range(limit):
            step = self.climb.step(0.016, x=x, y=y, window=self.window)
            x, y = step.x, step.y
            if step.phase == phase:
                return step
        self.fail(f"never reached {phase}")

    def test_walks_then_climbs_then_finishes_at_the_top(self):
        step = self.climb.step(0.016, x=900.0, y=660.0, window=self.window)
        self.assertEqual((step.phase, step.facing), ("approach", "right"))
        self.assertEqual(step.y, 660.0)
        climb = self.run_until("climb")
        self.assertEqual(climb.x, self.plan.climb_x)
        done = self.run_until("done")
        self.assertEqual(done.y, self.plan.top_y)
        self.assertFalse(self.climb.active)
        self.assertTrue(self.climb.sit_after)

    def test_climbs_straight_up_at_climb_speed(self):
        self.run_until("climb")
        step = self.climb.step(0.5, x=self.plan.climb_x, y=660.0, window=self.window)
        self.assertAlmostEqual(660.0 - step.y, CLIMB_SPEED * 0.5)
        self.assertEqual(step.x, self.plan.climb_x)

    def test_aborts_when_the_window_moves_or_closes(self):
        self.run_until("climb")
        moved = Rect(1300, 500, 1800, 1040)
        self.assertEqual(self.climb.step(0.016, x=0, y=0, window=moved).phase, "aborted")
        self.climb.start(self.plan)
        self.assertEqual(self.climb.step(0.016, x=0, y=0, window=None).phase, "aborted")


class FakeReader:
    def __init__(self, rects):
        self.rects = rects

    def foreground_handle(self):
        return 0

    def list_windows(self):
        return list(self.rects)

    def read(self, handle):
        return self.rects.get(handle)


class WindowClimbTests(unittest.TestCase):
    def test_climbs_onto_a_window_and_sits_on_its_edge(self):
        from PySide6.QtWidgets import QApplication

        from animation.clip import PetAction
        from app.paths import AppPaths
        from pet.window import PetWindow
        from settings.config import ConfigManager

        QApplication.instance() or QApplication([])
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            paths = AppPaths(app_dir=Path(folder), bundle_dir=root)
            window = PetWindow(paths, ConfigManager(paths.config_path))
            try:
                bounds = window._physics_bounds()
                floor_y = int(bounds.bottom) + 1 - window.height()
                window.move(0, floor_y)
                top = int(bounds.bottom) - 199
                window.surface_tracker.reader = FakeReader({9: (330, top, 700, int(bounds.bottom))})
                window._request_action(PetAction.WORKING, reason="test", force=True)
                self.assertTrue(window._start_climb(9, sit_after=True))
                now = 100.0
                window._tick_climb(0.05, now)
                self.assertEqual(window.action_machine.current, PetAction.WALKING)  # not gliding while typing
                seen = set()
                for _ in range(800):  # walk to the wall, then climb it
                    if not window.climb.active:
                        break
                    window._tick_climb(0.05, now)
                    seen.add(window.action_machine.current)
                    now += 0.05
                self.assertIn(PetAction.CLIMBING, seen)
                self.assertLess(window.y(), floor_y)  # she went up the wall
                self.assertTrue(window.physics.active)  # hopping over the top
                for _ in range(200):
                    if not window.physics.active:
                        break
                    window._tick_throw(0.03, now)
                    now += 0.03
                self.assertTrue(window.surface_tracker.attached)
                self.assertEqual(window.surface_tracker.attached_handle, 9)
                window.action_machine.update(now=now + 30.0)  # landing ends
                window._sync_animation_clip(immediate=True)
                self.assertEqual(window.action_machine.current, PetAction.PERCH)
                self.assertEqual(window.player.snapshot().current.asset_id, "perch_sit")
                sink = window._edge_sit_sink()
                self.assertGreater(sink, 20)  # legs hang below the edge
                update = window.surface_tracker.follow_attachment(
                    now=now + 31.0,
                    widget_x=float(window.x()),
                    widget_width=float(window.width()),
                    widget_height=float(window.height()),
                    sink=sink,
                )
                self.assertAlmostEqual(update.y, top - window.height() + sink)
            finally:
                window.telemetry.stop()
                window.hud_bar.close()
                window.token_meter.close()
                window.control_panel.close()
                window.food_panel.close()
                window.tray.hide()
                window.close()


class ExploreTests(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication

        from app.paths import AppPaths
        from pet.window import PetWindow
        from settings.config import ConfigManager

        QApplication.instance() or QApplication([])
        root = Path(__file__).resolve().parents[1]
        self.folder = tempfile.TemporaryDirectory()
        paths = AppPaths(app_dir=Path(self.folder.name), bundle_dir=root)
        self.window = PetWindow(paths, ConfigManager(paths.config_path))
        bounds = self.window._physics_bounds()
        self.bottom = int(bounds.bottom)
        self.floor_y = self.bottom + 1 - self.window.height()
        self.window.move(0, self.floor_y)

    def tearDown(self):
        window = self.window
        window.telemetry.stop()
        for widget in (window.hud_bar, window.token_meter, window.control_panel, window.food_panel):
            widget.close()
        window.tray.hide()
        window.close()
        self.folder.cleanup()

    def test_finds_the_nearest_climbable_window(self):
        top = self.bottom - 199
        self.window.surface_tracker.reader = FakeReader({
            1: (330, top, 700, self.bottom),  # near, reaches the floor
            2: (560, 100, 790, 300),  # floating: cannot climb
        })
        self.assertEqual(self.window._nearest_climbable(), 1)
        self.window.surface_tracker.reader = FakeReader({2: (560, 100, 790, 300)})
        self.assertIsNone(self.window._nearest_climbable())
        # Window 1 is buried under window 0: she climbs the one on top instead.
        self.window.surface_tracker.reader = FakeReader({0: (200, top - 100, 760, self.bottom), 1: (330, top, 700, self.bottom)})
        self.assertEqual(self.window._nearest_climbable(), 0)

    def test_stays_on_antigravity_after_a_long_run(self):
        from types import SimpleNamespace

        from animation.clip import PetAction

        window = self.window
        top = self.bottom - 199
        window.surface_tracker.reader = FakeReader({1: (330, top, 790, self.bottom)})
        window.surface_tracker.set_target(1)
        window.surface_tracker.attach("window:1", widget_x=400.0, widget_width=float(window.width()))
        window.telemetry.last_snapshot = SimpleNamespace(running=True)
        for minute in range(20):
            window._explore_next = 0.0
            window._tick_explore(100.0 + minute * 60.0)
        window.telemetry.last_snapshot = SimpleNamespace(running=False)
        window._request_action(PetAction.PERCH, reason="run_done", force=True)
        window._explore_next = 0.0
        window._tick_explore(100.0 + 21 * 60.0)
        self.assertIsNone(window._descend_x)  # keeps sitting on Antigravity

    def test_hops_down_from_the_window_end_and_lands_softly(self):
        from animation.clip import PetAction

        window = self.window
        top = self.bottom - 199
        window.surface_tracker.reader = FakeReader({1: (330, top, 790, self.bottom)})
        window.surface_tracker.set_target(1)
        window.move(400, top - window.height())
        self.assertTrue(window.surface_tracker.attach("window:1", widget_x=400.0, widget_width=float(window.width())))
        window._start_descend()
        self.assertIsNotNone(window._descend_x)
        now = 50.0
        for _ in range(400):
            if window._descend_x is None:
                break
            window._tick_descend(0.05, now)
            now += 0.05
        self.assertTrue(window.physics.active)
        self.assertFalse(window.surface_tracker.attached)
        for _ in range(300):
            if not window.physics.active:
                break
            window._tick_throw(0.03, now)
            now += 0.03
        self.assertFalse(window.surface_tracker.attached)  # on the floor, not back on the window
        self.assertEqual(window.y(), self.floor_y)
        self.assertEqual(window.action_machine.current, PetAction.LANDING)
        window.action_machine.update(now=now + 30.0)
        self.assertNotEqual(window.action_machine.current, PetAction.DIZZY)

    def test_on_the_edge_she_keeps_sitting_and_works_sitting(self):
        from animation.clip import PetAction

        window = self.window
        top = self.bottom - 199
        window.surface_tracker.reader = FakeReader({1: (330, top, 790, self.bottom)})
        window.surface_tracker.set_target(1)
        window.surface_tracker.attach("window:1", widget_x=400.0, widget_width=float(window.width()))
        window._request_action(PetAction.PERCH, reason="test", force=True, immediate=True)
        self.assertEqual(window.player.snapshot().current.asset_id, "perch_sit")
        other = "neon" if window.form_id != "neon" else "carbon"
        window.set_form(other, announce=False, persist=False)
        self.assertEqual(window.action_machine.current, PetAction.PERCH)  # no stand-up transform
        self.assertEqual(window.player.snapshot().current.asset_id, "perch_sit")
        clip = window.asset_registry.clip_for(PetAction.PERCH, height=window.current_height, direction="edge")
        self.assertEqual(len(clip.frames), 1)  # sits still: one frame, no wobble
        window._request_action(PetAction.POKE_REACT, reason="test", force=True)
        window.action_machine.update(now=time.monotonic() + 30.0)
        self.assertEqual(window.action_machine.current, PetAction.PERCH)  # back to sitting, not standing
        window._request_action(PetAction.WORKING, reason="test", force=True)
        self.assertEqual(window.player.snapshot().current.asset_id, "perch_work")
        # Follow-model switches the form and cheers (HAPPY): she stays at work on the edge.
        from types import SimpleNamespace

        target = "hydergon" if window.form_id != "hydergon" else "claude"
        window._agy_set("follow_model", True)
        window.reactions.observe = lambda *a, **k: [SimpleNamespace(form=target, action="HAPPY", text="", kind="form")]
        window._on_live_snapshot(None)
        self.assertEqual(window.form_id, target)
        self.assertEqual(window.action_machine.current, PetAction.WORKING)
        self.assertEqual(window.player.snapshot().current.asset_id, "perch_work")
        self.assertGreater(window._edge_sit_sink(), 20)


if __name__ == "__main__":
    unittest.main()
