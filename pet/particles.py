"""Lightweight QPainter vector particle bursts for desktop pet reactions."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF


@dataclass(slots=True)
class Particle:
    kind: str  # sparkle / confetti / heart / sweat / fish / ring
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


class ParticleSystem:
    """Zero-dependency procedural particles rendered inside PetWindow.paintEvent."""

    MAX_PARTICLES = 64

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.particles: list[Particle] = []
        self.enabled = True
        self.reduced_motion = False

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
            palette = (QColor("#fbbf24"), QColor("#c084fc"), QColor("#38bdf8"), QColor("#f472b6"))
            for _ in range(10):
                self.particles.append(
                    Particle(
                        kind="sparkle",
                        x=origin_x + r.uniform(-spread_w * 0.55, spread_w * 0.55),
                        y=origin_y + r.uniform(-24.0, 26.0),
                        vx=r.uniform(-22.0, 22.0),
                        vy=r.uniform(-58.0, -24.0),
                        size=r.uniform(5.5, 10.5),
                        age=0.0,
                        lifetime=r.uniform(0.75, 1.25),
                        color=r.choice(palette),
                        rotation=r.uniform(0.0, 90.0),
                        vrot=r.uniform(-90.0, 90.0),
                    )
                )
        elif kind == "confetti":
            palette = (
                QColor("#f43f5e"),
                QColor("#f59e0b"),
                QColor("#10b981"),
                QColor("#3b82f6"),
                QColor("#a855f7"),
                QColor("#ec4899"),
            )
            for _ in range(18):
                self.particles.append(
                    Particle(
                        kind="confetti",
                        x=origin_x + r.uniform(-spread_w * 0.45, spread_w * 0.45),
                        y=origin_y + r.uniform(-20.0, 10.0),
                        vx=r.uniform(-85.0, 85.0),
                        vy=r.uniform(-140.0, -55.0),
                        size=r.uniform(5.0, 8.5),
                        age=0.0,
                        lifetime=r.uniform(1.0, 1.65),
                        color=r.choice(palette),
                        rotation=r.uniform(0.0, 360.0),
                        vrot=r.uniform(-280.0, 280.0),
                        gravity=210.0,
                    )
                )
        elif kind == "hearts":
            palette = (QColor("#fb7185"), QColor("#f43f5e"), QColor("#f472b6"))
            for _ in range(7):
                self.particles.append(
                    Particle(
                        kind="heart",
                        x=origin_x + r.uniform(-spread_w * 0.42, spread_w * 0.42),
                        y=origin_y + r.uniform(-16.0, 12.0),
                        vx=r.uniform(-16.0, 16.0),
                        vy=r.uniform(-55.0, -28.0),
                        size=r.uniform(7.5, 11.5),
                        age=0.0,
                        lifetime=r.uniform(0.95, 1.45),
                        color=r.choice(palette),
                    )
                )
        elif kind == "sweat":
            for _ in range(4):
                self.particles.append(
                    Particle(
                        kind="sweat",
                        x=origin_x + r.choice((-1, 1)) * r.uniform(spread_w * 0.28, spread_w * 0.48),
                        y=origin_y + r.uniform(-18.0, 6.0),
                        vx=r.uniform(-8.0, 8.0),
                        vy=r.uniform(12.0, 34.0),
                        size=r.uniform(6.0, 9.0),
                        age=0.0,
                        lifetime=r.uniform(0.75, 1.1),
                        color=QColor("#38bdf8"),
                        gravity=95.0,
                    )
                )
        elif kind == "fish":
            for _ in range(8):
                self.particles.append(
                    Particle(
                        kind="fish",
                        x=origin_x + r.uniform(-spread_w * 0.55, spread_w * 0.55),
                        y=origin_y - r.uniform(18.0, 42.0),
                        vx=r.uniform(-35.0, 35.0),
                        vy=r.uniform(-75.0, -20.0),
                        size=r.uniform(9.0, 12.5),
                        age=0.0,
                        lifetime=r.uniform(1.1, 1.7),
                        color=r.choice((QColor("#fb923c"), QColor("#f59e0b"), QColor("#38bdf8"))),
                        rotation=r.uniform(-30.0, 30.0),
                        vrot=r.uniform(-110.0, 110.0),
                        gravity=185.0,
                    )
                )
            self.emit("sparkles", origin_x=origin_x, origin_y=origin_y, spread_w=spread_w)
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
                    )
                )
            self.emit("sparkles", origin_x=origin_x, origin_y=origin_y - 12.0, spread_w=spread_w * 0.8)

        added = len(self.particles) - before
        if len(self.particles) > self.MAX_PARTICLES:
            self.particles = self.particles[-self.MAX_PARTICLES :]
        return max(0, added)

    def update(self, dt: float) -> None:
        if not self.particles or dt <= 0:
            return
        step = min(0.10, float(dt))
        kept: list[Particle] = []
        for p in self.particles:
            p.age += step
            if p.age >= p.lifetime:
                continue
            if p.age >= 0.0:
                p.vy += p.gravity * step
                p.x += p.vx * step
                p.y += p.vy * step
                p.rotation += p.vrot * step
            kept.append(p)
        self.particles = kept

    def paint(self, painter: QPainter) -> None:
        if not self.particles or not self.enabled or self.reduced_motion:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base_opacity = painter.opacity()
        for p in self.particles:
            if p.age < 0.0:
                continue
            progress = max(0.0, min(1.0, p.age / max(0.01, p.lifetime)))
            alpha = (1.0 - progress) * (min(1.0, progress / 0.14) if progress < 0.14 else 1.0)
            if alpha <= 0.01:
                continue
            painter.save()
            painter.setOpacity(base_opacity * alpha)
            painter.translate(p.x, p.y)
            if p.rotation:
                painter.rotate(p.rotation)
            if p.kind == "sparkle":
                self._draw_sparkle(painter, p.size, p.color)
            elif p.kind == "confetti":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(p.color)
                painter.drawRoundedRect(QRectF(-p.size * 0.5, -p.size * 0.3, p.size, p.size * 0.6), 1.5, 1.5)
            elif p.kind == "heart":
                self._draw_heart(painter, p.size, p.color)
            elif p.kind == "sweat":
                self._draw_sweat(painter, p.size, p.color)
            elif p.kind == "fish":
                self._draw_fish(painter, p.size, p.color)
            elif p.kind == "ring":
                radius = p.size + progress * 34.0
                pen = QPen(p.color, 2.2)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)
            painter.restore()
        painter.restore()

    @staticmethod
    def _draw_sparkle(painter: QPainter, size: float, color: QColor) -> None:
        r_out = size * 0.55
        r_in = size * 0.18
        pts: list[QPointF] = []
        for i in range(8):
            angle = i * (math.pi / 4.0)
            rad = r_out if i % 2 == 0 else r_in
            pts.append(QPointF(math.cos(angle) * rad, math.sin(angle) * rad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF(pts))

    @staticmethod
    def _draw_heart(painter: QPainter, size: float, color: QColor) -> None:
        s = size * 0.5
        path = QPainterPath()
        path.moveTo(0.0, s * 0.85)
        path.cubicTo(-s * 1.25, s * 0.05, -s * 0.95, -s * 1.05, 0.0, -s * 0.35)
        path.cubicTo(s * 0.95, -s * 1.05, s * 1.25, s * 0.05, 0.0, s * 0.85)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)

    @staticmethod
    def _draw_sweat(painter: QPainter, size: float, color: QColor) -> None:
        s = size * 0.5
        path = QPainterPath()
        path.moveTo(0.0, -s)
        path.cubicTo(s * 0.85, s * 0.15, s * 0.7, s, 0.0, s)
        path.cubicTo(-s * 0.7, s, -s * 0.85, s * 0.15, 0.0, -s)
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1.0))
        painter.setBrush(color)
        painter.drawPath(path)

    @staticmethod
    def _draw_fish(painter: QPainter, size: float, color: QColor) -> None:
        s = size * 0.55
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(-s * 0.85, -s * 0.45, s * 1.35, s * 0.9))
        tail = QPolygonF([QPointF(s * 0.4, 0.0), QPointF(s * 1.05, -s * 0.48), QPointF(s * 1.05, s * 0.48)])
        painter.drawPolygon(tail)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(QPointF(-s * 0.42, -s * 0.08), s * 0.14, s * 0.14)
