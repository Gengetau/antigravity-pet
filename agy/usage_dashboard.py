"""Usage dashboard tab for the Token Meter: subscription ROI, Total/Today/Month/Year
hero cards, weighted cache ratio, quota windows, equivalent cost, and activity heatmap.
"""

from __future__ import annotations

import time
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

HEATMAP_THEMES = {
    "light": ("#ECEEF3", "#DDD6FE", "#C4B5FD", "#8B5CF6", "#6D28D9"),
    "dark": ("#1F2430", "#312E81", "#4F46E5", "#7C3AED", "#A78BFA"),
}
LEVEL_COLORS = HEATMAP_THEMES["light"]
CELL = 12
GAP = 3
MONTH_CELL = 46
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


def _fmt_compact(value: float) -> str:
    n = float(value)
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{int(round(n)):,}"


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
        self.theme = "light"
        self.month = _month_start(date.today())
        self.end = date.today()
        self.start = self.end - timedelta(days=370)
        self._cells: list[tuple[QRectF, date, int]] = []

    def set_theme(self, theme: str) -> None:
        self.theme = theme if theme in HEATMAP_THEMES else "light"
        self.update()

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
        self.start = min(first, self.end - timedelta(days=370))
        self.start -= timedelta(days=self.start.weekday())
        self.updateGeometry()
        self.update()

    def _weeks(self) -> int:
        return (self.end - self.start).days // 7 + 1

    def sizeHint(self) -> QSize:
        if self.span == "month":
            step = MONTH_CELL + MONTH_GAP
            return QSize(7 * step, 22 + 6 * step)
        return QSize(34 + self._weeks() * (CELL + GAP), 24 + 7 * (CELL + GAP))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = HEATMAP_THEMES.get(self.theme, HEATMAP_THEMES["light"])
        dark = self.theme == "dark"
        muted_pen = QColor("#9CA3AF" if dark else "#6B7280")
        today_pen = QColor("#E5E7EB" if dark else "#6D28D9")
        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)
        if self.span == "month":
            self._paint_month(painter, palette, muted_pen, today_pen)
            return
        left, top = 34, 20
        visible = {d: v for d, v in self.values.items() if self.start <= d <= self.end}
        peak = max(visible.values(), default=0)
        self._cells = []
        painter.setPen(muted_pen)
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
                painter.setPen(muted_pen)
                painter.drawText(QPointF(x, top - 6), f"{day.month}月")
            value = visible.get(day, 0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette[_level(value, peak)]))
            rect = QRectF(x, y, CELL, CELL)
            painter.drawRoundedRect(rect, 2.5, 2.5)
            self._cells.append((rect, day, value))
            day += timedelta(days=1)
        if day > self.end and self.end == date.today():
            for rect, cell_day, _value in self._cells:
                if cell_day == self.end:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(today_pen, 1.3))
                    painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)

    def _paint_month(self, painter: QPainter, palette: tuple[str, ...], muted_pen: QColor, today_pen: QColor) -> None:
        step = MONTH_CELL + MONTH_GAP
        top = 20
        first = self.month
        following = _shift_month(first, 1)
        month_values = {d: v for d, v in self.values.items() if first <= d < following}
        peak = max(month_values.values(), default=0)
        self._cells = []
        painter.setPen(muted_pen)
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
            painter.setBrush(QColor(palette[level]))
            painter.drawRoundedRect(rect, 6, 6)
            if day == today:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(today_pen, 1.6))
                painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 7, 7)
            painter.setPen(QColor("#FFFFFF") if level >= 3 else muted_pen)
            painter.drawText(rect.adjusted(5, 3, -3, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, str(day.day))
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


class _PeriodCard(QFrame):
    """Total / Today / Month / Year hero stat card."""

    def __init__(self, title: str, tag: str, tag_id: str) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        top = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        badge = QLabel(tag)
        badge.setObjectName(tag_id)
        top.addWidget(lbl)
        top.addStretch(1)
        top.addWidget(badge)
        layout.addLayout(top)

        self.value = QLabel("—")
        self.value.setObjectName("heroValue")
        self.sub = QLabel("—")
        self.sub.setObjectName("cardDetail")
        self.cost = QLabel("≈ $0")
        self.cost.setObjectName("cardDetail")
        layout.addWidget(self.value)
        layout.addWidget(self.sub)
        layout.addWidget(self.cost)


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
        layout.setContentsMargins(14, 10, 14, 10)
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
        self.bar.setFixedHeight(7)
        layout.addWidget(self.bar)

    def set_value(self, remaining_pct: float | None, reset_text: str) -> None:
        if remaining_pct is None:
            self.detail.setText("暂无数据")
            self.bar.setValue(0)
            return
        self.detail.setText(f"剩余 {remaining_pct:.0f}%" + (f" · {reset_text}" if reset_text else ""))
        self.bar.setValue(int(max(0.0, min(100.0, remaining_pct)) * 10))
        color = "#10B981" if remaining_pct >= 40 else "#F59E0B" if remaining_pct >= 20 else "#EF4444"
        self.bar.setStyleSheet(f"QProgressBar::chunk{{background:{color};border-radius:3px;}}")


class UsageDashboard(QScrollArea):
    """The 'Token 统计' overview dashboard tab."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._conversations: list = []
        self._source: str = ""
        self._user_tier_name: str = ""
        self._updated_at: float | None = None
        self._tier_expanded = False

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(12)

        # 1. Subscription Tier & ROI Banner
        self.tier_card = QFrame()
        self.tier_card.setObjectName("card")
        tier_layout = QVBoxLayout(self.tier_card)
        tier_layout.setContentsMargins(14, 10, 14, 10)
        tier_layout.setSpacing(8)
        tier_head = QHBoxLayout()
        self.tier_label = QLabel("💎 订阅档位暂未识别（连接 Antigravity 语言服务后自动同步）")
        self.tier_label.setObjectName("tierBannerText")
        self.tier_price = QLabel("")
        self.tier_price.setObjectName("tierPricePill")
        self.tier_price.setVisible(False)
        self.tier_toggle = QPushButton("详情 ▼")
        self.tier_toggle.setObjectName("ghostSmall")
        self.tier_toggle.clicked.connect(self._toggle_tier_detail)
        tier_head.addWidget(self.tier_label)
        tier_head.addStretch(1)
        tier_head.addWidget(self.tier_price)
        tier_head.addWidget(self.tier_toggle)
        tier_layout.addLayout(tier_head)

        self.tier_detail_box = QWidget()
        self.tier_detail_box.setObjectName("tierDetailBox")
        self.tier_detail_box.setVisible(False)
        td_layout = QVBoxLayout(self.tier_detail_box)
        td_layout.setContentsMargins(0, 4, 0, 2)
        td_layout.setSpacing(6)
        self.tier_detail_text = QLabel("")
        self.tier_detail_text.setObjectName("muted")
        self.tier_detail_text.setWordWrap(True)
        self.tier_roi_bar = QProgressBar()
        self.tier_roi_bar.setRange(0, 1000)
        self.tier_roi_bar.setTextVisible(False)
        self.tier_roi_bar.setFixedHeight(6)
        td_layout.addWidget(self.tier_detail_text)
        td_layout.addWidget(self.tier_roi_bar)
        tier_layout.addWidget(self.tier_detail_box)
        layout.addWidget(self.tier_card)

        # 2. Four Hero Period Cards (Total / Today / Month / Year)
        hero_grid = QHBoxLayout()
        hero_grid.setSpacing(10)
        self.hero_total = _PeriodCard("累计处理 Token\n含缓存读取", "Total", "tagViolet")
        self.hero_today = _PeriodCard("今日使用", "Today", "tagTeal")
        self.hero_month = _PeriodCard("本月使用", "Month", "tagIndigo")
        self.hero_year = _PeriodCard("年度使用", "Year", "tagSlate")
        for card in (self.hero_total, self.hero_today, self.hero_month, self.hero_year):
            hero_grid.addWidget(card, 1)
        layout.addLayout(hero_grid)

        # 3. Weighted Input / Cache Breakdown Bar
        cache_card = QFrame()
        cache_card.setObjectName("card")
        c_layout = QVBoxLayout(cache_card)
        c_layout.setContentsMargins(14, 11, 14, 11)
        c_layout.setSpacing(8)
        c_row = QHBoxLayout()
        self.cache_split_label = QLabel("输入(未缓存) —   缓存读取 —   总输入(输入+缓存) —   输出 —")
        self.cache_split_label.setObjectName("cardDetail")
        self.cache_split_label.setWordWrap(True)
        self.cache_ratio_label = QLabel("缓存读取占比 —")
        self.cache_ratio_label.setObjectName("accentLabel")
        c_row.addWidget(self.cache_split_label, 1)
        c_row.addWidget(self.cache_ratio_label)
        c_layout.addLayout(c_row)
        self.cache_share_bar = QProgressBar()
        self.cache_share_bar.setRange(0, 1000)
        self.cache_share_bar.setTextVisible(False)
        self.cache_share_bar.setFixedHeight(7)
        c_layout.addWidget(self.cache_share_bar)
        c_note = self._muted("按当前筛选范围总缓存读取 / 总输入（未命中缓存输入 + 缓存读取）加权计算。")
        c_layout.addWidget(c_note)
        layout.addWidget(cache_card)

        # 4. Dual Quota Windows (5h / Weekly)
        windows = QHBoxLayout()
        windows.setSpacing(10)
        self.window_5h = _Window("5 小时窗口")
        self.window_week = _Window("每周额度")
        windows.addWidget(self.window_5h, 1)
        windows.addWidget(self.window_week, 1)
        layout.addLayout(windows)

        # 5. Token Activity Heatmap Card (matches Screenshot 2 bottom block)
        heat_card = QFrame()
        heat_card.setObjectName("card")
        h_layout = QVBoxLayout(heat_card)
        h_layout.setContentsMargins(14, 12, 14, 12)
        h_layout.setSpacing(10)

        controls = QHBoxLayout()
        heading = QLabel("Token 活动")
        heading.setObjectName("sectionTitle")
        self.first_day_label = self._muted("")
        controls.addWidget(heading)
        controls.addSpacing(8)
        controls.addWidget(self.first_day_label)
        controls.addStretch(1)

        mode_pill = QFrame()
        mode_pill.setObjectName("pillGroup")
        mp_layout = QHBoxLayout(mode_pill)
        mp_layout.setContentsMargins(3, 3, 3, 3)
        mp_layout.setSpacing(2)
        self.mode_group = QButtonGroup(self)
        for key, label in (("day", "每天"), ("week", "每周"), ("total", "累计总量")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("mode", key)
            self.mode_group.addButton(button)
            mp_layout.addWidget(button)
            if key == "day":
                button.setChecked(True)
        controls.addWidget(mode_pill)
        h_layout.addLayout(controls)

        nav = QHBoxLayout()
        span_pill = QFrame()
        span_pill.setObjectName("pillGroup")
        sp_layout = QHBoxLayout(span_pill)
        sp_layout.setContentsMargins(3, 3, 3, 3)
        sp_layout.setSpacing(2)
        self.span_group = QButtonGroup(self)
        for key, label in (("month", "按月"), ("year", "按年")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("span", key)
            self.span_group.addButton(button)
            sp_layout.addWidget(button)
            if key == "month":
                button.setChecked(True)
        nav.addWidget(span_pill)
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
        self.model_box = QComboBox()
        self.model_box.addItem("全部模型", "")
        self.metric_box = QComboBox()
        for key, label in METRICS.items():
            self.metric_box.addItem(label, key)
        nav.addWidget(self.model_box)
        nav.addWidget(self.metric_box)
        h_layout.addLayout(nav)

        self.heatmap = Heatmap()
        heat_scroll = QScrollArea()
        heat_scroll.setWidget(self.heatmap)
        heat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        heat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        heat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        heat_scroll.setFixedHeight(self.heatmap.sizeHint().height() + 18)
        self.heat_scroll = heat_scroll
        h_layout.addWidget(heat_scroll)

        legend = QHBoxLayout()
        legend.addStretch(1)
        legend.addWidget(self._muted("少"))
        self._legend_swatches: list[QLabel] = []
        for color in HEATMAP_THEMES["light"]:
            swatch = QLabel()
            swatch.setFixedSize(CELL, CELL)
            swatch.setStyleSheet(f"background:{color};border-radius:2px;")
            self._legend_swatches.append(swatch)
            legend.addWidget(swatch)
        legend.addWidget(self._muted("多"))
        h_layout.addLayout(legend)
        layout.addWidget(heat_card)

        # 6. Streak & Peak Stats Strip
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

        # 7. Equivalent API Cost Card
        cost = QFrame()
        cost.setObjectName("card")
        cost_layout = QVBoxLayout(cost)
        cost_layout.setContentsMargins(14, 12, 14, 12)
        cost_layout.setSpacing(8)
        cost_head = QHBoxLayout()
        cost_title = QLabel("等效 API 费用明细")
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
        self.cost_rows.setVerticalSpacing(4)
        cost_layout.addLayout(self.cost_rows)
        self.cost_note = self._muted("")
        self.cost_note.setWordWrap(True)
        cost_layout.addWidget(self.cost_note)
        layout.addWidget(cost)

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

    # ----- theme & UI toggles -----------------------------------------------

    def set_theme(self, theme: str) -> None:
        self.heatmap.set_theme(theme)
        palette = HEATMAP_THEMES.get(theme, HEATMAP_THEMES["light"])
        for swatch, color in zip(self._legend_swatches, palette):
            swatch.setStyleSheet(f"background:{color};border-radius:2px;")

    def _toggle_tier_detail(self) -> None:
        self._tier_expanded = not self._tier_expanded
        self.tier_detail_box.setVisible(self._tier_expanded)
        self.tier_toggle.setText("收起 ▲" if self._tier_expanded else "详情 ▼")

    # ----- data -------------------------------------------------------------

    def set_quota(self, five_hour: tuple[float | None, str], weekly: tuple[float | None, str]) -> None:
        self.window_5h.set_value(*five_hour)
        self.window_week.set_value(*weekly)

    def set_conversations(
        self,
        conversations: list,
        *,
        source: str = "",
        user_tier_name: str = "",
        updated_at: float | None = None,
    ) -> None:
        self._conversations = list(conversations)
        self._source = source
        self._user_tier_name = user_tier_name
        self._updated_at = updated_at
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
        self.first_day_label.setText(
            f"首次使用：{stats.first_day:%Y年%m月%d日}" if stats.first_day else ""
        )
        self._show_hero_and_cost(today)

    def _show_hero_and_cost(self, today: date) -> None:
        try:
            table = pricing.load_table()
        except (OSError, ValueError, KeyError) as error:
            self.cost_total.setText("—")
            self.cost_note.setText(f"读不到价格表 assets/pricing.json：{error}")
            return
        rate = table.usd_to_cny
        report = pricing.compute(self._conversations, table)

        month_first = _month_start(today)
        year_first = date(today.year, 1, 1)
        total_tok = fresh_tok = cache_tok = output_tok = 0
        today_tok = month_tok = year_tok = 0
        today_convs = 0
        active_days: set[date] = set()
        year_days: set[date] = set()
        for conv in self._conversations:
            conv_today = False
            for step in getattr(conv, "steps", ()) or ():
                tot = int(getattr(step, "total_tokens", 0) or 0)
                inp = int(getattr(step, "input_tokens", 0) or 0)
                cac = int(getattr(step, "cache_read_tokens", 0) or 0)
                out = int(getattr(step, "output_tokens", 0) or 0)
                total_tok += tot
                fresh_tok += inp
                cache_tok += cac
                output_tok += out
                if step.created_ms:
                    d = usage_stats.local_day(step.created_ms)
                    active_days.add(d)
                    if d == today:
                        today_tok += tot
                        conv_today = True
                    if d >= month_first:
                        month_tok += tot
                    if d >= year_first:
                        year_tok += tot
                        year_days.add(d)
            if conv_today:
                today_convs += 1

        prompt_tok = fresh_tok + cache_tok
        cache_ratio = (cache_tok / prompt_tok * 100.0) if prompt_tok else 0.0
        self.cache_split_label.setText(
            f"输入(未缓存) {_fmt_compact(fresh_tok)}   "
            f"缓存读取 {_fmt_compact(cache_tok)}   "
            f"总输入(输入+缓存) {_fmt_compact(prompt_tok)}   "
            f"输出 {_fmt_compact(output_tok)}"
        )
        self.cache_ratio_label.setText(f"缓存读取占比 {cache_ratio:.1f}%")
        self.cache_share_bar.setValue(int(min(100.0, cache_ratio) * 10))

        n_days = max(1, len(active_days))
        effective_month_start = max(month_first, min(active_days)) if active_days else month_first
        month_days = max(1, (today - min(today, effective_month_start)).days + 1)
        today_usd = report.daily.get(today, 0.0)
        month_usd = report.spent_since(month_first)
        year_usd = report.spent_since(year_first)

        self.hero_total.value.setText(_fmt_compact(total_tok))
        self.hero_total.sub.setText(f"{total_tok:,} Tokens")
        self.hero_total.cost.setText(
            f"≈ {pricing.format_usd_cny(report.total_usd, rate)} · 日均 {pricing.format_usd(report.total_usd / n_days)}"
        )

        self.hero_today.value.setText(_fmt_compact(today_tok))
        self.hero_today.sub.setText(f"{today_convs} 会话活跃")
        self.hero_today.cost.setText(f"≈ {pricing.format_usd_cny(today_usd, rate)}")

        self.hero_month.value.setText(_fmt_compact(month_tok))
        self.hero_month.sub.setText(f"日均约 {_fmt_compact(month_tok / month_days)}")
        self.hero_month.cost.setText(
            f"≈ {pricing.format_usd_cny(month_usd, rate)} · 日均 {pricing.format_usd(month_usd / month_days)}"
        )

        self.hero_year.value.setText(_fmt_compact(year_tok))
        self.hero_year.sub.setText(f"{len(year_days)} 天活动记录")
        self.hero_year.cost.setText(
            f"≈ {pricing.format_usd_cny(year_usd, rate)} · 日均 {pricing.format_usd(year_usd / max(1, len(year_days)))}"
        )

        # Subscription banner update
        plan = table.find_subscription(self._user_tier_name)
        freshness = "刚刚更新" if (self._updated_at is None or time.time() - self._updated_at < 60) else "已同步"
        if self._user_tier_name:
            if self._source == "transcript":
                self.tier_label.setText(f"💎 {self._user_tier_name} · 历史已记录（当前离线统计）")
            else:
                self.tier_label.setText(f"💎 {self._user_tier_name} · 已自动识别 · {freshness}")
            if plan and plan.monthly_usd > 0:
                self.tier_price.setText(f"${plan.monthly_usd:,.2f}/月 (≈ {pricing.format_cny(plan.monthly_usd, rate)} CNY)")
                self.tier_price.setVisible(True)
                roi_pct = min(999.0, month_usd / plan.monthly_usd * 100.0)
                self.tier_roi_bar.setValue(int(min(100.0, roi_pct) * 10))
                self.tier_detail_text.setText(
                    f"本月等效 API 消耗 {pricing.format_usd_cny(month_usd, rate)}（占订阅月费 {roi_pct:.0f}%），"
                    f"缓存读取累计省下 {pricing.format_usd_cny(report.cache_saved_usd, rate)}。"
                )
            else:
                self.tier_price.setVisible(False)
                self.tier_roi_bar.setValue(0)
                self.tier_detail_text.setText(
                    f"本月等效 API 消耗 {pricing.format_usd_cny(month_usd, rate)}，缓存省下 {pricing.format_usd_cny(report.cache_saved_usd, rate)}。"
                )
        else:
            self.tier_label.setText("💎 订阅档位待同步（在 Antigravity 插件页开关一次 AGY 桌宠或重开 IDE 后自动识别）")
            self.tier_price.setVisible(False)
            self.tier_roi_bar.setValue(0)
            self.tier_detail_text.setText(
                f"当前按离线记录统计：本月等效 API 消耗 {pricing.format_usd_cny(month_usd, rate)}，"
                f"缓存读取累计省下 {pricing.format_usd_cny(report.cache_saved_usd, rate)}。"
            )

        self.cost_total.setText(pricing.format_usd_cny(report.total_usd, rate))
        self.cost_today.value.setText(pricing.format_usd(today_usd))
        self.cost_week.value.setText(pricing.format_usd(report.spent_since(today - timedelta(days=6))))
        self.cost_month.value.setText(pricing.format_usd(month_usd))
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
                pricing.format_usd_cny(item.total_usd, rate) if item.priced else "未定价",
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
            "按官方 API 标价折算（汇率按 1 USD = "
            f"{rate:.2f} CNY 估算），每一步用当天生效价格；输入只算未命中缓存部分，缓存读按缓存价，输出含思考。{estimated}"
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
            "启用本机用量账本后，超出最近 40 条或已删除的历史会话仍会累计保留。"
        )
