"""Floating comic speech-bubble card for Antigravity milestone progress reports.

Renders an always-on-top, non-focus-stealing translucent speech card anchored
above the desktop pet with a comic tail pointing directly at her head. Supports:
- Distinct visual badges for ``step_done``, ``progress``, and ``summary`` events
- Word-aware CJK + Latin wrapping across up to 5 readable lines
- Optional next-step / turn-token footer strip
- Smooth auto-dismiss countdown bar that pauses on hover and closes on click
- Multi-monitor screen clamping and full reduced-motion safety
"""

from __future__ import annotations

import re
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QApplication, QWidget

from agy.milestone import MilestoneEvent
from app.i18n import tr

TAIL_H = 10
PAD_X = 8
PAD_Y = 8
MIN_CARD_W = 228
MAX_CARD_W = 332
INNER_PAD_X = 14
INNER_PAD_Y = 10
MAX_BODY_LINES = 5
FADE_IN_S = 0.16
FADE_OUT_S = 0.20

_WORD_TOKEN_RE = re.compile(r"[A-Za-z0-9'’._/-]+|\s+|.")

_PALETTES: dict[str, tuple[str, str, str]] = {
    # (border_hex, pill_bg_hex, pill_fg_hex)
    "step_done": ("#10b981", "#d1fae5", "#047857"),
    "progress": ("#0ea5e9", "#e0f2fe", "#0369a1"),
    "summary": ("#8b5cf6", "#ede9fe", "#6d28d9"),
}


def _wrap_paragraphs(text: str, metrics: QFontMetrics, max_width: int, max_lines: int) -> list[str]:
    """Word-aware multi-line wrap preserving explicit newlines and eliding cleanly."""
    if not text or max_width <= 20 or max_lines <= 0:
        return []
    out: list[str] = []
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    for p_idx, para in enumerate(paragraphs):
        tokens = _WORD_TOKEN_RE.findall(para)
        current = ""
        for tok in tokens:
            if not current and tok.isspace():
                continue
            cand = current + tok
            if current and metrics.horizontalAdvance(cand.rstrip()) > max_width:
                out.append(current.rstrip())
                if len(out) >= max_lines:
                    break
                if tok.isspace():
                    current = ""
                elif metrics.horizontalAdvance(tok) > max_width:
                    # Break an overlong token (e.g. long filename/identifier) gracefully
                    piece = ""
                    for ch in tok:
                        if piece and metrics.horizontalAdvance(piece + ch) > max_width:
                            out.append(piece)
                            if len(out) >= max_lines:
                                piece = ""
                                break
                            piece = ch
                        else:
                            piece += ch
                    current = piece
                else:
                    current = tok
            else:
                current = cand
        if len(out) < max_lines and current.strip():
            out.append(current.rstrip())
        if len(out) >= max_lines:
            has_more = (p_idx + 1 < len(paragraphs)) or bool(current.strip() and current.rstrip() != out[-1])
            if has_more:
                out[-1] = metrics.elidedText(out[-1] + "…", Qt.TextElideMode.ElideRight, max_width)
            break
    return out[:max_lines]


