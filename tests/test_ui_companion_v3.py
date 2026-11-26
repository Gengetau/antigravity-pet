from __future__ import annotations

import os
import random
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect

from agy.characters import FORMS
from agy.hud_bar import APPEARANCES, TAIL, HudBar
from agy.reactions import ReactionTracker
from agy.telemetry import LiveSnapshot, SubagentInfo
from animation.clip import PetAction
from pet.subagent_clones import (
    CLONE_PHASE_STEP_SECONDS,
    FRAME_INTERVAL_SECONDS,
    SubagentCloneManager,
)
from settings.panel import PetControlPanel

ROOT = Path(__file__).resolve().parents[1]


class _FakeScreen:
    def __init__(self, rect: QRect) -> None:
        self._rect = QRect(rect)

    def availableGeometry(self) -> QRect:
        return QRect(self._rect)


class SubagentClonesV31Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _manager(self) -> SubagentCloneManager:
        return SubagentCloneManager(
            characters_root=ROOT,
            base_manifest=ROOT / "assets" / "manifests" / "actions_base.json",
            topmost=True,
        )

    def test_4frame_typing_animation_stagger_mirror_and_reduced_motion(self) -> None:
        mgr = self._manager()
        try:
            # All 5 forms load 4 normal + 4 horizontally mirrored work_typing frames
            for form in ("carbon", "hydergon", "neon", "argon", "claude"):
                normal = mgr._mini_frames(form, mirrored=False)
                flipped = mgr._mini_frames(form, mirrored=True)
                self.assertEqual(len(normal), 4, f"{form} should cache 4 normal frames")
                self.assertEqual(len(flipped), 4, f"{form} should cache 4 mirrored frames")
                self.assertFalse(any(p.isNull() for p in normal))
                self.assertFalse(any(p.isNull() for p in flipped))
                # Verify horizontal mirroring actually flips pixels (not identical copy)
                img_n = normal[0].toImage()
                img_f = flipped[0].toImage()
                self.assertEqual(img_n.size(), img_f.size())
                self.assertNotEqual(bytes(img_n.constBits()), bytes(img_f.constBits()))

            subs = [
                SubagentInfo("s1", "m1", "查文档", "Gemini 4 Neon", "neon"),
                SubagentInfo("s2", "m1", "审代码", "Claude 4.5 Sonnet", "claude"),
            ]
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True)
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)

            seen_frames_0: set[int] = set()
            seen_frames_1: set[int] = set()
            for step in range(4):
                now = step * FRAME_INTERVAL_SECONDS + 0.01
                mgr.position_around(host, now=now, reduced_motion=False, screen=screen)
                w0, w1 = mgr.visible_widgets
                expected_0 = int((now + 0 * CLONE_PHASE_STEP_SECONDS) / FRAME_INTERVAL_SECONDS) % 4
                expected_1 = int((now + 1 * CLONE_PHASE_STEP_SECONDS) / FRAME_INTERVAL_SECONDS) % 4
                self.assertEqual(w0.frame_index, expected_0)
                self.assertEqual(w1.frame_index, expected_1)
                self.assertNotEqual(w0.frame_index, w1.frame_index)
                seen_frames_0.add(w0.frame_index)
                seen_frames_1.add(w1.frame_index)

                # Left clone sits cleanly left of host (mirrored=False), right clone right of host (mirrored=True)
                self.assertLess(w0.frameGeometry().center().x(), host.left())
                self.assertGreater(w1.frameGeometry().center().x(), host.right())
                self.assertFalse(w0.mirrored)
                self.assertTrue(w1.mirrored)
                self.assertEqual(
                    w0._pixmap.cacheKey(),
                    mgr._mini_frames("neon", mirrored=False)[expected_0].cacheKey(),
                )
                self.assertEqual(
                    w1._pixmap.cacheKey(),
                    mgr._mini_frames("claude", mirrored=True)[expected_1].cacheKey(),
                )

            self.assertEqual(seen_frames_0, {0, 1, 2, 3})
            self.assertEqual(seen_frames_1, {0, 1, 2, 3})

            # Reduced motion pins all clones to frame 0
            mgr.position_around(host, now=1.23, reduced_motion=True, screen=screen)
            for w in mgr.visible_widgets:
                self.assertEqual(w.frame_index, 0)
        finally:
            mgr.close_all()

    def test_host_dock_hides_clones_and_undock_restores_them(self) -> None:
        mgr = self._manager()
        try:
            subs = [
                SubagentInfo("s1", "m1", "查日志", "Gemini 4 Neon", "neon"),
                SubagentInfo("s2", "m1", "写测试", "Gemini 4 Argon", "argon"),
            ]
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True)
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(900, 500, 160, 200)

            mgr.position_around(host, now=1.0, screen=screen, dock_edge=None)
            self.assertEqual(mgr.active_count, 2)
            self.assertEqual(len(mgr.visible_widgets), 2)

            # Docking on right or left hides all clone widgets cleanly
            mgr.position_around(host, now=1.2, screen=screen, dock_edge="right")
            self.assertEqual(mgr.active_count, 2)
            self.assertEqual(len(mgr.visible_widgets), 0)

            mgr.position_around(host, now=1.4, screen=screen, dock_edge="left")
            self.assertEqual(len(mgr.visible_widgets), 0)

            # Undocking shows clones normally again
            mgr.position_around(host, now=1.6, screen=screen, dock_edge=None)
            self.assertEqual(len(mgr.visible_widgets), 2)
        finally:
            mgr.close_all()

    def test_window_close_button_and_screen_top_right_keepout_avoidance(self) -> None:
        mgr = self._manager()
        try:
            subs = [
                SubagentInfo("s1", "m1", "任务1", "Gemini 4 Neon", "neon"),
                SubagentInfo("s2", "m1", "任务2", "Claude 4.5 Sonnet", "claude"),
                SubagentInfo("s3", "m1", "任务3", "Gemini 4 Argon", "argon"),
                SubagentInfo("s4", "m1", "任务4", "Gemini 4 Carbon", "carbon"),
            ]
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True)
            area = QRect(0, 0, 1920, 1040)
            screen = _FakeScreen(area)

            # Case 1: Host perched near top-right of an app window (right clone would hit _ □ ×)
            perched_win = QRect(200, 140, 1100, 700)
            win_keepout = QRect(
                QPoint(perched_win.right() - 150, perched_win.top() - 28),
                QPoint(perched_win.right() + 12, perched_win.top() + 68),
            )
            host_on_win = QRect(perched_win.right() - 250, perched_win.top() - 140, 140, 180)
            for t in (0.0, 0.5, 1.1, 2.3):
                mgr.position_around(
                    host_on_win,
                    now=t,
                    screen=screen,
                    perched_window_rect=perched_win,
                )
                self.assertEqual(len(mgr.visible_widgets), 4)
                for w in mgr.visible_widgets:
                    self.assertFalse(
                        w.geometry().intersects(win_keepout),
                        f"Clone {w.geometry()} overlapped window controls {win_keepout} at t={t}",
                    )

            # Case 2: Host near screen top-right (maximized window _ □ ×, no perched_window_rect)
            screen_top_right = QRect(
                QPoint(area.right() - 150, area.top()),
                QPoint(area.right(), area.top() + 56),
            )
            host_top_right = QRect(area.right() - 220, area.top() + 10, 140, 180)
            for t in (0.0, 0.7, 1.9):
                mgr.position_around(host_top_right, now=t, screen=screen, perched_window_rect=None)
                for w in mgr.visible_widgets:
                    self.assertFalse(
                        w.geometry().intersects(screen_top_right),
                        f"Clone {w.geometry()} overlapped screen top-right {screen_top_right}",
                    )

            # Case 3: Host pinched near left edge where left slot can't fit and right hits keepout -> drops below
            narrow_win = QRect(0, 20, 260, 500)
            narrow_keepout = QRect(
                QPoint(narrow_win.right() - 150, narrow_win.top() - 28),
                QPoint(narrow_win.right() + 12, narrow_win.top() + 68),
            )
            host_left_pinched = QRect(10, 0, 110, 140)
            mgr.position_around(
                host_left_pinched,
                now=0.5,
                screen=screen,
                perched_window_rect=narrow_win,
            )
            for w in mgr.visible_widgets:
                self.assertFalse(
                    w.geometry().intersects(narrow_keepout),
                    f"Pinched clone {w.geometry()} overlapped keep-out {narrow_keepout}",
                )
        finally:
            mgr.close_all()


