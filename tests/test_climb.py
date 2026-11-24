import tempfile
import time
import unittest
from pathlib import Path

from pet.climb import (
    CLIMB_SPEED,
    PULL_PERIOD,
    ClimbController,
    Rect,
    is_exposed,
    pick_jump,
    plan_climb,
    uncovered_top_span,
)

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
        self.assertIsNone(plan(Rect(1200, 375, 1700, 1040)))  # land_y = -5 < work_area.top
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
        grab = self.run_until("grab")  # a beat with both hands on the edge
        self.assertEqual((grab.x, grab.y), (self.plan.climb_x, 660.0))
        climb = self.run_until("climb")
        self.assertEqual(climb.x, self.plan.climb_x)
        mantle = self.run_until("mantle")  # hands on the top edge
        self.assertEqual(mantle.y, self.plan.top_y)
        done = self.run_until("done")  # pulled over: standing on the top
        self.assertEqual((done.x, done.y), (self.plan.land_x, self.plan.land_y))
        self.assertGreater(done.x, self.plan.climb_x)  # came up the left edge, now inside
        self.assertFalse(self.climb.active)
        self.assertTrue(self.climb.sit_after)

    def test_climbs_straight_up_in_pulls_at_climb_speed(self):
        self.run_until("climb")
        # One full pull averages CLIMB_SPEED ...
        step = self.climb.step(PULL_PERIOD, x=self.plan.climb_x, y=660.0, window=self.window)
        self.assertAlmostEqual(660.0 - step.y, CLIMB_SPEED * PULL_PERIOD, delta=0.5)
        self.assertEqual(step.x, self.plan.climb_x)
        # ... but it is a pull: slow at the start, fast in the middle.
        self.assertLess(ClimbController.pull_speed(0.0), CLIMB_SPEED * 0.5)
        self.assertGreater(ClimbController.pull_speed(PULL_PERIOD / 2), CLIMB_SPEED * 1.5)

    def test_measured_hands_set_the_wall_gap_and_the_stop_height(self):
        near = plan(Rect(1200, 500, 1700, 1040), reach=50.0, hand_rise=220.0)
        self.assertAlmostEqual(near.climb_x + 100.0, 1200 - 50.0)  # widget centre = wall - reach
        self.assertAlmostEqual(near.top_y + 380.0 - 11.0, 500 + 220.0)  # feet = top + hand rise

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
                self.assertNotIn(PetAction.FALLING, seen)  # pulled herself over, no jump
                self.assertLess(window.y(), floor_y)  # she went up the wall
                self.assertFalse(window.physics.active)
                self.assertEqual(window.y(), top - window.height())  # where attachment keeps her
                update = window.surface_tracker.follow_attachment(
                    now=now, widget_x=float(window.x()), widget_width=float(window.width()),
                    widget_height=float(window.height()), sink=0.0,
                )
                self.assertAlmostEqual(update.y, window.y())  # no snap after the pull-over
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


class WidgetCase(unittest.TestCase):
    """A real PetWindow standing on the floor of the offscreen screen."""

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


