from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget
from PySide6.QtCore import Qt


FOODS = ("小鱼", "虾", "贝", "海藻", "点心")  # fallback when a form has no food_menu


@dataclass(frozen=True, slots=True)
class FoodItem:
    id: str
    name: str
    icon: str = ""
    taste: str = "normal"  # favorite / normal / dislike
    lines: tuple[str, ...] = ()


def parse_food_menu(raw) -> tuple[FoodItem, ...]:
    """Foods from a form's ``food_menu`` (falls back to the shared FOODS)."""
    items: list[FoodItem] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        taste = str(entry.get("taste") or "normal")
        items.append(FoodItem(
            id=str(entry.get("id") or entry["name"]),
            name=str(entry["name"]),
            icon=str(entry.get("icon") or ""),
            taste=taste if taste in {"favorite", "normal", "dislike"} else "normal",
            lines=tuple(str(line) for line in entry.get("lines") or () if line),
        ))
    return tuple(items) or tuple(FoodItem(name, name) for name in FOODS)


@dataclass(frozen=True, slots=True)
class InteractionOutcome:
    kind: str
    body_region: str = "body"
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    held_seconds: float = 0.0


class InteractionController:
    """Recognizes click, head-pat, drag, and keeps drag samples for future throws."""

    def __init__(self) -> None:
        self._press_pos: QPoint | None = None
        self._body_region = "body"
        self._pressed_at = 0.0
        self.dragging = False
        self._samples: list[tuple[float, QPoint]] = []

    @property
    def active(self) -> bool:
        return self._press_pos is not None

    @property
    def body_region(self) -> str:
        return self._body_region

    @property
    def held_seconds(self) -> float:
        return max(0.0, time.monotonic() - self._pressed_at) if self.active else 0.0

    def press(
        self,
        position: QPoint,
        local_x: float,
        local_y: float,
        body_left: float,
        body_top: float,
        body_width: float,
        body_height: float,
    ) -> None:
        self._press_pos = position
        self._body_region = self.classify_region(
            local_x,
            local_y,
            body_left,
            body_top,
            body_width,
            body_height,
        )
        self._pressed_at = time.monotonic()
        self.dragging = False
        self._samples = [(time.monotonic(), position)]

    @staticmethod
    def classify_region(
        local_x: float,
        local_y: float,
        body_left: float,
        body_top: float,
        body_width: float,
        body_height: float,
    ) -> str:
        if body_width <= 0 or body_height <= 0:
            return "body"
        x = (float(local_x) - float(body_left)) / float(body_width)
        y = (float(local_y) - float(body_top)) / float(body_height)
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return "body"
        if 0.27 <= x <= 0.73 and 0.20 <= y <= 0.43:
            return "face"
        if 0.14 <= x <= 0.86 and 0.02 <= y <= 0.40:
            return "head"
        if (x >= 0.72 or x <= 0.24) and 0.45 <= y <= 0.88:
            return "tail"
        return "body"

    def move(self, position: QPoint) -> bool:
        if self._press_pos is None:
            return False
        self._samples.append((time.monotonic(), position))
        self._samples = self._samples[-18:]
        if not self.dragging and (position - self._press_pos).manhattanLength() > 6:
            self.dragging = True
        return self.dragging

    def release(self, position: QPoint) -> InteractionOutcome | None:
        if self._press_pos is None:
            return None
        self._samples.append((time.monotonic(), position))
        was_dragging = self.dragging
        region = self._body_region
        held_seconds = max(0.0, time.monotonic() - self._pressed_at)
        velocity_x, velocity_y = self._velocity()
        self._press_pos = None
        self._pressed_at = 0.0
        self.dragging = False
        self._samples = []
        if was_dragging:
            return InteractionOutcome("drag", region, velocity_x, velocity_y, held_seconds)
        return InteractionOutcome("click", region, held_seconds=held_seconds)

    def cancel(self) -> None:
        self._press_pos = None
        self.dragging = False
        self._pressed_at = 0.0
        self._samples = []

    def _velocity(self) -> tuple[float, float]:
        if len(self._samples) < 2:
            return 0.0, 0.0
        end_time, end_pos = self._samples[-1]
        # Only the final flick should influence a throw.  Using the entire drag
        # made a long, slow carry look fast and made a pause before release
        # retain stale velocity.
        recent = [sample for sample in self._samples if sample[0] >= end_time - 0.16]
        if len(recent) < 2:
            return 0.0, 0.0
        start_time, start_pos = recent[0]
        duration = max(0.001, end_time - start_time)
        if duration < 0.018:
            return 0.0, 0.0
        return (
            (end_pos.x() - start_pos.x()) / duration,
            (end_pos.y() - start_pos.y()) / duration,
        )


class FoodPanel(QWidget):
    """Small transient food picker; each form brings her own menu."""

    BUTTON_W = 58
    BUTTON_H = 52

    def __init__(self, on_pick) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("foodPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._on_pick = on_pick
        self._background = QColor(10, 43, 70, 235)
        self.items: tuple[FoodItem, ...] = ()
        self.buttons: list[QToolButton] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(6)
        self._close = QToolButton()
        self._close.setText("关闭")
        self._close.setFont(QFont("Microsoft YaHei UI", 10))
        self._close.setFixedSize(40, 30)
        self._close.clicked.connect(self.hide)
        self.set_menu(parse_food_menu(None))

    def set_menu(self, items, accent: str = "#339ad5") -> None:
        """Rebuild the buttons for ``items`` (FoodItem) in the form's colours."""
        for button in self.buttons:
            self._layout.removeWidget(button)
            button.hide()
            button.setParent(None)
            button.deleteLater()
        self._layout.removeWidget(self._close)
        self.items = tuple(items)
        self.buttons = []
        for item in self.items:
            button = QToolButton()
            button.setText(f"{item.icon}\n{item.name}" if item.icon else item.name)
            button.setToolTip(item.name)
            font = QFont("Microsoft YaHei UI", 9)
            font.setFamilies(["Microsoft YaHei UI", "Segoe UI Emoji"])
            button.setFont(font)
            button.setFixedSize(self.BUTTON_W, self.BUTTON_H)
            button.setStyleSheet(
                "QToolButton{background:rgba(255,255,255,238);border:none;"
                "border-radius:10px;color:#1f2937;font-weight:600;}"
                f"QToolButton:hover{{background:#ffffff;color:{accent};border:2px solid {accent};}}"
            )
            button.clicked.connect(lambda _=False, value=item.id: self._on_pick(value))
            self._layout.addWidget(button)
            self.buttons.append(button)
        self._layout.addWidget(self._close)
        self._close.setStyleSheet(
            "QToolButton{background:rgba(255,255,255,40);border:none;border-radius:8px;color:#f1f5f9;}"
            "QToolButton:hover{background:rgba(255,255,255,80);color:#fff;}"
        )
        count = len(self.buttons)
        self.setFixedSize(24 + count * (self.BUTTON_W + 6) + 40, self.BUTTON_H + 16)
        self._background = QColor(accent).darker(260)
        self._background.setAlpha(238)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._background)
        painter.drawRoundedRect(self.rect(), 14, 14)
        painter.end()

    def item(self, food_id: str) -> FoodItem | None:
        return next((item for item in self.items if item.id == food_id or item.name == food_id), None)

    def popup_at(self, x: float, y: float) -> None:
        self.move(round(x - self.width() / 2), round(y - self.height() - 10))
        self.show()
        self.raise_()
