"""Desktop Token Meter: per-model token ranking and per-step speed, like the
token-meter sidecar but available without opening Antigravity's aux pane."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .telemetry import LiveSnapshot, MeterReport, format_reset_countdown, format_tokens
from .usage_dashboard import UsageDashboard

SOURCE_TEXT = {
    "ls": ("实时 · 本地语言服务", "#34D399"),
    "pet_live": ("实时 · AGY 桌宠插件", "#34D399"),
    "hud_live": ("实时 · Token Meter 侧边栏", "#38BDF8"),
    "transcript": ("离线 · 本地会话日志（无配额、速率为估算）", "#FBBF24"),
}


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
    def __init__(self, *, on_request_report: Callable[[], None], on_toggle_subagents: Callable[[bool], None], icon=None) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Token Meter · Antigravity")
        if icon is not None:
            self.setWindowIcon(icon)
        self.resize(980, 640)
        self._on_request_report = on_request_report

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Token Meter")
        title.setObjectName("title")
        header.addWidget(title)
        self.source = QLabel("正在连接…")
        self.source.setObjectName("badge")
        header.addWidget(self.source)
        header.addStretch(1)
        self.updated = QLabel("")
        self.updated.setObjectName("muted")
        header.addWidget(self.updated)
        self.subagents = QCheckBox("合并子代理")
        self.subagents.setChecked(True)
        self.subagents.toggled.connect(on_toggle_subagents)
        header.addWidget(self.subagents)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(on_request_report)
        header.addWidget(refresh)
        root.addLayout(header)

        self.conversation = QLabel("")
        self.conversation.setObjectName("muted")
        root.addWidget(self.conversation)

        cards = QGridLayout()
        cards.setSpacing(10)
        self.card_speed = _Card("⚡ 生成速率", "#38BDF8")
        self.card_quota = _Card("🔋 限额剩余", "#34D399")
        self.card_cache = _Card("🎯 缓存命中", "#2DD4BF")
        self.card_ctx = _Card("🧠 上下文占用", "#C4B5FD")
        self.ctx_bar = self.card_ctx.add_bar()
        self.quota_bar = self.card_quota.add_bar()
        for index, card in enumerate((self.card_speed, self.card_quota, self.card_cache, self.card_ctx)):
            cards.addWidget(card, 0, index)
            cards.setColumnStretch(index, 1)
        root.addLayout(cards)

        tabs = QTabWidget()
        self.dashboard = UsageDashboard()
        tabs.addTab(self.dashboard, "用量看板")
        self.models = self._table(
            ("模型", "总 Token", "占比", "输入", "缓存读", "思考", "正文", "缓存命中", "流式 tok/s", "峰值", "端到端", "TTFT", "步数")
        )
        self.steps = self._table(("时间", "模型", "输入", "缓存读", "输出", "思考/正文", "TTFT", "流式 tok/s", "端到端", "工具调用"))
        tabs.addTab(self.models, "全局模型榜单")
        tabs.addTab(self.steps, "当前会话计速")
        root.addWidget(tabs, 1)
        self.footer = QLabel("")
        self.footer.setObjectName("muted")
        root.addWidget(self.footer)

        self.setStyleSheet(
            "QWidget{background:#0f1115;color:#e5e7eb;font-family:'Segoe UI','Microsoft YaHei UI';font-size:12px;}"
            "QLabel#title{font-size:18px;font-weight:700;}"
            "QLabel#badge{padding:2px 8px;border-radius:8px;background:#1f2937;font-size:11px;}"
            "QLabel#muted{color:#9ca3af;}"
            "QFrame#card{background:#161a22;border:1px solid #232937;border-radius:10px;}"
            "QLabel#cardTitle{color:#9ca3af;font-size:11px;background:transparent;}"
            "QLabel#cardValue{font-size:20px;font-weight:700;background:transparent;}"
            "QLabel#cardDetail{color:#9ca3af;font-size:11px;background:transparent;}"
            "QProgressBar{background:#232937;border:none;border-radius:2px;}"
            "QProgressBar::chunk{background:#a78bfa;border-radius:2px;}"
            "QTabWidget::pane{border:1px solid #232937;border-radius:8px;}"
            "QTabBar::tab{background:#161a22;padding:6px 14px;border-top-left-radius:6px;border-top-right-radius:6px;color:#9ca3af;}"
            "QTabBar::tab:selected{background:#232937;color:#f3f4f6;}"
            "QTableWidget{background:#0f1115;gridline-color:#1f2430;border:none;alternate-background-color:#131720;}"
            "QHeaderView::section{background:#161a22;color:#9ca3af;border:none;padding:5px;font-weight:600;}"
            "QPushButton{background:#232937;border:none;border-radius:6px;padding:5px 12px;}"
            "QPushButton:hover{background:#2f3747;}"
            "QCheckBox{background:transparent;}"
            "QFrame#statCell{background:transparent;}"
            "QLabel#statValue{font-size:20px;font-weight:700;color:#f3f4f6;background:transparent;}"
            "QLabel#statCaption{color:#9ca3af;font-size:11px;background:transparent;}"
            "QLabel#sectionTitle{font-size:14px;font-weight:700;}"
            "QLabel#costTotal{font-size:18px;font-weight:700;color:#FBBF24;background:transparent;}"
            "QLabel#costValue{font-weight:700;color:#FBBF24;background:transparent;}"
            "QFrame#card QLabel{background:transparent;}"
            "QPushButton#modeButton{background:transparent;color:#9ca3af;padding:4px 10px;}"
            "QPushButton#modeButton:checked{background:#232937;color:#f3f4f6;font-weight:600;}"
            "QComboBox{background:#161a22;border:1px solid #2f3747;border-radius:6px;padding:3px 8px;min-width:120px;}"
            "QComboBox QAbstractItemView{background:#161a22;selection-background-color:#2f3747;}"
        )
        self._timer = QTimer(self)
        self._timer.timeout.connect(on_request_report)

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

    # ----- lifecycle --------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._on_request_report()
        self._timer.start(8_000)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    # ----- rendering --------------------------------------------------------

    def update_live(self, snap: LiveSnapshot | None) -> None:
        if snap is None:
            self.source.setText("未连接 Antigravity")
            self.source.setStyleSheet("color:#9ca3af;")
            return
        text, color = SOURCE_TEXT.get(snap.source, (snap.source, "#9ca3af"))
        self.source.setText(text)
        self.source.setStyleSheet(f"color:{color};")
        state = "运行中" if snap.running else "空闲"
        self.conversation.setText(f"当前会话：{snap.title}（{state}） · 选择模型 {snap.selected_model_label} · 最近一步 {snap.last_step_model_label}")
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

    def update_report(self, report: MeterReport) -> None:
        self.update_live(report.live)
        self.updated.setText("更新于 " + datetime.fromtimestamp(report.generated_at).strftime("%H:%M:%S"))
        self.models.setRowCount(len(report.models))
        for row, model in enumerate(report.models):
            values = (
                model.label,
                format_tokens(model.total_tokens),
                f"{model.share_pct:.1f}%",
                format_tokens(model.input_tokens),
                format_tokens(model.cache_read_tokens),
                format_tokens(model.thinking_tokens),
                format_tokens(model.response_tokens),
                f"{model.cache_hit_pct:.1f}%",
                _num(model.avg_decode_tps),
                _num(model.peak_decode_tps),
                _num(model.avg_e2e_tps),
                f"{model.avg_ttft_ms / 1000:.2f}s" if model.avg_ttft_ms else "—",
                str(model.steps),
            )
            self._fill_row(self.models, row, values)
        self.dashboard.set_conversations(report.conversations, source=report.source)
        steps = list(reversed(report.active.steps[-60:])) if report.active else []
        self.steps.setRowCount(len(steps))
        for row, step in enumerate(steps):
            clock = datetime.fromtimestamp(step.created_ms / 1000).strftime("%H:%M:%S") if step.created_ms else "—"
            values = (
                clock,
                step.model_label,
                format_tokens(step.input_tokens),
                format_tokens(step.cache_read_tokens),
                format_tokens(step.output_tokens),
                f"{format_tokens(step.thinking_tokens)} / {format_tokens(step.response_tokens)}",
                f"{step.ttft_ms / 1000:.2f}s" if step.ttft_ms else "—",
                _num(step.decode_tps),
                _num(step.e2e_tps),
                ", ".join(step.tool_calls[:4]),
            )
            self._fill_row(self.steps, row, values)
        self.footer.setText(
            f"统计 {report.conversation_count} 个会话 · 全部模型合计 {format_tokens(report.grand_total)} tokens"
            " · 总 Token = 输入 + 缓存读 + 输出（含思考）"
        )

    @staticmethod
    def _fill_row(table: QTableWidget, row: int, values: tuple[str, ...]) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, column, item)
