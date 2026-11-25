"""Floating miniature pet clones for active Antigravity subagents.

Reuses the existing 5-form runtime sprite assets (carbon / hydergon / neon /
argon / claude) scaled down to ~50% height, matching each subagent's own model
family when known and falling back to the main pet's active form.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from agy.characters import form_by_id, form_for_model_label, normalize_form
from agy.telemetry import SubagentInfo
from animation.asset_registry import AssetRegistry
from animation.clip import PetAction

MAX_VISIBLE_CLONES = 4

_ACCENTS: dict[str, str] = {
    "carbon": "#4b5563",
    "hydergon": "#2b8fd6",
    "neon": "#c026d3",
    "argon": "#8b5cf6",
    "claude": "#ea580c",
}


class SubagentCloneWidget(QWidget):
    """One compact always-on-top miniature companion representing a running subagent."""

    def __init__(self, *, topmost: bool = True) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if topmost:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("AGY 子代理分身")

        self._pixmap = QPixmap()
        self._badge = ""
        self._accent = QColor("#8b5cf6")
        self._opacity = 1.0
        self._bob_y = 0.0
        self._badge_font = QFont()
        self._badge_font.setPointSize(8)
        self._badge_font.setWeight(QFont.Weight.DemiBold)
        self.setFixedSize(112, 132)

    def configure(
        self,
        *,
        pixmap: QPixmap,
        badge: str,
        accent: str,
        tooltip: str,
        opacity: float = 1.0,
    ) -> None:
        self._pixmap = pixmap
        self._badge = badge
        self._accent = QColor(accent)
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self.setToolTip(tooltip)
        w = max(84, (pixmap.width() if not pixmap.isNull() else 64) + 24)
        h = max(108, (pixmap.height() if not pixmap.isNull() else 84) + 34)
        if (self.width(), self.height()) != (w, h):
            self.setFixedSize(w, h)
        self.update()

    def set_bob(self, offset_y: float, opacity: float) -> None:
        self._bob_y = float(offset_y)
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self.update()

    def set_topmost(self, topmost: bool) -> None:
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(topmost))
        if was_visible:
            self.show()

    def paintEvent(self, _event) -> None:
        if self._opacity <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)

        # Soft halo shadow under the floating mini clone
        cx = self.width() / 2.0
        shadow_y = self.height() - 24.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 42))
        painter.drawEllipse(QRectF(cx - 24.0, shadow_y - 4.0, 48.0, 9.0))

        if not self._pixmap.isNull():
            px = (self.width() - self._pixmap.width()) / 2.0
            py = max(2.0, shadow_y - self._pixmap.height() + self._bob_y)
            painter.drawPixmap(round(px), round(py), self._pixmap)

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
    """Manages miniature floating clones orbiting the main desktop pet."""

    def __init__(
        self,
        characters_root: Path,
        base_manifest: Path,
        *,
        topmost: bool = True,
    ) -> None:
        self._characters_root = Path(characters_root)
        self._base_manifest = Path(base_manifest)
        self._topmost = bool(topmost)
        self._registries: dict[str, AssetRegistry] = {}
        self._pixmap_cache: dict[tuple[str, int], QPixmap] = {}
        self._widgets: list[SubagentCloneWidget] = []
        self._entries: list[tuple[SubagentInfo, str, str]] = []  # (info, form_id, badge)
        self._enabled = True
        self._host_visible = True
        self._sprite_height = 96
        self._fade = 0.0

    @property
    def active_count(self) -> int:
        return len(self._entries)

    @property
    def visible_widgets(self) -> tuple[SubagentCloneWidget, ...]:
        return tuple(w for w in self._widgets if w.isVisible())

    def set_topmost(self, topmost: bool) -> None:
        self._topmost = bool(topmost)
        for widget in self._widgets:
            widget.set_topmost(self._topmost)

    def set_scale_from_host(self, host_sprite_height: int) -> None:
        target = max(72, min(124, round(host_sprite_height * 0.44)))
        if abs(target - self._sprite_height) >= 4:
            self._sprite_height = target

    def _mini_pixmap(self, form_id: str) -> QPixmap:
        norm = normalize_form(form_id)
        key = (norm, self._sprite_height)
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            return cached
        registry = self._registries.get(norm)
        if registry is None:
            try:
                registry = AssetRegistry(self._characters_root / norm, base_manifest=self._base_manifest)
                self._registries[norm] = registry
            except Exception:
                return QPixmap()
        source = QPixmap()
        for action in (PetAction.WORKING, PetAction.IDLE):
            try:
                clip = registry.clip_for(action, height=187, direction="down")
                if clip.frames and not clip.frames[0].pixmap.isNull():
                    source = clip.frames[0].pixmap
                    break
            except Exception:
                continue
        if source.isNull():
            return QPixmap()
        scaled = source.scaledToHeight(self._sprite_height, Qt.TransformationMode.SmoothTransformation)
        self._pixmap_cache[key] = scaled
        return scaled

    def sync(
        self,
        subagents: list[SubagentInfo],
        *,
        default_form: str,
        enabled: bool,
        host_visible: bool,
    ) -> None:
        self._enabled = bool(enabled)
        self._host_visible = bool(host_visible)
        if not self._enabled or not self._host_visible or not subagents:
            self._entries = []
            self._fade = 0.0
            for widget in self._widgets:
                widget.hide()
            return

        shown = list(subagents[:MAX_VISIBLE_CLONES])
        overflow = max(0, len(subagents) - MAX_VISIBLE_CLONES)
        entries: list[tuple[SubagentInfo, str, str]] = []
        for idx, info in enumerate(shown):
            resolved_form = (
                normalize_form(info.form_id)
                if info.form_id
                else (form_for_model_label(info.model_label) or normalize_form(default_form))
            )
            form_meta = form_by_id(resolved_form)
            badge = f"+{overflow + 1}" if overflow > 0 and idx == len(shown) - 1 else form_meta.name
            entries.append((info, resolved_form, badge))
        self._entries = entries

        while len(self._widgets) < len(entries):
            self._widgets.append(SubagentCloneWidget(topmost=self._topmost))

        for idx, widget in enumerate(self._widgets):
            if idx >= len(entries):
                widget.hide()
                continue
            info, form_id, badge = entries[idx]
            pix = self._mini_pixmap(form_id)
            title = info.title or f"子代理 #{idx + 1}"
            model_line = f"\n模型：{info.model_label}" if info.model_label else ""
            widget.configure(
                pixmap=pix,
                badge=badge,
                accent=_ACCENTS.get(form_id, "#8b5cf6"),
                tooltip=f"子代理分身 · {title}{model_line}",
                opacity=max(0.25, self._fade),
            )
            if not widget.isVisible():
                widget.show()

    def position_around(self, host_rect: QRect, *, now: float, reduced_motion: bool = False) -> None:
        if not self._entries:
            return
        self._fade = min(1.0, self._fade + 0.14) if not reduced_motion else 1.0
        screen = QApplication.screenAt(host_rect.center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        # Alternate left / right slots arranged in a gentle arc beside the main pet.
        count = len(self._entries)
        side_order = (-1, 1, -1, 1)
        tier_order = (0, 0, 1, 1)
        for idx in range(count):
            widget = self._widgets[idx]
            side = side_order[idx]
            tier = tier_order[idx]
            gap_x = 12 + tier * (widget.width() - 10)
            if side < 0:
                x = host_rect.left() - widget.width() - gap_x
                if x < area.left():
                    x = host_rect.right() + gap_x
            else:
                x = host_rect.right() + gap_x
                if x + widget.width() > area.right():
                    x = host_rect.left() - widget.width() - gap_x
            base_y = host_rect.bottom() - widget.height() - (18 + tier * 42)
            sway_x = 0.0 if reduced_motion else math.sin(now * 1.9 + idx * 1.7) * 3.0
            bob_y = 0.0 if reduced_motion else math.sin(now * 3.1 + idx * 1.35) * 5.0
            clamped_x = max(area.left(), min(round(x + sway_x), area.right() - widget.width() + 1))
            clamped_y = max(area.top(), min(round(base_y), area.bottom() - widget.height() + 1))
            if (clamped_x, clamped_y) != (widget.x(), widget.y()):
                widget.move(clamped_x, clamped_y)
            widget.set_bob(bob_y, self._fade)

    def close_all(self) -> None:
        for widget in self._widgets:
            widget.hide()
            widget.close()
        self._widgets.clear()
        self._entries.clear()
