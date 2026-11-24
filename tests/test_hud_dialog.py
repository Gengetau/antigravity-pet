from PySide6.QtCore import QRect

from agy.hud_bar import TAIL, HudBar
from agy.telemetry import LiveSnapshot


def _hud(appearance: str) -> HudBar:
    hud = HudBar(
        settings={"hud_appearance": appearance, "hud_mode": "attached"},
        on_open_meter=lambda: None,
        on_refresh=lambda: None,
        on_pin=lambda _cid: None,
        on_hide=lambda: None,
    )
    hud.apply_appearance()
    return hud


def test_dialog_card_shows_session_and_tail(qapp=None):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    hud = _hud("dialog")
    assert hud.card.isVisibleTo(hud) and not hud.pill.isVisibleTo(hud)
    snap = LiveSnapshot(source="ls", title="写测试", status="CASCADE_RUN_STATUS_RUNNING",
                        selected_model_label="Gemini 3 Pro", quota_remaining_pct=10)
    hud.update_snapshot(snap)
    assert hud.card_title.text().startswith("生成中 · 写测试")
    assert hud.card_model.text() == "Gemini 3 Pro"
    assert "#dc2626" in hud.card_values["quota_5h"].styleSheet()
    assert hud.card_values["quota_week"].text() == "—"
    hud.follow_pet(QRect(400, 400, 160, 200), prefer_above=True)
    assert hud._tail_dir == "down"
    assert hud._outer.contentsMargins().bottom() == TAIL
    hud.update_snapshot(None)
    assert hud.card_title.text() == "Antigravity 没有在运行"


def test_capsule_has_no_tail_margin():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    hud = _hud("capsule")
    assert hud.pill.isVisibleTo(hud) and not hud.card.isVisibleTo(hud)
    hud.follow_pet(QRect(400, 400, 160, 200), prefer_above=True)
    margins = hud._outer.contentsMargins()
    assert (margins.top(), margins.bottom()) == (0, 0)


def test_hud_moves_to_side_when_top_headroom_is_tight():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    hud = _hud("dialog")
    hud.update_snapshot(LiveSnapshot(source="ls", title="顶部测试", status="CASCADE_RUN_STATUS_RUNNING"))
    pet_rect = QRect(400, 40, 160, 200)
    hud.follow_pet(pet_rect, sprite_top=40, prefer_above=True)
    area = app.primaryScreen().availableGeometry()
    assert hud._tail_dir is None
    assert hud.y() >= area.top()
    assert not hud.geometry().intersects(pet_rect)
