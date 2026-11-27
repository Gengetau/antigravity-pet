"""Interactive floating vector-art desktop scene props for themed companion gatherings.

Renders four cozy, hand-crafted translucent desktop mini-scenes positioned between
the main pet (姐姐) and her clones:
- ``tea_party``: lace café round table + steaming pastel teapot, teacups & strawberry cake
- ``campfire_night``: warm glowing campfire + crossed logs, flickering flames & roasting marshmallows
- ``art_studio``: wooden A-frame easel with a live chibi portrait sketch of sister + paint palette
- ``cloud_nap``: plump pastel cloud cushion + starry blanket & crescent pillow with gentle Zzz wisps

Props support left-click interaction (refill tea / stoke fire / cycle portrait / tuck blanket)
and right-click early pack-up, with full reduced-motion safety.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from pet.particles import ParticleSystem

DESKTOP_SCENE_KINDS: tuple[str, ...] = (
    "tea_party",
    "campfire_night",
    "art_studio",
    "cloud_nap",
)


@dataclass(frozen=True, slots=True)
class ScenePropSpec:
    kind: str
    label: str
    tooltip: str
    click_particles: tuple[str, ...]
    ambient_particle: str
    click_lines: tuple[str, ...]


SCENE_SPECS: dict[str, ScenePropSpec] = {
    "tea_party": ScenePropSpec(
        kind="tea_party",
        label="下午茶会",
        tooltip="🫖 奶油下午茶会 · 左键续杯/切草莓蛋糕 · 右键收起茶桌",
        click_particles=("steam", "sparkles", "hearts"),
        ambient_particle="steam",
        click_lines=(
            "叮～续杯花果茶！",
            "切好草莓蛋糕啦～",
            "新烤司康端上桌！",
            "再倒一杯暖红茶～",
        ),
    ),
    "campfire_night": ScenePropSpec(
        kind="campfire_night",
        label="篝火夜话",
        tooltip="🏕️ 星空篝火夜话 · 左键添柴/烤棉花糖 · 右键熄火收起",
        click_particles=("sparkles", "steam", "hearts"),
        ambient_particle="sparkles",
        click_lines=(
            "咔嚓～添块暖柴！",
            "棉花糖烤金黄啦～",
            "火苗跳得好暖和！",
            "再烤一串甜棉花糖",
        ),
    ),
    "art_studio": ScenePropSpec(
        kind="art_studio",
        label="桌面小画室",
        tooltip="🎨 桌面小画室 · 左键换一幅姐姐肖像新作 · 右键收起画架",
        click_particles=("sparkles", "notes", "hearts"),
        ambient_particle="notes",
        click_lines=(
            "完成新肖像啦！",
            "换张画布继续画～",
            "加上闪亮星光边！",
            "这幅姐姐超可爱～",
        ),
    ),
    "cloud_nap": ScenePropSpec(
        kind="cloud_nap",
        label="云朵午睡窝",
        tooltip="☁️ 云朵午睡窝 · 左键盖星星小被/拍松云垫 · 右键收起云垫",
        click_particles=("sleep_z", "hearts", "sparkles"),
        ambient_particle="sleep_z",
        click_lines=(
            "轻轻盖上星星小被～",
            "云朵拍得软乎乎！",
            "暖暖的，好梦哦～",
            "再掖一下小被角～",
        ),
    ),
}


def pick_scene_for_hour(hour: int, rng: random.Random | None = None) -> str:
    """Pick a themed desktop scene weighted naturally by local time of day.

    - Afternoon (13..17): strongly favors ``tea_party``
    - Evening / late night (19..23, 0..4): strongly favors ``campfire_night`` & ``cloud_nap``
    - Morning / midday / dusk (5..12, 18): mixes ``art_studio``, ``cloud_nap``, ``tea_party``, ``campfire_night``
    """
    r = rng or random.Random()
    h = int(hour) % 24
    if 13 <= h <= 17:
        return r.choices(
            ("tea_party", "art_studio", "cloud_nap"),
            weights=(0.58, 0.22, 0.20),
            k=1,
        )[0]
    if h >= 19 or h <= 4:
        return r.choices(
            ("campfire_night", "cloud_nap", "tea_party"),
            weights=(0.60, 0.28, 0.12),
            k=1,
        )[0]
    return r.choices(
        ("art_studio", "cloud_nap", "tea_party", "campfire_night"),
        weights=(0.34, 0.30, 0.24, 0.12),
        k=1,
    )[0]


class DesktopScenePropWidget(QWidget):
    """Floating translucent interactive prop centerpiece for themed desktop mini-scenes."""

    BUBBLE_TOP_PAD = 28
    PROP_WIDTH = 188
    PROP_HEIGHT = 144

    def __init__(
        self,
        *,
        topmost: bool = True,
        on_click: Callable[[str], None] | None = None,
        on_dismiss: Callable[[], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if topmost:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("AGY 桌面互动场景道具")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFixedSize(self.PROP_WIDTH, self.PROP_HEIGHT)

        self._on_click = on_click
        self._on_dismiss = on_dismiss
        self._rng = rng or random.Random()
        self._particles = ParticleSystem(self._rng)
        self._kind: str = "tea_party"
        self._accent = QColor("#c084fc")
        self._hovered = False
        self._opacity = 1.0
        self._scale = 1.0
        self._phase = 0.0
        self._reduced_motion = False
        self._interact_count = 0
        self._pulse_until = 0.0
        self._bubble_text = ""
        self._bubble_until = 0.0
        self._next_ambient_at = 0.0

        self._bubble_font = QFont()
        self._bubble_font.setPointSize(8)
        self._bubble_font.setWeight(QFont.Weight.DemiBold)
        self._label_font = QFont()
        self._label_font.setPointSize(8)
        self._label_font.setWeight(QFont.Weight.Bold)

    @property
    def scene_kind(self) -> str:
        return self._kind

    @property
    def interact_count(self) -> int:
        return self._interact_count

    @property
    def bubble_text(self) -> str:
        return self._bubble_text

    @property
    def visual_size(self) -> tuple[int, int]:
        return (148, 98)

    def set_topmost(self, topmost: bool) -> None:
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(topmost))
        if was_visible:
            self.show()

    def configure(
        self,
        kind: str,
        *,
        accent: str = "#c084fc",
        now: float | None = None,
        reduced_motion: bool = False,
    ) -> None:
        spec = SCENE_SPECS.get(kind, SCENE_SPECS["tea_party"])
        self._kind = spec.kind
        self._accent = QColor(accent)
        self._reduced_motion = bool(reduced_motion)
        self._interact_count = 0
        self._pulse_until = 0.0
        self._bubble_text = ""
        self._bubble_until = 0.0
        ts = time.monotonic() if now is None else float(now)
        self._next_ambient_at = ts + 1.2
        self._particles.clear()
        self.setToolTip(spec.tooltip)
        self.update()

    def say(self, text: str, *, now: float | None = None, duration: float = 2.6) -> None:
        ts = time.monotonic() if now is None else float(now)
        self._bubble_text = str(text or "").strip()
        self._bubble_until = ts + max(0.8, float(duration))
        self.update()

    def trigger_interact(self, *, now: float | None = None) -> str:
        """Apply visual pulse, particle burst, and prop bubble on user click."""
        ts = time.monotonic() if now is None else float(now)
        spec = SCENE_SPECS.get(self._kind, SCENE_SPECS["tea_party"])
        self._interact_count += 1
        self._pulse_until = ts + 0.65
        line = spec.click_lines[(self._interact_count - 1) % len(spec.click_lines)]
        self.say(line, now=ts, duration=2.5)
        self._particles.reduced_motion = self._reduced_motion
        cx = self.width() * 0.5
        cy = self.BUBBLE_TOP_PAD + 44.0
        for pkind in spec.click_particles:
            self._particles.emit(pkind, origin_x=cx, origin_y=cy)
        self.update()
        return line

    def tick(
        self,
        dt: float,
        *,
        now: float,
        opacity: float = 1.0,
        scale: float = 1.0,
        reduced_motion: bool = False,
    ) -> None:
        self._reduced_motion = bool(reduced_motion)
        self._opacity = max(0.0, min(1.0, float(opacity)))
        self._scale = max(0.2, min(1.25, float(scale)))
        if not reduced_motion:
            self._phase += max(0.0, dt) * 2.8
        if self._bubble_text and now >= self._bubble_until:
            self._bubble_text = ""
        if not reduced_motion and self._next_ambient_at > 0 and now >= self._next_ambient_at:
            self._next_ambient_at = now + self._rng.uniform(2.0, 3.6)
            spec = SCENE_SPECS.get(self._kind, SCENE_SPECS["tea_party"])
            self._particles.reduced_motion = False
            self._particles.emit(
                spec.ambient_particle,
                origin_x=self.width() * 0.5,
                origin_y=self.BUBBLE_TOP_PAD + 38.0,
            )
        self._particles.reduced_motion = self._reduced_motion
        if self._particles.active:
            self._particles.update(dt)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._on_click is not None:
                self._on_click(self._kind)
            else:
                self.trigger_interact()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            if self._on_dismiss is not None:
                self._on_dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacity)

        now = time.monotonic()
        pulse_boost = 1.0
        if not self._reduced_motion and now < self._pulse_until:
            rem = max(0.0, (self._pulse_until - now) / 0.65)
            pulse_boost = 1.0 + math.sin(rem * math.pi) * 0.11
        elif self._hovered and not self._reduced_motion:
            pulse_boost = 1.04

        draw_scale = self._scale * pulse_boost
        cx = self.width() * 0.5
        base_y = self.height() - 16.0

        painter.save()
        painter.translate(cx, base_y)
        painter.scale(draw_scale, draw_scale)
        painter.translate(-cx, -base_y)

        if self._kind == "tea_party":
            self._paint_tea_party(painter, cx, base_y)
        elif self._kind == "campfire_night":
            self._paint_campfire(painter, cx, base_y, flared=(now < self._pulse_until))
        elif self._kind == "art_studio":
            self._paint_art_studio(painter, cx, base_y)
        else:
            self._paint_cloud_nap(painter, cx, base_y)

        painter.restore()

        # Paint particles above the prop
        if self._particles.active:
            self._particles.paint(painter)

        # Mini caption pill on hover or active interaction bubble
        if self._bubble_text:
            self._paint_bubble(painter, self._bubble_text)
        elif self._hovered:
            spec = SCENE_SPECS.get(self._kind, SCENE_SPECS["tea_party"])
            self._paint_bubble(painter, f"{spec.label} · 点我互动")

    def _paint_bubble(self, painter: QPainter, text: str) -> None:
        painter.save()
        painter.setFont(self._bubble_font)
        fm = QFontMetrics(self._bubble_font)
        max_text_w = self.width() - 18
        shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, max_text_w)
        tw = fm.horizontalAdvance(shown)
        bw = min(self.width() - 6, tw + 16)
        bh = 22
        bx = (self.width() - bw) / 2.0
        by = 3.0
        rect = QRectF(bx, by, bw, bh)
        painter.setPen(QPen(QColor(214, 186, 170, 225), 1.4))
        painter.setBrush(QColor(255, 250, 244, 242))
        painter.drawRoundedRect(rect, 10.5, 10.5)
        painter.setPen(QColor(82, 58, 66))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, shown)
        painter.restore()

    def _paint_tea_party(self, painter: QPainter, cx: float, base_y: float) -> None:
        # Ground shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(92, 68, 76, 36))
        painter.drawEllipse(QPointF(cx, base_y + 2), 54, 10)

        # Wooden café table legs
        leg_pen = QPen(QColor("#b8825d"), 4.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(leg_pen)
        painter.drawLine(QPointF(cx - 28, base_y - 34), QPointF(cx - 34, base_y))
        painter.drawLine(QPointF(cx + 28, base_y - 34), QPointF(cx + 34, base_y))
        painter.drawLine(QPointF(cx, base_y - 32), QPointF(cx, base_y - 2))

        # Scalloped cream lace tablecloth
        cloth_y = base_y - 44
        cloth = QPainterPath()
        cloth.moveTo(cx - 52, cloth_y)
        cloth.lineTo(cx + 52, cloth_y)
        cloth.lineTo(cx + 50, cloth_y + 18)
        for i in range(6):
            sx = cx + 50 - i * 16.6
            cloth.quadTo(sx - 8.3, cloth_y + 26, sx - 16.6, cloth_y + 18)
        cloth.closeSubpath()
        painter.setPen(QPen(QColor("#e5b9a8"), 1.6))
        painter.setBrush(QColor("#fff8f1"))
        painter.drawPath(cloth)

        # Tabletop oval
        table_rect = QRectF(cx - 54, cloth_y - 10, 108, 22)
        grad = QLinearGradient(table_rect.topLeft(), table_rect.bottomLeft())
        grad.setColorAt(0.0, QColor("#fffdf9"))
        grad.setColorAt(1.0, QColor("#fceae1"))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor("#e4b3a0"), 1.6))
        painter.drawEllipse(table_rect)

        # Pastel teapot (left-center)
        pot_cx, pot_cy = cx - 16, cloth_y - 13
        # Spout & handle
        painter.setPen(QPen(QColor("#d97f9f"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(pot_cx - 24, pot_cy - 6, 15, 16), 90 * 16, 180 * 16)
        spout = QPainterPath()
        spout.moveTo(pot_cx + 12, pot_cy + 1)
        spout.quadTo(pot_cx + 22, pot_cy - 3, pot_cx + 24, pot_cy - 11)
        painter.drawPath(spout)
        # Body
        painter.setPen(QPen(QColor("#d97f9f"), 1.6))
        painter.setBrush(QColor("#ffd8e6"))
        painter.drawEllipse(QPointF(pot_cx, pot_cy), 15, 12.5)
        # Lid & golden knob
        painter.setBrush(QColor("#fff0f6"))
        painter.drawEllipse(QPointF(pot_cx, pot_cy - 11), 9, 4)
        painter.setBrush(QColor("#f5c25b"))
        painter.setPen(QPen(QColor("#c89331"), 1.2))
        painter.drawEllipse(QPointF(pot_cx, pot_cy - 15.5), 3.0, 3.0)

        # Animated gentle steam curls above teapot
        steam_shift = 0.0 if self._reduced_motion else math.sin(self._phase * 1.4) * 2.5
        painter.setPen(QPen(QColor(255, 255, 255, 195), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for dx, h_off in ((22, 0.0), (16, 4.0)):
            sp = QPainterPath()
            sx = pot_cx + dx
            sy = pot_cy - 16 - h_off
            sp.moveTo(sx, sy)
            sp.cubicTo(sx - 4 + steam_shift, sy - 7, sx + 5 - steam_shift, sy - 13, sx + steam_shift * 0.5, sy - 20)
            painter.drawPath(sp)

        # Strawberry shortcake on saucer (right-center)
        cake_cx, cake_cy = cx + 22, cloth_y - 6
        painter.setPen(QPen(QColor("#dec0b1"), 1.3))
        painter.setBrush(QColor("#fffdfa"))
        painter.drawEllipse(QPointF(cake_cx, cake_cy + 3), 17, 5.5)
        # Cake base
        painter.setPen(QPen(QColor("#d8a679"), 1.4))
        painter.setBrush(QColor("#ffe9bf"))
        painter.drawRoundedRect(QRectF(cake_cx - 11, cake_cy - 11, 22, 14), 4, 4)
        # Strawberry jam stripe + whipped cream top
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f78ca2"))
        painter.drawRect(QRectF(cake_cx - 10, cake_cy - 4, 20, 3))
        painter.setBrush(QColor("#fffdf9"))
        painter.drawRoundedRect(QRectF(cake_cx - 12, cake_cy - 14, 24, 6), 3, 3)
        # Red strawberry on top
        painter.setPen(QPen(QColor("#c93855"), 1.2))
        painter.setBrush(QColor("#ff5978"))
        painter.drawEllipse(QPointF(cake_cx, cake_cy - 17), 4.6, 5.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#52b768"))
        painter.drawEllipse(QPointF(cake_cx, cake_cy - 21.5), 3.8, 1.8)

        # Two miniature pastel teacups (front-left & front-right)
        for cup_x, cup_color in ((cx - 34, "#dff4ff"), (cx + 4, "#efe3ff")):
            cup_y = cloth_y + 1
            painter.setPen(QPen(QColor("#c7a6b6"), 1.2))
            painter.setBrush(QColor("#fffefe"))
            painter.drawEllipse(QPointF(cup_x, cup_y + 3), 8.5, 3.0)
            painter.setBrush(QColor(cup_color))
            painter.drawRoundedRect(QRectF(cup_x - 5.5, cup_y - 4.5, 11, 8), 3.5, 3.5)
            # Tea liquid gleam
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e89f6b"))
            painter.drawEllipse(QPointF(cup_x, cup_y - 3.0), 4.0, 1.5)

        # Extra macaron gift after user interacts!
        if self._interact_count > 0:
            mx, my = cx + 41, cloth_y + 2
            painter.setPen(QPen(QColor("#d98fb3"), 1.2))
            painter.setBrush(QColor("#ffc2dc"))
            painter.drawRoundedRect(QRectF(mx - 6, my - 5, 12, 7), 3.5, 3.5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#fff8f0"))
            painter.drawRect(QRectF(mx - 5, my - 2, 10, 1.8))

    def _paint_campfire(self, painter: QPainter, cx: float, base_y: float, *, flared: bool) -> None:
        flicker = 0.0 if self._reduced_motion else math.sin(self._phase * 2.6)
        glow_r = (66.0 if flared else 56.0) + flicker * 4.0

        # Warm glowing campfire halo
        glow = QRadialGradient(QPointF(cx, base_y - 24), glow_r)
        glow.setColorAt(0.0, QColor(255, 198, 92, 145 if flared else 110))
        glow.setColorAt(0.55, QColor(255, 126, 58, 52 if flared else 36))
        glow.setColorAt(1.0, QColor(255, 126, 58, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, base_y - 24), glow_r, glow_r * 0.72)

        # Ground shadow
        painter.setBrush(QColor(56, 36, 32, 48))
        painter.drawEllipse(QPointF(cx, base_y + 2), 48, 10)

        # Ring of cute smooth pebbles
        painter.setPen(QPen(QColor("#75687a"), 1.3))
        for dx, dy, rx, ry, col in (
            (-34, -2, 9, 5.5, "#b7adc0"),
            (-18, 3, 10, 5.8, "#c8bed0"),
            (0, 5, 10.5, 6.0, "#b1a6bc"),
            (19, 3, 10, 5.6, "#c8bed0"),
            (34, -2, 9, 5.2, "#a99db5"),
        ):
            painter.setBrush(QColor(col))
            painter.drawEllipse(QPointF(cx + dx, base_y + dy), rx, ry)

        # Crossed firewood logs
        for angle, col in ((-18, "#8c5737"), (18, "#74452b")):
            painter.save()
            painter.translate(cx, base_y - 8)
            painter.rotate(angle)
            painter.setPen(QPen(QColor("#522f1c"), 1.5))
            painter.setBrush(QColor(col))
            painter.drawRoundedRect(QRectF(-28, -5.5, 56, 11), 5, 5)
            painter.setBrush(QColor("#d9a97c"))
            painter.drawEllipse(QPointF(26, 0), 3.2, 4.6)
            painter.restore()

        # Layered animated 3-tongue dancing flame
        flame_h = (52.0 if flared else 44.0) + flicker * 3.5
        sway = 0.0 if self._reduced_motion else math.sin(self._phase * 2.1) * 3.0

        def flame_path(w: float, h: float, dx: float) -> QPainterPath:
            p = QPainterPath()
            p.moveTo(cx + dx - w, base_y - 10)
            p.cubicTo(cx + dx - w * 1.1, base_y - 10 - h * 0.55, cx + dx - w * 0.2, base_y - 10 - h * 0.85, cx + dx + sway, base_y - 10 - h)
            p.cubicTo(cx + dx + w * 0.3, base_y - 10 - h * 0.78, cx + dx + w * 1.1, base_y - 10 - h * 0.48, cx + dx + w, base_y - 10)
            p.closeSubpath()
            return p

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff6f3c"))
        painter.drawPath(flame_path(21, flame_h, 0))
        painter.setBrush(QColor("#ffba3b"))
        painter.drawPath(flame_path(14, flame_h * 0.74, -1.5))
        painter.setBrush(QColor("#fff3c4"))
        painter.drawPath(flame_path(7.5, flame_h * 0.45, 0.5))

        # Two grounded wooden Y-branch roasting stands staked beside the fire holding golden marshmallows!
        for side in (-1, 1):
            base_x = cx + side * 52
            fork_x = cx + side * 44
            fork_y = base_y - 28
            tip_x = cx + side * 24
            tip_y = base_y - 34
            painter.setPen(QPen(QColor("#6e462c"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(base_x, base_y + 1), QPointF(fork_x, fork_y))
            painter.drawLine(QPointF(fork_x, fork_y), QPointF(fork_x + side * 5, fork_y - 6))
            painter.setPen(QPen(QColor("#9c6d49"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(base_x + side * 8, base_y - 20), QPointF(tip_x, tip_y))
            painter.save()
            painter.translate(tip_x, tip_y)
            painter.rotate(side * -14)
            painter.setPen(QPen(QColor("#cfa382"), 1.3))
            painter.setBrush(QColor("#fff7e8" if self._interact_count == 0 else "#ffe0b2"))
            painter.drawRoundedRect(QRectF(-6.5, -5.0, 13, 10), 4, 4)
            painter.restore()
            painter.setPen(QPen(QColor("#c79388"), 1.3))
            painter.setBrush(QColor("#fde2d6" if side < 0 else "#e4eafc"))
            painter.drawRoundedRect(QRectF(cx + side * 66 - 11, base_y - 6, 22, 9), 4.5, 4.5)

        # Twinkling starry sparks above
        painter.setPen(Qt.PenStyle.NoPen)
        for sx, sy, r in ((-26, -64, 2.4), (24, -68, 2.8), (4, -76, 2.2)):
            alpha = 180 if self._reduced_motion else int(150 + 95 * math.sin(self._phase * 2.0 + sx))
            painter.setBrush(QColor(255, 232, 148, max(60, min(255, alpha))))
            painter.drawEllipse(QPointF(cx + sx, base_y + sy), r, r)

    def _paint_art_studio(self, painter: QPainter, cx: float, base_y: float) -> None:
        # Ground shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(86, 68, 88, 34))
        painter.drawEllipse(QPointF(cx, base_y + 2), 52, 10)

        # Honey-wood A-frame artist easel legs
        wood = QColor("#c68f5c")
        wood_dark = QColor("#8f5f35")
        painter.setPen(QPen(wood_dark, 5.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(cx - 2, base_y - 82), QPointF(cx - 28, base_y))
        painter.drawLine(QPointF(cx + 2, base_y - 82), QPointF(cx + 28, base_y))
        painter.drawLine(QPointF(cx, base_y - 82), QPointF(cx, base_y - 5))
        painter.setPen(QPen(wood, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(cx - 2, base_y - 82), QPointF(cx - 28, base_y))
        painter.drawLine(QPointF(cx + 2, base_y - 82), QPointF(cx + 28, base_y))

        # Canvas board
        canvas = QRectF(cx - 32, base_y - 76, 64, 52)
        painter.setPen(QPen(QColor("#b88252"), 2.4))
        painter.setBrush(QColor("#fffdf8"))
        painter.drawRoundedRect(canvas, 5, 5)

        # Easel ledge
        painter.setPen(QPen(wood_dark, 1.5))
        painter.setBrush(wood)
        painter.drawRoundedRect(QRectF(cx - 36, base_y - 26, 72, 6.5), 3, 3)

        # Live cute chibi portrait sketch of sister on the canvas! (cycles 4 variants on click)
        variant = self._interact_count % 4
        px, py = cx, base_y - 49
        tint = QColor(self._accent)
        tint.setAlpha(215)
        # Cute hair silhouette + cat ears
        painter.setPen(QPen(tint.darker(125), 1.4))
        painter.setBrush(tint)
        painter.drawEllipse(QPointF(px, py - 2), 14.5, 13.0)
        for side in (-1, 1):
            ear = QPainterPath()
            ear.moveTo(px + side * 12, py - 8)
            ear.lineTo(px + side * 14, py - 19)
            ear.lineTo(px + side * 4, py - 13)
            ear.closeSubpath()
            painter.drawPath(ear)
        # Chibi face
        painter.setPen(QPen(QColor("#a87d76"), 1.1))
        painter.setBrush(QColor("#fff2ea"))
        painter.drawEllipse(QPointF(px, py + 1), 10.5, 9.2)
        # Eyes + blush + expression per variant
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ff9fb2"))
        painter.drawEllipse(QPointF(px - 6.5, py + 3.2), 2.3, 1.3)
        painter.drawEllipse(QPointF(px + 6.5, py + 3.2), 2.3, 1.3)
        painter.setBrush(QColor("#4a3642"))
        if variant == 1:
            # Playful wink!
            painter.drawEllipse(QPointF(px - 4.2, py + 0.5), 1.7, 2.0)
            painter.setPen(QPen(QColor("#4a3642"), 1.4))
            painter.drawLine(QPointF(px + 2.4, py + 0.5), QPointF(px + 6.0, py + 0.5))
        else:
            painter.drawEllipse(QPointF(px - 4.2, py + 0.5), 1.7, 2.0)
            painter.drawEllipse(QPointF(px + 4.2, py + 0.5), 1.7, 2.0)
        # Cute smile
        painter.setPen(QPen(QColor("#7d4f5b"), 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(px - 3, py + 2.5, 6, 4.5), 200 * 16, 140 * 16)
        # Extra doodle per variant (crown / star / heart)
        if variant == 2:
            painter.setPen(QPen(QColor("#d49b2a"), 1.2))
            painter.setBrush(QColor("#ffd859"))
            crown = QPainterPath()
            crown.moveTo(px - 7, py - 14)
            crown.lineTo(px - 5, py - 21)
            crown.lineTo(px, py - 16)
            crown.lineTo(px + 5, py - 21)
            crown.lineTo(px + 7, py - 14)
            crown.closeSubpath()
            painter.drawPath(crown)
        elif variant == 3:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ff6b93"))
            painter.drawEllipse(QPointF(px + 18, py - 12), 3.4, 3.4)
            painter.drawEllipse(QPointF(px + 22, py - 12), 3.4, 3.4)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ffd35a"))
            painter.drawEllipse(QPointF(px + 20, py - 13), 2.8, 2.8)

        # Wooden paint palette + colorful paint dots at bottom-right
        pal_cx, pal_cy = cx + 38, base_y - 7
        painter.setPen(QPen(QColor("#9f6f44"), 1.4))
        painter.setBrush(QColor("#edd0a8"))
        painter.drawEllipse(QPointF(pal_cx, pal_cy), 16, 10.5)
        painter.setPen(Qt.PenStyle.NoPen)
        for dx, dy, col in (
            (-7, -3, "#ff7aa2"),
            (-1, -5, "#ffd452"),
            (6, -3, "#60c4ff"),
            (4, 3, "#b784ff"),
        ):
            painter.setBrush(QColor(col))
            painter.drawEllipse(QPointF(pal_cx + dx, pal_cy + dy), 2.8, 2.3)

    def _paint_cloud_nap(self, painter: QPainter, cx: float, base_y: float) -> None:
        breath = 0.0 if self._reduced_motion else math.sin(self._phase * 1.1) * 1.4

        # Ground shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(110, 102, 146, 36))
        painter.drawEllipse(QPointF(cx, base_y + 3), 72, 11)

        # Plump multi-puff pastel cloud cushion built with true boolean union (zero hollow inner arcs!)
        cloud_y = base_y - 22 + breath * 0.45
        cloud = QPainterPath()
        cloud.setFillRule(Qt.FillRule.WindingFill)
        cloud.addRoundedRect(QRectF(cx - 66, cloud_y - 6, 132, 32), 16, 16)
        for dx, dy, rx, ry in (
            (-46, -8, 24, 18),
            (-18, -17, 29, 23),
            (18, -16, 28, 22),
            (47, -8, 23, 17),
        ):
            puff = QPainterPath()
            puff.addEllipse(QPointF(cx + dx, cloud_y + dy), rx, ry)
            cloud = cloud.united(puff)

        # Pass 1: clean outer cloud outline; Pass 2: seamless solid creamy gradient fill
        painter.setPen(QPen(QColor("#c7bce8"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(cloud)

        grad = QLinearGradient(QPointF(cx, cloud_y - 38), QPointF(cx, base_y + 4))
        grad.setColorAt(0.0, QColor("#ffffff"))
        grad.setColorAt(0.68, QColor("#f7f4ff"))
        grad.setColorAt(1.0, QColor("#e3ddf8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawPath(cloud)

        # Soft rosy inner highlight puffs
        painter.setBrush(QColor(255, 255, 255, 175))
        painter.drawEllipse(QPointF(cx - 18, cloud_y - 22), 14, 7)
        painter.drawEllipse(QPointF(cx + 18, cloud_y - 20), 13, 6)

        # Cozy pastel starry blanket draped across the cloud (tucks wider when clicked!)
        blanket_w = 72 if self._interact_count > 0 else 56
        blanket = QPainterPath()
        blanket.moveTo(cx - blanket_w * 0.45, cloud_y - 6)
        blanket.quadTo(cx + 4, cloud_y - 15, cx + blanket_w * 0.55, cloud_y - 4)
        blanket.lineTo(cx + blanket_w * 0.60, cloud_y + 21)
        blanket.quadTo(cx + 4, cloud_y + 27, cx - blanket_w * 0.42, cloud_y + 19)
        blanket.closeSubpath()
        painter.setPen(QPen(QColor("#e7a8c2"), 1.5))
        painter.setBrush(QColor("#ffe3ef"))
        painter.drawPath(blanket)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f5c25b"))
        for sx, sy in ((-10, 4), (6, 0), (0, 13), (18, 8), (24, 15)):
            painter.drawEllipse(QPointF(cx + sx, cloud_y + sy), 2.4, 2.4)

        # Cute butter-yellow crescent moon pillow on left + pastel mint mini pillow on right
        moon_cx, moon_cy = cx - 42, cloud_y - 1
        painter.setPen(QPen(QColor("#d9ad52"), 1.3))
        painter.setBrush(QColor("#ffe79a"))
        painter.drawEllipse(QPointF(moon_cx, moon_cy), 11.5, 11.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f7f4ff"))
        painter.drawEllipse(QPointF(moon_cx + 5.0, moon_cy - 2.2), 8.8, 8.8)

        painter.setPen(QPen(QColor("#a5c9d8"), 1.2))
        painter.setBrush(QColor("#dff5ff"))
        painter.drawRoundedRect(QRectF(cx + 36, cloud_y - 6, 18, 12), 5, 5)

        # Floating soft lavender Zzz glyphs above
        painter.setFont(self._label_font)
        z_drift = 0.0 if self._reduced_motion else math.sin(self._phase * 1.2) * 3.0
        for idx, (zx, zy, ch) in enumerate(((-10, -44, "z"), (4, -56, "Z"), (19, -67, "Z"))):
            painter.setPen(QColor(148, 132, 206, 210 - idx * 25))
            painter.drawText(QPointF(cx + zx + z_drift * (idx + 1) * 0.35, cloud_y + zy), ch)
