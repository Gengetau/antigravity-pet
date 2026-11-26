from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from agy.telemetry import LiveSnapshot, SubagentInfo
from animation.clip import Anchor, AnimationPhase, ClipFrame, PetAction
from animation.effects import EffectPose
from animation.player import RenderLayer
from app.paths import AppPaths
from behavior.activity_director import ActivityCommand, ActivityCueType, ActivityKind
from pet.interaction import InteractionController
from pet.renderer import PetRenderer
from pet.surfaces import DesktopSurfaceTracker
from pet.window import BUBBLE_HEIGHT, EDGE_SIT_TUCK_PX, MARGIN, PetWindow
from settings.config import ConfigManager

ROOT = Path(__file__).resolve().parents[1]


class _FakeScreen:
    def __init__(self, rect: QRect) -> None:
        self._rect = QRect(rect)

    def availableGeometry(self) -> QRect:
        return QRect(self._rect)

    def geometry(self) -> QRect:
        return QRect(self._rect)


class _OccludingReader:
    def __init__(self, rects: dict[int, tuple[int, int, int, int]]) -> None:
        self.rects = dict(rects)
        self.occluded = False
        self.calls: list[tuple[int, float, float, tuple[int, ...]]] = []

    def read(self, handle: int):
        return self.rects.get(handle)

    def foreground_handle(self) -> int:
        return next(iter(self.rects), 0)

    def list_windows(self) -> list[int]:
        return list(self.rects)

    def is_point_occluded(
        self,
        handle: int,
        x: float,
        y: float,
        *,
        ignore_handles: tuple[int, ...] | set[int] = (),
    ) -> bool:
        self.calls.append((handle, x, y, tuple(ignore_handles)))
        return self.occluded


