from __future__ import annotations

import importlib.util
import json
import math
import os
import random
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from agy.reactions import ReactionTracker
from agy.telemetry import LiveSnapshot
from animation.asset_registry import TOOL_WORK_ASSETS, AssetRegistry
from animation.clip import PetAction
from animation.effects import pose_for
from app.paths import AppPaths
from pet.window import PetWindow
from settings.config import ConfigManager

ROOT = Path(__file__).resolve().parents[1]
BASE_MANIFEST = ROOT / "assets" / "manifests" / "actions_base.json"
ALL_FORMS = ("carbon", "hydergon", "neon", "argon", "claude")


class StageCStrongPropActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_all_five_forms_ship_real_frames_for_stage_c_strong_prop_poses(self) -> None:
        cases = (
            (PetAction.WORK_READING, "work_reading", 2, 420, None, "work_typing"),
            (PetAction.WORK_SEARCHING, "work_searching", 2, 380, None, "idle_think"),
            (PetAction.WORK_DRAWING, "work_drawing", 2, 320, None, "work_typing"),
            (PetAction.WORK_COMPACTING, "work_compacting", 2, 260, 2080, "work_typing"),
            (PetAction.QUOTA_GIFT, "quota_gift", 2, 300, 2400, "celebrate"),
        )
        for form in ALL_FORMS:
            reg = AssetRegistry(ROOT / form, base_manifest=BASE_MANIFEST)
            for action, asset_name, expected_frames, frame_ms, duration_ms, _fb in cases:
                spec = reg.specs[action]
                self.assertEqual(spec.frame_ms, frame_ms, (form, action))
                self.assertEqual(spec.duration_ms, duration_ms, (form, action))
                if duration_ms is not None:
                    self.assertEqual(duration_ms % (expected_frames * frame_ms), 0, (form, action))
                clip = reg.clip_for(action, height=238, direction="down")
                self.assertEqual(clip.asset_id, asset_name, (form, action))
                self.assertEqual(len(clip.frames), expected_frames, (form, asset_name))
                self.assertTrue(all(not f.pixmap.isNull() for f in clip.frames), (form, asset_name))
                self.assertTrue(all(f.pixmap.hasAlphaChannel() for f in clip.frames), (form, asset_name))

            # Verify v3.2 interplay + Stage C keys all coexist in every form's manifest
            raw_manifest = json.loads((ROOT / form / "manifests" / "actions.json").read_text(encoding="utf-8"))
            manifest_assets = raw_manifest["assets"]
            for required_key in (
                "high_five",
                "play_dance",
                "gift_toss",
                "summon_pop",
                "depart_poof",
                "work_reading",
                "work_searching",
                "work_drawing",
                "work_compacting",
                "quota_gift",
            ):
                self.assertIn(required_key, manifest_assets, (form, required_key))
                self.assertTrue(manifest_assets[required_key]["frames"]["238"], (form, required_key))

            # Verify dynamic tool_category resolution under PetAction.WORKING
            for direction, expected_asset in TOOL_WORK_ASSETS.items():
                clip = reg.clip_for(PetAction.WORKING, height=238, direction=direction)
                self.assertEqual(clip.asset_id, expected_asset, (form, direction))
                self.assertEqual(len(clip.frames), 2, (form, direction))

        # Verify graceful fallback if an asset is removed
        reg = AssetRegistry(ROOT / "neon", base_manifest=BASE_MANIFEST)
        for action, asset_name, _n, _fms, _dms, fallback in cases:
            reg._assets.pop(asset_name, None)
            reg._frame_cache.clear()
            self.assertEqual(reg.clip_for(action, height=238, direction="down").asset_id, fallback)

    def test_stage_c_procedural_effects_are_distinct_and_bounded(self) -> None:
        for name in ("work_reading", "work_searching", "work_drawing", "work_compacting", "quota_gift"):
            poses = [pose_for(name, i / 60.0) for i in range(120)]
            for pose in poses:
                self.assertLessEqual(abs(pose.offset_x), 8.0, name)
                self.assertGreaterEqual(pose.offset_y, -10.0, name)
                self.assertLessEqual(pose.offset_y, 6.0, name)
                self.assertTrue(0.85 <= pose.scale_x <= 1.15 and 0.85 <= pose.scale_y <= 1.15, name)
                self.assertLessEqual(abs(pose.rotation_degrees), 10.0, name)
                self.assertTrue(all(math.isfinite(v) for v in (pose.offset_x, pose.offset_y, pose.scale_x, pose.scale_y)))

    def test_reactions_and_live_window_switch_strong_props_by_tool_category(self) -> None:
        tracker = ReactionTracker(random.Random(0), cooldown_seconds=60.0)
        tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", quota_remaining_pct=20.0),
            now=100.0,
            follow_model=False,
            current_form="carbon",
        )
        r_refill = tracker.observe(
            LiveSnapshot(source="pet_live", conversation_id="c1", quota_remaining_pct=100.0, context_used_tokens=180_000, context_limit_tokens=200_000),
            now=120.0,
            follow_model=False,
            current_form="carbon",
        )
        by_kind = {r.kind: r for r in r_refill}
        self.assertEqual(by_kind["quota_refilled"].action, "QUOTA_GIFT")
        self.assertEqual(by_kind["quota_refilled"].particle, "fish")
        self.assertEqual(by_kind["context_high"].action, "WORK_COMPACTING")

        with tempfile.TemporaryDirectory(prefix="agy-stage-c-") as tmp:
            paths = AppPaths(app_dir=Path(tmp), bundle_dir=ROOT)
            cfg = ConfigManager(paths.config_path)
            cfg.set("mode", "still", save=False)
            cfg.set_nested("agy", "telemetry_enabled", False, save=False)
            cfg.set_nested("agy", "hud_enabled", False, save=False)
            pet = PetWindow(paths, cfg)
            try:
                pet.timer.stop()
                pet.persistence_timer.stop()
                pet._request_action(PetAction.WORKING, reason="test_work", force=True, immediate=True)
                for cat, expected_asset in (
                    ("reading", "work_reading"),
                    ("searching", "work_searching"),
                    ("drawing", "work_drawing"),
                    ("compacting", "work_compacting"),
                    ("writing", "work_typing"),
                ):
                    snap = LiveSnapshot(
                        source="pet_live",
                        conversation_id="c1",
                        status="CASCADE_RUN_STATUS_RUNNING",
                        latest_tool_category=cat,
                    )
                    pet.telemetry.last_snapshot = snap
                    pet._on_live_snapshot(snap)
                    self.assertEqual(pet.player.snapshot().current.asset_id, expected_asset, cat)
            finally:
                pet.subagent_clones.close_all()
                for w in (pet.hud_bar, pet.token_meter, pet.control_panel, pet.food_panel):
                    w.hide()
                    w.close()
                pet.close()

    def test_sprite_gen_install_preserves_manifest_key_order_on_partial_merge(self) -> None:
        spec = importlib.util.spec_from_file_location("sprite_gen_under_test", ROOT / "tools" / "sprite_gen" / "gen.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory(prefix="agy-gen-merge-") as tmp:
            root = Path(tmp)
            work = root / "art_work"
            backup = root / "art_backup"
            form_dir = root / "carbon"
            (form_dir / "manifests").mkdir(parents=True)
            (form_dir / "processed").mkdir(parents=True)
            old_manifest = {
                "format_version": 4,
                "character_id": "carbon",
                "assets": {
                    "idle_front": {"frame_count": 1, "frames": {"238": ["old_idle.png"]}},
                    "high_five": {"frame_count": 2, "frames": {"238": ["old_hf_0.png", "old_hf_1.png"]}},
                    "play_dance": {"frame_count": 4, "frames": {"238": ["pd.png"]}},
                    "depart_poof": {"frame_count": 4, "frames": {"238": ["dp.png"]}},
                },
            }
            (form_dir / "manifests" / "actions.json").write_text(
                json.dumps(old_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            staged = work / "carbon" / "processed_partial"
            (staged / "runtime" / "states" / "work_reading").mkdir(parents=True)
            (staged / "runtime" / "states" / "work_reading" / "work_reading_238_00.png").write_bytes(b"png")
            partial_manifest = {
                "format_version": 4,
                "character_id": "carbon",
                "assets": {
                    "high_five": {"frame_count": 2, "frames": {"238": ["new_hf_0.png", "new_hf_1.png"]}},
                    "work_reading": {"frame_count": 2, "frames": {"238": ["wr_0.png", "wr_1.png"]}},
                    "quota_gift": {"frame_count": 2, "frames": {"238": ["qg_0.png", "qg_1.png"]}},
                },
            }
            (work / "carbon" / "actions_partial.json").write_text(
                json.dumps(partial_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            args = types.SimpleNamespace(form="carbon", allow_partial=False, partial_stage=True)
            with mock.patch.object(mod, "ROOT", root), mock.patch.object(mod, "WORK", work), mock.patch.object(mod, "BACKUP", backup):
                mod.cmd_install(args)

            merged = json.loads((form_dir / "manifests" / "actions.json").read_text(encoding="utf-8"))
            self.assertEqual(
                list(merged["assets"].keys()),
                ["idle_front", "high_five", "play_dance", "depart_poof", "work_reading", "quota_gift"],
            )
            self.assertEqual(merged["assets"]["high_five"]["frames"]["238"], ["new_hf_0.png", "new_hf_1.png"])
            self.assertEqual(merged["assets"]["play_dance"]["frames"]["238"], ["pd.png"])
            self.assertEqual(merged["assets"]["depart_poof"]["frames"]["238"], ["dp.png"])


if __name__ == "__main__":
    unittest.main()
