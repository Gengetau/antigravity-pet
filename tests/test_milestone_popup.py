from __future__ import annotations

import json
import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QEnterEvent, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from agy.milestone import (
    MilestoneEvent,
    clean_milestone_text,
    extract_milestone_from_rpc_steps,
    extract_milestone_from_transcript_records,
    milestone_from_dict,
    read_latest_milestone_from_transcript,
)
from agy.reactions import ReactionTracker
from agy.telemetry import LiveSnapshot, TelemetryCollector, snapshot_from_hud_live
from app import i18n
from app.paths import AppPaths
from pet.milestone_popup import MilestonePopupWidget
from pet.window import PetWindow
from settings.config import ConfigManager

ROOT = Path(__file__).resolve().parent.parent


class MilestoneExtractionTests(unittest.TestCase):
    def test_clean_milestone_text_strips_markdown_and_redacts_secrets(self) -> None:
        fake_sk = "-".join(("sk", "proj", "AbCdEfGhIjKlMnOpQrSt"))
        fake_gh = "_".join(("ghp", "1234567890abcdef12345678"))
        fake_jwt = ".".join(
            (
                "eyJhbGciOiJIUzI1NiJ9",
                "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
                "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            )
        )
        raw = (
            "### 阶段完成\n"
            "已修复 [scene_props.py](file:///d:/agy-pet/pet/scene_props.py#L368-L375) 的 **中文悬停崩溃**。\n"
            "```python\nprint('ignore code block')\n```\n"
            f"- 校验 `pytest` 通过（265 passed），不要泄露 {fake_sk} {fake_gh} {fake_jwt} Bearer secret_token_12345\n"
            "- 详情见 https://private.example.invalid/token?x=1 API_KEY=supersecret999 <script>alert(1)</script>\n"
        )
        cleaned = clean_milestone_text(raw)
        self.assertIn("scene_props.py", cleaned)
        self.assertIn("中文悬停崩溃", cleaned)
        self.assertIn("265 passed", cleaned)
        self.assertNotIn("file:///", cleaned)
        self.assertNotIn("ignore code block", cleaned)
        self.assertNotIn(fake_sk, cleaned)
        self.assertNotIn(fake_gh, cleaned)
        self.assertNotIn(fake_jwt, cleaned)
        self.assertNotIn("secret_token_12345", cleaned)
        self.assertNotIn("supersecret999", cleaned)
        self.assertNotIn("private.example.invalid", cleaned)
        self.assertNotIn("alert(1)", cleaned)

        self.assertEqual(clean_milestone_text("OK"), "")
        self.assertEqual(clean_milestone_text("好的。"), "")

    def test_extract_merged_update_steps_and_prose_within_active_turn(self) -> None:
        records = [
            {"step_index": 1, "type": "USER_INPUT", "content": "old request"},
            {"step_index": 2, "type": "PLANNER_RESPONSE", "content": "旧回合总结，不该被带到新回合"},
            {"step_index": 10, "type": "USER_INPUT", "content": "new request"},
            {
                "step_index": 11,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-28T05:00:01Z",
                "tool_calls": [
                    {
                        "name": "update_steps",
                        "args": {
                            "steps": json.dumps(
                                [
                                    {"title": "Implement extractor", "status": "in_progress"},
                                    {"title": "Build popup", "status": "pending"},
                                ]
                            )
                        },
                    }
                ],
            },
        ]
        # Only pending/in_progress steps -> no premature milestone event
        self.assertIsNone(extract_milestone_from_transcript_records("conv-1", records, is_running=True))

        # Step 1 finishes WITH prose in the same PLANNER_RESPONSE -> merged unified event!
        records.append(
            {
                "step_index": 12,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-28T05:00:15Z",
                "content": "已完成第 1 步：双端提取器写完并通过校验，接下来接入遥测。",
                "tool_calls": [
                    {
                        "name": "update_steps",
                        "args": {
                            "steps": json.dumps(
                                [
                                    {"title": "Implement extractor", "status": "done"},
                                    {"title": "Build popup", "status": "in_progress"},
                                ]
                            )
                        },
                    }
                ],
            }
        )
        ev = extract_milestone_from_transcript_records("conv-1", records, is_running=True)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.kind, "progress")
        self.assertEqual(ev.title, "Implement extractor")
        self.assertEqual(ev.step_done, 1)
        self.assertEqual(ev.step_total, 2)
        self.assertEqual(ev.next_step, "Build popup")
        self.assertIn("双端提取器写完", ev.body)

        # Step 2 finishes WITHOUT prose -> step_done event
        records.append(
            {
                "step_index": 13,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-28T05:00:30Z",
                "tool_calls": [
                    {
                        "name": "update_steps",
                        "args": {
                            "steps": json.dumps(
                                [
                                    {"title": "Implement extractor", "status": "done"},
                                    {"title": "Build popup", "status": "done"},
                                ]
                            )
                        },
                    }
                ],
            }
        )
        ev2 = extract_milestone_from_transcript_records("conv-1", records, is_running=True)
        self.assertIsNotNone(ev2)
        self.assertEqual(ev2.kind, "step_done")
        self.assertEqual(ev2.title, "Build popup")
        self.assertEqual(ev2.step_done, 2)
        self.assertEqual(ev2.step_total, 2)
        self.assertEqual(ev2.next_step, "")

        # Final summary when turn stops -> kind == "summary"
        records.append(
            {
                "step_index": 14,
                "type": "PLANNER_RESPONSE",
                "created_at": "2026-11-28T05:00:45Z",
                "content": "全部功能已完成并跑通测试，可以体验新的阶段成果弹窗啦。",
            }
        )
        ev3 = extract_milestone_from_transcript_records("conv-1", records, is_running=False)
        self.assertIsNotNone(ev3)
        self.assertEqual(ev3.kind, "summary")
        self.assertIn("全部功能已完成", ev3.body)

    def test_extract_from_rpc_steps_and_large_transcript_tail(self) -> None:
        rpc_steps = [
            {"type": "CORTEX_STEP_TYPE_USER_INPUT", "userInput": {"items": [{"text": "build feature"}]}},
            {
                "type": "CORTEX_STEP_TYPE_PLANNER_RESPONSE",
                "metadata": {"finishedGeneratingAt": "2026-11-28T05:01:00Z"},
                "plannerResponse": {
                    "response": "已定位问题根因，正在补齐回归测试。",
                    "toolCalls": [
                        {
                            "name": "update_steps",
                            "argumentsJson": json.dumps(
                                {
                                    "steps": [
                                        {"title": "Diagnose crash", "status": "done"},
                                        {"title": "Add tests", "status": "in_progress"},
                                    ]
                                }
                            ),
                        }
                    ],
                },
            },
        ]
        ms = extract_milestone_from_rpc_steps("rpc-1", rpc_steps, is_running=True)
        self.assertIsNotNone(ms)
        self.assertEqual(ms.kind, "progress")
        self.assertEqual(ms.title, "Diagnose crash")
        self.assertEqual(ms.step_done, 1)
        self.assertEqual(ms.step_total, 2)
        self.assertEqual(ms.next_step, "Add tests")

        with tempfile.TemporaryDirectory(prefix="agy-ms-tail-") as tmp:
            path = Path(tmp) / "transcript.jsonl"
            filler = json.dumps({"step_index": 0, "type": "GENERIC", "content": "x" * 2000})
            tail_rec = json.dumps(
                {
                    "step_index": 99,
                    "type": "PLANNER_RESPONSE",
                    "created_at": "2026-11-28T05:02:00Z",
                    "content": "大日志尾读校验通过：成功提取最新阶段成果。",
                },
                ensure_ascii=False,
            )
            path.write_text("\n".join([filler] * 120 + [tail_rec]) + "\n", encoding="utf-8")
            got = read_latest_milestone_from_transcript("tail-1", path, is_running=False, tail_bytes=16384)
            self.assertIsNotNone(got)
            self.assertEqual(got.kind, "summary")
            self.assertIn("大日志尾读校验通过", got.body)


