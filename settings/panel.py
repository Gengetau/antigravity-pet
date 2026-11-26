"""A compact, pet-adjacent control surface with progressive disclosure."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QSizePolicy,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class PetControlPanel(QWidget):
    """Quick interaction first; secondary settings are explicitly revealed."""

    def __init__(
        self,
        *,
        on_mode: Callable[[str], None],
        on_size: Callable[[float], None],
        on_feed: Callable[[], None],
        on_say: Callable[[], None],
        on_snap: Callable[[], None],
        on_awareness: Callable[[bool], None],
        on_read_window_title: Callable[[bool], None],
        on_idle_detection: Callable[[bool], None],
        on_topmost: Callable[[bool], None],
        on_fullscreen_hide: Callable[[bool], None],
        on_passthrough: Callable[[bool], None],
        on_autostart: Callable[[bool], None],
        on_activity_level: Callable[[str], None],
        on_walk_speed: Callable[[float], None],
        on_reduced_motion: Callable[[bool], None],
        on_hover_pause: Callable[[bool], None],
        on_desktop_surfaces: Callable[[bool], None],
        on_action: Callable[[str], None],
        on_hide: Callable[[], None],
        on_privacy: Callable[[], None],
        on_quit: Callable[[], None],
        on_form: Callable[[str], None] | None = None,
        on_follow_model: Callable[[bool], None] | None = None,
        on_open_meter: Callable[[], None] | None = None,
        on_hud: Callable[[bool], None] | None = None,
        on_hud_hover_only: Callable[[bool], None] | None = None,
        on_playmates: Callable[[], None] | None = None,
        on_follow_cursor: Callable[[bool], None] | None = None,
        on_autonomy: Callable[[bool], None] | None = None,
        on_dock: Callable[[], None] | None = None,
        on_perch: Callable[[], None] | None = None,
        on_recall_primary: Callable[[], None] | None = None,
        forms: tuple[tuple[str, str], ...] = (("carbon", "Carbon"), ("hydergon", "Hydrogen"), ("neon", "Neon")),
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("petControlPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(258)
        self._mode_buttons: dict[str, QToolButton] = {}
        self._size_buttons: dict[float, QToolButton] = {}
        self._activity_buttons: dict[str, QToolButton] = {}
        self._speed_buttons: dict[float, QToolButton] = {}
        self._mode_group = QButtonGroup(self)
        self._size_group = QButtonGroup(self)
        self._activity_group = QButtonGroup(self)
        self._speed_group = QButtonGroup(self)
        self._form_buttons: dict[str, QToolButton] = {}
        self._form_group = QButtonGroup(self)
        self._expanded = False
        self._pet_rect: QRect | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 6)
        self._root_layout = root
        surface = QFrame()
        surface.setObjectName("controlSurface")
        self._surface = surface
        shadow = QGraphicsDropShadowEffect(surface)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(46, 24, 104, 72))
        self._shadow = shadow
        surface.setGraphicsEffect(shadow)
        root.addWidget(surface)

        layout = QVBoxLayout(surface)
        self._surface_layout = layout
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._header_layout = header
        title = QLabel("小A")
        title.setObjectName("panelTitle")
        header.addWidget(title)
        self.title_label = title
        self.state_label = QLabel("待机")
        self.state_label.setObjectName("stateLabel")
        header.addWidget(self.state_label)
        header.addStretch(1)
        close = QToolButton()
        close.setObjectName("closeButton")
        close.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setToolTip("关闭")
        close.setAccessibleName("关闭")
        close.clicked.connect(self.hide)
        header.addWidget(close)
        layout.addLayout(header)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(4)
        playmate_cb = on_playmates if on_playmates is not None else (lambda: on_action("HAPPY"))
        for label, callback in (
            ("投喂", on_feed),
            ("说话", on_say),
            ("唤玩伴", playmate_cb),
            ("休息", lambda: on_action("SLEEPING")),
        ):
            button = self._quick_button(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(callback)
            quick_row.addWidget(button)
        layout.addLayout(quick_row)

        # Promote high-frequency spatial actions (dock, climb, perch, recall)
        # into the primary area so users never have to expand advanced settings.
        dock_cb = on_dock if on_dock is not None else (lambda: on_action("EDGE_DOCK"))
        perch_cb = on_perch if on_perch is not None else (lambda: on_action("EDGE_SIT"))
        recall_cb = on_recall_primary if on_recall_primary is not None else on_snap

        spatial_row = QHBoxLayout()
        spatial_row.setSpacing(4)
        self.dock_button = self._quick_button("贴边")
        self.dock_button.setToolTip("贴到屏幕边缘藏身 / 取消贴边")
        self.dock_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.dock_button.clicked.connect(dock_cb)
        self.climb_button = self._quick_button("爬窗")
        self.climb_button.setToolTip("爬到附近窗口顶部")
        self.climb_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.climb_button.clicked.connect(lambda: on_action("CLIMB"))
        self.perch_button = self._quick_button("坐沿")
        self.perch_button.setToolTip("坐在附近窗口顶部边缘")
        self.perch_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.perch_button.clicked.connect(perch_cb)
        self.recall_button = self._quick_button("召回主屏")
        self.recall_button.setToolTip("取消贴边并召回到主屏幕")
        self.recall_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.recall_button.clicked.connect(recall_cb)
        spatial_row.addWidget(self.dock_button, 2)
        spatial_row.addWidget(self.climb_button, 2)
        spatial_row.addWidget(self.perch_button, 2)
        spatial_row.addWidget(self.recall_button, 3)
        layout.addLayout(spatial_row)

        layout.addWidget(self._divider())
        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)
        mode_label = QLabel("移动")
        mode_label.setObjectName("inlineLabel")
        mode_label.setFixedWidth(28)
        mode_row.addWidget(mode_label)
        for label, value in (("散步", "wander"), ("跟随", "follow"), ("静止", "still")):
            button = self._choice_button(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, key=value: on_mode(key))
            self._mode_group.addButton(button)
            self._mode_buttons[value] = button
            mode_row.addWidget(button, 1)
        layout.addLayout(mode_row)

        form_label = QLabel("形态")
        form_label.setObjectName("compactLabel")
        layout.addWidget(form_label)
        # Two columns so four (or more) form names never get elided.
        form_row = QGridLayout()
        form_row.setHorizontalSpacing(4)
        form_row.setVerticalSpacing(3)
        for index, (value, label) in enumerate(forms):
            button = self._choice_button(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if on_form is not None:
                button.clicked.connect(lambda _checked=False, key=value: on_form(key))
            self._form_group.addButton(button)
            self._form_buttons[value] = button
            form_row.addWidget(button, index // 2, index % 2)
        layout.addLayout(form_row)
        agy_row = QGridLayout()
        agy_row.setHorizontalSpacing(6)
        agy_row.setVerticalSpacing(2)
        self.follow_model = self._toggle("跟随模型", on_follow_model or (lambda _enabled: None))
        self.follow_model.setToolTip("根据 Antigravity 当前使用的模型（Carbon / Hydrogen / Neon / Claude）自动切换形态")
        self.hud = self._toggle("HUD 条", on_hud or (lambda _enabled: None))
        self.hud.setToolTip("显示 tok/s · 限额 · 缓存 · 上下文 迷你悬浮条")
        self.autonomy = self._toggle("自主行为", on_autonomy or (lambda _enabled: None))
        self.autonomy.setToolTip("模型干活时陪着干活、跳上 Antigravity 窗口、闲久了打盹、限额低会犯困、久坐提醒")
        self.hud_hover_only = self._toggle("悬停HUD", on_hud_hover_only or (lambda _enabled: None))
        self.hud_hover_only.setToolTip("平时隐藏 HUD 卡片还桌面清爽，鼠标悬停在桌宠身上时再弹出")
        agy_row.addWidget(self.follow_model, 0, 0)
        agy_row.addWidget(self.hud, 0, 1)
        agy_row.addWidget(self.autonomy, 1, 0)
        agy_row.addWidget(self.hud_hover_only, 1, 1)
        layout.addLayout(agy_row)
        meter = self._quick_button("Token Meter 面板")
        meter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if on_open_meter is not None:
            meter.clicked.connect(on_open_meter)
        layout.addWidget(meter)

        footer = QHBoxLayout()
        footer.setSpacing(4)
        self.more_button = QToolButton()
        self.more_button.setObjectName("moreButton")
        self.more_button.setText("更多设置")
        self.more_button.clicked.connect(self._toggle_advanced)
        footer.addWidget(self.more_button, 1)
        hide = QToolButton()
        hide.setObjectName("moreButton")
        hide.setText("隐藏")
        hide.clicked.connect(on_hide)
        footer.addWidget(hide)
        layout.addLayout(footer)

        self._advanced = QWidget()
        advanced_layout = QVBoxLayout(self._advanced)
        advanced_layout.setContentsMargins(0, 1, 0, 0)
        advanced_layout.setSpacing(4)
        advanced_layout.addWidget(self._divider())

        size_row = QHBoxLayout()
        size_row.setSpacing(4)
        size_label = QLabel("大小")
        size_label.setObjectName("inlineLabel")
        size_label.setFixedWidth(28)
        size_row.addWidget(size_label)
        for label, value in (("小", 0.55), ("中", 0.70), ("大", 0.90)):
            button = self._choice_button(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, size=value: on_size(size))
            self._size_group.addButton(button)
            self._size_buttons[value] = button
            size_row.addWidget(button, 1)
        advanced_layout.addLayout(size_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        action_label = QLabel("动作")
        action_label.setObjectName("inlineLabel")
        action_label.setFixedWidth(28)
        action_row.addWidget(action_label)
        for label, action in (("发呆", "THINKING"), ("扫地", "SWEEPING")):
            button = self._quick_button(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, value=action: on_action(value))
            action_row.addWidget(button, 1)
        advanced_layout.addLayout(action_row)

        rhythm_row = QHBoxLayout()
        rhythm_row.setSpacing(4)
        rhythm_label = QLabel("节奏")
        rhythm_label.setObjectName("inlineLabel")
        rhythm_label.setToolTip("陪伴节奏")
        rhythm_label.setFixedWidth(28)
        rhythm_row.addWidget(rhythm_label)
        for label, value in (("安静", "calm"), ("适中", "balanced"), ("活泼", "lively")):
            button = self._choice_button(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, key=value: on_activity_level(key))
            self._activity_group.addButton(button)
            self._activity_buttons[value] = button
            rhythm_row.addWidget(button, 1)
        advanced_layout.addLayout(rhythm_row)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(4)
        speed_label = QLabel("步速")
        speed_label.setObjectName("inlineLabel")
        speed_label.setToolTip("走路速度")
        speed_label.setFixedWidth(28)
        speed_row.addWidget(speed_label)
        for label, value in (("慢", 64.0), ("适中", 82.0), ("快", 104.0)):
            button = self._choice_button(label)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, speed=value: on_walk_speed(speed))
            self._speed_group.addButton(button)
            self._speed_buttons[value] = button
            speed_row.addWidget(button, 1)
        advanced_layout.addLayout(speed_row)

        self.awareness = self._toggle("本地感知", on_awareness)
        self.topmost = self._toggle("窗口置顶", on_topmost)
        self.read_window_title = self._toggle("读取标题", on_read_window_title)
        self.fullscreen_hide = self._toggle("全屏隐藏", on_fullscreen_hide)
        self.idle_detection = self._toggle("检测空闲", on_idle_detection)
        self.passthrough = self._toggle("鼠标穿透", on_passthrough)
        self.autostart = self._toggle("开机自启", on_autostart)
        self.reduced_motion = self._toggle("减少动态", on_reduced_motion)
        self.follow_cursor = self._toggle("目光跟随", on_follow_cursor or (lambda _enabled: None))
        self.hover_pause = self._toggle("悬停暂停", on_hover_pause)
        self.desktop_surfaces = self._toggle("窗口落脚", on_desktop_surfaces)
        toggle_grid = QGridLayout()
        toggle_grid.setHorizontalSpacing(8)
        toggle_grid.setVerticalSpacing(1)
        for index, toggle in enumerate(
            (
                self.awareness,
                self.topmost,
                self.read_window_title,
                self.fullscreen_hide,
                self.idle_detection,
                self.passthrough,
                self.autostart,
                self.reduced_motion,
                self.follow_cursor,
                self.hover_pause,
                self.desktop_surfaces,
            )
        ):
            toggle_grid.addWidget(toggle, index // 2, index % 2)
        advanced_layout.addLayout(toggle_grid)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        for label, callback, object_name in (
            ("回到屏幕内", on_snap, "utilityButton"),
            ("隐私", on_privacy, "utilityButton"),
            ("退出", on_quit, "dangerButton"),
        ):
            button = QPushButton(label)
            button.setObjectName(object_name)
            button.clicked.connect(callback)
            tools.addWidget(button)
        advanced_layout.addLayout(tools)
        self._advanced.setVisible(False)
        layout.addWidget(self._advanced)

        self.setStyleSheet(
            "#controlSurface{background:#fffdfb;border:1.5px solid #c4b5fd;border-radius:14px;}"
            "#panelTitle{color:#2a1b3d;font-size:15px;font-weight:700;}"
            "#stateLabel{padding:1px 7px;background:#ede9fe;border-radius:8px;color:#6d28d9;font-size:10px;font-weight:600;}"
            "QLabel#compactLabel,QLabel#inlineLabel{color:#7c5cd6;font-size:10px;font-weight:700;}"
            "QFrame#divider{background:#e9e3fb;min-height:1px;max-height:1px;}"
            "QToolButton#quickButton{min-height:23px;padding:0 4px;background:#f5f3ff;border:1px solid #dfd6fe;border-radius:8px;"
            "color:#3b2761;font-size:11px;font-weight:600;}"
            "QToolButton#quickButton:hover{background:#ede9fe;border-color:#c4b5fd;color:#2a1b3d;}"
            "QToolButton#choiceButton{min-height:21px;padding:0 5px;background:#faf8ff;border:1px solid #e5ddfe;border-radius:7px;"
            "color:#4c3b73;font-size:11px;font-weight:600;}"
            "QToolButton#choiceButton:hover{background:#ede9fe;}"
            "QToolButton#choiceButton:checked{background:#8b5cf6;border-color:#7c3aed;color:#ffffff;}"
            "QToolButton#moreButton,QToolButton#closeButton{min-height:22px;padding:0 8px;background:transparent;border:none;"
            "border-radius:7px;color:#6b5b95;font-size:11px;font-weight:600;}"
            "QToolButton#moreButton:hover,QToolButton#closeButton:hover{background:#ede9fe;color:#2a1b3d;}"
            "QCheckBox{min-height:16px;padding:0px;color:#3b2761;font-size:11px;spacing:5px;}"
            "QCheckBox::indicator{width:24px;height:13px;border-radius:6px;background:#e5ddfe;}"
            "QCheckBox::indicator:checked{background:#8b5cf6;}"
            "QPushButton#utilityButton,QPushButton#dangerButton{min-height:23px;padding:0 7px;border:none;border-radius:7px;"
            "font-size:11px;font-weight:600;}"
            "QPushButton#utilityButton{background:#ede9fe;color:#4c1d95;}"
            "QPushButton#utilityButton:hover{background:#ddd6fe;}"
            "QPushButton#dangerButton{background:#ffe4e6;color:#be123c;}"
            "QPushButton#dangerButton:hover{background:#fecdd3;}"
        )

    @staticmethod
    def _divider() -> QFrame:
        divider = QFrame()
        divider.setObjectName("divider")
        return divider

    @staticmethod
    def _choice_button(text: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("choiceButton")
        button.setText(text)
        button.setCheckable(True)
        button.setAutoExclusive(True)
        return button

    @staticmethod
    def _quick_button(text: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("quickButton")
        button.setText(text)
        return button

    @staticmethod
    def _toggle(text: str, callback: Callable[[bool], None]) -> QCheckBox:
        checkbox = QCheckBox(text)
        checkbox.clicked.connect(callback)
        return checkbox

    def _toggle_advanced(self) -> None:
        self._expanded = not self._expanded
        self._advanced.setVisible(self._expanded)
        self.more_button.setText("收起设置" if self._expanded else "更多设置")
        # Hiding a child queues a layout recalculation.  Resize on the next Qt
        # turn so the compact hint is already current instead of retaining the
        # expanded tool window's old height.
        QTimer.singleShot(0, self._fit_to_content)

    def _fit_to_content(self) -> None:
        # A top-level transparent Tool window does not reliably shrink from
        # ``adjustSize`` after a child is hidden on Windows.  Re-activate the
        # layout and apply its fresh height explicitly, otherwise the old empty
        # glass area remains below the compact panel.
        self._root_layout.invalidate()
        self._root_layout.activate()
        target_height = self.sizeHint().height()
        # Qt may still hold the expanded layout's minimum height until the next
        # event cycle, so release that stale bound before asking the window to
        # shrink to its current size hint.
        self.setMinimumHeight(0)
        self.resize(self.width(), target_height)
        if self._pet_rect is not None:
            self._move_near_pet(self._pet_rect)

    def sync(
        self,
        *,
        mode: str,
        size: float,
        awareness: bool,
        read_window_title: bool,
        idle_detection: bool,
        topmost: bool,
        fullscreen_hide: bool,
        passthrough: bool,
        autostart: bool,
        activity_level: str,
        walk_speed: float,
        reduced_motion: bool,
        hover_pause: bool,
        desktop_surfaces: bool,
        state_name: str,
        form: str | None = None,
        follow_model: bool | None = None,
        hud_enabled: bool | None = None,
        hud_hover_only: bool | None = None,
        follow_cursor: bool | None = None,
        autonomy: bool | None = None,
    ) -> None:
        if autonomy is not None:
            self.autonomy.setChecked(autonomy)
        if form in self._form_buttons:
            self._form_buttons[form].setChecked(True)
        if follow_model is not None:
            self.follow_model.setChecked(follow_model)
        if hud_enabled is not None:
            self.hud.setChecked(hud_enabled)
        if hud_hover_only is not None:
            self.hud_hover_only.setChecked(hud_hover_only)
        if follow_cursor is not None:
            self.follow_cursor.setChecked(follow_cursor)
        if mode in self._mode_buttons:
            self._mode_buttons[mode].setChecked(True)
        closest_size = min(self._size_buttons, key=lambda value: abs(value - size))
        self._size_buttons[closest_size].setChecked(True)
        if activity_level in self._activity_buttons:
            self._activity_buttons[activity_level].setChecked(True)
        closest_speed = min(self._speed_buttons, key=lambda value: abs(value - walk_speed))
        self._speed_buttons[closest_speed].setChecked(True)
        self.awareness.setChecked(awareness)
        self.read_window_title.setChecked(read_window_title)
        self.idle_detection.setChecked(idle_detection)
        self.topmost.setChecked(topmost)
        self.fullscreen_hide.setChecked(fullscreen_hide)
        self.passthrough.setChecked(passthrough)
        self.autostart.setChecked(autostart)
        self.reduced_motion.setChecked(reduced_motion)
        self.hover_pause.setChecked(hover_pause)
        self.desktop_surfaces.setChecked(desktop_surfaces)
        if self.state_label.text() != state_name:
            self.state_label.setText(state_name)
            self._refresh_header_paint()

    def set_title(self, text: str) -> None:
        if self.title_label.text() == text:
            return
        self.title_label.setText(text)
        self._refresh_header_paint()

    def _refresh_header_paint(self) -> None:
        # Force full repaint of the QGraphicsDropShadowEffect backing pixmap on
        # translucent top-level Tool windows so shrinking header text (e.g.
        # "Claude" -> "Argon") never leaves stale alpha ghost pixels behind.
        self.title_label.adjustSize()
        self.state_label.adjustSize()
        self._header_layout.invalidate()
        self._surface_layout.activate()
        self._shadow.update()
        self._surface.update()
        self.update()

    def popup_near_pet(self, pet_rect: QRect) -> None:
        self._pet_rect = QRect(pet_rect)
        self.adjustSize()
        self._move_near_pet(self._pet_rect)
        self.show()
        self.raise_()

    def popup_at(self, point: QPoint) -> None:
        """Fallback used from the tray when there is no visible pet anchor."""

        self._pet_rect = None
        self.adjustSize()
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(self._clamp(QPoint(point.x() + 12, point.y() + 12), area))
        else:
            self.move(point + QPoint(12, 12))
        self.show()
        self.raise_()

    def _move_near_pet(self, pet_rect: QRect) -> None:
        screen = QApplication.screenAt(pet_rect.center()) or QApplication.primaryScreen()
        if screen is None:
            self.move(pet_rect.topRight() + QPoint(14, 8))
            return
        area = screen.availableGeometry()
        gap = 14
        aligned_y = pet_rect.top() + max(0, min(24, pet_rect.height() - self.height()))
        centered_x = pet_rect.center().x() - self.width() // 2
        candidates = (
            QPoint(pet_rect.right() + gap, aligned_y),
            QPoint(pet_rect.left() - self.width() - gap, aligned_y),
            QPoint(centered_x, pet_rect.top() - self.height() - gap),
            QPoint(centered_x, pet_rect.bottom() + gap),
        )
        for candidate in candidates:
            rect = QRect(candidate, self.size())
            if area.contains(rect):
                self.move(candidate)
                return

        # On a very small screen, pick the clamped candidate that hides the
        # least of the pet rather than anchoring blindly over its centre.
        def overlap(candidate: QPoint) -> int:
            rect = QRect(self._clamp(candidate, area), self.size())
            intersection = rect.intersected(pet_rect)
            return intersection.width() * intersection.height()

        self.move(min(candidates, key=overlap))
        self.move(self._clamp(self.pos(), area))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def _clamp(self, point: QPoint, area: QRect) -> QPoint:
        return QPoint(
            min(max(area.left(), point.x()), area.right() - self.width() + 1),
            min(max(area.top(), point.y()), area.bottom() - self.height() + 1),
        )