class ReactionSemanticsV31Tests(unittest.TestCase):
    def test_quota_critical_emits_tired_sweat_and_dedupes_boundary_jitter(self) -> None:
        tracker = ReactionTracker(random.Random(0), cooldown_seconds=60.0)
        t = 100.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", quota_remaining_pct=60.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )

        # Drop into critical band (<= 10%) -> TIRED + sweat (NOT ANGRY)
        t += 5.0
        reactions = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", quota_remaining_pct=8.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        crit = [r for r in reactions if r.kind == "quota_critical"]
        self.assertEqual(len(crit), 1)
        self.assertEqual(crit[0].action, PetAction.TIRED)
        self.assertNotEqual(crit[0].action, PetAction.ANGRY)
        self.assertEqual(crit[0].particle, "sweat")

        # Jitter across 10% boundary inside cooldown must not spam quota_critical
        t += 10.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", quota_remaining_pct=12.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        t += 10.0
        jitter = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", quota_remaining_pct=9.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        self.assertFalse(any(r.kind == "quota_critical" for r in jitter))

    def test_waiting_for_user_emits_waiting_user_with_cooldown_and_edge_trigger(self) -> None:
        tracker = ReactionTracker(random.Random(0), cooldown_seconds=60.0)
        t = 500.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", waiting_for_user=False),
            now=t,
            follow_model=False,
            current_form="carbon",
        )

        # Rising edge triggers WAITING_USER + alert
        t += 2.0
        r1 = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", waiting_for_user=True),
            now=t,
            follow_model=False,
            current_form="carbon",
        )
        waiting = [r for r in r1 if r.kind == "waiting"]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0].action, PetAction.WAITING_USER)
        self.assertEqual(waiting[0].particle, "alert")

        # Staying True does not re-trigger
        t += 70.0
        r_stay = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", waiting_for_user=True),
            now=t,
            follow_model=False,
            current_form="carbon",
        )
        self.assertFalse(any(r.kind == "waiting" for r in r_stay))

        # Falling then rising within 60s of last fire is suppressed; after >=60s fires again
        t = 510.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", waiting_for_user=False),
            now=t,
            follow_model=False,
            current_form="carbon",
        )
        t += 5.0
        r_soon = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", waiting_for_user=True),
            now=t,
            follow_model=False,
            current_form="carbon",
        )
        self.assertFalse(any(r.kind == "waiting" for r in r_soon))

        t += 65.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", waiting_for_user=False),
            now=t,
            follow_model=False,
            current_form="carbon",
        )
        t += 2.0
        r_after = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", waiting_for_user=True),
            now=t,
            follow_model=False,
            current_form="carbon",
        )
        self.assertTrue(any(r.kind == "waiting" and r.action == PetAction.WAITING_USER for r in r_after))


class HudSeamlessContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _hud(self, appearance: str) -> HudBar:
        hud = HudBar(
            settings={"hud_appearance": appearance, "hud_mode": "attached"},
            on_open_meter=lambda: None,
            on_refresh=lambda: None,
            on_pin=lambda _cid: None,
            on_hide=lambda: None,
        )
        hud.apply_appearance()
        return hud

    def test_seamless_mode_legible_over_white_and_no_card_regression(self) -> None:
        self.assertIn("rgba(15,23,42,", APPEARANCES["seamless"][1])
        self.assertIn("rgba(255,255,255,", APPEARANCES["seamless"][1])

        hud = self._hud("seamless")
        try:
            snap = LiveSnapshot(
                source="ls",
                title="可读性检查",
                status="CASCADE_RUN_STATUS_RUNNING",
                selected_model_label="Gemini 4 Neon (High)",
                latest_decode_tps=112.5,
                quota_remaining_pct=65.0,
                cache_hit_pct=89.0,
                context_used_tokens=150_000,
            )
            hud.update_snapshot(snap)
            hud.show()
            self.app.processEvents()

            self.assertTrue(hud.pill.isVisibleTo(hud))
            self.assertFalse(hud.card.isVisibleTo(hud))
            self.assertIsInstance(hud.speed.graphicsEffect(), QGraphicsDropShadowEffect)

            # Render seamless HUD onto pure white background and verify solid contrast
            img = QImage(hud.size(), QImage.Format.Format_ARGB32)
            img.fill(QColor(255, 255, 255))
            hud.render(img)
            total_px = img.width() * img.height()
            contrasting_px = sum(
                1
                for y in range(img.height())
                for x in range(img.width())
                if img.pixelColor(x, y).lightness() < 180
            )
            self.assertGreater(
                contrasting_px / max(1, total_px),
                0.55,
                "Seamless HUD must provide a readable dark-tinted pill over pure white backgrounds",
            )

            # Switch to dialog (card) mode -> zero regression, drop shadows cleared on pill labels
            hud.settings["hud_appearance"] = "dialog"
            hud.apply_appearance()
            hud.update_snapshot(snap)
            self.assertTrue(hud.card.isVisibleTo(hud))
            self.assertFalse(hud.pill.isVisibleTo(hud))
            self.assertIsNone(hud.speed.graphicsEffect())
            hud.follow_pet(QRect(400, 400, 160, 200), prefer_above=True)
            self.assertEqual(hud._tail_dir, "down")
            self.assertEqual(hud._outer.contentsMargins().bottom(), TAIL)
        finally:
            hud.hide()


