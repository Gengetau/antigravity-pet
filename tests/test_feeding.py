from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMS = ("carbon", "hydergon", "neon", "argon", "claude")


class FoodMenuTests(unittest.TestCase):
    def test_every_form_has_its_own_menu(self) -> None:
        menus = {}
        for form in FORMS:
            voice = json.loads((ROOT / "assets" / "dialogue" / "forms" / f"{form}.json").read_text(encoding="utf-8"))
            menu = voice["food_menu"]
            self.assertEqual(len(menu), 5, form)
            tastes = [item["taste"] for item in menu]
            self.assertEqual(tastes.count("favorite"), 1, form)
            self.assertEqual(tastes.count("dislike"), 1, form)
            for item in menu:
                self.assertTrue(item["lines"], (form, item["id"]))
                self.assertLessEqual(len(item["name"]), 3, item["name"])  # fits the button
            menus[form] = tuple(item["name"] for item in menu)
        self.assertEqual(len(set(menus.values())), len(FORMS))


class FeedingTests(unittest.TestCase):
    def setUp(self) -> None:
        from PySide6.QtWidgets import QApplication

        from app.paths import AppPaths
        from pet.window import PetWindow
        from settings.config import ConfigManager

        QApplication.instance() or QApplication([])
        self.folder = tempfile.TemporaryDirectory()
        paths = AppPaths(app_dir=Path(self.folder.name), bundle_dir=ROOT)
        self.window = PetWindow(paths, ConfigManager(paths.config_path))

    def tearDown(self) -> None:
        window = self.window
        window.telemetry.stop()
        for widget in (window.hud_bar, window.token_meter, window.control_panel, window.food_panel):
            widget.close()
        window.tray.hide()
        window.close()
        self.folder.cleanup()

    def menu(self, form):
        return json.loads((ROOT / "assets" / "dialogue" / "forms" / f"{form}.json").read_text(encoding="utf-8"))["food_menu"]

    def test_panel_follows_the_form(self) -> None:
        for form in FORMS:
            self.window.set_form(form, manual=True, announce=False)
            names = [item.name for item in self.window.food_panel.items]
            self.assertEqual(names, [item["name"] for item in self.menu(form)])
            self.assertEqual(len(self.window.food_panel.buttons), 5)

    def test_favorite_dislike_and_normal_food(self) -> None:
        from animation.clip import PetAction

        window = self.window
        window.set_form("argon", manual=True, announce=False)
        menu = {item["taste"]: item for item in self.menu("argon")}
        state = window.pet_state

        fed, mood = state.total_feedings, state.mood = state.total_feedings, 0.5
        window._request_action(PetAction.IDLE, reason="test", force=True, immediate=True)  # transform done
        window.on_food(menu["favorite"]["id"])
        self.assertEqual(window.action_machine.current, PetAction.EATING)
        self.assertEqual(window.action_machine._queued_after, PetAction.HAPPY)
        self.assertIn(window.bubble.text, menu["favorite"]["lines"])
        self.assertEqual(state.total_feedings, fed + 1)
        self.assertAlmostEqual(state.mood, 0.62)

        window._request_action(PetAction.IDLE, reason="test", force=True)
        window.on_food(menu["dislike"]["id"])
        self.assertEqual(window.action_machine.current, PetAction.POKE_REACT)
        self.assertIn(window.bubble.text, menu["dislike"]["lines"])
        self.assertEqual(state.total_feedings, fed + 1)  # turned down, not eaten

        normal = next(item for item in self.menu("argon") if item["taste"] == "normal")
        window._request_action(PetAction.IDLE, reason="test", force=True)
        window.on_food(normal["id"])
        self.assertEqual(window.action_machine.current, PetAction.EATING)
        self.assertEqual(state.total_feedings, fed + 2)


if __name__ == "__main__":
    unittest.main()
