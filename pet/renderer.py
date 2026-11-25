from __future__ import annotations

import math
import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPolygonF

from animation.effects import EffectPose, pose_for, scaled
from animation.player import PlayerSnapshot, RenderLayer

# Poses that hang off a wall or a window edge rather than stand on a floor.
HANGING_ASSETS = frozenset({"perch_sit", "perch_work", "perch_sleep", "climb_side", "climb_side_right"})
BESPOKE_DOCK_ASSETS = frozenset({
    "dock_peek",
    "dock_peek_right",
    "dock_work",
    "dock_work_right",
    "dock_sleep",
    "dock_sleep_right",
})


@dataclass(slots=True)
class Bubble:
    text: str = ""
    until: float = 0.0
    appeared_at: float = 0.0
    inner: bool = False
    state_name: str = ""

    @property
    def visible(self) -> bool:
        return bool(self.text and time.monotonic() < self.until)

    def opacity_at(self, now: float | None = None) -> float:
        """Use a short entrance/exit so speech feels attached to the pet."""

        now = time.monotonic() if now is None else now
        if not self.text or now >= self.until:
            return 0.0
        if self.appeared_at <= 0:
            return 1.0
        fade_in = min(1.0, max(0.0, (now - self.appeared_at) / 0.13))
        fade_out = min(1.0, max(0.0, (self.until - now) / 0.20))
        return min(fade_in, fade_out)


