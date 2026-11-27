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

from app.i18n import format_month_label, format_short_month, get_language, tr, weekday_labels
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
        weekdays = weekday_labels()
        painter.setPen(muted_pen)
        for row in (0, 2, 4):
            painter.drawText(QRectF(0, top + row * (CELL + GAP) - 2, left - 6, CELL + 4), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, weekdays[row])
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
                painter.drawText(QPointF(x, top - 6), format_short_month(day.month))
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
        for col, name in enumerate(weekday_labels()):
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
                day_str = f"{day:%Y-%m-%d}"
                if self.mode == "week":
                    label = tr("dash.heat.tip_week", day=day_str)
                elif self.mode == "total":
                    label = tr("dash.heat.tip_total", day=day_str)
                else:
                    label = day_str
                QToolTip.showText(event.globalPosition().toPoint(), f"{label} · {self._fmt(value)}", self)
                return
        QToolTip.hideText()

    def _fmt(self, value: int) -> str:
        if self.unit == "steps":
            return tr("dash.heat.steps_unit", val=value)
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
        self.title_label = lbl
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
        self.caption_label = label
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
        self.title_label = title
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
        self._last_pct: float | None = None
        self._last_reset: str = ""

    def set_value(self, remaining_pct: float | None, reset_text: str) -> None:
        self._last_pct = remaining_pct
        self._last_reset = reset_text
        if remaining_pct is None:
            self.detail.setText(tr("dash.win.none"))
            self.bar.setValue(0)
            return
        reset_part = f" · {reset_text}" if reset_text else ""
        self.detail.setText(tr("dash.win.left", pct=remaining_pct, reset=reset_part))
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
        self.tier_label = QLabel(tr("dash.tier.unknown_init"))
        self.tier_label.setObjectName("tierBannerText")
        self.tier_price = QLabel("")
        self.tier_price.setObjectName("tierPricePill")
        self.tier_price.setVisible(False)
        self.tier_toggle = QPushButton(tr("dash.detail.open"))
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
        self.hero_total = _PeriodCard(tr("dash.hero.total"), "Total", "tagViolet")
        self.hero_today = _PeriodCard(tr("dash.hero.today"), "Today", "tagTeal")
        self.hero_month = _PeriodCard(tr("dash.hero.month"), "Month", "tagIndigo")
        self.hero_year = _PeriodCard(tr("dash.hero.year"), "Year", "tagSlate")
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
        self.cache_split_label = QLabel(tr("dash.cache.split", fresh="—", cache="—", prompt="—", out="—"))
        self.cache_split_label.setObjectName("cardDetail")
        self.cache_split_label.setWordWrap(True)
        self.cache_ratio_label = QLabel(tr("dash.cache.ratio", pct=0.0))
        self.cache_ratio_label.setObjectName("accentLabel")
        c_row.addWidget(self.cache_split_label, 1)
        c_row.addWidget(self.cache_ratio_label)
        c_layout.addLayout(c_row)
        self.cache_share_bar = QProgressBar()
        self.cache_share_bar.setRange(0, 1000)
        self.cache_share_bar.setTextVisible(False)
        self.cache_share_bar.setFixedHeight(7)
        c_layout.addWidget(self.cache_share_bar)
        self._cache_note = self._muted(tr("dash.cache.note"))
        c_layout.addWidget(self._cache_note)
        layout.addWidget(cache_card)

        # 4. Dual Quota Windows (5h / Weekly)
        windows = QHBoxLayout()
        windows.setSpacing(10)
        self.window_5h = _Window(tr("dash.win.5h"))
        self.window_week = _Window(tr("dash.win.week"))
        windows.addWidget(self.window_5h, 1)
        windows.addWidget(self.window_week, 1)
        layout.addLayout(windows)

        # 5. Token Activity Heatmap Card
        heat_card = QFrame()
        heat_card.setObjectName("card")
        h_layout = QVBoxLayout(heat_card)
        h_layout.setContentsMargins(14, 12, 14, 12)
        h_layout.setSpacing(10)

        controls = QHBoxLayout()
        self._heat_heading = QLabel(tr("dash.heat.title"))
        self._heat_heading.setObjectName("sectionTitle")
        self.first_day_label = self._muted("")
        controls.addWidget(self._heat_heading)
        controls.addSpacing(8)
        controls.addWidget(self.first_day_label)
        controls.addStretch(1)

        mode_pill = QFrame()
        mode_pill.setObjectName("pillGroup")
        mp_layout = QHBoxLayout(mode_pill)
        mp_layout.setContentsMargins(3, 3, 3, 3)
        mp_layout.setSpacing(2)
        self.mode_group = QButtonGroup(self)
        self._mode_buttons: dict[str, QPushButton] = {}
        for key in ("day", "week", "total"):
            button = QPushButton(tr(f"dash.heat.{key}"))
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("mode", key)
            self.mode_group.addButton(button)
            mp_layout.addWidget(button)
            self._mode_buttons[key] = button
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
        self._span_buttons: dict[str, QPushButton] = {}
        for key in ("month", "year"):
            button = QPushButton(tr(f"dash.heat.{key}"))
            button.setCheckable(True)
            button.setObjectName("modeButton")
            button.setProperty("span", key)
            self.span_group.addButton(button)
            sp_layout.addWidget(button)
            self._span_buttons[key] = button
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
        self.model_box.addItem(tr("dash.heat.all_models"), "")
        self.metric_box = QComboBox()
        for key in METRICS:
            self.metric_box.addItem(tr(f"dash.metric.{key}"), key)
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
        self._legend_less = self._muted(tr("dash.heat.less"))
        legend.addWidget(self._legend_less)
        self._legend_swatches: list[QLabel] = []
        for color in HEATMAP_THEMES["light"]:
            swatch = QLabel()
            swatch.setFixedSize(CELL, CELL)
            swatch.setStyleSheet(f"background:{color};border-radius:2px;")
            self._legend_swatches.append(swatch)
            legend.addWidget(swatch)
        self._legend_more = self._muted(tr("dash.heat.more"))
        legend.addWidget(self._legend_more)
        h_layout.addLayout(legend)
        layout.addWidget(heat_card)

        # 6. Streak & Peak Stats Strip
        stats = QFrame()
        stats.setObjectName("card")
        grid = QGridLayout(stats)
        grid.setContentsMargins(6, 6, 6, 6)
        self.stat_total = _Stat(tr("dash.stat.total"))
        self.stat_peak = _Stat(tr("dash.stat.peak"))
        self.stat_task = _Stat(tr("dash.stat.task"))
        self.stat_longest = _Stat(tr("dash.stat.longest"))
        self.stat_current = _Stat(tr("dash.stat.current"))
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
        self._cost_title = QLabel(tr("dash.cost.title"))
        self._cost_title.setObjectName("sectionTitle")
        self.cost_total = QLabel("—")
        self.cost_total.setObjectName("costTotal")
        cost_head.addWidget(self._cost_title)
        cost_head.addStretch(1)
        cost_head.addWidget(self.cost_total)
        cost_layout.addLayout(cost_head)
        cost_cells = QGridLayout()
        cost_cells.setHorizontalSpacing(6)
        self.cost_today = _Stat(tr("dash.cost.today"))
        self.cost_week = _Stat(tr("dash.cost.week"))
        self.cost_month = _Stat(tr("dash.cost.month"))
        self.cost_saved = _Stat(tr("dash.cost.saved"))
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

    def retranslate(self) -> None:
        self.tier_toggle.setText(tr("dash.detail.close") if self._tier_expanded else tr("dash.detail.open"))
        self.hero_total.title_label.setText(tr("dash.hero.total"))
        self.hero_today.title_label.setText(tr("dash.hero.today"))
        self.hero_month.title_label.setText(tr("dash.hero.month"))
        self.hero_year.title_label.setText(tr("dash.hero.year"))
        self._cache_note.setText(tr("dash.cache.note"))
        self.window_5h.title_label.setText(tr("dash.win.5h"))
        self.window_week.title_label.setText(tr("dash.win.week"))
        self.window_5h.set_value(self.window_5h._last_pct, self.window_5h._last_reset)
        self.window_week.set_value(self.window_week._last_pct, self.window_week._last_reset)
        self._heat_heading.setText(tr("dash.heat.title"))
        for key, btn in self._mode_buttons.items():
            btn.setText(tr(f"dash.heat.{key}"))
        for key, btn in self._span_buttons.items():
            btn.setText(tr(f"dash.heat.{key}"))
        self.model_box.blockSignals(True)
        if self.model_box.count() > 0:
            self.model_box.setItemText(0, tr("dash.heat.all_models"))
        self.model_box.blockSignals(False)
        self.metric_box.blockSignals(True)
        for idx in range(self.metric_box.count()):
            mkey = str(self.metric_box.itemData(idx) or "total")
            self.metric_box.setItemText(idx, tr(f"dash.metric.{mkey}"))
        self.metric_box.blockSignals(False)
        self._legend_less.setText(tr("dash.heat.less"))
        self._legend_more.setText(tr("dash.heat.more"))
        self.stat_total.caption_label.setText(tr("dash.stat.total"))
        self.stat_peak.caption_label.setText(tr("dash.stat.peak"))
        self.stat_task.caption_label.setText(tr("dash.stat.task"))
        self.stat_longest.caption_label.setText(tr("dash.stat.longest"))
        self.stat_current.caption_label.setText(tr("dash.stat.current"))
        self._cost_title.setText(tr("dash.cost.title"))
        self.cost_today.caption_label.setText(tr("dash.cost.today"))
        self.cost_week.caption_label.setText(tr("dash.cost.week"))
        self.cost_month.caption_label.setText(tr("dash.cost.month"))
        self.cost_saved.caption_label.setText(tr("dash.cost.saved"))
        self._refresh()

    def set_theme(self, theme: str) -> None:
        self.heatmap.set_theme(theme)
        palette = HEATMAP_THEMES.get(theme, HEATMAP_THEMES["light"])
        for swatch, color in zip(self._legend_swatches, palette):
            swatch.setStyleSheet(f"background:{color};border-radius:2px;")

    def _toggle_tier_detail(self) -> None:
        self._tier_expanded = not self._tier_expanded
        self.tier_detail_box.setVisible(self._tier_expanded)
        self.tier_toggle.setText(tr("dash.detail.close") if self._tier_expanded else tr("dash.detail.open"))

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
        self.model_box.addItem(tr("dash.heat.all_models"), "")
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
        self.month_label.setText(format_month_label(month.year, month.month))
        for widget in (self.prev_month, self.month_label, self.next_month):
            widget.setVisible(span == "month")
        self.next_month.setEnabled(month < _month_start(today))
        self.heat_scroll.setFixedHeight(self.heatmap.sizeHint().height() + 18)
        self.heat_scroll.horizontalScrollBar().setValue(self.heat_scroll.horizontalScrollBar().maximum())
        if stats.first_day:
            day_fmt = f"{stats.first_day:%Y-%m-%d}" if get_language() == "en" else f"{stats.first_day:%Y年%m月%d日}"
            self.first_day_label.setText(tr("dash.heat.first_day", day=day_fmt))
        else:
            self.first_day_label.setText("")
        self._show_hero_and_cost(today)

    def _show_hero_and_cost(self, today: date) -> None:
        try:
            table = pricing.load_table()
        except (OSError, ValueError, KeyError) as error:
            self.cost_total.setText("—")
            self.cost_note.setText(tr("dash.cost.missing", error=error))
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
            tr(
                "dash.cache.split",
                fresh=_fmt_compact(fresh_tok),
                cache=_fmt_compact(cache_tok),
                prompt=_fmt_compact(prompt_tok),
                out=_fmt_compact(output_tok),
            )
        )
        self.cache_ratio_label.setText(tr("dash.cache.ratio", pct=cache_ratio))
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
            tr("dash.hero.daily_avg", cost=pricing.format_usd_cny(report.total_usd, rate), daily=pricing.format_usd(report.total_usd / n_days))
        )

        self.hero_today.value.setText(_fmt_compact(today_tok))
        self.hero_today.sub.setText(tr("dash.hero.active_convs", count=today_convs))
        self.hero_today.cost.setText(f"≈ {pricing.format_usd_cny(today_usd, rate)}")

        self.hero_month.value.setText(_fmt_compact(month_tok))
        self.hero_month.sub.setText(tr("dash.hero.avg_tok_day", tok=_fmt_compact(month_tok / month_days)))
        self.hero_month.cost.setText(
            tr("dash.hero.daily_avg", cost=pricing.format_usd_cny(month_usd, rate), daily=pricing.format_usd(month_usd / month_days))
        )

        self.hero_year.value.setText(_fmt_compact(year_tok))
        self.hero_year.sub.setText(tr("dash.hero.active_days", days=len(year_days)))
        self.hero_year.cost.setText(
            tr("dash.hero.daily_avg", cost=pricing.format_usd_cny(year_usd, rate), daily=pricing.format_usd(year_usd / max(1, len(year_days))))
        )

        # Subscription banner update
        plan = table.find_subscription(self._user_tier_name)
        freshness = tr("dash.fresh.just") if (self._updated_at is None or time.time() - self._updated_at < 60) else tr("dash.fresh.synced")
        month_cost_str = pricing.format_usd_cny(month_usd, rate)
        saved_cost_str = pricing.format_usd_cny(report.cache_saved_usd, rate)
        if self._user_tier_name:
            if self._source == "transcript":
                self.tier_label.setText(tr("dash.tier.offline", tier=self._user_tier_name))
            else:
                self.tier_label.setText(tr("dash.tier.synced", tier=self._user_tier_name, freshness=freshness))
            if plan and plan.monthly_usd > 0:
                self.tier_price.setText(tr("dash.tier.price", usd=plan.monthly_usd, cny=pricing.format_cny(plan.monthly_usd, rate)))
                self.tier_price.setVisible(True)
                roi_pct = min(999.0, month_usd / plan.monthly_usd * 100.0)
                self.tier_roi_bar.setValue(int(min(100.0, roi_pct) * 10))
                self.tier_detail_text.setText(tr("dash.tier.roi", month_cost=month_cost_str, roi=roi_pct, saved_cost=saved_cost_str))
            else:
                self.tier_price.setVisible(False)
                self.tier_roi_bar.setValue(0)
                self.tier_detail_text.setText(tr("dash.tier.no_plan", month_cost=month_cost_str, saved_cost=saved_cost_str))
        else:
            self.tier_label.setText(tr("dash.tier.pending"))
            self.tier_price.setVisible(False)
            self.tier_roi_bar.setValue(0)
            self.tier_detail_text.setText(tr("dash.tier.offline_detail", month_cost=month_cost_str, saved_cost=saved_cost_str))

        self.cost_total.setText(pricing.format_usd_cny(report.total_usd, rate))
        self.cost_today.value.setText(pricing.format_usd(today_usd))
        self.cost_week.value.setText(pricing.format_usd(report.spent_since(today - timedelta(days=6))))
        self.cost_month.value.setText(pricing.format_usd(month_usd))
        self.cost_saved.value.setText(pricing.format_usd(report.cache_saved_usd))
        while self.cost_rows.count():
            item = self.cost_rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for col, title in enumerate(
            (tr("meter.col.model"), tr("meter.col.input"), tr("meter.col.cache_read"), tr("meter.col.output"), tr("dash.cost.col_amount"))
        ):
            label = self._muted(title)
            self.cost_rows.addWidget(label, 0, col, Qt.AlignmentFlag.AlignRight if col else Qt.AlignmentFlag.AlignLeft)
        for row, item in enumerate(report.rows, start=1):
            cells = (
                item.name,
                f"{usage_stats.format_tokens_cn(item.input_tokens)} · {pricing.format_usd(item.input_usd)}",
                f"{usage_stats.format_tokens_cn(item.cache_tokens)} · {pricing.format_usd(item.cache_usd)}",
                f"{usage_stats.format_tokens_cn(item.output_tokens)} · {pricing.format_usd(item.output_usd)}",
                pricing.format_usd_cny(item.total_usd, rate) if item.priced else tr("dash.cost.unpriced"),
            )
            for col, text in enumerate(cells):
                label = QLabel(text)
                if col == 4:
                    label.setObjectName("costValue")
                self.cost_rows.addWidget(label, row, col, Qt.AlignmentFlag.AlignRight if col else Qt.AlignmentFlag.AlignLeft)
        estimated = (
            tr(
                "dash.cost.estimated",
                usd=pricing.format_usd(report.estimated_usd),
                model=table.by_id(table.unknown_as).name if table.by_id(table.unknown_as) else table.unknown_as,
            )
            if report.estimated_usd
            else ""
        )
        self.cost_note.setText(tr("dash.cost.note", rate=rate, estimated=estimated))

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
        self.stat_longest.value.setText(tr("dash.stat.days", days=stats.longest_streak))
        self.stat_current.value.setText(tr("dash.stat.days", days=stats.current_streak))
        since = tr("dash.note.since", day=f"{stats.first_day:%Y-%m-%d}") if stats.first_day else ""
        self.note.setText(tr("dash.note", convs=len(self._conversations), steps=stats.steps_counted, since=since))