class ExploreTests(WidgetCase):
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

    def test_rejects_oversized_near_top_window_and_works_on_floor(self):
        from types import SimpleNamespace

        from agy.autonomy import AutonomyCommand, WindowTarget
        from agy.telemetry import LiveSnapshot
        from animation.clip import PetAction

        window = self.window
        top = 150  # smaller than window.height() (~322 px)
        target = WindowTarget(1, 200, top, 760, self.bottom)
        window.surface_tracker.reader = FakeReader({1: (200, top, 760, self.bottom)})
        self.assertFalse(window._start_climb(1))
        self.assertIsNone(window._nearest_climbable())
        self.assertIsNone(window._plan_jump(from_floor=True))
        self.assertFalse(window._hop_to(AutonomyCommand(kind="hop", window=target, reason="hop")))

        window.agy_windows.find = lambda: target
        window.surface_tracker.reader.foreground_handle = lambda: 1
        window.telemetry.last_snapshot = LiveSnapshot(
            source="ls",
            conversation_id="c",
            status="CASCADE_RUN_STATUS_IDLE",
            cumulative_total_tokens=0,
        )
        window._autonomy_next = 0.0
        window._tick_autonomy(1000.0)
        window.telemetry.last_snapshot = LiveSnapshot(
            source="ls",
            conversation_id="c",
            status="CASCADE_RUN_STATUS_RUNNING",
            cumulative_total_tokens=100,
        )
        window._autonomy_next = 0.0
        window._tick_autonomy(1010.0)
        self.assertEqual(window.action_machine.current, PetAction.WORKING)
        self.assertFalse(window.physics.active)
        self.assertFalse(window.climb.active)
        self.assertEqual(window.autonomy.state.last_hop_at, -1e9)

    def test_detaches_and_lands_gently_when_perched_window_grows_near_top(self):
        from animation.clip import PetAction

        window = self.window
        top = self.bottom - 199
        rects = {1: (260, top, 740, self.bottom)}
        window.surface_tracker.reader = FakeReader(rects)
        window.surface_tracker.set_target(1)
        window.move(360, top - window.height())
        self.assertTrue(
            window.surface_tracker.attach(
                "window:1",
                widget_x=360.0,
                widget_width=float(window.width()),
                widget_height=float(window.height()),
                work_area_top=window._surface_work_area_top,
            )
        )
        window._request_action(PetAction.PERCH, reason="test", force=True, immediate=True)

        # User pulls or resizes the window near the screen top: pet must detach cleanly.
        rects[1] = (260, 140, 740, self.bottom)
        window.surface_tracker.refresh_soon()
        window.tick()

        self.assertFalse(window.surface_tracker.attached)
        self.assertTrue(window.physics.active)
        bounds = window._physics_bounds()
        now = time.monotonic()
        for _ in range(400):
            if not window.physics.active:
                break
            window._tick_throw(0.02, now)
            self.assertGreaterEqual(window.y(), int(bounds.top))
            now += 0.02
        self.assertFalse(window.physics.active)
        self.assertEqual(window.y(), self.floor_y)
        self.assertEqual(window.action_machine.current, PetAction.LANDING)
        window.action_machine.update(now=now + 30.0)
        self.assertNotEqual(window.action_machine.current, PetAction.DIZZY)


if __name__ == "__main__":
    unittest.main()


class TopEdgeTests(unittest.TestCase):
    def test_uncovered_span_skips_windows_lying_over_the_top_edge(self):
        window = Rect(100, 500, 900, 1000)
        self.assertEqual(uncovered_top_span(window, []), (100, 900))
        self.assertEqual(uncovered_top_span(window, [Rect(0, 300, 400, 800)]), (400, 900))
        self.assertEqual(uncovered_top_span(window, [Rect(300, 450, 500, 700)]), (500, 900))
        self.assertEqual(uncovered_top_span(window, [Rect(300, 100, 500, 400)]), (100, 900))  # above, not touching
        self.assertIsNone(uncovered_top_span(window, [Rect(0, 0, 1000, 600)]))

    def test_pick_jump_prefers_the_closest_reachable_top(self):
        kw = dict(work_area=WORK, sprite_width=150.0, sprite_height=300.0, exclude=1,
                  max_gap=300.0, max_up=270.0, max_down=750.0)
        here = (1, Rect(100, 600, 700, 1000))
        near = (2, Rect(800, 500, 1300, 900))  # 100 px gap, 100 px higher
        far = (3, Rect(1500, 600, 1900, 1000))  # too far sideways
        high = (4, Rect(720, 100, 1100, 400))  # too high to jump up to
        jump = pick_jump(windows=[here, near, far, high], feet_y=600.0, center_x=650.0, **kw)
        self.assertEqual(jump.handle, 2)
        self.assertGreaterEqual(jump.land_center_x, 800 + 75)  # whole body on the new top
        self.assertIsNone(pick_jump(windows=[here, far, high], feet_y=600.0, center_x=650.0, **kw))
        # A window lying over the neighbour's near end pushes the landing spot past it.
        cover = (5, Rect(780, 450, 950, 700))  # too narrow to land on
        jump = pick_jump(windows=[cover, here, near], feet_y=600.0, center_x=650.0, **{**kw, "max_gap": 500.0})
        self.assertEqual(jump.handle, 2)
        self.assertGreaterEqual(jump.land_center_x, 950 + 75)

    def test_pick_jump_respects_min_headroom(self):
        # ``tight`` is closer horizontally than ``roomy``, but clipped at the top.
        tight = (2, Rect(200, 350, 600, 800))  # rect.top < 380: clipped with widget_height=380
        roomy = (3, Rect(1120, 460, 1550, 900))
        jump = pick_jump(
            windows=[tight, (1, Rect(650, 600, 1050, 1000)), roomy],
            work_area=WORK,
            feet_y=600.0,
            center_x=750.0,
            sprite_width=150.0,
            sprite_height=300.0,
            exclude=1,
            max_gap=450.0,
            max_up=270.0,
            max_down=750.0,
            min_headroom=380.0,
        )
        self.assertIsNotNone(jump)
        self.assertEqual(jump.handle, 3)


