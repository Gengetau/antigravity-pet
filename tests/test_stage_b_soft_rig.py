from __future__ import annotations

import os
import random
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from animation.asset_registry import AssetRegistry
from animation.clip import PetAction
from animation.soft_rig import RigParams, SoftRigController, SoftRigDeformer, _build_grid_weights
from app.paths import AppPaths
from pet.window import PetWindow
from settings.config import ConfigManager

ROOT = Path(__file__).resolve().parents[1]
BASE_MANIFEST = ROOT / "assets" / "manifests" / "actions_base.json"


class SoftRigControllerTests(unittest.TestCase):
    def test_cursor_gaze_tracks_and_blocks_during_sleep_or_sulk(self) -> None:
        ctrl = SoftRigController(random.Random(1))
        for _ in range(25):
            p = ctrl.step(0.033, cursor_dx=320.0, cursor_dy=-140.0, action_name="IDLE")
        self.assertGreater(p.look_x, 0.55)
        self.assertLess(p.look_y, -0.25)
        self.assertGreater(p.head_rot, 0.02)

        # Sleep/sulk smoothly returns gaze toward neutral
        for _ in range(35):
            p_sleep = ctrl.step(0.033, cursor_dx=320.0, cursor_dy=-140.0, action_name="SLEEPING")
        self.assertLess(abs(p_sleep.look_x), 0.1)

        # follow_cursor=False also neutralizes cursor tracking
        ctrl.follow_cursor = False
        for _ in range(30):
            p_off = ctrl.step(0.033, cursor_dx=-350.0, cursor_dy=150.0, action_name="IDLE")
        self.assertLess(abs(p_off.look_x), 0.1)

    def test_secondary_springs_follow_through_after_velocity_stop(self) -> None:
        ctrl = SoftRigController(random.Random(2))
        # Push pet strongly right (vx > 0) -> hair/skirt trail left (negative sway)
        for _ in range(8):
            p_move = ctrl.step(0.033, vx=900.0, vy=0.0, action_name="DRAGGING")
        self.assertLess(p_move.hair_sway_l, -2.5)
        self.assertLess(p_move.skirt_sway, -2.0)

        # Immediately stop moving -> spring still carries momentum and settles gradually
        p_after = ctrl.step(0.033, vx=0.0, vy=0.0, action_name="IDLE")
        self.assertLess(p_after.hair_sway_l, -1.5)
        for _ in range(60):
            p_rest = ctrl.step(0.033, vx=0.0, vy=0.0, action_name="IDLE")
        self.assertLess(abs(p_rest.hair_sway_l), 0.8)

    def test_quota_droop_gestures_and_reduced_motion(self) -> None:
        ctrl = SoftRigController(random.Random(3))
        for _ in range(30):
            p_low = ctrl.step(0.033, quota_pct=8.0, action_name="IDLE")
        self.assertGreater(p_low.quota_sag, 0.8)
        self.assertGreater(p_low.ear_l, 0.10)
        self.assertLess(p_low.ear_r, -0.10)
        self.assertGreater(p_low.ahoge, 0.18)

        ctrl.trigger("squish")
        for _ in range(6):
            p_sq = ctrl.step(0.033, action_name="IDLE")
        self.assertLess(p_sq.squash, -0.05)

        p_red = ctrl.step(0.033, vx=900.0, cursor_dx=300.0, quota_pct=5.0, reduced_motion=True)
        self.assertEqual(p_red.look_x, 0.0)
        self.assertEqual(p_red.hair_sway_l, 0.0)
        self.assertEqual(p_red.squash, 0.0)


class SoftRigDeformerAndRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_face_parallax_moves_in_cursor_direction_and_dock_seam_stays_locked(self) -> None:
        # Synthetic face dot at (80, 66) inside a 160x238 sprite
        img = QImage(160, 238, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        painter = QPainter(img)
        painter.setBrush(QColor(255, 80, 140, 255))
        painter.setPen(QColor(255, 80, 140, 255))
        painter.drawEllipse(74, 60, 12, 12)  # center at (80, 66)
        painter.end()
        pix = QPixmap.fromImage(img)

        deformer = SoftRigDeformer()
        out_r, pad_x, _pad_top = deformer.deform(pix, RigParams(look_x=1.0, hair_wave=0.0), asset_id="idle_front")
        out_l, _, _ = deformer.deform(pix, RigParams(look_x=-1.0, hair_wave=0.0), asset_id="idle_front")

        def centroid_x(qimg: QImage) -> float:
            total = 0.0
            wx = 0.0
            for y in range(40, 110):
                for x in range(qimg.width()):
                    a = qimg.pixelColor(x, y).alpha()
                    if a > 30:
                        total += a
                        wx += x * a
            return wx / max(1.0, total)

        cx_r = centroid_x(out_r) - pad_x
        cx_l = centroid_x(out_l) - pad_x
        self.assertGreater(cx_r, cx_l + 3.0, f"Positive look_x must shift face right: {cx_r:.2f} vs {cx_l:.2f}")

        # Dock seam mode keeps pad_x == 0 so left-wall seam never shifts off monitor border
        dock_img, dock_px, _ = deformer.deform(pix, RigParams(look_x=1.0, head_rot=0.1), asset_id="dock_peek")
        self.assertEqual(dock_px, 0)
        self.assertEqual(dock_img.width(), pix.width())

    def test_dock_seam_pins_wall_edge_and_allows_peeking_side_motion(self) -> None:
        g_left = _build_grid_weights(100, 200, mode="dock_left")
        g_right = _build_grid_weights(100, 200, mode="dock_right")
        stride = g_left.cols + 1
        mid_row = (g_left.rows // 2) * stride
        # dock_left pins nx=0 and nx=0.1 (left wall) while leaving nx=1 (right peeking side) mobile
        self.assertEqual(g_left.w_edge_mobility[mid_row + 0], 0.0)
        self.assertEqual(g_left.w_edge_mobility[mid_row + 1], 0.0)
        self.assertEqual(g_left.w_edge_mobility[mid_row + g_left.cols], 1.0)
        # dock_right pins nx=1 and nx=0.9 (right wall) while leaving nx=0 (left peeking side) mobile
        self.assertEqual(g_right.w_edge_mobility[mid_row + g_right.cols], 0.0)
        self.assertEqual(g_right.w_edge_mobility[mid_row + g_right.cols - 1], 0.0)
        self.assertEqual(g_right.w_edge_mobility[mid_row + 0], 1.0)

        deformer = SoftRigDeformer()
        strong = RigParams(
            time=1.5,
            look_x=1.0,
            look_y=1.0,
            head_rot=0.16,
            ear_l=0.22,
            ear_r=-0.22,
            hair_sway_l=9.0,
            hair_sway_r=9.0,
            hair_wave=2.8,
            breath=1.0,
        )
        reg = AssetRegistry(ROOT / "carbon", base_manifest=BASE_MANIFEST)
        for direction, asset_id, wall_side in (("dock_left", "dock_peek", "left"), ("dock_right", "dock_peek_right", "right")):
            pix = reg.clip_for(PetAction.IDLE, height=238, direction=direction).frames[0].pixmap
            orig = pix.toImage()
            out, px, py = deformer.deform(pix, strong, form_id="carbon", asset_id=asset_id)
            self.assertEqual(px, 0)
            w, h = orig.width(), orig.height()
            wall_x = 0 if wall_side == "left" else w - 1
            wall_alpha_diff = sum(abs(orig.pixelColor(wall_x, y).alpha() - out.pixelColor(wall_x, y + py).alpha()) for y in range(h))
            mid_alpha_diff = sum(abs(orig.pixelColor(w // 2, y).alpha() - out.pixelColor(w // 2, y + py).alpha()) for y in range(h))
            self.assertEqual(wall_alpha_diff, 0, f"{asset_id} wall edge column drifted by {wall_alpha_diff}")
            self.assertGreater(mid_alpha_diff, 100, f"{asset_id} peeking interior should still deform naturally")

    def test_deform_all_five_forms_real_sprites_fast_and_preserves_alpha(self) -> None:
        deformer = SoftRigDeformer()
        params = RigParams(time=2.3, look_x=0.65, look_y=-0.25, head_rot=0.04, ear_l=-0.15, hair_sway_l=4.0, breath=0.7)
        for form in ("carbon", "hydergon", "neon", "argon", "claude"):
            reg = AssetRegistry(ROOT / form, base_manifest=BASE_MANIFEST)
            pix = reg.clip_for(PetAction.IDLE, height=238, direction="down").frames[0].pixmap
            # Warm cache once
            deformer.deform(pix, params, form_id=form, asset_id="idle_front")
            t0 = time.perf_counter()
            out, pad_x, pad_top = deformer.deform(pix, params, form_id=form, asset_id="idle_front")
            dt_ms = (time.perf_counter() - t0) * 1000.0
            self.assertFalse(out.isNull(), form)
            self.assertEqual(out.width(), pix.width() + pad_x * 2)
            self.assertEqual(out.pixelColor(0, 0).alpha(), 0, f"{form} top-left corner must stay transparent")
            self.assertLess(dt_ms, 35.0, f"{form} mesh warp took {dt_ms:.2f}ms")

    def test_pet_window_paints_cleanly_with_soft_rig_and_follow_cursor_toggle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agy-stage-b-") as tmp:
            paths = AppPaths(app_dir=Path(tmp), bundle_dir=ROOT)
            cfg = ConfigManager(paths.config_path)
            cfg.set("mode", "still", save=False)
            cfg.set_nested("comfort", "reduced_motion", False, save=False)
            cfg.set_nested("agy", "telemetry_enabled", False, save=False)
            cfg.set_nested("agy", "hud_enabled", False, save=False)
            pet = PetWindow(paths, cfg)
            try:
                pet.timer.stop()
                pet.persistence_timer.stop()
                pet.show()
                pet.tick()
                grab = pet.grab()
                self.assertFalse(grab.isNull())
                pet.set_follow_cursor(False)
                self.assertFalse(pet.soft_rig.follow_cursor)
                self.assertFalse(pet.control_panel.follow_cursor.isChecked())
                pet.set_follow_cursor(True)
                self.assertTrue(pet.soft_rig.follow_cursor)
                self.assertTrue(pet.control_panel.follow_cursor.isChecked())
            finally:
                pet.subagent_clones.close_all()
                for w in (pet.hud_bar, pet.token_meter, pet.control_panel, pet.food_panel):
                    w.hide()
                    w.close()
                pet.close()


if __name__ == "__main__":
    unittest.main()
