"""Floating miniature pet clones for active Antigravity subagents.

Reuses the existing 5-form runtime sprite assets (carbon / hydergon / neon /
argon / claude) scaled down to ~50% height, matching each subagent's own model
family when known and falling back to the main pet's active form.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication, QWidget

from agy.characters import form_by_id, form_for_model_label, normalize_form
from agy.telemetry import SubagentInfo
from animation.asset_registry import AssetRegistry
from animation.clip import PetAction

MAX_VISIBLE_CLONES = 4
MAX_ANIMATION_FRAMES = 4
FRAME_INTERVAL_SECONDS = 0.18
CLONE_PHASE_STEP_SECONDS = 0.45

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
        self._mirrored = False
        self._frame_index = 0
        self._badge_font = QFont()
        self._badge_font.setPointSize(8)
        self._badge_font.setWeight(QFont.Weight.DemiBold)
        self.setFixedSize(112, 132)

    @property
    def mirrored(self) -> bool:
        return self._mirrored

    @property
    def frame_index(self) -> int:
        return self._frame_index

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
    ) -> None:
        self._pixmap = pixmap
        self._badge = badge
        self._accent = QColor(accent)
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self._frame_index = int(frame_index)
        self._mirrored = bool(mirrored)
        self.setToolTip(tooltip)
        frame_w = pixmap.width() if not pixmap.isNull() else 64
        frame_h = pixmap.height() if not pixmap.isNull() else 84
        if min_frame_size is not None:
            frame_w = max(frame_w, int(min_frame_size[0]))
            frame_h = max(frame_h, int(min_frame_size[1]))
        w = max(84, frame_w + 24)
        h = max(108, frame_h + 34)
        if (self.width(), self.height()) != (w, h):
            self.setFixedSize(w, h)
        self.update()

    def set_frame(self, pixmap: QPixmap, *, frame_index: int = 0, mirrored: bool = False) -> None:
        if pixmap.isNull():
            return
        idx = int(frame_index)
        mirror_flag = bool(mirrored)
        if (
            idx == self._frame_index
            and mirror_flag == self._mirrored
            and not self._pixmap.isNull()
            and pixmap.cacheKey() == self._pixmap.cacheKey()
        ):
            return
        self._pixmap = pixmap
        self._frame_index = idx
        self._mirrored = mirror_flag
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
        self._frame_cache: dict[tuple[str, int, bool], tuple[QPixmap, ...]] = {}
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

    def _mini_frames(self, form_id: str, *, mirrored: bool = False) -> tuple[QPixmap, ...]:
        norm = normalize_form(form_id)
        key = (norm, self._sprite_height, bool(mirrored))
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
        raw_frames: list[QPixmap] = []
        for action in (PetAction.WORKING, PetAction.IDLE):
            try:
                clip = registry.clip_for(action, height=187, direction="down")
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
        self._frame_cache[(norm, self._sprite_height, False)] = normal
        self._frame_cache[(norm, self._sprite_height, True)] = flipped
        return flipped if mirrored else normal

    def _mini_pixmap(self, form_id: str, *, mirrored: bool = False) -> QPixmap:
        frames = self._mini_frames(form_id, mirrored=mirrored)
        return frames[0] if frames else QPixmap()

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

        while len(self._widgets) < len(entries):
            self._widgets.append(SubagentCloneWidget(topmost=self._topmost))

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
                tooltip=f"子代理分身 · {title}{model_line}",
                opacity=self._fade,
                min_frame_size=(max_fw, max_fh),
                frame_index=0,
                mirrored=False,
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
        if not self._entries:
            return
        if (dock_edge or "").strip().lower() in ("left", "right"):
            self._fade = 0.0
            for widget in self._widgets:
                if widget.isVisible():
                    widget.hide()
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

        # Choose non-overlapping (side, tier) slots: alternate when both sides fit,
        # otherwise stack neatly on whichever side has room so clones never overlap.
        left_tier = 0
        right_tier = 0
        below_tier = 0
        placed_rects: list[QRect] = []
        for idx in range(count):
            widget = self._widgets[idx]
            _info, form_id, _badge = self._entries[idx]
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
            placed_rects.append(QRect(clamped_x, clamped_y, widget.width(), widget.height()))

            # Mirror clones on the right side (side > 0) so dual clones face symmetrically inward.
            mirrored = final_side > 0
            frames = self._mini_frames(form_id, mirrored=mirrored)
            if frames:
                frame_idx = (
                    0
                    if (reduced_motion or len(frames) <= 1)
                    else (int((now + idx * CLONE_PHASE_STEP_SECONDS) / FRAME_INTERVAL_SECONDS) % len(frames))
                )
                widget.set_frame(frames[frame_idx], frame_index=frame_idx, mirrored=mirrored)

            if (clamped_x, clamped_y) != (widget.x(), widget.y()):
                widget.move(clamped_x, clamped_y)
            widget.set_bob(bob_y, self._fade)
            if not widget.isVisible():
                widget.show()

        for extra in self._widgets[count:]:
            if extra.isVisible():
                extra.hide()

    def close_all(self) -> None:
        for widget in self._widgets:
            widget.hide()
            widget.close()
            widget.deleteLater()
        self._widgets.clear()
        self._entries.clear()
        self._frame_cache.clear()
        self._registries.clear()
