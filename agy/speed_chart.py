"""Custom QPainter speed comparison bar chart and trend line chart."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from . import speed_stats
from .speed_stats import SpeedGroup, TrendPoint


def _format_metric(metric: str, value: float) -> str:
    if metric == "speed":
        return f"{value:.1f} tok/s"
    return f"{value:.2f} s"


def _format_span(first_ms: int, last_ms: int) -> str:
    if not first_ms or not last_ms:
        return "—"
    a = datetime.fromtimestamp(first_ms / 1000.0).strftime("%m-%d %H:%M")
    b = datetime.fromtimestamp(last_ms / 1000.0).strftime("%m-%d %H:%M")
    return a if a == b else f"{a} ~ {b}"


def _model_dot_color(label: str) -> str:
    low = (label or "").lower()
    if "hydrogen" in low:
        return "#38BDF8"
    if "neon" in low:
        return "#EC4899"
    if "argon" in low:
        return "#8B5CF6"
    if "claude" in low:
        return "#F97316"
    if "carbon" in low:
        return "#64748B"
    if "gpt" in low:
        return "#10B981"
    return "#6366F1"


class SpeedBarChart(QWidget):
    """Horizontal median bars per model + thinking tier with rich tooltips."""

    model_selected = Signal(str)

    ROW_H = 38
    PAD_Y = 8

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self._groups: list[SpeedGroup] = []
        self._selected: str = ""
        self._hovered: int = -1
        self._theme: str = "light"
        self._row_rects: list[tuple[QRectF, SpeedGroup]] = []

    def set_theme(self, theme: str) -> None:
        self._theme = theme if theme in ("light", "dark") else "light"
        self.update()

    def set_data(self, groups: list[SpeedGroup], *, selected: str = "") -> None:
        self._groups = list(groups)
        self._selected = selected
        self._hovered = -1
        self.setMinimumHeight(self.sizeHint().height())
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        rows = max(1, len(self._groups))
        return QSize(520, self.PAD_Y * 2 + rows * self.ROW_H)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self._theme == "dark"
        text_main = QColor("#E5E7EB" if dark else "#1F2937")
        text_muted = QColor("#9CA3AF" if dark else "#6B7280")
        track_bg = QColor("#1F2636" if dark else "#F1F3F6")
        bar_fill = QColor("#7C3AED" if dark else "#4B5563")
        bar_active = QColor("#8B5CF6" if dark else "#6D28D9")
        hover_bg = QColor(139, 92, 246, 26) if dark else QColor(109, 40, 217, 14)
        badge_bg = QColor("#2D2518" if dark else "#FEF3C7")
        badge_fg = QColor("#FBBF24" if dark else "#B45309")

        self._row_rects = []
        if not self._groups:
            painter.setPen(text_muted)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("speed.empty_bar"))
            return

        w = float(self.width())
        label_w = min(260.0, max(165.0, w * 0.29))
        value_w = 166.0
        bar_x = label_w + 14.0
        bar_w = max(80.0, w - bar_x - value_w - 14.0)
        peak = max((g.median_value for g in self._groups), default=1.0) or 1.0

        font = QFont(self.font())
        font.setPointSize(9)
        small_font = QFont(font)
        small_font.setPointSize(8)

        for idx, group in enumerate(self._groups):
            y = float(self.PAD_Y + idx * self.ROW_H)
            row_rect = QRectF(4.0, y, max(100.0, w - 8.0), float(self.ROW_H - 2))
            self._row_rects.append((row_rect, group))
            is_sel = group.label == self._selected
            if idx == self._hovered or is_sel:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(hover_bg)
                painter.drawRoundedRect(row_rect, 8, 8)

            # Dot + elided model name
            dot_y = y + (self.ROW_H - 2) / 2.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(_model_dot_color(group.label)))
            painter.drawEllipse(QPointF(14.0, dot_y), 4.0, 4.0)

            painter.setFont(font)
            painter.setPen(text_main)
            fm = painter.fontMetrics()
            elided = fm.elidedText(group.label, Qt.TextElideMode.ElideRight, int(label_w - 24))
            painter.drawText(QRectF(26.0, y, label_w - 24.0, self.ROW_H - 2), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

            # Bar track & fill
            track_rect = QRectF(bar_x, y + 8.0, bar_w, 20.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track_bg)
            painter.drawRoundedRect(track_rect, 6, 6)

            ratio = max(0.06, min(1.0, group.median_value / peak))
            fill_rect = QRectF(bar_x, y + 8.0, bar_w * ratio, 20.0)
            painter.setBrush(bar_active if is_sel else bar_fill)
            painter.drawRoundedRect(fill_rect, 6, 6)

            # Value + optional low_sample tag
            val_text = _format_metric(group.metric, group.median_value)
            right_x = bar_x + bar_w + 12.0
            if group.low_sample:
                painter.setFont(small_font)
                badge_rect = QRectF(w - 58.0, y + 9.0, 48.0, 18.0)
                painter.setBrush(badge_bg)
                painter.drawRoundedRect(badge_rect, 5, 5)
                painter.setPen(badge_fg)
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, tr("speed.low_sample"))
                painter.setFont(font)
                painter.setPen(text_main)
                painter.drawText(
                    QRectF(right_x, y, max(60.0, w - 66.0 - right_x), self.ROW_H - 2),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    val_text,
                )
            else:
                painter.setFont(font)
                painter.setPen(text_main)
                painter.drawText(
                    QRectF(right_x, y, max(60.0, w - 14.0 - right_x), self.ROW_H - 2),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    val_text,
                )

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        hit = -1
        for idx, (rect, group) in enumerate(self._row_rects):
            if rect.contains(pos):
                hit = idx
                tip = tr(
                    "speed.tip_bar",
                    label=group.label,
                    count=group.sample_count,
                    low=tr("speed.tip_low_suffix") if group.low_sample else "",
                    span=_format_span(group.first_ms, group.last_ms),
                    out=group.median_output_tokens,
                    inp=group.median_input_tokens,
                )
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                break
        if hit == -1:
            QToolTip.hideText()
        if hit != self._hovered:
            self._hovered = hit
            self.update()

    def leaveEvent(self, _event) -> None:
        if self._hovered != -1:
            self._hovered = -1
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        for _rect, group in self._row_rects:
            if _rect.contains(pos):
                self._selected = group.label
                self.update()
                self.model_selected.emit(group.label)
                return


class SpeedTrendChart(QWidget):
    """Smooth time-series polyline chart for one selected model + tier."""

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumHeight(210)
        self._points: list[TrendPoint] = []
        self._metric: str = "speed"
        self._color: str = "#6D28D9"
        self._theme: str = "light"
        self._coords: list[tuple[QPointF, TrendPoint]] = []
        self._hovered: int = -1

    def set_theme(self, theme: str) -> None:
        self._theme = theme if theme in ("light", "dark") else "light"
        self.update()

    def set_data(self, points: list[TrendPoint], *, metric: str, label: str = "") -> None:
        self._points = list(points)
        self._metric = metric
        self._color = _model_dot_color(label)
        self._hovered = -1
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self._theme == "dark"
        text_muted = QColor("#9CA3AF" if dark else "#6B7280")
        grid_color = QColor("#252D3D" if dark else "#E5E7EB")
        accent = QColor("#A78BFA" if dark else "#4B5563")
        point_ring = QColor("#161B26" if dark else "#FFFFFF")

        self._coords = []
        if not self._points:
            painter.setPen(text_muted)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("speed.empty_trend"))
            return

        left, right, top, bottom = 54.0, 18.0, 18.0, 28.0
        plot_w = max(80.0, self.width() - left - right)
        plot_h = max(60.0, self.height() - top - bottom)

        vals = [p.value for p in self._points]
        vmin, vmax = min(vals), max(vals)
        if vmax - vmin < 1e-6:
            vmin = max(0.0, vmin * 0.85)
            vmax = vmax * 1.15 if vmax > 0 else 10.0
        else:
            pad = (vmax - vmin) * 0.12
            vmin = max(0.0, vmin - pad)
            vmax += pad
        vmid = (vmin + vmax) / 2.0

        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)

        # Horizontal reference gridlines
        for val in (vmax, vmid, vmin):
            y = top + (vmax - val) / (vmax - vmin) * plot_h
            painter.setPen(QPen(grid_color, 1))
            painter.drawLine(QPointF(left, y), QPointF(left + plot_w, y))
            painter.setPen(text_muted)
            label = f"{val:.0f}" if self._metric == "speed" and val >= 10 else f"{val:.1f}"
            painter.drawText(QRectF(0, y - 9, left - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)

        n = len(self._points)
        for idx, pt in enumerate(self._points):
            x = left + (plot_w / 2.0 if n == 1 else idx / (n - 1) * plot_w)
            y = top + (vmax - pt.value) / (vmax - vmin) * plot_h
            self._coords.append((QPointF(x, y), pt))

        # Soft fill + polyline
        if len(self._coords) >= 2:
            area = QPainterPath()
            area.moveTo(self._coords[0][0].x(), top + plot_h)
            for coord, _pt in self._coords:
                area.lineTo(coord)
            area.lineTo(self._coords[-1][0].x(), top + plot_h)
            area.closeSubpath()
            grad = QLinearGradient(0, top, 0, top + plot_h)
            c_top = QColor(accent)
            c_top.setAlpha(45 if dark else 34)
            c_bot = QColor(accent)
            c_bot.setAlpha(0)
            grad.setColorAt(0.0, c_top)
            grad.setColorAt(1.0, c_bot)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawPath(area)

            line_path = QPainterPath(self._coords[0][0])
            for coord, _pt in self._coords[1:]:
                line_path.lineTo(coord)
            painter.setPen(QPen(accent, 2.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line_path)

        # Data markers
        for idx, (coord, _pt) in enumerate(self._coords):
            radius = 5.0 if idx == self._hovered else 3.4
            painter.setPen(QPen(point_ring, 1.5))
            painter.setBrush(accent)
            painter.drawEllipse(coord, radius, radius)

        # X-axis first & last timestamps
        first_ts = self._points[0].created_ms
        last_ts = self._points[-1].created_ms
        painter.setPen(text_muted)
        if first_ts:
            painter.drawText(
                QRectF(left, top + plot_h + 6, 120, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                datetime.fromtimestamp(first_ts / 1000.0).strftime("%m-%d %H:%M"),
            )
        if last_ts and len(self._points) > 1:
            painter.drawText(
                QRectF(left + plot_w - 120, top + plot_h + 6, 120, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                datetime.fromtimestamp(last_ts / 1000.0).strftime("%m-%d %H:%M"),
            )

    def mouseMoveEvent(self, event) -> None:
        if not self._coords:
            return
        pos = event.position()
        best_idx = -1
        best_dist = 28.0
        for idx, (coord, _pt) in enumerate(self._coords):
            dist = abs(coord.x() - pos.x())
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        if best_idx >= 0:
            _coord, pt = self._coords[best_idx]
            ts = datetime.fromtimestamp(pt.created_ms / 1000.0).strftime("%m-%d %H:%M:%S") if pt.created_ms else "—"
            tip = tr("speed.tip_trend", ts=ts, val=_format_metric(self._metric, pt.value), out=pt.output_tokens, inp=pt.input_tokens)
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()
        if best_idx != self._hovered:
            self._hovered = best_idx
            self.update()

    def leaveEvent(self, _event) -> None:
        if self._hovered != -1:
            self._hovered = -1
            self.update()


class SpeedComparisonView(QScrollArea):
    """Full '速度对比' tab with filters, median bars, and trend chart."""

    source_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._conversations: list = []

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(12)

        # Filter bar: window days + conversation source
        filters = QHBoxLayout()
        filters.setSpacing(8)
        win_pill = QFrame()
        win_pill.setObjectName("pillGroup")
        win_layout = QHBoxLayout(win_pill)
        win_layout.setContentsMargins(3, 3, 3, 3)
        win_layout.setSpacing(2)
        self.window_group = QButtonGroup(self)
        self._win_buttons: dict[int, QPushButton] = {}
        for key in (7, 30, 0):
            btn = QPushButton(tr(f"speed.win.{key}"))
            btn.setCheckable(True)
            btn.setObjectName("modeButton")
            btn.setProperty("windowDays", key)
            self.window_group.addButton(btn)
            win_layout.addWidget(btn)
            self._win_buttons[key] = btn
            if key == 7:
                btn.setChecked(True)
        filters.addWidget(win_pill)
        filters.addStretch(1)

        src_pill = QFrame()
        src_pill.setObjectName("pillGroup")
        src_layout = QHBoxLayout(src_pill)
        src_layout.setContentsMargins(3, 3, 3, 3)
        src_layout.setSpacing(2)
        self.source_group = QButtonGroup(self)
        self._src_buttons: dict[str, QPushButton] = {}
        for key in ("all", "main", "subagent"):
            btn = QPushButton(tr(f"speed.src.{key}"))
            btn.setCheckable(True)
            btn.setObjectName("modeButton")
            btn.setProperty("sourceFilter", key)
            self.source_group.addButton(btn)
            src_layout.addWidget(btn)
            self._src_buttons[key] = btn
            if key == "all":
                btn.setChecked(True)
        filters.addWidget(src_pill)
        layout.addLayout(filters)

        # Upper card: median speed/TTFT/duration bars
        compare_card = QFrame()
        compare_card.setObjectName("card")
        c_layout = QVBoxLayout(compare_card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(10)
        c_head = QHBoxLayout()
        self.compare_title = QLabel(tr("speed.title.speed"))
        self.compare_title.setObjectName("sectionTitle")
        c_head.addWidget(self.compare_title)
        c_head.addStretch(1)

        metric_pill = QFrame()
        metric_pill.setObjectName("pillGroup")
        m_layout = QHBoxLayout(metric_pill)
        m_layout.setContentsMargins(3, 3, 3, 3)
        m_layout.setSpacing(2)
        self.metric_group = QButtonGroup(self)
        self._metric_buttons: dict[str, QPushButton] = {}
        for key in ("speed", "ttft", "duration"):
            btn = QPushButton(tr(f"speed.metric.{key}"))
            btn.setCheckable(True)
            btn.setObjectName("modeButton")
            btn.setProperty("metricKey", key)
            self.metric_group.addButton(btn)
            m_layout.addWidget(btn)
            self._metric_buttons[key] = btn
            if key == "speed":
                btn.setChecked(True)
        c_head.addWidget(metric_pill)
        c_layout.addLayout(c_head)

        self.bar_chart = SpeedBarChart()
        c_layout.addWidget(self.bar_chart)
        self.compare_note = QLabel(tr("speed.note"))
        self.compare_note.setObjectName("muted")
        self.compare_note.setWordWrap(True)
        c_layout.addWidget(self.compare_note)
        layout.addWidget(compare_card)

        # Lower card: single model trend
        trend_card = QFrame()
        trend_card.setObjectName("card")
        t_layout = QVBoxLayout(trend_card)
        t_layout.setContentsMargins(16, 14, 16, 14)
        t_layout.setSpacing(10)
        t_head = QHBoxLayout()
        self._trend_title = QLabel(tr("speed.trend_title"))
        self._trend_title.setObjectName("sectionTitle")
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(240)
        t_head.addWidget(self._trend_title)
        t_head.addStretch(1)
        t_head.addWidget(self.model_combo)
        t_layout.addLayout(t_head)

        self.trend_chart = SpeedTrendChart()
        t_layout.addWidget(self.trend_chart)
        layout.addWidget(trend_card)
        layout.addStretch(1)
        self.setWidget(body)

        self.window_group.buttonClicked.connect(lambda _b: self._refresh())
        self.source_group.buttonClicked.connect(self._on_source_clicked)
        self.metric_group.buttonClicked.connect(lambda _b: self._refresh())
        self.model_combo.currentIndexChanged.connect(lambda _i: self._refresh_trend())
        self.bar_chart.model_selected.connect(self._select_model)

    def retranslate(self) -> None:
        for key, btn in self._win_buttons.items():
            btn.setText(tr(f"speed.win.{key}"))
        for key, btn in self._src_buttons.items():
            btn.setText(tr(f"speed.src.{key}"))
        for key, btn in self._metric_buttons.items():
            btn.setText(tr(f"speed.metric.{key}"))
        self.compare_note.setText(tr("speed.note"))
        self._trend_title.setText(tr("speed.trend_title"))
        self._refresh()

    def _on_source_clicked(self, button: QPushButton) -> None:
        self._refresh()
        self.source_changed.emit(str(button.property("sourceFilter") or "all"))

    def set_source_filter(self, source_key: str) -> None:
        for btn in self.source_group.buttons():
            if str(btn.property("sourceFilter") or "all") == source_key:
                if not btn.isChecked():
                    btn.setChecked(True)
                    self._refresh()
                break

    def set_theme(self, theme: str) -> None:
        self.bar_chart.set_theme(theme)
        self.trend_chart.set_theme(theme)

    def set_conversations(self, conversations: list) -> None:
        self._conversations = list(conversations)
        self._refresh()

    def _window_days(self) -> int | None:
        btn = self.window_group.checkedButton()
        val = int(btn.property("windowDays")) if btn else 7
        return None if val <= 0 else val

    def _source_filter(self) -> str:
        btn = self.source_group.checkedButton()
        return str(btn.property("sourceFilter") or "all") if btn else "all"

    def _metric(self) -> str:
        btn = self.metric_group.checkedButton()
        return str(btn.property("metricKey") or "speed") if btn else "speed"

    def _select_model(self, label: str) -> None:
        idx = self.model_combo.findData(label)
        if idx >= 0 and idx != self.model_combo.currentIndex():
            self.model_combo.setCurrentIndex(idx)

    def _refresh(self) -> None:
        metric = self._metric()
        self.compare_title.setText(tr(f"speed.title.{metric}"))
        groups = speed_stats.compute_speed_groups(
            self._conversations,
            metric=metric,
            window_days=self._window_days(),
            source_filter=self._source_filter(),
        )
        previous = self.model_combo.currentData()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for group in groups:
            self.model_combo.addItem(group.label, group.label)
        idx = self.model_combo.findData(previous)
        self.model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.model_combo.blockSignals(False)

        selected = str(self.model_combo.currentData() or "")
        self.bar_chart.set_data(groups, selected=selected)
        self._refresh_trend(groups=groups)

    def _refresh_trend(self, *, groups: list[SpeedGroup] | None = None) -> None:
        metric = self._metric()
        selected = str(self.model_combo.currentData() or "")
        points = speed_stats.compute_speed_trend(
            self._conversations,
            model_label=selected,
            metric=metric,
            window_days=self._window_days(),
            source_filter=self._source_filter(),
        )
        self.trend_chart.set_data(points, metric=metric, label=selected)
        if groups is not None:
            self.bar_chart.set_data(groups, selected=selected)
