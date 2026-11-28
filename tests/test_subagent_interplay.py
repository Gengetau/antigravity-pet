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

    def test_autonomous_clone_roaming_facing_catchup_and_proactive_visits(self) -> None:
        mgr, events = self._make()
        try:
            subs = [
                SubagentInfo("idle-play-r1", "idle-play", "晒太阳发呆", "闲时随机玩伴", "neon"),
                SubagentInfo("idle-play-r2", "idle-play", "数星星", "闲时随机玩伴", "hydergon"),
            ]
            area = QRect(0, 0, 1920, 1040)
            screen = _FakeScreen(area)
            host = QRect(860, 520, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=11.0, screen=screen)
            w0, w1 = mgr.visible_widgets[0], mgr.visible_widgets[1]
            start_x = w0.x()

            # 1. Free roam rightward -> PetAction.WALKING, mirrored=False (walk_side_right), moves toward target
            self.assertTrue(mgr.start_roam(0, now=15.0, target=(start_x + 190.0, float(w0.y()))))
            mgr.position_around(host, now=15.05, screen=screen)
            self.assertEqual(w0.current_action, PetAction.WALKING)
            self.assertFalse(w0.mirrored)
            self.assertGreater(w0.x(), start_x)

            # Free roam leftward -> PetAction.WALKING, mirrored=True (walk_side)
            mid_x = w0.x()
            self.assertTrue(mgr.start_roam(0, now=15.2, target=(mid_x - 220.0, float(w0.y()))))
            mgr.position_around(host, now=15.25, screen=screen)
            self.assertEqual(w0.current_action, PetAction.WALKING)
            self.assertTrue(w0.mirrored)
            self.assertLess(w0.x(), mid_x)

            # Finish walk -> settles into paused inside screen bounds & outside top-right keepout
            t = 15.30
            for _ in range(90):
                t += 0.05
                mgr.position_around(host, now=t, screen=screen)
            self.assertTrue(area.contains(w0.frameGeometry()))
            rt0 = mgr._runtime["idle-play-r1"]
            self.assertEqual(rt0.roam_mode, "paused")

            # 2. Host moves far away -> strolling clone automatically enters returning catch-up walk!
            far_host = QRect(1420, 520, 180, 220)
            t += 0.05
            mgr.position_around(far_host, now=t, screen=screen)
            self.assertEqual(rt0.roam_mode, "returning")
            self.assertEqual(w0.current_action, PetAction.WALKING)
            self.assertFalse(w0.mirrored)  # walking right toward far_host
            for _ in range(180):
                t += 0.05
                mgr.position_around(far_host, now=t, screen=screen)
                if rt0.roam_mode == "home":
                    break
            self.assertEqual(rt0.roam_mode, "home")

            # 3. Proactive visit to host -> walks up and fires high_five & gift_share on arrival
            events.clear()
            self.assertTrue(mgr.start_roam(0, now=t, target=(far_host.left() - 260.0, float(w0.y()))))
            for _ in range(60):
                t += 0.05
                mgr.position_around(far_host, now=t, screen=screen)
            self.assertTrue(mgr.start_visit_host(0, action="high_five", now=t))
            for _ in range(120):
                t += 0.05
                mgr.position_around(far_host, now=t, screen=screen)
                if any(e.kind == "high_five" for e in events):
                    break
            self.assertTrue(any(e.kind == "high_five" for e in events))

            events.clear()
            rt0.pose_action = None
            rt0.pose_until = 0.0
            self.assertTrue(mgr.start_visit_host(0, action="gift_share", now=t))
            for _ in range(120):
                t += 0.05
                mgr.position_around(far_host, now=t, screen=screen)
                if any(e.kind == "gift_share" for e in events):
                    break
            self.assertTrue(any(e.kind == "gift_share" for e in events))

            # 4. Proactive visit to sibling clone -> walks over and fires clone_buddy facing each other
            events.clear()
            rt0.pose_action = None
            rt0.pose_until = 0.0
            mgr._runtime["idle-play-r2"].pose_action = None
            mgr._runtime["idle-play-r2"].pose_until = 0.0
            self.assertTrue(mgr.start_visit_clone(0, 1, action="clone_buddy", now=t))
            for _ in range(140):
                t += 0.05
                mgr.position_around(far_host, now=t, screen=screen)
                if any(e.kind == "clone_buddy" for e in events):
                    break
            self.assertTrue(any(e.kind == "clone_buddy" for e in events))
            t += 0.05
            mgr.position_around(far_host, now=t, screen=screen)
            self.assertNotEqual(w0.mirrored, w1.mirrored, "Clones should face each other during buddy high-five")

            # 5. Autonomous roam scheduler triggers walking/visits on its own without manual start_*
            mgr._group_scene = None
            mgr._next_group_scene_at = t + 30.0
            rt0.pose_action = None
            rt0.pose_until = 0.0
            rt0.roam_mode = "home"
            rt0.roam_pos = None
            rt0.roam_until = 0.0
            rt0.next_roam_at = t + 0.05
            saw_auto_walk = False
            for _ in range(40):
                t += 0.05
                mgr.position_around(far_host, now=t, screen=screen)
                if w0.current_action == PetAction.WALKING:
                    saw_auto_walk = True
                    break
            self.assertTrue(saw_auto_walk, "Playmate should autonomously start walking when next_roam_at elapses")

            # 6. reduced_motion disables roaming cleanly
            t += 0.05
            mgr.position_around(far_host, now=t, reduced_motion=True, screen=screen)
            self.assertEqual(rt0.roam_mode, "home")
            self.assertIsNone(rt0.roam_pos)
        finally:
            mgr.close_all()

    def test_choreographed_multi_pet_train_wave_snack_party_and_huddle(self) -> None:
        from pet.subagent_clones import TRAIN_DURATION_SECONDS, WAVE_STEP_SECONDS

        mgr, events = self._make()
        try:
            subs = [
                SubagentInfo(f"idle-play-g{i}", "idle-play", f"玩耍{i}", "闲时随机玩伴", fid)
                for i, fid in enumerate(("neon", "hydergon", "argon", "claude"))
            ]
            area = QRect(0, 0, 1920, 1040)
            screen = _FakeScreen(area)
            host = QRect(860, 520, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            mgr.position_around(host, now=11.0, screen=screen)
            widgets = mgr.visible_widgets
            self.assertEqual(len(widgets), 4)

            # 1. Mini Train Parade: leader + trailing cars walk together, stay in bounds, finish with CELEBRATE
            events.clear()
            ev_train = mgr.trigger_clone_train(now=20.0)
            assert ev_train is not None
            self.assertEqual(ev_train.kind, "clone_train")
            self.assertEqual(mgr.active_group_scene, "clone_train")
            initial_xs = [w.x() for w in widgets]
            t = 20.0
            for _ in range(20):
                t += 0.05
                mgr.position_around(host, now=t, screen=screen)
            self.assertTrue(all(w.current_action == PetAction.WALKING for w in widgets))
            self.assertTrue(any(abs(w.x() - ix) >= 20 for w, ix in zip(widgets, initial_xs)))
            self.assertTrue(all(area.contains(w.frameGeometry()) for w in widgets))
            # Complete the train duration -> scene clears & clones celebrate
            t = 20.0 + TRAIN_DURATION_SECONDS + 0.1
            mgr.position_around(host, now=t, screen=screen)
            self.assertIsNone(mgr.active_group_scene)
            self.assertTrue(all(w.current_action == PetAction.CELEBRATE for w in widgets))

            # 2. Mexican Wave Relay: strictly left-to-right staggered hops, then finale event to sister
            events.clear()
            for i, pos_x in enumerate((420, 620, 1140, 1340)):
                cid = subs[i].conversation_id
                rt = mgr._runtime[cid]
                rt.pose_action = None
                rt.pose_until = 0.0
                rt.roam_mode = "paused"
                rt.roam_pos = [float(pos_x), 600.0]
                widgets[i].move(pos_x, 600)
                widgets[i].clear_bubble()
            self.assertTrue(mgr.trigger_clone_wave(now=30.0))
            self.assertEqual(mgr.active_group_scene, "clone_wave")
            # Leftmost clone fired immediately; rightmost has not yet fired
            self.assertTrue(bool(widgets[0].bubble_text))
            self.assertEqual(widgets[3].bubble_text, "")
            self.assertFalse(any(e.kind == "clone_wave" for e in events))
            # Advance across all 4 stagger steps + finale
            t = 30.0
            for _ in range(40):
                t += 0.05
                mgr.position_around(host, now=t, screen=screen)
            self.assertTrue(all(bool(w.bubble_text) for w in widgets))
            self.assertTrue(any(e.kind == "clone_wave" for e in events))
            self.assertIn("姐姐", widgets[3].bubble_text)
            # Expire wave scene
            mgr.position_around(host, now=30.0 + 4 * WAVE_STEP_SECONDS + 2.2, screen=screen)
            self.assertIsNone(mgr.active_group_scene)

            # 3. Snack Party: scattered clones trot toward sister and switch to PetAction.EATING without overlap
            events.clear()
            for i, pos_x in enumerate((380, 520, 1280, 1440)):
                cid = subs[i].conversation_id
                rt = mgr._runtime[cid]
                rt.pose_action = None
                rt.pose_until = 0.0
                rt.roam_mode = "paused"
                rt.roam_pos = [float(pos_x), 600.0]
                widgets[i].move(pos_x, 600)
            ev_snack = mgr.trigger_snack_party(now=40.0)
            assert ev_snack is not None
            self.assertEqual(ev_snack.kind, "snack_party")
            self.assertEqual(mgr.active_group_scene, "snack_party")
            t = 40.0
            mgr.position_around(host, now=40.05, screen=screen)
            self.assertTrue(any(w.current_action == PetAction.WALKING for w in widgets))
            for _ in range(95):
                t += 0.05
                mgr.position_around(host, now=t, screen=screen)
                if all(w.current_action == PetAction.EATING for w in widgets):
                    break
            self.assertTrue(all(w.current_action == PetAction.EATING for w in widgets))
            _hl, _hr, host_vis = mgr._host_visual_bounds(host)
            for w in widgets:
                vr = mgr._clone_visual_rect(w.x(), w.y(), w.width(), w.height(), *w.visual_sprite_size)
                self.assertFalse(vr.intersects(host_vis))

            # 4. Group Huddle: scattered clones converge around sister and melt into PET_PURR + emit group_huddle
            events.clear()
            mgr._group_scene = None
            for i, pos_x in enumerate((420, 540, 1260, 1380)):
                cid = subs[i].conversation_id
                rt = mgr._runtime[cid]
                rt.pose_action = None
                rt.pose_until = 0.0
                rt.roam_mode = "paused"
                rt.roam_pos = [float(pos_x), 600.0]
                widgets[i].move(pos_x, 600)
            self.assertTrue(mgr.trigger_group_huddle(now=50.0))
            self.assertEqual(mgr.active_group_scene, "group_huddle")
            t = 50.0
            for _ in range(95):
                t += 0.05
                mgr.position_around(host, now=t, screen=screen)
                if any(e.kind == "group_huddle" for e in events):
                    break
            self.assertTrue(any(e.kind == "group_huddle" for e in events))
            t += 0.05
            mgr.position_around(host, now=t, screen=screen)
            self.assertTrue(all(w.current_action == PetAction.PET_PURR for w in widgets))

            # 5. Autonomous multi-pet scheduler starts a group scene on its own when _next_group_scene_at elapses
            mgr._group_scene = None
            for cid, rt in mgr._runtime.items():
                rt.pose_action = None
                rt.pose_until = 0.0
                rt.roam_mode = "home"
                rt.roam_pos = None
                rt.next_roam_at = t + 30.0
            mgr._next_group_scene_at = t + 0.02
            mgr.position_around(host, now=t + 0.05, screen=screen)
            self.assertIn(
                mgr.active_group_scene,
                {
                    "clone_train",
                    "clone_wave",
                    "snack_party",
                    "group_huddle",
                    "twin_mirror",
                    "tea_party",
                    "campfire_night",
                    "art_studio",
                    "cloud_nap",
                },
            )

            # 6. reduced_motion cleanly ends active motion group scenes and executes calm fallbacks
            if mgr.active_group_scene in {"tea_party", "campfire_night", "art_studio", "cloud_nap"}:
                mgr._group_scene = None
                self.assertIsNotNone(mgr.trigger_clone_train(now=t + 0.08))
            mgr.position_around(host, now=t + 0.10, reduced_motion=True, screen=screen)
            self.assertIsNone(mgr.active_group_scene)
            events.clear()
            self.assertTrue(mgr.trigger_clone_wave(now=t + 0.20))
            self.assertIsNone(mgr.active_group_scene)
            self.assertTrue(any(e.kind == "clone_wave" for e in events))
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
        # Summoning multiple times picks random forms across all 5 forms AND allows same-form twins/multiples!
        self.pet.set_form("carbon", manual=True, announce=False, persist=False)
        self.pet._request_action(PetAction.IDLE, reason="test_idle", force=True, immediate=True)
        seen_forms: set[str] = set()
        saw_twins = False
        for _ in range(30):
            mates = self.pet.summon_idle_playmates(count=3, now=100.0, duration=20.0, announce=False)
            self.assertEqual(len(mates), 3)
            if len({m.form_id for m in mates}) < len(mates):
                saw_twins = True
            seen_forms.update(m.form_id for m in mates)
        self.assertGreaterEqual(len(seen_forms), 4)
        self.assertTrue(saw_twins, "Idle playmates should allow same-form twins/multiples")

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
            *sc._HOST_PAT_CLONE_LINES,
            *sc._TRAIN_LEADER_LINES,
            *sc._TRAIN_FOLLOWER_LINES,
            *sc._WAVE_CHANT_LINES,
            sc._WAVE_BATON_LINE,
            *sc._SNACK_RUSH_LINES,
            *sc._SNACK_EAT_LINES,
            *sc._HUDDLE_CALL_LINES,
            *sc._HUDDLE_PURR_LINES,
            *(line for pair in sc._TWIN_MIRROR_PAIRS for line in pair),
            *sc._TRIPLET_CHORUS_LINES,
            *sc._MINI_ME_LINES,
            *sc._TEA_PARTY_LINES,
            *sc._TEA_CLICK_LINES,
            *sc._CAMPFIRE_LINES,
            *sc._CAMPFIRE_CLICK_LINES,
            *sc._ART_STUDIO_LINES,
            *sc._ART_CLICK_LINES,
            *sc._CLOUD_NAP_LINES,
            *sc._CLOUD_CLICK_LINES,
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

    def test_host_proactively_pats_clone_head_and_autonomous_affection(self) -> None:
        self.pet.summon_idle_playmates(count=2, now=800.0, duration=40.0, announce=False)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=801.0)
        w0 = self.pet.subagent_clones.visible_widgets[0]

        # 1. Direct host-initiated pat puts clone in PET_PURR with 姐姐 reply & turns sister toward clone
        ev = self.pet.subagent_clones.trigger_host_pat_clone(0, now=802.0)
        assert ev is not None
        self.assertEqual(ev.kind, "host_pat_clone")
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=802.1)
        self.assertEqual(w0.current_action, PetAction.PET_PURR)
        self.assertIn("姐姐", w0.bubble_text)
        expected_dir = "left" if ev.side < 0 else "right"
        self.assertEqual(self.pet.movement.direction, expected_dir)
        self.assertIn(self.pet.action_machine.current, {PetAction.GIFT_TOSS, PetAction.WAVE})
        self.assertTrue(bool(self.pet.bubble.text))

        # 2. request_host_pat_clone walks a far-roaming clone over first, then fires host_pat_clone on arrival
        rt0 = self.pet.subagent_clones._runtime[self.pet.subagent_clones._entries[0][0].conversation_id]
        rt0.pose_action = None
        rt0.pose_until = 0.0
        far_x = max(20.0, float(self.pet._sprite_rect().left() - 260))
        rt0.roam_mode = "paused"
        rt0.roam_pos = [far_x, float(w0.y())]
        w0.move(round(far_x), w0.y())
        req = self.pet.subagent_clones.request_host_pat_clone(0, now=806.0)
        self.assertTrue(req)
        self.assertEqual(rt0.roam_mode, "visit_host")
        self.assertEqual(rt0.roam_action_on_arrive, "host_pat")
        t = 806.0
        for _ in range(120):
            t += 0.05
            self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=t)
            if w0.current_action == PetAction.PET_PURR:
                break
        self.assertEqual(w0.current_action, PetAction.PET_PURR)

        # 3. Autonomous _tick_host_clone_affection pats clone when host is calm/idle, never while sulking
        self.pet._request_action(PetAction.SULK, now=t, reason="test_sulk", force=True, immediate=True)
        self.pet._sulk_until = t + 30.0
        self.pet._next_host_pat_clone_at = t - 1.0
        rt0.pose_action = None
        rt0.pose_until = 0.0
        self.pet._tick_host_clone_affection(t)
        self.assertIsNone(rt0.pose_action)

        # Calm idle -> autonomous sisterly affection fires (head pat, snack party, or cuddle huddle)!
        self.pet._sulk_until = 0.0
        self.pet._request_action(PetAction.IDLE, now=t + 1.0, reason="test_calm", force=True, immediate=True)
        self.pet._next_host_pat_clone_at = t + 0.5
        self.pet._tick_host_clone_affection(t + 1.0)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=t + 1.05)
        any_sister_affection = (
            self.pet.subagent_clones.active_group_scene in {"snack_party", "group_huddle"}
            or any(
                (
                    r.pose_action in {PetAction.PET_PURR, PetAction.EATING, PetAction.HIGH_FIVE, PetAction.CELEBRATE}
                    or r.roam_action_on_arrive == "host_pat"
                )
                for r in self.pet.subagent_clones._runtime.values()
            )
        )
        self.assertTrue(any_sister_affection)

    def test_window_responds_to_all_multi_pet_group_scenes(self) -> None:
        self.pet.summon_idle_playmates(count=4, now=900.0, duration=50.0, announce=False)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=901.0)

        # 1. Train parade -> sister waves & cheers
        ev_train = self.pet.subagent_clones.trigger_clone_train(now=902.0)
        assert ev_train is not None
        self.assertEqual(self.pet.action_machine.current, PetAction.WAVE)
        self.assertTrue(bool(self.pet.bubble.text))

        # 2. Snack party -> sister tosses fish gift & speaks
        self.pet.subagent_clones._group_scene = None
        ev_snack = self.pet.subagent_clones.trigger_snack_party(now=904.0)
        assert ev_snack is not None
        self.assertIn(self.pet.action_machine.current, {PetAction.QUOTA_GIFT, PetAction.WAVE})
        self.assertTrue(bool(self.pet.bubble.text))

        # 3. Group huddle -> sister melts into PET_PURR once clones gather
        self.pet.subagent_clones._group_scene = None
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=906.0, reduced_motion=True)
        self.assertTrue(self.pet.subagent_clones.trigger_group_huddle(now=907.0))
        self.assertEqual(self.pet.action_machine.current, PetAction.PET_PURR)
        self.assertTrue(bool(self.pet.bubble.text))

        # 4. Mexican wave finale -> sister celebrates
        self.assertTrue(self.pet.subagent_clones.trigger_clone_wave(now=908.0))
        self.assertEqual(self.pet.action_machine.current, PetAction.CELEBRATE)
        self.assertTrue(bool(self.pet.bubble.text))

    def test_two_thirds_scale_twin_mirror_drag_recognition_and_mini_me_mimic(self) -> None:
        from pet.subagent_clones import CLONE_HOST_SCALE_RATIO

        # 1. Clones scale cleanly to 2/3 of host sprite height across size presets
        self.pet.subagent_clones.set_scale_from_host(238)
        self.assertEqual(self.pet.subagent_clones._sprite_height, round(238 * CLONE_HOST_SCALE_RATIO))
        self.pet.subagent_clones.set_scale_from_host(306)
        self.assertEqual(self.pet.subagent_clones._sprite_height, round(306 * CLONE_HOST_SCALE_RATIO))
        self.assertEqual(self.pet.subagent_clones._source_tier_height(), 238)
        self.pet.subagent_clones.set_scale_from_host(self.pet.current_height)

        # 2. Summoning explicit twins formats cute "双胞胎" announcement
        self.pet.set_form("carbon", manual=True, announce=False, persist=False)
        self.pet._request_action(PetAction.IDLE, reason="test_twins", force=True, immediate=True)
        mates = self.pet.summon_idle_playmates(
            forms=["neon", "neon", "carbon"],
            now=1000.0,
            duration=40.0,
            announce=True,
            manual=True,
        )
        self.assertEqual(len(mates), 3)
        self.assertIn("双胞胎", self.pet.bubble.text)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1001.0)

        # 3. Twin mirror dance: same-form Neon twins face each other in mirrored PLAY_DANCE & sister celebrates
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1002.0, reduced_motion=True)
        res = self.pet.subagent_clones.trigger_twin_mirror(now=1003.0)
        self.assertIsNotNone(res)
        self.assertEqual(self.pet.action_machine.current, PetAction.CELEBRATE)
        w0, w1 = self.pet.subagent_clones.visible_widgets[0], self.pet.subagent_clones.visible_widgets[1]
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1003.1)
        self.assertEqual(w0.current_action, PetAction.PLAY_DANCE)
        self.assertEqual(w1.current_action, PetAction.PLAY_DANCE)
        self.assertNotEqual(w0.mirrored, w1.mirrored, "Twins should face each other in mirror symmetry")

        # 4. Dragging a clone onto its same-form twin auto-upgrades to twin_mirror!
        self.pet._request_action(PetAction.IDLE, reason="test_drag_twin", force=True, immediate=True)
        self.pet.subagent_clones._handle_widget_drag_start(w0)
        self.pet.subagent_clones._handle_widget_drag_end(w0, w1.frameGeometry().center())
        self.assertEqual(self.pet.action_machine.current, PetAction.CELEBRATE)

        # 5. Mini-me mimic: Carbon clone matching Carbon sister strikes showcase pose & sister responds!
        ev_mini = self.pet.subagent_clones.trigger_mini_me_mimic(now=1010.0)
        assert ev_mini is not None
        self.assertEqual(ev_mini.kind, "mini_me_mimic")
        self.assertEqual(ev_mini.form_id, "carbon")
        self.assertIn(self.pet.action_machine.current, {PetAction.HIGH_FIVE, PetAction.HAPPY})
        self.assertTrue(bool(self.pet.bubble.text))

    def test_desktop_prop_scenes_time_of_day_painting_click_interact_and_cleanup(self) -> None:
        from PySide6.QtGui import QImage
        from pet.scene_props import DESKTOP_SCENE_KINDS, SCENE_SPECS, pick_scene_for_hour

        # 1. Time-of-day automatic scene picker favors afternoon tea & night campfire
        rng = random.Random(42)
        afternoon_picks = [pick_scene_for_hour(15, rng) for _ in range(120)]
        self.assertGreater(afternoon_picks.count("tea_party"), 45)
        night_picks = [pick_scene_for_hour(22, rng) for _ in range(120)]
        self.assertGreater(night_picks.count("campfire_night"), 50)
        morning_picks = set(pick_scene_for_hour(10, rng) for _ in range(120))
        self.assertTrue({"art_studio", "cloud_nap", "tea_party"}.issubset(morning_picks))

        # 2. Control panel exposes all 4 compact scene launch buttons
        for kind in DESKTOP_SCENE_KINDS:
            self.assertIn(kind, self.pet.control_panel.scene_buttons)

        # 3. Manual tea_party launch auto-summons playmates, spawns non-overlapping prop, and responds to clicks!
        self.pet.dismiss_idle_playmates(now=1100.0)
        ev_tea = self.pet.start_desktop_scene("tea_party", now=1105.0)
        assert ev_tea is not None
        self.assertEqual(ev_tea.kind, "tea_party")
        self.assertGreaterEqual(self.pet.subagent_clones.active_count, 2)
        prop = self.pet.subagent_clones.scene_prop_widget
        assert prop is not None
        self.assertTrue(prop.isVisible())
        self.assertEqual(prop.scene_kind, "tea_party")
        self.assertEqual(self.pet.action_machine.current, PetAction.EATING)
        # Click prop -> refills tea, increments interact_count, extends duration, updates sister!
        prev_end = self.pet.subagent_clones._group_scene.ends_at
        ev_click = self.pet.subagent_clones.interact_scene_prop(now=1112.0)
        assert ev_click is not None
        self.assertEqual(ev_click.kind, "tea_party_interact")
        self.assertEqual(prop.interact_count, 1)
        self.assertGreater(self.pet.subagent_clones._group_scene.ends_at, prev_end)
        self.assertTrue(bool(prop.bubble_text))
        self.assertEqual(self.pet.action_machine.current, PetAction.HAPPY)

        # 4. Render all 4 themed vector props cleanly onto QImage (normal + hovered + reduced_motion)
        for kind in DESKTOP_SCENE_KINDS:
            ev_s = self.pet.start_desktop_scene(kind, now=1120.0)
            assert ev_s is not None
            self.assertEqual(ev_s.kind, kind)
            self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1120.2)
            prop = self.pet.subagent_clones.scene_prop_widget
            assert prop is not None
            img = QImage(prop.size(), QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(0)
            prop.render(img)
            # Confirm non-empty rendered vector pixels!
            self.assertGreater(img.pixelColor(prop.width() // 2, prop.height() - 32).alpha(), 0, kind)
            self.assertIn(kind, SCENE_SPECS)

        # 5. Art studio uses WORK_DRAWING/WORK_SEARCHING/WORK_READING; Campfire sits in PERCH;
        #    Cloud nap puts ALL clones + sister to sleep with proportional zero-clipped wide SLEEPING widgets!
        self.pet.start_desktop_scene("art_studio", now=1140.0)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1140.1, reduced_motion=True)
        art_actions = {w.current_action for w in self.pet.subagent_clones.visible_widgets}
        self.assertTrue(art_actions.issubset({PetAction.WORK_DRAWING, PetAction.WORK_SEARCHING, PetAction.WORK_READING}))

        self.pet.start_desktop_scene("campfire_night", now=1145.0)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1145.1, reduced_motion=True)
        self.assertIn(self.pet.action_machine.current, {PetAction.PERCH, PetAction.HAPPY})
        camp_actions = {w.current_action for w in self.pet.subagent_clones.visible_widgets}
        self.assertTrue(camp_actions.issubset({PetAction.PERCH, PetAction.TALKING, PetAction.EATING}))

        self.pet.start_desktop_scene("cloud_nap", now=1150.0)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1150.1, reduced_motion=True)
        self.assertIn(self.pet.action_machine.current, {PetAction.SLEEPING, PetAction.PERCH_SLEEP})
        nap_actions = {w.current_action for w in self.pet.subagent_clones.visible_widgets}
        self.assertTrue(nap_actions.issubset({PetAction.SLEEPING, PetAction.PERCH_SLEEP}))
        # Verify sleeping clone sprite is proportionally capped and NEVER clipped at left/right widget edges!
        sleep_widgets = [w for w in self.pet.subagent_clones.visible_widgets if w.current_action == PetAction.SLEEPING]
        self.assertTrue(sleep_widgets)
        for sw in sleep_widgets:
            self.assertLessEqual(sw._pixmap.width(), round(self.pet.subagent_clones._sprite_height * 1.18))
            self.assertGreaterEqual(sw.width(), sw._pixmap.width() + 24)
            simg = QImage(sw.size(), QImage.Format.Format_ARGB32_Premultiplied)
            simg.fill(0)
            sw.render(simg)
            left_col_max = max(simg.pixelColor(0, y).alpha() for y in range(simg.height()))
            right_col_max = max(simg.pixelColor(simg.width() - 1, y).alpha() for y in range(simg.height()))
            self.assertEqual(left_col_max, 0, "Sleeping clone clipped on left edge!")
            self.assertEqual(right_col_max, 0, "Sleeping clone clipped on right edge!")
        # Verify cloud prop interior is solidly filled (no hollow arc cutouts)
        cprop = self.pet.subagent_clones.scene_prop_widget
        assert cprop is not None
        cimg = QImage(cprop.size(), QImage.Format.Format_ARGB32_Premultiplied)
        cimg.fill(0)
        cprop.render(cimg)
        self.assertGreaterEqual(cimg.pixelColor(cprop.width() // 2, cprop.height() - 40).alpha(), 220)
        # Idle playmates stay alive during cloud_nap even while sister is SLEEPING!
        self.pet._tick_idle_playmates(1150.5)
        self.assertGreaterEqual(self.pet.subagent_clones.active_count, 2)

        # 6. All scene prop click lines render cleanly without elision inside the prop bubble width
        from PySide6.QtGui import QFontMetrics

        assert prop is not None
        pfm = QFontMetrics(prop._bubble_font)
        prop_max_w = prop.width() - 18
        for spec in SCENE_SPECS.values():
            for line in spec.click_lines:
                self.assertEqual(pfm.elidedText(line, Qt.TextElideMode.ElideRight, prop_max_w), line)

        # 7. Early right-click dismiss hides prop cleanly & wakes sister with STRETCH!
        self.pet.subagent_clones.dismiss_desktop_scene(now=1155.0)
        self.assertIsNone(self.pet.subagent_clones.active_group_scene)
        self.assertEqual(self.pet.action_machine.current, PetAction.STRETCH)
        assert self.pet.subagent_clones.scene_prop_widget is not None
        self.assertFalse(self.pet.subagent_clones.scene_prop_widget.isVisible())

    def test_host_leads_clone_train_walks_to_pat_and_strolls_without_banter_freeze(self) -> None:
        from pet.subagent_clones import TRAIN_DURATION_SECONDS

        self.pet.set_mode("wander")
        self.pet.set_reduced_motion(False)
        self.pet._sulk_until = 0.0
        self.pet._hovered = False
        self.pet.control_panel.hide()
        self.pet.food_panel.hide()
        self.pet.move(620, 520)
        self.pet._request_action(PetAction.IDLE, now=1200.0, reason="test_comotion", force=True, immediate=True)

        mates = self.pet.summon_idle_playmates(count=3, now=1200.0, duration=60.0, announce=True, manual=True)
        self.assertEqual(len(mates), 3)
        self.pet.subagent_clones.position_around(self.pet._sprite_rect(), now=1201.0)
        widgets = self.pet.subagent_clones.visible_widgets
        self.assertEqual(len(widgets), 3)

        # 1. Ambient clone chatter (relay / clone_chat / clicked) must NOT cancel host's walk target!
        self.pet.movement.target = (980.0, float(self.pet.y()))
        self.pet.subagent_clones.trigger_relay(0, now=1202.0)
        self.assertIsNotNone(self.pet.movement.target)
        self.pet.subagent_clones.trigger_clone_chat(0, 1, now=1202.5)
        self.assertIsNotNone(self.pet.movement.target)
        self.pet.subagent_clones.trigger_click(0, now=1203.0)
        self.assertIsNotNone(self.pet.movement.target)
        self.pet.movement.cancel_target()

        # 2. Host-led Clone Train: brief WAVE whistle -> host switches to WALKING locomotive & clones trail behind!
        start_x = self.pet.x()
        ev_train = self.pet.subagent_clones.trigger_clone_train(now=1210.0)
        assert ev_train is not None
        self.assertTrue(self.pet._host_train_active)
        self.assertEqual(self.pet.action_machine.current, PetAction.WAVE)

        t = 1210.0
        walked_ticks = 0
        # Advance past 0.30s lead-in and march for ~2.5s
        for _ in range(55):
            t += 0.05
            walked = self.pet._tick_host_clone_motion(0.05, t, sulking=False, hover_paused=False)
            facing = self.pet._host_train_facing if (self.pet._host_train_active and t >= self.pet._host_train_start_move_at) else 0
            self.pet.subagent_clones.position_around(
                self.pet._sprite_rect(),
                now=t,
                reduced_motion=False,
                host_train_facing=facing,
            )
            if walked:
                walked_ticks += 1
            if t >= self.pet._host_train_start_move_at + 0.15:
                self.assertTrue(walked)
                self.assertEqual(self.pet.action_machine.current, PetAction.WALKING)

        self.assertGreaterEqual(walked_ticks, 30, "Host locomotive must actively walk across parade ticks")
        self.assertGreaterEqual(abs(self.pet.x() - start_x), 80, "Host locomotive must visibly travel across desktop")
        self.assertTrue(all(w.current_action == PetAction.WALKING for w in widgets))
        # Trailing clones stay behind host without overlapping host visual sprite
        host_vis_left, host_vis_right, host_vis = self.pet.subagent_clones._host_visual_bounds(self.pet._sprite_rect())
        if self.pet._host_train_facing > 0:
            self.assertLessEqual(widgets[0].x() + widgets[0].width() // 2, host_vis_left + 12)
        else:
            self.assertGreaterEqual(widgets[0].x() + widgets[0].width() // 2, host_vis_right - 12)
        for w in widgets:
            vr = self.pet.subagent_clones._clone_visual_rect(w.x(), w.y(), w.width(), w.height(), *w.visual_sprite_size)
            self.assertFalse(vr.intersects(host_vis), "Train clone must not overlap host body")

        # Complete train duration -> host & all clones finish in synchronized CELEBRATE!
        t_end = 1210.0 + TRAIN_DURATION_SECONDS + 0.15
        self.pet.subagent_clones.position_around(
            self.pet._sprite_rect(),
            now=t_end,
            reduced_motion=False,
            host_train_facing=self.pet._host_train_facing,
        )
        self.assertIsNone(self.pet.subagent_clones.active_group_scene)
        self.assertFalse(self.pet._host_train_active)
        self.assertEqual(self.pet.action_machine.current, PetAction.CELEBRATE)
        self.assertTrue(all(w.current_action == PetAction.CELEBRATE for w in widgets))

        # 3. Host walks over to a nearby clone and pats its head on arrival!
        self.pet.move(500, 520)
        self.pet._request_action(PetAction.IDLE, now=1230.0, reason="test_visit_idle", force=True, immediate=True)
        for cid, rt in self.pet.subagent_clones._runtime.items():
            rt.pose_action = None
            rt.pose_until = 0.0
            rt.roam_mode = "paused"
            rt.roam_until = 1245.0
        target_w = widgets[0]
        target_w.move(820, 560)
        pick = self.pet.subagent_clones.pick_clone_for_host_visit(
            self.pet._sprite_rect(),
            host_widget_width=self.pet.width(),
            now=1230.0,
        )
        self.assertIsNotNone(pick)
        _idx, visit_cid, visit_tx, _face = pick
        self.pet._host_clone_visit_cid = visit_cid
        self.pet._host_clone_visit_target_x = visit_tx
        self.pet._host_clone_visit_until = 1240.0
        visit_start_x = self.pet.x()
        vt = 1230.0
        for _ in range(70):
            vt += 0.05
            self.pet._tick_host_clone_motion(0.05, vt, sulking=False, hover_paused=False)
            if self.pet._host_clone_visit_target_x is None:
                break
        self.assertIsNone(self.pet._host_clone_visit_target_x)
        self.assertGreater(abs(self.pet.x() - visit_start_x), 40)
        self.assertIn(self.pet.action_machine.current, {PetAction.GIFT_TOSS, PetAction.WAVE})

        # 4. Autonomous companion stroll starts when idle with playmates in wander mode
        self.pet._request_action(PetAction.IDLE, now=1260.0, reason="test_stroll_idle", force=True, immediate=True)
        self.pet.movement.cancel_target()
        self.pet._next_host_clone_stroll_at = 1259.0
        self.pet._tick_host_clone_motion(0.05, 1260.0, sulking=False, hover_paused=False)
        self.assertTrue(self.pet.movement.is_walking)

        # 5. mode='still' keeps host anchored during clone_train (graceful fallback to clone-only train)
        self.pet.set_mode("still")
        still_x = self.pet.x()
        ev_still = self.pet.subagent_clones.trigger_clone_train(now=1270.0)
        assert ev_still is not None
        self.assertFalse(self.pet._host_train_active)
        self.pet._tick_host_clone_motion(0.05, 1271.0, sulking=False, hover_paused=False)
        self.assertEqual(self.pet.x(), still_x)
        self.pet.set_mode("wander")


if __name__ == "__main__":
    unittest.main()