def _mouse_event(
    event_type: QEvent.Type,
    local_pos: QPointF,
    global_pos: QPointF,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    buttons: Qt.MouseButton = Qt.MouseButton.LeftButton,
) -> QMouseEvent:
    return QMouseEvent(
        event_type,
        local_pos,
        global_pos,
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


class DesktopFixesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="agy-desktop-fixes-")
        paths = AppPaths(app_dir=Path(self._tmp.name), bundle_dir=ROOT)
        config = ConfigManager(paths.config_path)
        config.set_nested("agy", "telemetry_enabled", False, save=False)
        config.set_nested("awareness", "enabled", False, save=True)
        self.pet = PetWindow(paths, config)
        self.pet.telemetry.stop()
        self.pet.timer.stop()
        self.pet.persistence_timer.stop()
        self.pet.awareness_timer.stop()
        self.pet.surface_timer.stop()
        self.pet._request_action(PetAction.IDLE, reason="test_reset", force=True, immediate=True)
        self.app.processEvents()

    def tearDown(self) -> None:
        self.pet.subagent_clones.close_all()
        self.pet.hud_bar.hide()
        self.pet.token_meter.hide()
        self.pet.control_panel.hide()
        self.pet.food_panel.hide()
        self.pet.tray.hide()
        self.pet.hide()
        self.pet.close()
        self.app.processEvents()
        self._tmp.cleanup()

    # ----- Group 1: Multi-monitor dock lock, screen-edge clip & peek easing -----

    def test_multimonitor_dock_lock_prevents_seam_teleport_on_form_switch_and_resize(self) -> None:
        disp0 = _FakeScreen(QRect(0, 0, 2560, 1400))
        disp1 = _FakeScreen(QRect(2560, 0, 2560, 1400))

        def fake_screen_at(pt: QPoint):
            return disp1 if pt.x() >= 2560 else disp0

        with patch.object(QApplication, "screenAt", side_effect=fake_screen_at):
            self.pet.move(2620, 700)
            self.pet.dock_to_edge("left")
            self.assertIs(self.pet._dock_screen, disp1)
            docked_x = self.pet.x()
            # Window overhangs the shared seam x=2560 onto Display 0, yet belongs to Display 1.
            self.assertLess(docked_x, 2560)
            self.assertGreater(docked_x + self.pet.width(), 2560)

            # Even if screenAt() returns Display 0 for the overhanging center,
            # form switches, resizes and dock ticks stay locked to Display 1.
            with patch.object(QApplication, "screenAt", return_value=disp0):
                other = "neon" if self.pet.form_id != "neon" else "carbon"
                self.pet.set_form(other, manual=True, announce=False, persist=False)
                self.assertEqual(self.pet.form_id, other)
                self.assertNotEqual(self.pet.action_machine.current, PetAction.TRANSFORM)
                self.assertIs(self.pet._dock_screen, disp1)
                self.assertGreater(self.pet.x() + self.pet.width(), 2560)
                self.assertGreater(self.pet.x(), 2000)  # never teleported to Display 0 left (x~0)

                self.pet.set_size(0.90)
                self.assertIs(self.pet._dock_screen, disp1)
                self.assertGreater(self.pet.x() + self.pet.width(), 2560)
                self.assertGreater(self.pet.x(), 2000)

                self.pet._tick_edge_dock(time.monotonic(), delta_seconds=0.02)
                self.assertGreater(self.pet.x(), 2000)

                # Undock clears _dock_screen and places pet back onto Display 1 (not Display 0).
                self.pet.undock_from_edge(fall_if_airborne=False)
                self.assertIsNone(self.pet._dock_screen)
                self.assertIsNone(self.pet._dock_side)
                self.assertGreaterEqual(self.pet.x(), 2560)

    def test_dock_screen_edge_clip_prevents_bleeding_across_monitor_seam(self) -> None:
        disp1 = _FakeScreen(QRect(2560, 0, 2560, 1400))
        with patch.object(QApplication, "screenAt", return_value=disp1):
            self.pet.move(2620, 700)
            self.pet.dock_to_edge("left")
        seam_local_x = 2560 - self.pet.x()
        self.assertGreater(seam_local_x, 0)
        self.assertLess(seam_local_x, self.pet.width())

        image = QImage(self.pet.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        try:
            self.pet.render(painter, QPoint())
        finally:
            painter.end()

        bleed_pixels = sum(
            1
            for y in range(image.height())
            for x in range(0, seam_local_x)
            if image.pixelColor(x, y).alpha() > 0
        )
        visible_pixels = sum(
            1
            for y in range(image.height())
            for x in range(seam_local_x, image.width())
            if image.pixelColor(x, y).alpha() >= 180
        )
        self.assertEqual(bleed_pixels, 0)
        self.assertGreater(visible_pixels, 500)

    def test_dock_peek_dt_normalized_easing_and_wider_reveal(self) -> None:
        self.pet.dock_to_edge("right")
        docked_x = self.pet.x()
        self.pet._dock_peeking = True

        # 2 steps of 0.02s must match 1 step of 0.04s (dt-normalized exponential ease).
        self.pet._dock_peek_progress = 0.0
        now = time.monotonic()
        self.pet._tick_edge_dock(now, delta_seconds=0.02)
        self.pet._tick_edge_dock(now + 0.02, delta_seconds=0.02)
        two_step = self.pet._dock_peek_progress

        self.pet._dock_peek_progress = 0.0
        self.pet._tick_edge_dock(now + 0.04, delta_seconds=0.04)
        one_step = self.pet._dock_peek_progress
        self.assertAlmostEqual(two_step, one_step, places=4)

        # Full reveal is noticeably wider (~35-42px instead of ~20px).
        peeked_x = self.pet._dock_target_x("right", peek=1.0)
        reveal = docked_x - peeked_x
        self.assertGreaterEqual(reveal, 34)
        self.assertLessEqual(reveal, 46)

    # ----- Group 2: Real sprite hitbox alignment & classify_region --------------

    def test_classify_region_expanded_head_tightened_face_and_reachable_tail(self) -> None:
        c = lambda x, y: InteractionController.classify_region(x, y, 0.0, 0.0, 100.0, 100.0)
        self.assertEqual(c(50, 10), "head")
        self.assertEqual(c(50, 25), "head")
        self.assertEqual(c(20, 15), "head")
        self.assertEqual(c(50, 30), "face")
        self.assertEqual(c(50, 38), "face")
        self.assertEqual(c(26, 42), "face")
        self.assertEqual(c(80, 65), "tail")
        self.assertEqual(c(18, 65), "tail")
        self.assertEqual(c(50, 65), "body")

    def test_mouse_press_uses_real_rendered_sprite_bounds(self) -> None:
        self.pet._request_action(PetAction.IDLE, reason="test", force=True, immediate=True)
        left, top, width, height = self.pet._local_sprite_bounds()
        self.assertLess(width, self.pet.width() * 0.75)  # much narrower than sleep-sized window

        # Click real sprite forehead (head), cheek (face), and outer tail (tail).
        for rx, ry, expected in (
            (0.50, 0.20, "head"),
            (0.50, 0.37, "face"),
            (0.82, 0.65, "tail"),
            (0.50, 0.65, "body"),
        ):
            lx = left + width * rx
            ly = top + height * ry
            gp = QPointF(self.pet.x() + lx, self.pet.y() + ly)
            self.pet.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, QPointF(lx, ly), gp))
            self.assertEqual(self.pet.interaction.body_region, expected, (rx, ry))
            self.pet.interaction.cancel()
            self.pet._hold_timer.stop()

    # ----- Group 3: Rapid-poke sulking vs double-click feed & PET_PURR ----------

    def test_rapid_poke_triggers_sulk_immediately_without_food_panel(self) -> None:
        left, top, width, height = self.pet._local_sprite_bounds()
        lx = left + width * 0.50
        ly = top + height * 0.37  # face
        gp = QPointF(self.pet.x() + lx, self.pet.y() + ly)

        self.pet._recent_pokes.clear()
        self.pet._sulk_until = 0.0

        # Simulate Qt's real 4-rapid-click sequence: Press/Release, DoubleClick/Release x2
        for idx in range(2):
            self.pet.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, QPointF(lx, ly), gp))
            self.pet.mouseReleaseEvent(
                _mouse_event(QEvent.Type.MouseButtonRelease, QPointF(lx, ly), gp, buttons=Qt.MouseButton.NoButton)
            )
            if idx == 0:
                # Single click reacts immediately without 280ms timer wait.
                self.assertEqual(len(self.pet._recent_pokes), 1)
                self.assertIn(self.pet.action_machine.current, {PetAction.POKE_REACT, PetAction.ANGRY})
            self.pet.mouseDoubleClickEvent(_mouse_event(QEvent.Type.MouseButtonDblClick, QPointF(lx, ly), gp))
            self.pet.mouseReleaseEvent(
                _mouse_event(QEvent.Type.MouseButtonRelease, QPointF(lx, ly), gp, buttons=Qt.MouseButton.NoButton)
            )
            self.assertFalse(self.pet.food_panel.isVisible())

        self.assertEqual(len(self.pet._recent_pokes), 4)
        self.assertGreater(self.pet._sulk_until, time.monotonic())
        self.assertEqual(self.pet.action_machine.current, PetAction.SULK)

    def test_double_click_body_opens_food_panel_only_when_not_on_poke_streak(self) -> None:
        left, top, width, height = self.pet._local_sprite_bounds()
        lx = left + width * 0.50
        ly = top + height * 0.65  # body
        gp = QPointF(self.pet.x() + lx, self.pet.y() + ly)

        self.pet._recent_pokes.clear()
        self.pet._sulk_until = 0.0
        self.pet.mouseDoubleClickEvent(_mouse_event(QEvent.Type.MouseButtonDblClick, QPointF(lx, ly), gp))
        self.assertTrue(self.pet.food_panel.isVisible())
        self.pet.food_panel.hide()

        # On a rapid-poke streak (>=2 recent pokes), double-clicking body must NOT open FoodPanel.
        now = time.monotonic()
        self.pet._recent_pokes.extend([now - 0.4, now - 0.2])
        self.pet.mouseDoubleClickEvent(_mouse_event(QEvent.Type.MouseButtonDblClick, QPointF(lx, ly), gp))
        self.assertFalse(self.pet.food_panel.isVisible())
        self.assertEqual(len(self.pet._recent_pokes), 3)

    def test_long_press_head_enters_pet_purr_emits_hearts_and_releases_warmly(self) -> None:
        left, top, width, height = self.pet._local_sprite_bounds()
        lx = left + width * 0.50
        ly = top + height * 0.16  # head
        gp = QPointF(self.pet.x() + lx, self.pet.y() + ly)

        self.pet.particles.clear()
        self.pet.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, QPointF(lx, ly), gp))
        self.assertTrue(self.pet._hold_timer.isActive())

        # Trigger >620ms long-press callback
        self.pet._do_long_press_reaction()
        self.assertEqual(self.pet.action_machine.current, PetAction.PET_PURR)
        self.assertTrue(self.pet._purring)
        self.assertTrue(self.pet.particles.active)

        # Periodic hearts every ~0.55s while still held
        self.pet.particles.clear()
        self.pet._next_purr_heart_at = time.monotonic() - 0.01
        self.pet.tick()
        self.assertTrue(self.pet.particles.active)

        # Releasing from purr returns warmly to IDLE with happy expression cue
        self.pet.mouseReleaseEvent(
            _mouse_event(QEvent.Type.MouseButtonRelease, QPointF(lx, ly), gp, buttons=Qt.MouseButton.NoButton)
        )
        self.assertFalse(self.pet._purring)
        self.assertEqual(self.pet.action_machine.current, PetAction.IDLE)
        self.assertIsNotNone(self.pet.expressions._cue)
        self.assertEqual(self.pet.expressions._cue[0], "happy")

    # ----- Group 4: Airborne undock, Z-order occlusion, drag dock, perch, jump_up -

    def test_airborne_undock_launches_gentle_gravity_fall_to_floor(self) -> None:
        area = self.pet._screen_area_for_pet()
        assert area is not None
        floor_y = area.bottom() - self.pet.height() + 1
        self.pet.move(area.right() - 100, area.top() + 10)
        self.pet.dock_to_edge("right")
        self.assertLess(self.pet.y(), floor_y - 40)

        self.pet.undock_from_edge()
        self.assertIsNone(self.pet._dock_side)
        self.assertTrue(self.pet.physics.active)
        self.assertEqual(self.pet.action_machine.current, PetAction.FALLING)

        now = time.monotonic()
        for _ in range(300):
            if not self.pet.physics.active:
                break
            self.pet._tick_throw(0.02, now)
            now += 0.02
        self.assertFalse(self.pet.physics.active)
        self.assertEqual(self.pet.y(), floor_y)
        self.assertEqual(self.pet.action_machine.current, PetAction.LANDING)
        self.pet.action_machine.update(now=now + 10.0)
        self.assertNotEqual(self.pet.action_machine.current, PetAction.DIZZY)

    def test_z_order_occlusion_detaches_and_falls_gently(self) -> None:
        bounds = self.pet._physics_bounds()
        top = int(bounds.bottom) - 220
        reader = _OccludingReader({42: (120, top, 720, int(bounds.bottom))})
        self.pet.surface_tracker = DesktopSurfaceTracker(reader)  # type: ignore[arg-type]
        self.pet.surface_tracker.observe_window(42, now=10.0)
        self.pet.move(260, top - self.pet.height())
        self.assertTrue(
            self.pet.surface_tracker.attach("window:42", widget_x=260.0, widget_width=float(self.pet.width()))
        )

        # Unoccluded: stays attached
        self.pet.surface_tracker.refresh_soon()
        self.pet.tick()
        self.assertTrue(self.pet.surface_tracker.attached)
        self.assertTrue(reader.calls)
        self.assertIn(int(self.pet.winId()), reader.calls[-1][3])

        # Another window covers window 42 at the pet's perch point -> detaches & falls gently
        reader.occluded = True
        self.pet.surface_tracker.refresh_soon()
        self.pet.tick()
        self.assertFalse(self.pet.surface_tracker.attached)
        self.assertTrue(self.pet.physics.active)
        self.assertEqual(self.pet.action_machine.current, PetAction.FALLING)

    def test_edge_drag_release_velocity_up_to_1400_toward_edge(self) -> None:
        area = self.pet._screen_area_for_pet()
        assert area is not None
        sprite_w = max(80.0, float(self.pet._frame_size()[0]))
        # Position sprite right edge 24px from screen right edge (within 36px, outside 12px)
        x_near_right = round(area.right() - 24 - (self.pet.width() + sprite_w) / 2.0)

        # Moving toward right edge at 1100 px/s -> docks!
        self.pet.move(x_near_right, area.bottom() - self.pet.height() + 1)
        with patch.object(
            self.pet.interaction,
            "release",
            return_value=SimpleNamespace(kind="drag", body_region="body", velocity_x=1100.0, velocity_y=0.0, held_seconds=0.2),
        ):
            self.pet.mouseReleaseEvent(
                _mouse_event(QEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(10, 10), buttons=Qt.MouseButton.NoButton)
            )
        self.assertEqual(self.pet._dock_side, "right")
        self.pet.undock_from_edge(fall_if_airborne=False)

        # Moving AWAY from right edge at -900 px/s -> throws instead of docking
        self.pet.move(x_near_right, area.bottom() - self.pet.height() + 1)
        with patch.object(
            self.pet.interaction,
            "release",
            return_value=SimpleNamespace(kind="drag", body_region="body", velocity_x=-900.0, velocity_y=0.0, held_seconds=0.2),
        ):
            self.pet.mouseReleaseEvent(
                _mouse_event(QEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(10, 10), buttons=Qt.MouseButton.NoButton)
            )
        self.assertIsNone(self.pet._dock_side)
        self.assertTrue(self.pet.physics.active)
        self.pet.physics.cancel()

        # Frantic fling > 1400 px/s toward edge -> throws instead of docking
        self.pet.move(x_near_right, area.bottom() - self.pet.height() + 1)
        with patch.object(
            self.pet.interaction,
            "release",
            return_value=SimpleNamespace(kind="drag", body_region="body", velocity_x=1600.0, velocity_y=0.0, held_seconds=0.2),
        ):
            self.pet.mouseReleaseEvent(
                _mouse_event(QEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(10, 10), buttons=Qt.MouseButton.NoButton)
            )
        self.assertIsNone(self.pet._dock_side)
        self.assertTrue(self.pet.physics.active)

    def test_perch_edge_change_updates_y_immediately_and_applies_tuck(self) -> None:
        bounds = self.pet._physics_bounds()
        top = int(bounds.bottom) - 220
        reader = _OccludingReader({1: (160, top, 760, int(bounds.bottom))})
        self.pet.surface_tracker = DesktopSurfaceTracker(reader)  # type: ignore[arg-type]
        self.pet.surface_tracker.observe_window(1, now=1.0)
        stand_y = top - self.pet.height()
        self.pet.move(300, stand_y)
        self.assertTrue(self.pet.surface_tracker.attach("window:1", widget_x=300.0, widget_width=float(self.pet.width())))

        self.pet._request_action(PetAction.PERCH, reason="test_perch", force=True, immediate=True)
        sink = self.pet._edge_sit_sink()
        self.assertGreater(sink, 20.0 + EDGE_SIT_TUCK_PX - 1.0)
        # Immediately aligned without waiting for next tick() (zero 1-frame flash!)
        self.assertEqual(self.pet.y(), round(top - self.pet.height() + sink))

        # Returning to standing snaps y back immediately too
        self.pet._request_action(PetAction.IDLE, reason="stand_up", force=True, immediate=True)
        self.assertEqual(self.pet.y(), round(stand_y))

    def test_active_jump_plays_jump_up_ascending_and_falling_descending(self) -> None:
        self.pet._launch_throw(180.0, -750.0, reason="test_jump", intentional_jump=True)
        self.assertEqual(self.pet.action_machine.current, PetAction.JUMP_UP)

        now = time.monotonic()
        saw_jump_up = False
        saw_falling = False
        for _ in range(120):
            if not self.pet.physics.active:
                break
            if self.pet.physics.velocity_y < 0:
                if self.pet.action_machine.current == PetAction.JUMP_UP:
                    saw_jump_up = True
            self.pet._tick_throw(0.02, now)
            if self.pet.physics.active and self.pet.physics.velocity_y >= 0:
                if self.pet.action_machine.current == PetAction.FALLING:
                    saw_falling = True
            now += 0.02
        self.assertTrue(saw_jump_up)
        self.assertTrue(saw_falling)

        # Frantic drag-throw (not intentional jump) goes straight to FALLING even when vy < 0
        self.pet._launch_throw(400.0, -750.0, reason="drag_release", intentional_jump=False)
        self.assertEqual(self.pet.action_machine.current, PetAction.FALLING)

    # ----- Group 5: Dock safety, sleep variants, sulk loop, contracts, renderer, wiring -

    def test_dock_safety_auto_undocks_on_feed_and_non_dock_preview(self) -> None:
        self.pet.dock_to_edge("right")
        fav = next(item.id for item in self.pet.food_panel.items if item.taste == "favorite")
        self.pet.on_food(fav)
        self.assertIsNone(self.pet._dock_side)
        self.assertEqual(self.pet.action_machine.current, PetAction.EATING)

        self.pet.dock_to_edge("right")
        self.pet._preview_action("WAVE")
        self.assertIsNone(self.pet._dock_side)
        self.assertEqual(self.pet.action_machine.current, PetAction.WAVE)

        self.pet.dock_to_edge("right")
        self.pet._preview_action("DOCK_SLEEP")
        self.assertEqual(self.pet._dock_side, "right")
        self.assertEqual(self.pet.action_machine.current, PetAction.DOCK_SLEEP)

    def test_sleep_variants_perch_sleep_and_dock_sleep(self) -> None:
        # On floor -> SLEEPING
        self.pet._request_action(PetAction.SLEEPING, reason="test_floor_sleep", force=True, immediate=True)
        self.assertEqual(self.pet.action_machine.current, PetAction.SLEEPING)

        # Perched -> PERCH_SLEEP with seated sink
        bounds = self.pet._physics_bounds()
        top = int(bounds.bottom) - 220
        reader = _OccludingReader({1: (160, top, 760, int(bounds.bottom))})
        self.pet.surface_tracker = DesktopSurfaceTracker(reader)  # type: ignore[arg-type]
        self.pet.surface_tracker.observe_window(1, now=1.0)
        self.pet.surface_tracker.attach("window:1", widget_x=300.0, widget_width=float(self.pet.width()))
        self.pet._request_action(PetAction.SLEEPING, reason="test_perch_sleep", force=True, immediate=True)
        self.assertEqual(self.pet.action_machine.current, PetAction.PERCH_SLEEP)
        self.assertGreater(self.pet._edge_sit_sink(), 20.0)

        # Docked -> DOCK_SLEEP
        self.pet.dock_to_edge("right")
        self.pet._request_action(PetAction.SLEEPING, reason="test_dock_sleep", force=True, immediate=True)
        self.assertEqual(self.pet.action_machine.current, PetAction.DOCK_SLEEP)

    def test_sulking_loop_pauses_activity_suppresses_hover_shy_and_withdraw_uses_sulk(self) -> None:
        now = time.monotonic()
        self.pet._sulk_until = now + 30.0
        self.pet._request_action(PetAction.SULK, now=now, reason="test_sulk", force=True, immediate=True)
        self.pet._hovered = True
        self.pet._update_expression()
        self.assertNotEqual(self.pet.expressions.current, "shy")

        # ActivityDirector does not start new activities while sulking
        self.pet.activity_director._next_decision_at = 0.0
        self.pet._tick_activity(now)
        self.assertFalse(self.pet.activity_director.active)

        # Withdraw's final THINKING cue plays SULK
        self.pet._sulk_until = 0.0
        self.pet._request_action(PetAction.IDLE, now=now, reason="reset", force=True, immediate=True)
        self.pet._execute_activity_command(
            ActivityCommand(ActivityKind.WITHDRAW, ActivityCueType.ACTION, action=PetAction.THINKING),
            now,
        )
        self.assertEqual(self.pet.action_machine.current, PetAction.SULK)

    def test_transient_reaction_returns_to_working_when_agy_running(self) -> None:
        self.pet.agy_windows.find = lambda: None  # Isolate from real host desktop windows
        self.pet.telemetry.last_snapshot = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_RUNNING",
        )
        start = time.monotonic() - 10.0
        self.pet._request_action(PetAction.WAVE, now=start, reason="test_wave", force=True, immediate=True)
        self.assertEqual(self.pet.action_machine.current, PetAction.WAVE)
        self.pet.tick()
        self.assertEqual(self.pet.action_machine.current, PetAction.WORKING)

    def test_engine_contracts_hold_duration_and_walk_frame_rate_scale(self) -> None:
        captured_tick: list[float] = []
        captured_hold: list[bool] = []
        orig_tick = self.pet.player.tick
        orig_update = self.pet.action_machine.update

        def spy_tick(dt: float, *, frame_rate_scale: float = 1.0):
            captured_tick.append(frame_rate_scale)
            return orig_tick(dt, frame_rate_scale=frame_rate_scale)

        def spy_update(*, now: float, hold_duration: bool = False):
            captured_hold.append(hold_duration)
            return orig_update(now=now, hold_duration=hold_duration)

        with patch.object(self.pet.player, "tick", side_effect=spy_tick), patch.object(
            self.pet.action_machine, "update", side_effect=spy_update
        ):
            # Walking at fast speed scales frame_rate_scale > 1.0
            self.pet._request_action(PetAction.WALKING, reason="test_walk", force=True, immediate=True)
            self.pet.movement.current_speed = 115.0
            self.pet.tick()
            self.assertGreater(captured_tick[-1], 1.2)
            self.assertEqual(captured_hold[-1], False)

            # Walking at slow speed scales frame_rate_scale < 1.0 (clamped >= 0.55)
            self.pet._request_action(PetAction.WALKING, reason="test_walk_slow", force=True, immediate=True)
            self.pet.movement.current_speed = 30.0
            self.pet.tick()
            self.assertAlmostEqual(captured_tick[-1], 0.55, places=2)

            # Exit transition sets hold_duration=True
            self.pet._request_action(PetAction.SLEEPING, reason="test_sleep", force=True, immediate=True)
            self.pet._request_action(PetAction.HAPPY, reason="wake_happy", force=True, immediate=False)
            self.assertTrue(self.pet.player.in_exit_transition)
            self.pet.tick()
            self.assertTrue(captured_hold[-1])

    def test_renderer_allows_positive_downward_squash_clamped_softly(self) -> None:
        renderer = PetRenderer(BUBBLE_HEIGHT, MARGIN)
        pix = QPixmap(40, 40)
        pix.fill(QColor(255, 0, 128, 255))
        layer = RenderLayer(
            frame=ClipFrame(Path("dummy.png"), pix),
            action=PetAction.LANDING,
            anchor=Anchor(kind="ground", x=0.5, y=1.0),
            mirrored=False,
            asset_id="landing",
            phase=AnimationPhase.BODY,
        )

        def bottom_opaque_y(offset_y: float) -> int:
            img = QImage(120, 140, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            try:
                renderer._draw_layer(
                    p,
                    layer,
                    QPointF(60.0, 100.0),
                    EffectPose(offset_y=offset_y),
                    1.0,
                )
            finally:
                p.end()
            rows = [y for y in range(img.height()) if img.pixelColor(60, y).alpha() > 200]
            return max(rows)

        y0 = bottom_opaque_y(0.0)
        y6 = bottom_opaque_y(6.0)
        y30 = bottom_opaque_y(30.0)
        self.assertEqual(y6 - y0, 6)
        self.assertEqual(y30 - y0, 12)  # softly clamped at +12px

    def test_subagent_clones_wiring_panel_auto_hide_and_recall_primary(self) -> None:
        # Subagent clones receive dock_edge and perched_window_rect
        subagents = [SubagentInfo("s1", "m1", "test", "Gemini 4 Neon", "neon")]
        snap = LiveSnapshot(source="pet_live", conversation_id="m1", active_subagents=subagents)
        with patch.object(self.pet.subagent_clones, "position_around") as spy_pos:
            self.pet.dock_to_edge("right")
            self.pet._sync_subagent_clones(snap)
            self.assertTrue(spy_pos.called)
            self.assertEqual(spy_pos.call_args.kwargs["dock_edge"], "right")
            self.assertIsNone(spy_pos.call_args.kwargs["perched_window_rect"])

            self.pet.undock_from_edge(fall_if_airborne=False)
            bounds = self.pet._physics_bounds()
            top = int(bounds.bottom) - 220
            reader = _OccludingReader({7: (160, top, 760, int(bounds.bottom))})
            self.pet.surface_tracker = DesktopSurfaceTracker(reader)  # type: ignore[arg-type]
            self.pet.surface_tracker.observe_window(7, now=1.0)
            self.pet.surface_tracker.attach("window:7", widget_x=300.0, widget_width=float(self.pet.width()))
            self.pet._sync_subagent_clones(snap)
            self.assertIsNone(spy_pos.call_args.kwargs["dock_edge"])
            self.assertEqual(
                spy_pos.call_args.kwargs["perched_window_rect"],
                QRect(160, top, 600, int(bounds.bottom) - top),
            )

        # Control panel auto-hides when pet moves >24px
        self.pet.control_panel.popup_near_pet(self.pet.frameGeometry())
        self.pet._panel_open_pet_pos = QPoint(self.pet.x(), self.pet.y())
        self.assertTrue(self.pet.control_panel.isVisible())
        self.pet.move(self.pet.x() + 10, self.pet.y())
        self.assertTrue(self.pet.control_panel.isVisible())
        self.pet.move(self.pet.x() + 30, self.pet.y())
        self.assertFalse(self.pet.control_panel.isVisible())

        # Control panel auto-hides immediately when dragging starts
        self.pet.control_panel.popup_near_pet(self.pet.frameGeometry())
        self.pet._panel_open_pet_pos = QPoint(self.pet.x(), self.pet.y())
        self.assertTrue(self.pet.control_panel.isVisible())
        start = QPointF(self.pet.x() + 40, self.pet.y() + 80)
        self.pet.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, QPointF(40, 80), start))
        self.pet.mouseMoveEvent(_mouse_event(QEvent.Type.MouseMove, QPointF(60, 80), start + QPointF(20, 0)))
        self.assertFalse(self.pet.control_panel.isVisible())
        self.pet.interaction.cancel()
        self.pet._drag_offset = None

        # recall_to_primary_screen undocks/detaches, moves to primary bottom-right, waves
        self.pet.dock_to_edge("left")
        self.pet.recall_to_primary_screen()
        self.assertIsNone(self.pet._dock_side)
        self.assertIsNone(self.pet._dock_screen)
        self.assertFalse(self.pet.surface_tracker.attached)
        self.assertEqual(self.pet.action_machine.current, PetAction.WAVE)
        primary = QApplication.primaryScreen().availableGeometry()
        self.assertGreaterEqual(self.pet.x(), primary.left())
        self.assertLessEqual(self.pet.x() + self.pet.width(), primary.right() + 1)
        self.assertEqual(self.pet.y(), max(primary.top(), primary.bottom() - self.pet.height() + 1))

    def test_win32_is_point_occluded_walks_gw_hwndprev_and_filters_windows(self) -> None:
        from pet.surfaces import Win32WindowRectReader

        own_pid = os.getpid()
        other_pid = own_pid + 999
        # Z-order above handle 100: 101 (invisible) -> 102 (tool) -> 103 (own pid) -> 104 (cloaked) -> 105 (ignored) -> 106 (Chrome)
        prev_map = {100: 101, 101: 102, 102: 103, 103: 104, 104: 105, 105: 106, 106: 0}
        rects = {
            101: (0, 0, 1000, 1000),
            102: (0, 0, 1000, 1000),
            103: (0, 0, 1000, 1000),
            104: (0, 0, 1000, 1000),
            105: (0, 0, 1000, 1000),
            106: (100, 100, 900, 800),
        }

        def _h(hwnd) -> int:
            return int(hwnd.value if hasattr(hwnd, "value") else hwnd)

        class _FakeUser32:
            def IsWindow(self, hwnd):
                return 1 if _h(hwnd) in prev_map else 0

            def GetWindow(self, hwnd, cmd):
                assert cmd == Win32WindowRectReader.GW_HWNDPREV
                return prev_map.get(_h(hwnd), 0)

            def IsWindowVisible(self, hwnd):
                return 0 if _h(hwnd) == 101 else 1

            def IsIconic(self, hwnd):
                return 0

            def GetWindowTextLengthW(self, hwnd):
                return 10

            def GetWindowLongW(self, hwnd, index):
                return 0x00000080 if _h(hwnd) == 102 else 0

            def GetWindowThreadProcessId(self, hwnd, pid_ptr):
                pid_ptr._obj.value = own_pid if _h(hwnd) == 103 else other_pid
                return 1

        reader = object.__new__(Win32WindowRectReader)
        reader.available = True
        reader.user32 = _FakeUser32()
        reader.dwmapi = None
        reader._cloaked = lambda hwnd: _h(hwnd) == 104
        reader.read = lambda h: rects.get(h)

        # Point covered by Chrome (106): occluded!
        self.assertTrue(reader.is_point_occluded(100, 400.0, 200.0, ignore_handles=(105,)))
        # Point outside Chrome (106), even though 101-105 cover it: NOT occluded!
        self.assertFalse(reader.is_point_occluded(100, 50.0, 50.0, ignore_handles=(105,)))
        # If Chrome itself is ignored, none of 101-105 occlude it:
        self.assertFalse(reader.is_point_occluded(100, 400.0, 200.0, ignore_handles=(105, 106)))