class MilestoneReactionAndTelemetryTests(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("auto")

    def test_baseline_seeding_dedupe_and_turn_finish_coalescing(self) -> None:
        i18n.set_language("zh")
        tracker = ReactionTracker(random.Random(7), cooldown_seconds=0.0)
        old_ms = MilestoneEvent(id="c1:2:summary:old11111", kind="summary", body="旧会话历史成果", created_ms=1000)

        # 1. Startup poll with stale historical milestone -> silent baseline, zero popup!
        r0 = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="IDLE", cumulative_total_tokens=10_000, milestone=old_ms),
            now=10.0,
            follow_model=False,
            current_form="carbon",
        )
        self.assertFalse(any(r.kind == "milestone" for r in r0))

        # 2. Turn starts -> running
        tracker.observe(
            LiveSnapshot(
                source="pet_live",
                conversation_id="c1",
                status="CASCADE_RUN_STATUS_RUNNING",
                cumulative_total_tokens=10_000,
                milestone=old_ms,
            ),
            now=20.0,
            follow_model=False,
            current_form="carbon",
        )

        # 3. Mid-turn progress arrives -> emits milestone reaction!
        mid_ms = MilestoneEvent(
            id="c1:12:progress:mid22222",
            kind="progress",
            title="修复崩溃",
            body="已修复悬停空指针，正在跑全量回归测试。",
            created_ms=2000,
            step_done=1,
            step_total=3,
            next_step="运行测试",
        )
        r_mid = tracker.observe(
            LiveSnapshot(
                source="pet_live",
                conversation_id="c1",
                status="CASCADE_RUN_STATUS_RUNNING",
                cumulative_total_tokens=18_000,
                milestone=mid_ms,
            ),
            now=25.0,
            follow_model=False,
            current_form="carbon",
        )
        ms_reactions = [r for r in r_mid if r.kind == "milestone"]
        self.assertEqual(len(ms_reactions), 1)
        self.assertEqual(ms_reactions[0].milestone, mid_ms)

        # 4. Same content with different id from alternate source within 20s -> deduped!
        dup_ms = MilestoneEvent(
            id="c1:x:progress:dup99999",
            kind="progress",
            title="修复崩溃",
            body="已修复悬停空指针，正在跑全量回归测试。",
            created_ms=2100,
            step_done=1,
            step_total=3,
        )
        r_dup = tracker.observe(
            LiveSnapshot(
                source="transcript",
                conversation_id="c1",
                status="CASCADE_RUN_STATUS_RUNNING",
                cumulative_total_tokens=18_000,
                milestone=dup_ms,
            ),
            now=27.0,
            follow_model=False,
            current_form="carbon",
        )
        self.assertFalse(any(r.kind == "milestone" for r in r_dup))

        # 5. Turn finishes WITH final summary -> coalesced into one milestone reaction with token meta (no duplicate 'finished')
        end_ms = MilestoneEvent(
            id="c1:15:summary:end33333",
            kind="summary",
            body="已提交合并并推送到 main，265 项测试全绿。",
            created_ms=3000,
        )
        r_end = tracker.observe(
            LiveSnapshot(
                source="pet_live",
                conversation_id="c1",
                status="CASCADE_RUN_STATUS_IDLE",
                cumulative_total_tokens=34_000,
                avg_decode_tps=135.0,
                milestone=end_ms,
            ),
            now=40.0,
            follow_model=False,
            current_form="carbon",
        )
        kinds = [r.kind for r in r_end]
        self.assertIn("milestone", kinds)
        self.assertNotIn("finished", kinds)
        end_reaction = next(r for r in r_end if r.kind == "milestone")
        self.assertEqual(end_reaction.action, "CELEBRATE")
        self.assertIn("24.0k", end_reaction.meta)
        self.assertIn("135", end_reaction.meta)

        # 6. Switching to another conversation with existing milestone -> silent baseline, no replay
        other_ms = MilestoneEvent(id="c2:5:summary:oth44444", kind="summary", body="另一个会话的历史成果", created_ms=1500)
        r_sw = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c2", status="IDLE", milestone=other_ms),
            now=50.0,
            follow_model=False,
            current_form="carbon",
        )
        self.assertFalse(any(r.kind == "milestone" for r in r_sw))

    def test_disabled_progress_bubbles_preserves_normal_finished_reaction(self) -> None:
        tracker = ReactionTracker(random.Random(3), cooldown_seconds=0.0)
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", status="CASCADE_RUN_STATUS_RUNNING", cumulative_total_tokens=5000),
            now=10.0,
            follow_model=False,
            current_form="carbon",
            progress_bubbles=False,
        )
        end_ms = MilestoneEvent(id="c1:8:summary:abc12345", kind="summary", body="本轮完成测试", created_ms=2000)
        r_end = tracker.observe(
            LiveSnapshot(
                source="pet_live",
                conversation_id="c1",
                status="CASCADE_RUN_STATUS_IDLE",
                cumulative_total_tokens=15_000,
                avg_decode_tps=120.0,
                milestone=end_ms,
            ),
            now=20.0,
            follow_model=False,
            current_form="carbon",
            progress_bubbles=False,
        )
        kinds = [r.kind for r in r_end]
        self.assertNotIn("milestone", kinds)
        self.assertIn("finished", kinds)

    def test_sidecar_snapshot_parses_milestone_and_falls_back_to_transcript(self) -> None:
        ms = MilestoneEvent(id="c1:4:step_done:abcd1234", kind="step_done", title="Run checks", body="Run checks", step_done=2, step_total=4)
        payload = {
            "activeConversationId": "c1",
            "active": {"conversationId": "c1", "title": "demo", "status": "CASCADE_RUN_STATUS_RUNNING", "milestone": ms.to_dict()},
            "conversations": [{"conversationId": "c1", "title": "demo", "status": "CASCADE_RUN_STATUS_RUNNING", "milestone": ms.to_dict()}],
        }
        snap = snapshot_from_hud_live(payload, source="pet_live")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.milestone, ms)
        self.assertEqual(milestone_from_dict(ms.to_dict()), ms)

        # Backwards compatibility: sidecar file without milestone field falls back to transcript.jsonl
        with tempfile.TemporaryDirectory(prefix="agy-ms-sidecar-") as tmp:
            root = Path(tmp)
            tr_path = root / "brain" / "c9" / ".system_generated" / "logs" / "transcript.jsonl"
            tr_path.parent.mkdir(parents=True, exist_ok=True)
            tr_path.write_text(
                json.dumps(
                    {
                        "step_index": 7,
                        "type": "PLANNER_RESPONSE",
                        "created_at": "2026-11-28T05:10:00Z",
                        "content": "离线兜底验证：旧版 sidecar 也能读到阶段成果。",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            collector = TelemetryCollector(app_data_root=root, use_language_server=False)
            collector.pet_live_path.parent.mkdir(parents=True, exist_ok=True)
            collector.pet_live_path.write_text(
                json.dumps(
                    {
                        "activeConversationId": "c9",
                        "active": {"conversationId": "c9", "title": "legacy sidecar", "status": "CASCADE_RUN_STATUS_IDLE"},
                        "conversations": [{"conversationId": "c9", "title": "legacy sidecar", "status": "CASCADE_RUN_STATUS_IDLE"}],
                    }
                ),
                encoding="utf-8",
            )
            live = collector.live_snapshot()
            self.assertIsNotNone(live)
            self.assertIsNotNone(live.milestone)
            self.assertIn("旧版 sidecar 也能读到阶段成果", live.milestone.body)


class MilestonePopupQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        i18n.set_language("auto")

    def test_popup_renders_all_kinds_languages_hover_pause_and_click_dismiss(self) -> None:
        popup = MilestonePopupWidget(topmost=True, reduced_motion=False)
        try:
            events = (
                MilestoneEvent(
                    id="m1",
                    kind="step_done",
                    title="Implement milestone extractor",
                    body="Implement milestone extractor",
                    step_done=1,
                    step_total=4,
                    next_step="Wire telemetry",
                ),
                MilestoneEvent(
                    id="m2",
                    kind="progress",
                    title="Wire telemetry",
                    body="双端遥测和反应追踪已打通，25 项定向测试通过。\n下一步开始做桌宠专属成果气泡弹窗。",
                    step_done=2,
                    step_total=4,
                    next_step="Build floating popup",
                ),
                MilestoneEvent(
                    id="m3",
                    kind="summary",
                    body="All milestone popup features are implemented and verified across zh, en, and ja locales.",
                ),
            )
            for lang in ("zh", "en", "ja"):
                i18n.set_language(lang)
                for ev in events:
                    meta = i18n.tr("milestone.turn_meta", total="1.8万", rate="145") if ev.kind == "summary" else ""
                    popup.show_milestone(ev, meta=meta, duration=8.0, now=100.0)
                    popup.follow_pet(QRect(420, 420, 200, 260), anchor_top=400)
                    popup.tick(now=100.5)
                    self.assertTrue(popup.isVisible())
                    img = QImage(popup.size(), QImage.Format.Format_ARGB32_Premultiplied)
                    img.fill(0)
                    popup.render(img)
                    self.assertGreater(popup.width(), 200)
                    self.assertGreater(popup.height(), 70)

            # Hover pauses countdown
            popup.show_milestone(events[1], duration=6.0, now=200.0)
            popup.tick(now=201.0)
            before_hover = popup.remaining_seconds
            popup.enterEvent(QEnterEvent(QPointF(20, 20), QPointF(20, 20), QPointF(20, 20)))
            self.assertTrue(popup.paused_by_hover)
            popup.tick(now=205.0)
            self.assertAlmostEqual(popup.remaining_seconds, before_hover, places=3)

            # Leave resumes and clamps >= 2.5s grace
            popup._remaining = 0.8
            popup.leaveEvent(QEvent(QEvent.Type.Leave))
            self.assertFalse(popup.paused_by_hover)
            self.assertGreaterEqual(popup.remaining_seconds, 2.5)

            # Top-edge pet position stays inside available screen geometry
            popup.follow_pet(QRect(120, 4, 200, 240), anchor_top=2)
            self.assertGreaterEqual(popup.y(), 0)

            # Click dismisses cleanly
            popup.set_reduced_motion(True)
            click_ev = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(24, 24),
                QPointF(24, 24),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            popup.mousePressEvent(click_ev)
            self.assertFalse(popup.isVisible())
        finally:
            popup.dismiss(immediate=True)
            popup.close()

    def test_pet_window_shows_and_toggles_milestone_popup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agy-ms-win-") as tmpdir:
            paths = AppPaths(app_dir=Path(tmpdir), bundle_dir=ROOT)
            config = ConfigManager(paths.config_path)
            config.set_nested("agy", "telemetry_enabled", False, save=False)
            config.set_nested("awareness", "enabled", False, save=False)
            config.set_nested("agy", "reactions", False, save=False)
            config.set_nested("agy", "progress_bubbles", True, save=True)
            pet = PetWindow(paths, config)
            try:
                pet.telemetry.stop()
                pet.timer.stop()
                pet.persistence_timer.stop()
                pet.awareness_timer.stop()
                pet.surface_timer.stop()
                self.app.processEvents()

                # Seed empty active conversation first
                pet._on_live_snapshot(
                    LiveSnapshot(source="pet_live", conversation_id="live-1", status="CASCADE_RUN_STATUS_RUNNING")
                )
                self.assertFalse(pet.milestone_popup.isVisible())

                # New milestone arrives -> opens popup even though general reactions=False
                ms = MilestoneEvent(
                    id="live-1:9:progress:feed1234",
                    kind="progress",
                    title="完成弹窗开发",
                    body="阶段成果气泡弹窗已完成接入，正在跑自动化测试。",
                    step_done=3,
                    step_total=5,
                    next_step="运行全量回归",
                )
                pet._on_live_snapshot(
                    LiveSnapshot(
                        source="pet_live",
                        conversation_id="live-1",
                        status="CASCADE_RUN_STATUS_RUNNING",
                        milestone=ms,
                    )
                )
                self.app.processEvents()
                self.assertTrue(pet.milestone_popup.isVisible())
                self.assertEqual(pet.milestone_popup.current_event, ms)
                self.assertTrue(pet.control_panel.progress_bubbles.isChecked())
                self.assertTrue(pet._tray_progress_action.isChecked())

                # Turning off progress_bubbles immediately dismisses popup and syncs UI
                pet.set_progress_bubbles(False)
                self.assertFalse(pet.milestone_popup.isVisible())
                self.assertFalse(pet.control_panel.progress_bubbles.isChecked())
                self.assertFalse(pet._tray_progress_action.isChecked())
            finally:
                pet.subagent_clones.close_all()
                pet.milestone_popup.dismiss(immediate=True)
                pet.milestone_popup.close()
                pet.hud_bar.hide()
                pet.token_meter.hide()
                pet.control_panel.hide()
                pet.food_panel.hide()
                pet.tray.hide()
                pet.hide()
                pet.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