class RoamTests(WidgetCase):
    """Strolling on a window top and jumping between windows (real widget)."""

    def attach_to(self, handle, rects, x=400):
        window = self.window
        window.surface_tracker.reader = FakeReader(rects)
        window.surface_tracker.set_target(handle)
        left, top, right, bottom = rects[handle]
        window.move(x, top - window.height() + 11)
        self.assertTrue(window.surface_tracker.attach(f"window:{handle}", widget_x=float(x), widget_width=float(window.width())))
        window.surface_tracker.set_target(None)

    def test_strolls_only_along_the_uncovered_part_of_the_top(self):
        from animation.clip import PetAction

        top = self.bottom - 300
        # The offscreen test screen is 800 x 800.
        self.attach_to(1, {0: (500, top - 200, 800, top + 100), 1: (100, top, 790, self.bottom)}, x=100)
        window = self.window
        window._request_action(PetAction.PERCH, reason="test", force=True)
        lower, upper = window._top_bounds()
        self.assertLessEqual(upper + window.width() / 2.0, 500)  # stops before the covering window
        self.assertTrue(window._walk_on_top(time.monotonic()))
        self.assertEqual(window.action_machine.current, PetAction.IDLE)  # stood up to walk
        target_x, _ = window.movement.target
        self.assertTrue(lower <= target_x <= upper)

    def test_jumps_across_to_a_neighbouring_window_and_lands_on_it(self):
        top = self.bottom - 300
        self.attach_to(1, {1: (20, top, 360, self.bottom), 2: (430, top - 120, 790, self.bottom)}, x=44)
        window = self.window
        jump = window._plan_jump(from_floor=False)
        self.assertIsNotNone(jump)
        self.assertEqual(jump.handle, 2)
        self.assertTrue(window._jump_to(jump))
        self.assertFalse(window.surface_tracker.attached)
        now = time.monotonic()
        for _ in range(400):
            if not window.physics.active:
                break
            window._tick_throw(0.02, now)
            now += 0.02
        self.assertEqual(window.surface_tracker.attached_handle, 2)
        self.assertEqual(window._explored_handle, 2)  # she may later climb down from it

    def test_hops_up_onto_a_floating_window_from_the_floor(self):
        window = self.window
        sprite_h = window._frame_size()[1]
        top = round(self.bottom - sprite_h * 1.2)
        window.surface_tracker.reader = FakeReader({3: (380, top, 790, top + 130)})  # floating
        self.assertIsNone(window._nearest_climbable())
        jump = window._plan_jump(from_floor=True)
        self.assertIsNotNone(jump)
        self.assertTrue(window._jump_to(jump))
        now = time.monotonic()
        for _ in range(400):
            if not window.physics.active:
                break
            window._tick_throw(0.02, now)
            now += 0.02
        self.assertEqual(window.surface_tracker.attached_handle, 3)

    def test_explores_during_a_run_but_not_off_antigravity(self):
        from types import SimpleNamespace

        from animation.clip import PetAction

        window = self.window
        top = self.bottom - 199
        window.surface_tracker.reader = FakeReader({1: (330, top, 700, self.bottom)})
        window.telemetry.last_snapshot = SimpleNamespace(running=True)
        window._request_action(PetAction.WORKING, reason="test", force=True)
        window._explore_next = 0.0
        window._tick_explore(time.monotonic())
        self.assertTrue(window.climb.active)  # climbs even while Antigravity works


class SitQuietlyTests(WidgetCase):
    def test_she_keeps_sitting_after_climbing_up_to_sit(self):
        from animation.clip import PetAction

        window = self.window
        top = self.bottom - 300
        window.surface_tracker.reader = FakeReader({1: (20, top, 360, self.bottom), 2: (430, top - 120, 790, self.bottom)})
        window.surface_tracker.set_target(1)
        window.move(44, top - window.height())
        window.surface_tracker.attach("window:1", widget_x=44.0, widget_width=float(window.width()))
        window._explored_handle = 1
        now = time.monotonic()
        window._perch_after_landing = True
        window._settle_landing("window:1", hard=False, now=now)
        window._request_action(PetAction.PERCH, reason="test", force=True, immediate=True)
        for second in range(80):
            window._explore_next = 0.0
            window._tick_explore(now + second)
        self.assertEqual(window.action_machine.current, PetAction.PERCH)
        self.assertFalse(window.physics.active)
        self.assertIsNone(window.movement.target)
