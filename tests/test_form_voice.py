from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMS = ("carbon", "hydergon", "neon", "argon", "claude")


class FormVoiceTests(unittest.TestCase):
    def test_each_form_has_its_own_lines(self) -> None:
        voices = {f: json.loads((ROOT / "assets" / "dialogue" / "forms" / f"{f}.json").read_text(encoding="utf-8")) for f in FORMS}
        taps = {f: tuple(v["dialogue"]["interaction"]["tap"]) for f, v in voices.items()}
        self.assertEqual(len(set(taps.values())), len(FORMS))
        values = dict(total="1.2k", rate="88", quota="20", reset="2 小时后重置", ctx="85", model="Gemini", form="Neon", minutes="95")
        for voice in voices.values():
            for lines in voice["agy"].values():
                for line in lines:
                    line.format(**values)
            for line in voice["agy"]["finished"]:
                self.assertIn("{total}", line)

    def test_switching_form_switches_voice(self) -> None:
        from PySide6.QtWidgets import QApplication

        from app.paths import AppPaths
        from pet.window import PetWindow
        from settings.config import ConfigManager

        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            paths = AppPaths(app_dir=Path(folder), bundle_dir=ROOT)
            window = PetWindow(paths, ConfigManager(paths.config_path))
            try:
                for form in FORMS:
                    window.set_form(form, manual=True, announce=False)
                    voice = json.loads((ROOT / "assets" / "dialogue" / "forms" / f"{form}.json").read_text(encoding="utf-8"))
                    self.assertIn(window.dialogue.pick_interaction("tap", personality="standard"), voice["dialogue"]["interaction"]["tap"])
                    self.assertEqual(list(window.reactions.lines["started"]), voice["agy"]["started"])
                    self.assertEqual(list(window.autonomy.lines["hop"]), voice["agy"]["hop"])
                    self.assertEqual(window.renderer.speaker_name, voice["speaker"])
                    self.assertEqual(window.control_panel.title_label.text(), voice["speaker"])
                    window.set_form("carbon" if form != "carbon" else "neon", manual=True, announce=False)
                    window.set_form(form, manual=True, announce=True)
                    self.assertIn(window.bubble.text, voice["announce"])
                # other personalities still use the shared lines
                shared = json.loads((ROOT / "assets" / "dialogue" / "interaction.json").read_text(encoding="utf-8"))["tap"]["sharp"]
                self.assertIn(window.dialogue.pick_interaction("tap", personality="sharp"), shared)
            finally:
                window.telemetry.stop()
                for widget in (window.hud_bar, window.token_meter, window.control_panel, window.food_panel):
                    widget.close()
                window.tray.hide()
                window.close()


if __name__ == "__main__":
    unittest.main()
