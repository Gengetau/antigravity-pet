"""Usage dashboard tab for the Token Meter: totals, streaks, quota windows and
a GitHub-style daily activity heatmap."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from . import pricing, usage_stats
from .usage_stats import METRICS, UsageStats

LEVEL_COLORS = ("#1f2430", "#0e4429", "#006d32", "#26a641", "#39d353")
CELL = 12
GAP = 3
MONTH_CELL = 46  # the month calendar uses bigger cells
MONTH_GAP = 6
WEEKDAYS = "一二三四五六日"


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _shift_month(first: date, months: int) -> date:
    index = first.year * 12 + first.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _level(value: int, top: int) -> int:
    if value <= 0 or top <= 0:
        return 0
    ratio = value / top
    return 1 if ratio < 0.25 else 2 if ratio < 0.5 else 3 if ratio < 0.75 else 4


class Heatmap(QWidget):
    """Daily activity: one month as a calendar (default), or a whole year of
    weeks with Monday on top."""

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.values: dict[date, int] = {}
        self.mode = "day"  # day / week / total
        self.unit = "token"
        self.span = "month"  # month / year
        self.month = _month_start(date.today())
        self.end = date.today()
        self.start = self.end - timedelta(days=370)
        self._cells: list[tuple[QRectF, date, int]] = []

    def set_span(self, span: str, month: date | None = None) -> None:
        self.span = span
        if month is not None:
            self.month = _month_start(month)
        self.updateGeometry()
        self.update()

    def _month_rows(self) -> int:
        first = self.month
        days = (_shift_month(first, 1) - first).days
        return (first.weekday() + days + 6) // 7

    def set_data(self, values: dict[date, int], *, mode: str, unit: str, end: date | None = None) -> None:
        self.values, self.mode, self.unit = values, mode, unit
        self.end = end or date.today()
        first = min(values) if values else self.end
        # Always show at least a year; go further back if data is older.
        self.start = min(first, self.end - timedelta(days=370))
        self.start -= timedelta(days=self.start.weekday())
        self.updateGeometry()
        self.update()

    def _weeks(self) -> int:
        return (self.end - self.start).days // 7 + 1

    def sizeHint(self) -> QSize:
        if self.span == "month":
            step = MONTH_CELL + MONTH_GAP
            return QSize(7 * step, 22 + 6 * step)  # room for six week rows
        return QSize(34 + self._weeks() * (CELL + GAP), 24 + 7 * (CELL + GAP))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)
        if self.span == "month":
            self._paint_month(painter)
            return
        left, top = 34, 20
        visible = {d: v for d, v in self.values.items() if self.start <= d <= self.end}
        peak = max(visible.values(), default=0)
        self._cells = []
        painter.setPen(QColor("#9ca3af"))
        for row, name in ((0, "一"), (2, "三"), (4, "五")):
            painter.drawText(QRectF(0, top + row * (CELL + GAP) - 2, left - 6, CELL + 4), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)
        last_month = None
        day = self.start
        while day <= self.end:
            week = (day - self.start).days // 7
            row = day.weekday()
            x = left + week * (CELL + GAP)
            y = top + row * (CELL + GAP)
            if row == 0 and day.month != last_month:
                last_month = day.month
                painter.setPen(QColor("#9ca3af"))
                painter.drawText(QPointF(x, top - 6), f"{day.month}月")
            value = visible.get(day, 0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(LEVEL_COLORS[_level(value, peak)]))
            rect = QRectF(x, y, CELL, CELL)
            painter.drawRoundedRect(rect, 2.5, 2.5)
            self._cells.append((rect, day, value))
            day += timedelta(days=1)
        if day > self.end and self.end == date.today():
            # Outline today so it is easy to find.
            for rect, cell_day, _value in self._cells:
                if cell_day == self.end:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor("#e5e7eb"), 1))
                    painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)

    def _paint_month(self, painter: QPainter) -> None:
        step = MONTH_CELL + MONTH_GAP
        top = 20
        first = self.month
        following = _shift_month(first, 1)
        month_values = {d: v for d, v in self.values.items() if first <= d < following}
        peak = max(month_values.values(), default=0)
        self._cells = []
        painter.setPen(QColor("#9ca3af"))
        for col, name in enumerate(WEEKDAYS):
            painter.drawText(QRectF(col * step, 0, MONTH_CELL, 16), Qt.AlignmentFlag.AlignCenter, name)
        today = date.today()
        day = first
        while day < following:
            index = first.weekday() + (day - first).days
            row, col = divmod(index, 7)
            rect = QRectF(col * step, top + row * step, MONTH_CELL, MONTH_CELL)
            value = month_values.get(day, 0)
            level = _level(value, peak)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(LEVEL_COLORS[level]))
            painter.drawRoundedRect(rect, 5, 5)
            if day == today:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#e5e7eb"), 1.2))
                painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 6, 6)
            painter.setPen(QColor("#0f1115") if level >= 3 else QColor("#9ca3af"))
            painter.drawText(rect.adjusted(4, 2, -3, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(day.day))
            self._cells.append((rect, day, value))
            day += timedelta(days=1)

    def mouseMoveEvent(self, event) -> None:
        point = event.position()
        for rect, day, value in self._cells:
            if rect.contains(point):
                if self.mode == "week":
                    label = f"{day:%Y-%m-%d} 所在周"
                elif self.mode == "total":
                    label = f"截至 {day:%Y-%m-%d} 累计"
                else:
                    label = f"{day:%Y-%m-%d}"
                QToolTip.showText(event.globalPosition().toPoint(), f"{label} · {self._fmt(value)}", self)
                return
        QToolTip.hideText()

    def _fmt(self, value: int) -> str:
        if self.unit == "steps":
            return f"{value:,} 步"
        if self.unit == "usd":
            return pricing.format_usd(value / usage_stats.MICRO)
        return f"{usage_stats.format_tokens_cn(value)} token" if value >= 10_000 else f"{value:,} token"


class _Stat(QFrame):
    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("statCell")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        self.value = QLabel("—")
        self.value.setObjectName("statValue")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(caption)
        label.setObjectName("statCaption")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value)
        layout.addWidget(label)


class _Window(QFrame):
    """One quota window: '5 小时窗口  剩余 62% · 11/22 18:20 重置' + a bar."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        row = QHBoxLayout()
        title = QLabel(caption)
        title.setObjectName("cardTitle")
        self.detail = QLabel("—")
        self.detail.setObjectName("cardDetail")
        row.addWidget(title)
        row.addStretch(1)
        row.addWidget(self.detail)
        layout.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        layout.addWidget(self.bar)

    def set_value(self, remaining_pct: float | None, reset_text: str) -> None:
        if remaining_pct is None:
            self.detail.setText("暂无数据")
            self.bar.setValue(0)
            return
        self.detail.setText(f"剩余 {remaining_pct:.0f}%" + (f" · {reset_text}" if reset_text else ""))
        self.bar.setValue(int(max(0.0, min(100.0, remaining_pct)) * 10))
        color = "#34D399" if remaining_pct >= 40 else "#FBBF24" if remaining_pct >= 20 else "#F87171"
        self.bar.setStyleSheet(f"QProgressBar::chunk{{background:{color};border-radius:3px;}}")


