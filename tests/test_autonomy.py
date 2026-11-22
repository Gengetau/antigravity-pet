from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from agy.autonomy import AgyAutonomy, AutonomyInput, AutonomySettings, WindowTarget, plan_hop
from agy.telemetry import LiveSnapshot
from pet.physics import PhysicsBounds, PhysicsPlatform, ThrowPhysics

ROOT = Path(__file__).resolve().parents[1]
WIN = WindowTarget(handle=42, left=600, top=500, right=1600, bottom=1300)


def snap(running=False, tokens=0, quota=None) -> LiveSnapshot:
    return LiveSnapshot(
        source="ls",
        conversation_id="c",
        status="CASCADE_RUN_STATUS_RUNNING" if running else "CASCADE_RUN_STATUS_IDLE",
        cumulative_total_tokens=tokens,
        quota_remaining_pct=quota,
    )


class Driver:
    """Feeds the autonomy layer and applies its actions like the window would."""

    def __init__(self, **settings) -> None:
        self.auto = AgyAutonomy(random.Random(1), AutonomySettings(**settings))
        self.action = "IDLE"
        self.perched = False

    def step(self, now, snapshot, *, busy=False, user_idle=None, window=None, can_hop=True):
        commands = self.auto.update(
            AutonomyInput(now=now, snapshot=snapshot, pet_action=self.action, busy=busy, perched=self.perched,
                          user_idle_seconds=user_idle, window=window, can_hop=can_hop)
        )
        for command in commands:
            if command.kind == "action":
                self.action = command.action
        return [(c.kind, c.action or c.reason) for c in commands]


class AutonomyTests(unittest.TestCase):
    def test_work_along_then_stop(self) -> None:
        d = Driver()
        d.step(0, snap())
        self.assertEqual(d.step(10, snap(running=True)), [("action", "WORKING")])
        self.assertEqual(d.step(11, snap(running=True)), [])  # stays working, no spam
        self.assertEqual(d.step(20, snap(tokens=500)), [("action", "IDLE")])

    def test_never_overrides_the_user(self) -> None:
        d = Driver()
        d.step(0, snap())
        d.action = "DRAGGING"
        self.assertEqual(d.step(1, snap(running=True), busy=True), [])
        d.action = "IDLE"
        self.assertEqual(d.step(2, snap(running=True)), [])  # still settling after the drag
        self.assertEqual(d.step(4, snap(running=True)), [("action", "WORKING")])
        d.action = "EATING"  # user is feeding: leave it
        self.assertEqual(d.step(5, snap(running=True)), [])

    def test_hop_once_per_run_with_cooldown(self) -> None:
        d = Driver()
        d.step(0, snap())
        self.assertEqual(d.step(10, snap(running=True), window=WIN), [("hop", "hop"), ("say", "hop")])
        self.assertEqual(d.step(11, snap(running=True), window=WIN), [("action", "WORKING")])
        d.step(20, snap())
        # new run inside the 10-minute cooldown: no second jump
        self.assertEqual(d.step(30, snap(running=True), window=WIN), [("action", "WORKING")])
        d.step(40, snap())
        self.assertEqual(d.step(700, snap(running=True), window=WIN)[0], ("hop", "hop"))
        self.assertEqual(Driver().step(0, snap(running=True), window=WIN, can_hop=False), [("action", "WORKING")])

    def test_perch_after_run_then_resume_life(self) -> None:
        d = Driver(perch_linger_seconds=60)
        d.perched = True
        d.step(0, snap(running=True))
        self.assertEqual(d.step(5, snap()), [("action", "PERCH")])
        self.assertEqual(d.step(30, snap()), [])
        self.assertEqual(d.step(70, snap()), [("action", "IDLE")])

    def test_wake_from_nap_when_run_starts(self) -> None:
        d = Driver(nap_after_seconds=100)
        d.step(0, snap(tokens=1))
        self.assertEqual(d.step(50, snap(tokens=1), user_idle=999), [])
        self.assertEqual(d.step(120, snap(tokens=1), user_idle=10), [])  # user is here: no nap
        self.assertEqual(d.step(121, snap(tokens=1), user_idle=999), [("action", "SLEEPING"), ("say", "nap")])
        self.assertEqual(d.step(200, snap(tokens=1), user_idle=999), [])  # once per quiet stretch
        self.assertEqual(d.step(210, snap(running=True, tokens=2))[:2], [("action", "WAVE"), ("say", "wake")])

    def test_quota_tired_and_recharged(self) -> None:
        d = Driver(tired_interval=(100, 100))
        d.step(0, snap(quota=60))
        self.assertEqual(d.step(1, snap(quota=20)), [])
        self.assertEqual(d.step(30, snap(quota=20)), [("action", "TIRED"), ("say", "tired")])
        d.action = "IDLE"
        self.assertEqual(d.step(60, snap(quota=20)), [])
        self.assertEqual(d.step(131, snap(quota=19))[0], ("action", "TIRED"))
        d.action = "IDLE"
        self.assertEqual(d.step(140, snap(quota=100)), [("action", "CELEBRATE"), ("say", "recharged")])

    def test_stretch_after_long_session(self) -> None:
        d = Driver(stretch_after_seconds=600, session_gap_seconds=300)
        d.step(0, snap(running=True))
        for t in range(60, 600, 60):
            d.step(t, snap(running=t % 120 == 0, tokens=t))
            d.action = "IDLE"
        self.assertEqual(d.step(610, snap(tokens=999)), [("action", "STRETCH"), ("say", "stretch")])

    def test_greet_after_antigravity_reopens(self) -> None:
        d = Driver()
        d.step(0, snap())
        d.step(10, None)
        self.assertEqual(d.step(30, snap()), [])  # only 20 s away
        d.step(40, None)
        self.assertEqual(d.step(200, snap()), [("action", "WAVE"), ("say", "greet")])