class QuickControlPanelV31Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _build_panel(self, **overrides) -> PetControlPanel:
        kwargs = dict(
            on_mode=lambda _mode: None,
            on_size=lambda _size: None,
            on_feed=lambda: None,
            on_say=lambda: None,
            on_snap=lambda: None,
            on_awareness=lambda _enabled: None,
            on_read_window_title=lambda _enabled: None,
            on_idle_detection=lambda _enabled: None,
            on_topmost=lambda _enabled: None,
            on_fullscreen_hide=lambda _enabled: None,
            on_passthrough=lambda _enabled: None,
            on_autostart=lambda _enabled: None,
            on_activity_level=lambda _level: None,
            on_walk_speed=lambda _speed: None,
            on_reduced_motion=lambda _enabled: None,
            on_hover_pause=lambda _enabled: None,
            on_desktop_surfaces=lambda _enabled: None,
            on_action=lambda _action: None,
            on_hide=lambda: None,
            on_privacy=lambda: None,
            on_quit=lambda: None,
            forms=tuple((f.id, f.name) for f in FORMS),
        )
        kwargs.update(overrides)
        return PetControlPanel(**kwargs)

    def test_promoted_primary_buttons_and_optional_callback_wiring(self) -> None:
        calls: list[str] = []
        panel = self._build_panel(
            on_action=lambda act: calls.append(f"action:{act}"),
            on_dock=lambda: calls.append("dock"),
            on_perch=lambda: calls.append("perch"),
            on_recall_primary=lambda: calls.append("recall"),
            on_snap=lambda: calls.append("snap"),
        )
        try:
            panel.show()
            self.app.processEvents()
            # All 4 spatial buttons must be visible in the collapsed primary area
            self.assertFalse(panel._advanced.isVisibleTo(panel))
            for btn, expected_text in (
                (panel.dock_button, "贴边"),
                (panel.climb_button, "爬窗"),
                (panel.perch_button, "坐沿"),
                (panel.recall_button, "召回主屏"),
            ):
                self.assertEqual(btn.text(), expected_text)
                self.assertTrue(btn.isVisibleTo(panel))

            panel.dock_button.click()
            panel.climb_button.click()
            panel.perch_button.click()
            panel.recall_button.click()
            self.assertEqual(calls, ["dock", "action:CLIMB", "perch", "recall"])
        finally:
            panel.hide()

    def test_optional_callbacks_fallback_gracefully_when_omitted(self) -> None:
        calls: list[str] = []
        panel = self._build_panel(
            on_action=lambda act: calls.append(f"action:{act}"),
            on_snap=lambda: calls.append("snap"),
        )
        try:
            panel.dock_button.click()
            panel.perch_button.click()
            panel.recall_button.click()
            self.assertEqual(calls, ["action:EDGE_DOCK", "action:EDGE_SIT", "snap"])
        finally:
            panel.hide()

    def test_expanded_panel_stays_compact_under_660px(self) -> None:
        panel = self._build_panel()
        try:
            panel.show()
            self.app.processEvents()
            collapsed_h = panel.height()
            self.assertLessEqual(panel.width(), 258)

            panel._toggle_advanced()
            self.app.processEvents()
            panel._fit_to_content()
            self.app.processEvents()
            expanded_h = panel.height()

            self.assertGreater(expanded_h, collapsed_h)
            self.assertLessEqual(panel.width(), 258)
            self.assertLessEqual(
                expanded_h,
                660,
                f"Expanded panel height {expanded_h}px exceeds compact budget of 660px",
            )

            # Re-collapsing shrinks cleanly back to collapsed height
            panel._toggle_advanced()
            self.app.processEvents()
            panel._fit_to_content()
            self.app.processEvents()
            self.assertLessEqual(panel.height(), collapsed_h)
        finally:
            panel.hide()


if __name__ == "__main__":
    unittest.main()
