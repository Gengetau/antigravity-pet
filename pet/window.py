from __future__ import annotations

import ctypes
import math
import os
import random
import subprocess
import sys
import json
import time
import uuid
from collections import deque
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QWidget,
)

from app.paths import AppPaths
from app.recovery import RecoveryStatus
from agy.autonomy import AgyAutonomy, AutonomyCommand, AutonomyInput, WindowTarget, plan_hop
from agy.characters import FORMS, FORM_IDS, form_by_id, normalize_form
from agy.hud_bar import HudBar
from agy.reactions import ReactionTracker, TOOL_STATUS_NAMES, greeting_for_moment
from agy.service import TelemetryService
from agy.telemetry import SubagentInfo, TelemetryCollector
from agy.token_meter import TokenMeterWindow
from agy.windows import AntigravityWindowFinder
from awareness.privacy import PrivacyPolicy
from awareness.sensor import ContextSensor
from animation.asset_registry import BESPOKE_DOCK_ASSETS, DOCK_LEFT_ASSETS, EDGE_ASSETS, AssetRegistry
from animation.expressions import CALM, ExpressionDirector, ExpressionInput
from animation.clip import PetAction
from animation.player import AnimationPlayer
from animation.state_machine import ActionStateMachine, StateChange
from behavior.activity_director import (
    ActivityCommand,
    ActivityCueType,
    ActivityDirector,
    ActivityKind,
    MicroMotionDirector,
)
from behavior.behavior_engine import BehaviorEngine
from behavior.classifier import AppClassifier
from behavior.cooldown import Cooldown
from behavior.events import EventType
from behavior.scheduler import ContextEventScheduler
from dialogue.local_rules import DialogueManager
from dialogue.personality import normalize_personality
from pet.climb import JumpPlan, pick_jump, uncovered_top_span, ClimbController, Rect as ClimbRect, is_exposed, plan_climb
from pet.interaction import FoodPanel, InteractionController, parse_food_menu
from pet.movement import MovementController
from pet.particles import ParticleSystem
from pet.physics import PhysicsBounds, ThrowPhysics
from pet.renderer import Bubble, PetRenderer
from pet.state import PetStateStore
from pet.subagent_clones import MAX_VISIBLE_CLONES, PLAYMATE_PREFIX, CloneEvent, SubagentCloneManager
from pet.surfaces import DesktopSurfaceTracker
from settings.config import ConfigManager
from settings.panel import PetControlPanel


BUBBLE_HEIGHT = 66
MARGIN = 4
BASE_SPRITE_HEIGHT = 340
SIZE_LEVELS = {"小": 0.55, "中": 0.70, "大": 0.90}
TICK_MS = 20
BASELINE_WALK_SPEED = 82.0
EDGE_SIT_TUCK_PX = 5.0
PURR_HEART_INTERVAL_S = 0.55
DOCK_PEEK_EASE_RATE = 12.5

_DOCK_DIRECTIONAL_ACTIONS = frozenset(DOCK_LEFT_ASSETS) | {PetAction.DOCK_SLEEP}
_BESPOKE_DOCK_ASSET_IDS = frozenset(BESPOKE_DOCK_ASSETS) | {"dock_sleep", "dock_sleep_right"}
_EDGE_ACTION_ASSETS = {**EDGE_ASSETS, PetAction.PERCH_SLEEP: "perch_sleep"}
_SLEEP_ACTIONS = frozenset({PetAction.SLEEPING, PetAction.PERCH_SLEEP, PetAction.DOCK_SLEEP})
_RETURN_TO_WORKING_AFTER = frozenset({
    PetAction.HAPPY,
    PetAction.CELEBRATE,
    PetAction.TALKING,
    PetAction.WAVE,
})

# Bubble name-tag colour per form (readable on the white bubble).
ACCENTS = {"carbon": "#4b5563", "hydergon": "#2b8fd6", "neon": "#c026d3", "argon": "#8b5cf6", "claude": "#ea580c"}
# Agents that bring their own form when they report through the control API.

STATE_NAMES = {
    PetAction.IDLE: "待机",
    PetAction.BLINK: "眨眨眼",
    PetAction.GLANCE: "四处看看",
    PetAction.THINKING: "发呆",
    PetAction.WALKING: "散步",
    PetAction.HAPPY: "开心",
    PetAction.HEAD_PAT: "被摸摸",
    PetAction.TALKING: "说话",
    PetAction.ANGRY: "生气",
    PetAction.POKE_REACT: "被戳",
    PetAction.TAIL_REACT: "尾巴被碰",
    PetAction.EATING: "吃东西",
    PetAction.SWEEPING: "扫地",
    PetAction.SLEEPING: "睡觉",
    PetAction.DRAGGING: "抓取中",
    PetAction.FALLING: "落下",
    PetAction.LANDING: "着陆",
    PetAction.DIZZY: "眩晕",
    PetAction.WORKING: "陪你干活",
    PetAction.CELEBRATE: "庆祝",
    PetAction.TIRED: "没精神",
    PetAction.STRETCH: "伸懒腰",
    PetAction.TRANSFORM: "变身中",
    PetAction.WAVE: "打招呼",
    PetAction.PERCH: "坐在窗口上",
    PetAction.CLIMBING: "爬窗户",
    PetAction.SULK: "闹别扭中",
    PetAction.WAITING_USER: "等你确认啦",
    PetAction.JUMP_UP: "起跳",
    PetAction.PET_PURR: "享受摸头",
    PetAction.PERCH_SLEEP: "窗口打盹",
    PetAction.DOCK_SLEEP: "贴边打盹",
    PetAction.REFUSE_FOOD: "拒绝投喂",
}


