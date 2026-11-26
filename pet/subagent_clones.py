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

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from agy.characters import form_by_id, form_for_model_label, normalize_form
from agy.telemetry import SubagentInfo
from animation.asset_registry import AssetRegistry
from animation.clip import PetAction
from pet.particles import ParticleSystem

MAX_VISIBLE_CLONES = 4
MAX_ANIMATION_FRAMES = 4
FRAME_INTERVAL_SECONDS = 0.18
CLONE_PHASE_STEP_SECONDS = 0.45
SUMMON_SLIDE_SECONDS = 0.38
HANDOFF_DURATION_SECONDS = 1.15
HIGH_FIVE_RADIUS_PX = 140.0
GLIDE_RETURN_SECONDS = 0.36
RELAY_INTERVAL_MIN_SECONDS = 14.0
RELAY_INTERVAL_MAX_SECONDS = 22.0
DRAG_THRESHOLD_PX = 6

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
    "谢谢夸奖～干劲满满！",
    "被摸头了！效率翻倍～",
    "嘿嘿，继续努力！",
    "收到打气，冲鸭！",
)

_RELAY_LINES: tuple[str, ...] = (
    "发现线索，传给主宠！",
    "进度同步给主宠～",
    "这块我先兜底啦！",
    "整理好一批结果！",
)

_HANDOFF_LINES: tuple[str, ...] = (
    "搞定！交卷啦～",
    "汇报完毕，收工！",
    "成果交给主宠啦～",
)

_HIGH_FIVE_LINES: tuple[str, ...] = (
    "击掌成功！合作无间～",
    "贴贴！配合满分！",
    "耶！最佳拍档～",
)

_GROUP_CHEER_LINES: tuple[str, ...] = (
    "全员出击，效率起飞！",
    "小队干劲拉满～",
    "一起冲鸭！",
)

_HOST_MOOD_RESPONSES: dict[PetAction, tuple[PetAction, float, str | None, tuple[str, ...]]] = {
    PetAction.HEAD_PAT: (
        PetAction.HAPPY,
        2.4,
        "hearts",
        ("也摸摸我嘛～", "主宠被夸啦～", "好羡慕，我也想要！"),
    ),
    PetAction.PET_PURR: (
        PetAction.HAPPY,
        2.8,
        "hearts",
        ("主宠好幸福呀～", "我也要蹭蹭！"),
    ),
    PetAction.EATING: (
        PetAction.WAVE,
        2.4,
        "sparkles",
        ("好香！给我留一口～", "干完活我也想吃！"),
    ),
    PetAction.CELEBRATE: (
        PetAction.CELEBRATE,
        2.2,
        "sparkles",
        ("耶！一起庆祝～", "太棒啦主宠！"),
    ),
    PetAction.HAPPY: (
        PetAction.HAPPY,
        1.8,
        None,
        ("主宠开心我也开心～",),
    ),
    PetAction.SULK: (
        PetAction.WAVE,
        2.8,
        None,
        ("别生气啦主宠…", "我加快进度哄你！"),
    ),
    PetAction.ANGRY: (
        PetAction.POKE_REACT,
        1.8,
        "sweat",
        ("哇！主宠生气了…", "我马上乖乖干活！"),
    ),
    PetAction.WAITING_USER: (
        PetAction.WAITING_USER,
        3.2,
        "alert",
        ("主宠在等你确认哦！", "快看看确认弹窗吧～"),
    ),
    PetAction.SLEEPING: (
        PetAction.WORKING,
        2.6,
        None,
        ("嘘，主宠睡了，我值班～",),
    ),
    PetAction.PERCH_SLEEP: (
        PetAction.WORKING,
        2.6,
        None,
        ("嘘，主宠打盹中～",),
    ),
    PetAction.DRAGGING: (
        PetAction.FALLING,
        1.5,
        None,
        ("等等我呀主宠！", "慢点飞——"),
    ),
    PetAction.FALLING: (
        PetAction.FALLING,
        1.4,
        None,
        ("主宠抓稳啦！", "我来接应～"),
    ),
}