class PetRenderer:
    """Compose a manifest-selected sprite, subtle motion and a compact bubble."""

    def __init__(self, bubble_height: int, margin: int) -> None:
        self.bubble_height = bubble_height
        self.margin = margin
        # Use Qt's system default instead of pinning a Windows family.  That
        # preserves the platform's CJK fallback chain in bundled/offscreen runs.
        self.speaker_name = "小A"
        self.speaker_accent = QColor(51, 154, 213)
        self.bubble_font = QFont()
        self.bubble_font.setPointSize(10)
        self.bubble_font.setWeight(QFont.Weight.DemiBold)
        self.reduced_motion = False
        self.motion_scale = 0.4  # how strong the procedural whole-body motion is
        # Optional face swap for the idle frame: (asset_id, current, previous,
        # fade) where current/previous are QPixmaps or None (plain idle).
        self.expression: tuple[str, object, object, float] | None = None

    def set_motion_scale(self, amount: float) -> None:
        self.motion_scale = max(0.0, min(1.5, float(amount)))

    def set_reduced_motion(self, enabled: bool) -> None:
        self.reduced_motion = bool(enabled)

    def paint(
        self,
        widget,
        *,
        snapshot: PlayerSnapshot,
        bubble: Bubble,
        particles=None,
        dock_pose: tuple[str, float] | None = None,
        visible_x_range: tuple[float, float] | None = None,
        clip_rect: QRect | None = None,
    ) -> None:
        painter = QPainter(widget)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if clip_rect is not None:
            painter.setClipRect(clip_rect)

        tail_x: float | None = None
        bespoke_dock = (
            snapshot.current is not None
            and dock_pose is not None
            and snapshot.current.asset_id in BESPOKE_DOCK_ASSETS
        )
        if snapshot.current is not None and dock_pose is not None:
            side, peek = dock_pose
            p = max(0.0, min(1.0, float(peek)))
            sign = -1.0 if side == "right" else 1.0
            if bespoke_dock:
                pix_w = max(80.0, float(snapshot.current.frame.pixmap.width()))
                tail_x = widget.width() / 2.0 + sign * pix_w * 0.08
            else:
                angle = sign * (27.0 - 23.0 * p)
                pix_h = max(120.0, float(snapshot.current.frame.pixmap.height()))
                tail_x = widget.width() / 2.0 + math.sin(math.radians(angle)) * pix_h * 0.72
        if bubble.visible:
            self._draw_bubble(
                painter,
                widget.width(),
                bubble,
                visible_x_range=visible_x_range,
                tail_x=tail_x,
            )

        if snapshot.current is None:
            if particles is not None:
                particles.paint(painter)
            return
        hanging = snapshot.current.asset_id in HANGING_ASSETS
        if dock_pose is not None:
            side, peek = dock_pose
            p = max(0.0, min(1.0, float(peek)))
            sign = -1.0 if side == "right" else 1.0
            if bespoke_dock:
                sway = 0.0 if self.reduced_motion else math.sin(snapshot.elapsed_seconds * 2.0) * 1.1
                bob = 0.0 if self.reduced_motion else math.sin(snapshot.elapsed_seconds * 2.4) * 1.5
                pose = EffectPose(rotation_degrees=sign * (2.5 * p) + sway, offset_y=bob - 18.0)
            else:
                sway = 0.0 if self.reduced_motion else math.sin(snapshot.elapsed_seconds * 2.1) * 1.3
                pose = EffectPose(rotation_degrees=sign * (27.0 - 23.0 * p) + sway)
        elif hanging:
            # On a wall or a window edge: no floor shadow and no procedural
            # sway, bob or tilt; she sits (or hangs) still.
            pose = EffectPose()
        else:
            pose = EffectPose() if self.reduced_motion else scaled(pose_for(snapshot.effect, snapshot.elapsed_seconds), self.motion_scale)
        floor = QPointF(widget.width() / 2.0, widget.height() - self.margin - 7.0)
        current_anchor = self._render_anchor(widget, snapshot.current)
        if not hanging and dock_pose is None:
            self._draw_shadow(painter, floor, snapshot.current, pose)
        if snapshot.previous is not None and snapshot.previous_opacity > 0:
            self._draw_layer(
                painter,
                snapshot.previous,
                self._render_anchor(widget, snapshot.previous),
                pose,
                snapshot.previous_opacity,
                docked=dock_pose is not None,
            )
        self._draw_layer(
            painter,
            snapshot.current,
            current_anchor,
            pose,
            snapshot.current_opacity,
            docked=dock_pose is not None,
        )
        if particles is not None:
            particles.paint(painter)

    def _render_anchor(self, widget, layer: RenderLayer) -> QPointF:
        """Keep non-standing actions inside the allocated sprite slot.

        Ground-anchored clips pivot at the feet.  Dragging, falling and seated
        clips pivot near the centre of that same slot; drawing those clips at
        the floor was the cause of the "head only" crop during a grab.
        """

        slot_top = self.bubble_height + self.margin
        slot_bottom = widget.height() - self.margin - 7.0
        if layer.anchor.kind in {"drag", "seat", "sleep"}:
            return QPointF(widget.width() / 2.0, (slot_top + slot_bottom) / 2.0)
        return QPointF(widget.width() / 2.0, slot_bottom)

    def _draw_layer(
        self,
        painter: QPainter,
        layer: RenderLayer,
        ground: QPointF,
        pose: EffectPose,
        opacity: float,
        *,
        docked: bool = False,
    ) -> None:
        pixmap = layer.frame.pixmap
        if pixmap.isNull() or opacity <= 0:
            return
        under = None  # the face we are fading away from
        if self.expression is not None and layer.asset_id == self.expression[0] and not layer.frame.pixmap.isNull():
            _asset, face, old_face, fade = self.expression
            if fade < 1.0:
                under = old_face if old_face is not None else pixmap
            if face is not None and face.size() == pixmap.size():
                pixmap = face
            if under is not None and (under is pixmap or under.size() != pixmap.size()):
                under = None
        anchor_x = pixmap.width() * layer.anchor.x
        anchor_y = pixmap.height() * layer.anchor.y
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, opacity)))
        offset_y = pose.offset_y
        if layer.anchor.kind not in {"drag", "seat", "sleep"}:
            # Grounded clips pivot at the feet: allow a subtle downward squash
            # for landing/head_pat/tired while still lifting by tilt dip.
            dip_factor = 0.12 if docked else 0.32
            dip = abs(math.sin(math.radians(pose.rotation_degrees))) * pixmap.width() * dip_factor
            offset_y = min(12.0, offset_y) - dip
        painter.translate(ground.x() + pose.offset_x, ground.y() + offset_y)
        painter.rotate(pose.rotation_degrees)
        scale_x = pose.scale_x * (-1.0 if layer.mirrored else 1.0)
        painter.scale(scale_x, pose.scale_y)
        painter.translate(-anchor_x, -anchor_y)
        if under is not None:
            # Same pose, different face: lay the old face fully, the new one
            # over it, so the body never turns see-through mid-fade.
            painter.drawPixmap(0, 0, under)
            painter.setOpacity(max(0.0, min(1.0, opacity)) * self.expression[3])
        painter.drawPixmap(0, 0, pixmap)
        painter.restore()

    def _draw_shadow(
        self,
        painter: QPainter,
        ground: QPointF,
        layer: RenderLayer,
        pose: EffectPose,
    ) -> None:
        pixmap = layer.frame.pixmap
        width = max(22.0, pixmap.width() * 0.27 * pose.shadow_scale)
        height = max(4.0, pixmap.height() * 0.027 * pose.shadow_scale)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        # Two offset translucent ellipses create depth without a hard outline.
        painter.setBrush(QColor(10, 48, 87, max(0, int(pose.shadow_opacity * 34))))
        painter.drawEllipse(QRectF(ground.x() - width / 2 - 1, ground.y() - height / 2 + 2, width + 2, height + 2))
        painter.setBrush(QColor(10, 48, 87, max(0, int(pose.shadow_opacity * 130))))
        painter.drawEllipse(QRectF(ground.x() - width / 2, ground.y() - height / 2 + 1, width, height))
        painter.restore()

    def _draw_bubble(
        self,
        painter: QPainter,
        width: int,
        bubble: Bubble,
        *,
        visible_x_range: tuple[float, float] | None = None,
        tail_x: float | None = None,
    ) -> None:
        opacity = 1.0 if self.reduced_motion and bubble.visible else bubble.opacity_at()
        if opacity <= 0:
            return
        font = QFont(self.bubble_font)
        if bubble.inner:
            font.setItalic(True)
            background = QColor(232, 243, 251, 248)
            foreground = QColor(50, 84, 113)
            accent = QColor(98, 148, 187)
            label = "内心 OS"
        else:
            background = QColor(250, 253, 255, 250)
            foreground = QColor(18, 57, 91)
            accent = QColor(self.speaker_accent)
            label = self.speaker_name
        metrics = QFontMetrics(font)
        label_font = QFont(font)
        label_font.setPointSize(8)
        label_font.setWeight(QFont.Weight.DemiBold)
        label_metrics = QFontMetrics(label_font)
        vis_left = 0.0
        vis_right = float(width)
        if visible_x_range is not None:
            vis_left = max(0.0, min(float(width), float(visible_x_range[0])))
            vis_right = max(vis_left, min(float(width), float(visible_x_range[1])))
        avail_w = max(84.0, vis_right - vis_left - 12.0)
        max_width = min(242, int(avail_w))
        lines = self._wrap_text(bubble.text, metrics, max(56, max_width - 28))
        if not lines:
            return
        min_bubble_w = min(126, max_width)
        bubble_width = max(min_bubble_w, max(metrics.horizontalAdvance(line) for line in lines) + 28)
        bubble_width = min(max_width, bubble_width)
        bubble_height = label_metrics.height() + len(lines) * metrics.height() + 17
        center_x = width / 2.0 if tail_x is None else float(tail_x)
        bubble_x = center_x - bubble_width / 2.0
        min_bx = vis_left + 6.0
        max_bx = max(min_bx, vis_right - bubble_width - 6.0)
        bubble_x = max(min_bx, min(max_bx, bubble_x))
        bubble_y = 4.0
        body = QRectF(bubble_x, bubble_y, bubble_width, bubble_height)

        painter.save()
        painter.setOpacity(opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        # One light offset shadow keeps the bubble legible without turning it
        # into a heavy notification card.
        painter.setBrush(QColor(8, 42, 77, 25))
        painter.drawRoundedRect(body.translated(0, 3), 12, 12)
        painter.setBrush(background)
        painter.drawRoundedRect(body, 12, 12)
        clamped_tail_x = max(bubble_x + 18.0, min(bubble_x + bubble_width - 18.0, center_x))
        tail_y = bubble_y + bubble_height
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(clamped_tail_x - 5.0, tail_y),
                    QPointF(clamped_tail_x + 5.0, tail_y),
                    QPointF(clamped_tail_x, tail_y + 6.0),
                ]
            )
        )
        painter.setBrush(accent)
        painter.drawEllipse(QRectF(bubble_x + 12, bubble_y + 8, 5, 5))
        painter.setPen(accent)
        painter.setFont(label_font)
        painter.drawText(
            QRectF(bubble_x + 21, bubble_y + 4, bubble_width - 32, label_metrics.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        painter.setPen(foreground)
        painter.setFont(font)
        for index, line in enumerate(lines):
            painter.drawText(
                QRectF(
                    bubble_x + 14,
                    bubble_y + label_metrics.height() + 7 + index * metrics.height(),
                    bubble_width - 28,
                    metrics.height(),
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line,
            )
        painter.restore()

    @staticmethod
    def _wrap_text(text: str, metrics: QFontMetrics, max_width: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for character in text:
            if current and metrics.horizontalAdvance(current + character) > max_width:
                lines.append(current)
                current = character
            else:
                current += character
        if current:
            lines.append(current)
        return lines[:2]
