from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF

from animation.effects import EffectPose, pose_for, scaled
from animation.player import PlayerSnapshot, RenderLayer
from animation.soft_rig import RigParams, SoftRigDeformer
from pet.particles import draw_fish_stash

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


def _has_cjk(text: str) -> bool:
    return any("\u3400" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" for ch in text)


@dataclass(slots=True)
class Bubble:
    text: str = ""
    until: float = 0.0
    appeared_at: float = 0.0
    inner: bool = False
    state_name: str = ""
    is_ai: bool = False

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

    def visible_text_at(self, now: float | None = None, *, reduced_motion: bool = False) -> str:
        """Progressive typewriter reveal matching lively comic-bubble pacing."""

        if not self.text:
            return ""
        if reduced_motion or self.appeared_at <= 0:
            return self.text
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self.appeared_at)
        total = len(self.text)
        per_char = 0.036 if _has_cjk(self.text) else 0.018
        # Cap full reveal duration so long sentences still finish crisply.
        effective_step = min(per_char, 1.15 / max(1, total))
        shown = max(1, int(elapsed / max(0.006, effective_step)) + 1)
        return self.text[: min(total, shown)]

    def is_typing_at(self, now: float | None = None, *, reduced_motion: bool = False) -> bool:
        if reduced_motion or not self.text or self.appeared_at <= 0:
            return False
        now = time.monotonic() if now is None else now
        return now < self.until and len(self.visible_text_at(now, reduced_motion=False)) < len(self.text)