class UsageDashboard(QScrollArea):
    """The '用量看板' tab."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._conversations: list = []
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        stats = QFrame()
        stats.setObjectName("card")
        grid = QGridLayout(stats)
        grid.setContentsMargins(6, 6, 6, 6)
        self.stat_total = _Stat("累计 Token")
        self.stat_peak = _Stat("单日峰值")
        self.stat_task = _Stat("最长连续工作")
        self.stat_longest = _Stat("最长连续天数")
        self.stat_current = _Stat("当前连续天数")
        for index, cell in enumerate((self.stat_total, self.stat_peak, self.stat_task, self.stat_longest, self.stat_current)):
            grid.addWidget(cell, 0, index)
            grid.setColumnStretch(index, 1)
        layout.addWidget(stats)

        windows = QHBoxLayout()
        windows.setSpacing(10)
        self.window_5h = _Window("5 小时窗口")
        self.window_week = _Window("每周额度")
        windows.addWidget(self.window_5h, 1)
        windows.addWidget(self.window_week, 1)
        layout.addLayout(windows)

        cost = QFrame()
        cost.setObjectName("card")
        cost_layout = QVBoxLayout(cost)
        cost_layout.setContentsMargins(12, 10, 12, 10)
        cost_layout.setSpacing(8)
        cost_head = QHBoxLayout()
        cost_title = QLabel("等效 API 费用")
        cost_title.setObjectName("sectionTitle")
        self.cost_total = QLabel("—")
        self.cost_total.setObjectName("costTotal")
        cost_head.addWidget(cost_title)
        cost_head.addStretch(1)
        cost_head.addWidget(self.cost_total)
        cost_layout.addLayout(cost_head)
        cost_cells = QGridLayout()
        cost_cells.setHorizontalSpacing(6)
        self.cost_today = _Stat("今天")
        self.cost_week = _Stat("近 7 天")
        self.cost_month = _Stat("本月")
        self.cost_saved = _Stat("缓存省下")
        for index, cell in enumerate((self.cost_today, self.cost_week, self.cost_month, self.cost_saved)):
            cost_cells.addWidget(cell, 0, index)
            cost_cells.setColumnStretch(index, 1)
        cost_layout.addLayout(cost_cells)
        self.cost_rows = QGridLayout()
        self.cost_rows.setHorizontalSpacing(14)
        self.cost_rows.setVerticalSpacing(3)
        cost_layout.addLayout(self.cost_rows)
        self.cost_note = self._muted("")
        self.cost_note.setWordWrap(True)
        cost_layout.addWidget(self.cost_note)
        layout.addWidget(cost)

        controls = QHBoxLayout()
        heading = QLabel("Token 活动")
        heading.setObjectName("sectionTitle")
        controls.addWidget(heading)
        controls.addStretch(1)
        self.model_box = QComboBox()
        self.model_box.addItem("全部模型", "")
        self.metric_box = QComboBox()
        for key, label in METRICS.items():
            self.metric_box.addItem(label, key)
        controls.addWidget(self.model_box)
        controls.addWidget(self.metric_box)
        self.mode_group = QButtonGroup(self)
        for key, label in (("day", "每天"), ("week", "每周"), ("total", "累计总量")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("mode", key)
            self.mode_group.addButton(button)
            controls.addWidget(button)
            if key == "day":
                button.setChecked(True)
        layout.addLayout(controls)

        nav = QHBoxLayout()
        self.span_group = QButtonGroup(self)
        for key, label in (("month", "按月"), ("year", "按年")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("span", key)
            self.span_group.addButton(button)
            nav.addWidget(button)
            if key == "month":
                button.setChecked(True)
        nav.addSpacing(10)
        self.prev_month = QPushButton("‹")
        self.next_month = QPushButton("›")
        for button in (self.prev_month, self.next_month):
            button.setObjectName("modeButton")
            button.setFixedWidth(28)
        self.month_label = QLabel("")
        self.month_label.setObjectName("sectionTitle")
        nav.addWidget(self.prev_month)
        nav.addWidget(self.month_label)
        nav.addWidget(self.next_month)
        nav.addStretch(1)
        layout.addLayout(nav)

        self.heatmap = Heatmap()
        heat_scroll = QScrollArea()
        heat_scroll.setWidget(self.heatmap)
        heat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        heat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        heat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        heat_scroll.setFixedHeight(self.heatmap.sizeHint().height() + 18)
        self.heat_scroll = heat_scroll
        layout.addWidget(heat_scroll)

        legend = QHBoxLayout()
        legend.addStretch(1)
        legend.addWidget(self._muted("少"))
        for color in LEVEL_COLORS:
            swatch = QLabel()
            swatch.setFixedSize(CELL, CELL)
            swatch.setStyleSheet(f"background:{color};border-radius:2px;")
            legend.addWidget(swatch)
        legend.addWidget(self._muted("多"))
        layout.addLayout(legend)

        self.note = self._muted("")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)
        self.setWidget(body)

        self.model_box.currentIndexChanged.connect(self._refresh)
        self.metric_box.currentIndexChanged.connect(self._refresh)
        self.mode_group.buttonClicked.connect(lambda _b: self._refresh())
        self.span_group.buttonClicked.connect(lambda _b: self._refresh())
        self.prev_month.clicked.connect(lambda: self._move_month(-1))
        self.next_month.clicked.connect(lambda: self._move_month(1))

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("muted")
        return label

    # ----- data -------------------------------------------------------------

    def set_quota(self, five_hour: tuple[float | None, str], weekly: tuple[float | None, str]) -> None:
        self.window_5h.set_value(*five_hour)
        self.window_week.set_value(*weekly)

    def set_conversations(self, conversations: list, *, source: str = "") -> None:
        self._conversations = list(conversations)
        self._source = source
        labels = usage_stats.compute(self._conversations).models
        current = self.model_box.currentData()
        self.model_box.blockSignals(True)
        self.model_box.clear()
        self.model_box.addItem("全部模型", "")
        for label in labels:
            self.model_box.addItem(label, label)
        index = self.model_box.findData(current)
        self.model_box.setCurrentIndex(max(0, index))
        self.model_box.blockSignals(False)
        self._refresh()

    def _span(self) -> str:
        button = self.span_group.checkedButton()
        return str(button.property("span")) if button else "month"

    def _move_month(self, months: int) -> None:
        target = _shift_month(self.heatmap.month, months)
        if target > _month_start(date.today()):
            return
        self.heatmap.set_span(self.heatmap.span, target)
        self._refresh()

    def _mode(self) -> str:
        button = self.mode_group.checkedButton()
        return str(button.property("mode")) if button else "day"

    def _refresh(self) -> None:
        metric = self.metric_box.currentData() or "total"
        model = self.model_box.currentData() or ""
        stats = usage_stats.compute(self._conversations, metric=metric, model=model)
        self._show_stats(stats, metric)
        mode = self._mode()
        today = date.today()
        values = stats.daily
        if mode == "week":
            weeks = usage_stats.weekly(stats.daily)
            values = {}
            for monday, total in weeks.items():
                for offset in range(7):
                    values[monday + timedelta(days=offset)] = total
        elif mode == "total" and stats.first_day:
            values = usage_stats.cumulative(stats.daily, stats.first_day, today)
        unit = "steps" if metric == "steps" else "usd" if metric == "cost" else "token"
        span = self._span()
        self.heatmap.set_span(span)
        self.heatmap.set_data(values, mode=mode, unit=unit, end=today)
        month = self.heatmap.month
        self.month_label.setText(f"{month.year} 年 {month.month} 月")
        for widget in (self.prev_month, self.month_label, self.next_month):
            widget.setVisible(span == "month")
        self.next_month.setEnabled(month < _month_start(today))
        self.heat_scroll.setFixedHeight(self.heatmap.sizeHint().height() + 18)
        self.heat_scroll.horizontalScrollBar().setValue(self.heat_scroll.horizontalScrollBar().maximum())
        self._show_cost()

    def _show_cost(self) -> None:
        try:
            table = pricing.load_table()
        except (OSError, ValueError, KeyError) as error:
            self.cost_total.setText("—")
            self.cost_note.setText(f"读不到价格表 assets/pricing.json：{error}")
            return
        report = pricing.compute(self._conversations, table)
        today = date.today()
        self.cost_total.setText(pricing.format_usd(report.total_usd))
        self.cost_today.value.setText(pricing.format_usd(report.daily.get(today, 0.0)))
        self.cost_week.value.setText(pricing.format_usd(report.spent_since(today - timedelta(days=6))))
        self.cost_month.value.setText(pricing.format_usd(report.spent_since(_month_start(today))))
        self.cost_saved.value.setText(pricing.format_usd(report.cache_saved_usd))
        while self.cost_rows.count():
            item = self.cost_rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for col, title in enumerate(("模型", "输入", "缓存读", "输出", "金额")):
            label = self._muted(title)
            self.cost_rows.addWidget(label, 0, col, Qt.AlignmentFlag.AlignRight if col else Qt.AlignmentFlag.AlignLeft)
        for row, item in enumerate(report.rows, start=1):
            cells = (
                item.name,
                f"{usage_stats.format_tokens_cn(item.input_tokens)} · {pricing.format_usd(item.input_usd)}",
                f"{usage_stats.format_tokens_cn(item.cache_tokens)} · {pricing.format_usd(item.cache_usd)}",
                f"{usage_stats.format_tokens_cn(item.output_tokens)} · {pricing.format_usd(item.output_usd)}",
                pricing.format_usd(item.total_usd) if item.priced else "未定价",
            )
            for col, text in enumerate(cells):
                label = QLabel(text)
                if col == 4:
                    label.setObjectName("costValue")
                self.cost_rows.addWidget(label, row, col, Qt.AlignmentFlag.AlignRight if col else Qt.AlignmentFlag.AlignLeft)
        estimated = (
            f"其中 {pricing.format_usd(report.estimated_usd)} 来自离线日志里没记录模型的步骤，按 "
            f"{table.by_id(table.unknown_as).name if table.by_id(table.unknown_as) else table.unknown_as} 的价格估算。"
            if report.estimated_usd
            else ""
        )
        self.cost_note.setText(
            "按官方 API 标价（付费 Standard 档）折算，每一步用当天生效的价格；输入只算未命中缓存的部分，"
            f"缓存读按缓存价，输出含思考。{estimated}"
            "价格表在 assets/pricing.json，可以自己改。"
        )

    def _show_stats(self, stats: UsageStats, metric: str) -> None:
        if metric == "cost":
            self.stat_total.value.setText(pricing.format_usd(stats.total / usage_stats.MICRO))
            self.stat_peak.value.setText(pricing.format_usd(stats.peak_value / usage_stats.MICRO))
        elif metric == "steps":
            self.stat_total.value.setText(f"{stats.total:,}")
            self.stat_peak.value.setText(f"{stats.peak_value:,}")
        else:
            self.stat_total.value.setText(usage_stats.format_tokens_cn(stats.total))
            self.stat_peak.value.setText(usage_stats.format_tokens_cn(stats.peak_value))
        self.stat_peak.setToolTip(f"{stats.peak_day:%Y-%m-%d}" if stats.peak_day else "")
        self.stat_task.value.setText(usage_stats.format_duration(stats.longest_task_ms) if stats.longest_task_ms else "—")
        self.stat_longest.value.setText(f"{stats.longest_streak} 天")
        self.stat_current.value.setText(f"{stats.current_streak} 天")
        since = f"，最早一条在 {stats.first_day:%Y-%m-%d}" if stats.first_day else ""
        self.note.setText(
            f"按每一步的时间戳统计 {len(self._conversations)} 个会话、{stats.steps_counted:,} 步{since}。"
            "只包含 Token Meter 读得到的会话（最近的会话或本地日志），更早删除的会话不在内。"
            "“最长连续工作”是同一会话里步骤间隔不超过 5 分钟的最长一段，属于估算。"
        )