class LiveQaRegressionFixesTests(unittest.TestCase):
    """Regression tests for the 4 bugs caught during live v3.1 dual-monitor QA."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="agy-live-qa-fixes-")
        self.tmp_path = Path(self.tmp.name)
        paths = AppPaths(app_dir=self.tmp_path, bundle_dir=ROOT)
        config = ConfigManager(paths.config_path)
        config.set("mode", "still", save=False)
        config.set_nested("comfort", "reduced_motion", False, save=False)
        config.set_nested("agy", "telemetry_enabled", False, save=False)
        config.set_nested("agy", "follow_model", False, save=False)
        config.set_nested("agy", "hud_enabled", False, save=False)
        config.set_nested("awareness", "enabled", False, save=True)
        self.pet = PetWindow(paths, config)
        self.pet.telemetry.stop()
        self.pet.timer.stop()
        self.pet.persistence_timer.stop()
        self.pet.awareness_timer.stop()
        self.pet.surface_timer.stop()
        self.pet.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.pet.control_panel.hide()
        self.pet.food_panel.hide()
        self.pet.tray.hide()
        self.pet.hide()
        self.pet.close()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_docked_control_panel_stays_open_across_peek_and_leave(self) -> None:
        screen = _FakeScreen(QRect(0, 0, 2560, 1392))
        with patch.object(QApplication, "screenAt", return_value=screen):
            self.pet.move(2300, 700)
            self.pet.dock_to_edge("right")
            self.pet._dock_peek_progress = 0.0
            self.pet._dock_peeking = False
            self.pet._hovered = False

            # Opening the panel while docked keeps her peeking out and does not auto-hide it
            # even when _tick_edge_dock slides the window >24px outward or after leave timeout.
            self.pet._dock_peeking = True
            self.pet._panel_open_pet_pos = QPoint(self.pet.x(), self.pet.y())
            self.pet.control_panel.popup_near_pet(self.pet.frameGeometry())
            self.assertTrue(self.pet.control_panel.isVisible())

            start_x = self.pet.x()
            now = time.monotonic()
            self.pet._dock_leave_at = now - 5.0  # Simulate cursor moved away onto panel >0.55s ago
            for step in range(20):
                self.pet._tick_edge_dock(now + step * 0.05, delta_seconds=0.05)
            self.assertGreater(abs(self.pet.x() - start_x), 24)
            self.assertTrue(self.pet._dock_peeking)
            self.assertTrue(self.pet.control_panel.isVisible())

    def test_safe_mode_runtime_override_cleared_only_for_explicit_user_edit(self) -> None:
        cfg = ConfigManager(self.tmp_path / "safe_cfg.json")
        cfg.apply_runtime_overrides(
            {
                "mode": "still",
                "comfort": {"reduced_motion": True, "desktop_surfaces": False},
            }
        )
        self.assertFalse(cfg.section("comfort")["desktop_surfaces"])
        # Explicitly toggling desktop_surfaces back on clears that override immediately...
        cfg.set_nested("comfort", "desktop_surfaces", True)
        self.assertTrue(cfg.section("comfort")["desktop_surfaces"])
        # ...without clearing unrelated overrides or leaking them to disk.
        self.assertTrue(cfg.section("comfort")["reduced_motion"])
        self.assertEqual(cfg.get("mode"), "still")
        reloaded = ConfigManager(self.tmp_path / "safe_cfg.json")
        self.assertFalse(reloaded.section("comfort")["reduced_motion"])
        self.assertEqual(reloaded.get("mode"), "wander")

    def test_recovery_write_marker_retries_transient_permission_error(self) -> None:
        from app.recovery import CrashRecovery

        marker = self.tmp_path / "session_recovery.json"
        rec = CrashRecovery(marker, self.tmp_path / "crashes", version="3.1", clock=lambda: 100.0)
        attempts = {"n": 0}
        real_replace = Path.replace

        def flaky_replace(self_path: Path, target: Path):
            attempts["n"] += 1
            if attempts["n"] <= 2 and self_path.suffix == ".tmp":
                raise PermissionError(13, "WinError 5 transient lock")
            return real_replace(self_path, target)

        with patch.object(Path, "replace", flaky_replace):
            rec._write_marker({"active": True, "session_id": "ok"})
        self.assertEqual(attempts["n"], 3)
        self.assertTrue(marker.is_file())

    def test_panel_climb_guides_user_when_desktop_surfaces_disabled(self) -> None:
        self.pet.surface_tracker.set_enabled(False)
        spoken: list[str] = []
        self.pet.say = lambda text, **_kw: spoken.append(text)  # type: ignore[assignment]
        self.pet._panel_climb(sit_after=True)
        self.assertEqual(len(spoken), 1)
        self.assertIn("窗口落脚", spoken[0])

    def test_panel_set_title_refreshes_header_cleanly(self) -> None:
        panel = self.pet.control_panel
        panel.popup_near_pet(self.pet.frameGeometry())
        panel.set_title("Claude")
        self.assertEqual(panel.title_label.text(), "Claude")
        panel.set_title("Argon")
        self.assertEqual(panel.title_label.text(), "Argon")


if __name__ == "__main__":
    unittest.main()
