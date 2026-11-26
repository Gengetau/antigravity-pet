"""Standalone local rehearsal stage for previewing AGY Pet poses, particles,
subagent clones, edge docking, sulking mood ladder, and telemetry reactions
without running Antigravity.

Usage:
    py -3.13 tools/rehearsal_stage.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agy.characters import FORMS
from agy.reactions import greeting_for_moment
from agy.telemetry import LiveSnapshot, SubagentInfo
from animation.clip import PetAction
from app.paths import AppPaths
from pet.window import PetWindow
from settings.config import ConfigManager


class RehearsalStage(QWidget):
    def __init__(self, pet: PetWindow) -> None:
        super().__init__()
        self.pet = pet
        self.setWindowTitle("AGY 桌宠 · 本地排练舞台")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setSpacing(10)

        hint = QLabel("无需 Antigravity：一键预览形态、粒子特效、子代理分身、贴边探头与遥测反应。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # Forms
        form_box = QGroupBox("切换形态")
        form_row = QHBoxLayout(form_box)
        for form in FORMS:
            btn = QPushButton(form.name)
            btn.clicked.connect(lambda _c=False, fid=form.id: self.pet.set_form(fid, manual=True))
            form_row.addWidget(btn)
        root.addWidget(form_box)

        # Subagent clones & host-subagent interplay
        sub_box = QGroupBox("子代理迷你分身与主宠互动（复用五形态素材）")
        sub_col = QVBoxLayout(sub_box)
        sub_row = QHBoxLayout()
        for count in (0, 1, 2, 4, 5):
            btn = QPushButton(f"{count} 个分身")
            btn.clicked.connect(lambda _c=False, n=count: self._simulate_subagents(n))
            sub_row.addWidget(btn)
        sub_col.addLayout(sub_row)
        interplay_row = QHBoxLayout()
        for label, fn in (
            ("🎲 闲时随机玩伴", self._sim_idle_playmates),
            ("💖 摸摸分身", lambda: self._sim_clone_action("click")),
            ("📋 抛球汇报", lambda: self._sim_clone_action("report")),
            ("🤝 双向击掌", lambda: self._sim_clone_action("high_five")),
            ("🌟 抛星光球", lambda: self._sim_clone_action("relay")),
            ("💃 共舞派对", lambda: self._sim_clone_action("group_cheer")),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _c=False, cb=fn: cb())
            interplay_row.addWidget(btn)
        sub_col.addLayout(interplay_row)
        root.addWidget(sub_box)

        # Particles
        fx_box = QGroupBox("矢量粒子特效")
        fx_grid = QGridLayout(fx_box)
        for idx, (label, kind) in enumerate(
            (
                ("✨ 星星", "sparkles"),
                ("🎉 彩带", "confetti"),
                ("💖 爱心", "hearts"),
                ("💧 汗滴", "sweat"),
                ("🐟 小鱼干雨", "fish"),
                ("🔔 等待提醒波纹", "alert"),
            )
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _c=False, k=kind: self.pet.emit_particles(k))
            fx_grid.addWidget(btn, idx // 3, idx % 3)
        root.addWidget(fx_box)

        # Telemetry & emotion rehearsals
        ev_box = QGroupBox("遥测反应与互动彩排")
        ev_grid = QGridLayout(ev_box)
        scenarios = (
            ("🔔 等用户确认", self._sim_waiting),
            ("💥 任务出错", self._sim_error),
            ("⏳ 限额将重置", self._sim_reset_soon),
            ("🐟 限额刚补满", self._sim_quota_refilled),
            ("✦ AI 活台词", self._sim_ai_comment),
            ("🎄 春节/节日问候", self._sim_festival),
            ("👈 左侧贴边藏身", lambda: self.pet.dock_to_edge("left")),
            ("👉 右侧贴边藏身", lambda: self.pet.dock_to_edge("right")),
            ("↩ 回到屏幕", self.pet.undock_from_edge),
            ("😠 连戳闹别扭", self._sim_sulk),
            ("🥰 摸头哄好", self._sim_forgive),
            ("💻 细粒度写代码", self._sim_tool_writing),
        )
        for idx, (label, fn) in enumerate(scenarios):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _c=False, cb=fn: cb())
            ev_grid.addWidget(btn, idx // 3, idx % 3)
        root.addWidget(ev_box)

    def _simulate_subagents(self, count: int) -> None:
        presets = [
            SubagentInfo("sub-1", "main-1", "检索项目结构与依赖", "Gemini 4 Neon (High)", "neon"),
            SubagentInfo("sub-2", "main-1", "审查安全与边界条件", "Claude 4.5 Sonnet", "claude"),
            SubagentInfo("sub-3", "main-1", "运行回归测试套件", "Gemini 4 Hydrogen (Low)", "hydergon"),
            SubagentInfo("sub-4", "main-1", "分析慢查询日志", "Gemini 4 Argon", "argon"),
            SubagentInfo("sub-5", "main-1", "补充文档示例", "Gemini 4 Carbon", "carbon"),
        ]
        snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            title="排练舞台模拟会话",
            status="CASCADE_RUN_STATUS_RUNNING" if count > 0 else "CASCADE_RUN_STATUS_IDLE",
            selected_model_label="Gemini 4 Neon (High)",
            latest_tool_category="delegating" if count > 0 else "",
            active_subagents=presets[:count],
        )
        self.pet.telemetry.last_snapshot = snap
        self.pet._on_live_snapshot(snap)

    def _sim_idle_playmates(self) -> None:
        # Clear any simulated work subagents so idle random playmates take the stage.
        idle_snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            title="排练舞台模拟会话",
            status="CASCADE_RUN_STATUS_IDLE",
            active_subagents=[],
        )
        self.pet.telemetry.last_snapshot = idle_snap
        self.pet._on_live_snapshot(idle_snap)
        self.pet.summon_idle_playmates(count=2)

    def _sim_clone_action(self, kind: str) -> None:
        if self.pet.subagent_clones.active_count == 0:
            self._simulate_subagents(2)
        clones = self.pet.subagent_clones
        if kind == "click":
            clones.trigger_click(0)
        elif kind == "report":
            clones.trigger_report(0)
        elif kind == "high_five":
            clones.trigger_high_five(0)
        elif kind == "relay":
            clones.trigger_relay(0)
        elif kind == "group_cheer":
            clones.trigger_group_cheer()

    def _sim_waiting(self) -> None:
        snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            title="等待审批排练",
            status="CASCADE_RUN_STATUS_RUNNING",
            waiting_for_user=True,
            latest_tool_category="asking",
        )
        self.pet.reactions._was_waiting = False
        self.pet.reactions._last_at.pop("waiting", None)
        self.pet.telemetry.last_snapshot = snap
        self.pet._on_live_snapshot(snap)

    def _sim_error(self) -> None:
        self.pet.reactions._last_conversation = "rehearsal-1"
        self.pet.reactions._last_running = True
        self.pet.reactions._last_at.pop("turn_error", None)
        snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            status="CASCADE_RUN_STATUS_IDLE",
            termination_reason="ERROR",
        )
        self.pet.telemetry.last_snapshot = snap
        self.pet._on_live_snapshot(snap)

    def _sim_reset_soon(self) -> None:
        from datetime import timezone

        soon_iso = datetime.fromtimestamp(time.time() + 12 * 60, tz=timezone.utc).isoformat()
        self.pet.reactions._reset_soon_active = False
        self.pet.reactions._last_at.pop("quota_reset_soon", None)
        snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            status="CASCADE_RUN_STATUS_IDLE",
            quota_remaining_pct=28.0,
            quota_reset_time=soon_iso,
        )
        self.pet.telemetry.last_snapshot = snap
        self.pet._on_live_snapshot(snap)

    def _sim_quota_refilled(self) -> None:
        self.pet.reactions._last_quota_pct = 15.0
        self.pet.reactions._last_at.pop("quota_refilled", None)
        snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            status="CASCADE_RUN_STATUS_IDLE",
            quota_remaining_pct=100.0,
        )
        self.pet.telemetry.last_snapshot = snap
        self.pet._on_live_snapshot(snap)

    def _sim_ai_comment(self) -> None:
        snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            status="CASCADE_RUN_STATUS_IDLE",
            ai_comment_id=f"demo-{time.time_ns()}",
            ai_comment_text="✦ 这一波重构又稳又快，灯光给观众打满！",
            ai_comment_trigger="turn_done_big",
        )
        self.pet.telemetry.last_snapshot = snap
        self.pet._on_live_snapshot(snap)

    def _sim_festival(self) -> None:
        _kind, line, fx = greeting_for_moment(datetime(2026, 2, 17, 10, 0))
        if fx:
            self.pet.emit_particles(fx)
        self.pet._request_action(PetAction.CELEBRATE, reason="rehearsal_fest", force=True)
        self.pet.say(line, preserve_action=True)

    def _sim_sulk(self) -> None:
        self.pet._recent_pokes.clear()
        self.pet._sulk_until = 0.0
        self.pet._pending_click_region = "body"
        for _ in range(4):
            self.pet._do_click_reaction()

    def _sim_forgive(self) -> None:
        self.pet._pending_click_region = "head"
        self.pet._do_click_reaction()

    def _sim_tool_writing(self) -> None:
        snap = LiveSnapshot(
            source="pet_live",
            conversation_id="rehearsal-1",
            status="CASCADE_RUN_STATUS_RUNNING",
            latest_tool_name="edit_file",
            latest_tool_category="writing",
        )
        self.pet.telemetry.last_snapshot = snap
        self.pet._request_action(PetAction.WORKING, reason="rehearsal_tool", force=True)
        self.pet._refresh_control_panel()
        self.pet.say(f"当前状态：{self.pet._display_state_name()}", preserve_action=True)

    def closeEvent(self, event) -> None:
        self.pet.quit_app()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    with tempfile.TemporaryDirectory(prefix="agy-pet-rehearsal-") as tmp:
        paths = AppPaths(app_dir=Path(tmp), bundle_dir=ROOT)
        config = ConfigManager(paths.config_path)
        config.set_nested("agy", "telemetry_enabled", False, save=False)
        config.set_nested("awareness", "enabled", False, save=True)
        pet = PetWindow(paths, config)
        pet.telemetry.stop()
        stage = RehearsalStage(pet)
        stage.show()
        stage.move(80, 80)
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
