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

from app.i18n import tr


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
        on_scene: Callable[[str], None] | None = None,
        on_follow_cursor: Callable[[bool], None] | None = None,
        on_autonomy: Callable[[bool], None] | None = None,
        on_dock: Callable[[], None] | None = None,
        on_perch: Callable[[], None] | None = None,
        on_recall_primary: Callable[[], None] | None = None,
        on_language: Callable[[str], None] | None = None,
        on_progress_bubbles: Callable[[bool], None] | None = None,
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
        self._lang_buttons: dict[str, QToolButton] = {}
        self._mode_group = QButtonGroup(self)
        self._size_group = QButtonGroup(self)
        self._activity_group = QButtonGroup(self)
        self._speed_group = QButtonGroup(self)
        self._lang_group = QButtonGroup(self)
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
        title = QLabel(tr("panel.default_title"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        self.title_label = title
        self.state_label = QLabel(tr("state.idle"))
        self.state_label.setObjectName("stateLabel")
        header.addWidget(self.state_label)
        header.addStretch(1)
        close = QToolButton()
        close.setObjectName("closeButton")
        close.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.clicked.connect(self.hide)
        self._close_button = close
        header.addWidget(close)
        layout.addLayout(header)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(4)
        playmate_cb = on_playmates if on_playmates is not None else (lambda: on_action("HAPPY"))
        self._quick_buttons: dict[str, QToolButton] = {}
        for key, callback in (
            ("feed", on_feed),
            ("say", on_say),
            ("playmates", playmate_cb),
            ("rest", lambda: on_action("SLEEPING")),
        ):
            button = self._quick_button(tr(f"panel.{key}"))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(callback)
            self._quick_buttons[key] = button
            quick_row.addWidget(button)
        layout.addLayout(quick_row)

        # Promote high-frequency spatial actions (dock, climb, perch, recall)
        # into the primary area so users never have to expand advanced settings.
        dock_cb = on_dock if on_dock is not None else (lambda: on_action("EDGE_DOCK"))
        perch_cb = on_perch if on_perch is not None else (lambda: on_action("EDGE_SIT"))
        recall_cb = on_recall_primary if on_recall_primary is not None else on_snap

        spatial_row = QHBoxLayout()
        spatial_row.setSpacing(4)
        self.dock_button = self._quick_button(tr("panel.dock"))
        self.dock_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.dock_button.clicked.connect(dock_cb)
        self.climb_button = self._quick_button(tr("panel.climb"))
        self.climb_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.climb_button.clicked.connect(lambda: on_action("CLIMB"))
        self.perch_button = self._quick_button(tr("panel.perch"))
        self.perch_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.perch_button.clicked.connect(perch_cb)
        self.recall_button = self._quick_button(tr("panel.recall"))
        self.recall_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.recall_button.clicked.connect(recall_cb)
        spatial_row.addWidget(self.dock_button, 2)
        spatial_row.addWidget(self.climb_button, 2)
        spatial_row.addWidget(self.perch_button, 2)
        spatial_row.addWidget(self.recall_button, 3)
        layout.addLayout(spatial_row)

        scene_row = QHBoxLayout()
        scene_row.setSpacing(4)
        self.scene_buttons: dict[str, QToolButton] = {}
        for kind in ("tea_party", "campfire_night", "art_studio", "cloud_nap"):
            btn = self._quick_button(tr(f"panel.scene.{kind}"))
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if on_scene is not None:
                btn.clicked.connect(lambda _c=False, k=kind: on_scene(k))
            else:
                btn.clicked.connect(lambda _c=False: on_action("HAPPY"))
            self.scene_buttons[kind] = btn
            scene_row.addWidget(btn)
        layout.addLayout(scene_row)

        layout.addWidget(self._divider())
        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)
        self._mode_label = QLabel(tr("panel.mode"))
        self._mode_label.setObjectName("inlineLabel")
        self._mode_label.setFixedWidth(30)
        mode_row.addWidget(self._mode_label)
        for value in ("wander", "follow", "still"):
            button = self._choice_button(tr(f"panel.mode.{value}"))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, key=value: on_mode(key))
            self._mode_group.addButton(button)
            self._mode_buttons[value] = button
            mode_row.addWidget(button, 1)
        layout.addLayout(mode_row)

        self._form_label = QLabel(tr("panel.form"))
        self._form_label.setObjectName("compactLabel")
        layout.addWidget(self._form_label)
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
        self.follow_model = self._toggle(tr("panel.follow_model"), on_follow_model or (lambda _enabled: None))
        self.hud = self._toggle(tr("panel.hud"), on_hud or (lambda _enabled: None))
        self.autonomy = self._toggle(tr("panel.autonomy"), on_autonomy or (lambda _enabled: None))
        self.hud_hover_only = self._toggle(tr("panel.hud_hover_only"), on_hud_hover_only or (lambda _enabled: None))
        agy_row.addWidget(self.follow_model, 0, 0)
        agy_row.addWidget(self.hud, 0, 1)
        agy_row.addWidget(self.autonomy, 1, 0)
        agy_row.addWidget(self.hud_hover_only, 1, 1)
        layout.addLayout(agy_row)
        self._meter_button = self._quick_button(tr("panel.open_meter"))
        self._meter_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if on_open_meter is not None:
            self._meter_button.clicked.connect(on_open_meter)
        layout.addWidget(self._meter_button)

        footer = QHBoxLayout()
        footer.setSpacing(4)
        self.more_button = QToolButton()
        self.more_button.setObjectName("moreButton")
        self.more_button.clicked.connect(self._toggle_advanced)
        footer.addWidget(self.more_button, 1)
        self._hide_button = QToolButton()
        self._hide_button.setObjectName("moreButton")
        self._hide_button.clicked.connect(on_hide)
        footer.addWidget(self._hide_button)
        layout.addLayout(footer)

        self._advanced = QWidget()
        advanced_layout = QVBoxLayout(self._advanced)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(2)
        advanced_layout.addWidget(self._divider())

        size_row = QHBoxLayout()
        size_row.setSpacing(4)
        self._size_label = QLabel(tr("panel.size"))
        self._size_label.setObjectName("inlineLabel")
        self._size_label.setFixedWidth(30)
        size_row.addWidget(self._size_label)
        self._size_key_map = ((0.55, "panel.size.small"), (0.70, "panel.size.medium"), (0.90, "panel.size.large"))
        for value, i18n_key in self._size_key_map:
            button = self._choice_button(tr(i18n_key))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, size=value: on_size(size))
            self._size_group.addButton(button)
            self._size_buttons[value] = button
            size_row.addWidget(button, 1)
        advanced_layout.addLayout(size_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        self._action_label = QLabel(tr("panel.action"))
        self._action_label.setObjectName("inlineLabel")
        self._action_label.setFixedWidth(30)
        action_row.addWidget(self._action_label)
        self._action_buttons: dict[str, QToolButton] = {}
        for key, action in (("think", "THINKING"), ("sweep", "SWEEPING")):
            button = self._quick_button(tr(f"panel.action.{key}"))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, value=action: on_action(value))
            self._action_buttons[key] = button
            action_row.addWidget(button, 1)
        advanced_layout.addLayout(action_row)

        rhythm_row = QHBoxLayout()
        rhythm_row.setSpacing(4)
        self._rhythm_label = QLabel(tr("panel.rhythm"))
        self._rhythm_label.setObjectName("inlineLabel")
        self._rhythm_label.setFixedWidth(30)
        rhythm_row.addWidget(self._rhythm_label)
        for value in ("calm", "balanced", "lively"):
            button = self._choice_button(tr(f"panel.rhythm.{value}"))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, key=value: on_activity_level(key))
            self._activity_group.addButton(button)
            self._activity_buttons[value] = button
            rhythm_row.addWidget(button, 1)
        advanced_layout.addLayout(rhythm_row)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(4)
        self._speed_label = QLabel(tr("panel.speed"))
        self._speed_label.setObjectName("inlineLabel")
        self._speed_label.setFixedWidth(30)
        speed_row.addWidget(self._speed_label)
        self._speed_key_map = ((64.0, "panel.speed.slow"), (82.0, "panel.speed.normal"), (104.0, "panel.speed.fast"))
        for value, i18n_key in self._speed_key_map:
            button = self._choice_button(tr(i18n_key))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, speed=value: on_walk_speed(speed))
            self._speed_group.addButton(button)
            self._speed_buttons[value] = button
            speed_row.addWidget(button, 1)
        advanced_layout.addLayout(speed_row)

        lang_row = QHBoxLayout()
        lang_row.setSpacing(3)
        self._lang_label = QLabel(tr("lang.label"))
        self._lang_label.setObjectName("inlineLabel")
        self._lang_label.setFixedWidth(30)
        lang_row.addWidget(self._lang_label)
        lang_cb = on_language if on_language is not None else (lambda _lang: None)
        for value in ("auto", "zh", "en", "ja"):
            button = self._choice_button(tr(f"lang.{value}"))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, code=value: lang_cb(code))
            self._lang_group.addButton(button)
            self._lang_buttons[value] = button
            lang_row.addWidget(button, 1)
        advanced_layout.addLayout(lang_row)

        self.awareness = self._toggle(tr("panel.awareness"), on_awareness)
        self.topmost = self._toggle(tr("panel.topmost"), on_topmost)
        self.read_window_title = self._toggle(tr("panel.read_window_title"), on_read_window_title)
        self.fullscreen_hide = self._toggle(tr("panel.fullscreen_hide"), on_fullscreen_hide)
        self.idle_detection = self._toggle(tr("panel.idle_detection"), on_idle_detection)
        self.passthrough = self._toggle(tr("panel.passthrough"), on_passthrough)
        self.autostart = self._toggle(tr("panel.autostart"), on_autostart)
        self.reduced_motion = self._toggle(tr("panel.reduced_motion"), on_reduced_motion)
        self.follow_cursor = self._toggle(tr("panel.follow_cursor"), on_follow_cursor or (lambda _enabled: None))
        self.hover_pause = self._toggle(tr("panel.hover_pause"), on_hover_pause)
        self.desktop_surfaces = self._toggle(tr("panel.desktop_surfaces"), on_desktop_surfaces)
        self.progress_bubbles = self._toggle(
            tr("panel.progress_bubbles"),
            on_progress_bubbles or (lambda _enabled: None),
        )
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
                self.progress_bubbles,
            )
        ):
            toggle_grid.addWidget(toggle, index // 2, index % 2)
        advanced_layout.addLayout(toggle_grid)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        self._tool_buttons: dict[str, QPushButton] = {}
        for key, callback, object_name in (
            ("snap", on_snap, "utilityButton"),
            ("privacy", on_privacy, "utilityButton"),
            ("quit", on_quit, "dangerButton"),
        ):
            button = QPushButton(tr(f"panel.{key}"))
            button.setObjectName(object_name)
            button.clicked.connect(callback)
            self._tool_buttons[key] = button
            tools.addWidget(button)
        advanced_layout.addLayout(tools)
        self._advanced.setVisible(False)
        layout.addWidget(self._advanced)
        self.retranslate()

        self.setStyleSheet(
            "#controlSurface{background:#fffdfb;border:1.5px solid #c4b5fd;border-radius:14px;}"
            "#panelTitle{color:#2a1b3d;font-size:15px;font-weight:700;}"
            "#stateLabel{padding:1px 7px;background:#ede9fe;border-radius:8px;color:#6d28d9;font-size:10px;font-weight:600;}"
            "QLabel#compactLabel,QLabel#inlineLabel{color:#7c5cd6;font-size:10px;font-weight:700;}"
            "QFrame#divider{background:#e9e3fb;min-height:1px;max-height:1px;}"
            "QToolButton#quickButton{min-height:21px;padding:0 4px;background:#f5f3ff;border:1px solid #dfd6fe;border-radius:8px;"
            "color:#3b2761;font-size:11px;font-weight:600;}"
            "QToolButton#quickButton:hover{background:#ede9fe;border-color:#c4b5fd;color:#2a1b3d;}"
            "QToolButton#choiceButton{min-height:19px;padding:0 4px;background:#faf8ff;border:1px solid #e5ddfe;border-radius:7px;"
            "color:#4c3b73;font-size:11px;font-weight:600;}"
            "QToolButton#choiceButton:hover{background:#ede9fe;}"
            "QToolButton#choiceButton:checked{background:#8b5cf6;border-color:#7c3aed;color:#ffffff;}"
            "QToolButton#moreButton,QToolButton#closeButton{min-height:20px;padding:0 8px;background:transparent;border:none;"
            "border-radius:7px;color:#6b5b95;font-size:11px;font-weight:600;}"
            "QToolButton#moreButton:hover,QToolButton#closeButton:hover{background:#ede9fe;color:#2a1b3d;}"
            "QCheckBox{min-height:14px;padding:0px;color:#3b2761;font-size:11px;spacing:5px;}"
            "QCheckBox::indicator{width:24px;height:13px;border-radius:6px;background:#e5ddfe;}"
            "QCheckBox::indicator:checked{background:#8b5cf6;}"
            "QPushButton#utilityButton,QPushButton#dangerButton{min-height:21px;padding:0 7px;border:none;border-radius:7px;"
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

    def retranslate(self) -> None:
        self._close_button.setToolTip(tr("panel.close"))
        self._close_button.setAccessibleName(tr("panel.close"))
        for key, btn in self._quick_buttons.items():
            btn.setText(tr(f"panel.{key}"))
        self.dock_button.setText(tr("panel.dock"))
        self.dock_button.setToolTip(tr("panel.dock_tip"))
        self.climb_button.setText(tr("panel.climb"))
        self.climb_button.setToolTip(tr("panel.climb_tip"))
        self.perch_button.setText(tr("panel.perch"))
        self.perch_button.setToolTip(tr("panel.perch_tip"))
        self.recall_button.setText(tr("panel.recall"))
        self.recall_button.setToolTip(tr("panel.recall_tip"))
        for kind, btn in self.scene_buttons.items():
            btn.setText(tr(f"panel.scene.{kind}"))
            btn.setToolTip(tr(f"panel.scene.{kind}_tip"))
        self._mode_label.setText(tr("panel.mode"))
        for key, btn in self._mode_buttons.items():
            btn.setText(tr(f"panel.mode.{key}"))
        self._form_label.setText(tr("panel.form"))
        self.follow_model.setText(tr("panel.follow_model"))
        self.follow_model.setToolTip(tr("panel.follow_model_tip"))
        self.hud.setText(tr("panel.hud"))
        self.hud.setToolTip(tr("panel.hud_tip"))
        self.autonomy.setText(tr("panel.autonomy"))
        self.autonomy.setToolTip(tr("panel.autonomy_tip"))
        self.hud_hover_only.setText(tr("panel.hud_hover_only"))
        self.hud_hover_only.setToolTip(tr("panel.hud_hover_only_tip"))
        self._meter_button.setText(tr("panel.open_meter"))
        self.more_button.setText(tr("panel.less") if self._expanded else tr("panel.more"))
        self._hide_button.setText(tr("panel.hide"))
        self._size_label.setText(tr("panel.size"))
        for value, i18n_key in self._size_key_map:
            self._size_buttons[value].setText(tr(i18n_key))
        self._action_label.setText(tr("panel.action"))
        for key, btn in self._action_buttons.items():
            btn.setText(tr(f"panel.action.{key}"))
        self._rhythm_label.setText(tr("panel.rhythm"))
        self._rhythm_label.setToolTip(tr("panel.rhythm_tip"))
        for key, btn in self._activity_buttons.items():
            btn.setText(tr(f"panel.rhythm.{key}"))
        self._speed_label.setText(tr("panel.speed"))
        self._speed_label.setToolTip(tr("panel.speed_tip"))
        for value, i18n_key in self._speed_key_map:
            self._speed_buttons[value].setText(tr(i18n_key))
        self._lang_label.setText(tr("lang.label"))
        for code, btn in self._lang_buttons.items():
            btn.setText(tr(f"lang.{code}"))
        self.awareness.setText(tr("panel.awareness"))
        self.topmost.setText(tr("panel.topmost"))
        self.read_window_title.setText(tr("panel.read_window_title"))
        self.fullscreen_hide.setText(tr("panel.fullscreen_hide"))
        self.idle_detection.setText(tr("panel.idle_detection"))
        self.passthrough.setText(tr("panel.passthrough"))
        self.autostart.setText(tr("panel.autostart"))
        self.reduced_motion.setText(tr("panel.reduced_motion"))
        self.follow_cursor.setText(tr("panel.follow_cursor"))
        self.hover_pause.setText(tr("panel.hover_pause"))
        self.desktop_surfaces.setText(tr("panel.desktop_surfaces"))
        self.progress_bubbles.setText(tr("panel.progress_bubbles"))
        for key, btn in self._tool_buttons.items():
            btn.setText(tr(f"panel.{key}"))
        if self.isVisible():
            QTimer.singleShot(0, self._fit_to_content)

    def _toggle_advanced(self) -> None:
        self._expanded = not self._expanded
        self._advanced.setVisible(self._expanded)
        self.more_button.setText(tr("panel.less") if self._expanded else tr("panel.more"))
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
        language: str | None = None,
        progress_bubbles: bool | None = None,
    ) -> None:
        if autonomy is not None:
            self.autonomy.setChecked(autonomy)
        if progress_bubbles is not None:
            self.progress_bubbles.setChecked(progress_bubbles)
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
        if language in self._lang_buttons:
            self._lang_buttons[language].setChecked(True)
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
