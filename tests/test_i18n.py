from __future__ import annotations

from datetime import datetime
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from agy.autonomy import LINES as AUTONOMY_ZH_LINES, AgyAutonomy
from agy.characters import FORMS, form_tagline
from agy.hud_bar import HudBar
from agy.reactions import LINES as REACTION_ZH_LINES, ReactionTracker, greeting_for_moment, tool_status_name
from agy.speed_chart import SpeedComparisonView
from agy.telemetry import LiveSnapshot, format_reset_countdown
from agy.token_meter import TokenMeterWindow
from agy.usage_dashboard import UsageDashboard
from agy.usage_stats import format_duration, format_tokens_cn
from app import i18n, i18n_lines
from app.paths import AppPaths
from dialogue.local_rules import DialogueManager, load_form_voice
from dialogue.personality import personality_label
from pet.interaction import FoodPanel, parse_food_menu
from pet.scene_props import SCENE_SPECS, DesktopScenePropWidget
from pet.window import PetWindow
from settings.config import ConfigManager
from settings.panel import PetControlPanel

ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_DIR = ROOT / "assets" / "dialogue"
SHARED_FILES = (
    "coding.json",
    "daily.json",
    "document.json",
    "github.json",
    "idle.json",
    "inner_voice.json",
    "interaction.json",
    "late_night.json",
    "relationship.json",
    "routine.json",
    "state.json",
    "video.json",
)
FORM_IDS = tuple(f.id for f in FORMS)
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(text))


def _panel(on_language=None) -> PetControlPanel:
    return PetControlPanel(
        on_mode=lambda _mode: None,
        on_size=lambda _size: None,
        on_feed=lambda: None,
        on_say=lambda: None,
        on_snap=lambda: None,
        on_awareness=lambda _enabled: None,
        on_read_window_title=lambda _enabled: None,
        on_idle_detection=lambda _enabled: None,
        on_topmost=lambda _enabled: None,
        on_fullscreen_hide=lambda _enabled: None,
        on_passthrough=lambda _enabled: None,
        on_autostart=lambda _enabled: None,
        on_activity_level=lambda _level: None,
        on_walk_speed=lambda _speed: None,
        on_reduced_motion=lambda _enabled: None,
        on_hover_pause=lambda _enabled: None,
        on_desktop_surfaces=lambda _enabled: None,
        on_action=lambda _action: None,
        on_hide=lambda: None,
        on_privacy=lambda: None,
        on_quit=lambda: None,
        on_language=on_language,
    )


