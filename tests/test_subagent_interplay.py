from __future__ import annotations

import os
import random
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QContextMenuEvent, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from agy.telemetry import LiveSnapshot, SubagentInfo
from animation.clip import PetAction
from app.paths import AppPaths
from pet.particles import ParticleSystem
from pet.subagent_clones import (
    HANDOFF_DURATION_SECONDS,
    CloneEvent,
    SubagentCloneManager,
)
from pet.window import PetWindow
from settings.config import ConfigManager

ROOT = Path(__file__).resolve().parents[1]


class _FakeScreen:
    def __init__(self, rect: QRect) -> None:
        self._rect = QRect(rect)

    def availableGeometry(self) -> QRect:
        return QRect(self._rect)


def _mouse(
    etype: QEvent.Type,
    local: QPointF,
    glob: QPointF,
    button: Qt.MouseButton = Qt.MouseButton.LeftButton,
    buttons: Qt.MouseButton = Qt.MouseButton.LeftButton,
) -> QMouseEvent:
    return QMouseEvent(etype, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier)


class RelayParticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_emit_relay_flows_from_clone_side_into_host_and_paints(self) -> None:
        ps = ParticleSystem(random.Random(7))
        added_left = ps.emit_relay(from_side=-1, target_x=150.0, target_y=120.0, spread_w=120.0, accent="#c084fc")
        self.assertEqual(added_left, 6)
        self.assertTrue(all(p.x < 150.0 and p.vx > 0.0 for p in ps.particles))
        self.assertTrue(any(p.kind == "orb" for p in ps.particles))

        # Advance past staggered launch delays and verify QPainter renders orbs cleanly
        ps.update(0.25)
        img = QImage(300, 260, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        ps.paint(painter)
        painter.end()
        self.assertTrue(any(img.pixelColor(x, y).alpha() > 0 for x in range(0, 300, 4) for y in range(0, 260, 4)))

        # Right side flows leftward (vx < 0)
        ps.clear()
        added_right = ps.emit_relay(from_side=1, target_x=150.0, target_y=120.0, spread_w=120.0, accent="#ea580c")
        self.assertEqual(added_right, 6)
        self.assertTrue(all(p.x > 150.0 and p.vx < 0.0 for p in ps.particles))

        # Respects reduced_motion
        ps.clear()
        ps.reduced_motion = True
        self.assertEqual(ps.emit_relay(from_side=-1, target_x=150.0, target_y=120.0), 0)


class SubagentInterplayManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _make(self):
        events: list[CloneEvent] = []
        mgr = SubagentCloneManager(
            characters_root=ROOT,
            base_manifest=ROOT / "assets" / "manifests" / "actions_base.json",
            topmost=True,
            on_interaction=events.append,
            rng=random.Random(42),
        )
        return mgr, events

    def test_multi_action_frames_cached_across_five_forms(self) -> None:
        mgr, _ = self._make()
        try:
            for form in ("carbon", "hydergon", "neon", "argon", "claude"):
                for action in (PetAction.WORKING, PetAction.HAPPY, PetAction.CELEBRATE, PetAction.HEAD_PAT, PetAction.WAVE):
                    frames = mgr._mini_frames(form, mirrored=False, action=action)
                    self.assertGreaterEqual(len(frames), 1, (form, action))
                    self.assertFalse(frames[0].isNull(), (form, action))
        finally:
            mgr.close_all()

    def test_direct_mouse_click_double_click_right_click_and_drag_high_five(self) -> None:
        mgr, events = self._make()
        try:
            subs = [
                SubagentInfo("s1", "m1", "检查双屏裁剪与热区", "Gemini 4 Neon", "neon"),
                SubagentInfo("s2", "m1", "核对安全脱敏清单", "Claude 4.5 Sonnet", "claude"),
            ]
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=10.5, screen=screen)
            events.clear()  # Ignore initial summoned event

            w0, w1 = mgr.visible_widgets
            w0._click_debounce_ms = 25  # Fast deterministic debounce in unit test
            center_local = QPointF(w0.width() / 2.0, w0.height() / 2.0)
            center_global = QPointF(w0.frameGeometry().center())

            # 1. Single left click -> delayed until double-click window elapses, then triggers cheer
            w0.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, center_local, center_global))
            w0.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, center_local, center_global))
            self.assertEqual(events, [])  # Waiting for double-click window
            deadline = time.monotonic() + 0.3
            while not events and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertEqual([e.kind for e in events], ["clicked"])
            self.assertEqual(events[0].conversation_id, "s1")
            self.assertTrue(bool(w0.bubble_text))
            mgr.position_around(host, now=time.monotonic(), screen=screen)
            self.assertEqual(w0.current_action, PetAction.HEAD_PAT)

            # 2. Full Qt double-click sequence (press1 -> release1 -> dblclick -> release2)
            # MUST suppress the pending single-click and emit ONLY ["report"]!
            events.clear()
            w0.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, center_local, center_global))
            w0.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, center_local, center_global))
            w0.mouseDoubleClickEvent(_mouse(QEvent.Type.MouseButtonDblClick, center_local, center_global))
            w0.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, center_local, center_global))
            wait_until = time.monotonic() + 0.08
            while time.monotonic() < wait_until:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertEqual([e.kind for e in events], ["report"])
            self.assertIn("汇报", w0.bubble_text)

            # 2b. Hiding a clone cancels any pending debounced single-click
            events.clear()
            w0.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, center_local, center_global))
            w0.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, center_local, center_global))
            w0.hide()
            wait_until = time.monotonic() + 0.08
            while time.monotonic() < wait_until:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertEqual(events, [])
            w0.show()

            # 3. Right click -> group dance cheer across all clones
            events.clear()
            w1.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(20, 20), QPoint(20, 20)))
            self.assertEqual([e.kind for e in events], ["group_cheer"])
            mgr.position_around(host, now=time.monotonic(), screen=screen)
            self.assertEqual(w0.current_action, PetAction.PLAY_DANCE)
            self.assertEqual(w1.current_action, PetAction.PLAY_DANCE)

            # 4. Drag clone close to host and drop -> mutual high_five!
            events.clear()
            start_g = QPointF(w0.frameGeometry().center())
            host_g = QPointF(host.center())
            w0.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, center_local, start_g))
            w0.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, center_local, host_g))
            self.assertTrue(w0.dragging)
            w0.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, center_local, host_g))
            self.assertFalse(w0.dragging)
            self.assertEqual([e.kind for e in events], ["high_five"])

            # 5. Drag clone far away and drop -> no high_five, glides back cleanly
            events.clear()
            far_g = QPointF(100.0, 100.0)
            start_g2 = QPointF(w0.frameGeometry().center())
            w0.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, center_local, start_g2))
            w0.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, center_local, far_g))
            w0.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, center_local, far_g))
            self.assertEqual(events, [])
            self.assertIn("干活", w0.bubble_text)
        finally:
            mgr.close_all()

    def test_host_mood_resonance_single_speaker_and_cooldown(self) -> None:
        mgr, _ = self._make()
        try:
            subs = [
                SubagentInfo("s1", "m1", "任务A", "Gemini 4 Neon", "neon"),
                SubagentInfo("s2", "m1", "任务B", "Claude 4.5 Sonnet", "claude"),
            ]
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=10.5, screen=screen)
            for w in mgr.visible_widgets:
                w.clear_bubble()

            # Host gets head-patted -> clones enter HAPPY, only 1 clone speaks (no shouting overlap)
            self.assertTrue(mgr.notify_host_action(PetAction.HEAD_PAT, now=20.0))
            # Immediate repeat within 5.5s cooldown is ignored
            self.assertFalse(mgr.notify_host_action(PetAction.HEAD_PAT, now=21.0))

            mgr.position_around(host, now=20.2, screen=screen)
            speakers = [w for w in mgr.visible_widgets if w.bubble_text]
            self.assertEqual(len(speakers), 1)
            for w in mgr.visible_widgets:
                self.assertEqual(w.current_action, PetAction.HAPPY)

            # After pose expires, clones naturally return to WORKING typing
            mgr.position_around(host, now=25.0, screen=screen)
            for w in mgr.visible_widgets:
                self.assertEqual(w.current_action, PetAction.WORKING)
        finally:
            mgr.close_all()

    def test_handoff_departure_lifecycle_and_immediate_cleanup_on_hide_or_dock(self) -> None:
        mgr, events = self._make()
        try:
            subs = [SubagentInfo("s1", "m1", "分析日志", "Gemini 4 Neon", "neon")]
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=10.5, screen=screen)
            events.clear()

            # Subagent finishes -> active_count drops to 0 immediately, departing handoff plays!
            mgr.sync([], default_form="carbon", enabled=True, host_visible=True, now=12.0)
            self.assertEqual(mgr.active_count, 0)
            self.assertTrue(mgr.has_departing)
            self.assertEqual(len(mgr.departing_widgets), 1)
            self.assertEqual([e.kind for e in events], ["handoff"])
            self.assertEqual(events[0].conversation_id, "s1")

            # Mid-flight tick keeps departing clone animating toward host
            mgr.position_around(host, now=12.4, screen=screen)
            self.assertTrue(mgr.has_departing)

            # Past handoff duration -> departing clone finishes & cleans up
            mgr.position_around(host, now=12.0 + HANDOFF_DURATION_SECONDS + 0.1, screen=screen)
            self.assertFalse(mgr.has_departing)
            self.assertEqual(len(mgr.departing_widgets), 0)

            # Docking clears any in-flight departing clone immediately
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=20.0)
            mgr.position_around(host, now=20.5, screen=screen)
            mgr.sync([], default_form="carbon", enabled=True, host_visible=True, now=21.0)
            self.assertTrue(mgr.has_departing)
            mgr.position_around(host, now=21.1, screen=screen, dock_edge="right")
            self.assertFalse(mgr.has_departing)
            self.assertEqual(len(mgr.all_visible_widgets), 0)
        finally:
            mgr.close_all()

    def test_periodic_relay_fires_after_interval_and_paints_widget_bubbles(self) -> None:
        mgr, events = self._make()
        try:
            subs = [SubagentInfo("s1", "m1", "重构状态机", "Gemini 4 Argon", "argon")]
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=10.5, screen=screen)
            events.clear()

            # Advance past max relay interval -> triggers automatic collaborative relay
            mgr.position_around(host, now=35.0, screen=screen)
            self.assertEqual([e.kind for e in events], ["relay"])
            w = mgr.visible_widgets[0]
            self.assertTrue(bool(w.bubble_text))
            # Verify clone widget paints cleanly with bubble, badge, and particles
            pix = w.grab()
            self.assertFalse(pix.isNull())
        finally:
            mgr.close_all()

    def test_clone_lines_call_host_jiejie_without_jargon(self) -> None:
        mgr, _events = self._make()
        try:
            subs = [SubagentInfo("s1", "m1", "核对逻辑", "Gemini 4 Neon", "neon")]
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            mgr.sync(subs, default_form="hydergon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=10.5, screen=screen)
            w = mgr.visible_widgets[0]
            self.assertIn("拖给姐姐击掌", w.toolTip())
            self.assertNotIn("主宠", w.toolTip())
            mgr.notify_host_action(PetAction.SLEEPING, now=20.0)
            self.assertEqual(w.bubble_text, "嘘，姐姐睡着啦～")

            mgr.sync(subs, default_form="neon", enabled=True, host_visible=True, now=25.0)
            self.assertIn("拖给姐姐击掌", w.toolTip())
            mgr.notify_host_action(PetAction.PERCH_SLEEP, now=30.0)
            self.assertEqual(w.bubble_text, "嘘，姐姐打盹中～")
        finally:
            mgr.close_all()

    def test_new_clone_interactions_drag_buddy_rub_trick_gift_chat_and_organic_idle(self) -> None:
        mgr, events = self._make()
        try:
            subs = [
                SubagentInfo("idle-play-a", "idle-play", "晒太阳发呆", "闲时随机玩伴", "neon"),
                SubagentInfo("idle-play-b", "idle-play", "喝下午茶", "闲时随机玩伴", "hydergon"),
                SubagentInfo("idle-play-c", "idle-play", "数星星", "闲时随机玩伴", "claude"),
            ]
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=11.0, screen=screen)
            events.clear()

            # 1. Head rub -> PET_PURR + pet_rub event
            ev_rub = mgr.trigger_pet_rub(0, now=12.0)
            assert ev_rub is not None
            self.assertEqual(ev_rub.kind, "pet_rub")
            mgr.position_around(host, now=12.1, screen=screen)
            self.assertEqual(mgr.visible_widgets[0].current_action, PetAction.PET_PURR)

            # 2. Wheel trick -> lively pose + trick event
            ev_trick = mgr.trigger_spin_trick(1, now=13.0)
            assert ev_trick is not None
            self.assertEqual(ev_trick.kind, "trick")

            # 3. Gift share -> QUOTA_GIFT + gift_share event with 姐姐 line
            ev_gift = mgr.trigger_gift_share(2, now=14.0)
            assert ev_gift is not None
            self.assertEqual(ev_gift.kind, "gift_share")
            self.assertTrue(bool(mgr.visible_widgets[2].bubble_text))

            # 4. Drag clone 0 onto clone 1 (away from host) -> clone_buddy high-five!
            w0, w1 = mgr.visible_widgets[0], mgr.visible_widgets[1]
            mgr._handle_widget_drag_start(w0)
            mgr._handle_widget_drag_end(w0, w1.frameGeometry().center())
            self.assertEqual(events[-1].kind, "clone_buddy")

            # 5. Clone-to-clone chat -> both clones speak
            ev_chat = mgr.trigger_clone_chat(0, 1, now=16.0)
            assert ev_chat is not None
            self.assertEqual(ev_chat.kind, "clone_chat")
            self.assertTrue(bool(w0.bubble_text))
            self.assertTrue(bool(w1.bubble_text))

            # 6. Organic playmate idle cycles across varied poses over time
            seen_actions: set[PetAction] = set()
            for step in range(30):
                mgr.position_around(host, now=20.0 + step * 1.4, screen=screen)
                seen_actions.add(mgr.visible_widgets[0].current_action)
            self.assertGreaterEqual(len(seen_actions), 3, f"Expected varied idle poses, got {seen_actions}")

            # 7. Real subagent transitions from WORKING into semantic title pose after settle
            work_subs = [SubagentInfo("work-1", "m1", "分析慢查询日志", "Gemini 4 Argon", "argon")]
            mgr.sync(work_subs, default_form="carbon", enabled=True, host_visible=True, now=100.0, silent_depart=True)
            mgr.position_around(host, now=101.0, screen=screen)
            self.assertEqual(mgr.visible_widgets[0].current_action, PetAction.WORKING)
            mgr.position_around(host, now=104.2, screen=screen)
            self.assertEqual(mgr.visible_widgets[0].current_action, PetAction.WORK_SEARCHING)
        finally:
            mgr.close_all()

    def test_six_clones_stay_close_to_host_and_never_stack_even_near_screen_edge(self) -> None:
        mgr, _events = self._make()
        try:
            subs = [
                SubagentInfo(f"idle-play-{i}", "idle-play", f"活动{i}", "闲时随机玩伴", fid)
                for i, fid in enumerate(("neon", "hydergon", "argon", "claude", "carbon", "neon"))
            ]
            area = QRect(0, 0, 1920, 1040)
            screen = _FakeScreen(area)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)

            # Check both center-of-screen and right-edge-pinched (exact screenshot scenario!)
            for label, host in (
                ("center", QRect(820, 520, 260, 255)),
                ("right_edge", QRect(1600, 520, 260, 255)),
                ("left_edge", QRect(20, 520, 260, 255)),
            ):
                mgr.position_around(host, now=12.0, reduced_motion=True, screen=screen)
                widgets = mgr.visible_widgets
                self.assertEqual(len(widgets), 6, label)
                host_left, host_right, host_vis = mgr._host_visual_bounds(host)
                vrects = [
                    mgr._clone_visual_rect(w.x(), w.y(), w.width(), w.height(), *w.visual_sprite_size)
                    for w in widgets
                ]
                # 1. Zero pairwise visual overlap among all 6 clones and between clones & host
                for i, vr in enumerate(vrects):
                    self.assertFalse(vr.intersects(host_vis), f"{label}: clone {i} overlapped host {vr} vs {host_vis}")
                    for j in range(i + 1, len(vrects)):
                        self.assertFalse(vr.intersects(vrects[j]), f"{label}: clones {i}&{j} stacked {vr} vs {vrects[j]}")
                # 2. Innermost clone sits cozily close to host visual body (<= 24px gap, never a 100px canyon!)
                min_edge_gap = min(
                    min(abs(host_left - vr.right()), abs(vr.left() - host_right))
                    for vr in vrects
                )
                self.assertLessEqual(min_edge_gap, 24, f"{label}: innermost clone too far ({min_edge_gap}px)")
        finally:
            mgr.close_all()


class PetWindowSubagentInterplayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="agy-subagent-interplay-")
        paths = AppPaths(app_dir=Path(self._tmp.name), bundle_dir=ROOT)
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
        self.pet.subagent_clones.close_all()
        self.pet.control_panel.hide()
        self.pet.food_panel.hide()
        self.pet.tray.hide()
        self.pet.hide()
        self.pet.close()
        self.app.processEvents()
        self._tmp.cleanup()

    def test_host_and_clones_interact_bidirectionally_with_state_safety(self) -> None:
        subs = [
            SubagentInfo("sub-a", "main", "检索接口调用", "Gemini 4 Neon", "neon"),
            SubagentInfo("sub-b", "main", "审核边界用例", "Claude 4.5 Sonnet", "claude"),
        ]
        snap = LiveSnapshot(source="pet_live", conversation_id="main", active_subagents=subs)
        self.pet._sync_subagent_clones(snap)
        self.assertEqual(self.pet.subagent_clones.active_count, 2)

        # 1. Click clone -> host gets happy + hearts + playful reply (no recursive loop!)
        self.pet.particles.clear()
        self.pet.subagent_clones.trigger_click(0)
        self.assertEqual(self.pet.action_machine.current, PetAction.HAPPY)
        self.assertTrue(self.pet.particles.active)
        self.assertIn("Neon", self.pet.bubble.text)

        # 2. High-five -> host plays HIGH_FIVE with confetti + hearts + relay orbs
        self.pet.particles.clear()
        self.pet.subagent_clones.trigger_high_five(1)
        self.assertEqual(self.pet.action_machine.current, PetAction.HIGH_FIVE)
        self.assertIn("Claude", self.pet.bubble.text)
        self.assertTrue(any(p.kind == "orb" for p in self.pet.particles.particles))

        # 3. Report -> host waves + acknowledges task title
        self.pet.subagent_clones.trigger_report(0)
        self.assertEqual(self.pet.action_machine.current, PetAction.WAVE)
        self.assertIn("检索接口调用", self.pet.bubble.text)

        # 3b. Group cheer -> host & clones sync PLAY_DANCE!
        self.pet.subagent_clones.trigger_group_cheer()
        self.assertEqual(self.pet.action_machine.current, PetAction.PLAY_DANCE)

        # 4. State safety: while host is sulking, clone interactions do NOT override SULK
        self.pet._sulk_until = time.monotonic() + 25.0
        self.pet._request_action(PetAction.SULK, reason="test_sulk", force=True, immediate=True)
        self.pet.subagent_clones.trigger_click(0)
        self.assertEqual(self.pet.action_machine.current, PetAction.SULK)

        # 5. Host action -> clones react sympathetically (SULK -> WAVE soothing)
        self.pet._sulk_until = 0.0
        self.pet._request_action(PetAction.EATING, reason="test_eat", force=True, immediate=True)
        self.pet.subagent_clones.position_around(
            self.pet._sprite_rect(),
            now=time.monotonic(),
            reduced_motion=False,
            screen=self.pet._screen_for_pet(),
        )
        self.assertTrue(all(w.current_action == PetAction.WAVE for w in self.pet.subagent_clones.visible_widgets))

        # 6. Handoff when subagents complete -> host waves & thanks clone
        self.pet._request_action(PetAction.IDLE, reason="test_idle", force=True, immediate=True)
        empty_snap = LiveSnapshot(source="pet_live", conversation_id="main", active_subagents=[])
        self.pet._sync_subagent_clones(empty_snap)
        self.assertEqual(self.pet.subagent_clones.active_count, 0)
        self.assertTrue(self.pet.subagent_clones.has_departing)
        self.assertEqual(self.pet.action_machine.current, PetAction.WAVE)
        self.assertTrue(any(name in self.pet.bubble.text for name in ("Neon", "Claude")))

    def test_idle_playmates_random_forms_playful_poses_and_real_subagent_preemption(self) -> None:
        # Summoning multiple times picks random forms across all 5 forms (not bound to host form!)
        self.pet.set_form("carbon", manual=True, announce=False, persist=False)
        self.pet._request_action(PetAction.IDLE, reason="test_idle", force=True, immediate=True)
        seen_forms: set[str] = set()
        for _ in range(15):
            mates = self.pet.summon_idle_playmates(count=2, now=100.0, duration=20.0, announce=False)
            self.assertEqual(len(mates), 2)
            self.assertNotEqual(mates[0].form_id, mates[1].form_id)
            seen_forms.update(m.form_id for m in mates)
        self.assertGreaterEqual(len(seen_forms), 4)

        # Playmates use playful poses (PLAY_DANCE/HAPPY/WAVE/IDLE, NOT WORKING typing!)
        mates = self.pet.summon_idle_playmates(count=2, now=200.0, duration=15.0, announce=True)
        self.assertEqual(self.pet.subagent_clones.active_count, 2)
        self.pet.subagent_clones.position_around(
            self.pet._sprite_rect(),
            now=201.2,
            reduced_motion=False,
            screen=self.pet._screen_for_pet(),
        )
        # Playmates use organic playful/idle poses (NOT WORKING typing!)
        import pet.subagent_clones as sc

        for w in self.pet.subagent_clones.visible_widgets:
            self.assertIn(w.current_action, set(sc._PLAY_IDLE_POSES))
            self.assertNotEqual(w.current_action, PetAction.WORKING)

        # Clicking a playmate extends playtime and emits is_playmate=True
        ev = self.pet.subagent_clones.trigger_click(0, now=210.0)
        self.assertIsNotNone(ev)
        self.assertTrue(ev.is_playmate)
        self.assertGreaterEqual(self.pet._idle_play_until, 215.0)

        # Autonomous tick summons playmates when idle & due, and dismisses when expired or when AGY runs
        self.pet.dismiss_idle_playmates(now=220.0)
        self.assertEqual(self.pet.subagent_clones.active_count, 0)
        self.pet._request_action(PetAction.IDLE, reason="test_idle_auto", force=True, immediate=True)
        self.pet.telemetry.last_snapshot = LiveSnapshot(
            source="pet_live",
            conversation_id="main",
            status="CASCADE_RUN_STATUS_IDLE",
        )
        self.pet._idle_play_next_at = 300.0
        self.pet._tick_idle_playmates(301.0)
        self.assertGreaterEqual(self.pet.subagent_clones.active_count, 1)

        # Real subagent arriving immediately preempts idle playmates cleanly
        real_snap = LiveSnapshot(
            source="pet_live",
            conversation_id="main",
            status="CASCADE_RUN_STATUS_RUNNING",
            active_subagents=[SubagentInfo("real-1", "main", "跑单测", "Gemini 4 Neon", "neon")],
        )
        self.pet.telemetry.last_snapshot = real_snap
        self.pet._sync_subagent_clones(real_snap)
        self.assertEqual(self.pet._idle_play_clones, [])
        self.assertEqual(self.pet.subagent_clones.active_count, 1)
        self.assertEqual(self.pet.subagent_clones._entries[0][0].conversation_id, "real-1")

    def test_clone_mini_bubbles_never_elide_built_in_lines(self) -> None:
        from PySide6.QtGui import QFontMetrics
        import pet.subagent_clones as sc

        self.pet.summon_idle_playmates(count=1, now=400.0, duration=20.0, announce=False)
        widget = self.pet.subagent_clones.visible_widgets[0]
        fm = QFontMetrics(widget._bubble_font)
        max_w = max(44, widget.width() - 14)
        all_lines = (
            *sc._SUMMON_LINES,
            *sc._CLICK_LINES,
            *sc._RELAY_LINES,
            *sc._HANDOFF_LINES,
            *sc._HIGH_FIVE_LINES,
            *sc._GROUP_CHEER_LINES,
            *sc._PLAY_SUMMON_LINES,
            *sc._PLAY_CLICK_LINES,
            *sc._PLAY_RELAY_LINES,
            *sc._PLAY_HANDOFF_LINES,
            *sc._PLAY_HIGH_FIVE_LINES,
            *sc._PLAY_GROUP_CHEER_LINES,
            *sc._PET_RUB_LINES,
            *sc._TRICK_LINES,
            *sc._GIFT_SHARE_LINES,
            *sc._CLONE_BUDDY_LINES,
            *(line for pair in sc._CLONE_CHAT_PAIRS for line in pair),
            *(line for pair in sc._WORK_CHAT_PAIRS for line in pair),
            *(line for _a, _d, _p, lines in sc._HOST_MOOD_RESPONSES.values() for line in lines),
        )
        for line in all_lines:
            rendered = sc._format_host_line(line, sc.HOST_CALL_NAME)
            self.assertNotIn("主宠", rendered)
            elided = fm.elidedText(rendered, Qt.TextElideMode.ElideRight, max_w)
            self.assertEqual(elided, rendered, f"Mini bubble truncated ({widget.width()}px): {rendered!r} -> {elided!r}")

    def test_random_playmates_scale_up_to_six_and_window_handles_new_events(self) -> None:
        from pet.subagent_clones import MAX_VISIBLE_CLONES

        self.assertEqual(MAX_VISIBLE_CLONES, 6)
        counts = set()
        for idx in range(25):
            mates = self.pet.summon_idle_playmates(now=500.0 + idx, duration=25.0, announce=False)
            counts.add(len(mates))
            self.assertGreaterEqual(len(mates), 2)
            self.assertLessEqual(len(mates), 5)
        self.assertTrue(any(c >= 4 for c in counts), f"Expected larger random squads, got {counts}")

        # summon_or_add_playmates grows squad up to MAX_VISIBLE_CLONES (6)
        self.pet.summon_idle_playmates(count=3, now=600.0, duration=25.0, announce=False)
        self.pet.summon_or_add_playmates(now=601.0, add_count=2)
        self.assertEqual(self.pet.subagent_clones.active_count, 5)
        self.pet.summon_or_add_playmates(now=602.0, add_count=2)
        self.assertEqual(self.pet.subagent_clones.active_count, MAX_VISIBLE_CLONES)

        # New clone events animate PetWindow cleanly
        self.pet.subagent_clones.trigger_gift_share(0, now=603.0)
        self.assertEqual(self.pet.action_machine.current, PetAction.QUOTA_GIFT)
        self.pet.subagent_clones.trigger_spin_trick(1, now=604.0)
        self.assertEqual(self.pet.action_machine.current, PetAction.CELEBRATE)
        self.pet.subagent_clones.trigger_pet_rub(2, now=605.0)
        self.assertEqual(self.pet.action_machine.current, PetAction.HAPPY)
        self.pet.subagent_clones.trigger_clone_buddy(0, 1, now=606.0)
        self.assertEqual(self.pet.action_machine.current, PetAction.HAPPY)

        # Manual "唤玩伴" summon must NOT immediately play departure while AGY is running or pet was sleeping
        self.pet.dismiss_idle_playmates(now=700.0)
        self.pet.subagent_clones._clear_departing()
        self.pet.telemetry.last_snapshot = LiveSnapshot(
            source="pet_live",
            conversation_id="main",
            status="CASCADE_RUN_STATUS_RUNNING",
            active_subagents=[],
        )
        self.pet._request_action(PetAction.SLEEPING, reason="test_sleep", force=True, immediate=True)
        mates = self.pet.summon_or_add_playmates(now=705.0)
        self.assertGreaterEqual(len(mates), 2)
        self.assertFalse(self.pet.subagent_clones.has_departing)
        self.pet._tick_idle_playmates(705.05)
        self.assertEqual(self.pet.subagent_clones.active_count, len(mates))
        self.assertFalse(self.pet.subagent_clones.has_departing)
        # Clicking again appends without departing existing playmates
        prev_count = self.pet.subagent_clones.active_count
        self.pet.summon_or_add_playmates(now=706.0, add_count=1)
        self.assertEqual(self.pet.subagent_clones.active_count, min(MAX_VISIBLE_CLONES, prev_count + 1))
        self.assertFalse(self.pet.subagent_clones.has_departing)

    def test_cinematic_summon_pop_and_two_stage_depart_poof_animation(self) -> None:
        events: list[CloneEvent] = []
        mgr = SubagentCloneManager(
            characters_root=ROOT,
            base_manifest=ROOT / "assets" / "manifests" / "actions_base.json",
            topmost=True,
            on_interaction=events.append,
            rng=random.Random(99),
        )
        try:
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            subs = [SubagentInfo("sub-pop", "main", "查文档", "Gemini 4 Neon", "neon")]
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=50.0)

            # Early entrance (t=0.08s): SUMMON_POP pose + elastic scale < 1.0 + upward arc
            mgr.position_around(host, now=50.08, reduced_motion=False, screen=screen)
            w = mgr.visible_widgets[0]
            self.assertEqual(w.current_action, PetAction.SUMMON_POP)
            self.assertLess(w.render_scale, 0.90)
            early_y = w.y()

            # Mid-entrance (t=0.34s): elastic overshoot scale > 1.0
            mgr.position_around(host, now=50.34, reduced_motion=False, screen=screen)
            self.assertGreater(w.render_scale, 1.0)

            # Settled (t=0.80s): scale returns to 1.0, switches cleanly to WORKING typing
            mgr.position_around(host, now=50.80, reduced_motion=False, screen=screen)
            self.assertAlmostEqual(w.render_scale, 1.0, places=2)
            self.assertEqual(w.current_action, PetAction.WORKING)
            self.assertGreaterEqual(w.y(), early_y)

            # Exit: 2-stage DEPART_POOF (Stage 1 wave hop -> Stage 2 shrinking arc -> depart_complete)
            events.clear()
            mgr.sync([], default_form="carbon", enabled=True, host_visible=True, now=52.0)
            self.assertEqual([e.kind for e in events], ["handoff"])
            dep_w = mgr.departing_widgets[0]

            # Stage 1 (t=0.18s): upbeat anticipation scale >= 1.0, DEPART_POOF pose
            mgr.position_around(host, now=52.18, reduced_motion=False, screen=screen)
            self.assertEqual(dep_w.current_action, PetAction.DEPART_POOF)
            self.assertGreaterEqual(dep_w.render_scale, 1.0)

            # Stage 2 (t=0.95s): shrinking back toward host + summon poof emitted
            mgr.position_around(host, now=52.95, reduced_motion=False, screen=screen)
            self.assertLess(dep_w.render_scale, 0.75)

            # Complete (t=1.35s): cleaned up + depart_complete emitted to trigger host catch ring!
            mgr.position_around(host, now=53.35, reduced_motion=False, screen=screen)
            self.assertFalse(mgr.has_departing)
            self.assertIn("depart_complete", [e.kind for e in events])

            # Also verify ParticleSystem "summon" burst emits ring + orbs/sparkles
            ps = ParticleSystem(random.Random(5))
            added = ps.emit("summon", origin_x=100.0, origin_y=100.0)
            self.assertEqual(added, 9)
            self.assertTrue(any(p.kind == "ring" for p in ps.particles))
            self.assertTrue(any(p.kind == "orb" for p in ps.particles))
        finally:
            mgr.close_all()


if __name__ == "__main__":
    unittest.main()
