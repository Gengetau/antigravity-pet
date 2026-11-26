from __future__ import annotations

import os
import random
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QEnterEvent, QFontMetrics, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from agy.telemetry import LiveSnapshot, SubagentInfo
from animation.asset_registry import AssetRegistry
from animation.clip import PetAction
from app.paths import AppPaths
from pet.particles import ParticleSystem, draw_fish_stash
from pet.physics import PhysicsBounds, ThrowPhysics
from pet.renderer import Bubble, PetRenderer
from pet.subagent_clones import CloneEvent, SubagentCloneManager
from pet.window import PetWindow
from settings.config import ConfigManager

ROOT = Path(__file__).resolve().parents[1]
BASE_MANIFEST = ROOT / "assets" / "manifests" / "actions_base.json"


class _FakeScreen:
    def __init__(self, rect: QRect) -> None:
        self._rect = QRect(rect)

    def availableGeometry(self) -> QRect:
        return QRect(self._rect)


def _mouse(
    etype: QEvent.Type,
    local: QPointF,
    glob: QPointF,
    button: Qt.MouseButton = Qt.MouseButton.NoButton,
    buttons: Qt.MouseButton = Qt.MouseButton.NoButton,
) -> QMouseEvent:
    return QMouseEvent(etype, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier)


class StageAComicBubbleAndParticlesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_bubble_typewriter_ai_mark_and_orphan_punctuation_wrap(self) -> None:
        b = Bubble(text="✦ 你好呀，今天一起写代码！", appeared_at=10.0, until=16.0, is_ai=True)
        early = b.visible_text_at(10.02, reduced_motion=False)
        mid = b.visible_text_at(10.18, reduced_motion=False)
        full = b.visible_text_at(12.0, reduced_motion=False)
        self.assertLess(len(early), len(mid))
        self.assertLess(len(mid), len(full))
        self.assertEqual(full, b.text)
        self.assertTrue(b.is_typing_at(10.10, reduced_motion=False))
        self.assertFalse(b.is_typing_at(12.0, reduced_motion=False))
        # Reduced motion reveals full text immediately
        self.assertEqual(b.visible_text_at(10.01, reduced_motion=True), b.text)
        self.assertFalse(b.is_typing_at(10.01, reduced_motion=True))

        # No single trailing punctuation dangling on line 2
        renderer = PetRenderer(72, 16)
        fm = QFontMetrics(renderer.bubble_font)
        sample = "主宠和小分身合体共舞！"
        max_w = fm.horizontalAdvance(sample[:-1]) + 1
        lines = renderer._wrap_text(sample, fm, max_w)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith("！"))

    def test_two_layer_particles_and_fish_stash_bowl_render_cleanly(self) -> None:
        ps = ParticleSystem(random.Random(3))
        self.assertGreater(ps.emit("fish", origin_x=120.0, origin_y=120.0), 0)
        self.assertGreater(ps.emit("notes", origin_x=120.0, origin_y=100.0), 0)
        self.assertGreater(ps.emit("steam", origin_x=120.0, origin_y=100.0), 0)
        self.assertGreater(ps.emit("dust", origin_x=120.0, origin_y=160.0), 0)
        self.assertGreater(ps.emit("sleep_z", origin_x=120.0, origin_y=90.0), 0)
        self.assertTrue(any(not p.front for p in ps.particles))
        self.assertTrue(any(p.front for p in ps.particles))

        ps.update(0.25)
        for layer in ("back", "front", "all"):
            img = QImage(240, 240, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            painter = QPainter(img)
            ps.paint(painter, layer=layer)
            painter.end()
            self.assertTrue(
                any(img.pixelColor(x, y).alpha() > 0 for x in range(0, 240, 6) for y in range(0, 240, 6)),
                f"layer={layer} should render non-empty pixels",
            )

        # Render fish stash bowl at full (100%), half (50%), and empty (0% fishbone)
        for level, lbl in ((1.0, "100%"), (0.5, "50%"), (0.0, "0%")):
            img = QImage(160, 140, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            painter = QPainter(img)
            draw_fish_stash(painter, x=80.0, y=75.0, level=level, label=lbl, show=1.0, elapsed=1.2, scale=0.8)
            painter.end()
            self.assertTrue(
                any(img.pixelColor(x, y).alpha() > 0 for x in range(20, 140, 4) for y in range(20, 120, 4)),
                f"fish stash level={level} rendered empty",
            )

    def test_host_mirrors_high_five_and_gift_toss_only_when_facing_left(self) -> None:
        reg = AssetRegistry(ROOT / "neon", base_manifest=BASE_MANIFEST)
        self.assertTrue(reg.clip_for(PetAction.HIGH_FIVE, height=238, direction="left").mirrored)
        self.assertFalse(reg.clip_for(PetAction.HIGH_FIVE, height=238, direction="right").mirrored)
        self.assertFalse(reg.clip_for(PetAction.HIGH_FIVE, height=238, direction="down").mirrored)
        self.assertTrue(reg.clip_for(PetAction.GIFT_TOSS, height=238, direction="left").mirrored)
        self.assertFalse(reg.clip_for(PetAction.GIFT_TOSS, height=238, direction="right").mirrored)
        self.assertFalse(reg.clip_for(PetAction.IDLE, height=238, direction="left").mirrored)


class StageAClonesAndWindowInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="agy-stage-a-")
        paths = AppPaths(app_dir=Path(self._tmp.name), bundle_dir=ROOT)
        config = ConfigManager(paths.config_path)
        config.set("mode", "still", save=False)
        config.set_nested("comfort", "reduced_motion", False, save=False)
        config.set_nested("agy", "telemetry_enabled", False, save=False)
        config.set_nested("agy", "hud_enabled", True, save=False)
        config.set_nested("agy", "hud_hover_only", False, save=False)
        self.pet = PetWindow(paths, config)
        self.pet.timer.stop()
        self.pet.persistence_timer.stop()
        self.pet.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.pet.subagent_clones.close_all()
        for w in (self.pet.hud_bar, self.pet.token_meter, self.pet.control_panel, self.pet.food_panel):
            w.hide()
            w.close()
        self.pet.close()
        self._tmp.cleanup()

    def test_head_rub_triggers_purr_and_forgives_sulking(self) -> None:
        now = time.monotonic()
        self.pet._sulk_until = now + 20.0
        self.pet._request_action(PetAction.SULK, now=now, reason="test_sulk", force=True)
        bl, bt, bw, bh = self.pet._local_sprite_bounds()
        hx = bl + bw * 0.5
        hy = bt + bh * 0.25
        # Rub cursor back and forth over head without holding mouse buttons
        for step in range(8):
            offset = -38.0 if step % 2 == 0 else 38.0
            local = QPointF(hx + offset, hy)
            glob = QPointF(self.pet.x() + local.x(), self.pet.y() + local.y())
            self.pet.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, local, glob))
        self.assertEqual(self.pet._sulk_until, 0.0)
        self.assertEqual(self.pet.action_machine.current, PetAction.PET_PURR)
        self.assertTrue(self.pet.particles.active)

    def test_drag_shake_triggers_dizzy_and_wall_bounce_emits_dust(self) -> None:
        # 1. Wall bounce detection in pure physics engine
        phys = ThrowPhysics()
        phys.launch(x=5.0, y=200.0, velocity_x=-900.0, velocity_y=-100.0)
        step = phys.step(0.05, width=120.0, height=180.0, bounds=PhysicsBounds(0.0, 0.0, 1000.0, 800.0))
        self.assertGreaterEqual(step.wall_bounce_speed, 500.0)

        # 2. Rapid horizontal shake while dragging -> DIZZY on release
        bl, bt, bw, bh = self.pet._local_sprite_bounds()
        local = QPointF(bl + bw * 0.5, bt + bh * 0.5)
        base_x, base_y = float(self.pet.x() + local.x()), float(self.pet.y() + local.y())
        self.pet.mousePressEvent(
            _mouse(QEvent.Type.MouseButtonPress, local, QPointF(base_x, base_y), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        )
        for i in range(7):
            dx = 42.0 if i % 2 == 0 else -42.0
            self.pet.mouseMoveEvent(
                _mouse(QEvent.Type.MouseMove, local, QPointF(base_x + dx, base_y), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
            )
        self.pet.mouseReleaseEvent(
            _mouse(QEvent.Type.MouseButtonRelease, local, QPointF(base_x, base_y), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
        )
        self.assertEqual(self.pet.action_machine.current, PetAction.DIZZY)

    def test_hud_hover_only_toggles_visibility_and_fish_stash_shows_on_hover(self) -> None:
        self.pet.telemetry.last_snapshot = LiveSnapshot(
            source="pet_live",
            conversation_id="c1",
            status="CASCADE_RUN_STATUS_IDLE",
            quota_remaining_pct=62.0,
        )
        self.pet.set_hud_hover_only(True)
        self.assertFalse(self.pet.hud_bar.isVisible())
        self.pet._sync_fish_stash(time.monotonic())
        self.assertEqual(self.pet.renderer._stash_target, 0.0)

        # Hovering reveals both hover-only HUD and floating dried-fish bowl
        self.pet.enterEvent(QEnterEvent(QPointF(20, 20), QPointF(20, 20), QPointF(20, 20)))
        self.assertTrue(self.pet.hud_bar.isVisible())
        self.pet._sync_fish_stash(time.monotonic())
        self.assertEqual(self.pet.renderer._stash_target, 1.0)
        self.assertEqual(self.pet.renderer._stash_label, "62%")

        self.pet.leaveEvent(QEvent(QEvent.Type.Leave))
        self.assertFalse(self.pet.hud_bar.isVisible())

    def test_clone_high_five_holds_before_glide_and_host_faces_left_clone(self) -> None:
        mgr = SubagentCloneManager(
            characters_root=ROOT,
            base_manifest=BASE_MANIFEST,
            topmost=True,
            rng=random.Random(1),
        )
        try:
            subs = [SubagentInfo("s1", "m1", "查日志", "Gemini 4 Neon", "neon")]
            screen = _FakeScreen(QRect(0, 0, 1920, 1080))
            host = QRect(860, 500, 180, 220)
            mgr.sync(subs, default_form="carbon", enabled=True, host_visible=True, now=10.0)
            # Summon starts bursting from host center horizontally
            mgr.position_around(host, now=10.05, screen=screen)
            w = mgr.visible_widgets[0]
            self.assertGreater(w.x(), host.left() - w.width() - 4)

            # Settle, drag close to host, release -> holds at drop position during contact hold
            mgr.position_around(host, now=12.0, screen=screen)
            drop_pt = QPoint(host.left() - w.width() + 40, host.top() + 30)
            w.move(drop_pt)
            mgr._handle_widget_drag_start(w)
            mgr._handle_widget_drag_end(w, host.center())
            rt = mgr._runtime["s1"]
            self.assertGreater(rt.glide_hold_until, 0.0)
            mgr.position_around(host, now=rt.glide_hold_until - 0.2, screen=screen)
            self.assertEqual(w.pos(), drop_pt)
        finally:
            mgr.close_all()

        # Host mirrors HIGH_FIVE left when interacting with a left-side clone
        self.pet._on_subagent_interaction(
            CloneEvent("high_five", "s1", "neon", "Neon", "查日志", side=-1)
        )
        self.assertEqual(self.pet.action_machine.current, PetAction.HIGH_FIVE)
        self.assertTrue(self.pet.player.snapshot().current.mirrored)


if __name__ == "__main__":
    unittest.main()
