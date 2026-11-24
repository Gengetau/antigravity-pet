"""Desktop Token Meter v2: light/dark themed monitoring dashboard with
Token Overview + persistent ledger, Model/Tier Speed Comparison,
Model Cost & Share ranking, and Live Request steps.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import pricing, speed_stats
from .speed_chart import SpeedComparisonView
from .telemetry import LiveSnapshot, MeterReport, build_model_rows, format_reset_countdown, format_tokens
from .usage_dashboard import UsageDashboard

SOURCE_TEXT = {
    "ls": ("实时 · 本地语言服务", "#10B981"),
    "pet_live": ("实时 · AGY 桌宠插件", "#10B981"),
    "hud_live": ("实时 · 侧边栏桥接", "#0EA5E9"),
    "transcript": ("离线 · 本地会话日志（无配额、速率为估算）", "#D97706"),
}

TAB_ITEMS = (
    ("overview", "Token 统计"),
    ("speed", "速度对比"),
    ("models", "按模型 / 费用"),
    ("steps", "实时请求"),
)

LIGHT_QSS = """
QWidget { background: #F6F7FB; color: #111827; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #F6F7FB; border: none; }
QLabel#title { font-size: 18px; font-weight: 700; color: #111827; background: transparent; }
QLabel#badge { padding: 3px 10px; border-radius: 10px; background: #ECEFF4; font-size: 11px; font-weight: 600; }
QLabel#muted { color: #6B7280; background: transparent; }
QFrame#card { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; }
QWidget#tierDetailBox { background: transparent; }
QLabel#cardTitle { color: #6B7280; font-size: 11px; font-weight: 600; background: transparent; }
QLabel#cardValue { font-size: 20px; font-weight: 700; background: transparent; }
QLabel#heroValue { font-size: 25px; font-weight: 800; color: #111827; background: transparent; }
QLabel#cardDetail { color: #6B7280; font-size: 11px; background: transparent; }
QLabel#sectionTitle { font-size: 14px; font-weight: 700; color: #111827; background: transparent; }
QLabel#tierBannerText { font-size: 13px; font-weight: 700; color: #5B21B6; background: transparent; }
QLabel#tierPricePill { background: #F3E8FF; color: #6D28D9; border: 1px solid #DDD6FE; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 700; }
QLabel#accentLabel { color: #6D28D9; font-size: 12px; font-weight: 700; background: transparent; }
QLabel#tagViolet { color: #6D28D9; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#tagTeal { color: #0F766E; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#tagIndigo { color: #4338CA; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#tagSlate { color: #475569; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#costTotal { font-size: 18px; font-weight: 700; color: #6D28D9; background: transparent; }
QLabel#costValue { font-weight: 700; color: #6D28D9; background: transparent; }
QFrame#statCell { background: transparent; }
QLabel#statValue { font-size: 19px; font-weight: 700; color: #111827; background: transparent; }
QLabel#statCaption { color: #6B7280; font-size: 11px; background: transparent; }
QProgressBar { background: #ECEEF3; border: none; border-radius: 3px; }
QProgressBar::chunk { background: #7C3AED; border-radius: 3px; }
QFrame#pillGroup { background: #ECEFF4; border: 1px solid #E5E7EB; border-radius: 9px; }
QPushButton { background: #FFFFFF; color: #1F2937; border: 1px solid #D1D5DB; border-radius: 7px; padding: 5px 12px; font-weight: 600; }
QPushButton:hover { background: #F3F4F6; border-color: #9CA3AF; }
QPushButton#modeButton, QPushButton#navButton { background: transparent; border: none; color: #6B7280; padding: 5px 12px; border-radius: 6px; font-weight: 600; }
QPushButton#modeButton:hover, QPushButton#navButton:hover { color: #111827; background: rgba(255,255,255,0.55); }
QPushButton#modeButton:checked, QPushButton#navButton:checked { background: #FFFFFF; color: #111827; font-weight: 700; border: 1px solid #E5E7EB; }
QPushButton#ghostSmall { background: transparent; border: none; color: #6B7280; padding: 3px 8px; }
QPushButton#ghostSmall:hover { color: #111827; background: #F3F4F6; }
QComboBox { background: #FFFFFF; color: #111827; border: 1px solid #D1D5DB; border-radius: 7px; padding: 4px 10px; min-width: 120px; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #111827; border: 1px solid #D1D5DB; selection-background-color: #EDE9FE; selection-color: #4C1D95; }
QTableWidget { background: #FFFFFF; color: #111827; gridline-color: #F1F5F9; border: none; alternate-background-color: #F9FAFB; }
QHeaderView::section { background: #F9FAFB; color: #6B7280; border: none; border-bottom: 1px solid #E5E7EB; padding: 6px; font-weight: 700; }
QFrame#statusBar { background: #FFFFFF; border-top: 1px solid #E5E7EB; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px 0; }
QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 0 2px; }
QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 3px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""

DARK_QSS = """
QWidget { background: #0E1117; color: #F3F4F6; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 12px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #0E1117; border: none; }
QLabel#title { font-size: 18px; font-weight: 700; color: #F9FAFB; background: transparent; }
QLabel#badge { padding: 3px 10px; border-radius: 10px; background: #1E2534; font-size: 11px; font-weight: 600; }
QLabel#muted { color: #9CA3AF; background: transparent; }
QFrame#card { background: #161B26; border: 1px solid #252D3D; border-radius: 12px; }
QWidget#tierDetailBox { background: transparent; }
QLabel#cardTitle { color: #9CA3AF; font-size: 11px; font-weight: 600; background: transparent; }
QLabel#cardValue { font-size: 20px; font-weight: 700; background: transparent; }
QLabel#heroValue { font-size: 25px; font-weight: 800; color: #F9FAFB; background: transparent; }
QLabel#cardDetail { color: #9CA3AF; font-size: 11px; background: transparent; }
QLabel#sectionTitle { font-size: 14px; font-weight: 700; color: #F9FAFB; background: transparent; }
QLabel#tierBannerText { font-size: 13px; font-weight: 700; color: #C4B5FD; background: transparent; }
QLabel#tierPricePill { background: #2A2247; color: #DDD6FE; border: 1px solid #4C3F7D; border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 700; }
QLabel#accentLabel { color: #A78BFA; font-size: 12px; font-weight: 700; background: transparent; }
QLabel#tagViolet { color: #A78BFA; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#tagTeal { color: #2DD4BF; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#tagIndigo { color: #818CF8; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#tagSlate { color: #94A3B8; font-size: 11px; font-weight: 700; background: transparent; }
QLabel#costTotal { font-size: 18px; font-weight: 700; color: #FBBF24; background: transparent; }
QLabel#costValue { font-weight: 700; color: #FBBF24; background: transparent; }
QFrame#statCell { background: transparent; }
QLabel#statValue { font-size: 19px; font-weight: 700; color: #F9FAFB; background: transparent; }
QLabel#statCaption { color: #9CA3AF; font-size: 11px; background: transparent; }
QProgressBar { background: #232A3A; border: none; border-radius: 3px; }
QProgressBar::chunk { background: #8B5CF6; border-radius: 3px; }
QFrame#pillGroup { background: #1A202E; border: 1px solid #252D3D; border-radius: 9px; }
QPushButton { background: #1E2534; color: #F3F4F6; border: 1px solid #2E374B; border-radius: 7px; padding: 5px 12px; font-weight: 600; }
QPushButton:hover { background: #273044; }
QPushButton#modeButton, QPushButton#navButton { background: transparent; border: none; color: #9CA3AF; padding: 5px 12px; border-radius: 6px; font-weight: 600; }
QPushButton#modeButton:hover, QPushButton#navButton:hover { color: #F3F4F6; background: rgba(255,255,255,0.06); }
QPushButton#modeButton:checked, QPushButton#navButton:checked { background: #263044; color: #F9FAFB; font-weight: 700; border: 1px solid #35415B; }
QPushButton#ghostSmall { background: transparent; border: none; color: #9CA3AF; padding: 3px 8px; }
QPushButton#ghostSmall:hover { color: #F3F4F6; background: #232A3A; }
QComboBox { background: #161B26; color: #F3F4F6; border: 1px solid #2E374B; border-radius: 7px; padding: 4px 10px; min-width: 120px; }
QComboBox QAbstractItemView { background: #161B26; color: #F3F4F6; border: 1px solid #2E374B; selection-background-color: #312E81; }
QTableWidget { background: #161B26; color: #F3F4F6; gridline-color: #1F2636; border: none; alternate-background-color: #1A202E; }
QHeaderView::section { background: #1B2130; color: #9CA3AF; border: none; border-bottom: 1px solid #252D3D; padding: 6px; font-weight: 700; }
QFrame#statusBar { background: #131722; border-top: 1px solid #252D3D; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px 0; }
QScrollBar::handle:vertical { background: #334155; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #475569; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 0 2px; }
QScrollBar::handle:horizontal { background: #334155; border-radius: 3px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


def _num(value: float | None, suffix: str = "", digits: int = 1) -> str:
    return f"{value:.{digits}f}{suffix}" if value else "—"


class _Card(QFrame):
    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        caption = QLabel(title)
        caption.setObjectName("cardTitle")
        self.value = QLabel("—")
        self.value.setObjectName("cardValue")
        self.value.setStyleSheet(f"color:{accent};")
        self.detail = QLabel("")
        self.detail.setObjectName("cardDetail")
        self.detail.setWordWrap(True)
        layout.addWidget(caption)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        self.bar: QProgressBar | None = None

    def add_bar(self) -> QProgressBar:
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(5)
        self.layout().addWidget(self.bar)
        return self.bar


class TokenMeterWindow(QWidget):
    def __init__(
        self,
        *,
        on_request_report: Callable[[], None],
        on_toggle_subagents: Callable[[bool], None],
        icon=None,
        initial_theme: str = "light",
        default_tab: str = "overview",
        on_theme_changed: Callable[[str], None] | None = None,
        on_default_tab_changed: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Token Meter · Antigravity 监控看板")
        if icon is not None:
            self.setWindowIcon(icon)
        self.resize(1060, 760)
        self._on_request_report = on_request_report
        self._on_toggle_subagents = on_toggle_subagents
        self._on_theme_changed = on_theme_changed
        self._on_default_tab_changed = on_default_tab_changed
        self._theme = initial_theme if initial_theme in ("light", "dark") else "light"
        self._default_tab = default_tab if default_tab in dict(TAB_ITEMS) else "overview"
        self._last_report: MeterReport | None = None
        self._last_snapshot: LiveSnapshot | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top workspace container
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 8)
        body_layout.setSpacing(10)

        # Top header bar
        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("本机已记录用量 · Token Meter")
        title.setObjectName("title")
        header.addWidget(title)
        self.source = QLabel("正在连接…")
        self.source.setObjectName("badge")
        header.addWidget(self.source)
        header.addStretch(1)
        self.updated = QLabel("")
        self.updated.setObjectName("muted")
        header.addWidget(self.updated)
        self.theme_btn = QPushButton("🌙 深色")
        self.theme_btn.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_btn)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(on_request_report)
        header.addWidget(refresh)
        body_layout.addLayout(header)

        # Sub-navigation pills & "设为默认"
        nav_row = QHBoxLayout()
        nav_row.setSpacing(10)
        nav_pill = QFrame()
        nav_pill.setObjectName("pillGroup")
        np_layout = QHBoxLayout(nav_pill)
        np_layout.setContentsMargins(3, 3, 3, 3)
        np_layout.setSpacing(3)
        self.nav_group = QButtonGroup(self)
        self._tab_buttons: dict[str, QPushButton] = {}
        for index, (tab_key, tab_label) in enumerate(TAB_ITEMS):
            btn = QPushButton(tab_label)
            btn.setCheckable(True)
            btn.setObjectName("navButton")
            btn.setProperty("tabKey", tab_key)
            btn.setProperty("tabIndex", index)
            self.nav_group.addButton(btn)
            np_layout.addWidget(btn)
            self._tab_buttons[tab_key] = btn
        nav_row.addWidget(nav_pill)
        nav_row.addStretch(1)

        self.subagents = QCheckBox("合并子代理")
        self.subagents.setChecked(True)
        self.subagents.setVisible(False)  # kept synced for external caller compatibility
        self.subagents.toggled.connect(on_toggle_subagents)

        self.default_btn = QPushButton("设为默认")
        self.default_btn.clicked.connect(self._save_default_tab)
        nav_row.addWidget(self.default_btn)
        body_layout.addLayout(nav_row)

        # Shared source + account scope filter bar (shown on overview & models views)
        self.scope_bar = QWidget()
        sb_layout = QHBoxLayout(self.scope_bar)
        sb_layout.setContentsMargins(0, 2, 0, 2)
        sb_layout.setSpacing(10)
        sb_layout.addWidget(self._muted("来源："))
        src_pill = QFrame()
        src_pill.setObjectName("pillGroup")
        sp_layout = QHBoxLayout(src_pill)
        sp_layout.setContentsMargins(3, 3, 3, 3)
        sp_layout.setSpacing(2)
        self.scope_source_group = QButtonGroup(self)
        for key, label in (("all", "全部"), ("main", "主对话"), ("subagent", "子代理")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("modeButton")
            btn.setProperty("sourceFilter", key)
            self.scope_source_group.addButton(btn)
            sp_layout.addWidget(btn)
            if key == "all":
                btn.setChecked(True)
        sb_layout.addWidget(src_pill)

        sb_layout.addSpacing(8)
        sb_layout.addWidget(self._muted("账本范围："))
        self.account_box = QComboBox()
        self.account_box.addItem("全部已记用量（含未归属）", "all")
        self.account_box.setMinimumWidth(210)
        sb_layout.addWidget(self.account_box)
        self.account_meta = self._muted("")
        sb_layout.addWidget(self.account_meta)
        sb_layout.addStretch(1)
        body_layout.addWidget(self.scope_bar)

        # Stacked Views
        self.stack = QStackedWidget()
        self.dashboard = UsageDashboard()
        self.speed_view = SpeedComparisonView()

        # Tab 3: Models breakdown table
        models_page = QWidget()
        mp_layout = QVBoxLayout(models_page)
        mp_layout.setContentsMargins(0, 4, 0, 0)
        models_card = QFrame()
        models_card.setObjectName("card")
        mc_layout = QVBoxLayout(models_card)
        mc_layout.setContentsMargins(12, 10, 12, 10)
        mc_layout.setSpacing(8)
        self.models = self._table(
            ("模型", "总 Token", "占比", "输入", "缓存读", "思考", "正文", "缓存命中", "等效费用", "流式 tok/s", "峰值", "端到端", "TTFT", "步数")
        )
        mc_layout.addWidget(self.models, 1)
        mp_layout.addWidget(models_card, 1)

        # Tab 4: Live conversation + 4 real-time KPI cards + per-step table
        steps_page = QWidget()
        stp_layout = QVBoxLayout(steps_page)
        stp_layout.setContentsMargins(0, 4, 0, 0)
        stp_layout.setSpacing(10)
        self.conversation = QLabel("当前会话：等待遥测数据…")
        self.conversation.setObjectName("muted")
        stp_layout.addWidget(self.conversation)

        cards = QGridLayout()
        cards.setSpacing(10)
        self.card_speed = _Card("⚡ 生成速率", "#0EA5E9")
        self.card_quota = _Card("🔋 限额剩余", "#10B981")
        self.card_cache = _Card("🎯 缓存命中", "#14B8A6")
        self.card_ctx = _Card("🧠 上下文占用", "#8B5CF6")
        self.ctx_bar = self.card_ctx.add_bar()
        self.quota_bar = self.card_quota.add_bar()
        for index, card in enumerate((self.card_speed, self.card_quota, self.card_cache, self.card_ctx)):
            cards.addWidget(card, 0, index)
            cards.setColumnStretch(index, 1)
        stp_layout.addLayout(cards)

        steps_card = QFrame()
        steps_card.setObjectName("card")
        sc_layout = QVBoxLayout(steps_card)
        sc_layout.setContentsMargins(12, 10, 12, 10)
        self.steps = self._table(("时间", "模型", "输入", "缓存读", "输出", "思考/正文", "TTFT", "总耗时", "流式 tok/s", "端到端", "工具调用"))
        sc_layout.addWidget(self.steps, 1)
        stp_layout.addWidget(steps_card, 1)

        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.speed_view)
        self.stack.addWidget(models_page)
        self.stack.addWidget(steps_page)
        body_layout.addWidget(self.stack, 1)
        root.addWidget(body, 1)

        # Compact bottom status bar
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        sb_bottom = QHBoxLayout(status_bar)
        sb_bottom.setContentsMargins(16, 7, 16, 7)
        self.footer = QLabel("● 就绪 · 等待数据…")
        self.footer.setObjectName("muted")
        sb_bottom.addWidget(self.footer, 1)
        root.addWidget(status_bar)

        self.nav_group.buttonClicked.connect(self._on_nav_clicked)
        self.scope_source_group.buttonClicked.connect(lambda _b: self._apply_filters(sync_speed=True))
        self.speed_view.source_changed.connect(self._sync_source_from_speed)
        self.account_box.currentIndexChanged.connect(lambda _i: self._apply_filters())

        self.set_theme(self._theme, notify=False)
        self.switch_tab(self._default_tab)

        self._timer = QTimer(self)
        self._timer.timeout.connect(on_request_report)

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("muted")
        return label

    @staticmethod
    def _table(headers: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return table

    # ----- theme & navigation -----------------------------------------------

    def set_theme(self, theme: str, *, notify: bool = True) -> None:
        self._theme = theme if theme in ("light", "dark") else "light"
        self.setStyleSheet(DARK_QSS if self._theme == "dark" else LIGHT_QSS)
        self.theme_btn.setText("☀ 浅色" if self._theme == "dark" else "🌙 深色")
        self.dashboard.set_theme(self._theme)
        self.speed_view.set_theme(self._theme)
        if notify and self._on_theme_changed is not None:
            self._on_theme_changed(self._theme)

    def _toggle_theme(self) -> None:
        self.set_theme("dark" if self._theme == "light" else "light", notify=True)

    def current_tab(self) -> str:
        idx = self.stack.currentIndex()
        if 0 <= idx < len(TAB_ITEMS):
            return TAB_ITEMS[idx][0]
        return "overview"

    def switch_tab(self, tab_key: str) -> None:
        btn = self._tab_buttons.get(tab_key) or self._tab_buttons["overview"]
        btn.setChecked(True)
        idx = int(btn.property("tabIndex"))
        self.stack.setCurrentIndex(idx)
        self.scope_bar.setVisible(tab_key in ("overview", "models"))
        self.default_btn.setText("已设为默认" if tab_key == self._default_tab else "设为默认")

    def _on_nav_clicked(self, button: QPushButton) -> None:
        self.switch_tab(str(button.property("tabKey") or "overview"))

    def _save_default_tab(self) -> None:
        self._default_tab = self.current_tab()
        self.default_btn.setText("已设为默认")
        if self._on_default_tab_changed is not None:
            self._on_default_tab_changed(self._default_tab)

    # ----- lifecycle --------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._on_request_report()
        self._timer.start(8_000)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    # ----- rendering --------------------------------------------------------

    def _source_filter(self) -> str:
        btn = self.scope_source_group.checkedButton()
        return str(btn.property("sourceFilter") or "all") if btn else "all"

    def _account_filter(self) -> str:
        return str(self.account_box.currentData() or "all")

    def update_live(self, snap: LiveSnapshot | None) -> None:
        self._last_snapshot = snap
        if snap is None:
            self.source.setText("未连接 Antigravity")
            self.source.setStyleSheet("color:#6B7280;")
            return
        text, color = SOURCE_TEXT.get(snap.source, (snap.source, "#6B7280"))
        self.source.setText(text)
        self.source.setStyleSheet(f"color:{color};")
        state = "运行中" if snap.running else "空闲"
        self.conversation.setText(
            f"当前会话：{snap.title}（{state}） · 选择模型 {snap.selected_model_label} · 最近一步 {snap.last_step_model_label or '—'}"
        )
        self.card_speed.value.setText(_num(snap.display_rate, " tok/s"))
        ttft = f"{snap.latest_ttft_ms / 1000:.2f}s" if snap.latest_ttft_ms else "—"
        self.card_speed.detail.setText(f"会话均值 {_num(snap.avg_decode_tps)} · 端到端 {_num(snap.latest_e2e_tps)} · TTFT {ttft}")
        five, five_reset = snap.quota_for("5h")
        week, week_reset = snap.quota_for("week")
        if five is not None or week is not None:
            self.card_quota.value.setText(f"5h {five:.0f}%" if five is not None else "5h —")
            week_text = f"周 {week:.0f}%" if week is not None else "周 —"
            self.card_quota.detail.setText(f"{week_text} · {format_reset_countdown(five_reset) or '5h 窗口'}")
            self.quota_bar.setValue(int((five if five is not None else 0) * 10))
        else:
            self.card_quota.value.setText("—")
            self.card_quota.detail.setText("离线模式无法获取配额")
            self.quota_bar.setValue(0)
        self.dashboard.set_quota(
            (five, format_reset_countdown(five_reset) if five is not None else ""),
            (week, format_reset_countdown(week_reset) if week is not None else ""),
        )
        self.card_cache.value.setText(f"{snap.cache_hit_pct:.1f}%")
        self.card_cache.detail.setText(f"会话累计 {format_tokens(snap.cumulative_total_tokens)} tokens")
        self.card_ctx.value.setText(f"{snap.context_pct:.1f}%")
        self.card_ctx.detail.setText(f"{snap.context_used_tokens:,} / {snap.context_limit_tokens:,}")
        self.ctx_bar.setValue(int(min(100.0, snap.context_pct) * 10))
        self._update_status_bar()

    def update_report(self, report: MeterReport) -> None:
        self._last_report = report
        self.update_live(report.live)
        self.updated.setText("更新于 " + datetime.fromtimestamp(report.generated_at).strftime("%H:%M:%S"))
        self._sync_account_box(report)
        self._apply_filters()

    def _sync_account_box(self, report: MeterReport) -> None:
        current = self.account_box.currentData() or "all"
        accounts = list(getattr(report, "accounts", ()) or ())
        unattr_count = sum(1 for c in report.conversations if not getattr(c, "account_id", ""))
        self.account_box.blockSignals(True)
        self.account_box.clear()
        self.account_box.addItem("全部已记用量（含未归属）", "all")
        for acct_id, tier in accounts:
            suffix = f" · {tier}" if tier else ""
            self.account_box.addItem(f"账号 {acct_id}{suffix}", acct_id)
        if unattr_count > 0:
            self.account_box.addItem(f"仅未归属历史 ({unattr_count} 会话)", "unattributed")
        idx = self.account_box.findData(current)
        self.account_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.account_box.blockSignals(False)

        attr_txt = f"含 {len(accounts)} 个已归属账号" if accounts else "暂无账号归属"
        extra_txt = " + 未归属历史" if unattr_count else ""
        self.account_meta.setText(f"{attr_txt}{extra_txt} · 共 {len(report.conversations)} 条会话")

    def _sync_source_from_speed(self, source_key: str) -> None:
        for btn in self.scope_source_group.buttons():
            if str(btn.property("sourceFilter") or "all") == source_key:
                if not btn.isChecked():
                    btn.setChecked(True)
                    self._apply_filters(sync_speed=False)
                break

    def _apply_filters(self, *, sync_speed: bool = False) -> None:
        report = self._last_report
        if report is None:
            return
        src_filter = self._source_filter()
        acct_filter = self._account_filter()
        if sync_speed:
            self.speed_view.set_source_filter(src_filter)
        # Keep compatibility checkbox synced when user switches to main-only vs all
        want_sub = src_filter != "main"
        if self.subagents.isChecked() != want_sub:
            self.subagents.blockSignals(True)
            self.subagents.setChecked(want_sub)
            self.subagents.blockSignals(False)

        filtered = speed_stats.filter_conversations(
            report.conversations,
            source_filter=src_filter,
            account_filter=acct_filter,
        )
        tier_name = report.user_tier_name or (report.live.user_tier_name if report.live else "")
        self.dashboard.set_conversations(
            filtered,
            source=report.source,
            user_tier_name=tier_name,
            updated_at=report.generated_at,
        )
        self.speed_view.set_conversations(speed_stats.filter_conversations(report.conversations, account_filter=acct_filter))

        # Populate "按模型 / 费用" table for the filtered slice
        model_rows = build_model_rows(filtered) if (src_filter != "all" or acct_filter != "all") else report.models
        try:
            table = pricing.load_table()
            cost_map = {r.name: r.total_usd for r in pricing.compute(filtered, table).rows if r.priced}
            rate = table.usd_to_cny
        except (OSError, ValueError, KeyError):
            table = None
            cost_map = {}
            rate = 7.25

        self.models.setRowCount(len(model_rows))
        for row, model in enumerate(model_rows):
            matched = table.find("", model.label) if table else None
            cost_val = cost_map.get(matched.name) if matched else cost_map.get(model.label)
            cost_text = pricing.format_usd_cny(cost_val, rate) if cost_val else "—"
            values = (
                model.label,
                format_tokens(model.total_tokens),
                f"{model.share_pct:.1f}%",
                format_tokens(model.input_tokens),
                format_tokens(model.cache_read_tokens),
                format_tokens(model.thinking_tokens),
                format_tokens(model.response_tokens),
                f"{model.cache_hit_pct:.1f}%",
                cost_text,
                _num(model.avg_decode_tps),
                _num(model.peak_decode_tps),
                _num(model.avg_e2e_tps),
                f"{model.avg_ttft_ms / 1000:.2f}s" if model.avg_ttft_ms else "—",
                str(model.steps),
            )
            self._fill_row(self.models, row, values)

        steps = list(reversed(report.active.steps[-60:])) if report.active else []
        self.steps.setRowCount(len(steps))
        for row, step in enumerate(steps):
            clock = datetime.fromtimestamp(step.created_ms / 1000).strftime("%H:%M:%S") if step.created_ms else "—"
            dur_s = step.duration_ms / 1000.0 if getattr(step, "duration_ms", None) else None
            values = (
                clock,
                step.model_label,
                format_tokens(step.input_tokens),
                format_tokens(step.cache_read_tokens),
                format_tokens(step.output_tokens),
                f"{format_tokens(step.thinking_tokens)} / {format_tokens(step.response_tokens)}",
                f"{step.ttft_ms / 1000:.2f}s" if step.ttft_ms else "—",
                f"{dur_s:.2f}s" if dur_s else "—",
                _num(step.decode_tps),
                _num(step.e2e_tps),
                ", ".join(step.tool_calls[:4]),
            )
            self._fill_row(self.steps, row, values)
        self._update_status_bar(filtered)

    def _update_status_bar(self, filtered: list | None = None) -> None:
        snap = self._last_snapshot
        report = self._last_report
        state = "运行中" if (snap and snap.running) else "就绪"
        active_steps = len(report.active.steps) if (report and report.active) else 0
        rate = snap.display_rate if snap else None
        speed_txt = f"{rate:.1f} tok/s" if rate else "— tok/s"
        convs = filtered if filtered is not None else (report.conversations if report else [])
        total_tok = sum(s.total_tokens for c in convs for s in c.steps)
        cache_tok = sum(s.cache_read_tokens for c in convs for s in c.steps)
        fresh_tok = sum(s.input_tokens for c in convs for s in c.steps)
        hit_pct = (cache_tok / (cache_tok + fresh_tok) * 100.0) if (cache_tok + fresh_tok) else (snap.cache_hit_pct if snap else 0.0)
        self.footer.setText(
            f"● {state} · ⏱ 当前会话 {active_steps} 步 · {speed_txt} · "
            f"🗄 账本累计 {format_tokens(total_tok)} tok · 综合缓存命中率 {hit_pct:.1f}%"
        )

    @staticmethod
    def _fill_row(table: QTableWidget, row: int, values: tuple[str, ...]) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, column, item)