class PetRenderer:
    """Compose a manifest-selected sprite, two-layer particles, fish stash, and comic bubble."""

    def __init__(self, bubble_height: int, margin: int) -> None:
        self.bubble_height = bubble_height
        self.margin = margin
        # Use Qt's system default instead of pinning a Windows family. That
        # preserves the platform's CJK fallback chain in bundled/offscreen runs.
        self.speaker_name = "小A"
        self.speaker_accent = QColor("#a78bfa")
        self.bubble_font = QFont()
        self.bubble_font.setPointSize(10)
        self.bubble_font.setWeight(QFont.Weight.DemiBold)
        self.reduced_motion = False
        self.motion_scale = 0.4  # how strong the procedural whole-body motion is
        # Optional face swap for the idle frame: (asset_id, current, previous,
        # fade) where current/previous are QPixmaps or None (plain idle).
        self.expression: tuple[str, object, object, float] | None = None
        # Optional floating dried-fish quota bowl ("小鱼干碗")
        self._stash_show = 0.0
        self._stash_target = 0.0
        self._stash_level = 1.0
        self._stash_label = ""
        self._visual_clock = 0.0
        self.soft_rig_enabled = True
        self._deformer = SoftRigDeformer()

    def set_motion_scale(self, amount: float) -> None:
        self.motion_scale = max(0.0, min(1.5, float(amount)))

    def set_reduced_motion(self, enabled: bool) -> None:
        self.reduced_motion = bool(enabled)

    def set_fish_stash(self, *, level: float | None, label: str = "", show: bool = False) -> None:
        if level is None or not show:
            self._stash_target = 0.0
            return
        self._stash_level = max(0.0, min(1.0, float(level)))
        self._stash_label = str(label or "")
        self._stash_target = 1.0

    def tick_visuals(self, dt: float) -> None:
        if dt <= 0:
            return
        step = min(0.10, float(dt))
        self._visual_clock += step
        if self.reduced_motion:
            self._stash_show = self._stash_target
        else:
            rate = 1.0 - math.exp(-step * 7.5)
            self._stash_show += (self._stash_target - self._stash_show) * rate
            if abs(self._stash_show - self._stash_target) < 0.005:
                self._stash_show = self._stash_target

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
        rig_params: RigParams | None = None,
        form_id: str = "carbon",
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

        if snapshot.current is None:
            if particles is not None:
                particles.paint(painter)
            if bubble.visible:
                self._draw_bubble(
                    painter,
                    widget.width(),
                    bubble,
                    visible_x_range=visible_x_range,
                    tail_x=tail_x,
                )
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
            pose = (
                EffectPose()
                if self.reduced_motion
                else scaled(pose_for(snapshot.effect, snapshot.elapsed_seconds), self.motion_scale)
            )
            # Subtle rhythmic talking nod while comic bubble typewriter is speaking.
            if not self.reduced_motion and bubble.is_typing_at(reduced_motion=self.reduced_motion):
                nod = max(0.0, math.sin(self._visual_clock * 17.0)) * 2.1
                pose = EffectPose(
                    offset_x=pose.offset_x,
                    offset_y=pose.offset_y + nod,
                    rotation_degrees=pose.rotation_degrees,
                    scale_x=pose.scale_x,
                    scale_y=pose.scale_y - nod * 0.003,
                    shadow_scale=pose.shadow_scale,
                    shadow_opacity=pose.shadow_opacity,
                    decoration=pose.decoration,
                )

        floor = QPointF(widget.width() / 2.0, widget.height() - self.margin - 7.0)
        current_anchor = self._render_anchor(widget, snapshot.current)

        # Back particle layer (rings, background stars/fish) behind the character
        if particles is not None:
            particles.paint(painter, layer="back")

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
                rig_params=rig_params,
                form_id=form_id,
            )
        self._draw_layer(
            painter,
            snapshot.current,
            current_anchor,
            pose,
            snapshot.current_opacity,
            docked=dock_pose is not None,
            rig_params=rig_params,
            form_id=form_id,
        )

        # Floating ceramic bowl of dried fish (小鱼干碗) beside her shoulder
        if self._stash_show > 0.015 and dock_pose is None:
            pix_w = max(90.0, float(snapshot.current.frame.pixmap.width()))
            pix_h = max(120.0, float(snapshot.current.frame.pixmap.height()))
            bowl_scale = max(0.46, min(0.72, pix_h / 360.0))
            bowl_x = max(36.0, widget.width() / 2.0 - pix_w * 0.48 - 10.0)
            bowl_y = max(self.bubble_height + 28.0, floor.y() - pix_h * 0.56)
            draw_fish_stash(
                painter,
                x=bowl_x,
                y=bowl_y,
                level=self._stash_level,
                label=self._stash_label,
                show=self._stash_show,
                elapsed=self._visual_clock,
                scale=bowl_scale,
            )

        # Front particle layer (foreground hearts, sparkles, notes, steam, fish)
        if particles is not None:
            particles.paint(painter, layer="front")

        # Speech bubble always sits crisp on top of particles and sprite
        if bubble.visible:
            self._draw_bubble(
                painter,
                widget.width(),
                bubble,
                visible_x_range=visible_x_range,
                tail_x=tail_x,
            )

    def _render_anchor(self, widget, layer: RenderLayer) -> QPointF:
        """Keep non-standing actions inside the allocated sprite slot.

        Ground-anchored clips pivot at the feet. Dragging, falling and seated
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
        rig_params: RigParams | None = None,
        form_id: str = "carbon",
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
        use_rig = self.soft_rig_enabled and not self.reduced_motion and rig_params is not None
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
            if use_rig:
                u_img, u_px, u_py = self._deformer.deform(
                    under, rig_params, form_id=form_id, asset_id=layer.asset_id, mirrored=layer.mirrored
                )
                painter.drawImage(QPointF(-u_px, -u_py), u_img)
            else:
                painter.drawPixmap(0, 0, under)
            painter.setOpacity(max(0.0, min(1.0, opacity)) * self.expression[3])
        if use_rig:
            img, pad_x, pad_top = self._deformer.deform(
                pixmap, rig_params, form_id=form_id, asset_id=layer.asset_id, mirrored=layer.mirrored
            )
            painter.drawImage(QPointF(-pad_x, -pad_top), img)
        else:
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
        painter.setBrush(QColor(32, 24, 68, max(0, int(pose.shadow_opacity * 36))))
        painter.drawEllipse(QRectF(ground.x() - width / 2 - 1, ground.y() - height / 2 + 2, width + 2, height + 2))
        painter.setBrush(QColor(32, 24, 68, max(0, int(pose.shadow_opacity * 125))))
        painter.drawEllipse(QRectF(ground.x() - width / 2, ground.y() - height / 2 + 1, width, height))
        painter.restore()

    def _comic_border_color(self) -> QColor:
        c = QColor(self.speaker_accent)
        if not c.isValid():
            return QColor("#a78bfa")
        # Keep the 2px border vivid and readable on both bright white and dark desktops.
        if c.lightness() > 215 or c.saturation() < 35:
            return QColor("#a78bfa")
        return c

    def _draw_bubble(
        self,
        painter: QPainter,
        width: int,
        bubble: Bubble,
        *,
        visible_x_range: tuple[float, float] | None = None,
        tail_x: float | None = None,
    ) -> None:
        now = time.monotonic()
        opacity = 1.0 if self.reduced_motion and bubble.visible else bubble.opacity_at(now)
        if opacity <= 0:
            return
        font = QFont(self.bubble_font)
        is_ai = bubble.is_ai or bubble.text.lstrip().startswith("✦")
        if bubble.inner:
            font.setItalic(True)
            background = QColor(245, 242, 255, 250)
            foreground = QColor("#4c3b73")
            border_color = QColor("#b79cff")
        else:
            background = QColor(255, 253, 251, 252)
            foreground = QColor("#2a1b3d")
            border_color = self._comic_border_color()

        metrics = QFontMetrics(font)
        vis_left = 0.0
        vis_right = float(width)
        if visible_x_range is not None:
            vis_left = max(0.0, min(float(width), float(visible_x_range[0])))
            vis_right = max(vis_left, min(float(width), float(visible_x_range[1])))
        avail_w = max(92.0, vis_right - vis_left - 12.0)
        max_width = min(248, int(avail_w))
        full_lines = self._wrap_text(bubble.text, metrics, max(60, max_width - 28))
        if not full_lines:
            return
        shown_text = bubble.visible_text_at(now, reduced_motion=self.reduced_motion)
        remaining = len(shown_text)
        shown_lines: list[str] = []
        for line in full_lines:
            if remaining <= 0:
                break
            take = min(len(line), remaining)
            shown_lines.append(line[:take])
            remaining -= len(line)
        if not shown_lines:
            shown_lines = [full_lines[0][:1]]

        min_bubble_w = min(74, max_width)
        widest_line = max(metrics.horizontalAdvance(line) for line in full_lines)
        max_bubble_w = min(int(avail_w), max_width + 20)
        bubble_width = max(min_bubble_w, widest_line + 28)
        bubble_width = min(max_bubble_w, bubble_width)
        bubble_height = len(full_lines) * metrics.height() + 18
        center_x = width / 2.0 if tail_x is None else float(tail_x)
        bubble_x = center_x - bubble_width / 2.0
        min_bx = vis_left + 6.0
        max_bx = max(min_bx, vis_right - bubble_width - 6.0)
        bubble_x = max(min_bx, min(max_bx, bubble_x))
        # Anchor near the bottom of the bubble band so it hovers warmly right above her head.
        bubble_y = max(3.0, float(self.bubble_height) - bubble_height - 10.0)
        body = QRectF(bubble_x, bubble_y, bubble_width, bubble_height)

        clamped_tail_x = max(bubble_x + 18.0, min(bubble_x + bubble_width - 18.0, center_x))
        tail_y = bubble_y + bubble_height
        shape = QPainterPath()
        shape.addRoundedRect(body, 14.0, 14.0)
        tail = QPainterPath()
        tail.addPolygon(
            QPolygonF(
                [
                    QPointF(clamped_tail_x - 6.0, tail_y - 1.0),
                    QPointF(clamped_tail_x + 6.0, tail_y - 1.0),
                    QPointF(clamped_tail_x, tail_y + 7.0),
                ]
            )
        )
        unified = shape.united(tail)

        painter.save()
        painter.setOpacity(opacity)
        # Soft purple-tinted shadow keeps the cream comic card crisp over any wallpaper.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(46, 24, 104, 46))
        painter.drawPath(unified.translated(0.0, 3.0))

        painter.setBrush(background)
        pen_style = Qt.PenStyle.DashLine if bubble.inner else Qt.PenStyle.SolidLine
        painter.setPen(QPen(border_color, 2.0, pen_style, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(unified)

        painter.setFont(font)
        text_top = bubble_y + 9.0
        for index, line in enumerate(shown_lines):
            row_rect = QRectF(
                bubble_x + 14.0,
                text_top + index * metrics.height(),
                bubble_width - 28.0,
                metrics.height(),
            )
            if index == 0 and is_ai and line.startswith("✦"):
                mark_w = metrics.horizontalAdvance("✦")
                painter.setPen(QColor("#8b5cf6"))
                painter.drawText(row_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "✦")
                painter.setPen(foreground)
                rest_rect = QRectF(row_rect.left() + mark_w, row_rect.top(), row_rect.width() - mark_w, row_rect.height())
                painter.drawText(rest_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line[1:])
            else:
                painter.setPen(foreground)
                painter.drawText(row_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
        painter.restore()

    @staticmethod
    def _wrap_text(text: str, metrics: QFontMetrics, max_width: int) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9'’-]+|\s+|.", text)
        lines: list[str] = []
        current = ""
        for token in tokens:
            if not current and token.isspace():
                continue
            candidate = current + token
            if current and metrics.horizontalAdvance(candidate) > max_width:
                lines.append(current.rstrip())
                if token.isspace():
                    current = ""
                    continue
                if metrics.horizontalAdvance(token) > max_width:
                    # Single unbroken token wider than max_width: fall back to char split.
                    current = ""
                    for ch in token:
                        if current and metrics.horizontalAdvance(current + ch) > max_width:
                            lines.append(current)
                            current = ch
                        else:
                            current += ch
                else:
                    current = token
            else:
                current = candidate
        if current.strip():
            lines.append(current.rstrip())
        # Avoid a lone punctuation glyph dangling alone on a trailing line.
        if len(lines) >= 2 and len(lines[-1]) == 1 and lines[-1] in "～~！!。，,？?…":
            punct = lines[-1]
            prev = lines[-2]
            if metrics.horizontalAdvance(prev + punct) <= max_width + metrics.horizontalAdvance(punct) + 2:
                lines[-2] = prev + punct
                lines.pop()
            elif len(prev) >= 2:
                lines[-2] = prev[:-1]
                lines[-1] = prev[-1] + punct
        return lines[:3]