class HopPhysicsTests(unittest.TestCase):
    def test_planned_jump_lands_on_the_window_edge(self) -> None:
        physics = ThrowPhysics()
        width, height = 300.0, 330.0
        start_x, start_y = 200.0, 1392.0 - height
        velocity = plan_hop(start_x=start_x, start_y=start_y, widget_width=width, widget_height=height, target=WIN,
                            gravity=physics.gravity, max_speed=physics.max_jump_speed, work_area_top=0.0)
        self.assertIsNotNone(velocity)
        platform = PhysicsPlatform(WIN.left + 8.0, WIN.right - 8.0, float(WIN.top), "window:42")
        bounds = PhysicsBounds(0.0, 0.0, 2559.0, 1392.0, platforms=(platform,))
        physics.launch(start_x, start_y, *velocity, planned_jump=True)
        step = None
        for _ in range(400):
            step = physics.step(0.016, width=width, height=height, bounds=bounds)
            if step.settled:
                break
        self.assertTrue(step.settled)
        self.assertEqual(step.landed_surface_id, "window:42")
        self.assertFalse(step.hard_landing)
        self.assertAlmostEqual(step.y, WIN.top - height, delta=1.0)
        # sticks the landing well inside the window, not sliding off its edge
        center = step.x + width / 2.0
        self.assertGreater(center, WIN.left + 40)
        self.assertLess(center, WIN.right - 40)

    def test_unreachable_windows_are_rejected(self) -> None:
        kwargs = dict(start_x=0.0, start_y=1000.0, widget_width=300.0, widget_height=330.0, gravity=2350.0, max_speed=3200.0, work_area_top=0.0)
        maximized = WindowTarget(1, 0, 0, 2560, 1392)
        narrow = WindowTarget(2, 100, 600, 200, 900)
        self.assertIsNone(plan_hop(target=maximized, **kwargs))
        self.assertIsNone(plan_hop(target=narrow, **kwargs))


class FallbackActionTests(unittest.TestCase):
    def test_new_actions_fall_back_to_existing_art(self) -> None:
        from animation.asset_registry import AssetRegistry

        base = ROOT / "assets" / "manifests" / "actions_base.json"
        registry = AssetRegistry(ROOT / "carbon", base_manifest=base)
        # the generated art now ships real frames for the new actions
        self.assertTrue(registry.has_real_frames("work_typing"))
        self.assertEqual(registry.resolve_asset_id("work_typing"), "work_typing")
        registry.manifest["fallbacks"]["not_drawn_yet"] = "idle_think"
        self.assertFalse(registry.has_real_frames("not_drawn_yet"))
        self.assertEqual(registry.resolve_asset_id("not_drawn_yet"), "idle_think")
        self.assertEqual(registry.resolve_asset_id("happy"), "happy")
        registry.manifest["fallbacks"]["loop_a"] = "loop_b"
        registry.manifest["fallbacks"]["loop_b"] = "loop_a"
        self.assertIn(registry.resolve_asset_id("loop_a"), {"loop_a", "loop_b"})  # cycle-safe


class WindowAutonomyTests(unittest.TestCase):
    def test_pet_works_along_and_hops(self) -> None:
        from PySide6.QtWidgets import QApplication

        from animation.clip import PetAction
        from app.paths import AppPaths
        from pet.window import PetWindow
        from settings.config import ConfigManager

        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            paths = AppPaths(app_dir=Path(folder), bundle_dir=ROOT)
            window = PetWindow(paths, ConfigManager(paths.config_path))
            try:
                window.telemetry.last_snapshot = snap()
                window._autonomy_next = 0
                window._tick_autonomy(1000.0)
                window.telemetry.last_snapshot = snap(running=True)
                window.agy_windows.find = lambda: None  # no reachable window
                window._autonomy_next = 0
                window._tick_autonomy(1010.0)
                self.assertEqual(window.action_machine.current, PetAction.WORKING)
                window.telemetry.last_snapshot = snap(tokens=10)
                window._autonomy_next = 0
                window._tick_autonomy(1020.0)
                self.assertEqual(window.action_machine.current, PetAction.IDLE)
                window.set_autonomy(False)
                self.assertFalse(json.loads(paths.config_path.read_text(encoding="utf-8"))["agy"]["autonomy"])
            finally:
                window.telemetry.stop()
                window.hud_bar.close()
                window.token_meter.close()
                window.control_panel.close()
                window.food_panel.close()
                window.tray.hide()
                window.close()


if __name__ == "__main__":
    unittest.main()