@dataclass(frozen=True, slots=True)
class CloneEvent:
    """Structured host <-> subagent interaction event sent to PetWindow."""

    kind: str  # summoned / handoff / clicked / report / high_five / group_cheer / relay
    conversation_id: str
    form_id: str
    badge: str
    title: str
    side: int  # -1 left of host, +1 right of host
    text: str = ""


@dataclass(slots=True)
class _CloneRuntime:
    spawned_at: float
    pose_action: PetAction | None = None
    pose_until: float = 0.0
    nudge_until: float = 0.0
    nudge_strength: float = 16.0
    last_side: int = -1
    dragging: bool = False
    glide_from: QPoint | None = None
    glide_started_at: float = 0.0


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

        self._pixmap = QPixmap()
        self._badge = ""
        self._accent = QColor("#8b5cf6")
        self._opacity = 1.0
        self._bob_y = 0.0
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

        self._on_click: Callable[[SubagentCloneWidget], None] | None = None
        self._on_double_click: Callable[[SubagentCloneWidget], None] | None = None
        self._on_right_click: Callable[[SubagentCloneWidget], None] | None = None
        self._on_drag_start: Callable[[SubagentCloneWidget], None] | None = None
        self._on_drag_end: Callable[[SubagentCloneWidget, QPoint], None] | None = None

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

    def bind_handlers(
        self,
        *,
        on_click: Callable[[SubagentCloneWidget], None] | None = None,
        on_double_click: Callable[[SubagentCloneWidget], None] | None = None,
        on_right_click: Callable[[SubagentCloneWidget], None] | None = None,
        on_drag_start: Callable[[SubagentCloneWidget], None] | None = None,
        on_drag_end: Callable[[SubagentCloneWidget, QPoint], None] | None = None,
    ) -> None:
        self._on_click = on_click
        self._on_double_click = on_double_click
        self._on_right_click = on_right_click
        self._on_drag_start = on_drag_start
        self._on_drag_end = on_drag_end

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
        w = max(92, frame_w + 30)
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

    def set_bob(self, offset_y: float, opacity: float) -> None:
        new_bob = float(offset_y)
        new_op = max(0.0, min(1.0, float(opacity)))
        if abs(new_bob - self._bob_y) < 0.05 and abs(new_op - self._opacity) < 0.005:
            return
        self._bob_y = new_bob
        self._opacity = new_op
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
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_window_pos = self.pos()
            self._dragging = False
            self._suppress_next_release = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_global is not None and self._press_window_pos is not None:
            delta = event.globalPosition().toPoint() - self._press_global
            if not self._dragging and delta.manhattanLength() > DRAG_THRESHOLD_PX:
                self._dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                if self._on_drag_start is not None:
                    self._on_drag_start(self)
            if self._dragging:
                self.move(self._press_window_pos + delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

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
                if self._on_drag_end is not None:
                    self._on_drag_end(self, self.frameGeometry().center())
            elif not suppressed and self._on_click is not None:
                self._on_click(self)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
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

        # Soft halo shadow under the floating mini clone (brighter on hover/drag)
        cx = self.width() / 2.0
        shadow_y = self.height() - 24.0
        painter.setPen(Qt.PenStyle.NoPen)
        halo_alpha = 88 if (self._hovered or self._dragging) else 42
        halo_w = 56.0 if (self._hovered or self._dragging) else 48.0
        painter.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), halo_alpha))
        painter.drawEllipse(QRectF(cx - halo_w / 2.0, shadow_y - 4.5, halo_w, 10.0))

        if not self._pixmap.isNull():
            hover_lift = -3.0 if self._hovered and not self._dragging else 0.0
            px = (self.width() - self._pixmap.width()) / 2.0
            py = max(float(self.BUBBLE_TOP_PAD) - 2.0, shadow_y - self._pixmap.height() + self._bob_y + hover_lift)
            painter.drawPixmap(round(px), round(py), self._pixmap)

        if self._particles.active:
            self._particles.paint(painter)

        # Top mini speech bubble (active dialogue takes precedence over hover task label)
        shown_bubble = self._bubble_text or (self._hover_label if self._hovered else "")
        if shown_bubble:
            is_speech = bool(self._bubble_text)
            painter.setFont(self._bubble_font)
            fm = QFontMetrics(self._bubble_font)
            text = fm.elidedText(shown_bubble, Qt.TextElideMode.ElideRight, max(44, self.width() - 14))
            bw = min(self.width() - 4, max(42, fm.horizontalAdvance(text) + 12))
            bh = min(self.BUBBLE_TOP_PAD - 2, fm.height() + 6)
            bx = (self.width() - bw) / 2.0
            by = 2.0
            rect = QRectF(bx, by, bw, bh)
            bg = QColor(15, 23, 42, 224 if is_speech else 188)
            border = QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 220 if is_speech else 145)
            painter.setBrush(bg)
            painter.setPen(QPen(border, 1.1))
            painter.drawRoundedRect(rect, bh / 2.0, bh / 2.0)
            painter.setPen(QColor(248, 250, 252))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        if self._badge:
            painter.setFont(self._badge_font)
            fm = QFontMetrics(self._badge_font)
            bw = min(self.width() - 8, max(34, fm.horizontalAdvance(self._badge) + 14))
            bh = fm.height() + 5
            bx = (self.width() - bw) / 2.0
            by = self.height() - bh - 2.0
            pill = QRectF(bx, by, bw, bh)
            painter.setBrush(QColor(18, 26, 38, 205))
            painter.setPen(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 190))
            painter.drawRoundedRect(pill, bh / 2.0, bh / 2.0)
            painter.setPen(QColor(248, 250, 252))
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
        self._sprite_height = 96
        self._fade = 0.0
        self._last_host_rect: QRect | None = None
        self._last_dock_edge: str | None = None
        self._last_reduced_motion = False
        self._last_tick_now: float | None = None
        self._last_mood_at: dict[PetAction, float] = {}
        self._next_relay_at = 0.0

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
        near_host = False
        if self._last_host_rect is not None and self._last_host_rect.isValid():
            host_center = self._last_host_rect.center()
            dist = math.hypot(drop_center.x() - host_center.x(), drop_center.y() - host_center.y())
            near_host = dist <= HIGH_FIVE_RADIUS_PX
        if near_host:
            self.trigger_high_five(idx, now=now)
        else:
            if rt is not None:
                rt.pose_action = PetAction.WAVE
                rt.pose_until = now + 1.0
            widget.say("回来继续干活啦～", now=now, duration=1.8)

    # ----- Direct / programmatic host <-> subagent interaction triggers ---------

    def trigger_click(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Pet / encourage a mini clone directly and notify the host pet."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        rt.pose_action = PetAction.HEAD_PAT
        rt.pose_until = ts + 2.0
        rt.nudge_until = ts + 0.55
        rt.nudge_strength = 8.0
        line = self._rng.choice(_CLICK_LINES)
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
        )
        self._emit_event(event)
        return event

    def trigger_report(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Clone nudges inward toward the host pet and reports its current task."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        rt.pose_action = PetAction.WAVE
        rt.pose_until = ts + 2.1
        rt.nudge_until = ts + 0.95
        rt.nudge_strength = 24.0
        short_title = _compact_text(info.title or "处理任务中", 10)
        line = f"汇报：{short_title}"
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
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        rt.pose_action = PetAction.CELEBRATE
        rt.pose_until = ts + 2.2
        rt.nudge_until = ts + 0.85
        rt.nudge_strength = 22.0
        line = self._rng.choice(_HIGH_FIVE_LINES)
        widget.say(line, now=ts, duration=2.6)
        widget.emit_particles("hearts", reduced_motion=self._last_reduced_motion)
        widget.emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="high_five",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
        )
        self._emit_event(event)
        return event

    def trigger_group_cheer(self, *, source_index: int = 0, now: float | None = None) -> CloneEvent | None:
        """All active clones + host pet celebrate together."""
        if not self._entries:
            return None
        ts = time.monotonic() if now is None else float(now)
        lead_idx = max(0, min(source_index, len(self._entries) - 1))
        lead_line = self._rng.choice(_GROUP_CHEER_LINES)
        for idx, (info, _fid, _badge) in enumerate(self._entries):
            if idx >= len(self._widgets):
                break
            rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
            rt.pose_action = PetAction.CELEBRATE
            rt.pose_until = ts + 2.0
            rt.nudge_until = ts + 0.65
            rt.nudge_strength = 12.0
            self._widgets[idx].emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
            if idx == lead_idx:
                self._widgets[idx].say(lead_line, now=ts, duration=2.4)
        info, form_id, badge = self._entries[lead_idx]
        rt_lead = self._runtime[info.conversation_id]
        event = CloneEvent(
            kind="group_cheer",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt_lead.last_side,
            text=lead_line,
        )
        self._emit_event(event)
        return event

    def trigger_relay(self, index: int = 0, *, now: float | None = None) -> CloneEvent | None:
        """Clone sends a collaborative clue / energy relay pulse to the host pet."""
        if not (0 <= index < len(self._entries)) or index >= len(self._widgets):
            return None
        ts = time.monotonic() if now is None else float(now)
        info, form_id, badge = self._entries[index]
        widget = self._widgets[index]
        rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
        if rt.dragging:
            return None
        rt.nudge_until = ts + 0.72
        rt.nudge_strength = 16.0
        line = self._rng.choice(_RELAY_LINES)
        widget.say(line, now=ts, duration=2.4)
        widget.emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
        event = CloneEvent(
            kind="relay",
            conversation_id=info.conversation_id,
            form_id=form_id,
            badge=badge,
            title=info.title,
            side=rt.last_side,
            text=line,
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
            rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=ts))
            if clone_action != PetAction.WORKING:
                rt.pose_action = clone_action
                rt.pose_until = ts + duration
            if idx == speaker_idx and lines:
                self._widgets[idx].say(self._rng.choice(lines), now=ts, duration=min(2.6, duration))
                if particle:
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
    ) -> None:
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
        if finished_ids and not docked and self._last_host_rect is not None:
            for cid in finished_ids[:2]:
                start_pos, side, form_id, badge, title = prev_positions[cid]
                dep_widget = SubagentCloneWidget(topmost=self._topmost, rng=self._rng)
                frames = self._mini_frames(form_id, mirrored=(side > 0), action=PetAction.CELEBRATE)
                pix = frames[0] if frames else self._mini_pixmap(form_id, mirrored=(side > 0))
                max_fw = max((p.width() for p in frames), default=64)
                max_fh = max((p.height() for p in frames), default=84)
                line = self._rng.choice(_HANDOFF_LINES)
                dep_widget.configure(
                    pixmap=pix,
                    badge=badge,
                    accent=_ACCENTS.get(form_id, "#8b5cf6"),
                    tooltip=f"子代理交卷 · {title or badge}",
                    opacity=max(0.75, self._fade),
                    min_frame_size=(max_fw, max_fh),
                    frame_index=0,
                    mirrored=(side > 0),
                )
                dep_widget.move(start_pos)
                dep_widget.say(line, now=ts, duration=HANDOFF_DURATION_SECONDS)
                dep_widget.emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
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

        if not prev_ids:
            self._next_relay_at = ts + self._rng.uniform(RELAY_INTERVAL_MIN_SECONDS, RELAY_INTERVAL_MAX_SECONDS)

        newly_announced = False
        for idx, widget in enumerate(self._widgets):
            if idx >= len(entries):
                widget.hide()
                continue
            info, form_id, badge = entries[idx]
            frames = self._mini_frames(form_id, mirrored=False)
            pix = frames[0] if frames else QPixmap()
            max_fw = max((p.width() for p in frames), default=64)
            max_fh = max((p.height() for p in frames), default=84)
            title = info.title or f"子代理 #{idx + 1}"
            model_line = f"\n模型：{info.model_label}" if info.model_label else ""
            widget.configure(
                pixmap=pix,
                badge=badge,
                accent=_ACCENTS.get(form_id, "#8b5cf6"),
                tooltip=f"子代理分身 · {title}{model_line}\n单击打气 · 双击汇报 · 拖给主宠击掌 · 右键欢呼",
                opacity=self._fade,
                min_frame_size=(max_fw, max_fh),
                frame_index=0,
                mirrored=False,
                hover_label=title,
            )
            if info.conversation_id not in self._runtime:
                side = -1 if idx % 2 == 0 else 1
                self._runtime[info.conversation_id] = _CloneRuntime(spawned_at=ts, last_side=side)
                if not newly_announced and not docked:
                    newly_announced = True
                    line = self._rng.choice(_SUMMON_LINES)
                    widget.say(line, now=ts, duration=2.2)
                    widget.emit_particles("sparkles", reduced_motion=self._last_reduced_motion)
                    self._emit_event(
                        CloneEvent(
                            kind="summoned",
                            conversation_id=info.conversation_id,
                            form_id=form_id,
                            badge=badge,
                            title=title,
                            side=side,
                            text=line,
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
    def _resolve_keepout_slot(
        *,
        preferred_x: int,
        preferred_y: int,
        preferred_side: int,
        widget_w: int,
        widget_h: int,
        host_rect: QRect,
        area: QRect,
        keepouts: list[QRect],
        placed_rects: list[QRect],
        left_tier: int,
        below_tier: int,
        single_side_stack: bool,
        sway_x: float,
    ) -> tuple[int, int, int, bool, bool]:
        """Resolve a clone position so it never overlaps any keep-out zone.

        Returns ``(x, y, final_side, used_left_tier, used_below_tier)``.
        """

        def clamp(px: int, py: int) -> tuple[int, int]:
            return (
                max(area.left(), min(px, area.right() - widget_w + 1)),
                max(area.top(), min(py, area.bottom() - widget_h + 1)),
            )

        def hitting(px: int, py: int) -> list[QRect]:
            rect = QRect(px, py, widget_w, widget_h)
            return [kz for kz in keepouts if rect.intersects(kz)]

        def overlap_area(px: int, py: int) -> int:
            rect = QRect(px, py, widget_w, widget_h)
            total = 0
            for other in placed_rects:
                inter = rect.intersected(other)
                if inter.isValid():
                    total += inter.width() * inter.height()
            return total

        cx, cy = clamp(preferred_x, preferred_y)
        hits = hitting(cx, cy)
        if not hits:
            return cx, cy, preferred_side, False, False

        candidates: list[tuple[int, int, int, bool, bool]] = []

        # 1. Prefer shifting cleanly to the left of the host pet.
        for t in range(left_tier, left_tier + 4):
            gap_x = 12 + (t % 2) * (widget_w - 10)
            row = (t // 2) if single_side_stack else t
            lx = round(host_rect.left() - widget_w - gap_x + sway_x)
            ly = round(host_rect.bottom() - widget_h - (18 + row * 48))
            lx, ly = clamp(lx, ly)
            if not hitting(lx, ly):
                if overlap_area(lx, ly) == 0:
                    return lx, ly, -1, True, False
                candidates.append((lx, ly, -1, True, False))

        # 2. If host itself sits near the keep-out zone, tuck just left of the keep-out.
        min_kz_left = min(kz.left() for kz in hits)
        for t in range(4):
            lx = min_kz_left - widget_w - 8 - (t % 2) * (widget_w - 10)
            ly = cy + (t // 2) * 52
            lx, ly = clamp(lx, ly)
            if not hitting(lx, ly):
                if overlap_area(lx, ly) == 0:
                    return lx, ly, -1, True, False
                candidates.append((lx, ly, -1, True, False))

        # 3. Otherwise drop cleanly below the keep-out zone.
        max_kz_bottom = max(kz.bottom() for kz in hits)
        for t in range(below_tier, below_tier + 4):
            by = max_kz_bottom + 8 + t * 48
            for bx_raw in (preferred_x, host_rect.right() + 12, host_rect.left() - widget_w - 12):
                bx, by_c = clamp(bx_raw, by)
                if not hitting(bx, by_c):
                    b_side = -1 if (bx + widget_w // 2) < host_rect.center().x() else 1
                    if overlap_area(bx, by_c) == 0:
                        return bx, by_c, b_side, False, True
                    candidates.append((bx, by_c, b_side, False, True))

        if candidates:
            return min(candidates, key=lambda c: overlap_area(c[0], c[1]))

        # Last-resort fallback on tiny screens: bottom-left of work area.
        fx, fy = clamp(area.left(), area.bottom() - widget_h + 1)
        return fx, fy, -1, False, True

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
                continue
            t = min(1.0, elapsed / max(0.05, dep.duration))
            ease = 1.0 - (1.0 - t) ** 2
            target_x = (
                host_rect.left() - dep.widget.width() + 12
                if dep.side < 0
                else host_rect.right() - 12
            )
            target_y = host_rect.center().y() - dep.widget.height() // 2
            if not reduced_motion:
                nx = round(dep.start_pos.x() + (target_x - dep.start_pos.x()) * ease)
                ny = round(dep.start_pos.y() + (target_y - dep.start_pos.y()) * ease - math.sin(t * math.pi) * 18.0)
                dep.widget.move(nx, ny)
            opacity = 1.0 if t < 0.65 else max(0.0, (1.0 - t) / 0.35)
            frames = self._mini_frames(dep.form_id, mirrored=(dep.side > 0), action=PetAction.CELEBRATE)
            if frames:
                frame_idx = 0 if (reduced_motion or len(frames) <= 1) else (int(elapsed / 0.16) % len(frames))
                dep.widget.set_frame(frames[frame_idx], frame_index=frame_idx, mirrored=(dep.side > 0), action=PetAction.CELEBRATE)
            dep.widget.set_bob(0.0 if reduced_motion else -abs(math.sin(elapsed * 8.0)) * 5.0, opacity)
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
        space_left = host_rect.left() - area.left()
        space_right = area.right() - host_rect.right()
        min_slot_w = max((self._widgets[i].width() for i in range(count)), default=112) + 16
        can_left = space_left >= min_slot_w
        can_right = space_right >= min_slot_w
        single_side_stack = not can_left or not can_right

        left_tier = 0
        right_tier = 0
        below_tier = 0
        placed_rects: list[QRect] = []
        for idx in range(count):
            widget = self._widgets[idx]
            info, form_id, _badge = self._entries[idx]
            rt = self._runtime.setdefault(info.conversation_id, _CloneRuntime(spawned_at=now))
            if can_left and can_right:
                side = -1 if idx % 2 == 0 else 1
            elif can_left:
                side = -1
            elif can_right:
                side = 1
            else:
                side = -1 if space_left >= space_right else 1
            if side < 0:
                tier = left_tier
                gap_x = 12 + (tier % 2) * (widget.width() - 10)
                x = host_rect.left() - widget.width() - gap_x
            else:
                tier = right_tier
                gap_x = 12 + (tier % 2) * (widget.width() - 10)
                x = host_rect.right() + gap_x
            row = tier // 2 if single_side_stack else tier
            base_y = host_rect.bottom() - widget.height() - (18 + row * 48)
            sway_x = 0.0 if reduced_motion else math.sin(now * 1.9 + idx * 1.7) * 3.0
            bob_y = 0.0 if reduced_motion else math.sin(now * 3.1 + idx * 1.35) * 5.0

            clamped_x, clamped_y, final_side, used_left, used_below = self._resolve_keepout_slot(
                preferred_x=round(x + sway_x),
                preferred_y=round(base_y),
                preferred_side=side,
                widget_w=widget.width(),
                widget_h=widget.height(),
                host_rect=host_rect,
                area=area,
                keepouts=keepouts,
                placed_rects=placed_rects,
                left_tier=left_tier,
                below_tier=below_tier,
                single_side_stack=single_side_stack,
                sway_x=sway_x,
            )
            if used_left:
                left_tier += 1
            elif used_below:
                below_tier += 1
            elif final_side < 0:
                left_tier += 1
            else:
                right_tier += 1
            rt.last_side = final_side
            placed_rects.append(QRect(clamped_x, clamped_y, widget.width(), widget.height()))

            # Resolve active pose override (falls back to WORKING typing once expired)
            active_action = PetAction.WORKING
            if rt.pose_action is not None:
                if now < rt.pose_until or rt.dragging:
                    active_action = rt.pose_action
                else:
                    rt.pose_action = None
                    rt.pose_until = 0.0

            # Mirror clones on the right side (side > 0) so dual clones face symmetrically inward.
            mirrored = final_side > 0
            frames = self._mini_frames(form_id, mirrored=mirrored, action=active_action)
            if frames:
                frame_idx = (
                    0
                    if (reduced_motion or len(frames) <= 1)
                    else (int((now + idx * CLONE_PHASE_STEP_SECONDS) / FRAME_INTERVAL_SECONDS) % len(frames))
                )
                widget.set_frame(frames[frame_idx], frame_index=frame_idx, mirrored=mirrored, action=active_action)

            if not rt.dragging:
                target_x, target_y = clamped_x, clamped_y
                # Smooth inward nudge during report / high-five / relay (never crosses host edge!)
                if not reduced_motion and now < rt.nudge_until:
                    rem = max(0.0, rt.nudge_until - now)
                    nudge_px = math.sin(min(1.0, rem / 0.75) * math.pi) * rt.nudge_strength
                    if final_side < 0:
                        target_x = min(host_rect.left() - widget.width() - 2, round(target_x + nudge_px))
                    else:
                        target_x = max(host_rect.right() + 2, round(target_x - nudge_px))
                # Gentle pop-out slide on fresh summon (stays strictly on clone's own side of host)
                elif not reduced_motion and (now - rt.spawned_at) < SUMMON_SLIDE_SECONDS:
                    st = max(0.0, min(1.0, (now - rt.spawned_at) / SUMMON_SLIDE_SECONDS))
                    ease = 1.0 - (1.0 - st) ** 3
                    origin_x = (
                        host_rect.left() - widget.width() - 2
                        if final_side < 0
                        else host_rect.right() + 2
                    )
                    target_x = round(origin_x + (clamped_x - origin_x) * ease)
                # Smooth glide back to orbit after user drops a dragged clone
                if rt.glide_from is not None:
                    gt = max(0.0, min(1.0, (now - rt.glide_started_at) / GLIDE_RETURN_SECONDS))
                    if reduced_motion or gt >= 1.0:
                        rt.glide_from = None
                    else:
                        ge = 1.0 - (1.0 - gt) ** 3
                        target_x = round(rt.glide_from.x() + (target_x - rt.glide_from.x()) * ge)
                        target_y = round(rt.glide_from.y() + (target_y - rt.glide_from.y()) * ge)
                target_x = max(area.left(), min(target_x, area.right() - widget.width() + 1))
                target_y = max(area.top(), min(target_y, area.bottom() - widget.height() + 1))
                if (target_x, target_y) != (widget.x(), widget.y()):
                    widget.move(target_x, target_y)
            widget.set_bob(bob_y, self._fade)
            widget.tick_fx(dt, now=now, reduced_motion=reduced_motion)
            if not widget.isVisible():
                widget.show()

        for extra in self._widgets[count:]:
            if extra.isVisible():
                extra.hide()

        # Periodic collaborative banter / relay pulse while subagents work
        if self._next_relay_at > 0 and now >= self._next_relay_at:
            self._next_relay_at = now + self._rng.uniform(RELAY_INTERVAL_MIN_SECONDS, RELAY_INTERVAL_MAX_SECONDS)
            free_indices = [
                i
                for i, (info, _f, _b) in enumerate(self._entries)
                if not self._runtime.get(info.conversation_id, _CloneRuntime(now)).dragging
            ]
            if free_indices:
                self.trigger_relay(self._rng.choice(free_indices), now=now)

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
