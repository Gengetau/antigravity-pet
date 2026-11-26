"""Illustration-grade QPainter vector particles and dried-fish quota bowl."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

OUTLINE_COLOR = QColor("#2f2a6e")
PASTEL_PALETTE = (
    QColor("#b79cff"),
    QColor("#8fd8ff"),
    QColor("#ffb3d9"),
    QColor("#ffe08a"),
    QColor("#d4c4ff"),
    QColor("#a8f0e4"),
)


def draw_dried_fish(
    painter: QPainter,
    x: float,
    y: float,
    length: float,
    angle_deg: float = 0.0,
    *,
    flip: bool = False,
) -> None:
    """Draw one curled silver-back, warm-belly dried fish (小鱼干) with ink outline."""

    k = max(0.05, length / 62.0)
    painter.save()
    painter.translate(x, y)
    if angle_deg:
        painter.rotate(angle_deg)
    painter.scale(-k if flip else k, k)

    body = QPainterPath()
    body.moveTo(-31.0, 2.0)
    body.cubicTo(-25.0, -10.0, -6.0, -13.0, 10.0, -7.0)
    body.quadTo(16.0, -4.5, 20.0, -2.0)
    body.quadTo(26.0, -7.0, 33.0, -11.0)
    body.quadTo(29.0, -1.0, 33.0, 8.0)
    body.quadTo(25.0, 5.0, 20.0, 2.0)
    body.quadTo(14.0, 6.0, 8.0, 7.5)
    body.cubicTo(-8.0, 11.5, -24.0, 10.0, -31.0, 2.0)
    body.closeSubpath()

    skin = QLinearGradient(0.0, -12.0, 0.0, 11.0)
    skin.setColorAt(0.0, QColor("#7d86bd"))
    skin.setColorAt(0.42, QColor("#c9cee8"))
    skin.setColorAt(0.72, QColor("#f7e6bf"))
    skin.setColorAt(1.0, QColor("#e8b877"))

    painter.setBrush(skin)
    painter.setPen(QPen(OUTLINE_COLOR, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPath(body)

    # Dorsal shine + gill curve clipped inside fish body
    painter.save()
    painter.setClipPath(body)
    shine = QPainterPath()
    shine.moveTo(-14.0, -6.0)
    shine.quadTo(0.0, -9.0, 10.0, -4.5)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 195), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPath(shine)

    gill = QPainterPath()
    gill.moveTo(-16.0, -6.0)
    gill.quadTo(-12.0, 0.0, -15.0, 7.0)
    painter.setPen(QPen(QColor(47, 42, 110, 128), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPath(gill)
    painter.restore()

    # Crisp outlined eye
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(QPen(OUTLINE_COLOR, 1.4))
    painter.drawEllipse(QPointF(-22.5, -1.0), 3.6, 3.6)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(OUTLINE_COLOR)
    painter.drawEllipse(QPointF(-22.8, -0.8), 1.9, 1.9)
    painter.restore()


def draw_fishbone(painter: QPainter, x: float, y: float) -> None:
    """All that remains when the dried-fish quota hits 0%."""

    painter.save()
    painter.translate(x, y)
    painter.rotate(-4.5)
    for width, color in ((4.4, OUTLINE_COLOR), (2.0, QColor("#f2eeff"))):
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(-16.0, 0.0), QPointF(17.0, 0.0))
        for rib in (-8.0, -1.0, 6.0):
            painter.drawLine(QPointF(rib + 2.0, -6.0), QPointF(rib - 1.0, 6.0))
        painter.drawLine(QPointF(17.0, 0.0), QPointF(23.0, -5.0))
        painter.drawLine(QPointF(17.0, 0.0), QPointF(23.0, 5.0))

    head = QPainterPath()
    head.moveTo(-24.0, 0.0)
    head.quadTo(-20.0, -7.0, -14.0, -3.0)
    head.lineTo(-14.0, 3.0)
    head.quadTo(-20.0, 7.0, -24.0, 0.0)
    head.closeSubpath()
    painter.setBrush(QColor("#f2eeff"))
    painter.setPen(QPen(OUTLINE_COLOR, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPath(head)
    painter.restore()


_STASH_PILE: tuple[tuple[float, float, float, float], ...] = (
    (-27.0, -8.0, 18.0, 0.90),
    (-6.0, -12.0, -11.5, 1.00),
    (17.0, -8.0, 8.0, 0.95),
    (32.0, -6.0, -26.0, 0.80),
    (-17.0, -21.0, -24.0, 0.95),
    (7.0, -24.0, 17.0, 1.00),
    (25.0, -19.0, -11.5, 0.88),
    (-5.0, -34.0, 28.5, 0.92),
    (13.0, -36.0, -20.5, 0.86),
)


def draw_fish_stash(
    painter: QPainter,
    *,
    x: float,
    y: float,
    level: float,
    label: str = "",
    show: float = 1.0,
    elapsed: float = 0.0,
    scale: float = 0.62,
) -> None:
    """Draw a floating ceramic bowl filled with dried fish proportional to quota."""

    vis = max(0.0, min(1.0, float(show)))
    if vis <= 0.01:
        return
    lvl = max(0.0, min(1.0, float(level)))
    pop = vis * (1.0 + 0.14 * math.sin(vis * math.pi)) * max(0.25, float(scale))

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setOpacity(painter.opacity() * min(1.0, vis * 1.4))
    painter.translate(x + math.sin(elapsed * 1.1) * 3.0, y + math.sin(elapsed * 1.7) * 4.5)
    painter.rotate(math.sin(elapsed * 0.9) * 2.3)
    painter.scale(pop, pop)

    # Inside of the ceramic bowl
    inside = QLinearGradient(0.0, -15.0, 0.0, 11.0)
    inside.setColorAt(0.0, QColor("#574a9c"))
    inside.setColorAt(1.0, QColor("#8a78d4"))
    painter.setBrush(inside)
    painter.setPen(QPen(OUTLINE_COLOR, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawEllipse(QPointF(0.0, -2.0), 47.0, 13.0)

    count = 0 if lvl <= 0.001 else max(1, math.ceil(lvl * len(_STASH_PILE)))
    if count == 0:
        draw_fishbone(painter, 2.0, -3.0)
    else:
        for idx in range(count - 1, -1, -1):
            fx, fy, fang, fsize = _STASH_PILE[idx]
            draw_dried_fish(
                painter,
                fx,
                fy + math.sin(elapsed * 2.0 + idx) * 0.5,
                52.0 * fsize,
                fang,
                flip=(idx % 2 == 0),
            )

    # Front wall of the bowl hides the bottom of the fish pile
    wall = QPainterPath()
    wall.moveTo(-47.0, -2.0)
    wall.cubicTo(-44.0, 8.0, -44.0, 22.0, -30.0, 31.0)
    wall.quadTo(0.0, 37.0, 30.0, 31.0)
    wall.cubicTo(44.0, 22.0, 44.0, 8.0, 47.0, -2.0)
    wall.cubicTo(30.0, 16.0, -30.0, 16.0, -47.0, -2.0)
    wall.closeSubpath()

    wall_grad = QLinearGradient(0.0, -2.0, 0.0, 36.0)
    wall_grad.setColorAt(0.0, QColor("#fbf8ff"))
    wall_grad.setColorAt(0.55, QColor("#d9cdfb"))
    wall_grad.setColorAt(1.0, QColor("#a896ee"))
    painter.setBrush(wall_grad)
    painter.setPen(QPen(OUTLINE_COLOR, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPath(wall)

    # Ceramic specular shine
    shine = QPainterPath()
    shine.moveTo(-36.0, 11.0)
    shine.quadTo(-30.0, 20.0, -21.0, 25.0)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 230), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPath(shine)

    if label:
        font = QFont()
        font.setPixelSize(16)
        font.setWeight(QFont.Weight.Bold)
        text_path = QPainterPath()
        text_path.addText(0.0, 0.0, font, label)
        bounds = text_path.boundingRect()
        painter.save()
        painter.translate(-bounds.center().x() + 1.0, 21.0 - bounds.center().y())
        painter.setPen(QPen(QColor(255, 255, 255, 220), 3.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(text_path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(OUTLINE_COLOR)
        painter.drawPath(text_path)
        painter.restore()

    painter.restore()


@dataclass(slots=True)
class Particle:
    kind: str  # sparkle / confetti / heart / sweat / fish / ring / orb / note / z / puff
    x: float
    y: float
    vx: float
    vy: float
    size: float
    age: float
    lifetime: float
    color: QColor
    rotation: float = 0.0
    vrot: float = 0.0
    gravity: float = 0.0
    front: bool = True
    wobble: float = 0.0
    phase: float = 0.0
    drag: float = 0.0
    text: str = ""
    flip: bool = False


class ParticleSystem:
    """Two-layer (back/front) illustration-grade procedural particles."""

    MAX_PARTICLES = 96

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.particles: list[Particle] = []
        self.enabled = True
        self.reduced_motion = False
        self._elapsed = 0.0

    @property
    def active(self) -> bool:
        return bool(self.particles)

    def clear(self) -> None:
        self.particles.clear()

    def emit(self, effect: str, *, origin_x: float, origin_y: float, spread_w: float = 92.0) -> int:
        if not self.enabled or self.reduced_motion or not effect:
            return 0
        kind = str(effect).strip().lower()
        before = len(self.particles)
        r = self.rng

        if kind == "sparkles":
            for idx in range(12):
                self.particles.append(
                    Particle(
                        kind="sparkle",
                        x=origin_x + r.uniform(-spread_w * 0.58, spread_w * 0.58),
                        y=origin_y + r.uniform(-28.0, 28.0),
                        vx=r.uniform(-18.0, 18.0),
                        vy=r.uniform(-52.0, -18.0),
                        size=r.uniform(7.0, 13.0),
                        age=0.0,
                        lifetime=r.uniform(0.75, 1.35),
                        color=r.choice(PASTEL_PALETTE),
                        rotation=r.uniform(0.0, 90.0),
                        vrot=r.uniform(-95.0, 95.0),
                        front=(idx % 3 != 0),
                    )
                )
        elif kind == "confetti":
            for idx in range(20):
                self.particles.append(
                    Particle(
                        kind="confetti",
                        x=origin_x + r.uniform(-spread_w * 0.48, spread_w * 0.48),
                        y=origin_y + r.uniform(-22.0, 10.0),
                        vx=r.uniform(-92.0, 92.0),
                        vy=r.uniform(-148.0, -52.0),
                        size=r.uniform(6.0, 10.0),
                        age=0.0,
                        lifetime=r.uniform(1.05, 1.75),
                        color=r.choice(PASTEL_PALETTE),
                        rotation=r.uniform(0.0, 360.0),
                        vrot=r.uniform(-280.0, 280.0),
                        gravity=205.0,
                        drag=0.65,
                        front=(idx % 3 != 0),
                    )
                )
            for idx in range(6):
                self.particles.append(
                    Particle(
                        kind="sparkle",
                        x=origin_x + r.uniform(-spread_w * 0.5, spread_w * 0.5),
                        y=origin_y + r.uniform(-24.0, 12.0),
                        vx=r.uniform(-65.0, 65.0),
                        vy=r.uniform(-110.0, -35.0),
                        size=r.uniform(8.0, 13.5),
                        age=0.0,
                        lifetime=r.uniform(0.85, 1.35),
                        color=r.choice(PASTEL_PALETTE),
                        rotation=r.uniform(0.0, 90.0),
                        vrot=r.uniform(-120.0, 120.0),
                        gravity=85.0,
                        drag=0.8,
                        front=(idx % 2 == 0),
                    )
                )
        elif kind == "hearts":
            palette = (QColor("#fb7199"), QColor("#f43f5e"), QColor("#f472b6"))
            for idx in range(7):
                self.particles.append(
                    Particle(
                        kind="heart",
                        x=origin_x + r.uniform(-spread_w * 0.42, spread_w * 0.42),
                        y=origin_y + r.uniform(-18.0, 12.0),
                        vx=r.uniform(-14.0, 14.0),
                        vy=r.uniform(-58.0, -28.0),
                        size=r.uniform(9.5, 14.5),
                        age=0.0,
                        lifetime=r.uniform(1.0, 1.6),
                        color=r.choice(palette),
                        wobble=22.0,
                        phase=r.uniform(0.0, math.tau),
                        front=(idx % 4 != 0),
                    )
                )
        elif kind == "sweat":
            for _ in range(5):
                self.particles.append(
                    Particle(
                        kind="sweat",
                        x=origin_x + r.choice((-1, 1)) * r.uniform(spread_w * 0.26, spread_w * 0.46),
                        y=origin_y + r.uniform(-20.0, 6.0),
                        vx=r.uniform(18.0, 52.0) * r.choice((-1, 1)),
                        vy=r.uniform(-42.0, -6.0),
                        size=r.uniform(7.5, 11.0),
                        age=0.0,
                        lifetime=r.uniform(0.68, 0.95),
                        color=QColor("#8dd0f7"),
                        gravity=240.0,
                        front=True,
                    )
                )
        elif kind == "fish":
            for idx in range(10):
                self.particles.append(
                    Particle(
                        kind="fish",
                        x=origin_x + r.uniform(-spread_w * 0.58, spread_w * 0.58),
                        y=origin_y - r.uniform(22.0, 48.0),
                        vx=r.uniform(-30.0, 30.0),
                        vy=r.uniform(12.0, 64.0),
                        size=r.uniform(24.0, 34.0),
                        age=-idx * 0.04,
                        lifetime=r.uniform(1.0, 1.55),
                        color=QColor("#e8b877"),
                        rotation=r.uniform(-35.0, 35.0),
                        vrot=r.uniform(-145.0, 145.0),
                        gravity=185.0,
                        front=(idx % 2 == 0),
                        flip=(idx % 2 == 0),
                    )
                )
            self.emit("sparkles", origin_x=origin_x, origin_y=origin_y, spread_w=spread_w)
        elif kind == "notes":
            for idx in range(4):
                self.particles.append(
                    Particle(
                        kind="note",
                        x=origin_x + r.uniform(-spread_w * 0.45, spread_w * 0.45),
                        y=origin_y - r.uniform(12.0, 28.0),
                        vx=r.uniform(-8.0, 8.0),
                        vy=r.uniform(-46.0, -24.0),
                        size=r.uniform(15.0, 20.0),
                        age=-idx * 0.14,
                        lifetime=r.uniform(1.15, 1.75),
                        color=QColor("#8b6bf0"),
                        wobble=20.0,
                        phase=r.uniform(0.0, math.tau),
                        text="♪" if idx % 2 == 0 else "♫",
                        front=True,
                    )
                )
        elif kind == "sleep_z":
            self.particles.append(
                Particle(
                    kind="z",
                    x=origin_x + spread_w * 0.34,
                    y=origin_y - 26.0,
                    vx=12.0,
                    vy=-24.0,
                    size=r.uniform(15.0, 22.0),
                    age=0.0,
                    lifetime=1.9,
                    color=QColor("#7f70e8"),
                    wobble=12.0,
                    phase=r.uniform(0.0, math.tau),
                    text="z" if r.random() < 0.65 else "Z",
                    front=True,
                )
            )
        elif kind == "steam":
            for side in (-1, 1):
                for _ in range(5):
                    self.particles.append(
                        Particle(
                            kind="puff",
                            x=origin_x + side * spread_w * 0.38,
                            y=origin_y - 16.0,
                            vx=side * r.uniform(22.0, 68.0),
                            vy=r.uniform(-54.0, -18.0),
                            size=r.uniform(10.0, 18.0),
                            age=0.0,
                            lifetime=r.uniform(0.55, 0.95),
                            color=QColor(255, 255, 255, 220),
                            drag=1.4,
                            front=True,
                        )
                    )
        elif kind == "dust":
            for idx in range(8):
                self.particles.append(
                    Particle(
                        kind="puff",
                        x=origin_x + r.uniform(-spread_w * 0.42, spread_w * 0.42),
                        y=origin_y + r.uniform(12.0, 34.0),
                        vx=r.uniform(-55.0, 55.0),
                        vy=r.uniform(-24.0, -4.0),
                        size=r.uniform(9.0, 16.0),
                        age=0.0,
                        lifetime=r.uniform(0.45, 0.80),
                        color=QColor(196, 184, 232, 165),
                        drag=1.6,
                        front=(idx % 2 == 0),
                    )
                )
        elif kind == "alert":
            for idx in range(2):
                self.particles.append(
                    Particle(
                        kind="ring",
                        x=origin_x,
                        y=origin_y - 10.0,
                        vx=0.0,
                        vy=0.0,
                        size=18.0 + idx * 14.0,
                        age=-idx * 0.18,
                        lifetime=0.85,
                        color=QColor("#f59e0b"),
                        front=False,
                    )
                )
            self.emit("sparkles", origin_x=origin_x, origin_y=origin_y - 12.0, spread_w=spread_w * 0.8)
        elif kind == "summon":
            self.particles.append(
                Particle(
                    kind="ring",
                    x=origin_x,
                    y=origin_y,
                    vx=0.0,
                    vy=0.0,
                    size=12.0,
                    age=0.0,
                    lifetime=0.58,
                    color=QColor("#a855f7"),
                    front=False,
                )
            )
            palette = (QColor("#c084fc"), QColor("#8fd8ff"), QColor("#ffe08a"), QColor("#ffb3d9"))
            for idx in range(8):
                angle = (idx / 8.0) * math.tau + r.uniform(-0.18, 0.18)
                speed = r.uniform(42.0, 82.0)
                self.particles.append(
                    Particle(
                        kind="orb" if idx % 2 == 0 else "sparkle",
                        x=origin_x,
                        y=origin_y,
                        vx=math.cos(angle) * speed,
                        vy=math.sin(angle) * speed - 18.0,
                        size=r.uniform(6.5, 11.0),
                        age=0.0,
                        lifetime=r.uniform(0.55, 0.90),
                        color=palette[idx % len(palette)],
                        rotation=r.uniform(0.0, 90.0),
                        vrot=r.uniform(-160.0, 160.0),
                        gravity=40.0,
                        front=(idx % 2 == 0),
                    )
                )

        added = len(self.particles) - before
        if len(self.particles) > self.MAX_PARTICLES:
            self.particles = self.particles[-self.MAX_PARTICLES :]
        return max(0, added)

    def emit_relay(
        self,
        *,
        from_side: int,
        target_x: float,
        target_y: float,
        spread_w: float = 110.0,
        accent: str = "#c084fc",
    ) -> int:
        """Emit glowing data/energy orbs flowing from a subagent's side into the host pet."""
        if not self.enabled or self.reduced_motion:
            return 0
        before = len(self.particles)
        r = self.rng
        side = -1 if from_side < 0 else 1
        start_x = target_x + side * max(56.0, spread_w * 0.54)
        accent_color = QColor(accent)
        if not accent_color.isValid():
            accent_color = QColor("#c084fc")
        palette = (accent_color, QColor("#8fd8ff"), QColor("#ffe08a"))
        for idx in range(6):
            lifetime = r.uniform(0.52, 0.78)
            sx = start_x + r.uniform(-10.0, 10.0)
            sy = target_y + r.uniform(-22.0, 22.0)
            dx = target_x - sx
            dy = (target_y - 8.0) - sy
            gravity = 55.0
            vx = dx / lifetime
            vy = (dy - 0.5 * gravity * lifetime * lifetime) / lifetime
            self.particles.append(
                Particle(
                    kind="orb" if idx % 2 == 0 else "sparkle",
                    x=sx,
                    y=sy,
                    vx=vx,
                    vy=vy,
                    size=r.uniform(7.0, 11.0),
                    age=-idx * 0.055,
                    lifetime=lifetime,
                    color=palette[idx % len(palette)],
                    rotation=r.uniform(0.0, 90.0),
                    vrot=r.uniform(-140.0, 140.0),
                    gravity=gravity,
                    front=True,
                )
            )
        added = len(self.particles) - before
        if len(self.particles) > self.MAX_PARTICLES:
            self.particles = self.particles[-self.MAX_PARTICLES :]
        return max(0, added)

    def update(self, dt: float) -> None:
        if dt <= 0:
            return
        step = min(0.10, float(dt))
        self._elapsed += step
        if not self.particles:
            return
        kept: list[Particle] = []
        for p in self.particles:
            p.age += step
            if p.age >= p.lifetime:
                continue
            if p.age >= 0.0:
                p.vy += p.gravity * step
                if p.drag > 0.0:
                    damp = max(0.0, 1.0 - p.drag * step)
                    p.vx *= damp
                    p.vy *= damp
                wobble_dx = math.cos(self._elapsed * 3.0 + p.phase) * p.wobble * step if p.wobble else 0.0
                p.x += p.vx * step + wobble_dx
                p.y += p.vy * step
                p.rotation += p.vrot * step
            kept.append(p)
        self.particles = kept

    def paint(self, painter: QPainter, *, layer: str = "all") -> None:
        if not self.particles or not self.enabled or self.reduced_motion:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base_opacity = painter.opacity()
        for p in self.particles:
            if p.age < 0.0:
                continue
            if layer == "back" and p.front:
                continue
            if layer == "front" and not p.front:
                continue
            progress = max(0.0, min(1.0, p.age / max(0.01, p.lifetime)))
            fade_in = min(1.0, progress / 0.12) if progress < 0.12 else 1.0
            fade_out = min(1.0, (1.0 - progress) / 0.30) if progress > 0.70 else 1.0
            alpha = fade_in * fade_out
            if alpha <= 0.01:
                continue
            grow = min(1.0, p.age / 0.12) if p.kind != "ring" else 1.0
            painter.save()
            painter.setOpacity(base_opacity * alpha)
            painter.translate(p.x, p.y)
            if p.rotation:
                painter.rotate(p.rotation)
            if grow < 0.999:
                painter.scale(grow, grow)
            if p.kind == "sparkle":
                self._draw_sparkle(painter, p.size, p.color)
            elif p.kind == "confetti":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(p.color)
                painter.drawRoundedRect(
                    QRectF(-p.size * 0.5, -p.size * 0.25, p.size, p.size * 0.5),
                    p.size * 0.16,
                    p.size * 0.16,
                )
            elif p.kind == "heart":
                self._draw_heart(painter, p.size, p.color)
            elif p.kind == "sweat":
                self._draw_sweat(painter, p.size, p.color)
            elif p.kind == "fish":
                draw_dried_fish(painter, 0.0, 0.0, p.size, 0.0, flip=p.flip)
            elif p.kind == "ring":
                radius = p.size + progress * 34.0
                pen = QPen(p.color, 2.2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)
            elif p.kind == "orb":
                self._draw_orb(painter, p.size, p.color)
            elif p.kind in ("note", "z"):
                self._draw_text_glyph(painter, p.text or ("♪" if p.kind == "note" else "z"), p.size, p.color)
            elif p.kind == "puff":
                self._draw_puff(painter, p.size, p.color)
            painter.restore()
        painter.restore()

    @staticmethod
    def _draw_sparkle(painter: QPainter, size: float, color: QColor) -> None:
        r_out = size * 0.62
        r_in = size * 0.19
        pts: list[QPointF] = []
        for i in range(8):
            angle = i * (math.pi / 4.0) - math.pi / 2.0
            rad = r_out if i % 2 == 0 else r_in
            pts.append(QPointF(math.cos(angle) * rad, math.sin(angle) * rad))
        glow = QRadialGradient(0.0, 0.0, r_out)
        glow.setColorAt(0.0, QColor("#ffffff"))
        glow.setColorAt(0.45, color)
        glow.setColorAt(1.0, color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawPolygon(QPolygonF(pts))

    @staticmethod
    def _draw_heart(painter: QPainter, size: float, color: QColor) -> None:
        s = size * 0.52
        path = QPainterPath()
        path.moveTo(0.0, s * 0.92)
        path.cubicTo(-s * 1.45, -s * 0.08, -s * 0.78, -s * 1.08, 0.0, -s * 0.34)
        path.cubicTo(s * 0.78, -s * 1.08, s * 1.45, -s * 0.08, 0.0, s * 0.92)
        path.closeSubpath()
        grad = QLinearGradient(0.0, -s, 0.0, s)
        grad.setColorAt(0.0, QColor("#ffb3cb"))
        grad.setColorAt(1.0, color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawPath(path)

    @staticmethod
    def _draw_sweat(painter: QPainter, size: float, color: QColor) -> None:
        s = size * 0.52
        path = QPainterPath()
        path.moveTo(0.0, -s)
        path.quadTo(s * 0.95, s * 0.38, 0.0, s)
        path.quadTo(-s * 0.95, s * 0.38, 0.0, -s)
        path.closeSubpath()
        grad = QLinearGradient(0.0, -s, 0.0, s)
        grad.setColorAt(0.0, QColor(255, 255, 255, 215))
        grad.setColorAt(0.45, color)
        grad.setColorAt(1.0, color)
        painter.setPen(QPen(QColor(47, 42, 110, 120), 1.0))
        painter.setBrush(grad)
        painter.drawPath(path)

    @staticmethod
    def _draw_text_glyph(painter: QPainter, text: str, size: float, color: QColor) -> None:
        font = QFont()
        font.setPixelSize(max(11, int(round(size))))
        font.setWeight(QFont.Weight.Bold)
        path = QPainterPath()
        path.addText(0.0, 0.0, font, text)
        bounds = path.boundingRect()
        painter.save()
        painter.translate(-bounds.center().x(), -bounds.center().y())
        painter.setPen(
            QPen(QColor(255, 255, 255, 220), 4.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
        painter.restore()

    @staticmethod
    def _draw_puff(painter: QPainter, size: float, color: QColor) -> None:
        r = max(2.0, size * 0.65)
        grad = QRadialGradient(0.0, 0.0, r)
        grad.setColorAt(0.0, color)
        edge = QColor(color.red(), color.green(), color.blue(), 0)
        grad.setColorAt(1.0, edge)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(QPointF(0.0, 0.0), r, r)

    @staticmethod
    def _draw_orb(painter: QPainter, size: float, color: QColor) -> None:
        r = size * 0.55
        painter.setPen(Qt.PenStyle.NoPen)
        glow = QColor(color.red(), color.green(), color.blue(), 115)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(0.0, 0.0), r * 1.48, r * 1.48)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(0.0, 0.0), r * 0.85, r * 0.85)
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawEllipse(QPointF(-r * 0.18, -r * 0.18), r * 0.34, r * 0.34)