class I18nCoreTests(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("auto")

    def test_normalize_and_resolve_language_settings(self) -> None:
        self.assertEqual(i18n.normalize_language_setting("auto"), "auto")
        self.assertEqual(i18n.normalize_language_setting("system"), "auto")
        self.assertEqual(i18n.normalize_language_setting(""), "auto")
        self.assertEqual(i18n.normalize_language_setting("EN_US"), "en")
        self.assertEqual(i18n.normalize_language_setting("ja-JP"), "ja")
        self.assertEqual(i18n.normalize_language_setting("zh-Hans"), "zh")
        self.assertEqual(i18n.normalize_language_setting("unknown-xx"), "auto")

        self.assertEqual(i18n.resolve_language("en"), "en")
        self.assertEqual(i18n.resolve_language("ja"), "ja")
        self.assertEqual(i18n.resolve_language("zh"), "zh")

    def test_detect_system_language_env_override_and_fallback(self) -> None:
        with mock.patch.dict(os.environ, {"AGY_PET_LANG": "ja"}, clear=False):
            self.assertEqual(i18n.detect_system_language(), "ja")
        with mock.patch.dict(os.environ, {"AGY_PET_LANG": "en_GB"}, clear=False):
            self.assertEqual(i18n.detect_system_language(), "en")
        with mock.patch.dict(os.environ, {"AGY_PET_LANG": "zh_CN"}, clear=False):
            self.assertEqual(i18n.detect_system_language(), "zh")
        # Other non-CJK locales default cleanly to English
        self.assertEqual(i18n._locale_tag_to_lang("fr_FR"), "en")
        self.assertEqual(i18n._locale_tag_to_lang("de-DE"), "en")
        self.assertIsNone(i18n._locale_tag_to_lang("C"))
        self.assertIsNone(i18n._locale_tag_to_lang("POSIX"))

    def test_strings_catalog_complete_and_placeholders_match(self) -> None:
        self.assertGreater(len(i18n.STRINGS), 100)
        for key, entry in i18n.STRINGS.items():
            for lang in i18n.SUPPORTED_LANGUAGES:
                self.assertIn(lang, entry, f"Missing {lang} in STRINGS[{key!r}]")
                self.assertTrue(entry[lang].strip(), f"Empty {lang} in STRINGS[{key!r}]")
            zh_vars = _placeholders(entry["zh"])
            self.assertEqual(_placeholders(entry["en"]), zh_vars, f"Placeholder mismatch in STRINGS[{key!r}]['en']")
            self.assertEqual(_placeholders(entry["ja"]), zh_vars, f"Placeholder mismatch in STRINGS[{key!r}]['ja']")

    def test_i18n_lines_catalogs_complete_and_placeholders_match(self) -> None:
        # Tables with all 3 languages (zh / en / ja)
        for name, table in (
            ("PET_STATE_NAMES", i18n_lines.PET_STATE_NAMES),
            ("WINDOW_MESSAGES", i18n_lines.WINDOW_MESSAGES),
        ):
            zh_keys = set(table["zh"].keys())
            for lang in ("en", "ja"):
                self.assertEqual(set(table[lang].keys()), zh_keys, f"{name}[{lang}] keys differ from zh")
                for key in zh_keys:
                    zh_val = table["zh"][key]
                    loc_val = table[lang][key]
                    self.assertTrue(loc_val.strip(), f"Empty string in {name}[{lang}][{key!r}]")
                    self.assertEqual(_placeholders(loc_val), _placeholders(zh_val), f"Placeholder mismatch in {name}[{lang}][{key!r}]")

        # Tables with en / ja overrides (zh defaults live in source modules)
        for name, table in (
            ("REACTION_TOOL_STATUS", i18n_lines.REACTION_TOOL_STATUS),
            ("GREETING_LINES", i18n_lines.GREETING_LINES),
            ("CLONE_POOLS", i18n_lines.CLONE_POOLS),
        ):
            en_keys = set(table["en"].keys())
            ja_keys = set(table["ja"].keys())
            self.assertEqual(ja_keys, en_keys, f"{name} ja keys differ from en")

        # SCENE_PROP_TEXT en/ja must cover every SCENE_SPECS kind
        for lang in ("en", "ja"):
            self.assertEqual(set(i18n_lines.SCENE_PROP_TEXT[lang].keys()), set(SCENE_SPECS.keys()))
            for kind, entry in i18n_lines.SCENE_PROP_TEXT[lang].items():
                self.assertTrue(entry["label"].strip())
                self.assertTrue(entry["tooltip"].strip())
                self.assertGreater(len(entry["click_lines"]), 0)

        # REACTION_LINES & AUTONOMY_LINES en/ja must match the live Chinese defaults in reactions.py / autonomy.py
        for name, zh_base, loc_table in (
            ("REACTION_LINES", REACTION_ZH_LINES, i18n_lines.REACTION_LINES),
            ("AUTONOMY_LINES", AUTONOMY_ZH_LINES, i18n_lines.AUTONOMY_LINES),
        ):
            zh_keys = set(zh_base.keys())
            for lang in ("en", "ja"):
                self.assertEqual(set(loc_table[lang].keys()), zh_keys, f"{name}[{lang}] keys differ from zh defaults")
                for key in zh_keys:
                    self.assertGreater(len(loc_table[lang][key]), 0)
                    zh_vars = set().union(*(_placeholders(s) for s in zh_base[key]))
                    loc_vars = set().union(*(_placeholders(s) for s in loc_table[lang][key]))
                    self.assertEqual(loc_vars, zh_vars, f"Placeholder mismatch in {name}[{lang}][{key!r}]")

        self.assertEqual(set(i18n_lines.CLONE_HOST_CALL.keys()), set(i18n.SUPPORTED_LANGUAGES))
        self.assertEqual(set(i18n_lines.IDLE_PLAY_ACTIVITIES.keys()), set(i18n.SUPPORTED_LANGUAGES))

    def test_formatters_and_helpers_in_all_languages(self) -> None:
        self.assertEqual(i18n.format_tokens_localized(15000, lang="zh"), "1.5万")
        self.assertEqual(i18n.format_tokens_localized(15000, lang="en"), "15K")
        self.assertEqual(i18n.format_tokens_localized(15000, lang="ja"), "1.5万")
        self.assertEqual(i18n.format_tokens_localized(250_000_000, lang="ja"), "2.5億")
        self.assertEqual(i18n.format_tokens_localized(250_000_000, lang="en"), "250M")

        i18n.set_language("zh")
        self.assertEqual(format_tokens_cn(15000), "1.5万")
        self.assertIn("小时", format_duration(90 * 60_000))
        i18n.set_language("en")
        self.assertEqual(format_tokens_cn(15000), "15K")
        self.assertEqual(format_duration(90 * 60_000), "1h 30m")
        i18n.set_language("ja")
        self.assertEqual(format_tokens_cn(250_000_000), "2.5億")
        self.assertEqual(format_duration(90 * 60_000), "1時間30分")

        now_ms = 1795791600_000
        i18n.set_language("zh")
        self.assertIn("重置", format_reset_countdown("2026-11-27T16:00:00Z", now_ms=now_ms))
        i18n.set_language("en")
        self.assertIn("resets", format_reset_countdown("2026-11-27T16:00:00Z", now_ms=now_ms).lower())
        i18n.set_language("ja")
        self.assertIn("リセット", format_reset_countdown("2026-11-27T16:00:00Z", now_ms=now_ms))

        for lang in i18n.SUPPORTED_LANGUAGES:
            i18n.set_language(lang)
            self.assertEqual(len(i18n.weekday_labels(lang=lang)), 7)
            self.assertTrue(i18n.format_month_label(2026, 11, lang=lang))
            self.assertTrue(i18n.format_short_month(11, lang=lang))
            self.assertTrue(personality_label("standard", lang=lang))
            self.assertTrue(form_tagline("carbon", lang=lang))
            self.assertTrue(tool_status_name("running"))
            self.assertTrue(greeting_for_moment(datetime(2026, 11, 27, 10, 0)))


class DialoguePacksParityTests(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("auto")

    def _assert_structure_matches(self, base: object, localized: object, context: str) -> None:
        self.assertEqual(type(localized), type(base), f"Type mismatch at {context}")
        if isinstance(base, dict):
            self.assertEqual(set(localized.keys()), set(base.keys()), f"Key mismatch at {context}")
            for key in base:
                self._assert_structure_matches(base[key], localized[key], f"{context}.{key}")
        elif isinstance(base, list):
            self.assertGreater(len(localized), 0, f"Empty list at {context}")
            self.assertEqual(len(localized), len(base), f"Length mismatch at {context}")
            for idx, (b_item, l_item) in enumerate(zip(base, localized)):
                if isinstance(b_item, str):
                    self.assertTrue(l_item.strip(), f"Empty line at {context}[{idx}]")
                    self.assertEqual(
                        _placeholders(l_item),
                        _placeholders(b_item),
                        f"Placeholder mismatch at {context}[{idx}]: {l_item!r} vs {b_item!r}",
                    )
                else:
                    self._assert_structure_matches(b_item, l_item, f"{context}[{idx}]")
        elif isinstance(base, str):
            self.assertTrue(localized.strip(), f"Empty string at {context}")

    def test_all_five_forms_have_complete_en_and_ja_packs(self) -> None:
        sample_kwargs = {
            "total": "12.3K",
            "rate": "142",
            "quota": "18",
            "reset": "Resets in 1h",
            "ctx": "82",
            "model": "Gemini 4 Carbon",
            "form": "Carbon",
            "minutes": "90",
        }
        for form_id in FORM_IDS:
            zh_data = json.loads((DIALOGUE_DIR / "forms" / f"{form_id}.json").read_text(encoding="utf-8"))
            for lang in ("en", "ja"):
                loc_path = DIALOGUE_DIR / "locales" / lang / "forms" / f"{form_id}.json"
                self.assertTrue(loc_path.exists(), f"Missing localized form pack: {loc_path}")
                loc_data = json.loads(loc_path.read_text(encoding="utf-8"))
                self._assert_structure_matches(zh_data, loc_data, f"{lang}/forms/{form_id}")
                self.assertEqual(loc_data["form"], zh_data["form"])

                # Food menu ids, icons, and tastes MUST stay identical across languages
                for idx, (zh_food, loc_food) in enumerate(zip(zh_data["food_menu"], loc_data["food_menu"])):
                    self.assertEqual(loc_food["id"], zh_food["id"], f"food_menu[{idx}].id mismatch in {lang}/{form_id}")
                    self.assertEqual(loc_food["icon"], zh_food["icon"], f"food_menu[{idx}].icon mismatch in {lang}/{form_id}")
                    self.assertEqual(loc_food["taste"], zh_food["taste"], f"food_menu[{idx}].taste mismatch in {lang}/{form_id}")
                    self.assertTrue(loc_food["name"].strip())

                # Every agy template must format cleanly without KeyError
                for key, lines in loc_data["agy"].items():
                    for line in lines:
                        rendered = line.format(**sample_kwargs)
                        self.assertTrue(rendered.strip(), f"Empty rendered agy.{key} in {lang}/{form_id}")

    def test_all_twelve_shared_dialogue_files_have_complete_en_and_ja_packs(self) -> None:
        for filename in SHARED_FILES:
            zh_data = json.loads((DIALOGUE_DIR / filename).read_text(encoding="utf-8"))
            for lang in ("en", "ja"):
                loc_path = DIALOGUE_DIR / "locales" / lang / filename
                self.assertTrue(loc_path.exists(), f"Missing localized shared dialogue: {loc_path}")
                loc_data = json.loads(loc_path.read_text(encoding="utf-8"))
                self._assert_structure_matches(zh_data, loc_data, f"{lang}/{filename}")

    def test_dialogue_manager_and_form_voice_switch_languages_live(self) -> None:
        i18n.set_language("en")
        dm = DialogueManager(DIALOGUE_DIR)
        dm.set_language("en")
        en_voice = load_form_voice(DIALOGUE_DIR, "carbon", lang="en")
        self.assertIsNotNone(en_voice)
        self.assertEqual(en_voice["food_menu"][0]["name"], "Black Coffee")
        dm.set_form_lines(en_voice["dialogue"])
        line_en = dm.pick_daily(personality="standard")
        self.assertTrue(line_en.isascii() or "…" in line_en or "—" in line_en or "₂" in line_en)
        shared_en = dm.pick_daily(personality="sharp")
        self.assertTrue(shared_en.isascii() or "…" in shared_en or "—" in shared_en)

        dm.set_language("ja")
        ja_voice = load_form_voice(DIALOGUE_DIR, "carbon", lang="ja")
        self.assertIsNotNone(ja_voice)
        self.assertEqual(ja_voice["food_menu"][0]["name"], "ブラックコーヒー")
        dm.set_form_lines(ja_voice["dialogue"])
        line_ja = dm.pick_daily(personality="standard")
        self.assertTrue(any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in line_ja))
        shared_ja = dm.pick_daily(personality="sharp")
        self.assertTrue(any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in shared_ja))

        fallback_voice = load_form_voice(DIALOGUE_DIR, "carbon", lang="zh")
        self.assertEqual(fallback_voice["food_menu"][0]["name"], "黑咖啡")


class QtLiveRetranslateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        i18n.set_language("auto")

    def test_control_panel_language_buttons_and_retranslate(self) -> None:
        picked: list[str] = []
        panel = _panel(on_language=picked.append)
        try:
            i18n.set_language("en")
            panel.retranslate()
            self.assertEqual(panel._quick_buttons["feed"].text(), i18n.tr("panel.feed", lang="en"))
            self.assertEqual(panel._quick_buttons["say"].text(), i18n.tr("panel.say", lang="en"))

            i18n.set_language("ja")
            panel.retranslate()
            self.assertEqual(panel._quick_buttons["feed"].text(), i18n.tr("panel.feed", lang="ja"))
            self.assertEqual(panel._quick_buttons["say"].text(), i18n.tr("panel.say", lang="ja"))

            panel._lang_buttons["en"].click()
            self.assertEqual(picked, ["en"])
        finally:
            panel.close()

    def test_hud_bar_food_panel_and_scene_prop_retranslate(self) -> None:
        hud = HudBar(
            settings={"hud_appearance": "dialog", "hud_mode": "attached"},
            on_open_meter=lambda: None,
            on_refresh=lambda: None,
            on_pin=lambda _cid: None,
            on_hide=lambda: None,
        )
        food = FoodPanel(on_pick=lambda _item: None)
        prop = DesktopScenePropWidget()
        try:
            snap = LiveSnapshot(
                source="ls",
                title="i18n session",
                status="CASCADE_RUN_STATUS_RUNNING",
                selected_model_label="Gemini 4 Carbon",
                quota_remaining_pct=82,
            )
            i18n.set_language("en")
            hud.update_snapshot(snap)
            hud.retranslate()
            self.assertIn("Context", hud._card_captions["context"].text())
            self.assertIn("Running", hud.card_title.text())

            food.set_menu(parse_food_menu(load_form_voice(DIALOGUE_DIR, "claude", lang="en")["food_menu"]), accent="#a78bfa")
            food.retranslate()
            self.assertEqual(food._close.text(), i18n.tr("food.close", lang="en"))
            self.assertIn("Black Tea", food.buttons[0].text())

            prop.retranslate()
            self.assertIn("Tea Party", prop.toolTip())
            self.assertTrue(prop.trigger_interact().strip())

            i18n.set_language("ja")
            hud.retranslate()
            self.assertIn("文脈", hud._card_captions["context"].text())
            food.set_menu(parse_food_menu(load_form_voice(DIALOGUE_DIR, "claude", lang="ja")["food_menu"]), accent="#a78bfa")
            food.retranslate()
            self.assertEqual(food._close.text(), i18n.tr("food.close", lang="ja"))
            self.assertIn("紅茶", food.buttons[0].text())

            prop.retranslate()
            self.assertIn("アフタヌーンティー会", prop.toolTip())
        finally:
            hud.close()
            food.close()
            prop.close()

    def test_token_meter_usage_dashboard_and_speed_chart_retranslate(self) -> None:
        meter = TokenMeterWindow(
            on_request_report=lambda: None,
            on_toggle_subagents=lambda _v: None,
        )
        dash = UsageDashboard()
        chart = SpeedComparisonView()
        try:
            for lang in ("en", "ja", "zh"):
                i18n.set_language(lang)
                meter.retranslate()
                dash.retranslate()
                chart.retranslate()
                self.assertEqual(meter.windowTitle(), i18n.tr("meter.win_title", lang=lang))
                self.assertEqual(meter._tab_buttons["overview"].text(), i18n.tr("meter.tab.overview", lang=lang))
        finally:
            meter.close()
            dash.close()
            chart.close()

    def test_reactions_autonomy_and_clone_helpers_switch_languages(self) -> None:
        tracker = ReactionTracker()
        autonomy = AgyAutonomy()
        i18n.set_language("en")
        self.assertIn("token", tracker._line("finished", total="12K", rate="120").lower())
        self.assertIn("min", autonomy._line("stretch", minutes=90))
        self.assertEqual(i18n_lines.clone_host_call(), "Big Sis")

        i18n.set_language("ja")
        self.assertIn("token", tracker._line("finished", total="12K", rate="120").lower())
        self.assertIn("分", autonomy._line("stretch", minutes=90))
        self.assertEqual(i18n_lines.clone_host_call(), "お姉さま")

    def test_pet_window_live_language_switch_and_external_config_hot_reload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agy-i18n-window-") as tmpdir:
            paths = AppPaths(app_dir=Path(tmpdir), bundle_dir=ROOT)
            config = ConfigManager(paths.config_path)
            config.set_nested("agy", "telemetry_enabled", False, save=False)
            config.set_nested("awareness", "enabled", False, save=True)
            pet = PetWindow(paths, config)
            try:
                pet.telemetry.stop()
                pet.timer.stop()
                pet.persistence_timer.stop()
                pet.awareness_timer.stop()
                pet.surface_timer.stop()
                self.app.processEvents()

                # Direct live switch to English
                pet.set_language("en")
                self.app.processEvents()
                self.assertEqual(i18n.get_language(), "en")
                self.assertEqual(config.get("agy")["language"], "en")
                self.assertEqual(pet.control_panel._quick_buttons["feed"].text(), "Feed")
                self.assertIn("Black Coffee", pet.food_panel.buttons[0].text())
                self.assertEqual(pet.token_meter.windowTitle(), i18n.tr("meter.win_title", lang="en"))
                self.assertEqual(pet._tray_toggle_action.text(), i18n.tr("tray.toggle_visible", lang="en"))
                self.assertTrue(pet._tray_lang_actions["en"].isChecked())
                self.assertEqual(pet.dialogue._lang, "en")

                # Simulate external sidecar writing language="ja" to config.json
                raw = json.loads(paths.config_path.read_text(encoding="utf-8"))
                raw["agy"]["language"] = "ja"
                paths.config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                stat = paths.config_path.stat()
                os.utime(paths.config_path, (stat.st_atime, stat.st_mtime + 5.0))

                pet._sync_external_config()
                self.app.processEvents()
                self.assertEqual(i18n.get_language(), "ja")
                self.assertEqual(pet.control_panel._quick_buttons["feed"].text(), "おやつ")
                self.assertIn("ブラックコーヒー", pet.food_panel.buttons[0].text())
                self.assertEqual(pet.token_meter.windowTitle(), i18n.tr("meter.win_title", lang="ja"))
                self.assertEqual(pet._tray_toggle_action.text(), i18n.tr("tray.toggle_visible", lang="ja"))
                self.assertTrue(pet._tray_lang_actions["ja"].isChecked())
                self.assertEqual(pet.dialogue._lang, "ja")
            finally:
                pet.subagent_clones.close_all()
                pet.hud_bar.hide()
                pet.token_meter.hide()
                pet.control_panel.hide()
                pet.food_panel.hide()
                pet.tray.hide()
                pet.hide()
                pet.close()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
