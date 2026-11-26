"""Floating interactive miniature pet clones for active Antigravity subagents.

Reuses the existing 5-form runtime sprite assets (carbon / hydergon / neon /
argon / claude) scaled down to ~44% height, matching each subagent's own model
family when known and falling back to the main pet's active form.

Supports rich host <-> subagent interplay:
- Pop-out summon slide & celebratory handoff return when a subagent completes
- Host mood/action resonance (head pat, eating, celebrate, sulk, waiting, drag)
- Periodic collaborative banter + directional relay pulse into the host pet
- Direct clone mouse interaction: hover status pill, left-click cheer, double-
  click progress report, right-click group cheer, and drag-to-host high-five
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from agy.characters import form_by_id, form_for_model_label, normalize_form
from agy.telemetry import SubagentInfo
from animation.asset_registry import AssetRegistry
from animation.clip import PetAction
from pet.particles import ParticleSystem

MAX_VISIBLE_CLONES = 6
MAX_ANIMATION_FRAMES = 4
FRAME_INTERVAL_SECONDS = 0.18
CLONE_PHASE_STEP_SECONDS = 0.45
SUMMON_SLIDE_SECONDS = 0.68
HANDOFF_DURATION_SECONDS = 1.25
HIGH_FIVE_RADIUS_PX = 140.0
CLONE_HIGH_FIVE_RADIUS_PX = 115.0
GLIDE_RETURN_SECONDS = 0.36
RELAY_INTERVAL_MIN_SECONDS = 12.0
RELAY_INTERVAL_MAX_SECONDS = 19.0
PLAY_RELAY_INTERVAL_MIN_SECONDS = 5.5
PLAY_RELAY_INTERVAL_MAX_SECONDS = 9.5
DRAG_THRESHOLD_PX = 6
CLICK_DEBOUNCE_MS = 240
PLAYMATE_PREFIX = "idle-play-"
HOST_CALL_NAME = "姐姐"


def is_playmate_id(conversation_id: str) -> bool:
    return str(conversation_id or "").startswith(PLAYMATE_PREFIX)

_ACCENTS: dict[str, str] = {
    "carbon": "#4b5563",
    "hydergon": "#2b8fd6",
    "neon": "#c026d3",
    "argon": "#8b5cf6",
    "claude": "#ea580c",
}

_SUMMON_LINES: tuple[str, ...] = (
    "收到！开工啦～",
    "马上查好！",
    "交给我吧！",
    "小分身就位～",
)

_CLICK_LINES: tuple[str, ...] = (
    "谢谢夸奖！干劲满格",
    "被摸头了！效率翻倍",
    "嘿嘿，继续努力！",
    "收到打气，冲鸭！",
)

def _format_host_line(template: str, host_name: str = HOST_CALL_NAME) -> str:
    if "{host}" not in template:
        return template
    name = (host_name or HOST_CALL_NAME).strip() or HOST_CALL_NAME
    if any("\u4e00" <= ch <= "\u9fff" for ch in name):
        return (
            template.replace(" {host} ", name)
            .replace(" {host}", name)
            .replace("{host} ", name)
            .replace("{host}", name)
        )
    return template.replace("{host}", name)


_RELAY_LINES: tuple[str, ...] = (
    "发现线索啦！",
    "同步给 {host}～",
    "这块我兜底啦！",
    "整理好结果啦！",
)

_HANDOFF_LINES: tuple[str, ...] = (
    "搞定！交卷啦～",
    "汇报完毕，收工！",
    "交给 {host} 啦～",
)

_HIGH_FIVE_LINES: tuple[str, ...] = (
    "击掌！合作无间～",
    "贴贴！配合满分！",
    "耶！最佳拍档～",
)

_GROUP_CHEER_LINES: tuple[str, ...] = (
    "全员出击，起飞！",
    "小队干劲拉满～",
    "一起冲鸭！",
)

_PLAY_SUMMON_LINES: tuple[str, ...] = (
    "嘿！来找 {host} 玩～",
    "摸鱼时间，一起玩！",
    "随机分身来串门～",
    "闲着也是闲着，嗨！",
)

_PLAY_CLICK_LINES: tuple[str, ...] = (
    "嘿嘿，好痒呀～",
    "再来摸一下嘛！",
    "开心到转圈圈～",
    "贴贴！今天超开心",
)

_PLAY_RELAY_LINES: tuple[str, ...] = (
    "接招！星光球～",
    "比比谁跳得高！",
    "晒太阳好舒服～",
    "发射一颗爱心球！",
)

_PLAY_HANDOFF_LINES: tuple[str, ...] = (
    "超开心，下次再约～",
    "先回口袋啦，拜拜！",
    "闲了再叫我玩哦～",
)

_PLAY_HIGH_FIVE_LINES: tuple[str, ...] = (
    "击掌！最爱一起玩",
    "贴贴！玩伴满分～",
    "耶！玩得超开心～",
)

_PLAY_GROUP_CHEER_LINES: tuple[str, ...] = (
    "闲时派对开场啦～",
    "一起蹦蹦跳跳！",
    "摸鱼小队万岁～",
)

_PET_RUB_LINES: tuple[str, ...] = (
    "呜哇…好舒服呀～",
    "呼噜呼噜，别停嘛",
    "被揉得软乎乎啦～",
    "最喜欢揉头啦！",
)

_TRICK_LINES: tuple[str, ...] = (
    "看我转个小圈圈～",
    "锵锵！变个小花样",
    "{host} 快看我这招！",
    "哒哒哒，跳一支舞",
)

_GIFT_SHARE_LINES: tuple[str, ...] = (
    "小礼物送给 {host}！",
    "给 {host} 囤的小鱼干",
    "偷偷塞颗星星糖～",
    "{host} 辛苦啦，收下",
)

_CLONE_BUDDY_LINES: tuple[str, ...] = (
    "贴贴！最佳搭档～",
    "嘿嘿，击掌成功！",
    "姐妹同心效率翻倍",
    "一起陪 {host} 玩吧～",
)

_CLONE_CHAT_PAIRS: tuple[tuple[str, str], ...] = (
    ("偷偷夸 {host} 一句～", "{host} 超厉害的！"),
    ("分你一半小鱼干～", "哇谢谢，好香呀！"),
    ("比比谁跳得更高！", "我肯定跳得更高～"),
    ("一起逗 {host} 笑吧！", "好呀好呀，冲鸭！"),
    ("休息下伸个懒腰～", "呼——精神满满啦"),
)

_WORK_CHAT_PAIRS: tuple[tuple[str, str], ...] = (
    ("这块我快查完啦～", "加油！我来接力～"),
    ("线索同步给你啦！", "收到，马上核对～"),
    ("一起帮 {host} 兜底！", "嗯嗯，配合满分～"),
)

_PLAY_IDLE_POSES: tuple[PetAction, ...] = (
    PetAction.IDLE,
    PetAction.BLINK,
    PetAction.GLANCE,
    PetAction.HAPPY,
    PetAction.WAVE,
    PetAction.STRETCH,
    PetAction.THINKING,
    PetAction.PLAY_DANCE,
    PetAction.WORK_DRAWING,
    PetAction.WORK_READING,
    PetAction.QUOTA_GIFT,
)

_WORK_MICRO_BREAK_POSES: tuple[PetAction, ...] = (
    PetAction.THINKING,
    PetAction.STRETCH,
    PetAction.GLANCE,
    PetAction.WAVE,
)

_ACTION_FRAME_INTERVALS: dict[PetAction, float] = {
    PetAction.IDLE: 0.32,
    PetAction.BLINK: 0.26,
    PetAction.GLANCE: 0.30,
    PetAction.THINKING: 0.30,
    PetAction.STRETCH: 0.30,
    PetAction.TIRED: 0.32,
    PetAction.WORK_READING: 0.32,
    PetAction.WORK_SEARCHING: 0.30,
    PetAction.WORK_DRAWING: 0.25,
    PetAction.WORK_COMPACTING: 0.22,
    PetAction.QUOTA_GIFT: 0.25,
    PetAction.WAVE: 0.24,
    PetAction.HAPPY: 0.24,
    PetAction.PET_PURR: 0.24,
    PetAction.HEAD_PAT: 0.24,
    PetAction.PLAY_DANCE: 0.18,
    PetAction.CELEBRATE: 0.18,
    PetAction.HIGH_FIVE: 0.18,
    PetAction.GIFT_TOSS: 0.18,
    PetAction.WORKING: 0.18,
}


def _work_pose_for_title(title: str) -> PetAction:
    text = (title or "").lower()
    if any(k in text for k in ("画", "图", "设计", "ui", "样式", "排版", "绘")):
        return PetAction.WORK_DRAWING
    if any(k in text for k in ("查", "搜", "分析", "日志", "定位", "排障", "search", "grep")):
        return PetAction.WORK_SEARCHING
    if any(k in text for k in ("读", "文档", "审查", "核对", "看", "read", "review")):
        return PetAction.WORK_READING
    if any(k in text for k in ("整理", "压缩", "重构", "归档", "合并", "compact")):
        return PetAction.WORK_COMPACTING
    return PetAction.WORKING


_HOST_MOOD_RESPONSES: dict[PetAction, tuple[PetAction, float, str | None, tuple[str, ...]]] = {
    PetAction.HEAD_PAT: (
        PetAction.HAPPY,
        2.4,
        "hearts",
        ("也摸摸我嘛～", "{host} 被夸啦～", "好羡慕，我也想！"),
    ),
    PetAction.PET_PURR: (
        PetAction.HAPPY,
        2.8,
        "hearts",
        ("{host} 好幸福呀～", "我也要蹭蹭！"),
    ),
    PetAction.EATING: (
        PetAction.WAVE,
        2.6,
        "sparkles",
        ("好香！留一口嘛～", "干完活我也想吃！", "{host} 分我小鱼干"),
    ),
    PetAction.CELEBRATE: (
        PetAction.CELEBRATE,
        2.2,
        "sparkles",
        ("耶！一起庆祝～", "太棒啦 {host}！"),
    ),
    PetAction.HAPPY: (
        PetAction.HAPPY,
        1.8,
        None,
        ("{host} 开心我也开心",),
    ),
    PetAction.SULK: (
        PetAction.WAVE,
        2.8,
        None,
        ("别生气啦 {host}…", "加快进度哄你！"),
    ),
    PetAction.ANGRY: (
        PetAction.POKE_REACT,
        1.8,
        "sweat",
        ("哇！{host} 生气了…", "我乖乖干活去！"),
    ),
    PetAction.WAITING_USER: (
        PetAction.WAITING_USER,
        3.2,
        "alert",
        ("{host} 等你确认哦！", "快看看确认弹窗～"),
    ),
    PetAction.SLEEPING: (
        PetAction.WORKING,
        2.6,
        None,
        ("嘘，{host} 睡着啦～",),
    ),
    PetAction.PERCH_SLEEP: (
        PetAction.WORKING,
        2.6,
        None,
        ("嘘，{host} 打盹中～",),
    ),
    PetAction.DRAGGING: (
        PetAction.FALLING,
        1.5,
        None,
        ("等等我呀 {host}！", "慢点飞——"),
    ),
    PetAction.FALLING: (
        PetAction.FALLING,
        1.4,
        None,
        ("{host} 抓稳啦！", "我来接应～"),
    ),
}


@dataclass(frozen=True, slots=True)
class CloneEvent:
    """Structured host <-> subagent interaction event sent to PetWindow."""

    kind: str  # summoned / handoff / clicked / report / high_five / group_cheer / relay / pet_rub / trick / gift_share / clone_buddy / clone_chat
    conversation_id: str
    form_id: str
    badge: str
    title: str
    side: int  # -1 left of host, +1 right of host
    text: str = ""
    is_playmate: bool = False


@dataclass(slots=True)
class _CloneRuntime:
    spawned_at: float
    pose_action: PetAction | None = None
    pose_until: float = 0.0
    nudge_until: float = 0.0
    nudge_strength: float = 16.0
    nudge_dir_x: int = 0
    last_side: int = -1
    dragging: bool = False
    glide_from: QPoint | None = None
    glide_started_at: float = 0.0
    glide_hold_until: float = 0.0
    motion_phase: float = 0.0
    motion_speed: float = 1.0
    idle_action: PetAction | None = None
    idle_until: float = 0.0
    idle_glance_until: float = 0.0
    next_hop_at: float = 0.0
    hop_started_at: float = 0.0
    hop_duration: float = 0.42
    hop_height: float = 8.0
    next_ambient_fx_at: float = 0.0


@dataclass(slots=True)
class _DepartingClone:
    conversation_id: str
    form_id: str
    badge: str
    title: str
    side: int
    start_pos: QPoint
    started_at: float
    duration: float
    widget: "SubagentCloneWidget"
    poof_emitted: bool = False


def _compact_text(text: str, max_chars: int = 16) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max(1, max_chars - 1)] + "…"


class SubagentCloneWidget(QWidget):
    """One compact always-on-top interactive miniature companion representing a subagent."""

    BUBBLE_TOP_PAD = 26

    def __init__(self, *, topmost: bool = True, rng: random.Random | None = None) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if topmost:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("AGY 子代理分身")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)

        self._pixmap = QPixmap()
        self._sprite_w = 64
        self._sprite_h = 92
        self._badge = ""
        self._accent = QColor("#8b5cf6")
        self._opacity = 1.0
        self._bob_y = 0.0
        self._tilt_deg = 0.0
        self._render_scale = 1.0
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._mirrored = False
        self._frame_index = 0
        self._action = PetAction.WORKING
        self._hovered = False
        self._hover_label = ""
        self._bubble_text = ""
        self._bubble_until = 0.0
        self._particles = ParticleSystem(rng)

        self._press_global: QPoint | None = None
        self._press_window_pos: QPoint | None = None
        self._dragging = False
        self._suppress_next_release = False
        self._click_debounce_ms = CLICK_DEBOUNCE_MS
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._fire_pending_click)

        # Mouse back-and-forth head-rub & wheel-trick state
        self._rub_last_x: float | None = None
        self._rub_dir: int = 0
        self._rub_flips: int = 0
        self._rub_dist: float = 0.0
        self._rub_window_start: float = 0.0
        self._rub_cooldown_until: float = 0.0
        self._wheel_cooldown_until: float = 0.0

        self._on_click: Callable[[SubagentCloneWidget], None] | None = None
        self._on_double_click: Callable[[SubagentCloneWidget], None] | None = None
        self._on_right_click: Callable[[SubagentCloneWidget], None] | None = None
        self._on_drag_start: Callable[[SubagentCloneWidget], None] | None = None
        self._on_drag_end: Callable[[SubagentCloneWidget, QPoint], None] | None = None
        self._on_pet_rub: Callable[[SubagentCloneWidget], None] | None = None
        self._on_wheel_trick: Callable[[SubagentCloneWidget], None] | None = None
        self._on_middle_click: Callable[[SubagentCloneWidget], None] | None = None

        self._badge_font = QFont()
        self._badge_font.setPointSize(8)
        self._badge_font.setWeight(QFont.Weight.DemiBold)
        self._bubble_font = QFont()
        self._bubble_font.setPointSize(8)
        self._bubble_font.setWeight(QFont.Weight.Medium)
        self.setFixedSize(112, 148)

    @property
    def mirrored(self) -> bool:
        return self._mirrored

    @property
    def frame_index(self) -> int:
        return self._frame_index

    @property
    def current_action(self) -> PetAction:
        return self._action

    @property
    def bubble_text(self) -> str:
        return self._bubble_text

    @property
    def hovered(self) -> bool:
        return self._hovered

    @property
    def dragging(self) -> bool:
        return self._dragging

    @property
    def render_scale(self) -> float:
        return self._render_scale

    def bind_handlers(
        self,
        *,
        on_click: Callable[[SubagentCloneWidget], None] | None = None,
        on_double_click: Callable[[SubagentCloneWidget], None] | None = None,
        on_right_click: Callable[[SubagentCloneWidget], None] | None = None,
        on_drag_start: Callable[[SubagentCloneWidget], None] | None = None,
        on_drag_end: Callable[[SubagentCloneWidget, QPoint], None] | None = None,
        on_pet_rub: Callable[[SubagentCloneWidget], None] | None = None,
        on_wheel_trick: Callable[[SubagentCloneWidget], None] | None = None,
        on_middle_click: Callable[[SubagentCloneWidget], None] | None = None,
    ) -> None:
        self._on_click = on_click
        self._on_double_click = on_double_click
        self._on_right_click = on_right_click
        self._on_drag_start = on_drag_start
        self._on_drag_end = on_drag_end
        self._on_pet_rub = on_pet_rub
        self._on_wheel_trick = on_wheel_trick
        self._on_middle_click = on_middle_click

    @property
    def visual_sprite_size(self) -> tuple[int, int]:
        return (self._sprite_w, self._sprite_h)

    def configure(
        self,
        *,
        pixmap: QPixmap,
        badge: str,
        accent: str,
        tooltip: str,
        opacity: float = 1.0,
        min_frame_size: tuple[int, int] | None = None,
        frame_index: int = 0,
        mirrored: bool = False,
        hover_label: str = "",
    ) -> None:
        self._pixmap = pixmap
        self._badge = badge
        self._accent = QColor(accent)
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self._frame_index = int(frame_index)
        self._mirrored = bool(mirrored)
        self._hover_label = _compact_text(hover_label, 14) if hover_label else ""
        self.setToolTip(tooltip)
        frame_w = pixmap.width() if not pixmap.isNull() else 64
        frame_h = pixmap.height() if not pixmap.isNull() else 84
        if min_frame_size is not None:
            frame_w = max(frame_w, int(min_frame_size[0]))
            frame_h = max(frame_h, int(min_frame_size[1]))
        self._sprite_w = max(44, frame_w)
        self._sprite_h = max(64, frame_h)
        w = max(148, frame_w + 54)
        h = max(124, frame_h + 34 + self.BUBBLE_TOP_PAD)
        if (self.width(), self.height()) != (w, h):
            self.setFixedSize(w, h)
        self.update()

    def set_frame(
        self,
        pixmap: QPixmap,
        *,
        frame_index: int = 0,
        mirrored: bool = False,
        action: PetAction = PetAction.WORKING,
    ) -> None:
        if pixmap.isNull():
            return
        idx = int(frame_index)
        mirror_flag = bool(mirrored)
        if (
            idx == self._frame_index
            and mirror_flag == self._mirrored
            and action == self._action
            and not self._pixmap.isNull()
            and pixmap.cacheKey() == self._pixmap.cacheKey()
        ):
            return
        self._pixmap = pixmap
        self._frame_index = idx
        self._mirrored = mirror_flag
        self._action = action
        self.update()

    def say(self, text: str, *, now: float | None = None, duration: float = 2.4) -> None:
        clean = _compact_text(text, 15)
        if not clean:
            return
        ts = time.monotonic() if now is None else float(now)
        self._bubble_text = clean
        self._bubble_until = ts + max(0.4, float(duration))
        if self.isVisible():
            self.raise_()
        self.update()

    def clear_bubble(self) -> None:
        if self._bubble_text:
            self._bubble_text = ""
            self._bubble_until = 0.0
            self.update()

    def emit_particles(self, effect: str, *, reduced_motion: bool = False) -> int:
        self._particles.reduced_motion = bool(reduced_motion)
        count = self._particles.emit(
            effect,
            origin_x=self.width() / 2.0,
            origin_y=float(self.BUBBLE_TOP_PAD) + max(24.0, (self.height() - self.BUBBLE_TOP_PAD - 24.0) * 0.42),
            spread_w=max(44.0, self.width() * 0.55),
        )
        if count:
            self.update()
        return count

    def tick_fx(self, dt: float, *, now: float, reduced_motion: bool = False) -> None:
        self._particles.reduced_motion = bool(reduced_motion)
        dirty = False
        if self._bubble_text and now >= self._bubble_until:
            self._bubble_text = ""
            self._bubble_until = 0.0
            dirty = True
        if self._particles.active:
            if reduced_motion:
                self._particles.clear()
            else:
                self._particles.update(dt)
            dirty = True
        if dirty:
            self.update()

    def set_bob(
        self,
        offset_y: float,
        opacity: float,
        *,
        scale: float = 1.0,
        scale_x: float | None = None,
        scale_y: float | None = None,
        tilt_deg: float = 0.0,
    ) -> None:
        new_bob = float(offset_y)
        new_op = max(0.0, min(1.0, float(opacity)))
        new_scale = max(0.20, min(1.35, float(scale)))
        new_sx = max(0.20, min(1.35, float(new_scale if scale_x is None else scale_x)))
        new_sy = max(0.20, min(1.35, float(new_scale if scale_y is None else scale_y)))
        new_tilt = max(-14.0, min(14.0, float(tilt_deg)))
        if (
            abs(new_bob - self._bob_y) < 0.05
            and abs(new_op - self._opacity) < 0.005
            and abs(new_scale - self._render_scale) < 0.005
            and abs(new_sx - self._scale_x) < 0.004
            and abs(new_sy - self._scale_y) < 0.004
            and abs(new_tilt - self._tilt_deg) < 0.12
        ):
            return
        self._bob_y = new_bob
        self._opacity = new_op
        self._render_scale = new_scale
        self._scale_x = new_sx
        self._scale_y = new_sy
        self._tilt_deg = new_tilt
        self.update()

    def set_topmost(self, topmost: bool) -> None:
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(topmost))
        if was_visible:
            self.show()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._rub_last_x = None
        self._rub_dir = 0
        self._rub_flips = 0
        self._rub_dist = 0.0
        self.update()
        super().leaveEvent(event)

    def _fire_pending_click(self) -> None:
        if self.isVisible() and not self._dragging and self._on_click is not None:
            self._on_click(self)

    def hideEvent(self, event) -> None:
        self._click_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self._click_timer.stop()
        super().closeEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_window_pos = self.pos()
            self._dragging = False
            self._suppress_next_release = False
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton and self._on_middle_click is not None:
            self._click_timer.stop()
            self._on_middle_click(self)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_global is not None and self._press_window_pos is not None:
            delta = event.globalPosition().toPoint() - self._press_global
            if not self._dragging and delta.manhattanLength() > DRAG_THRESHOLD_PX:
                self._click_timer.stop()
                self._dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                if self._on_drag_start is not None:
                    self._on_drag_start(self)
            if self._dragging:
                self.move(self._press_window_pos + delta)
                event.accept()
                return
        elif self._on_pet_rub is not None and self._hovered:
            pos = event.position()
            if pos.y() >= self.BUBBLE_TOP_PAD - 6:
                now = time.monotonic()
                if now >= self._rub_cooldown_until:
                    x = float(pos.x())
                    if self._rub_last_x is None or now - self._rub_window_start > 1.25:
                        self._rub_last_x = x
                        self._rub_dir = 0
                        self._rub_flips = 0
                        self._rub_dist = 0.0
                        self._rub_window_start = now
                    else:
                        dx = x - self._rub_last_x
                        if abs(dx) >= 3.5:
                            direction = 1 if dx > 0 else -1
                            if self._rub_dir != 0 and direction != self._rub_dir:
                                self._rub_flips += 1
                            self._rub_dir = direction
                            self._rub_dist += abs(dx)
                            self._rub_last_x = x
                            if self._rub_flips >= 3 and self._rub_dist >= 26.0:
                                self._rub_cooldown_until = now + 2.6
                                self._rub_flips = 0
                                self._rub_dist = 0.0
                                self._on_pet_rub(self)
        super().mouseMoveEvent(event)

    def wheelEvent(self, event) -> None:
        if self._on_wheel_trick is not None and not self._dragging:
            now = time.monotonic()
            if now >= self._wheel_cooldown_until:
                self._wheel_cooldown_until = now + 1.4
                self._on_wheel_trick(self)
            event.accept()
            return
        super().wheelEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_global is not None:
            was_dragging = self._dragging
            suppressed = self._suppress_next_release
            self._press_global = None
            self._press_window_pos = None
            self._dragging = False
            self._suppress_next_release = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if was_dragging:
                self._click_timer.stop()
                if self._on_drag_end is not None:
                    self._on_drag_end(self, self.frameGeometry().center())
            elif not suppressed and self._on_click is not None:
                self._click_timer.start(self._click_debounce_ms)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self._press_global = None
            self._press_window_pos = None
            self._dragging = False
            self._suppress_next_release = True
            if self._on_double_click is not None:
                self._on_double_click(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        self._click_timer.stop()
        if self._on_right_click is not None:
            self._on_right_click(self)
            event.accept()
            return
        super().contextMenuEvent(event)

    def paintEvent(self, _event) -> None:
        if self._opacity <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)

        # Soft halo shadow under the floating mini clone (brighter on hover/drag, scales on pop-in/poof-out)
        cx = self.width() / 2.0
        shadow_y = self.height() - 24.0
        s = self._render_scale
        painter.setPen(Qt.PenStyle.NoPen)
        halo_alpha = 88 if (self._hovered or self._dragging) else 42
        halo_w = (56.0 if (self._hovered or self._dragging) else 48.0) * max(0.35, s)
        painter.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), halo_alpha))
        painter.drawEllipse(QRectF(cx - halo_w / 2.0, shadow_y - 4.5, halo_w, 10.0 * max(0.4, s)))

        if self._particles.active:
            self._particles.paint(painter, layer="back")

        if not self._pixmap.isNull():
            hover_lift = -3.0 if self._hovered and not self._dragging else 0.0
            fw = float(self._pixmap.width())
            fh = float(self._pixmap.height())
            foot_y = max(float(self.BUBBLE_TOP_PAD) - 2.0 + fh, shadow_y + self._bob_y + hover_lift)
            sx, sy = self._scale_x, self._scale_y
            if abs(sx - 1.0) > 0.004 or abs(sy - 1.0) > 0.004 or abs(self._tilt_deg) > 0.1:
                painter.save()
                painter.translate(cx, foot_y)
                if abs(self._tilt_deg) > 0.1:
                    painter.rotate(self._tilt_deg)
                if abs(sx - 1.0) > 0.004 or abs(sy - 1.0) > 0.004:
                    painter.scale(sx, sy)
                painter.drawPixmap(round(-fw / 2.0), round(-fh), self._pixmap)
                painter.restore()
            else:
                px = (self.width() - fw) / 2.0
                py = foot_y - fh
                painter.drawPixmap(round(px), round(py), self._pixmap)

        if self._particles.active:
            self._particles.paint(painter, layer="front")

        # Top mini comic bubble (warm cream + theme accent border, matching host bubble!)
        shown_bubble = self._bubble_text or (self._hover_label if self._hovered else "")
        if shown_bubble:
            is_speech = bool(self._bubble_text)
            painter.setFont(self._bubble_font)
            fm = QFontMetrics(self._bubble_font)
            text = fm.elidedText(shown_bubble, Qt.TextElideMode.ElideRight, max(44, self.width() - 14))
            bw = min(self.width() - 4, max(44, fm.horizontalAdvance(text) + 14))
            bh = min(self.BUBBLE_TOP_PAD - 5, fm.height() + 6)
            bx = (self.width() - bw) / 2.0
            by = 1.5
            rect = QRectF(bx, by, bw, bh)
            border_c = QColor(self._accent)
            if not border_c.isValid() or border_c.lightness() > 215 or border_c.saturation() < 35:
                border_c = QColor("#a78bfa")
            if is_speech:
                bg = QColor(255, 253, 251, 250)
                fg = QColor("#2a1b3d")
                pen_w = 1.6
            else:
                bg = QColor(245, 243, 255, 236)
                fg = QColor("#4c3b73")
                pen_w = 1.2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(46, 24, 104, 34))
            painter.drawRoundedRect(rect.translated(0.0, 1.5), 9.0, 9.0)
            painter.setBrush(bg)
            painter.setPen(QPen(border_c, pen_w))
            painter.drawRoundedRect(rect, 9.0, 9.0)
            painter.setPen(fg)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        # Keep bottom clean by default; show light pill badge on hover, drag, or overflow (+N)
        show_badge = bool(self._badge) and (self._hovered or self._dragging or "+" in self._badge)
        if show_badge:
            painter.setFont(self._badge_font)
            fm = QFontMetrics(self._badge_font)
            bw = min(self.width() - 8, max(34, fm.horizontalAdvance(self._badge) + 14))
            bh = fm.height() + 5
            bx = (self.width() - bw) / 2.0
            by = self.height() - bh - 2.0
            pill = QRectF(bx, by, bw, bh)
            painter.setBrush(QColor(255, 253, 251, 238))
            painter.setPen(QPen(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 195), 1.3))
            painter.drawRoundedRect(pill, bh / 2.0, bh / 2.0)
            painter.setPen(QColor("#2a1b3d"))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, self._badge)


class SubagentCloneManager:
    """Manages interactive miniature floating clones orbiting the main desktop pet."""

    def __init__(
        self,
        characters_root: Path,
        base_manifest: Path,
        *,
        topmost: bool = True,
        on_interaction: Callable[[CloneEvent], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._characters_root = Path(characters_root)
        self._base_manifest = Path(base_manifest)
        self._topmost = bool(topmost)
        self._on_interaction = on_interaction
        self._rng = rng or random.Random()
        self._registries: dict[str, AssetRegistry] = {}
        self._frame_cache: dict[tuple[str, int, bool, PetAction], tuple[QPixmap, ...]] = {}
        self._widgets: list[SubagentCloneWidget] = []
        self._entries: list[tuple[SubagentInfo, str, str]] = []  # (info, form_id, badge)
        self._runtime: dict[str, _CloneRuntime] = {}
        self._departing: list[_DepartingClone] = []
        self._enabled = True
        self._host_visible = True
        self._host_form = "carbon"
        self._host_name: str = HOST_CALL_NAME
        self._sprite_height = 96
        self._fade = 0.0
        self._last_host_rect: QRect | None = None
        self._last_dock_edge: str | None = None
        self._last_reduced_motion = False
        self._last_tick_now: float | None = None
        self._last_mood_at: dict[PetAction, float] = {}
        self._next_relay_at = 0.0

    def set_host_name(self, name: str, *, form_id: str | None = None) -> None:
        cleaned = (name or "").strip()
        self._host_name = cleaned or HOST_CALL_NAME

    def _host_display_name(self) -> str:
        return self._host_name or HOST_CALL_NAME

    def _format_line(self, template: str) -> str:
        return _format_host_line(template, self._host_display_name())

    def _make_runtime(self, now: float, side: int) -> _CloneRuntime:
        return _CloneRuntime(
            spawned_at=now,
            last_side=side,
            motion_phase=self._rng.uniform(0.0, math.tau),
            motion_speed=self._rng.uniform(0.86, 1.16),
            next_hop_at=now + self._rng.uniform(3.8, 8.2),
            next_ambient_fx_at=now + self._rng.uniform(5.5, 11.0),
        )

    @property
    def active_count(self) -> int:
        return len(self._entries)

    @property
    def has_departing(self) -> bool:
        return bool(self._departing)

    @property
    def visible_widgets(self) -> tuple[SubagentCloneWidget, ...]:
        return tuple(w for w in self._widgets if w.isVisible())

    @property
    def departing_widgets(self) -> tuple[SubagentCloneWidget, ...]:
        return tuple(d.widget for d in self._departing if d.widget.isVisible())

    @property
    def all_visible_widgets(self) -> tuple[SubagentCloneWidget, ...]:
        return self.visible_widgets + self.departing_widgets

    def set_topmost(self, topmost: bool) -> None:
        self._topmost = bool(topmost)
        for widget in self._widgets:
            widget.set_topmost(self._topmost)
        for dep in self._departing:
            dep.widget.set_topmost(self._topmost)

    def set_scale_from_host(self, host_sprite_height: int) -> None:
        target = max(72, min(124, round(host_sprite_height * 0.44)))
        if abs(target - self._sprite_height) >= 4:
            self._sprite_height = target

    def _emit_event(self, event: CloneEvent) -> None:
        if self._on_interaction is None:
            return
        try:
            self._on_interaction(event)
        except Exception:
            pass

    def _mini_frames(
        self,
        form_id: str,
        *,
        mirrored: bool = False,
        action: PetAction = PetAction.WORKING,
    ) -> tuple[QPixmap, ...]:
        norm = normalize_form(form_id)
        key = (norm, self._sprite_height, bool(mirrored), action)
        cached = self._frame_cache.get(key)
        if cached is not None:
            return cached
        registry = self._registries.get(norm)
        if registry is None:
            try:
                registry = AssetRegistry(self._characters_root / norm, base_manifest=self._base_manifest)
                self._registries[norm] = registry
            except Exception:
                return ()
        candidates = (
            (PetAction.WORKING, PetAction.IDLE)
            if action == PetAction.WORKING
            else (action, PetAction.HAPPY, PetAction.WORKING, PetAction.IDLE)
        )
        raw_frames: list[QPixmap] = []
        for candidate in candidates:
            try:
                clip = registry.clip_for(candidate, height=187, direction="down")
                valid = [frame.pixmap for frame in clip.frames if not frame.pixmap.isNull()][:MAX_ANIMATION_FRAMES]
                if valid:
                    raw_frames = valid
                    break
            except Exception:
                continue
        if not raw_frames:
            return ()
        normal = tuple(
            pix.scaledToHeight(self._sprite_height, Qt.TransformationMode.SmoothTransformation)
            for pix in raw_frames
        )
        mirror_tx = QTransform().scale(-1.0, 1.0)
        flipped = tuple(
            pix.transformed(mirror_tx, Qt.TransformationMode.SmoothTransformation)
            for pix in normal
        )
        self._frame_cache[(norm, self._sprite_height, False, action)] = normal
        self._frame_cache[(norm, self._sprite_height, True, action)] = flipped
        return flipped if mirrored else normal

    def _mini_pixmap(
        self,
        form_id: str,
        *,
        mirrored: bool = False,
        action: PetAction = PetAction.WORKING,
    ) -> QPixmap:
        frames = self._mini_frames(form_id, mirrored=mirrored, action=action)
        return frames[0] if frames else QPixmap()

    def _clear_departing(self) -> None:
        for dep in self._departing:
            dep.widget.hide()
            dep.widget.close()
            dep.widget.deleteLater()
        self._departing.clear()

    def _index_for_widget(self, widget: SubagentCloneWidget) -> int | None:
        for idx in range(len(self._entries)):
            if idx < len(self._widgets) and self._widgets[idx] is widget:
                return idx
        return None

    def _attach_widget_handlers(self, widget: SubagentCloneWidget) -> None:
        widget.bind_handlers(
            on_click=self._handle_widget_click,
            on_double_click=self._handle_widget_double_click,
            on_right_click=self._handle_widget_right_click,
            on_drag_start=self._handle_widget_drag_start,
            on_drag_end=self._handle_widget_drag_end,
            on_pet_rub=self._handle_widget_pet_rub,
            on_wheel_trick=self._handle_widget_wheel_trick,
            on_middle_click=self._handle_widget_middle_click,
        )

    def _handle_widget_click(self, widget: SubagentCloneWidget) -> None:
        idx = self._index_for_widget(widget)
        if idx is not None:
            self.trigger_click(idx)

    def _handle_widget_double_click(self, widget: SubagentCloneWidget) -> None:
        idx = self._index_for_widget(widget)
        if idx is not None:
            self.trigger_report(idx)

    def _handle_widget_right_click(self, widget: SubagentCloneWidget) -> None:
        idx = self._index_for_widget(widget)
        if idx is not None:
            self.trigger_group_cheer(source_index=idx)

    def _handle_widget_pet_rub(self, widget: SubagentCloneWidget) -> None:
        idx = self._index_for_widget(widget)
        if idx is not None:
            self.trigger_pet_rub(idx)

    def _handle_widget_wheel_trick(self, widget: SubagentCloneWidget) -> None:
        idx = self._index_for_widget(widget)
        if idx is not None:
            self.trigger_spin_trick(idx)

    def _handle_widget_middle_click(self, widget: SubagentCloneWidget) -> None:
        idx = self._index_for_widget(widget)
        if idx is not None:
            self.trigger_gift_share(idx)

    def _handle_widget_drag_start(self, widget: SubagentCloneWidget) -> None:
        idx = self._index_for_widget(widget)
        if idx is None:
            return
        info, _form_id, _badge = self._entries[idx]
        now = time.monotonic()
        rt = self._runtime.get(info.conversation_id)
        if rt is not None:
            rt.dragging = True
            rt.pose_action = PetAction.FALLING
            rt.pose_until = now + 30.0
        widget.say("哇！要带我去哪～", now=now, duration=1.8)

    def _handle_widget_drag_end(self, widget: SubagentCloneWidget, drop_center: QPoint) -> None:
        idx = self._index_for_widget(widget)
        if idx is None:
            return
        info, _form_id, _badge = self._entries[idx]
        now = time.monotonic()
        rt = self._runtime.get(info.conversation_id)
        if rt is not None:
            rt.dragging = False
            rt.glide_from = QPoint(widget.x(), widget.y())
            rt.glide_started_at = now
        host_dist = float("inf")
        if self._last_host_rect is not None and self._last_host_rect.isValid():
            host_center = self._last_host_rect.center()
            host_dist = math.hypot(drop_center.x() - host_center.x(), drop_center.y() - host_center.y())
        # Also check nearest sibling clone so dropping directly onto a sibling triggers clone_buddy
        # even when clones stand cozily close beside the host.
        nearest_other: int | None = None
        nearest_dist = float("inf")
        for other_idx in range(len(self._entries)):
            if other_idx == idx or other_idx >= len(self._widgets):
                continue
            other_w = self._widgets[other_idx]
            if not other_w.isVisible():
                continue
            oc = other_w.frameGeometry().center()
            d = math.hypot(drop_center.x() - oc.x(), drop_center.y() - oc.y())
            if d < nearest_dist:
                nearest_dist = d
                nearest_other = other_idx
        if nearest_other is not None and nearest_dist <= CLONE_HIGH_FIVE_RADIUS_PX and nearest_dist < host_dist:
            if rt is not None:
                rt.glide_hold_until = now + 0.48
                rt.glide_started_at = rt.glide_hold_until
            self.trigger_clone_buddy(idx, nearest_other, now=now)
            return
        if host_dist <= HIGH_FIVE_RADIUS_PX:
            if rt is not None:
                # Hold briefly beside the host so hands visibly clap before gliding back.
                rt.glide_hold_until = now + 0.48
                rt.glide_started_at = rt.glide_hold_until
            self.trigger_high_five(idx, now=now)
            return
        if rt is not None:
            rt.glide_hold_until = 0.0
            rt.pose_action = PetAction.WAVE
            rt.pose_until = now + 1.0
        back_line = "跑回来继续玩啦～" if is_playmate_id(info.conversation_id) else "回来继续干活啦～"
        widget.say(back_line, now=now, duration=1.8)

    # ----- Direct / programmatic host <-> subagent interaction triggers ---------

    def trigger_click(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Pet / encourage a mini clone directly and notify the host pet."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        playmate = is_playmate_id(info.conversation_id)
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        rt.pose_action = PetAction.HEAD_PAT
        rt.pose_until = ts + 2.0
        rt.nudge_until = ts + 0.55
        rt.nudge_strength = 8.0
        line = self._rng.choice(_PLAY_CLICK_LINES if playmate else _CLICK_LINES)
        widget.say(line, now=ts, duration=2.4)
        widget.emit_particles("hearts", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="clicked",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_report(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Clone nudges inward toward the host pet and reports its current task or play activity."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        playmate = is_playmate_id(info.conversation_id)
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        rt.pose_action = PetAction.GIFT_TOSS
        rt.pose_until = ts + 1.5
        rt.nudge_until = ts + 0.95
        rt.nudge_strength = 24.0
        short_title = _compact_text(info.title or ("晒太阳发呆" if playmate else "处理任务中"), 10)
        line = f"正在{short_title}～" if playmate else f"汇报：{short_title}"
        widget.say(line, now=ts, duration=2.6)
        widget.emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="report",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_high_five(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Mutual high-five huddle when a clone is dropped near the host pet."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        playmate = is_playmate_id(info.conversation_id)
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        rt.pose_action = PetAction.HIGH_FIVE
        rt.pose_until = ts + 2.0
        rt.nudge_until = ts + 0.85
        rt.nudge_strength = 22.0
        line = self._rng.choice(_PLAY_HIGH_FIVE_LINES if playmate else _HIGH_FIVE_LINES)
        widget.say(line, now=ts, duration=2.6)
        widget.emit_particles("hearts", reduced_motion=self._last_reduced_motion)
        widget.emit_particles("summon", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="high_five",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_group_cheer(self, *, source_index: int = 0, now: float | None = None) -> CloneEvent | None:
        """All active clones + host pet dance and celebrate together."""
        if not self._entries:
            return None
        ts = time.monotonic() if now is None else float(now)
        lead_idx = max(0, min(source_index, len(self._entries) - 1))
        info, form_id, badge = self._entries[lead_idx]
        playmate = is_playmate_id(info.conversation_id)
        lead_line = self._rng.choice(_PLAY_GROUP_CHEER_LINES if playmate else _GROUP_CHEER_LINES)
        for idx, (entry_info, _fid, _badge) in enumerate(self._entries):
            if idx >= len(self._widgets):
                break
            rt = self._runtime.setdefault(entry_info.conversation_id, _CloneRuntime(spawned_at=ts))
            rt.pose_action = PetAction.PLAY_DANCE
            rt.pose_until = ts + 2.55
            rt.nudge_until = ts + 0.65
            rt.nudge_strength = 12.0
            self._widgets[idx].emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
            if idx == lead_idx:
                self._widgets[idx].say(lead_line, now=ts, duration=2.5)
        rt_lead = self._runtime[info.conversation_id]
        event = CloneEvent(
            kind="group_cheer",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt_lead.last_side,
            text=lead_line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_relay(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Clone tosses a glowing star-orb / clue relay pulse to the host pet."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        playmate = is_playmate_id(info.conversation_id)
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        if rt.dragging:
            return None
        rt.pose_action = PetAction.GIFT_TOSS
        rt.pose_until = ts + 1.35
        rt.nudge_until = ts + 0.72
        rt.nudge_strength = 16.0
        line = self._format_line(self._rng.choice(_PLAY_RELAY_LINES if playmate else _RELAY_LINES))
        widget.say(line, now=ts, duration=2.4)
        widget.emit_particles("hearts" if playmate else "sparkles", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="relay",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_pet_rub(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Gentle mouse back-and-forth head rub melts a clone into a happy purr."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        playmate = is_playmate_id(info.conversation_id)
        rt = self._runtime.setdefault(info.conversation_id, self._make_runtime(ts, -1))
        rt.pose_action = PetAction.PET_PURR
        rt.pose_until = ts + 2.6
        rt.hop_started_at = ts
        rt.hop_duration = 0.36
        rt.hop_height = 6.0
        line = self._format_line(self._rng.choice(_PET_RUB_LINES))
        widget.say(line, now=ts, duration=2.6)
        widget.emit_particles("hearts", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="pet_rub",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_spin_trick(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Scroll wheel or trigger makes the clone hop and show off a lively trick."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        playmate = is_playmate_id(info.conversation_id)
        rt = self._runtime.setdefault(info.conversation_id, self._make_runtime(ts, -1))
        rt.pose_action = self._rng.choice((PetAction.PLAY_DANCE, PetAction.CELEBRATE, PetAction.QUOTA_GIFT))
        rt.pose_until = ts + 2.2
        rt.hop_started_at = ts
        rt.hop_duration = 0.44
        rt.hop_height = 13.0
        line = self._format_line(self._rng.choice(_TRICK_LINES))
        widget.say(line, now=ts, duration=2.5)
        widget.emit_particles("notes", reduced_motion=self._last_reduced_motion)
        widget.emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="trick",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_gift_share(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Clone holds up a little gift / dried fish for the host sister."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        playmate = is_playmate_id(info.conversation_id)
        rt = self._runtime.setdefault(info.conversation_id, self._make_runtime(ts, -1))
        if rt.dragging:
            return None
        rt.pose_action = PetAction.QUOTA_GIFT
        rt.pose_until = ts + 2.3
        rt.nudge_until = ts + 0.85
        rt.nudge_strength = 18.0
        rt.nudge_dir_x = 0
        line = self._format_line(self._rng.choice(_GIFT_SHARE_LINES))
        widget.say(line, now=ts, duration=2.6)
        widget.emit_particles("fish", reduced_motion=self._last_reduced_motion)
        widget.emit_particles("hearts", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="gift_share",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_clone_buddy(
        self,
        index_a: int = 0,
        index_b: int = 1,
        *,
        now: float | None = None,
    ) -> CloneEvent | None:
        """Two clones clap hands and celebrate together (drag-to-sibling or programmatic)."""
        if len(self._entries) < 2:
            return None
        if not (0 <= index_a < len(self._entries)) or not (0 <= index_b < len(self._entries)) or index_a == index_b:
            return None
        if index_a >= len(self._widgets) or index_b >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info_a, form_a, badge_a = self._entries[index_a]
        info_b, _form_b, _badge_b = self._entries[index_b]
        w_a, w_b = self._widgets[index_a], self._widgets[index_b]
        rt_a = self._runtime.setdefault(info_a.conversation_id, self._make_runtime(ts, -1))
        rt_b = self._runtime.setdefault(info_b.conversation_id, self._make_runtime(ts, 1))
        playmate = is_playmate_id(info_a.conversation_id) or is_playmate_id(info_b.conversation_id)
        for rt in (rt_a, rt_b):
            rt.pose_action = PetAction.HIGH_FIVE
            rt.pose_until = ts + 2.1
            rt.hop_started_at = ts
            rt.hop_duration = 0.40
            rt.hop_height = 10.0
        line_a = self._format_line(self._rng.choice(_CLONE_BUDDY_LINES))
        others = [c for c in _CLONE_BUDDY_LINES if self._format_line(c) != line_a]
        line_b = self._format_line(self._rng.choice(others or _CLONE_BUDDY_LINES))
        w_a.say(line_a, now=ts, duration=2.5)
        w_b.say(line_b, now=ts, duration=2.5)
        for w in (w_a, w_b):
            w.emit_particles("hearts", reduced_motion=self._last_reduced_motion)
            w.emit_particles("confetti", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="clone_buddy",
            conversation_id=info_a.conversation_id,
            form_id=form_a,
            badge=badge_a,
            title=info_a.title,
            side=rt_a.last_side,
            text=line_a,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def trigger_clone_chat(
        self,
        index_a: int = 0,
        index_b: int = 1,
        *,
        now: float | None = None,
    ) -> CloneEvent | None:
        """Two clones exchange playful whispers / encouragement with each other."""
        if len(self._entries) < 2:
            return None
        if not (0 <= index_a < len(self._entries)) or not (0 <= index_b < len(self._entries)) or index_a == index_b:
            return None
        if index_a >= len(self._widgets) or index_b >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info_a, form_a, badge_a = self._entries[index_a]
        info_b, _form_b, _badge_b = self._entries[index_b]
        rt_a = self._runtime.setdefault(info_a.conversation_id, self._make_runtime(ts, -1))
        rt_b = self._runtime.setdefault(info_b.conversation_id, self._make_runtime(ts, 1))
        if rt_a.dragging or rt_b.dragging:
            return None
        playmate = is_playmate_id(info_a.conversation_id) or is_playmate_id(info_b.conversation_id)
        raw_a, raw_b = self._rng.choice(_CLONE_CHAT_PAIRS if playmate else _WORK_CHAT_PAIRS)
        line_a = self._format_line(raw_a)
        line_b = self._format_line(raw_b)
        rt_a.pose_action = PetAction.WAVE
        rt_a.pose_until = ts + 2.2
        rt_b.pose_action = PetAction.HAPPY if playmate else PetAction.WAVE
        rt_b.pose_until = ts + 2.2
        rt_b.hop_started_at = ts + 0.12
        rt_b.hop_duration = 0.38
        rt_b.hop_height = 8.0
        w_a, w_b = self._widgets[index_a], self._widgets[index_b]
        w_a.say(line_a, now=ts, duration=2.5)
        w_b.say(line_b, now=ts, duration=2.6)
        w_a.emit_particles("notes" if playmate else "sparkles", reduced_motion=self._last_reduced_motion)
        w_b.emit_particles("hearts" if playmate else "sparkles", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="clone_chat",
            conversation_id=info_a.conversation_id,
            form_id=form_a,
            badge=badge_a,
            title=info_a.title,
            side=rt_a.last_side,
            text=line_a,
            is_playmate=playmate,
        )
        self._emit_event(event)
        return event

    def notify_host_action(
        self,
        action: PetAction,
        *,
        now: float | None = None,
        reduced_motion: bool = False,
    ) -> bool:
        """Let active mini clones react sympathetically to the host pet's state/mood."""
        if not self._entries or not self._enabled or not self._host_visible:
            return False
        if (self._last_dock_edge or "").strip().lower() in ("left", "right"):
            return False
        spec = _HOST_MOOD_RESPONSES.get(action)
        if spec is None:
            return False
        ts = time.monotonic() if now is None else float(now)
        last = self._last_mood_at.get(action, -1e9)
        if ts - last < 5.5:
            return False
        self._last_mood_at[action] = ts
        clone_action, duration, particle, lines = spec

        eligible = [
            idx
            for idx, (info, _f, _b) in enumerate(self._entries)
            if idx < len(self._widgets) and not self._runtime.get(info.conversation_id, _CloneRuntime(ts)).dragging
        ]
        if not eligible:
            return False
        speaker_idx = self._rng.choice(eligible)
        for idx in eligible:
            info = self._entries[idx][0]
            rt = self._runtime.setdefault(info.conversation_id, self._make_runtime(ts, -1))
            if clone_action != PetAction.WORKING:
                rt.pose_action = clone_action
                rt.pose_until = ts + duration
            if idx == speaker_idx and lines:
                self._widgets[idx].say(self._format_line(self._rng.choice(lines)), now=ts, duration=min(2.6, duration))
                if particle:
                    self._widgets[idx].emit_particles(particle, reduced_motion=reduced_motion)
            elif action in {PetAction.EATING, PetAction.CELEBRATE} and particle:
                self._widgets[idx].emit_particles(particle, reduced_motion=reduced_motion)
        return True

    def sync(
        self,
        subagents: list[SubagentInfo],
        *,
        default_form: str,
        enabled: bool,
        host_visible: bool,
        now: float | None = None,
        silent_depart: bool = False,
    ) -> None:
        self._host_form = normalize_form(default_form)
        ts = time.monotonic() if now is None else float(now)
        prev_entries = list(self._entries)
        prev_ids = {info.conversation_id for info, _f, _b in prev_entries}
        prev_positions: dict[str, tuple[QPoint, int, str, str, str]] = {}
        for idx, (info, form_id, badge) in enumerate(prev_entries):
            if idx < len(self._widgets):
                rt = self._runtime.get(info.conversation_id)
                side = rt.last_side if rt is not None else (-1 if idx % 2 == 0 else 1)
                prev_positions[info.conversation_id] = (
                    QPoint(self._widgets[idx].x(), self._widgets[idx].y()),
                    side,
                    form_id,
                    badge,
                    info.title,
                )

        self._enabled = bool(enabled)
        self._host_visible = bool(host_visible)
        if not self._enabled or not self._host_visible:
            self._entries = []
            self._runtime.clear()
            self._fade = 0.0
            self._clear_departing()
            for widget in self._widgets:
                widget.hide()
            return

        shown = list(subagents[:MAX_VISIBLE_CLONES])
        overflow = max(0, len(subagents) - MAX_VISIBLE_CLONES)
        new_ids = {info.conversation_id for info in shown}

        # Spawn celebratory handoff clones for subagents that just finished!
        docked = (self._last_dock_edge or "").strip().lower() in ("left", "right")
        finished_ids = [cid for cid in prev_positions if cid not in new_ids]
        if finished_ids and not silent_depart and not docked and self._last_host_rect is not None:
            for cid in finished_ids[:4]:
                start_pos, side, form_id, badge, title = prev_positions[cid]
                playmate = is_playmate_id(cid)
                dep_widget = SubagentCloneWidget(topmost=self._topmost, rng=self._rng)
                frames = self._mini_frames(form_id, mirrored=(side > 0), action=PetAction.DEPART_POOF)
                pix = frames[0] if frames else self._mini_pixmap(form_id, mirrored=(side > 0))
                max_fw = max((p.width() for p in frames), default=64)
                max_fh = max((p.height() for p in frames), default=84)
                line = self._format_line(self._rng.choice(_PLAY_HANDOFF_LINES if playmate else _HANDOFF_LINES))
                dep_widget.configure(
                    pixmap=pix,
                    badge=badge,
                    accent=_ACCENTS.get(form_id, "#8b5cf6"),
                    tooltip=f"{'闲时玩伴道别' if playmate else '子代理交卷'} · {title or badge}",
                    opacity=max(0.85, self._fade),
                    min_frame_size=(max_fw, max_fh),
                    frame_index=0,
                    mirrored=(side > 0),
                )
                dep_widget.move(start_pos)
                dep_widget.say(line, now=ts, duration=HANDOFF_DURATION_SECONDS)
                dep_widget.emit_particles("hearts" if playmate else "sparkles", reduced_motion=self._last_reduced_motion)
                dep_widget.show()
                duration = 0.25 if self._last_reduced_motion else HANDOFF_DURATION_SECONDS
                self._departing.append(
                    _DepartingClone(
                        conversation_id=cid,
                        form_id=form_id,
                        badge=badge,
                        title=title,
                        side=side,
                        start_pos=start_pos,
                        started_at=ts,
                        duration=duration,
                        widget=dep_widget,
                    )
                )
                self._emit_event(
                    CloneEvent(
                        kind="handoff",
                        conversation_id=cid,
                        form_id=form_id,
                        badge=badge,
                        title=title,
                        side=side,
                        text=line,
                        is_playmate=playmate,
                    )
                )

        if not shown:
            self._entries = []
            self._runtime.clear()
            self._fade = 0.0
            for widget in self._widgets:
                widget.hide()
            return

        entries: list[tuple[SubagentInfo, str, str]] = []
        for idx, info in enumerate(shown):
            label_lower = (info.model_label or "").lower()
            if info.form_id:
                resolved_form = normalize_form(info.form_id)
            else:
                matched = form_for_model_label(info.model_label)
                if matched:
                    resolved_form = matched
                elif any(w in label_lower for w in ("flash", "lite", "mini")):
                    resolved_form = "argon"
                elif any(w in label_lower for w in ("gpt", "oss")):
                    resolved_form = "carbon"
                else:
                    resolved_form = normalize_form(default_form)
            form_meta = form_by_id(resolved_form)
            if overflow > 0 and idx == len(shown) - 1:
                badge = f"+{overflow + 1}"
            elif "flash" in label_lower and "lite" in label_lower:
                badge = "Flash Lite"
            elif "flash" in label_lower and resolved_form == "argon":
                badge = "Flash"
            else:
                badge = form_meta.name
            entries.append((info, resolved_form, badge))
        self._entries = entries

        # Prune old runtime state & initialize newly arrived clones
        for stale in list(self._runtime):
            if stale not in new_ids:
                self._runtime.pop(stale, None)

        while len(self._widgets) < len(entries):
            w = SubagentCloneWidget(topmost=self._topmost, rng=self._rng)
            self._attach_widget_handlers(w)
            self._widgets.append(w)

        any_playmate = any(is_playmate_id(info.conversation_id) for info, _f, _b in entries)
        if not prev_ids:
            if any_playmate:
                self._next_relay_at = ts + self._rng.uniform(
                    PLAY_RELAY_INTERVAL_MIN_SECONDS,
                    PLAY_RELAY_INTERVAL_MAX_SECONDS,
                )
            else:
                self._next_relay_at = ts + self._rng.uniform(
                    RELAY_INTERVAL_MIN_SECONDS,
                    RELAY_INTERVAL_MAX_SECONDS,
                )

        newly_announced = False
        for idx, widget in enumerate(self._widgets):
            if idx >= len(entries):
                widget.hide()
                continue
            info, form_id, badge = entries[idx]
            playmate = is_playmate_id(info.conversation_id)
            base_action = PetAction.HAPPY if playmate else PetAction.WORKING
            frames = self._mini_frames(form_id, mirrored=False, action=base_action)
            pix = frames[0] if frames else QPixmap()
            max_fw = max((p.width() for p in frames), default=64)
            max_fh = max((p.height() for p in frames), default=84)
            title = info.title or ("闲时小玩伴" if playmate else f"子代理 #{idx + 1}")
            model_line = f"\n模型：{info.model_label}" if (info.model_label and not playmate) else ""
            tip_head = f"闲时随机小玩伴 · {title}" if playmate else f"子代理分身 · {title}{model_line}"
            tip_hint = self._format_line(
                "单击摸摸 · 揉头蹭蹭 · 滚轮花招 · 中键送礼\n双击玩闹 · 拖给 {host} 击掌 · 拖给同伴贴贴 · 右键派对"
                if playmate
                else "单击打气 · 揉头蹭蹭 · 滚轮花招 · 中键送礼\n双击汇报 · 拖给 {host} 击掌 · 拖给同伴贴贴 · 右键派对"
            )
            widget.configure(
                pixmap=pix,
                badge=badge,
                accent=_ACCENTS.get(form_id, "#8b5cf6"),
                tooltip=f"{tip_head}\n{tip_hint}",
                opacity=self._fade,
                min_frame_size=(max_fw, max_fh),
                frame_index=0,
                mirrored=False,
                hover_label=title,
            )
            if info.conversation_id not in self._runtime:
                side = -1 if idx % 2 == 0 else 1
                self._runtime[info.conversation_id] = self._make_runtime(ts, side)
                if not newly_announced and not docked:
                    newly_announced = True
                    line = self._format_line(self._rng.choice(_PLAY_SUMMON_LINES if playmate else _SUMMON_LINES))
                    widget.say(line, now=ts, duration=2.4)
                    widget.emit_particles("summon", reduced_motion=self._last_reduced_motion)
                    self._emit_event(
                        CloneEvent(
                            kind="summoned",
                            conversation_id=info.conversation_id,
                            form_id=form_id,
                            badge=badge,
                            title=title,
                            side=side,
                            text=line,
                            is_playmate=playmate,
                        )
                    )

    @staticmethod
    def _keepout_zones(area: QRect, perched_window_rect: QRect | None) -> list[QRect]:
        """Regions reserved for window controls (_ □ ×) that clones must never cover."""
        zones: list[QRect] = []
        if perched_window_rect is not None and perched_window_rect.isValid():
            zones.append(
                QRect(
                    QPoint(perched_window_rect.right() - 150, perched_window_rect.top() - 28),
                    QPoint(perched_window_rect.right() + 12, perched_window_rect.top() + 68),
                )
            )
        # Protect maximized window controls at the screen's very top-right corner
        if area.width() >= 260 and area.height() >= 160:
            zones.append(
                QRect(
                    QPoint(area.right() - 150, area.top()),
                    QPoint(area.right(), area.top() + 56),
                )
            )
        return zones

    @staticmethod
    def _host_visual_bounds(host_rect: QRect) -> tuple[int, int, QRect]:
        """Estimate the opaque character body inside ``host_rect`` (ignoring bubble width padding)."""
        host_cx = host_rect.center().x()
        body_w = min(host_rect.width(), max(108, round(host_rect.height() * 0.54)))
        left = host_cx - body_w // 2
        right = left + body_w
        return left, right, QRect(left, host_rect.top(), body_w, host_rect.height())

    @staticmethod
    def _clone_visual_rect(wx: int, wy: int, widget_w: int, widget_h: int, vis_w: int, vis_h: int) -> QRect:
        """Collision rect covering the visible mini sprite + margin (excluding wide transparent bubble padding)."""
        cx = wx + widget_w // 2
        cw = vis_w + 12
        ch = vis_h + 18
        top = wy + widget_h - 18 - ch
        return QRect(cx - cw // 2, top, cw, ch)

    @classmethod
    def _place_clone_slot(
        cls,
        *,
        idx: int,
        widget_w: int,
        widget_h: int,
        vis_w: int,
        vis_h: int,
        host_rect: QRect,
        host_vis_left: int,
        host_vis_right: int,
        host_vis_rect: QRect,
        area: QRect,
        keepouts: list[QRect],
        placed_visual_rects: list[QRect],
        sway_x: float,
    ) -> tuple[int, int, int, QRect]:
        """Choose the closest cozy slot around the host with zero keep-out and zero sprite overlap.

        Clones line up side-by-side right next to the host's visual body first (alternating left/right
        when open, or spilling cleanly to the open side near a screen edge) and only step up to a full
        non-overlapping second row when horizontal space is exhausted.
        """
        host_gap = 10
        col_step = vis_w + 18
        row_step = vis_h + 24
        base_y = host_rect.bottom() - widget_h - 6
        arc_lifts = (0, 8, 14, 8, 14, 18)

        def clamp(px: int, py: int) -> tuple[int, int]:
            return (
                max(area.left(), min(px, area.right() - widget_w + 1)),
                max(area.top(), min(py, area.bottom() - widget_h + 1)),
            )

        def hits_keepout(px: int, py: int) -> bool:
            rect = QRect(px, py, widget_w, widget_h)
            return any(rect.intersects(kz) for kz in keepouts)

        def visual_overlap(vrect: QRect) -> int:
            total = 0
            inter_h = vrect.intersected(host_vis_rect)
            if inter_h.isValid():
                total += inter_h.width() * inter_h.height() * 4
            for other in placed_visual_rects:
                inter = vrect.intersected(other)
                if inter.isValid():
                    total += inter.width() * inter.height()
            return total

        def slot_pos(side: int, col: int, row: int) -> tuple[int, int]:
            if side < 0:
                center_x = host_vis_left - host_gap - vis_w // 2 - col * col_step
            else:
                center_x = host_vis_right + host_gap + vis_w // 2 + col * col_step
            wx = round(center_x - widget_w / 2.0 + sway_x)
            lift = arc_lifts[col % len(arc_lifts)] if row == 0 else 0
            wy = round(base_y - row * row_step - lift)
            return clamp(wx, wy)

        preferred_side = -1 if idx % 2 == 0 else 1
        sides_order = (preferred_side, -preferred_side)

        # Ordered candidate list: closest horizontal slots first, then clean non-overlapping upper rows,
        # then below-keepout rows if top edge / window controls block above.
        candidates: list[tuple[int, int, int]] = []
        for row in (0, 1, 2):
            for col in range(6):
                for s in sides_order:
                    px, py = slot_pos(s, col, row)
                    final_side = -1 if (px + widget_w // 2) < host_rect.center().x() else 1
                    candidates.append((px, py, final_side))

        if keepouts:
            max_kz_bottom = max(kz.bottom() for kz in keepouts)
            for r in range(3):
                by = max_kz_bottom + 8 + r * row_step
                for col in range(6):
                    for s in sides_order:
                        px, _ = slot_pos(s, col, 0)
                        bx, by_c = clamp(px, by)
                        final_side = -1 if (bx + widget_w // 2) < host_rect.center().x() else 1
                        candidates.append((bx, by_c, final_side))

        # Also add fallback positions cleanly below the host if upper screen is tight
        below_host_y = host_rect.bottom() + 8
        for col in range(6):
            for s in sides_order:
                px, _ = slot_pos(s, col, 0)
                bx, by_c = clamp(px, below_host_y)
                final_side = -1 if (bx + widget_w // 2) < host_rect.center().x() else 1
                candidates.append((bx, by_c, final_side))

        best_fallback: tuple[int, int, int, int, QRect] | None = None
        seen: set[tuple[int, int]] = set()
        for px, py, side in candidates:
            if (px, py) in seen:
                continue
            seen.add((px, py))
            if hits_keepout(px, py):
                continue
            vrect = cls._clone_visual_rect(px, py, widget_w, widget_h, vis_w, vis_h)
            ov = visual_overlap(vrect)
            if ov == 0:
                return px, py, side, vrect
            if best_fallback is None or ov < best_fallback[0]:
                best_fallback = (ov, px, py, side, vrect)

        if best_fallback is not None:
            _ov, px, py, side, vrect = best_fallback
            return px, py, side, vrect

        fx, fy = clamp(area.left(), area.bottom() - widget_h + 1)
        return fx, fy, -1, cls._clone_visual_rect(fx, fy, widget_w, widget_h, vis_w, vis_h)

    def _tick_departing(self, host_rect: QRect, *, now: float, dt: float, reduced_motion: bool) -> None:
        if not self._departing:
            return
        remaining: list[_DepartingClone] = []
        for dep in self._departing:
            elapsed = max(0.0, now - dep.started_at)
            if elapsed >= dep.duration:
                dep.widget.hide()
                dep.widget.close()
                dep.widget.deleteLater()
                self._emit_event(
                    CloneEvent(
                        kind="depart_complete",
                        conversation_id=dep.conversation_id,
                        form_id=dep.form_id,
                        badge=dep.badge,
                        title=dep.title,
                        side=dep.side,
                        is_playmate=is_playmate_id(dep.conversation_id),
                    )
                )
                continue
            t = min(1.0, elapsed / max(0.05, dep.duration))
            target_x = (
                host_rect.left() - dep.widget.width() // 2 + 12
                if dep.side < 0
                else host_rect.right() - dep.widget.width() // 2 - 12
            )
            target_y = host_rect.center().y() - dep.widget.height() // 2
            # 2-stage cinematic exit:
            # Stage 1 (0..0.36): salute/goodbye wave + upbeat anticipation hop
            # Stage 2 (0.36..1.0): parabolic leap back into host + starlight shrink poof
            if reduced_motion:
                scale = 1.0
                opacity = 1.0 if t < 0.55 else max(0.0, (1.0 - t) / 0.45)
                bob = 0.0
            elif t < 0.36:
                t1 = t / 0.36
                hop = math.sin(t1 * math.pi)
                dep.widget.move(dep.start_pos.x(), round(dep.start_pos.y() - hop * 14.0))
                scale = 1.0 + 0.08 * hop
                opacity = 1.0
                bob = -hop * 3.0
            else:
                t2 = (t - 0.36) / 0.64
                if not dep.poof_emitted:
                    dep.poof_emitted = True
                    dep.widget.emit_particles("summon", reduced_motion=False)
                ease = t2 * t2 * (3.0 - 2.0 * t2)
                nx = round(dep.start_pos.x() + (target_x - dep.start_pos.x()) * ease)
                ny = round(dep.start_pos.y() + (target_y - dep.start_pos.y()) * ease - math.sin(t2 * math.pi) * 44.0)
                dep.widget.move(nx, ny)
                scale = max(0.30, 1.06 - 0.76 * (t2 ** 1.35))
                opacity = 1.0 if t2 < 0.45 else max(0.0, (1.0 - t2) / 0.55)
                bob = -math.sin(t2 * math.pi) * 4.0

            frames = self._mini_frames(dep.form_id, mirrored=(dep.side > 0), action=PetAction.DEPART_POOF)
            if frames:
                frame_idx = 0 if (reduced_motion or len(frames) <= 1) else min(len(frames) - 1, int(t * len(frames)))
                dep.widget.set_frame(frames[frame_idx], frame_index=frame_idx, mirrored=(dep.side > 0), action=PetAction.DEPART_POOF)
            dep.widget.set_bob(bob, opacity, scale=scale)
            dep.widget.tick_fx(dt, now=now, reduced_motion=reduced_motion)
            if not dep.widget.isVisible():
                dep.widget.show()
            remaining.append(dep)
        self._departing = remaining

    def position_around(
        self,
        host_rect: QRect,
        *,
        now: float,
        reduced_motion: bool = False,
        screen=None,
        dock_edge: str | None = None,
        perched_window_rect: QRect | None = None,
    ) -> None:
        self._last_host_rect = QRect(host_rect)
        self._last_dock_edge = dock_edge
        self._last_reduced_motion = bool(reduced_motion)
        dt = 0.033 if self._last_tick_now is None else max(0.0, min(0.10, now - self._last_tick_now))
        self._last_tick_now = now

        if (dock_edge or "").strip().lower() in ("left", "right"):
            self._fade = 0.0
            self._clear_departing()
            for widget in self._widgets:
                if widget.isVisible():
                    widget.hide()
            return

        self._tick_departing(host_rect, now=now, dt=dt, reduced_motion=reduced_motion)
        if not self._entries:
            return

        self._fade = 1.0 if reduced_motion else min(1.0, max(0.22, self._fade + 0.14))
        target_screen = QApplication.screenAt(host_rect.center()) or screen or QApplication.primaryScreen()
        area = target_screen.availableGeometry() if target_screen else QRect(0, 0, 1920, 1080)
        keepouts = self._keepout_zones(area, perched_window_rect)

        count = len(self._entries)
        host_vis_left, host_vis_right, host_vis_rect = self._host_visual_bounds(host_rect)
        placed_visual_rects: list[QRect] = []
        for idx in range(count):
            widget = self._widgets[idx]
            info, form_id, _badge = self._entries[idx]
            rt = self._runtime.setdefault(info.conversation_id, self._make_runtime(now, -1 if idx % 2 == 0 else 1))
            vis_w, vis_h = widget.visual_sprite_size
            phase = rt.motion_phase
            spd = rt.motion_speed
            sway_x = 0.0 if reduced_motion else (
                math.sin(now * 1.45 * spd + phase) * 2.2 + math.sin(now * 0.72 * spd + phase * 1.6) * 1.1
            )
            bob_y = 0.0 if reduced_motion else (
                math.sin(now * 2.4 * spd + phase) * 3.6 + math.sin(now * 1.15 * spd + phase * 1.7) * 1.5
            )

            clamped_x, clamped_y, final_side, placed_vrect = self._place_clone_slot(
                idx=idx,
                widget_w=widget.width(),
                widget_h=widget.height(),
                vis_w=vis_w,
                vis_h=vis_h,
                host_rect=host_rect,
                host_vis_left=host_vis_left,
                host_vis_right=host_vis_right,
                host_vis_rect=host_vis_rect,
                area=area,
                keepouts=keepouts,
                placed_visual_rects=placed_visual_rects,
                sway_x=sway_x,
            )
            rt.last_side = final_side
            placed_visual_rects.append(placed_vrect)

            # Resolve active pose:
            # - Fresh entrance plays SUMMON_POP arc
            # - Active interactions override idle until pose_until
            # - Playmates run an independent organic idle state machine (varied poses + micro-hops + glances)
            # - Working subagents settle into WORKING, then alternate semantic tool poses & natural micro-breaks
            playmate = is_playmate_id(info.conversation_id)
            spawn_age = now - rt.spawned_at
            in_summon = (
                not reduced_motion
                and not rt.dragging
                and 0.0 <= spawn_age < SUMMON_SLIDE_SECONDS
                and rt.pose_action is None
            )
            if in_summon:
                active_action = PetAction.SUMMON_POP
            elif reduced_motion:
                active_action = PetAction.HAPPY if playmate else PetAction.WORKING
            elif playmate:
                if rt.idle_action is None or now >= rt.idle_until:
                    pool = [p for p in _PLAY_IDLE_POSES if p != rt.idle_action] or list(_PLAY_IDLE_POSES)
                    rt.idle_action = self._rng.choice(pool)
                    rt.idle_until = now + self._rng.uniform(3.4, 6.2)
                    if rt.idle_action in {PetAction.IDLE, PetAction.THINKING, PetAction.WAVE} and self._rng.random() < 0.28:
                        rt.idle_glance_until = now + self._rng.uniform(1.1, 2.0)
                active_action = rt.idle_action
            else:
                if spawn_age < 3.5:
                    active_action = PetAction.WORKING
                else:
                    if rt.idle_action is None or now >= rt.idle_until:
                        primary_work = _work_pose_for_title(info.title)
                        if rt.idle_action in _WORK_MICRO_BREAK_POSES or rt.idle_action is None:
                            rt.idle_action = primary_work
                            rt.idle_until = now + self._rng.uniform(6.0, 10.5)
                        else:
                            rt.idle_action = self._rng.choice(_WORK_MICRO_BREAK_POSES)
                            rt.idle_until = now + self._rng.uniform(2.2, 3.3)
                            if rt.idle_action == PetAction.THINKING and self._rng.random() < 0.35:
                                rt.idle_glance_until = now + self._rng.uniform(1.0, 1.8)
                    active_action = rt.idle_action
            if rt.pose_action is not None:
                if now < rt.pose_until or rt.dragging:
                    active_action = rt.pose_action
                else:
                    rt.pose_action = None
                    rt.pose_until = 0.0

            # Periodic organic micro-hop + subtle ambient particles during idle
            if not reduced_motion and not rt.dragging and not in_summon:
                if rt.next_hop_at > 0 and now >= rt.next_hop_at:
                    rt.next_hop_at = now + self._rng.uniform(4.5, 9.0 if playmate else 14.0)
                    if playmate or active_action in {PetAction.HAPPY, PetAction.WAVE, PetAction.STRETCH}:
                        rt.hop_started_at = now
                        rt.hop_duration = self._rng.uniform(0.36, 0.46)
                        rt.hop_height = self._rng.uniform(6.0, 10.5) if playmate else self._rng.uniform(4.5, 7.0)
                if playmate and rt.next_ambient_fx_at > 0 and now >= rt.next_ambient_fx_at:
                    rt.next_ambient_fx_at = now + self._rng.uniform(6.5, 12.5)
                    if active_action == PetAction.PLAY_DANCE:
                        widget.emit_particles("notes", reduced_motion=False)
                    elif active_action in {PetAction.HAPPY, PetAction.QUOTA_GIFT}:
                        widget.emit_particles("sparkles", reduced_motion=False)
                    elif active_action == PetAction.WAVE:
                        widget.emit_particles("hearts", reduced_motion=False)

            # Mirror clones on the right side (side > 0) so dual clones face symmetrically inward;
            # briefly glance outward during natural idle look-arounds.
            glancing_out = not reduced_motion and not rt.dragging and rt.pose_action is None and now < rt.idle_glance_until
            mirrored = (final_side <= 0) if glancing_out else (final_side > 0)
            frames = self._mini_frames(form_id, mirrored=mirrored, action=active_action)
            if frames:
                if in_summon:
                    st_f = max(0.0, min(0.999, spawn_age / SUMMON_SLIDE_SECONDS))
                    frame_idx = min(len(frames) - 1, int(st_f * len(frames)))
                else:
                    cadence = _ACTION_FRAME_INTERVALS.get(active_action, FRAME_INTERVAL_SECONDS)
                    frame_idx = (
                        0
                        if (reduced_motion or len(frames) <= 1)
                        else (int((now + idx * CLONE_PHASE_STEP_SECONDS) / cadence) % len(frames))
                    )
                widget.set_frame(frames[frame_idx], frame_index=frame_idx, mirrored=mirrored, action=active_action)

            render_scale = 1.0
            scale_x = 1.0
            scale_y = 1.0
            render_opacity = self._fade
            if not rt.dragging:
                target_x, target_y = clamped_x, clamped_y
                # Smooth inward nudge during report / high-five / relay (never crosses host visual edge!)
                if not reduced_motion and now < rt.nudge_until:
                    rem = max(0.0, rt.nudge_until - now)
                    nudge_px = math.sin(min(1.0, rem / 0.75) * math.pi) * rt.nudge_strength
                    if final_side < 0:
                        max_left_x = host_vis_left - (widget.width() + vis_w) // 2 - 2
                        target_x = min(max_left_x, round(target_x + nudge_px))
                    else:
                        min_right_x = host_vis_right - (widget.width() - vis_w) // 2 + 2
                        target_x = max(min_right_x, round(target_x - nudge_px))
                # Cinematic parabolic pop-out entrance bursting from host center with elastic scale
                elif in_summon:
                    st = max(0.0, min(1.0, spawn_age / SUMMON_SLIDE_SECONDS))
                    ease = 1.0 - (1.0 - st) ** 3
                    arc = math.sin(st * math.pi)
                    origin_x = host_rect.center().x() - widget.width() // 2
                    target_x = round(origin_x + (clamped_x - origin_x) * ease)
                    target_y = round(clamped_y - arc * 42.0)
                    render_scale = 0.36 + 0.64 * ease + 0.12 * arc
                    scale_x = render_scale
                    scale_y = render_scale
                    render_opacity = min(1.0, max(self._fade, 0.25 + st * 1.25))
                # Smooth glide back to orbit after user drops a dragged clone (with optional high-five hold)
                if rt.glide_from is not None:
                    if not reduced_motion and now < rt.glide_hold_until:
                        target_x = rt.glide_from.x()
                        target_y = rt.glide_from.y()
                    else:
                        gt = max(0.0, min(1.0, (now - rt.glide_started_at) / GLIDE_RETURN_SECONDS))
                        if reduced_motion or gt >= 1.0:
                            rt.glide_from = None
                            rt.glide_hold_until = 0.0
                        else:
                            ge = 1.0 - (1.0 - gt) ** 3
                            target_x = round(rt.glide_from.x() + (target_x - rt.glide_from.x()) * ge)
                            target_y = round(rt.glide_from.y() + (target_y - rt.glide_from.y()) * ge)
                target_x = max(area.left(), min(target_x, area.right() - widget.width() + 1))
                target_y = max(area.top(), min(target_y, area.bottom() - widget.height() + 1))
                if (target_x, target_y) != (widget.x(), widget.y()):
                    widget.move(target_x, target_y)

            # Organic breathing squash-stretch + playful micro-hop arc
            hop_y = 0.0
            if not reduced_motion and not rt.dragging and not in_summon:
                breath = math.sin(now * 2.1 * spd + phase) * 0.022
                scale_x = render_scale * (1.0 - breath * 0.65)
                scale_y = render_scale * (1.0 + breath)
                if rt.hop_started_at > 0 and rt.hop_started_at <= now < rt.hop_started_at + rt.hop_duration:
                    hp = (now - rt.hop_started_at) / max(0.05, rt.hop_duration)
                    hop_arc = math.sin(hp * math.pi)
                    hop_y = -hop_arc * rt.hop_height
                    if hp < 0.18 or hp > 0.82:
                        # Subtle landing/takeoff squash
                        scale_x *= 1.06
                        scale_y *= 0.94
                    else:
                        scale_x *= 0.96
                        scale_y *= 1.05
            tilt_amp = 4.2 if active_action in {PetAction.PLAY_DANCE, PetAction.HAPPY, PetAction.CELEBRATE} else 2.6
            tilt_deg = 0.0 if (reduced_motion or rt.dragging) else (
                math.sin(now * 1.85 * spd + phase) * tilt_amp
                + math.sin(now * 0.92 * spd + phase * 1.4) * 0.9
            )
            widget.set_bob(
                bob_y + hop_y,
                render_opacity,
                scale=render_scale,
                scale_x=scale_x,
                scale_y=scale_y,
                tilt_deg=tilt_deg,
            )
            widget.tick_fx(dt, now=now, reduced_motion=reduced_motion)
            if not widget.isVisible():
                widget.show()

        for extra in self._widgets[count:]:
            if extra.isVisible():
                extra.hide()

        # Periodic collaborative banter: single clone relays to sister; 2+ clones mix chat, gift share, and relay!
        if self._next_relay_at > 0 and now >= self._next_relay_at:
            any_playmate = any(is_playmate_id(info.conversation_id) for info, _f, _b in self._entries)
            if any_playmate:
                self._next_relay_at = now + self._rng.uniform(
                    PLAY_RELAY_INTERVAL_MIN_SECONDS,
                    PLAY_RELAY_INTERVAL_MAX_SECONDS,
                )
            else:
                self._next_relay_at = now + self._rng.uniform(
                    RELAY_INTERVAL_MIN_SECONDS,
                    RELAY_INTERVAL_MAX_SECONDS,
                )
            free_indices = [
                i
                for i, (info, _f, _b) in enumerate(self._entries)
                if not self._runtime.get(info.conversation_id, _CloneRuntime(now)).dragging
            ]
            if len(free_indices) >= 2:
                roll = self._rng.random()
                if roll < 0.42:
                    idx_a, idx_b = self._rng.sample(free_indices, 2)
                    self.trigger_clone_chat(idx_a, idx_b, now=now)
                elif roll < (0.62 if any_playmate else 0.52):
                    self.trigger_gift_share(self._rng.choice(free_indices), now=now)
                else:
                    self.trigger_relay(self._rng.choice(free_indices), now=now)
            elif free_indices:
                self.trigger_relay(free_indices[0], now=now)

    def close_all(self) -> None:
        self._clear_departing()
        for widget in self._widgets:
            widget.hide()
            widget.close()
            widget.deleteLater()
        self._widgets.clear()
        self._entries.clear()
        self._runtime.clear()
        self._frame_cache.clear()
        self._registries.clear()