class MilestonePopupWidget(QWidget):
    """Floating comic speech-card above the pet showing Agent milestone results."""

    def __init__(
        self,
        *,
        topmost: bool = True,
        accent: str = "#8b5cf6",
        reduced_motion: bool = False,
    ) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        if topmost:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setObjectName("milestonePopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._accent = QColor(accent)
        self._reduced_motion = bool(reduced_motion)
        self._event: MilestoneEvent | None = None
        self._meta: str = ""
        self._tail_dir: str | None = "down"  # "down" | "up" | None
        self._tail_x_global: int | None = None
        self._pet_rect: QRect | None = None
        self._anchor_top: int | None = None

        self._hovered = False
        self._close_hovered = False
        self._close_rect = QRectF()
        self._appeared_at = 0.0
        self._last_tick = 0.0
        self._clock_override: float | None = None
        self._duration = 8.0
        self._remaining = 0.0
        self._dismissing = False
        self._dismiss_started = 0.0

        self._badge_font = QFont()
        self._badge_font.setPointSize(8)
        self._badge_font.setWeight(QFont.Weight.Bold)
        self._title_font = QFont()
        self._title_font.setPointSize(9)
        self._title_font.setWeight(QFont.Weight.Bold)
        self._body_font = QFont()
        self._body_font.setPointSize(9)
        self._body_font.setWeight(QFont.Weight.Medium)
        self._footer_font = QFont()
        self._footer_font.setPointSize(8)
        self._footer_font.setWeight(QFont.Weight.DemiBold)

        self._card_w = MIN_CARD_W
        self._card_h = 84
        self._badge_text = ""
        self._header_title = ""
        self._body_lines: list[str] = []
        self._footer_text = ""

        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self.tick)

    @property
    def current_event(self) -> MilestoneEvent | None:
        return self._event

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._remaining)

    @property
    def paused_by_hover(self) -> bool:
        return self._hovered

    def set_topmost(self, topmost: bool) -> None:
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(topmost))
        if was_visible:
            self.show()

    def set_accent(self, accent: str) -> None:
        self._accent = QColor(accent)
        if self.isVisible():
            self.update()

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)
        if self.isVisible():
            self.update()

    def retranslate(self) -> None:
        if self._event is not None:
            self._rebuild_layout()
            if self._pet_rect is not None:
                self.follow_pet(self._pet_rect, anchor_top=self._anchor_top)
            if self.isVisible():
                self.setToolTip(tr("milestone.hover_hint"))
                self.update()

    def show_milestone(
        self,
        event: MilestoneEvent,
        *,
        meta: str = "",
        duration: float | None = None,
        now: float | None = None,
    ) -> None:
        ts = time.monotonic() if now is None else float(now)
        self._clock_override = None if now is None else ts
        self._event = event
        self._meta = str(meta or "").strip()
        body_len = len(event.body or event.title)
        if duration is None:
            duration = min(12.0, max(6.5, 4.2 + body_len * 0.075))
        self._duration = max(2.0, float(duration))
        self._remaining = self._duration
        self._appeared_at = ts
        self._last_tick = ts
        self._dismissing = False
        self._dismiss_started = 0.0
        self._rebuild_layout()
        self.setToolTip(tr("milestone.hover_hint"))
        if self._pet_rect is not None:
            self.follow_pet(self._pet_rect, anchor_top=self._anchor_top)
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def dismiss(self, *, immediate: bool = False, now: float | None = None) -> None:
        if not self.isVisible() and not self._timer.isActive():
            self._dismissing = False
            self._remaining = 0.0
            return
        if immediate or self._reduced_motion:
            self._dismissing = False
            self._remaining = 0.0
            self._timer.stop()
            self.hide()
            return
        ts = time.monotonic() if now is None else float(now)
        if now is not None:
            self._clock_override = ts
        if not self._dismissing:
            self._dismissing = True
            self._dismiss_started = ts
            if not self._timer.isActive():
                self._timer.start()
            self.update()

    def tick(self, now: float | None = None) -> None:
        if not self.isVisible():
            self._timer.stop()
            return
        ts = time.monotonic() if now is None else float(now)
        if now is not None:
            self._clock_override = ts
        dt = max(0.0, min(0.25, ts - self._last_tick)) if self._last_tick > 0 else 0.0
        if now is not None and self._last_tick > 0:
            dt = max(0.0, ts - self._last_tick)
        self._last_tick = ts
        if self._dismissing:
            if self._reduced_motion or (ts - self._dismiss_started) >= FADE_OUT_S:
                self._dismissing = False
                self._remaining = 0.0
                self._timer.stop()
                self.hide()
                return
            self.update()
            return
        if not self._hovered:
            self._remaining -= dt
            if self._remaining <= 0.0:
                self.dismiss(now=ts)
                return
        self.update()

    def _palette(self) -> tuple[QColor, QColor, QColor]:
        kind = self._event.kind if self._event else "progress"
        border_hex, bg_hex, fg_hex = _PALETTES.get(kind, _PALETTES["progress"])
        return QColor(border_hex), QColor(bg_hex), QColor(fg_hex)

    def _badge_label(self) -> str:
        ev = self._event
        if ev is None:
            return ""
        if ev.step_total > 0 and ev.step_done > 0:
            return f"✓ {ev.step_done}/{ev.step_total}"
        if ev.kind == "summary":
            return f"✨ {tr('milestone.badge.summary')}"
        if ev.kind == "step_done":
            return f"✓ {tr('milestone.badge.step_done')}"
        return f"📌 {tr('milestone.badge.progress')}"

    def _rebuild_layout(self) -> None:
        ev = self._event
        if ev is None:
            return
        self._badge_text = self._badge_label()
        body_src = ev.body or ev.title
        self._header_title = ev.title if (ev.title and ev.title != body_src) else ""

        footer_parts: list[str] = []
        if ev.next_step:
            footer_parts.append(f"→ {tr('milestone.next_prefix', step=ev.next_step)}")
        if self._meta:
            footer_parts.append(f"⚡ {self._meta}")
        self._footer_text = "  ·  ".join(footer_parts)

        badge_fm = QFontMetrics(self._badge_font)
        title_fm = QFontMetrics(self._title_font)
        body_fm = QFontMetrics(self._body_font)
        footer_fm = QFontMetrics(self._footer_font)

        badge_w = badge_fm.horizontalAdvance(self._badge_text) + 16
        close_reserve = 22
        max_text_w = MAX_CARD_W - INNER_PAD_X * 2
        self._body_lines = _wrap_paragraphs(body_src, body_fm, max_text_w, MAX_BODY_LINES)
        if not self._body_lines:
            self._body_lines = [body_fm.elidedText(body_src, Qt.TextElideMode.ElideRight, max_text_w)]

        header_need = badge_w + close_reserve + 6
        if self._header_title:
            header_need += min(max_text_w - badge_w - close_reserve, title_fm.horizontalAdvance(self._header_title) + 8)
        body_need = max((body_fm.horizontalAdvance(ln) for ln in self._body_lines), default=0)
        footer_need = min(max_text_w, footer_fm.horizontalAdvance(self._footer_text)) if self._footer_text else 0

        content_w = max(header_need, body_need, footer_need)
        self._card_w = max(MIN_CARD_W, min(MAX_CARD_W, content_w + INNER_PAD_X * 2))

        # Re-wrap body cleanly if card ended up at MIN_CARD_W or narrower
        actual_text_w = self._card_w - INNER_PAD_X * 2
        self._body_lines = _wrap_paragraphs(body_src, body_fm, actual_text_w, MAX_BODY_LINES)

        header_h = max(badge_fm.height() + 6, title_fm.height() + 2) + 7
        line_h = body_fm.height() + 3
        body_h = max(1, len(self._body_lines)) * line_h
        footer_h = (footer_fm.height() + 10) if self._footer_text else 0
        self._card_h = INNER_PAD_Y + header_h + body_h + footer_h + INNER_PAD_Y + 6
        self._sync_fixed_size()

    def _sync_fixed_size(self) -> None:
        extra_h = TAIL_H if self._tail_dir in {"down", "up"} else 0
        w = int(self._card_w + PAD_X * 2)
        h = int(self._card_h + PAD_Y * 2 + extra_h)
        if self.width() != w or self.height() != h:
            self.setFixedSize(w, h)

    def follow_pet(
        self,
        pet_rect: QRect,
        *,
        anchor_top: int | None = None,
        screen=None,
    ) -> None:
        self._pet_rect = QRect(pet_rect)
        self._anchor_top = anchor_top
        self._tail_x_global = pet_rect.center().x()
        scr = screen or QApplication.screenAt(pet_rect.center()) or QApplication.primaryScreen()
        area = scr.availableGeometry() if scr else QRect(0, 0, 1920, 1080)

        top_limit = anchor_top if anchor_top is not None else pet_rect.top()
        # Prefer sitting cleanly right above the pet's head with a downward tail
        self._tail_dir = "down"
        self._sync_fixed_size()
        x = pet_rect.center().x() - self.width() // 2
        y = top_limit - self.height() + 4

        if y < area.top():
            # Not enough headroom: try below the pet, then beside the pet
            below_y = pet_rect.bottom() + 2
            self._tail_dir = "up"
            self._sync_fixed_size()
            if below_y + self.height() <= area.bottom():
                y = below_y
            else:
                self._tail_dir = None
                self._sync_fixed_size()
                side_left = pet_rect.left() - self.width() - 6
                side_right = pet_rect.right() + 6
                if side_left >= area.left():
                    x = side_left
                elif side_right + self.width() <= area.right():
                    x = side_right
                y = max(area.top() + 4, min(pet_rect.top(), area.bottom() - self.height() + 1))

        x = max(area.left(), min(x, area.right() - self.width() + 1))
        y = max(area.top(), min(y, area.bottom() - self.height() + 1))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
        self.update()

    def _current_opacity(self) -> float:
        if self._reduced_motion:
            return 0.0 if self._dismissing else 1.0
        now = self._clock_override if self._clock_override is not None else time.monotonic()
        if self._dismissing:
            return max(0.0, 1.0 - (now - self._dismiss_started) / FADE_OUT_S)
        if self._appeared_at <= 0:
            return 1.0
        return min(1.0, max(0.0, (now - self._appeared_at) / FADE_IN_S))

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self._close_hovered = False
        if self._remaining > 0:
            self._remaining = max(self._remaining, 2.5)
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        was = self._close_hovered
        self._close_hovered = self._close_rect.contains(pos)
        if self._close_hovered != was:
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() in {Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton}:
            self.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._event is None:
            return
        opacity = self._current_opacity()
        if opacity <= 0.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(opacity)

        card_top = float(PAD_Y + (TAIL_H if self._tail_dir == "up" else 0))
        body = QRectF(float(PAD_X), card_top, float(self._card_w), float(self._card_h))

        shape = QPainterPath()
        shape.addRoundedRect(body, 14.0, 14.0)

        if self._tail_dir in {"down", "up"}:
            local_tx = (
                float(self._tail_x_global - self.x())
                if self._tail_x_global is not None
                else body.center().x()
            )
            tx = max(body.left() + 22.0, min(body.right() - 22.0, local_tx))
            tail = QPainterPath()
            if self._tail_dir == "down":
                ty = body.bottom()
                tail.addPolygon(
                    QPolygonF(
                        [
                            QPointF(tx - 7.5, ty - 1.0),
                            QPointF(tx + 7.5, ty - 1.0),
                            QPointF(tx, ty + TAIL_H - 1.0),
                        ]
                    )
                )
            else:
                ty = body.top()
                tail.addPolygon(
                    QPolygonF(
                        [
                            QPointF(tx - 7.5, ty + 1.0),
                            QPointF(tx + 7.5, ty + 1.0),
                            QPointF(tx, ty - TAIL_H + 1.0),
                        ]
                    )
                )
            shape = shape.united(tail)

        border_color, pill_bg, pill_fg = self._palette()

        # Soft purple-tinted drop shadow matching PetRenderer comic cards
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(46, 24, 104, 42))
        painter.drawPath(shape.translated(0.0, 3.0))

        # Main warm ivory bubble card
        painter.setBrush(QColor(255, 253, 251, 248))
        painter.setPen(
            QPen(border_color, 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawPath(shape)

        # Header row: colored badge pill + optional title + subtle close glyph
        x_cursor = body.left() + INNER_PAD_X
        y_cursor = body.top() + INNER_PAD_Y

        badge_fm = QFontMetrics(self._badge_font)
        pill_w = float(badge_fm.horizontalAdvance(self._badge_text) + 14)
        pill_h = float(badge_fm.height() + 5)
        pill_rect = QRectF(x_cursor, y_cursor, pill_w, pill_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pill_bg)
        painter.drawRoundedRect(pill_rect, pill_h / 2.0, pill_h / 2.0)
        painter.setFont(self._badge_font)
        painter.setPen(pill_fg)
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, self._badge_text)

        # Subtle × dismiss button at top-right
        close_size = 18.0
        self._close_rect = QRectF(
            body.right() - INNER_PAD_X - close_size + 2.0,
            y_cursor + (pill_h - close_size) / 2.0,
            close_size,
            close_size,
        )
        if self._close_hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(139, 92, 246, 36))
            painter.drawEllipse(self._close_rect)
        painter.setFont(self._badge_font)
        painter.setPen(QColor("#6b5b95") if self._close_hovered else QColor("#a599be"))
        painter.drawText(self._close_rect, Qt.AlignmentFlag.AlignCenter, "×")

        # Optional header title next to badge
        if self._header_title:
            title_fm = QFontMetrics(self._title_font)
            title_left = pill_rect.right() + 7.0
            title_max_w = max(20.0, self._close_rect.left() - title_left - 4.0)
            elided_title = title_fm.elidedText(self._header_title, Qt.TextElideMode.ElideRight, int(title_max_w))
            painter.setFont(self._title_font)
            painter.setPen(QColor("#2a1b3d"))
            painter.drawText(
                QRectF(title_left, y_cursor, title_max_w, pill_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided_title,
            )

        y_cursor += pill_h + 7.0

        # Body lines
        body_fm = QFontMetrics(self._body_font)
        line_h = float(body_fm.height() + 3)
        text_w = body.width() - INNER_PAD_X * 2
        painter.setFont(self._body_font)
        painter.setPen(QColor("#2a1b3d"))
        for line in self._body_lines:
            painter.drawText(
                QRectF(x_cursor, y_cursor, text_w, line_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line,
            )
            y_cursor += line_h

        # Optional footer (next step / turn token meta)
        if self._footer_text:
            y_cursor += 3.0
            painter.setPen(QPen(QColor(border_color.red(), border_color.green(), border_color.blue(), 46), 1.0))
            painter.drawLine(QPointF(x_cursor, y_cursor), QPointF(body.right() - INNER_PAD_X, y_cursor))
            y_cursor += 4.0
            footer_fm = QFontMetrics(self._footer_font)
            elided_footer = footer_fm.elidedText(self._footer_text, Qt.TextElideMode.ElideRight, int(text_w))
            painter.setFont(self._footer_font)
            painter.setPen(QColor("#6b5b95"))
            painter.drawText(
                QRectF(x_cursor, y_cursor, text_w, float(footer_fm.height() + 2)),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided_footer,
            )

        # Bottom countdown strip (pauses & glows gently when hovered)
        frac = max(0.0, min(1.0, self._remaining / max(0.1, self._duration)))
        bar_h = 2.6
        bar_rect = QRectF(body.left() + 14.0, body.bottom() - 6.0, body.width() - 28.0, bar_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(border_color.red(), border_color.green(), border_color.blue(), 36))
        painter.drawRoundedRect(bar_rect, bar_h / 2.0, bar_h / 2.0)
        if frac > 0.0:
            fill_rect = QRectF(bar_rect.left(), bar_rect.top(), bar_rect.width() * frac, bar_h)
            fill_color = QColor(border_color)
            fill_color.setAlpha(235 if self._hovered else 185)
            painter.setBrush(fill_color)
            painter.drawRoundedRect(fill_rect, bar_h / 2.0, bar_h / 2.0)