class PetWindow(QWidget):
    """The transparent desktop pet window and the wiring between its modules."""

    def __init__(
        self,
        paths: AppPaths,
        config: ConfigManager,
        *,
        recovery_status: RecoveryStatus | None = None,
    ) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.get("topmost", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.paths = paths
        self.config = config
        self.recovery_status = recovery_status or RecoveryStatus()
        self.rng = random.Random()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("AGY 桌宠")

        self.current_height = self._height_for_size(
            self._normalized_size(config.get("size", 0.7))
        )
        self.form_id = normalize_form(self._agy().get("form"))
        self._pending_form: str | None = None
        self.asset_registry = self._load_registry(self.form_id)
        self.action_machine = ActionStateMachine(self.asset_registry.specs)
        self.player = AnimationPlayer()
        self._resize_window()

        comfort = config.section("comfort")
        self.movement = MovementController(
            config.get("mode", "wander"),
            speed=float(comfort.get("walk_speed", 82.0)),
            rng=self.rng,
        )
        self.physics = ThrowPhysics()
        self.climb = ClimbController()
        self._explore_next = time.monotonic() + 90.0
        self._perched_since: float | None = None
        self._descend_x: float | None = None
        self._explored_handle: int | None = None
        self._gentle_landing = False
        self._intentional_jump = False
        self._climb_pos = (0.0, 0.0)
        self._perch_after_landing = False
        self._hop_token = 0  # guards the delayed set_target(None) of older hops
        self._roam_next = 0.0  # next stroll / jump while standing on a window
        self._top_bounds_cache: tuple[int, float, tuple[float, float] | None] | None = None
        self._climb_metrics_cache: dict[tuple, tuple[float, float] | None] = {}
        self.interaction = InteractionController()
        self.renderer = PetRenderer(BUBBLE_HEIGHT, MARGIN)
        self.renderer.set_reduced_motion(bool(comfort.get("reduced_motion", False)))
        self.renderer.set_motion_scale(float(comfort.get("motion_scale", 0.4)))
        self.particles = ParticleSystem(self.rng)
        self.particles.enabled = bool(self._agy().get("particles", True))
        self.particles.reduced_motion = bool(comfort.get("reduced_motion", False))
        self.subagent_clones = SubagentCloneManager(
            self.paths.characters_root,
            self.paths.base_manifest_path,
            topmost=bool(config.get("topmost", True)),
            on_interaction=self._on_subagent_interaction,
            rng=self.rng,
        )
        self.subagent_clones.set_scale_from_host(self.current_height)
        self._handling_clone_interaction = False
        self._last_clone_banter_at = 0.0
        self._idle_play_clones: list[SubagentInfo] = []
        self._idle_play_until = 0.0
        self._idle_play_next_at = time.monotonic() + self._next_idle_play_delay(
            initial=True,
            activity_level=str(comfort.get("activity_level", "balanced")),
        )
        self._dock_side: str | None = None
        self._dock_screen = None
        self._dock_peeking = False
        self._dock_peek_progress = 0.0
        self._dock_leave_at = 0.0
        self._sulk_until = 0.0
        self._purring = False
        self._next_purr_heart_at = 0.0
        self._panel_open_pet_pos: QPoint | None = None
        self.expressions = ExpressionDirector()
        self.surface_tracker = DesktopSurfaceTracker(
            enabled=bool(comfort.get("desktop_surfaces", True))
        )
        self.bubble = Bubble()
        self._last_line = ""
        self._last_tick_at = time.monotonic()
        self._last_state_update = self._last_tick_at
        self._drag_offset: QPoint | None = None
        self._drag_last_pos: QPoint | None = None
        self._caught_throw = False
        self._pending_click_region = "body"
        self._hovered = False
        self._recent_pokes: deque[float] = deque(maxlen=8)
        self._recent_feedings: deque[float] = deque(maxlen=6)

        self.dialogue = DialogueManager(paths.assets_dir / "dialogue", self.rng)
        self._apply_form_voice(self.form_id)
        self.state_store = PetStateStore(paths.state_path)
        self.pet_state = self.state_store.load()
        self._first_session_today = self.pet_state.begin_session()
        activity_level = str(comfort.get("activity_level", "balanced"))
        self.activity_director = ActivityDirector(self.rng, activity_level=activity_level)
        self.micro_motion_director = MicroMotionDirector(
            self.rng,
            activity_level=activity_level,
        )

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._do_long_press_reaction)
        self._long_press_handled = False
        self.food_panel = FoodPanel(self.on_food)
        self.food_panel.set_menu(
            parse_food_menu(self._form_voice.get("food_menu")), ACCENTS.get(self.form_id, "#339ad5")
        )
        self.control_panel = PetControlPanel(
            on_mode=self.set_mode,
            on_size=self.set_size,
            on_feed=self._open_food_panel,
            on_say=self._say_daily_line,
            on_snap=self.snap_into_screen,
            on_awareness=self.set_awareness_enabled,
            on_read_window_title=lambda enabled: self._set_awareness_flag("read_window_title", enabled),
            on_idle_detection=lambda enabled: self._set_awareness_flag("idle_detection", enabled),
            on_topmost=self.set_topmost,
            on_fullscreen_hide=lambda enabled: self._set_awareness_flag("hide_on_fullscreen", enabled),
            on_passthrough=self.set_passthrough,
            on_autostart=self.set_autostart,
            on_activity_level=self.set_activity_level,
            on_walk_speed=self.set_walk_speed,
            on_reduced_motion=self.set_reduced_motion,
            on_hover_pause=self.set_hover_pause,
            on_desktop_surfaces=self.set_desktop_surfaces,
            on_action=self._preview_action,
            on_hide=self._hide_from_panel,
            on_privacy=self._show_privacy_notice,
            on_quit=self.quit_app,
            on_form=lambda form: self.set_form(form, manual=True),
            on_follow_model=self.set_follow_model,
            on_open_meter=self.open_token_meter,
            on_hud=self.set_hud_enabled,
            on_autonomy=self.set_autonomy,
            on_dock=self._toggle_edge_dock,
            on_perch=lambda: self._preview_action("EDGE_SIT"),
            on_recall_primary=self.recall_to_primary_screen,
            forms=tuple((form.id, form.name) for form in FORMS),
        )
        self._create_tray()
        self._create_agy()

        self._create_awareness()
        self._sync_animation_clip(crossfade=False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)

        self.persistence_timer = QTimer(self)
        self.persistence_timer.timeout.connect(self.save_snapshot)
        self.persistence_timer.start(30_000)

        self._restore_position()
        self.show()
        self.snap_into_screen()
        self._sync_awareness_timer()
        self._sync_surface_timer()
        QTimer.singleShot(1_600, self._show_startup_recovery_line)
        self._sync_hud_visibility()

    # ----- window and rendering -------------------------------------------------

    @staticmethod
    def _height_for_size(multiplier: float) -> int:
        return round(BASE_SPRITE_HEIGHT * float(multiplier))

    @staticmethod
    def _normalized_size(value: object) -> float:
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            return 0.70
        for multiplier in SIZE_LEVELS.values():
            if abs(candidate - multiplier) < 0.01:
                return multiplier
        return 0.70

    def _resize_window(self) -> None:
        widths = []
        for direction in ("left", "right", "up", "down"):
            # Special poses such as sleeping and being held can legitimately be
            # wider than the standing sprite.  Reserve their width up front so
            # switching action never crops arms, tail or the lower body.
            for action in PetAction:
                clip = self.asset_registry.clip_for(
                    action,
                    height=self.current_height,
                    direction=direction,
                )
                widths.extend(frame.pixmap.width() for frame in clip.frames)
        if not widths:
            raise RuntimeError("当前桌宠尺寸没有可用的精灵图。")
        horizontal_margin = int(self.current_height * 0.062) + 6
        self.setFixedSize(
            max(widths) + horizontal_margin * 2,
            self.current_height + BUBBLE_HEIGHT + MARGIN * 2 + 10,
        )

    def _restore_position(self) -> None:
        x, y = self.config.get("x"), self.config.get("y")
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.right() - self.width() + 1 - 80,
            geometry.bottom() - self.height() + 1 - 60,
        )

    def _ceiling_at(self, x: float, y: float) -> float:
        screen = QApplication.screenAt(QPoint(round(x), round(y))) or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return 0.0
        upper = QApplication.screenAt(QPoint(round(x), screen.geometry().top() - 2))
        if upper is not None and upper is not screen:
            return float(upper.availableGeometry().top())
        return float(screen.availableGeometry().top())

    def _window_work_area_top(self, left: float, top: float, right: float) -> float:
        return self._ceiling_at((left + right) / 2.0, top + 8.0)

    def _surface_work_area_top(self, surface) -> float:
        return self._window_work_area_top(surface.left, surface.top, surface.right)

    def _physics_bounds(self, lookahead_seconds: float = 0.0) -> PhysicsBounds:
        if self.physics.active:
            center_x, center_y = self.physics.projected_center(
                lookahead_seconds,
                self.width(),
                self.height(),
            )
            probe = QPoint(round(center_x), round(center_y))
        else:
            probe = self.frameGeometry().center()
        screen = QApplication.screenAt(probe) or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return PhysicsBounds(0.0, 0.0, float(self.width()), float(self.height()))
        geometry = screen.availableGeometry()
        work_areas = [candidate.availableGeometry() for candidate in QApplication.screens()]
        left = min((area.left() for area in work_areas), default=geometry.left())
        right = max((area.right() for area in work_areas), default=geometry.right())
        top = self._ceiling_at(float(probe.x()), float(probe.y()))
        return PhysicsBounds(
            float(left),
            float(top),
            float(right),
            float(geometry.bottom()),
            platforms=self.surface_tracker.physics_platforms(
                work_area_top=self._surface_work_area_top,
                widget_height=float(self.height()),
            ),
        )

    def _launch_throw(
        self,
        velocity_x: float,
        velocity_y: float,
        *,
        reason: str,
        intentional_jump: bool = False,
    ) -> None:
        self.surface_tracker.detach()
        self.movement.rest_after_drag()
        self.physics.launch(
            self.x(),
            self.y(),
            velocity_x,
            velocity_y,
            planned_jump=intentional_jump,
        )
        self._intentional_jump = bool(intentional_jump and velocity_y < 0.0)
        action = PetAction.JUMP_UP if self._intentional_jump else PetAction.FALLING
        self._request_action(
            action,
            reason=reason,
            force=True,
            immediate=True,
        )

    def emit_particles(self, effect: str | None) -> int:
        if not effect or not hasattr(self, "particles"):
            return 0
        self.particles.enabled = bool(self._agy().get("particles", True))
        self.particles.reduced_motion = self.renderer.reduced_motion
        count = self.particles.emit(
            effect,
            origin_x=self.width() / 2.0,
            origin_y=float(BUBBLE_HEIGHT + MARGIN) + self.current_height * 0.34,
            spread_w=max(80.0, self.width() * 0.65),
        )
        if count:
            self.update()
        return count

    def emit_relay_particles(self, *, from_side: int, accent: str = "#c084fc") -> int:
        if not hasattr(self, "particles"):
            return 0
        count = self.particles.emit_relay(
            from_side=from_side,
            target_x=self.width() / 2.0,
            target_y=float(BUBBLE_HEIGHT + MARGIN) + self.current_height * 0.42,
            spread_w=max(92.0, self.width() * 0.72),
            accent=accent,
        )
        if count:
            self.update()
        return count

    def paintEvent(self, _event) -> None:
        self._update_expression()
        dock_pose = (self._dock_side, self._dock_peek_progress) if self._dock_side is not None else None
        vis_x: tuple[float, float] | None = None
        clip_rect: QRect | None = None
        if self._dock_side is not None:
            area = self._screen_area_for_pet()
            if area is not None:
                vis_x = (
                    max(0.0, float(area.left() - self.x())),
                    min(float(self.width()), float(area.right() + 1 - self.x())),
                )
                local_area = QRect(
                    area.left() - self.x(),
                    area.top() - self.y(),
                    area.width(),
                    area.height(),
                )
                clip_rect = local_area.intersected(self.rect())
        self.renderer.paint(
            self,
            snapshot=self.player.snapshot(),
            bubble=self.bubble,
            particles=getattr(self, "particles", None),
            dock_pose=dock_pose,
            visible_x_range=vis_x,
            clip_rect=clip_rect,
        )

    _EXPRESSION_CUES = {
        PetAction.HAPPY: "happy",
        PetAction.CELEBRATE: "happy",
        PetAction.PET_PURR: "happy",
        PetAction.ANGRY: "pout",
        PetAction.SULK: "pout",
        PetAction.DIZZY: "worried",
    }

    def _update_expression(self) -> None:
        """Pick the idle face and hand it to the renderer (idle frame only)."""
        registry = getattr(self, "asset_registry", None)
        if not bool(self.config.section("comfort").get("expressions", True)) or registry is None:
            self.renderer.expression = None
            return
        if not registry.expression_names():
            self.renderer.expression = None
            return
        now = time.monotonic()
        telemetry = getattr(self, "telemetry", None)
        snapshot = telemetry.last_snapshot if telemetry is not None else None
        state = self.pet_state
        sulking = now < self._sulk_until or self.action_machine.current == PetAction.SULK
        self.expressions.update(
            ExpressionInput(
                now=now,
                hovered=False if sulking else self._hovered,
                running=bool(snapshot is not None and snapshot.running),
                quota_pct=getattr(snapshot, "quota_remaining_pct", None),
                mood=state.mood,
                energy=state.energy,
                annoyance=max(state.annoyance, 0.5) if sulking else state.annoyance,
                user_idle_seconds=getattr(self, "_last_user_idle", None),
            )
        )
        idle_asset = registry.resolve_asset_id(registry.specs[PetAction.IDLE].asset_id)
        layer = self.player.snapshot().current
        height = layer.frame.pixmap.height() if layer is not None and layer.asset_id == idle_asset else 238

        def face(name: str):
            return None if name == CALM else registry.expression_pixmap(name, height)

        director = self.expressions
        self.renderer.expression = (
            idle_asset,
            face(director.current),
            face(director.previous),
            director.fade(now),
        )

    def _set_direction(self, direction: str, facing: int | None = None) -> None:
        if self.movement.set_direction(direction, facing):
            self._sync_animation_clip()

    def _resolve_sleep_action(self, action: PetAction) -> PetAction:
        if action != PetAction.SLEEPING:
            return action
        if self._dock_side is not None:
            return PetAction.DOCK_SLEEP
        if self.surface_tracker.attached:
            return PetAction.PERCH_SLEEP
        return action

    def _is_agy_actively_working(self) -> bool:
        if not bool(self._agy().get("autonomy", True)):
            return False
        telemetry = getattr(self, "telemetry", None)
        snap = telemetry.last_snapshot if telemetry is not None else None
        return bool(snap is not None and getattr(snap, "running", False))

    def _sync_animation_clip(
        self,
        *,
        crossfade: bool = True,
        immediate: bool = False,
    ) -> None:
        current = self.action_machine.current
        direction = self.movement.direction
        if self._dock_side is not None and current in _DOCK_DIRECTIONAL_ACTIONS:
            direction = f"dock_{self._dock_side}"
        elif current in _EDGE_ACTION_ASSETS and self.surface_tracker.attached:
            direction = "edge"
        elif current == PetAction.CLIMBING and self.climb.plan is not None:
            direction = self.climb.plan.facing
        program = self.asset_registry.program_for(
            current,
            height=self.current_height,
            direction=direction,
        )
        self.player.play(program, crossfade=crossfade, immediate=immediate)
        if self._dock_side is not None:
            target_x = self._dock_target_x(self._dock_side, peek=self._dock_peek_progress)
            if target_x != self.x():
                self.move(target_x, self.y())
        # Sitting over the edge sits lower than standing on it: re-place immediately
        # to eliminate 1-frame perch flashes, and schedule a fresh Win32 read.
        self._sync_attached_y_now()
        self.surface_tracker.refresh_soon()
        self._refresh_control_panel()

    def _request_action(
        self,
        action: PetAction,
        *,
        now: float | None = None,
        reason: str,
        force: bool = False,
        immediate: bool = False,
    ) -> bool:
        now = time.monotonic() if now is None else now
        action = self._resolve_sleep_action(action)
        change = self.action_machine.request(action, now=now, reason=reason, force=force)
        if change is None:
            return False
        if self._edge_change(change):
            # Sitting over the edge sits lower: cut, don't crossfade, or the
            # outgoing pose shows sunk into (or floating above) the window.
            immediate = True
            spec = self.action_machine.specs.get(change.current)
            if change.previous in {PetAction.PERCH, PetAction.WORKING} and spec is not None and not spec.loop:
                # A poke, a word, a blink: then back to sitting on the edge.
                self.action_machine.queue_after_current(change.previous)
            elif change.previous == PetAction.PERCH_SLEEP and spec is not None and not spec.loop:
                self.action_machine.queue_after_current(PetAction.PERCH)
        cue = self._EXPRESSION_CUES.get(action)
        if cue and hasattr(self, "expressions"):
            self.expressions.cue(cue, now)
        self._sync_animation_clip(immediate=immediate)
        if (
            not getattr(self, "_handling_clone_interaction", False)
            and hasattr(self, "subagent_clones")
            and self.subagent_clones.active_count > 0
        ):
            self.subagent_clones.notify_host_action(
                action,
                now=now,
                reduced_motion=self.renderer.reduced_motion,
            )
        return True

    def _refresh_control_panel(self) -> None:
        awareness = self.config.section("awareness")
        comfort = self.config.section("comfort")
        self.control_panel.sync(
            mode=self.movement.mode,
            size=self._normalized_size(self.config.get("size", 0.70)),
            awareness=bool(awareness.get("enabled", True)),
            read_window_title=bool(awareness.get("read_window_title", True)),
            idle_detection=bool(awareness.get("idle_detection", True)),
            topmost=bool(self.config.get("topmost", True)),
            fullscreen_hide=bool(awareness.get("hide_on_fullscreen", False)),
            passthrough=bool(self.config.get("passthrough", False)),
            autostart=bool(self.config.get("autostart", False)),
            activity_level=str(comfort.get("activity_level", "balanced")),
            walk_speed=float(comfort.get("walk_speed", 82.0)),
            reduced_motion=bool(comfort.get("reduced_motion", False)),
            hover_pause=bool(comfort.get("hover_pause", True)),
            desktop_surfaces=bool(comfort.get("desktop_surfaces", True)),
            state_name=self._display_state_name(),
            form=self.form_id,
            follow_model=bool(self._agy().get("follow_model", False)),
            hud_enabled=bool(self._agy().get("hud_enabled", True)),
            autonomy=bool(self._agy().get("autonomy", True)),
        )

    def _display_state_name(self) -> str:
        if self._dock_side is not None:
            return "探头看你" if self._dock_peeking else "贴边藏身"
        if time.monotonic() < self._sulk_until:
            return "闹别扭中"
        telemetry = getattr(self, "telemetry", None)
        snap = telemetry.last_snapshot if telemetry is not None else None
        if snap is not None and getattr(snap, "waiting_for_user", False):
            return TOOL_STATUS_NAMES["asking"]
        tool_category = getattr(snap, "latest_tool_category", "") if snap is not None else ""
        if (
            self.action_machine.current == PetAction.WORKING
            and tool_category in TOOL_STATUS_NAMES
        ):
            return TOOL_STATUS_NAMES[tool_category]
        if self.action_machine.current != PetAction.IDLE:
            return STATE_NAMES.get(self.action_machine.current, "待机")
        return {
            "tired": "有点困",
            "annoyed": "闹脾气",
            "restless": "想走走",
            "cheerful": "心情很好",
            "affectionate": "很亲近",
            "steady": "待机",
        }.get(self.pet_state.visible_condition(), "待机")

    def _open_food_panel(self) -> None:
        self._interrupt_activity()
        if self._dock_side is not None:
            self.undock_from_edge(fall_if_airborne=False)
        self.food_panel.popup_at(
            self.x() + self.width() / 2,
            self.y() + BUBBLE_HEIGHT,
        )

    def _say_daily_line(self) -> None:
        self.say(self.dialogue.pick_daily(personality=self._personality()))

    def _preview_action(self, raw_action: str) -> None:
        if raw_action == "EDGE_DOCK":
            self._toggle_edge_dock()
            return
        if raw_action in {"CLIMB", "EDGE_SIT"}:
            if self._dock_side is not None:
                self.undock_from_edge(fall_if_airborne=False)
            self._panel_climb(sit_after=raw_action == "EDGE_SIT")
            return
        try:
            action = PetAction.coerce(raw_action)
        except ValueError:
            return
        self._interrupt_activity()
        if self._dock_side is not None and action != PetAction.DOCK_SLEEP:
            self.undock_from_edge(fall_if_airborne=False)
        if action in _SLEEP_ACTIONS:
            self.movement.rest_after_drag()
        self._intentional_jump = False
        self.physics.cancel()
        self._request_action(action, reason="panel_preview", force=True, immediate=True)

    def _hide_from_panel(self) -> None:
        self.control_panel.hide()
        self.hide()
        self._sync_subagent_clones()

    # ----- main animation loop --------------------------------------------------

    def tick(self) -> None:
        now = time.monotonic()
        delta_seconds = min(0.10, max(0.001, now - self._last_tick_at))
        self._last_tick_at = now
        frame_rate_scale = 1.0
        if self.action_machine.current == PetAction.WALKING:
            actual_speed = (
                self.movement.current_speed
                if self.movement.current_speed > 1.0
                else self.movement.speed
            )
            frame_rate_scale = max(0.55, min(1.8, actual_speed / BASELINE_WALK_SPEED))
        self.player.tick(delta_seconds, frame_rate_scale=frame_rate_scale)
        self.particles.update(delta_seconds)
        change = self.action_machine.update(
            now=now,
            hold_duration=self.player.in_exit_transition,
        )
        if change is not None:
            if (
                change.current == PetAction.IDLE
                and change.previous in _RETURN_TO_WORKING_AFTER
                and self._is_agy_actively_working()
                and now >= self._sulk_until
            ):
                working_change = self.action_machine.request(
                    PetAction.WORKING,
                    now=now,
                    reason="resume_working",
                    force=True,
                )
                if working_change is not None:
                    change = StateChange(
                        change.previous,
                        working_change.current,
                        working_change.reason,
                    )
            self._sync_animation_clip(immediate=self._edge_change(change))
        if (
            self._purring
            and self.interaction.active
            and not self.interaction.dragging
            and self.action_machine.current == PetAction.PET_PURR
            and now >= self._next_purr_heart_at
        ):
            self.emit_particles("hearts")
            self._next_purr_heart_at = now + PURR_HEART_INTERVAL_S
        sulking = now < self._sulk_until
        if sulking:
            if self.activity_director.active:
                self.activity_director.interrupt(
                    now=now,
                    delay_seconds=max(1.0, self._sulk_until - now),
                )
            if (
                self._dock_side is None
                and not self.physics.active
                and not self.interaction.active
                and not self.climb.active
                and self.action_machine.current == PetAction.IDLE
            ):
                self._request_action(PetAction.SULK, now=now, reason="sulk_hold", force=True)
        elif (
            self.action_machine.current == PetAction.SULK
            and not self.activity_director.active
        ):
            self._request_action(
                PetAction.PERCH if self.surface_tracker.attached else PetAction.IDLE,
                now=now,
                reason="sulk_expired",
                force=True,
            )
        if self._dock_side is not None and not self.interaction.active:
            self._tick_edge_dock(now, delta_seconds=delta_seconds)
        if not self.physics.active and not self.interaction.active and self._dock_side is None:
            attachment = self.surface_tracker.follow_attachment(
                now=now,
                widget_x=float(self.x()),
                widget_width=float(self.width()),
                widget_height=float(self.height()),
                sink=self._edge_sit_sink(),
                work_area_top=self._surface_work_area_top,
                pet_x=float(self.x()) + self.width() / 2.0,
                ignore_handles=self._own_window_handles(),
            )
            if attachment is not None:
                if attachment.lost:
                    if self.y() < round(attachment.y):
                        self.move(self.x(), round(attachment.y))
                    self._gentle_landing = True
                    self._launch_throw(0.0, 0.0, reason="surface_lost")
                    self._schedule_routine_line("window_lost", delay_ms=900)
                else:
                    self.move(round(attachment.x), round(attachment.y))
        walking = False
        movable_actions = {PetAction.IDLE, PetAction.THINKING, PetAction.WALKING}
        cue = self.activity_director.current_cue
        activity_allows_movement = (
            not self.activity_director.active
            or (cue is not None and cue.kind == ActivityCueType.WALK)
        )
        hover_paused = self._hovered and bool(
            self.config.section("comfort").get("hover_pause", True)
        )
        if self.physics.active:
            self._tick_throw(delta_seconds, now)
        elif self.climb.active and not self.interaction.active:
            walking = self._tick_climb(delta_seconds, now)
        elif self._descend_x is not None and not self.interaction.active:
            walking = self._tick_descend(delta_seconds, now)
        elif (
            not self.interaction.active
            and self._dock_side is None
            and not sulking
            and not self._purring
            and not hover_paused
            and activity_allows_movement
            and self.action_machine.current in movable_actions
        ):
            walking = self.movement.update(
                self,
                now=now,
                delta_seconds=delta_seconds,
                set_direction=self._set_direction,
                energy=self.pet_state.energy,
                horizontal_bounds=self._top_bounds(now),
            )
            if self.surface_tracker.attached:
                self.surface_tracker.record_pet_position(
                    widget_x=float(self.x()),
                    widget_width=float(self.width()),
                )
        if walking:
            self._request_action(PetAction.WALKING, now=now, reason="movement")
        elif not self.interaction.dragging and self.action_machine.current == PetAction.WALKING:
            self._request_action(PetAction.IDLE, now=now, reason="movement_stop", force=True)
        self._tick_activity(now)
        self._tick_micro_motion(now)
        if self._pending_form and not self.physics.active and not self.interaction.active and not self.climb.active:
            pending, self._pending_form = self._pending_form, None
            self.set_form(pending, announce=False)
        self._follow_hud()
        self._tick_idle_playmates(now)
        if self.subagent_clones.active_count > 0 or getattr(self.subagent_clones, "has_departing", False):
            if not self.isVisible() or self.isMinimized():
                self._sync_subagent_clones()
            else:
                self.subagent_clones.position_around(
                    self._sprite_rect(),
                    now=now,
                    reduced_motion=self.renderer.reduced_motion,
                    screen=self._screen_for_pet(),
                    dock_edge=self._dock_edge,
                    perched_window_rect=self._attached_window_qrect(),
                )
        self._maybe_auto_hide_control_panel()
        if now >= getattr(self, "_next_config_poll", 0.0):
            self._next_config_poll = now + 1.5
            self._sync_external_config()
        self._tick_autonomy(now)
        if self._dock_side is None:
            self._tick_explore(now)
        if now - self._last_state_update >= 5.0:
            self.pet_state.advance(
                now - self._last_state_update,
                activity=self.action_machine.current.value.lower(),
            )
            self._last_state_update = now
        self.update()

    def _tick_throw(self, delta_seconds: float, now: float) -> None:
        step = self.physics.step(
            delta_seconds,
            width=self.width(),
            height=self.height(),
            bounds=self._physics_bounds(delta_seconds),
        )
        self.move(round(step.x), round(step.y))
        if not step.settled:
            if (
                self._intentional_jump
                and step.velocity_y >= 0.0
                and self.action_machine.current == PetAction.JUMP_UP
            ):
                self._intentional_jump = False
                self._request_action(
                    PetAction.FALLING,
                    now=now,
                    reason="jump_apex",
                    force=True,
                    immediate=True,
                )
            return

        self._intentional_jump = False
        self._settle_landing(step.landed_surface_id, hard=step.hard_landing, now=now)

    def _settle_landing(self, surface_id: str | None, *, hard: bool, now: float, quiet: bool = False) -> None:
        """Feet down after a throw, a hop or a climb: attach, land, maybe sit."""
        self.movement.rest_after_drag(now)
        self._set_direction("down")
        if surface_id:
            if not self.surface_tracker.attach(
                surface_id,
                widget_x=float(self.x()),
                widget_width=float(self.width()),
                widget_height=float(self.height()),
                work_area_top=self._surface_work_area_top,
            ):
                self._perch_after_landing = False
                self._gentle_landing = True
                self._launch_throw(0.0, 0.0, reason="surface_lost")
                return
        else:
            self.surface_tracker.detach()
        hard = hard and not self._gentle_landing
        self._gentle_landing = False
        self._top_bounds_cache = None
        if surface_id:
            self._roam_next = now + self.rng.uniform(25.0, 50.0)
        if self._request_action(
            PetAction.LANDING,
            now=now,
            reason="hard_landing" if hard else "landing",
            force=True,
            immediate=True,
        ) and hard:
            self.action_machine.queue_after_current(PetAction.DIZZY)
        if surface_id and self._perch_after_landing:
            self.action_machine.queue_after_current(PetAction.PERCH)
        self._perch_after_landing = False
        if quiet:
            return
        if surface_id:
            self._schedule_routine_line("window_land", delay_ms=1_100)
        elif hard:
            self._schedule_routine_line("hard_landing", delay_ms=2_200)
        else:
            self._schedule_routine_line("soft_landing", delay_ms=1_000)

    def _tick_activity(self, now: float) -> None:
        hover_paused = self._hovered and bool(
            self.config.section("comfort").get("hover_pause", True)
        )
        command = self.activity_director.update(
            now=now,
            state=self.pet_state,
            can_start=(
                self.action_machine.current == PetAction.IDLE
                and self._dock_side is None
                and now >= self._sulk_until
                and not self._purring
                and not self.interaction.active
                and not self.movement.is_walking
                and not self.control_panel.isVisible()
                and not self.food_panel.isVisible()
                and not hover_paused
            ),
            is_walking=self.movement.is_walking,
            allow_movement=self.movement.mode == "wander",
        )
        if command is not None:
            self._execute_activity_command(command, now)

    def _tick_micro_motion(self, now: float) -> None:
        comfort = self.config.section("comfort")
        hover_paused = self._hovered and bool(comfort.get("hover_pause", True))
        action = self.micro_motion_director.update(
            now=now,
            state=self.pet_state,
            can_start=(
                self.action_machine.current == PetAction.IDLE
                and self._dock_side is None
                and now >= self._sulk_until
                and not self._purring
                and not self.activity_director.active
                and not self.interaction.active
                and not self.movement.is_walking
                and not self.physics.active
                and not self.control_panel.isVisible()
                and not self.food_panel.isVisible()
                and not hover_paused
            ),
            reduced_motion=bool(comfort.get("reduced_motion", False)),
        )
        if action is not None:
            self._request_action(action, now=now, reason="idle_micro_motion")

    def _execute_activity_command(self, command: ActivityCommand, now: float) -> None:
        reason = f"activity_{command.activity.value}"
        if command.cue_type == ActivityCueType.COMPLETE:
            self.pet_state.finish_activity(command.activity.value)
            if (
                command.activity == ActivityKind.WITHDRAW
                and now >= self._sulk_until
                and self.action_machine.current == PetAction.SULK
            ):
                self._request_action(
                    PetAction.PERCH if self.surface_tracker.attached else PetAction.IDLE,
                    now=now,
                    reason="withdraw_complete",
                    force=True,
                )
            return
        if command.cue_type == ActivityCueType.WALK:
            started = self.movement.request_short_wander(
                self,
                body_widths=command.distance_body_widths,
                now=now,
                away_from_cursor=command.away_from_cursor,
                horizontal_bounds=self._top_bounds(now),
            )
            if not started:
                self.activity_director.skip_walk(now=now)
            return
        if command.cue_type == ActivityCueType.SPEAK:
            personality = self._personality()
            condition = self.pet_state.visible_condition()
            line = None
            if condition != "steady" and self.rng.random() < 0.72:
                line = self.dialogue.pick_state(condition, personality=personality)
            if line is None:
                line = (
                    self.dialogue.pick_inner_voice(personality=personality)
                    if command.inner
                    else self.dialogue.pick_daily(personality=personality)
                )
            self.say(line, inner=command.inner, from_activity=True)
            return
        if command.action is None:
            self.activity_director.interrupt(now=now)
            return
        requested_action = (
            PetAction.SULK
            if command.activity == ActivityKind.WITHDRAW and command.action == PetAction.THINKING
            else command.action
        )
        effective_action = self._resolve_sleep_action(requested_action)
        changed = self._request_action(requested_action, now=now, reason=reason)
        if not changed and self.action_machine.current != effective_action:
            self.activity_director.interrupt(now=now)

    def _interrupt_activity(self, *, delay_seconds: float | None = None) -> None:
        now = time.monotonic()
        interrupted = self.activity_director.interrupt(
            now=now,
            delay_seconds=delay_seconds,
        )
        self.micro_motion_director.defer(now, minimum_seconds=3.0)
        self.movement.cancel_target()
        if interrupted is not None and self.action_machine.current in _SLEEP_ACTIONS:
            fallback = PetAction.PERCH if self.surface_tracker.attached else PetAction.IDLE
            self._request_action(fallback, reason="activity_interrupted", force=True)

    def say(
        self,
        text: str | None,
        *,
        inner: bool = False,
        from_activity: bool = False,
        preserve_action: bool = False,
    ) -> bool:
        if not from_activity:
            self._interrupt_activity()
        if not text or text == self._last_line:
            return False
        self._last_line = text
        if not preserve_action:
            action = PetAction.THINKING if inner else PetAction.TALKING
            self._request_action(action, reason="inner_voice" if inner else "speech")
        now = time.monotonic()
        display_seconds = min(5.4, max(2.9, 1.9 + len(text) * 0.18))
        self.bubble = Bubble(
            text=f"（{text}）" if inner else text,
            until=now + display_seconds,
            appeared_at=now,
            inner=inner,
            state_name=STATE_NAMES.get(self.action_machine.current, ""),
        )
        self.update()
        return True

    def _schedule_routine_line(self, situation: str, *, delay_ms: int) -> None:
        def speak() -> None:
            line = self.dialogue.pick_routine(
                situation,
                personality=self._personality(),
            )
            self.say(line)

        QTimer.singleShot(max(0, int(delay_ms)), speak)

    def _show_startup_recovery_line(self) -> None:
        if self.recovery_status.safe_mode:
            situation = "safe_mode"
        elif self.recovery_status.unclean_exit:
            situation = "recovered"
        elif self._first_session_today:
            kind, greeting, particle = greeting_for_moment()
            if kind.startswith("fest_") or kind == "late_night":
                if particle:
                    self.emit_particles(particle)
                self.say(greeting)
                return
            if particle:
                self.emit_particles(particle)
            self.say(greeting)
            return
        else:
            line = self.dialogue.pick_relationship(
                self.pet_state.affinity,
                personality=self._personality(),
            )
            self.say(line)
            return
        self.say(self.dialogue.pick_routine(situation, personality=self._personality()))

    def save_snapshot(self) -> None:
        """Atomically persist the small recoverable state during long sessions."""
        self._sync_external_config()
        self.config.set("x", self.x(), save=False)
        self.config.set("y", self.y(), save=False)
        self.config.save()
        self.state_store.save(self.pet_state)

    # ----- user interaction -----------------------------------------------------

    def _local_sprite_bounds(self) -> tuple[float, float, float, float]:
        """Actual rendered sprite rect (left, top, width, height) in widget-local coords."""
        snap = self.player.snapshot()
        layer = snap.current
        slot_bottom = float(self.height() - MARGIN - 7)
        if layer is None or layer.frame.pixmap.isNull():
            body_w = float(self.current_height) * 0.6
            body_h = float(self.current_height)
            return (self.width() - body_w) / 2.0, slot_bottom - body_h, body_w, body_h
        pixmap = layer.frame.pixmap
        body_w = float(pixmap.width())
        body_h = float(pixmap.height())
        anchor_pos = self.renderer._render_anchor(self, layer)
        body_left = anchor_pos.x() - body_w * layer.anchor.x
        body_top = anchor_pos.y() - body_h * layer.anchor.y
        if self._dock_side is not None and layer.asset_id in _BESPOKE_DOCK_ASSET_IDS:
            body_top -= 18.0
        return body_left, body_top, body_w, body_h

    def _maybe_auto_hide_control_panel(self) -> None:
        if not hasattr(self, "control_panel") or not self.control_panel.isVisible():
            self._panel_open_pet_pos = None
            return
        anchor = self._panel_open_pet_pos
        if anchor is None:
            self._panel_open_pet_pos = QPoint(self.x(), self.y())
            return
        dx = self.x() - anchor.x()
        dy = self.y() - anchor.y()
        if dx * dx + dy * dy > 24 * 24:
            self.control_panel.hide()
            self._panel_open_pet_pos = None

    def moveEvent(self, event) -> None:
        if hasattr(self, "control_panel") and self.control_panel.isVisible():
            if self._panel_open_pet_pos is None:
                self._panel_open_pet_pos = QPoint(event.oldPos())
            self._maybe_auto_hide_control_panel()
        super().moveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._interrupt_activity()
        position = event.globalPosition().toPoint()
        self._descend_x = None
        if self.climb.active:
            # Grabbed off the wall: treat it like catching her mid-air.
            self.climb.cancel()
            self._launch_throw(0.0, 0.0, reason="climb_grabbed")
        self._caught_throw = self.physics.active
        if self._caught_throw:
            self._intentional_jump = False
            self.physics.cancel()
            self.movement.cancel_target()
            self._request_action(
                PetAction.DRAGGING,
                reason="midair_catch",
                force=True,
                immediate=True,
            )
        self._drag_last_pos = position
        self._drag_offset = None
        self._long_press_handled = False
        self._purring = False
        body_left, body_top, body_width, body_height = self._local_sprite_bounds()
        self.interaction.press(
            position,
            event.position().x(),
            event.position().y(),
            body_left,
            body_top,
            body_width,
            body_height,
        )
        if self.interaction.body_region in {"head", "face"}:
            self._hold_timer.start(620)

    def mouseMoveEvent(self, event) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        position = event.globalPosition().toPoint()
        if not self.interaction.move(position):
            return
        if self._drag_offset is None:
            self._hold_timer.stop()
            self._purring = False
            self._intentional_jump = False
            self._dock_side = None
            self._dock_screen = None
            self._dock_peeking = False
            self._dock_peek_progress = 0.0
            if self.control_panel.isVisible():
                self.control_panel.hide()
                self._panel_open_pet_pos = None
            if self.food_panel.isVisible():
                self.food_panel.hide()
            self._drag_offset = position - QPoint(self.x(), self.y())
            self.physics.cancel()
            self.surface_tracker.detach()
            self._request_action(
                PetAction.DRAGGING,
                reason="drag_start",
                force=True,
                immediate=True,
            )
        self.move(position - self._drag_offset)
        if self._drag_last_pos is not None:
            delta = position - self._drag_last_pos
            if abs(delta.x()) > 10:
                self._set_direction("left" if delta.x() < 0 else "right")
        self._drag_last_pos = position
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        outcome = self.interaction.release(event.globalPosition().toPoint())
        self._hold_timer.stop()
        was_purring = self._purring
        self._purring = False
        caught_throw = self._caught_throw
        self._caught_throw = False
        self._drag_offset = None
        self._drag_last_pos = None
        if outcome is None:
            return
        if outcome.kind == "drag":
            self.pet_state.drag()
            throw_speed = (
                outcome.velocity_x * outcome.velocity_x + outcome.velocity_y * outcome.velocity_y
            ) ** 0.5
            if bool(self._agy().get("edge_dock", True)):
                edge = self._near_screen_edge(threshold=12)
                if edge is not None and throw_speed < 650.0:
                    self.dock_to_edge(edge)
                    return
                wide_edge = self._near_screen_edge(threshold=36)
                moving_toward_edge = (
                    (wide_edge == "left" and outcome.velocity_x < 0.0)
                    or (wide_edge == "right" and outcome.velocity_x > 0.0)
                )
                if wide_edge is not None and moving_toward_edge and throw_speed <= 1400.0:
                    self.dock_to_edge(wide_edge)
                    return
            self._launch_throw(
                outcome.velocity_x,
                outcome.velocity_y,
                reason="fast_release" if throw_speed >= 900.0 else "drag_release",
            )
            drag_key = "drag_fast" if throw_speed >= 900.0 else "drag_gentle"
            self.say(
                self.dialogue.pick_interaction(drag_key, personality=self._personality())
                or self.dialogue.pick_interaction("drag", personality=self._personality()),
                preserve_action=True,
            )
            return
        if caught_throw:
            self.pet_state.drag()
            self._launch_throw(0.0, 0.0, reason="caught_release")
            return
        if was_purring:
            self._long_press_handled = False
            now = time.monotonic()
            if hasattr(self, "expressions"):
                self.expressions.cue("happy", now)
            self._request_action(PetAction.IDLE, now=now, reason="pet_purr_release", force=True)
            return
        if self._long_press_handled:
            self._long_press_handled = False
            return
        self._pending_click_region = outcome.body_region
        self._do_click_reaction()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._hold_timer.stop()
        self._purring = False
        body_left, body_top, body_width, body_height = self._local_sprite_bounds()
        region = self.interaction.classify_region(
            event.position().x(),
            event.position().y(),
            body_left,
            body_top,
            body_width,
            body_height,
        )
        now = time.monotonic()
        recent_count = sum(1 for ts in self._recent_pokes if now - ts <= 8.0)
        if region != "body" or now < self._sulk_until or recent_count >= 2:
            # Rapid-poking head/face/tail or already on a poke streak:
            # treat the second click as a poke/pat rather than opening FoodPanel.
            self._pending_click_region = region
            self._do_click_reaction()
            return
        self._open_food_panel()

    def _do_click_reaction(self) -> None:
        region = self._pending_click_region
        personality = self._personality()
        now = time.monotonic()
        if region == "head":
            self.pet_state.pet_head()
            self.emit_particles("hearts")
            if now < self._sulk_until:
                self._sulk_until = 0.0
                self.pet_state.annoyance = max(0.0, self.pet_state.annoyance - 0.18)
                self._request_action(PetAction.HAPPY, reason="sulk_forgiven", force=True)
                self.say("哼……好吧，看在摸头的份上原谅你啦～", preserve_action=True)
                return
            self._request_action(PetAction.HEAD_PAT, reason="head_pat")
            self.say(
                self.dialogue.pick_interaction("head", personality=personality),
                preserve_action=True,
            )
            return

        if now < self._sulk_until:
            self.pet_state.tap(0.6)
            self.emit_particles("sweat")
            self._request_action(PetAction.ANGRY, reason="sulking_ignore", force=True)
            self.action_machine.queue_after_current(PetAction.SULK)
            self.say("哼，还在生闷气呢……摸摸头再哄我嘛。", preserve_action=True)
            return

        self._recent_pokes.append(now)
        recent_count = sum(1 for timestamp in self._recent_pokes if now - timestamp <= 8.0)
        intensity = {"face": 1.15, "body": 1.0, "tail": 2.0}.get(region, 1.0)
        self.pet_state.tap(intensity)
        if recent_count >= 4:
            self._sulk_until = now + 30.0
            self._interrupt_activity(delay_seconds=30.0)
            self.emit_particles("sweat")
            self._request_action(PetAction.SULK, reason="poke_sulk", force=True)
            self.say("气鼓鼓！不理你了，要摸头才原谅！", preserve_action=True)
            return
        if recent_count == 3:
            self.emit_particles("sweat")
            self._request_action(PetAction.ANGRY, reason="repeated_poke")
            self.say(
                self.dialogue.pick_routine("repeated_poke", personality=personality),
                preserve_action=True,
            )
            return
        if region == "tail":
            self.emit_particles("sweat")
            self._request_action(PetAction.TAIL_REACT, reason="tail_touch")
            self.say(
                self.dialogue.pick_routine("tail_touch", personality=personality),
                preserve_action=True,
            )
            return
        if recent_count == 2:
            self.emit_particles("sweat")
        reaction = PetAction.ANGRY if self.pet_state.annoyance >= 0.26 else PetAction.POKE_REACT
        self._request_action(reaction, reason=f"poke_{region}")
        self.say(
            self.dialogue.pick_interaction(region, personality=personality)
            or self.dialogue.pick_interaction("tap", personality=personality),
            preserve_action=True,
        )

    def _do_long_press_reaction(self) -> None:
        if not self.interaction.active or self.interaction.dragging:
            return
        region = self.interaction.body_region
        if region not in {"head", "face"}:
            return
        self._long_press_handled = True
        self.pet_state.pet_head()
        self.emit_particles("hearts")
        now = time.monotonic()
        forgiven = False
        if now < self._sulk_until:
            self._sulk_until = 0.0
            self.pet_state.annoyance = max(0.0, self.pet_state.annoyance - 0.22)
            forgiven = True
        if region == "head":
            self._purring = True
            self._next_purr_heart_at = now + PURR_HEART_INTERVAL_S
            self._request_action(PetAction.PET_PURR, now=now, reason="long_head_purr", force=True)
            if forgiven:
                self.say("唔……摸这么温柔，那就原谅你吧～", preserve_action=True)
            else:
                self.say(
                    self.dialogue.pick_interaction("head_hold", personality=self._personality())
                    or self.dialogue.pick_interaction("head", personality=self._personality()),
                    preserve_action=True,
                )
            return
        if forgiven:
            self._request_action(PetAction.HAPPY, reason="long_pat_forgiven", force=True)
            self.say("唔……摸这么温柔，那就原谅你吧～", preserve_action=True)
            return
        self._request_action(PetAction.HEAD_PAT, reason="long_head_pat")
        self.say(
            self.dialogue.pick_interaction("head_hold", personality=self._personality())
            or self.dialogue.pick_interaction("head", personality=self._personality()),
            preserve_action=True,
        )

    def on_food(self, food: str) -> None:
        """Feed her ``food`` (an id from the current form's menu)."""
        self._interrupt_activity()
        self.food_panel.hide()
        self._recent_pokes.clear()
        if self._dock_side is not None:
            self.undock_from_edge(fall_if_airborne=False)
        item = self.food_panel.item(food)
        taste = item.taste if item is not None else "normal"
        self.pet_state.feed(taste)
        own_lines = self._personality() == "standard" and item is not None and bool(item.lines)
        if taste == "dislike":
            # Not her thing: she waves it away instead of eating it.
            self._request_action(PetAction.REFUSE_FOOD, reason="feed_dislike", force=True)
            if own_lines:
                line = self.rng.choice(item.lines)
            else:
                line = self.dialogue.pick_routine("repeated_feed", personality=self._personality())
            self.say(line, preserve_action=True)
            return
        now = time.monotonic()
        self._recent_feedings.append(now)
        self._request_action(PetAction.EATING, reason="feed")
        recent_count = sum(1 for timestamp in self._recent_feedings if now - timestamp <= 20.0)
        if recent_count >= 3:
            line = self.dialogue.pick_routine("repeated_feed", personality=self._personality())
        else:
            if taste == "favorite":
                self._sulk_until = 0.0
                self.emit_particles("hearts")
                self.action_machine.queue_after_current(PetAction.HAPPY)
            else:
                self.emit_particles("sparkles")
            generic = self.dialogue.pick_interaction("food", personality=self._personality())
            if own_lines and (taste == "favorite" or self.rng.random() < 0.6 or not generic):
                line = self.rng.choice(item.lines)
            else:
                line = generic
        self.say(line, preserve_action=True)

    # ----- local environment awareness -----------------------------------------

    def _create_awareness(self) -> None:
        classifier = AppClassifier(self.paths.assets_dir / "app_categories.json")
        privacy = PrivacyPolicy(self.paths.assets_dir / "privacy_rules.json")
        self.context_sensor = ContextSensor(classifier, privacy)
        self.awareness_timer = QTimer(self)
        self.awareness_timer.timeout.connect(self._poll_context)
        self.surface_timer = QTimer(self)
        self.surface_timer.timeout.connect(self._poll_surface)
        self._hidden_by_fullscreen = False
        self._rebuild_behavior_components()

    def _rebuild_behavior_components(self) -> None:
        awareness = self.config.section("awareness")
        self.context_scheduler = ContextEventScheduler(
            min_dwell_seconds=float(awareness.get("min_dwell_seconds", 15)),
        )
        self.cooldown = Cooldown(
            float(awareness.get("global_cooldown_seconds", 150)),
            float(awareness.get("context_cooldown_seconds", 900)),
        )
        self.behavior_engine = BehaviorEngine(self.dialogue, self.cooldown)

    def _sync_awareness_timer(self) -> None:
        awareness = self.config.section("awareness")
        if awareness.get("enabled", True):
            interval = max(500, int(awareness.get("poll_interval_ms", 1000)))
            self.awareness_timer.start(interval)
        else:
            self.awareness_timer.stop()

    def _sync_surface_timer(self) -> None:
        if bool(self.config.section("comfort").get("desktop_surfaces", True)):
            self.surface_timer.start(800)
        else:
            self.surface_timer.stop()

    def _poll_surface(self) -> None:
        ignored = {int(self.winId()), int(self.control_panel.winId()), int(self.food_panel.winId())}
        self.surface_tracker.observe_foreground(ignored_handles=ignored)

    def _poll_context(self) -> None:
        awareness = self.config.section("awareness")
        privacy = self.config.section("privacy")
        snapshot = self.context_sensor.capture(
            read_window_title=bool(awareness.get("read_window_title", True)),
            idle_detection=bool(awareness.get("idle_detection", True)),
            custom_private_process_names=privacy.get("custom_process_names", []),
        )
        if snapshot is None:
            return
        self.surface_tracker.observe_window(snapshot.window_handle)
        self._last_user_idle = (
            float(snapshot.idle_seconds) if awareness.get("idle_detection", True) else None
        )
        self.activity_director.observe_context(
            category=snapshot.category,
            idle_seconds=snapshot.idle_seconds,
            private=snapshot.is_private,
            late_night=time.localtime().tm_hour >= 23,
        )
        events = self.context_scheduler.observe(snapshot)
        for event in events:
            if event.type == EventType.FULLSCREEN_ENTER and awareness.get(
                "hide_on_fullscreen", True
            ):
                if self.isVisible():
                    self._hidden_by_fullscreen = True
                    self.control_panel.hide()
                    self.hide()
                    self._sync_subagent_clones()
            elif event.type == EventType.FULLSCREEN_EXIT and self._hidden_by_fullscreen:
                self._hidden_by_fullscreen = False
                self.show()
                self.raise_()
                self._sync_subagent_clones()

        reaction = self.behavior_engine.react(
            snapshot,
            events,
            personality=self._personality(),
        )
        if reaction is not None:
            self.say(reaction.text, inner=reaction.inner)

    def set_awareness_enabled(self, enabled: bool) -> None:
        self.config.set_nested("awareness", "enabled", bool(enabled))
        self._rebuild_behavior_components()
        self._sync_awareness_timer()
        self._refresh_control_panel()
        if enabled:
            self.say("本地环境感知已开启。")
        else:
            self.say("本地环境感知已暂停。")

    def _set_awareness_flag(self, key: str, enabled: bool) -> None:
        self.config.set_nested("awareness", key, bool(enabled))
        self._refresh_control_panel()

    # ----- menus, tray, and persistence ----------------------------------------

    def contextMenuEvent(self, event) -> None:
        self._interrupt_activity()
        if self._dock_side is not None:
            self._dock_peeking = True
            self._dock_leave_at = 0.0
        self._refresh_control_panel()
        self._panel_open_pet_pos = QPoint(self.x(), self.y())
        self.control_panel.popup_near_pet(self.frameGeometry())
        event.accept()

    def _create_tray(self) -> None:
        icon = QIcon(str(self.paths.icon_path))
        self.tray = QSystemTrayIcon(icon, self)
        tray_menu = QMenu()
        tray_menu.addAction("显示/隐藏", self.toggle_visible)
        tray_menu.addAction("打开快速控制", self._open_control_panel_from_tray)
        tray_menu.addAction(
            "暂停/启用环境感知",
            lambda: self.set_awareness_enabled(
                not bool(self.config.section("awareness").get("enabled", True))
            ),
        )
        form_menu = tray_menu.addMenu("切换形态")
        self._tray_form_actions = {}
        for form in FORMS:
            action = form_menu.addAction(f"{form.name} · {form.tagline}")
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, key=form.id: self.set_form(key, manual=True))
            self._tray_form_actions[form.id] = action
        form_menu.addSeparator()
        self._tray_follow_action = form_menu.addAction("跟随 Antigravity 当前模型")
        self._tray_follow_action.setCheckable(True)
        self._tray_follow_action.triggered.connect(self.set_follow_model)
        form_menu.aboutToShow.connect(self._sync_tray_forms)
        tray_menu.addAction("Token Meter 面板", self.open_token_meter)
        tray_menu.addAction(
            "显示/隐藏 HUD 悬浮条",
            lambda: self.set_hud_enabled(not bool(self._agy().get("hud_enabled", True))),
        )
        tray_menu.addSeparator()
        tray_menu.addAction("退出", self.quit_app)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def _open_control_panel_from_tray(self) -> None:
        self._interrupt_activity()
        self._refresh_control_panel()
        self._panel_open_pet_pos = QPoint(self.x(), self.y())
        self.control_panel.popup_at(self.pos())

    def set_mode(self, mode: str) -> None:
        self._interrupt_activity(delay_seconds=1.5)
        self.movement.set_mode(mode)
        self.config.set("mode", self.movement.mode)
        self._refresh_control_panel()

    def set_activity_level(self, level: str) -> None:
        level = ActivityDirector._normalized_activity_level(level)
        now = time.monotonic()
        self.activity_director.set_activity_level(level, now=now)
        self.micro_motion_director.set_activity_level(level, now=now)
        self.config.set_nested("comfort", "activity_level", level)
        self._refresh_control_panel()

    def set_walk_speed(self, speed: float) -> None:
        speed = min((64.0, 82.0, 104.0), key=lambda value: abs(value - float(speed)))
        self.movement.set_speed(speed)
        self.config.set_nested("comfort", "walk_speed", speed)
        self._refresh_control_panel()

    def set_reduced_motion(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.renderer.set_reduced_motion(enabled)
        self.particles.reduced_motion = enabled
        if enabled:
            self.particles.clear()
        self.config.set_nested("comfort", "reduced_motion", enabled)
        self._refresh_control_panel()
        self.update()

    def set_hover_pause(self, enabled: bool) -> None:
        self.config.set_nested("comfort", "hover_pause", bool(enabled))
        self._refresh_control_panel()

    def set_desktop_surfaces(self, enabled: bool) -> None:
        dropped = self.surface_tracker.set_enabled(bool(enabled))
        self.config.set_nested("comfort", "desktop_surfaces", bool(enabled))
        self._sync_surface_timer()
        self._refresh_control_panel()
        if dropped and not self.physics.active and not self.interaction.active:
            self._launch_throw(0.0, 0.0, reason="surfaces_disabled")

    def set_size(self, multiplier: float) -> None:
        self._intentional_jump = False
        self.physics.cancel()
        multiplier = self._normalized_size(multiplier)
        self.current_height = self._height_for_size(multiplier)
        self.config.set("size", multiplier)
        self._resize_window()
        self.subagent_clones.set_scale_from_host(self.current_height)
        self._sync_subagent_clones()
        self._sync_animation_clip(crossfade=False, immediate=True)
        if self._dock_side is not None:
            area = self._screen_area_for_pet()
            target_x = self._dock_target_x(self._dock_side, peek=self._dock_peek_progress)
            target_y = self.y()
            if area is not None:
                target_y = max(area.top(), min(area.bottom() - self.height() + 1, target_y))
            self.move(target_x, target_y)
        else:
            self.snap_into_screen()

    def snap_into_screen(self) -> None:
        was_docked = self._dock_side is not None
        self._dock_side = None
        self._dock_screen = None
        self._dock_peeking = False
        self._dock_peek_progress = 0.0
        self._intentional_jump = False
        if was_docked:
            self._sync_animation_clip(crossfade=False, immediate=True)
        self.physics.cancel()
        self.surface_tracker.detach()
        self.movement.cancel_target()
        screen = (
            QApplication.screenAt(self.frameGeometry().center())
            or self.screen()
            or QApplication.primaryScreen()
        )
        if screen is None:
            return
        geometry = screen.availableGeometry()
        max_x = geometry.right() - self.width() + 1
        max_y = geometry.bottom() - self.height() + 1
        self.move(max(geometry.left(), min(max_x, self.x())), max_y)

    def recall_to_primary_screen(self) -> None:
        """Undock/detach and move the pet cleanly to the primary screen bottom-right."""
        self._interrupt_activity()
        was_docked = self._dock_side is not None
        self._dock_side = None
        self._dock_screen = None
        self._dock_peeking = False
        self._dock_peek_progress = 0.0
        self._dock_leave_at = 0.0
        self._intentional_jump = False
        self._descend_x = None
        self._purring = False
        self.physics.cancel()
        self.climb.cancel()
        self.surface_tracker.detach()
        self.movement.cancel_target()
        self.movement.rest_after_drag()
        self._set_direction("down")
        screen = QApplication.primaryScreen() or self.screen()
        if screen is not None:
            geometry = screen.availableGeometry()
            target_x = max(geometry.left(), geometry.right() - self.width() + 1 - 80)
            target_y = max(geometry.top(), geometry.bottom() - self.height() + 1)
            self.move(target_x, target_y)
        if was_docked:
            self._sync_animation_clip(crossfade=False, immediate=True)
        self._gentle_landing = False
        self._request_action(PetAction.WAVE, reason="recall_primary", force=True, immediate=True)
        self.emit_particles("sparkles")
        self.say("我回来主屏幕啦～", preserve_action=True)
        self._refresh_control_panel()

    def _toggle_edge_dock(self) -> None:
        if self._dock_side is not None:
            self.undock_from_edge()
        else:
            self.dock_to_edge("right")

    # ----- edge dock & peek ----------------------------------------------------

    @property
    def _dock_edge(self) -> str | None:
        return self._dock_side

    def _resolve_screen_for_pet(self):
        return (
            QApplication.screenAt(self.frameGeometry().center())
            or self.screen()
            or QApplication.primaryScreen()
        )

    def _screen_for_pet(self):
        if self._dock_side is not None and self._dock_screen is not None:
            return self._dock_screen
        return self._resolve_screen_for_pet()

    def _screen_area_for_pet(self) -> QRect | None:
        screen = self._screen_for_pet()
        return screen.availableGeometry() if screen is not None else None

    def _near_screen_edge(self, threshold: int = 12) -> str | None:
        area = self._screen_area_for_pet()
        if area is None:
            return None
        sprite_w = max(80.0, float(self._frame_size()[0]))
        body_left = self.x() + (self.width() - sprite_w) / 2.0
        body_right = self.x() + (self.width() + sprite_w) / 2.0
        if body_left <= area.left() + threshold:
            return "left"
        if body_right >= area.right() - threshold:
            return "right"
        return None

    def _current_asset_is_bespoke_dock(self) -> bool:
        snap = self.player.snapshot()
        return snap.current is not None and snap.current.asset_id in _BESPOKE_DOCK_ASSET_IDS

    def _dock_target_x(self, side: str, *, peeking: bool = False, peek: float | None = None) -> int:
        area = self._screen_area_for_pet()
        if area is None:
            return self.x()
        p = max(0.0, min(1.0, (1.0 if peeking else 0.0) if peek is None else float(peek)))
        cx = self.width() / 2.0
        raw_w, raw_h = self._frame_size()
        sprite_w = max(72.0, float(raw_w))
        sprite_h = max(100.0, float(raw_h))
        if self._current_asset_is_bespoke_dock():
            # Bespoke dock_peek / dock_work / dock_sleep sprites have a clean vertical bezel cut.
            # Keep the cut tucked behind the bezel when idle and reveal ~36-42px on hover peek.
            effective_p = max(p, 0.92) if self.action_machine.current == PetAction.WORKING else p
            flush_inset = max(2.0, sprite_w * 0.025)
            reveal_px = max(36.0, min(42.0, sprite_w * 0.34))
            tuck_inset = min(sprite_w * 0.48, flush_inset + reveal_px)
            edge_inset = tuck_inset * (1.0 - effective_p) + flush_inset * effective_p
            if side == "right":
                cut_x = cx + sprite_w / 2.0 - edge_inset
                return round(area.right() + 1 - cut_x)
            cut_x = cx - sprite_w / 2.0 + edge_inset
            return round(area.left() - cut_x)
        # Fallback for forms without bespoke dock art: tilted peek-a-boo around the bezel.
        head_shift = math.sin(math.radians(27.0)) * sprite_h * 0.72
        tuck_offset = max(sprite_w * 0.22, head_shift - sprite_w * 0.22)
        hover_offset = sprite_w * 0.48
        if side == "right":
            cut_x = (cx - tuck_offset) * (1.0 - p) + (cx + hover_offset) * p
            return round(area.right() + 1 - cut_x)
        cut_x = (cx + tuck_offset) * (1.0 - p) + (cx - hover_offset) * p
        return round(area.left() - cut_x)

    def dock_to_edge(self, side: str = "right") -> None:
        side = "left" if side == "left" else "right"
        screen = (
            self._dock_screen
            if self._dock_side is not None and self._dock_screen is not None
            else self._resolve_screen_for_pet()
        )
        self._dock_screen = screen
        area = screen.availableGeometry() if screen is not None else None
        self._intentional_jump = False
        self.physics.cancel()
        self.climb.cancel()
        self.surface_tracker.detach()
        self.movement.cancel_target()
        self._dock_side = side
        self._dock_peeking = False
        self._dock_peek_progress = 0.0
        self._dock_leave_at = 0.0
        self._set_direction("down")
        telemetry = getattr(self, "telemetry", None)
        snap = telemetry.last_snapshot if telemetry is not None else None
        dock_action = PetAction.WORKING if (snap is not None and getattr(snap, "running", False)) else PetAction.IDLE
        changed = self._request_action(dock_action, reason="edge_dock", force=True, immediate=True)
        if not changed:
            self._sync_animation_clip(crossfade=False, immediate=True)
        target_x = self._dock_target_x(side, peek=0.0)
        target_y = self.y()
        if area is not None:
            target_y = max(area.top(), min(area.bottom() - self.height() + 1, target_y))
        self.move(target_x, target_y)
        self.say("先躲到屏幕边上探头看你，鼠标过来我再出来～", preserve_action=True)
        self._refresh_control_panel()

    def undock_from_edge(self, *, fall_if_airborne: bool = True) -> None:
        if self._dock_side is None:
            return
        area = self._screen_area_for_pet()
        self._dock_side = None
        self._dock_screen = None
        self._dock_peeking = False
        self._dock_peek_progress = 0.0
        self._dock_leave_at = 0.0
        self._set_direction("down")
        if self.action_machine.current == PetAction.DOCK_SLEEP:
            self._request_action(PetAction.IDLE, reason="undock_wake", force=True, immediate=True)
        else:
            self._sync_animation_clip(crossfade=False, immediate=True)
        if area is not None:
            clamped_x = max(area.left() + 8, min(area.right() - self.width() - 8, self.x()))
            self.move(clamped_x, self.y())
            floor_y = area.bottom() - self.height() + 1
            if fall_if_airborne and not self.surface_tracker.attached and self.y() < floor_y - 4:
                self._gentle_landing = True
                self._launch_throw(0.0, 0.0, reason="undock_fall")
        self.emit_particles("sparkles")
        self._refresh_control_panel()

    def _tick_edge_dock(self, now: float, *, delta_seconds: float | None = None) -> None:
        if self._dock_side is None:
            return
        panel_open = hasattr(self, "control_panel") and self.control_panel.isVisible()
        if panel_open:
            # Keep her peeking out while the user interacts with the control panel,
            # so moving the cursor from the pet onto the panel never retracts & closes it.
            self._dock_peeking = True
            self._dock_leave_at = 0.0
        elif not self._hovered and self._dock_peeking and self._dock_leave_at > 0 and now >= self._dock_leave_at:
            self._dock_peeking = False
            self._dock_leave_at = 0.0
            self._refresh_control_panel()
        goal = 1.0 if self._dock_peeking else 0.0
        dt = (TICK_MS / 1000.0) if delta_seconds is None else max(0.001, min(0.10, float(delta_seconds)))
        if self.renderer.reduced_motion or abs(goal - self._dock_peek_progress) <= 0.02:
            self._dock_peek_progress = goal
        else:
            alpha = 1.0 - math.exp(-DOCK_PEEK_EASE_RATE * dt)
            self._dock_peek_progress += (goal - self._dock_peek_progress) * alpha
        target_x = self._dock_target_x(self._dock_side, peek=self._dock_peek_progress)
        if target_x != self.x():
            if panel_open:
                self._panel_open_pet_pos = QPoint(target_x, self.y())
            self.move(target_x, self.y())

    def enterEvent(self, event) -> None:
        self._hovered = True
        if self._dock_side is not None:
            self._dock_peeking = True
            self._dock_leave_at = 0.0
            self._refresh_control_panel()
        elif bool(self.config.section("comfort").get("hover_pause", True)):
            self._interrupt_activity(delay_seconds=5.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        if self._dock_side is not None:
            self._dock_leave_at = time.monotonic() + 0.55
        super().leaveEvent(event)

    def set_passthrough(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if sys.platform != "win32":
            QMessageBox.information(self, "鼠标穿透", "鼠标穿透目前仅在 Windows 上可用。")
            return
        try:
            user32 = ctypes.windll.user32
            handle = int(self.winId())
            get_style = user32.GetWindowLongPtrW
            set_style = user32.SetWindowLongPtrW
            style = get_style(handle, -20)
            layered = 0x80000
            transparent = 0x20
            new_style = style | layered | (transparent if enabled else 0)
            if not enabled:
                new_style &= ~transparent
            set_style(handle, -20, new_style)
            self.config.set("passthrough", enabled)
            self._refresh_control_panel()
            if enabled:
                self.say("我隐身了！右键托盘图标可以解除。")
        except OSError as error:
            QMessageBox.warning(self, "鼠标穿透", f"设置失败：{error}")

    def set_topmost(self, enabled: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(enabled))
        self.config.set("topmost", bool(enabled))
        self.show()
        self.subagent_clones.set_topmost(bool(enabled))
        self._refresh_control_panel()

    def set_autostart(self, enabled: bool) -> None:
        enabled = bool(enabled)
        startup_dir = Path(
            os.environ.get(
                "APPDATA",
                str(Path.home() / "AppData" / "Roaming"),
            )
        ) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        link = startup_dir / "AGY 桌宠.lnk"
        try:
            if enabled:
                pythonw = self.paths.app_dir / ".venv" / "Scripts" / "pythonw.exe"
                interpreter = Path(sys.executable)
                system_pythonw = interpreter.with_name("pythonw.exe")
                target = str(
                    interpreter
                    if getattr(sys, "frozen", False)
                    else (pythonw if pythonw.exists() else system_pythonw if system_pythonw.exists() else interpreter)
                )
                arguments = "" if getattr(sys, "frozen", False) else f'"{self.paths.app_dir / "main.py"}"'
                quote = lambda value: value.replace("'", "''")
                script = (
                    "$shortcut=(New-Object -ComObject WScript.Shell).CreateShortcut('"
                    + quote(str(link))
                    + "');$shortcut.TargetPath='"
                    + quote(target)
                    + "';$shortcut.Arguments='"
                    + quote(arguments)
                    + "';$shortcut.WorkingDirectory='"
                    + quote(str(self.paths.app_dir))
                    + "';$shortcut.Save()"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", script],
                    check=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self.say("已设置开机自启，明天见。")
            elif link.exists():
                link.unlink()
                self.say("已取消开机自启。")
            self.config.set("autostart", enabled)
            self._refresh_control_panel()
        except (OSError, subprocess.CalledProcessError) as error:
            QMessageBox.warning(self, "开机自启", f"设置失败：{error}")

    def toggle_visible(self) -> None:
        if self.isVisible():
            self._hidden_by_fullscreen = False
            self.control_panel.hide()
            self.hide()
        else:
            self.show()
            self.raise_()
        self._sync_hud_visibility()
        self._sync_subagent_clones()

    def activate_from_shortcut(self) -> None:
        """Bring the existing pet back when its shortcut is clicked again."""
        self._hidden_by_fullscreen = False
        self.show()
        self.raise_()
        self.activateWindow()
        self._sync_subagent_clones()

    def _show_privacy_notice(self) -> None:
        QMessageBox.information(
            self,
            "本地隐私规则",
            "环境感知只在本机读取前台进程名、窗口标题、空闲时长和全屏状态。\n\n"
            "开启“窗口落脚”时，只额外读取前台窗口句柄和外框位置，用来判断顶部落点与随动；不会读取窗口内容。\n\n"
            "密码管理器、支付/银行、远程桌面、聊天和邮件应用，以及无痕窗口默认不保留标题，也不会触发台词。"
            "\n\n不会截图、不会读取浏览历史、不会把感知数据发送到网络。",
        )

    # ----- Antigravity: forms, telemetry, HUD and Token Meter -------------------

    def _agy(self) -> dict:
        """Live (mutable) agy settings; HudBar edits the same dict."""
        section = self.config.data.get("agy")
        if not isinstance(section, dict):
            section = {}
            self.config.data["agy"] = section
        return section

    def _agy_set(self, key: str, value: object) -> None:
        self._agy()[key] = value
        self.config.save()

    def _load_registry(self, form_id: str) -> AssetRegistry:
        return AssetRegistry(
            self.paths.characters_root / form_id,
            base_manifest=self.paths.base_manifest_path,
        )

    def set_form(self, form_id: str, *, manual: bool = False, announce: bool = True, persist: bool = True) -> None:
        form_id = normalize_form(form_id)
        if manual and self._agy().get("follow_model"):
            self._agy_set("follow_model", False)
        if form_id == self.form_id:
            self._refresh_control_panel()
            return
        if self.physics.active or self.interaction.active:
            self._pending_form = form_id
            return
        registry = self._load_registry(form_id)
        bottom = self.y() + self.height()
        center_x = self.x() + self.width() // 2
        self.asset_registry = registry
        self.form_id = form_id
        self._apply_form_voice(form_id)
        if persist:
            self._agy_set("form", form_id)
        self._resize_window()
        if self._dock_side is not None:
            # Stay cleanly locked to `_dock_screen` and skip TRANSFORM while docked.
            area = self._screen_area_for_pet()
            target_y = bottom - self.height()
            if area is not None:
                target_y = max(area.top(), min(area.bottom() - self.height() + 1, target_y))
            self.move(self.x(), target_y)
        else:
            self.move(center_x - self.width() // 2, bottom - self.height())
            if not (self.surface_tracker.attached and self.action_machine.current in _EDGE_ACTION_ASSETS):
                # Sitting on a window edge she just changes outfit and keeps sitting.
                self._request_action(PetAction.TRANSFORM, reason="form_switch", force=True, immediate=True)
        self._sync_animation_clip(crossfade=False, immediate=True)
        if announce:
            lines = self._form_voice.get("announce") if isinstance(self._form_voice.get("announce"), list) else []
            form = form_by_id(form_id)
            text = self.rng.choice(lines) if lines else f"{form.name} 形态！{form.tagline}。"
            self.say(str(text), preserve_action=True)

    def _apply_form_voice(self, form_id: str) -> None:
        """Load assets/dialogue/forms/<form>.json: each form talks differently."""
        try:
            voice = json.loads((self.paths.assets_dir / "dialogue" / "forms" / f"{form_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            voice = {}
        if not isinstance(voice, dict):
            voice = {}
        self._form_voice = voice
        form = form_by_id(form_id)
        speaker = str(voice.get("speaker") or form.name)
        if hasattr(self, "renderer"):
            self.renderer.speaker_name = speaker
            self.renderer.speaker_accent = QColor(ACCENTS.get(form_id, "#339ad5"))
        if hasattr(self, "control_panel"):
            self.control_panel.set_title(speaker)
        if hasattr(self, "dialogue"):
            self.dialogue.set_form_lines(voice.get("dialogue"))
        if hasattr(self, "food_panel"):
            self.food_panel.hide()
            self.food_panel.set_menu(parse_food_menu(voice.get("food_menu")), ACCENTS.get(form_id, "#339ad5"))
        agy_lines = voice.get("agy") if isinstance(voice.get("agy"), dict) else {}
        for target in (getattr(self, "reactions", None), getattr(self, "autonomy", None)):
            if target is not None:
                target.set_lines(agy_lines)

    def set_follow_model(self, enabled: bool) -> None:
        self._agy_set("follow_model", bool(enabled))
        self._refresh_control_panel()
        if enabled:
            self.reactions.reset_follow()
            self.say("我会跟着 Antigravity 当前的模型换形态。")
            snapshot = self.telemetry.last_snapshot
            if snapshot is not None:
                self._on_live_snapshot(snapshot)

    def _sync_tray_forms(self) -> None:
        for form_id, action in self._tray_form_actions.items():
            action.setChecked(form_id == self.form_id)
        self._tray_follow_action.setChecked(bool(self._agy().get("follow_model", False)))

    def _create_agy(self) -> None:
        settings = self._agy()
        self.reactions = ReactionTracker(self.rng)
        self.autonomy = AgyAutonomy(self.rng)
        self._apply_form_voice(self.form_id)
        self.agy_windows = AntigravityWindowFinder()
        self._autonomy_next = 0.0
        self._next_config_poll = 0.0
        self._last_user_idle: float | None = None
        self.telemetry = TelemetryService(
            TelemetryCollector(
                use_language_server=bool(settings.get("use_language_server", True)),
                ledger_path=self.paths.ledger_path,
            ),
            parent=self,
        )
        self.telemetry.pinned_conversation = str(settings.get("pinned_conversation") or "")
        self.hud_bar = HudBar(
            settings=settings,
            on_open_meter=self.open_token_meter,
            on_refresh=self.telemetry.refresh_now,
            on_pin=self._pin_conversation,
            on_hide=lambda: self.set_hud_enabled(False),
        )
        self.hud_bar.settings_changed.connect(self.config.save)
        self.token_meter = TokenMeterWindow(
            on_request_report=self.telemetry.request_report,
            on_toggle_subagents=self._set_include_subagents,
            icon=QIcon(str(self.paths.icon_path)),
            initial_theme=str(settings.get("meter_theme") or "light"),
            default_tab=str(settings.get("meter_default_tab") or "overview"),
            on_theme_changed=lambda t: self._agy_set("meter_theme", t),
            on_default_tab_changed=lambda tab: self._agy_set("meter_default_tab", tab),
        )
        self.telemetry.live_updated.connect(self._on_live_snapshot)
        self.telemetry.report_ready.connect(self.token_meter.update_report)
        self._hud_anchor: tuple[int, int, int, int] | None = None
        if settings.get("telemetry_enabled", True):
            self.telemetry.start()
        if settings.get("hud_mode") == "floating":
            self.hud_bar.restore_floating_position()

    def _set_include_subagents(self, enabled: bool) -> None:
        self.telemetry.include_subagents = bool(enabled)
        self.telemetry.request_report()

    def _pin_conversation(self, conversation_id: str) -> None:
        self._agy_set("pinned_conversation", conversation_id)
        self.telemetry.pinned_conversation = conversation_id
        self.telemetry.refresh_now()

    def _sync_external_config(self) -> None:
        if not hasattr(self, "telemetry") or not self.config.reload_if_external_change():
            return
        settings = self._agy()
        pinned = str(settings.get("pinned_conversation") or "")
        if pinned != self.telemetry.pinned_conversation:
            self.telemetry.pinned_conversation = pinned
            self.telemetry.refresh_now()
        follow = bool(settings.get("follow_model", False))
        if follow:
            self.reactions.reset_follow()
            snapshot = self.telemetry.last_snapshot
            if snapshot is not None:
                self._on_live_snapshot(snapshot)
        else:
            target_form = normalize_form(settings.get("form"))
            if target_form != self.form_id:
                self.set_form(target_form, manual=False, persist=False)
        was_attached = self.hud_bar.attached
        self.hud_bar.settings = settings
        if was_attached and not self.hud_bar.attached:
            self.hud_bar.restore_floating_position()
        self.hud_bar.apply_appearance()
        self._sync_hud_visibility()
        self._hud_anchor = None
        self._follow_hud()
        if self.telemetry.last_snapshot is not None:
            self.hud_bar.update_snapshot(self.telemetry.last_snapshot)
        if not settings.get("autonomy", True) and self.action_machine.current in {PetAction.WORKING, PetAction.PERCH}:
            self._request_action(PetAction.IDLE, reason="autonomy_off", force=True)
        self.particles.enabled = bool(settings.get("particles", True))
        if not self.particles.enabled:
            self.particles.clear()
        if not bool(settings.get("edge_dock", True)) and self._dock_side is not None:
            self.undock_from_edge()
        self._sync_subagent_clones()
        self._refresh_control_panel()
        self._sync_tray_forms()

    def open_token_meter(self) -> None:
        self.token_meter.update_live(self.telemetry.last_snapshot)
        self.token_meter.show()
        self.token_meter.raise_()
        self.token_meter.activateWindow()

    def set_hud_enabled(self, enabled: bool) -> None:
        self._agy_set("hud_enabled", bool(enabled))
        self._sync_hud_visibility()
        self._refresh_control_panel()

    def _sync_hud_visibility(self) -> None:
        settings = self._agy()
        want = bool(settings.get("hud_enabled", True)) and (
            settings.get("hud_mode") == "floating" or self.isVisible()
        )
        if want and not self.hud_bar.isVisible():
            self.hud_bar.show()
            self._hud_anchor = None
            self._follow_hud()
        elif not want and self.hud_bar.isVisible():
            self.hud_bar.hide()

    # ----- autonomy ---------------------------------------------------------------

    def set_autonomy(self, enabled: bool) -> None:
        self._agy_set("autonomy", bool(enabled))
        self._refresh_control_panel()
        if not enabled and self.action_machine.current in {PetAction.WORKING, PetAction.PERCH}:
            self._request_action(PetAction.IDLE, reason="autonomy_off", force=True)

    def _tick_autonomy(self, now: float) -> None:
        if not hasattr(self, "autonomy") or now < self._autonomy_next:
            return
        self._autonomy_next = now + 0.5
        settings = self._agy()
        if not settings.get("autonomy", True):
            return
        snapshot = self.telemetry.last_snapshot
        busy = (
            self.interaction.active
            or self.physics.active
            or self.climb.active
            or self.control_panel.isVisible()
            or self.food_panel.isVisible()
            or now < self._sulk_until
            or self._purring
        )
        can_hop = (
            bool(settings.get("hop_to_window", True))
            and self.surface_tracker.enabled
            and self.movement.mode != "still"
            and self._dock_side is None
        )
        window = None
        if can_hop and snapshot is not None and snapshot.running and not self.surface_tracker.attached:
            window = self.agy_windows.find()
            # Only hop onto Antigravity while the user is looking at it; a
            # covered window would leave the pet sitting on thin air.
            foreground = getattr(self.surface_tracker.reader, "foreground_handle", None)
            if window is not None and callable(foreground) and int(foreground() or 0) != window.handle:
                window = None
            if (
                window is not None
                and window.top - self.height() < self._window_work_area_top(window.left, window.top, window.right)
            ):
                window = None
        current_action_name = (
            PetAction.SLEEPING.value
            if self.action_machine.current in _SLEEP_ACTIONS
            else self.action_machine.current.value
        )
        commands = self.autonomy.update(
            AutonomyInput(
                now=now,
                snapshot=snapshot,
                pet_action=current_action_name,
                busy=busy,
                perched=self.surface_tracker.attached,
                user_idle_seconds=self._last_user_idle,
                window=window,
                can_hop=can_hop,
            )
        )
        skip_say = False
        for command in commands:
            if command.kind == "hop":
                skip_say = not self._hop_to(command)
            elif command.kind == "say":
                if not skip_say:
                    self.say(command.text, preserve_action=True)
                skip_say = False
            elif command.kind == "action" and command.action:
                self._autonomy_action(command, now)

    def _autonomy_action(self, command: AutonomyCommand, now: float) -> None:
        try:
            action = PetAction.coerce(command.action)
        except ValueError:
            return
        if action == self.action_machine.current or self.climb.active:
            return
        if self._dock_side is not None:
            if command.reason == "wake" and self.action_machine.current == PetAction.DOCK_SLEEP:
                action = PetAction.WORKING if self._is_agy_actively_working() else PetAction.IDLE
            elif action not in {PetAction.IDLE, PetAction.WORKING, PetAction.SLEEPING, PetAction.DOCK_SLEEP}:
                return
        if action not in {PetAction.IDLE, PetAction.PERCH}:
            self.activity_director.interrupt(now=now)
            self.micro_motion_director.defer(now, minimum_seconds=3.0)
            self.movement.cancel_target()
        self._request_action(action, now=now, reason=f"autonomy_{command.reason}", force=command.force)

    def _hop_to(self, command: AutonomyCommand) -> bool:
        """Jump onto the Antigravity window's top edge; False if unreachable."""
        target = command.window
        if target is None or self.physics.active or self.interaction.active or self.climb.active:
            return False
        if command.reason != "panel" and self._start_climb(target.handle):
            return True
        bounds = self._physics_bounds()
        velocity = plan_hop(
            start_x=float(self.x()),
            start_y=float(self.y()),
            widget_width=float(self.width()),
            widget_height=float(self.height()),
            target=target,
            gravity=self.physics.gravity,
            max_speed=self.physics.max_jump_speed,
            work_area_top=self._window_work_area_top(target.left, target.top, target.right),
        )
        if velocity is None or not self.surface_tracker.set_target(target.handle):
            return False
        vx, vy = velocity
        self._set_direction("left" if vx < 0 else "right")
        self.activity_director.interrupt(now=time.monotonic())
        self.movement.cancel_target()
        self.surface_tracker.detach()
        self.movement.rest_after_drag()
        self.physics.launch(self.x(), self.y(), vx, vy, planned_jump=True)
        self._intentional_jump = vy < 0.0
        self._request_action(
            PetAction.JUMP_UP if self._intentional_jump else PetAction.FALLING,
            reason="autonomy_hop",
            force=True,
            immediate=True,
        )
        self._clear_target_later()
        return True

    def _clear_target_later(self, delay_ms: int = 4_000) -> None:
        """Drop the landing target after a hop, unless a newer hop owns it."""
        self._hop_token += 1
        token = self._hop_token

        def clear() -> None:
            if token == self._hop_token:
                self.surface_tracker.set_target(None)

        QTimer.singleShot(delay_ms, clear)

    # ----- climbing and sitting on window edges -----------------------------------

    def _edge_change(self, change) -> bool:
        """True when a change enters or leaves sitting on the window edge."""
        return self.surface_tracker.attached and bool(
            {change.previous, change.current} & set(_EDGE_ACTION_ASSETS)
        )

    def _sync_attached_y_now(self) -> None:
        """Immediately align y to the attached window top + current edge-sit sink."""
        if (
            not self.surface_tracker.attached
            or self.physics.active
            or self.interaction.active
            or self._dock_side is not None
        ):
            return
        handle = self.surface_tracker.attached_handle
        if handle is None:
            return
        surface = self.surface_tracker._surfaces.get(handle)
        if surface is None:
            return
        target_y = round(surface.top - self.height() + self._edge_sit_sink())
        if target_y != self.y():
            self.move(self.x(), target_y)

    def _edge_sit_sink(self) -> float:
        """How far below the window's top edge she sits with her legs hanging."""
        asset = _EDGE_ACTION_ASSETS.get(self.action_machine.current)
        if asset is None or not self.surface_tracker.attached:
            return 0.0
        layer = self.player.snapshot().current
        resolved = self.asset_registry.resolve_asset_id(asset)
        if layer is None or layer.asset_id not in {asset, resolved} or layer.frame.pixmap.isNull():
            return 0.0
        seat = self.asset_registry.manifest.get("seat_line") or {}
        if resolved not in seat:
            return 0.0  # no edge art yet: she stands on the edge instead
        seat_y = float(seat[resolved])
        # Standing puts the feet (anchor y) on the edge; drop the seat there,
        # plus a slight tuck so hips/hands rest firmly on the window bezel.
        return max(0.0, (layer.anchor.y - seat_y) * layer.frame.pixmap.height() + EDGE_SIT_TUCK_PX)

    def _frame_size(self) -> tuple[float, float]:
        layer = self.player.snapshot().current
        if layer is None or layer.frame.pixmap.isNull():
            return float(self.current_height) * 0.6, float(self.current_height)
        pixmap = layer.frame.pixmap
        return float(pixmap.width()), float(pixmap.height())

    def _start_climb(self, handle: int | None, *, sit_after: bool = False) -> bool:
        """Walk to the nearer side of window ``handle`` and climb it."""
        if not handle or self.physics.active or self.interaction.active or self.surface_tracker.attached:
            return False
        rect = self.surface_tracker.read_rect(int(handle))
        if rect is None:
            return False
        bounds = self._physics_bounds()
        work_top = self._window_work_area_top(rect.left, rect.top, rect.right)
        sprite_width, sprite_height = self._frame_size()
        plan = plan_climb(
            handle=int(handle),
            window=ClimbRect(rect.left, rect.top, rect.right, rect.bottom),
            work_area=ClimbRect(bounds.left, work_top, bounds.right, bounds.bottom),
            widget_x=float(self.x()),
            widget_y=float(self.y()),
            widget_width=float(self.width()),
            widget_height=float(self.height()),
            feet_offset=float(MARGIN + 7),
            sprite_width=sprite_width,
            sprite_height=sprite_height,
            **self._climb_reach(),
        )
        if plan is None:
            return False
        now = time.monotonic()
        self.activity_director.interrupt(now=now)
        self.micro_motion_director.defer(now, minimum_seconds=3.0)
        self.movement.cancel_target()
        self.climb.start(plan, sit_after=sit_after)
        self._climb_pos = (float(self.x()), float(self.y()))
        return True

    def _tick_climb(self, delta_seconds: float, now: float) -> bool:
        """Advance the climb; True while she is still walking to the wall."""
        plan = self.climb.plan
        if plan is None:
            return False
        rect = self.surface_tracker.read_rect(plan.handle, now=now)
        if rect is not None and rect.top - self.height() < self._window_work_area_top(rect.left, rect.top, rect.right):
            self.climb.cancel()
            self._gentle_landing = True
            self._launch_throw(0.0, 0.0, reason="climb_lost")
            return False
        window = None if rect is None else ClimbRect(rect.left, rect.top, rect.right, rect.bottom)
        x, y = self._climb_pos
        was_on_wall = self.climb.on_wall
        step = self.climb.step(delta_seconds, x=x, y=y, window=window)
        if step.phase == "aborted":
            self.climb.cancel()
            self._gentle_landing = True
            self._launch_throw(0.0, 0.0, reason="climb_lost")
            return False
        self._climb_pos = (step.x, step.y)
        self.move(round(step.x), round(step.y))
        if step.phase == "approach":
            self._set_direction(step.facing)
            if self.action_machine.current != PetAction.WALKING:
                # Whatever she was doing (typing, celebrating), she walks now.
                self._request_action(PetAction.WALKING, now=now, reason="climb_approach", force=True)
            return True
        if not was_on_wall or self.action_machine.current != PetAction.CLIMBING:
            # Hands on the wall: the pulls start in step with frame 0.
            self.movement.set_direction(step.facing)
            self._request_action(PetAction.CLIMBING, now=now, reason="climb", force=True, immediate=True)
        if step.phase == "done":
            self._finish_climb(rect, now)
        return False

    def _finish_climb(self, rect, now: float) -> None:
        """Pulled up over the edge: she now stands on the window's top."""
        plan, sit_after = self.climb.plan, self.climb.sit_after
        self.climb.cancel()
        if (
            plan is None
            or rect is None
            or rect.top - self.height() < self._window_work_area_top(rect.left, rect.top, rect.right)
            or not self.surface_tracker.set_target(plan.handle)
        ):
            self._gentle_landing = True
            self._launch_throw(0.0, 0.0, reason="climb_lost")
            return
        self._perch_after_landing = sit_after
        self._gentle_landing = True
        self._settle_landing(f"window:{plan.handle}", hard=False, now=now)
        self.surface_tracker.set_target(None)

    def _climb_reach(self) -> dict[str, float]:
        """``reach`` / ``hand_rise`` for plan_climb, measured on the climb frames."""
        key = (self.form_id, self.current_height)
        if key not in self._climb_metrics_cache:
            self._climb_metrics_cache[key] = self._measure_climb_frames()
        metrics = self._climb_metrics_cache[key]
        if metrics is None:
            return {}
        reach, rise = metrics
        return {"reach": reach, "hand_rise": rise}

    def _measure_climb_frames(self) -> tuple[float, float] | None:
        """Hands on the wall: centre-to-wall distance and feet-to-hand height.

        The left-facing climb frames have the wall on the left, so the hands
        are the leftmost opaque pixels and the highest pixels near that side.
        """
        try:
            clip = self.asset_registry.clip_for(PetAction.CLIMBING, height=self.current_height, direction="left")
        except Exception:
            return None
        reaches, rises = [], []
        for frame in clip.frames:
            image = frame.pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            width, height = image.width(), image.height()
            if width < 8 or height < 8 or image.bytesPerLine() != width * 4:
                continue
            alpha = bytes(image.constBits())[3::4]  # one byte per pixel, row-major
            wall = next((x for x in range(width) if max(alpha[x::width]) > 40), None)
            if wall is None:
                continue
            band = max(2, round(width * 0.22))  # the strip next to the wall
            top = next(
                (y for y in range(height) if max(alpha[y * width + wall : y * width + min(width, wall + band)]) > 40),
                None,
            )
            if top is None:
                continue
            feet = clip.anchor.y * height
            reaches.append(width * clip.anchor.x - wall)
            rises.append(feet - top)
        if not reaches:
            return None
        return max(4.0, min(reaches)), max(rises)

    def _climb_candidate(self) -> int | None:
        """The window to climb from the panel: the last foreground app window."""
        handle = self.surface_tracker.candidate_handle
        if handle:
            return handle
        window = self.agy_windows.find() if hasattr(self, "agy_windows") else None
        return window.handle if window is not None else None

    def _panel_climb(self, *, sit_after: bool) -> None:
        self._interrupt_activity()
        if not self.surface_tracker.enabled:
            self.say("先在「更多设置」打开「窗口落脚」就能爬窗啦", preserve_action=True)
            return
        if sit_after and self.surface_tracker.attached:
            self._request_action(PetAction.PERCH, reason="panel_edge_sit", force=True, immediate=True)
            return
        if self.climb.active:
            return
        nearest = self._nearest_climbable()
        if nearest is not None and self._start_climb(nearest, sit_after=sit_after):
            self._explored_handle = nearest
            return
        handle = self._climb_candidate()
        if self._start_climb(handle, sit_after=sit_after):
            self._explored_handle = handle
            return
        # Too far or no floor under the window: jump up instead.
        rect = self.surface_tracker.read_rect(int(handle)) if handle else None
        if rect is not None:
            target = WindowTarget(int(handle), round(rect.left), round(rect.top), round(rect.right), round(rect.bottom))
            if self._hop_to(AutonomyCommand(kind="hop", window=target, reason="panel")):
                self._perch_after_landing = sit_after
                self._explored_handle = int(handle)
                return
        self.say("这里没有能爬的窗口呀", preserve_action=True)

    # ----- exploring nearby windows on her own -----------------------------------

    def _nearest_climbable(self) -> int | None:
        """The closest window she could climb right now (None if there is none)."""
        if self.surface_tracker.attached:
            return None
        bounds = self._physics_bounds()
        sprite_width, sprite_height = self._frame_size()
        best: tuple[float, int] | None = None
        above: list[ClimbRect] = []  # windows stacked over the current one
        for surface in self.surface_tracker.nearby_windows():
            rect = ClimbRect(surface.left, surface.top, surface.right, surface.bottom)
            work_top = self._window_work_area_top(surface.left, surface.top, surface.right)
            plan = plan_climb(
                handle=surface.handle,
                window=ClimbRect(surface.left, surface.top, surface.right, surface.bottom),
                work_area=ClimbRect(bounds.left, work_top, bounds.right, bounds.bottom),
                widget_x=float(self.x()),
                widget_y=float(self.y()),
                widget_width=float(self.width()),
                widget_height=float(self.height()),
                feet_offset=float(MARGIN + 7),
                sprite_width=sprite_width,
                sprite_height=sprite_height,
            )
            covered = plan is None or not is_exposed(plan, rect, above)
            above.append(rect)
            if covered:
                continue
            distance = abs(plan.climb_x - self.x())
            if best is None or distance < best[0]:
                best = (distance, surface.handle)
        return best[1] if best is not None else None

    def _top_bounds(self, now: float | None = None) -> tuple[float, float] | None:
        """Walking range on the window she stands on: its uncovered top edge."""
        bounds = self.surface_tracker.movement_bounds(widget_width=float(self.width()))
        handle = self.surface_tracker.attached_handle
        if bounds is None or handle is None:
            return bounds
        now = time.monotonic() if now is None else now
        cache = self._top_bounds_cache
        if cache is not None and cache[0] == handle and now - cache[1] < 1.0:
            span = cache[2]
        else:
            span = None
            above: list[ClimbRect] = []
            for surface in self.surface_tracker.nearby_windows(now=now):
                rect = ClimbRect(surface.left, surface.top, surface.right, surface.bottom)
                if surface.handle == handle:
                    span = uncovered_top_span(rect, above)
                    break
                above.append(rect)
            self._top_bounds_cache = (handle, now, span)
        if span is None:
            return bounds
        margin = min(38.0, max(18.0, (span[1] - span[0]) * 0.055))
        lower = max(bounds[0], span[0] + margin - self.width() / 2.0)
        upper = min(bounds[1], span[1] - margin - self.width() / 2.0)
        if upper < lower:
            return bounds
        return lower, upper

    def _walk_on_top(self, now: float) -> bool:
        """Get up and stroll to another spot along the window top."""
        bounds = self._top_bounds(now)
        if bounds is None:
            return False
        lower, upper = bounds
        x = float(self.x())
        body = max(60.0, self._frame_size()[0])
        options = [t for t in (self.rng.uniform(lower, upper) for _ in range(6)) if abs(t - x) >= body * 0.8]
        if not options:
            return False
        if self.action_machine.current != PetAction.IDLE:
            self._request_action(PetAction.IDLE, now=now, reason="top_stroll", force=True, immediate=True)
        self.movement.rest_until = 0.0
        self.movement.target = (options[0], float(self.y()))
        return True

    def _jump_candidates(self) -> list[tuple[int, ClimbRect]]:
        return [
            (surface.handle, ClimbRect(surface.left, surface.top, surface.right, surface.bottom))
            for surface in self.surface_tracker.nearby_windows()
        ]

    def _plan_jump(self, *, from_floor: bool) -> JumpPlan | None:
        bounds = self._physics_bounds()
        sprite_width, sprite_height = self._frame_size()
        feet = float(self.y() + self.height() - (MARGIN + 7))
        return pick_jump(
            windows=self._jump_candidates(),
            work_area=ClimbRect(bounds.left, bounds.top, bounds.right, bounds.bottom),
            feet_y=feet,
            center_x=float(self.x()) + self.width() / 2.0,
            sprite_width=sprite_width,
            sprite_height=sprite_height,
            exclude=self.surface_tracker.attached_handle,
            max_gap=sprite_width * (2.5 if from_floor else 2.0),
            max_up=sprite_height * (1.6 if from_floor else 0.9),
            max_down=0.0 if from_floor else sprite_height * 2.5,
            min_headroom=float(self.height()),
        )

    def _jump_to(self, jump: JumpPlan, *, sit_after: bool = False) -> bool:
        """Ballistic hop onto ``jump``'s window top (from the floor or a window)."""
        if self.physics.active or self.interaction.active or self.climb.active:
            return False
        rect = jump.window
        target = WindowTarget(jump.handle, round(rect.left), round(rect.top), round(rect.right), round(rect.bottom))
        fraction = (jump.land_center_x - rect.left) / max(1.0, rect.width)
        velocity = plan_hop(
            start_x=float(self.x()),
            start_y=float(self.y()),
            widget_width=float(self.width()),
            widget_height=float(self.height()),
            target=target,
            gravity=self.physics.gravity,
            max_speed=self.physics.max_jump_speed,
            work_area_top=self._window_work_area_top(rect.left, rect.top, rect.right),
            landing_fraction=max(0.0, min(1.0, fraction)),
            apex_clearance=40.0,
        )
        if velocity is None or not self.surface_tracker.set_target(jump.handle):
            return False
        now = time.monotonic()
        source = self.surface_tracker.attached_handle
        if source is not None:
            # Do not land straight back on the window she leaves.
            self.surface_tracker.ignore_platform(source, seconds=1.5, now=now)
        vx, vy = velocity
        self._set_direction("left" if vx < 0 else "right")
        self.activity_director.interrupt(now=now)
        self.movement.cancel_target()
        self.surface_tracker.detach()
        self.movement.rest_after_drag()
        self._perch_after_landing = sit_after
        self._gentle_landing = True
        self.physics.launch(self.x(), self.y(), vx, vy, planned_jump=True)
        self._intentional_jump = vy < 0.0
        self._request_action(
            PetAction.JUMP_UP if self._intentional_jump else PetAction.FALLING,
            reason="window_jump",
            force=True,
            immediate=True,
        )
        self._clear_target_later()
        self._explored_handle = jump.handle
        self._perched_since = None
        return True

    def _tick_explore(self, now: float) -> None:
        """Climb or hop onto nearby windows, stroll along their tops, jump
        across to neighbouring windows, and later come back down."""
        attached = self.surface_tracker.attached
        if not attached:
            self._perched_since = None
        elif self._perched_since is None:
            self._perched_since = now
        if now < self._explore_next:
            return
        self._explore_next = now + 1.0
        if not bool(self._agy().get("explore_windows", True)) or not self.surface_tracker.enabled:
            return
        snapshot = self.telemetry.last_snapshot
        running = snapshot is not None and bool(snapshot.running)
        own = (
            attached
            and self._explored_handle is not None
            and self.surface_tracker.attached_handle == self._explored_handle
        )
        if running and attached:
            # Working along with Antigravity on a window top: stay put.
            self._perched_since = now
            return
        if self.movement.target is not None and self.action_machine.current not in {PetAction.IDLE, PetAction.WALKING}:
            self.movement.cancel_target()
        calm = {PetAction.IDLE, PetAction.PERCH} | ({PetAction.WORKING} if running else set())
        if (
            self.action_machine.current not in calm
            or self.movement.mode != "wander"
            or self.movement.target is not None
            or self.interaction.active
            or self.physics.active
            or self.climb.active
            or self._descend_x is not None
            or self._hovered
            or self.control_panel.isVisible()
            or self.food_panel.isVisible()
            or self.activity_director.active
            or now < self._sulk_until
            or self._purring
        ):
            return
        if attached:
            # Only climb back down from a window she went up by herself (or
            # from the panel); Antigravity's window belongs to autonomy.
            if own and self._perched_since is not None and now - self._perched_since >= self._explore_stay:
                self._start_descend()
                return
            if now < self._roam_next:
                return
            self._roam_next = now + self.rng.uniform(14.0, 32.0)
            if self.action_machine.current == PetAction.PERCH:
                # Sitting quietly: stay at least a while (6 minutes after a
                # run, like autonomy), and then only sometimes get up.
                seated = now - (self._perched_since or now)
                linger = self.autonomy.settings.perch_linger_seconds if not own else 90.0
                if seated < linger or self.rng.random() < 0.5:
                    return
            roll = self.rng.random()
            if roll < 0.35:
                jump = self._plan_jump(from_floor=False)
                if jump is not None and self._jump_to(jump, sit_after=self.rng.random() < 0.4):
                    self._explore_stay = self.rng.uniform(120.0, 300.0)
                    return
            if roll < 0.85:
                self._walk_on_top(now)
            return
        self._explore_next = now + (self.rng.uniform(90.0, 200.0) if running else self.rng.uniform(45.0, 110.0))
        sit_after = self.rng.random() < 0.6
        handle = self._nearest_climbable()
        if handle is not None and self._start_climb(handle, sit_after=sit_after):
            self._explored_handle = handle
            self._explore_stay = self.rng.uniform(120.0, 300.0)
            return
        jump = self._plan_jump(from_floor=True)
        if jump is not None and self._jump_to(jump, sit_after=sit_after):
            self._explore_stay = self.rng.uniform(120.0, 300.0)

    _explore_stay = 180.0

    def _start_descend(self) -> None:
        """Walk to the nearer end of the window top, then hop off."""
        bounds = self._top_bounds()
        if bounds is None:
            return
        lower, upper = bounds
        x = float(self.x())
        self._descend_x = lower if x - lower <= upper - x else upper
        self.movement.cancel_target()

    def _tick_descend(self, delta_seconds: float, now: float) -> bool:
        target = self._descend_x
        handle = self.surface_tracker.attached_handle
        if target is None or handle is None:
            self._descend_x = None
            return False
        x = float(self.x())
        gap = target - x
        step = 85.0 * delta_seconds
        if abs(gap) > step:
            self.move(round(x + (step if gap > 0 else -step)), self.y())
            self.surface_tracker.record_pet_position(widget_x=float(self.x()), widget_width=float(self.width()))
            self._set_direction("right" if gap > 0 else "left")
            if self.action_machine.current != PetAction.WALKING:
                self._request_action(PetAction.WALKING, now=now, reason="descend_walk", force=True)
            return True
        # At the end of the window: a small hop outward, then fall to the floor.
        self._descend_x = None
        outward = 1.0 if gap >= 0 else -1.0
        self.surface_tracker.ignore_platform(handle, seconds=3.0, now=now)
        self.surface_tracker.set_target(None)
        self._gentle_landing = True
        self._launch_throw(300.0 * outward, -280.0, reason="descend", intentional_jump=True)
        self._perched_since = None
        return False

    def _own_window_handles(self) -> tuple[int, ...]:
        handles: list[int] = []
        for widget in (
            self,
            getattr(self, "control_panel", None),
            getattr(self, "food_panel", None),
            getattr(self, "hud_bar", None),
            getattr(self, "token_meter", None),
            *(
                getattr(
                    getattr(self, "subagent_clones", None),
                    "all_visible_widgets",
                    getattr(getattr(self, "subagent_clones", None), "visible_widgets", ()),
                )
                if hasattr(self, "subagent_clones")
                else ()
            ),
        ):
            if widget is None:
                continue
            try:
                handle = int(widget.winId())
            except Exception:
                continue
            if handle:
                handles.append(handle)
        return tuple(handles)

    def _attached_window_qrect(self) -> QRect | None:
        if not self.surface_tracker.attached:
            return None
        handle = self.surface_tracker.attached_handle
        if handle is None:
            return None
        surface = self.surface_tracker._surfaces.get(handle)
        if surface is None:
            return None
        return QRect(
            round(surface.left),
            round(surface.top),
            max(0, round(surface.right - surface.left)),
            max(0, round(surface.bottom - surface.top)),
        )

    def _sprite_rect(self) -> QRect:
        """Global rectangle of the sprite area (window minus bubble strip)."""
        top = self.y() + BUBBLE_HEIGHT + MARGIN
        return QRect(self.x(), top, self.width(), self.y() + self.height() - top)

    def _follow_hud(self) -> None:
        if not hasattr(self, "hud_bar"):
            return
        if self.hud_bar.isVisible() != (
            bool(self._agy().get("hud_enabled", True))
            and (self._agy().get("hud_mode") == "floating" or self.isVisible())
        ):
            self._sync_hud_visibility()
        if not self.hud_bar.isVisible() or not self.hud_bar.attached:
            return
        bubble_visible = self.bubble.visible
        # Sitting on a window: never drop the HUD over that window's title bar.
        perched = self.surface_tracker.attached
        anchor = (self.x(), self.y(), self.width(), self.height(), bubble_visible, perched)
        if anchor == self._hud_anchor:
            return
        self._hud_anchor = anchor
        self.hud_bar.follow_pet(
            self._sprite_rect(),
            sprite_top=self._hud_ceiling(bubble_visible),
            prefer_above=perched,
        )

    def _hud_ceiling(self, bubble_visible: bool) -> int:
        """Lowest y the HUD may reach when it has to sit above the pet.

        The bubble strip fills the window's top ``BUBBLE_HEIGHT`` pixels and the
        sprite's head starts right under it, so a HUD squeezed between them
        covers either the text or the head.  Without a bubble it rests on the
        head; with one it moves above the window.
        """
        if bubble_visible:
            return self.y() - 2
        # Renderer floor is ``height - MARGIN - 7``; sprites are current_height tall.
        head_top = self.y() + self.height() - MARGIN - 7 - self.current_height
        return max(self.y() + BUBBLE_HEIGHT, head_top) - 2

    _IDLE_PLAY_ACTIVITIES: tuple[str, ...] = (
        "晒太阳发呆",
        "玩捉迷藏",
        "比比谁跳得高",
        "喝下午茶",
        "一起数星星",
        "串门聊天",
    )

    def _next_idle_play_delay(self, *, initial: bool = False, activity_level: str | None = None) -> float:
        level = (
            str(activity_level or self.config.section("comfort").get("activity_level", "balanced"))
            .strip()
            .lower()
        )
        ranges = {
            "calm": (65.0, 110.0) if initial else (120.0, 210.0),
            "lively": (25.0, 50.0) if initial else (35.0, 75.0),
            "balanced": (45.0, 80.0) if initial else (65.0, 125.0),
        }
        low, high = ranges.get(level, ranges["balanced"])
        return self.rng.uniform(low, high)

    def summon_idle_playmates(
        self,
        count: int | None = None,
        *,
        now: float | None = None,
        duration: float | None = None,
        announce: bool = True,
    ) -> list[SubagentInfo]:
        """Summon 1-2 random-form mini clones during idle time to play together."""
        if (
            not hasattr(self, "subagent_clones")
            or not bool(self._agy().get("subagent_clones", True))
            or self._dock_side is not None
        ):
            return []
        ts = time.monotonic() if now is None else float(now)
        all_form_ids = list(FORM_IDS)
        desired = self.rng.choice((1, 1, 2)) if count is None else int(count)
        desired = max(1, min(MAX_VISIBLE_CLONES, desired))
        if desired <= len(all_form_ids):
            picked_forms = self.rng.sample(all_form_ids, desired)
        else:
            picked_forms = [self.rng.choice(all_form_ids) for _ in range(desired)]
        activities = list(self._IDLE_PLAY_ACTIVITIES)
        self.rng.shuffle(activities)
        playmates: list[SubagentInfo] = []
        for idx, fid in enumerate(picked_forms):
            playmates.append(
                SubagentInfo(
                    conversation_id=f"{PLAYMATE_PREFIX}{uuid.uuid4().hex[:8]}",
                    parent_conversation_id="idle-play",
                    title=activities[idx % len(activities)],
                    model_label="闲时随机玩伴",
                    form_id=fid,
                )
            )
        play_duration = float(duration) if duration is not None else self.rng.uniform(22.0, 34.0)
        self._idle_play_clones = playmates
        self._idle_play_until = ts + max(3.0, play_duration)
        self._idle_play_next_at = self._idle_play_until + self._next_idle_play_delay()
        self._sync_subagent_clones()
        if announce and self.isVisible() and not self.isMinimized() and self._dock_side is None:
            names = "、".join(form_by_id(item.form_id).name for item in playmates)
            busy = {
                PetAction.DRAGGING,
                PetAction.FALLING,
                PetAction.JUMP_UP,
                PetAction.CLIMBING,
                PetAction.LANDING,
                PetAction.TRANSFORM,
                PetAction.DIZZY,
                PetAction.SLEEPING,
                PetAction.PERCH_SLEEP,
                PetAction.DOCK_SLEEP,
                PetAction.SULK,
            }
            if self.action_machine.current not in busy and ts >= self._sulk_until:
                self._handling_clone_interaction = True
                try:
                    self._request_action(PetAction.HAPPY, now=ts, reason="idle_playmate_summon", force=True)
                    self.emit_particles("sparkles")
                    tracker = getattr(self, "reactions", None)
                    line = (
                        tracker._line("playmate_summon", names=names)
                        if tracker is not None and "playmate_summon" in getattr(tracker, "lines", {})
                        else f"叮！随机召唤出 {names} 来串门啦～"
                    )
                    self.say(line, preserve_action=True)
                finally:
                    self._handling_clone_interaction = False
        return list(playmates)

    def dismiss_idle_playmates(self, *, now: float | None = None) -> None:
        if not self._idle_play_clones:
            return
        ts = time.monotonic() if now is None else float(now)
        self._idle_play_clones = []
        self._idle_play_until = 0.0
        self._idle_play_next_at = max(self._idle_play_next_at, ts + self._next_idle_play_delay())
        self._sync_subagent_clones()

    def _tick_idle_playmates(self, now: float) -> None:
        if not hasattr(self, "subagent_clones"):
            return
        snap = getattr(getattr(self, "telemetry", None), "last_snapshot", None)
        real_subs = list(getattr(snap, "active_subagents", None) or [])
        agy_running = bool(snap is not None and getattr(snap, "running", False))
        clones_enabled = bool(self._agy().get("subagent_clones", True))
        quiet_states = {PetAction.SLEEPING, PetAction.PERCH_SLEEP, PetAction.DOCK_SLEEP, PetAction.SULK}

        if self._idle_play_clones:
            should_dismiss = (
                not clones_enabled
                or bool(real_subs)
                or agy_running
                or self._dock_side is not None
                or not self.isVisible()
                or self.isMinimized()
                or now < self._sulk_until
                or self.action_machine.current in quiet_states
                or now >= self._idle_play_until
            )
            if should_dismiss:
                self.dismiss_idle_playmates(now=now)
            return

        if not clones_enabled or real_subs or agy_running:
            return
        if now < self._idle_play_next_at:
            return
        comfort = self.config.section("comfort")
        hover_paused = self._hovered and bool(comfort.get("hover_pause", True))
        ctx = self.activity_director.context
        can_summon = (
            self.isVisible()
            and not self.isMinimized()
            and self._dock_side is None
            and now >= self._sulk_until
            and not self._purring
            and not self.interaction.active
            and not self.physics.active
            and not self.climb.active
            and not self.movement.is_walking
            and not self.control_panel.isVisible()
            and not self.food_panel.isVisible()
            and not hover_paused
            and not ctx.private
            and not ctx.late_night
            and self.action_machine.current in {PetAction.IDLE, PetAction.PERCH}
        )
        if can_summon:
            self.summon_idle_playmates(now=now)

    def _sync_subagent_clones(self, snapshot=None) -> None:
        if not hasattr(self, "subagent_clones"):
            return
        snap = snapshot if snapshot is not None else getattr(getattr(self, "telemetry", None), "last_snapshot", None)
        real_subagents = list(getattr(snap, "active_subagents", None) or [])
        preempted_playmates = False
        if real_subagents:
            if self._idle_play_clones:
                self._idle_play_clones = []
                self._idle_play_until = 0.0
                preempted_playmates = True
            subagents = real_subagents
        else:
            subagents = list(self._idle_play_clones)
        self.subagent_clones.sync(
            subagents,
            default_form=self.form_id,
            enabled=bool(self._agy().get("subagent_clones", True)),
            host_visible=self.isVisible() and not self.isMinimized(),
            silent_depart=preempted_playmates,
        )
        if self.subagent_clones.active_count > 0 or getattr(self.subagent_clones, "has_departing", False):
            self.subagent_clones.position_around(
                self._sprite_rect(),
                now=time.monotonic(),
                reduced_motion=self.renderer.reduced_motion,
                screen=self._screen_for_pet(),
                dock_edge=self._dock_edge,
                perched_window_rect=self._attached_window_qrect(),
            )

    def _on_subagent_interaction(self, event: CloneEvent) -> None:
        if not self.isVisible() or self.isMinimized() or self._dock_side is not None:
            return
        now = time.monotonic()
        accent = ACCENTS.get(event.form_id, "#c084fc")
        playmate = bool(getattr(event, "is_playmate", False))
        # Extend playtime slightly when the user actively plays with idle playmates
        if playmate and self._idle_play_clones and event.kind in {"clicked", "report", "high_five", "group_cheer"}:
            self._idle_play_until = min(now + 45.0, max(self._idle_play_until, now + 10.0))
        busy_actions = {
            PetAction.DRAGGING,
            PetAction.FALLING,
            PetAction.JUMP_UP,
            PetAction.CLIMBING,
            PetAction.LANDING,
            PetAction.TRANSFORM,
            PetAction.DIZZY,
        }
        quiet_actions = {PetAction.SLEEPING, PetAction.PERCH_SLEEP, PetAction.DOCK_SLEEP, PetAction.SULK}
        current = self.action_machine.current
        can_emote = current not in busy_actions and current not in quiet_actions and now >= self._sulk_until

        def pick_line(kind: str, fallback: str, **values: object) -> str:
            tracker = getattr(self, "reactions", None)
            if tracker is not None and kind in getattr(tracker, "lines", {}):
                return tracker._line(kind, **values)
            return fallback.format(**values)

        self._handling_clone_interaction = True
        try:
            if event.kind == "summoned":
                self.emit_relay_particles(from_side=event.side, accent=accent)
            elif event.kind == "handoff":
                self.emit_relay_particles(from_side=event.side, accent=accent)
                self.emit_particles("hearts" if playmate else "sparkles")
                if can_emote:
                    self._request_action(PetAction.WAVE, now=now, reason="subagent_handoff", force=True)
                    key = "playmate_done" if playmate else "subagent_done"
                    fb = "拜拜啦 {name}，下次闲了再一起玩～" if playmate else "辛苦啦 {name}，成果我收下啦～"
                    self.say(pick_line(key, fb, name=event.badge), preserve_action=True)
            elif event.kind == "clicked":
                self.emit_particles("hearts")
                if can_emote:
                    self._request_action(PetAction.HAPPY, now=now, reason="subagent_clicked", force=True)
                    key = "playmate_cheer" if playmate else "subagent_cheer"
                    fb = "喂，摸完 {name} 也要顺手摸摸我呀～" if playmate else "喂，摸完 {name} 也要多摸摸我才行～"
                    self.say(pick_line(key, fb, name=event.badge), preserve_action=True)
            elif event.kind == "report":
                self.emit_relay_particles(from_side=event.side, accent=accent)
                short_title = " ".join((event.title or ("晒太阳发呆" if playmate else "当前任务")).split())
                if len(short_title) > 16:
                    short_title = short_title[:15] + "…"
                if can_emote:
                    self._request_action(PetAction.WAVE, now=now, reason="subagent_report", force=True)
                    key = "playmate_report" if playmate else "subagent_report"
                    fb = "好呀好呀，和 {name} 一起{title}！" if playmate else "收到 {name} 的汇报：{title}！"
                    self.say(pick_line(key, fb, name=event.badge, title=short_title), preserve_action=True)
            elif event.kind == "high_five":
                self.emit_relay_particles(from_side=event.side, accent=accent)
                self.emit_particles("confetti")
                self.emit_particles("hearts")
                if can_emote:
                    self._request_action(PetAction.CELEBRATE, now=now, reason="subagent_high_five", force=True)
                    key = "playmate_high_five" if playmate else "subagent_high_five"
                    fb = "和 {name} 击掌贴贴！摸鱼搭子满分～" if playmate else "和 {name} 击掌成功！合作无间～"
                    self.say(pick_line(key, fb, name=event.badge), preserve_action=True)
            elif event.kind == "group_cheer":
                self.emit_particles("confetti")
                self.emit_particles("sparkles")
                if can_emote:
                    self._request_action(PetAction.CELEBRATE, now=now, reason="subagent_group_cheer", force=True)
                    key = "playmate_group_cheer" if playmate else "subagent_group_cheer"
                    fb = "闲时小派对！大家一起蹦起来～" if playmate else "全员干劲拉满，一起冲鸭！"
                    self.say(pick_line(key, fb), preserve_action=True)
            elif event.kind == "relay":
                self.emit_relay_particles(from_side=event.side, accent=accent)
                min_gap = 6.0 if playmate else 10.0
                if can_emote and now - self._last_clone_banter_at >= min_gap:
                    self._last_clone_banter_at = now
                    key = "playmate_relay" if playmate else "subagent_relay"
                    fb = "接住啦 {name}！我也回你一颗星星～" if playmate else "收到 {name} 传来的线索啦～"
                    self.say(pick_line(key, fb, name=event.badge), preserve_action=True)
        finally:
            self._handling_clone_interaction = False

    def _on_live_snapshot(self, snapshot) -> None:
        self.hud_bar.update_snapshot(snapshot)
        self._hud_anchor = None
        if self.token_meter.isVisible():
            self.token_meter.update_live(snapshot)
        self._sync_subagent_clones(snapshot)
        self._refresh_control_panel()
        settings = self._agy()
        if not settings.get("reactions", True) and not settings.get("follow_model"):
            return
        reactions = self.reactions.observe(
            snapshot,
            now=time.monotonic(),
            follow_model=bool(settings.get("follow_model", False)),
            current_form=self.form_id,
        )
        for reaction in reactions:
            if reaction.form:
                self.set_form(reaction.form, announce=False)
            if not settings.get("reactions", True):
                continue
            busy = (
                self.interaction.active
                or self.physics.active
                or self.action_machine.current in _SLEEP_ACTIONS
                or time.monotonic() < self._sulk_until
                or self._purring
            )
            action_name = reaction.action
            if action_name == "WORKING" and not settings.get("autonomy", True):
                action_name = "THINKING"  # WORKING loops; only autonomy ends it
            if (
                action_name not in {"WORKING", "PERCH"}
                and self.surface_tracker.attached
                and self.action_machine.current in _EDGE_ACTION_ASSETS
            ):
                # Sitting on a window edge: cheer with words, don't stand up.
                action_name = None
            elif self._dock_side is not None and action_name not in {"WORKING", "IDLE"}:
                # Docked on screen edge: keep bespoke peek/work pose and react with speech + particles.
                action_name = None
            if action_name and not busy:
                try:
                    self._request_action(PetAction.coerce(action_name), reason=f"agy_{reaction.kind}")
                except ValueError:
                    pass
            particle = getattr(reaction, "particle", None)
            if particle:
                self.emit_particles(particle)
            self.say(reaction.text, preserve_action=True)

    def _personality(self) -> str:
        return normalize_personality(self.config.get("personality", "standard"))

    def quit_app(self) -> None:
        self.save_snapshot()
        self.telemetry.stop()
        self.subagent_clones.close_all()
        self.hud_bar.hide()
        self.token_meter.hide()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self.quit_app()
        event.accept()
