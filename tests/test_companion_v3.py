from __future__ import annotations

import os
import random
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QEnterEvent, QImage, QPainter
from PySide6.QtWidgets import QApplication

from agy.reactions import ReactionTracker, greeting_for_moment
from agy.telemetry import LiveSnapshot, SubagentInfo, TelemetryCollector, clean_title, snapshot_from_hud_live
from animation.clip import PetAction
from app.paths import AppPaths
from pet.particles import ParticleSystem
from pet.subagent_clones import MAX_VISIBLE_CLONES
from pet.window import PetWindow
from settings.config import ConfigManager
from tools.rehearsal_stage import RehearsalStage

ROOT = Path(__file__).resolve().parents[1]


class TelemetryAndReactionV3Tests(unittest.TestCase):
    def test_snapshot_from_hud_live_parses_v3_fields(self) -> None:
        payload = {
            "active": {
                "conversationId": "conv-main",
                "title": "修一下粒子特效",
                "status": "CASCADE_RUN_STATUS_RUNNING",
                "selectedModelLabel": "Gemini 4 Neon (High)",
                "waitingForUser": True,
                "terminationReason": "",
                "latestToolName": "edit_file",
                "latestToolCategory": "writing",
                "quotaRemainingPct": 42.0,
            },
            "availableUpdateSha": "abcdef1234567890",
            "runningSessionsCount": 3,
            "activeSubagents": [
                {
                    "conversationId": "sub-1",
                    "parentConversationId": "conv-main",
                    "title": "查源码",
                    "modelLabel": "Claude 4.5 Sonnet",
                    "formId": "claude",
                },
                {
                    "conversationId": "",
                    "title": "invalid-ignored",
                },
            ],
            "aiComment": {
                "id": "ai-42",
                "text": "✦ 这波改动稳得一批！",
                "trigger": "turn_done_big",
            },
        }
        snap = snapshot_from_hud_live(payload, source="pet_live")
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertTrue(snap.waiting_for_user)
        self.assertEqual(snap.latest_tool_name, "edit_file")
        self.assertEqual(snap.latest_tool_category, "writing")
        self.assertEqual(snap.available_update_sha, "abcdef1234567890")
        self.assertEqual(snap.running_sessions_count, 3)
        self.assertEqual(len(snap.active_subagents), 1)
        self.assertEqual(snap.active_subagents[0].form_id, "claude")
        self.assertEqual(snap.ai_comment_id, "ai-42")
        self.assertEqual(snap.ai_comment_text, "✦ 这波改动稳得一批！")
        self.assertEqual(snap.ai_comment_trigger, "turn_done_big")

    def test_waiting_error_subagent_quota_and_update_reactions(self) -> None:
        tracker = ReactionTracker(random.Random(0), cooldown_seconds=60.0)
        t = 1000.0

        # Initial running snapshot
        s1 = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_RUNNING",
            quota_remaining_pct=60.0,
        )
        tracker.observe(s1, now=t, follow_model=False, current_form="carbon")

        # Waiting for user approval
        t += 5.0
        s2 = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_RUNNING",
            waiting_for_user=True,
            quota_remaining_pct=60.0,
        )
        r2 = tracker.observe(s2, now=t, follow_model=False, current_form="carbon")
        waiting = [r for r in r2 if r.kind == "waiting"]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0].action, "WAITING_USER")
        self.assertEqual(waiting[0].particle, "alert")

        # Repeated poll while still waiting must not spam
        t += 2.0
        r2_repeat = tracker.observe(s2, now=t, follow_model=False, current_form="carbon")
        self.assertFalse(any(r.kind == "waiting" for r in r2_repeat))

        # 1 subagent -> subagent_start; then 3 subagents -> subagent_many
        t += 5.0
        s3 = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_RUNNING",
            active_subagents=[SubagentInfo("sub-1", "c1", "A", "Gemini 4 Neon", "neon")],
            quota_remaining_pct=60.0,
        )
        r3 = tracker.observe(s3, now=t, follow_model=False, current_form="carbon")
        self.assertTrue(any(r.kind == "subagent_start" and r.particle == "sparkles" for r in r3))

        t += 5.0
        s4 = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_RUNNING",
            active_subagents=[
                SubagentInfo("sub-1", "c1", "A", "Gemini 4 Neon", "neon"),
                SubagentInfo("sub-2", "c1", "B", "Claude 4.5 Sonnet", "claude"),
                SubagentInfo("sub-3", "c1", "C", "Gemini 4 Argon", "argon"),
            ],
            quota_remaining_pct=60.0,
        )
        r4 = tracker.observe(s4, now=t, follow_model=False, current_form="carbon")
        self.assertTrue(any(r.kind == "subagent_many" and "3" in r.text for r in r4))

        # Running -> Idle with ERROR termination produces turn_error (not finished)
        t += 5.0
        s5 = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_IDLE",
            termination_reason="ERROR",
            quota_remaining_pct=30.0,
            quota_reset_time=datetime.fromtimestamp(time.time() + 10 * 60, tz=timezone.utc).isoformat(),
            available_update_sha="deadbeef123456",
            ai_comment_id="ai-1",
            ai_comment_text="✦ 翻车啦，先别慌！",
        )
        r5 = tracker.observe(s5, now=t, follow_model=False, current_form="carbon")
        kinds5 = {r.kind for r in r5}
        self.assertIn("turn_error", kinds5)
        self.assertNotIn("finished", kinds5)
        self.assertIn("quota_reset_soon", kinds5)
        self.assertIn("update", kinds5)
        self.assertIn("ai_comment", kinds5)
        upd = next(r for r in r5 if r.kind == "update")
        self.assertIn("deadbee", upd.text)

        # Same SHA and same AI comment id are deduped; quota refill (+70%) triggers fish rain
        t += 10.0
        s6 = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_IDLE",
            quota_remaining_pct=100.0,
            available_update_sha="deadbeef123456",
            ai_comment_id="ai-1",
            ai_comment_text="✦ 翻车啦，先别慌！",
        )
        r6 = tracker.observe(s6, now=t, follow_model=False, current_form="carbon")
        kinds6 = {r.kind for r in r6}
        self.assertNotIn("update", kinds6)
        self.assertNotIn("ai_comment", kinds6)
        refill = [r for r in r6 if r.kind == "quota_refilled"]
        self.assertEqual(len(refill), 1)
        self.assertEqual(refill[0].particle, "fish")

    def test_greeting_for_moment_covers_festivals_and_time_slots(self) -> None:
        self.assertEqual(greeting_for_moment(datetime(2026, 2, 17, 9, 0))[0], "fest_spring")
        self.assertEqual(greeting_for_moment(datetime(2026, 2, 17, 9, 0))[2], "confetti")
        self.assertEqual(greeting_for_moment(datetime(2026, 12, 25, 14, 0))[0], "fest_christmas")
        self.assertEqual(greeting_for_moment(datetime(2026, 4, 10, 2, 30))[0], "late_night")
        self.assertEqual(greeting_for_moment(datetime(2026, 4, 10, 2, 30))[2], "sweat")
        self.assertEqual(greeting_for_moment(datetime(2026, 4, 10, 8, 0))[0], "morning")
        self.assertEqual(greeting_for_moment(datetime(2026, 4, 10, 12, 30))[0], "noon")
        self.assertEqual(greeting_for_moment(datetime(2026, 4, 10, 16, 0))[0], "afternoon")
        self.assertEqual(greeting_for_moment(datetime(2026, 4, 10, 20, 0))[0], "evening")
        self.assertEqual(greeting_for_moment(datetime(2026, 4, 10, 23, 30))[0], "night")

    def test_subagent_hook_does_not_hijack_active_and_system_message_stripped(self) -> None:
        import json

        self.assertEqual(
            clean_title("<SYSTEM_MESSAGE>The following is a message not actually sent by the user.</SYSTEM_MESSAGE> 真正任务"),
            "真正任务",
        )
        with tempfile.TemporaryDirectory(prefix="agy-sub-hook-") as tmp:
            root = Path(tmp)
            pet_dir = root / "sidecar_data" / "agy-pet" / "pet-bridge" / "data"
            hook_dir = root / "sidecar_data" / "agy-pet"
            sub_log_dir = root / "brain" / "sub-999" / ".system_generated" / "logs"
            pet_dir.mkdir(parents=True)
            sub_log_dir.mkdir(parents=True)

            now_ms = int(time.time() * 1000)
            payload = {
                "active": {
                    "conversationId": "conv-main",
                    "title": "主会话任务",
                    "status": "CASCADE_RUN_STATUS_RUNNING",
                    "selectedModelLabel": "Gemini 4 Neon (High)",
                    "contextUsedTokens": 8000,
                },
                "activeSubagents": [
                    {
                        "conversationId": "sub-999",
                        "parentConversationId": "conv-main",
                        "title": "代码审查子代理",
                        "modelLabel": "Gemini 4 Neon (XHigh)",
                        "formId": "neon",
                    }
                ],
                "conversations": [
                    {
                        "conversationId": "conv-main",
                        "title": "主会话任务",
                        "status": "CASCADE_RUN_STATUS_RUNNING",
                        "lastModifiedTime": datetime.now(timezone.utc).isoformat(),
                        "contextUsedTokens": 8000,
                    }
                ],
            }
            (pet_dir / "pet_live.json").write_text(json.dumps(payload), encoding="utf-8")
            (hook_dir / "active_session.json").write_text(
                json.dumps({"conversationId": "sub-999", "lastUserInput": "", "updatedMs": now_ms}),
                encoding="utf-8",
            )
            (sub_log_dir / "transcript.jsonl").write_text(
                json.dumps({"source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": "system prompt"}) + "\n",
                encoding="utf-8",
            )

            collector = TelemetryCollector(root, use_language_server=False)
            snap = collector.live_snapshot()
            self.assertIsNotNone(snap)
            assert snap is not None
            self.assertEqual(snap.conversation_id, "conv-main")
            self.assertEqual(snap.context_used_tokens, 8000)
            self.assertEqual(len(snap.active_subagents), 1)
            self.assertEqual(snap.active_subagents[0].conversation_id, "sub-999")

    def test_error_cooldown_never_celebrates_and_zero_timestamp_safe(self) -> None:
        from agy.telemetry import format_reset_countdown, parse_iso_ms

        # Windows-safe handling of Protobuf zero timestamps and lowercase 'z'
        self.assertEqual(format_reset_countdown("0001-01-01T00:00:00Z"), "")
        self.assertIsNotNone(parse_iso_ms("2026-11-25T10:00:00z"))

        tracker = ReactionTracker(random.Random(0), cooldown_seconds=60.0)
        t = 2000.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="CASCADE_RUN_STATUS_RUNNING", selected_model_label="Gemini 4 Neon", quota_remaining_pct=80.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        t += 2.0
        r_err1 = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="CASCADE_RUN_STATUS_IDLE", termination_reason="ERROR", selected_model_label="Gemini 4 Neon", quota_remaining_pct=80.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        self.assertEqual([r.kind for r in r_err1], ["turn_error"])

        # Second error inside 30s cooldown must NOT fall through to finished/confetti
        t += 5.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="CASCADE_RUN_STATUS_RUNNING", selected_model_label="Gemini 4 Neon", quota_remaining_pct=80.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        t += 5.0
        r_err2 = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="CASCADE_RUN_STATUS_IDLE", termination_reason="ERROR", selected_model_label="Gemini 4 Neon", quota_remaining_pct=80.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        self.assertFalse(any(r.kind == "finished" for r in r_err2))

        # Switching quota groups (Gemini 15% -> Claude 95%) must not fire fake quota_refilled
        t += 100.0
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="CASCADE_RUN_STATUS_IDLE", selected_model_label="Gemini 4 Neon", quota_remaining_pct=15.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        t += 2.0
        r_switch = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="CASCADE_RUN_STATUS_IDLE", selected_model_label="Claude 4.5 Sonnet", quota_remaining_pct=95.0),
            now=t,
            follow_model=False,
            current_form="neon",
        )
        self.assertFalse(any(r.kind == "quota_refilled" for r in r_switch))


class ParticleSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_all_effects_emit_render_cap_and_expire(self) -> None:
        system = ParticleSystem(random.Random(7))
        for effect in ("sparkles", "confetti", "hearts", "sweat", "fish", "alert"):
            system.clear()
            count = system.emit(effect, origin_x=100.0, origin_y=100.0)
            self.assertGreater(count, 0, effect)
            self.assertLessEqual(len(system.particles), ParticleSystem.MAX_PARTICLES)
            system.update(0.25)

            image = QImage(220, 220, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            try:
                system.paint(painter)
            finally:
                painter.end()
            # Ensure at least one visible pixel was drawn
            raw = bytes(image.constBits())
            self.assertTrue(any(raw), f"effect {effect} painted nothing")

        # Cap enforcement
        for _ in range(10):
            system.emit("confetti", origin_x=100.0, origin_y=100.0)
        self.assertLessEqual(len(system.particles), ParticleSystem.MAX_PARTICLES)

        # Expiration
        for _ in range(30):
            system.update(0.10)
        self.assertFalse(system.active)

    def test_disabled_and_reduced_motion_emit_nothing(self) -> None:
        system = ParticleSystem(random.Random(1))
        system.enabled = False
        self.assertEqual(system.emit("sparkles", origin_x=50.0, origin_y=50.0), 0)
        system.enabled = True
        system.reduced_motion = True
        self.assertEqual(system.emit("confetti", origin_x=50.0, origin_y=50.0), 0)


class PetWindowCompanionV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="agy-pet-v3-test-")
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
        self.application.processEvents()

    def tearDown(self) -> None:
        self.pet.subagent_clones.close_all()
        self.pet.hud_bar.hide()
        self.pet.control_panel.hide()
        self.pet.food_panel.hide()
        self.pet.tray.hide()
        self.pet.hide()
        self.pet.close()
        self.application.processEvents()
        self._tmp.cleanup()

    def test_subagent_clones_reuse_forms_cap_and_hide_with_toggle(self) -> None:
        subagents = [
            SubagentInfo("sub-1", "m1", "查文档", "Gemini 4 Neon (High)", "neon"),
            SubagentInfo("sub-2", "m1", "代码审查", "Claude 4.5 Sonnet", "claude"),
            SubagentInfo("sub-3", "m1", "跑测试", "Gemini 4 Hydrogen (Low)", "hydergon"),
            SubagentInfo("sub-4", "m1", "查日志", "Gemini 4 Argon", "argon"),
            SubagentInfo("sub-5", "m1", "写单测", "Gemini 4 Carbon", "carbon"),
        ]
        snap2 = LiveSnapshot(source="pet_live", conversation_id="m1", active_subagents=subagents[:2])
        self.pet._on_live_snapshot(snap2)
        self.application.processEvents()
        self.assertEqual(self.pet.subagent_clones.active_count, 2)
        self.assertEqual(len(self.pet.subagent_clones.visible_widgets), 2)
        self.assertFalse(self.pet.subagent_clones.visible_widgets[0]._pixmap.isNull())
        self.assertFalse(self.pet.subagent_clones.visible_widgets[1]._pixmap.isNull())

        # Flash Lite (without explicit form_id) maps to argon with a distinct Flash Lite badge
        snap_flash = LiveSnapshot(
            source="pet_live",
            conversation_id="m1",
            active_subagents=[SubagentInfo("sub-fl", "m1", "轻量检查", "Gemini 3.5 Flash Lite", "")],
        )
        self.pet._on_live_snapshot(snap_flash)
        self.application.processEvents()
        self.assertEqual(self.pet.subagent_clones.visible_widgets[0]._badge, "Flash Lite")

        # 5 subagents -> capped at MAX_VISIBLE_CLONES with +2 overflow badge on the last visible clone
        snap5 = LiveSnapshot(source="pet_live", conversation_id="m1", active_subagents=subagents)
        self.pet._on_live_snapshot(snap5)
        self.application.processEvents()
        self.assertEqual(self.pet.subagent_clones.active_count, MAX_VISIBLE_CLONES)
        self.assertEqual(len(self.pet.subagent_clones.visible_widgets), MAX_VISIBLE_CLONES)
        self.assertEqual(self.pet.subagent_clones.visible_widgets[-1]._badge, "+2")

        # Disabling subagent_clones hides all clone windows
        self.pet._agy_set("subagent_clones", False)
        self.pet._sync_subagent_clones(snap5)
        self.application.processEvents()
        self.assertEqual(self.pet.subagent_clones.active_count, 0)
        self.assertEqual(len(self.pet.subagent_clones.visible_widgets), 0)

        # Re-enabling shows again; hiding pet hides clones
        self.pet._agy_set("subagent_clones", True)
        self.pet._sync_subagent_clones(snap2)
        self.assertEqual(len(self.pet.subagent_clones.visible_widgets), 2)
        self.pet._hide_from_panel()
        self.assertEqual(len(self.pet.subagent_clones.visible_widgets), 0)

    def test_edge_dock_peek_and_undock(self) -> None:
        area = self.pet._screen_area_for_pet()
        assert area is not None
        self.pet.dock_to_edge("right")
        self.assertEqual(self.pet._dock_side, "right")
        self.assertEqual(self.pet._display_state_name(), "贴边藏身")
        docked_x = self.pet.x()
        self.assertGreater(docked_x + self.pet.width(), area.right())

        # Hover enters -> peeking
        enter = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
        self.pet.enterEvent(enter)
        self.assertTrue(self.pet._dock_peeking)
        self.assertEqual(self.pet._display_state_name(), "探头看你")
        for _ in range(20):
            self.pet._tick_edge_dock(time.monotonic())
        self.assertLess(self.pet.x(), docked_x)

        # Hover leaves -> retracts after delay
        self.pet.leaveEvent(QEvent(QEvent.Type.Leave))
        future = time.monotonic() + 2.0
        for _ in range(25):
            self.pet._tick_edge_dock(future)
        self.assertFalse(self.pet._dock_peeking)
        self.assertEqual(self.pet.x(), docked_x)

        # Undock restores fully inside screen and returns from bespoke dock asset
        self.pet.undock_from_edge()
        self.assertIsNone(self.pet._dock_side)
        self.assertLessEqual(self.pet.x() + self.pet.width(), area.right() + 1)
        self.assertNotIn(self.pet.player.snapshot().current.asset_id, {"dock_peek", "dock_peek_right", "dock_work", "dock_work_right"})

        # Verify bespoke dock_peek / dock_work assets load on left & right dock
        self.pet.dock_to_edge("left")
        self.assertEqual(self.pet.player.snapshot().current.asset_id, "dock_peek")
        self.pet._request_action(PetAction.WORKING, reason="test_dock_work", force=True, immediate=True)
        self.assertEqual(self.pet.player.snapshot().current.asset_id, "dock_work")
        self.pet.dock_to_edge("right")
        self.assertEqual(self.pet.player.snapshot().current.asset_id, "dock_peek_right")
        self.pet._request_action(PetAction.WORKING, reason="test_dock_work_r", force=True, immediate=True)
        self.assertEqual(self.pet.player.snapshot().current.asset_id, "dock_work_right")
        self.pet.undock_from_edge()

    def test_stepped_sulking_and_forgiveness_by_head_pat_and_favorite_food(self) -> None:
        self.pet._recent_pokes.clear()
        self.pet._sulk_until = 0.0
        self.pet._pending_click_region = "body"
        for _ in range(4):
            self.pet._do_click_reaction()
        self.assertGreater(self.pet._sulk_until, time.monotonic())
        self.assertEqual(self.pet._display_state_name(), "闹别扭中")

        # Another body poke keeps sulking
        self.pet._pending_click_region = "body"
        self.pet._do_click_reaction()
        self.assertGreater(self.pet._sulk_until, time.monotonic())
        self.assertEqual(self.pet.action_machine.current, PetAction.ANGRY)

        # Head pat immediately forgives
        self.pet._pending_click_region = "head"
        self.pet._do_click_reaction()
        self.assertEqual(self.pet._sulk_until, 0.0)
        self.assertEqual(self.pet.action_machine.current, PetAction.HAPPY)
        self.assertTrue(self.pet.particles.active)

        # Sulk again and forgive with favorite food
        self.pet._sulk_until = time.monotonic() + 30.0
        fav = next((item.id for item in self.pet.food_panel.items if item.taste == "favorite"), None)
        self.assertIsNotNone(fav)
        assert fav is not None
        self.pet.on_food(fav)
        self.assertEqual(self.pet._sulk_until, 0.0)

    def test_display_state_name_and_rehearsal_stage_smoke(self) -> None:
        stage = RehearsalStage(self.pet)
        try:
            stage._simulate_subagents(3)
            self.assertEqual(self.pet.subagent_clones.active_count, 3)
            stage._sim_tool_writing()
            self.assertEqual(self.pet._display_state_name(), "陪你写代码")
            stage._sim_waiting()
            self.assertEqual(self.pet._display_state_name(), "等你确认啦")
            stage._sim_error()
            stage._sim_reset_soon()
            stage._sim_quota_refilled()
            stage._sim_ai_comment()
            stage._sim_festival()
            stage._sim_sulk()
            self.assertEqual(self.pet._display_state_name(), "闹别扭中")
            stage._sim_forgive()
            self.assertEqual(self.pet._sulk_until, 0.0)
            stage._simulate_subagents(0)
            self.assertEqual(self.pet.subagent_clones.active_count, 0)
        finally:
            stage.hide()


if __name__ == "__main__":
    unittest.main()
