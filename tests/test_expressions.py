from __future__ import annotations

import unittest
from pathlib import Path

from animation.expressions import CALM, EXPRESSIONS, ExpressionDirector, ExpressionInput

ROOT = Path(__file__).resolve().parents[1]


class ExpressionDirectorTests(unittest.TestCase):
    def test_rules_pick_the_expected_face(self) -> None:
        director = ExpressionDirector()
        cases = [
            (ExpressionInput(now=0, hovered=True, running=True), "shy"),
            (ExpressionInput(now=0, quota_pct=10, running=True), "worried"),
            (ExpressionInput(now=0, running=True), "focused"),
            (ExpressionInput(now=0, annoyance=0.5), "pout"),
            (ExpressionInput(now=0, energy=0.1), "sleepy"),
            (ExpressionInput(now=0, user_idle_seconds=900), "sleepy"),
            (ExpressionInput(now=0, mood=0.9), "happy"),
            (ExpressionInput(now=0), CALM),
        ]
        for data, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(director.wanted(data), expected)

    def test_face_is_held_but_hover_and_cues_are_immediate(self) -> None:
        director = ExpressionDirector(hold_seconds=12)
        self.assertEqual(director.update(ExpressionInput(now=100, running=True)), "focused")
        # The agent stopped 3 s later: keep the face, no twitching.
        self.assertEqual(director.update(ExpressionInput(now=103)), "focused")
        self.assertEqual(director.update(ExpressionInput(now=113)), CALM)
        # Hover reacts at once, and leaving hover does too.
        self.assertEqual(director.update(ExpressionInput(now=114, hovered=True)), "shy")
        self.assertEqual(director.update(ExpressionInput(now=115)), CALM)
        director.cue("happy", 116)
        self.assertEqual(director.update(ExpressionInput(now=116)), "happy")
        self.assertEqual(director.update(ExpressionInput(now=130)), "happy")  # cue lasts ~20 s
        self.assertEqual(director.update(ExpressionInput(now=137)), CALM)

    def test_fade_runs_from_zero_to_one(self) -> None:
        director = ExpressionDirector(fade_seconds=0.2)
        director.update(ExpressionInput(now=10, hovered=True))
        self.assertEqual(director.previous, CALM)
        self.assertAlmostEqual(director.fade(10.0), 0.0)
        self.assertAlmostEqual(director.fade(10.1), 0.5)
        self.assertEqual(director.fade(11.0), 1.0)


class ExpressionAssetTests(unittest.TestCase):
    def test_every_form_has_all_expressions_matching_the_idle_frame(self) -> None:
        from PySide6.QtWidgets import QApplication

        from animation.asset_registry import AssetRegistry
        from animation.clip import PetAction

        QApplication.instance() or QApplication([])
        base = ROOT / "assets" / "manifests" / "actions_base.json"
        for form in ("carbon", "hydergon", "neon", "argon", "claude"):
            registry = AssetRegistry(ROOT / form, base_manifest=base)
            self.assertEqual(set(registry.expression_names()), set(EXPRESSIONS), form)
            for height in (187, 238, 306):
                idle = registry.program_for(PetAction.IDLE, height=height, direction="right").body.frames[0].pixmap
                for name in EXPRESSIONS:
                    with self.subTest(form=form, height=height, name=name):
                        face = registry.expression_pixmap(name, height)
                        self.assertIsNotNone(face)
                        self.assertEqual(face.size(), idle.size())
            self.assertIsNone(registry.expression_pixmap("nope", 238))


class ExpressionRenderTests(unittest.TestCase):
    def test_renderer_swaps_only_the_idle_frame(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage, QPainter, QPixmap
        from PySide6.QtWidgets import QApplication

        from animation.clip import Anchor, AnimationPhase, ClipFrame, PetAction
        from animation.player import RenderLayer
        from pet.renderer import PetRenderer

        QApplication.instance() or QApplication([])

        def solid(color) -> QPixmap:
            pixmap = QPixmap(20, 20)
            pixmap.fill(color)
            return pixmap

        idle, face = solid(Qt.GlobalColor.red), solid(Qt.GlobalColor.blue)

        def draw(asset_id: str, fade: float) -> tuple[int, int, int]:
            renderer = PetRenderer(0, 0)
            renderer.expression = ("idle_front", face, None, fade)
            layer = RenderLayer(ClipFrame(Path("x"), idle), PetAction.IDLE, Anchor(x=0.0, y=0.0), False, asset_id, AnimationPhase.BODY)
            image = QImage(40, 40, QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            renderer._draw_layer(painter, layer, renderer_point(0, 0), _no_pose(), 1.0)
            painter.end()
            color = image.pixelColor(5, 5)
            return color.red(), color.green(), color.blue()

        self.assertEqual(draw("idle_front", 1.0), (0, 0, 255))
        self.assertEqual(draw("walk_side", 1.0), (255, 0, 0))
        mid = draw("idle_front", 0.5)
        self.assertTrue(100 < mid[0] < 160 and 100 < mid[2] < 160, mid)


def renderer_point(x: float, y: float):
    from PySide6.QtCore import QPointF

    return QPointF(x, y)


def _no_pose():
    from animation.effects import EffectPose

    return EffectPose()


if __name__ == "__main__":
    unittest.main()
