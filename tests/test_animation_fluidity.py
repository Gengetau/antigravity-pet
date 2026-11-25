from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from animation.asset_registry import (
    BESPOKE_DOCK_ASSETS,
    DOCK_LEFT_ASSETS,
    DOCK_RIGHT_ASSETS,
    EDGE_ASSETS,
    AssetRegistry,
)
from animation.clip import (
    Anchor,
    AnimationClip,
    AnimationPhase,
    AnimationProgram,
    ClipFrame,
    PetAction,
)
from animation.effects import pose_for, scaled
from animation.player import (
    COMPATIBLE_CROSSFADE_GROUPS,
    COMPATIBLE_POSE_CROSSFADE_SECONDS,
    SAME_ASSET_CROSSFADE_SECONDS,
    AnimationPlayer,
)
from animation.state_machine import ActionStateMachine

ROOT = Path(__file__).resolve().parents[1]
BASE_MANIFEST = ROOT / "assets" / "manifests" / "actions_base.json"
ALL_FORMS = ("carbon", "hydergon", "neon", "argon", "claude")


def _make_clip(
    action: PetAction,
    asset_id: str,
    *,
    frame_count: int = 1,
    frame_duration_ms: int = 100,
    phase: AnimationPhase = AnimationPhase.BODY,
    duration_ms: int | None = None,
    loop: bool = True,
    cycle: bool = False,
    mirrored: bool = False,
    anchor: Anchor | None = None,
) -> AnimationClip:
    frames = tuple(
        ClipFrame(Path(f"{asset_id}_{i}.png"), object())  # type: ignore[arg-type]
        for i in range(frame_count)
    )
    return AnimationClip(
        action=action,
        asset_id=asset_id,
        frames=frames,
        loop=loop,
        duration_ms=duration_ms,
        frame_duration_ms=frame_duration_ms,
        anchor=anchor or Anchor(),
        effect="breath",
        quality="source",
        requires_real_frames=False,
        mirrored=mirrored,
        phase=phase,
        cycle=cycle,
    )


class ExitTransitionHoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AssetRegistry(ROOT / "neon", base_manifest=BASE_MANIFEST)
        self.machine = ActionStateMachine(self.registry.specs)

    def test_sleep_wake_exit_holds_new_action_duration_until_exit_finishes(self) -> None:
        player = AnimationPlayer()
        sleeping = AnimationProgram(
            action=PetAction.SLEEPING,
            body=_make_clip(PetAction.SLEEPING, "sleep", frame_count=3, frame_duration_ms=750),
            exit=_make_clip(
                PetAction.SLEEPING,
                "sleep_wake",
                frame_count=3,
                frame_duration_ms=300,
                phase=AnimationPhase.EXIT,
                duration_ms=900,
                loop=False,
            ),
        )
        blink = AnimationProgram(
            action=PetAction.BLINK,
            body=_make_clip(
                PetAction.BLINK,
                "idle_blink",
                frame_count=5,
                frame_duration_ms=112,
                duration_ms=560,
                loop=False,
            ),
        )
        self.machine.request(PetAction.SLEEPING, now=10.0, reason="nap", force=True)
        player.play(sleeping, crossfade=False, immediate=True)
        self.assertFalse(player.in_exit_transition)

        # Wake into BLINK (560ms) — shorter than sleep_wake (900ms)!
        change = self.machine.request(PetAction.BLINK, now=12.0, reason="wake", force=True)
        self.assertIsNotNone(change)
        player.play(blink, crossfade=False, immediate=False)
        self.assertTrue(player.in_exit_transition)

        # Simulate 60fps ticks through the 900ms sleep_wake exit transition.
        now = 12.0
        dt = 0.02
        for _ in range(44):  # 0.88s < 0.90s
            now += dt
            player.tick(dt)
            self.assertTrue(player.in_exit_transition)
            expired = self.machine.update(now=now, hold_duration=player.in_exit_transition)
            self.assertIsNone(expired)
            self.assertEqual(self.machine.current, PetAction.BLINK)

        # Next tick crosses 0.90s: exit finishes and BLINK body begins.
        now += dt  # 12.90s
        player.tick(dt)
        self.assertFalse(player.in_exit_transition)
        self.assertEqual(player.snapshot().current.action, PetAction.BLINK)
        self.assertIsNone(self.machine.update(now=now, hold_duration=player.in_exit_transition))

        # BLINK must stay active for almost its full 560ms after exit ended.
        self.assertIsNone(self.machine.update(now=now + 0.50, hold_duration=False))
        self.assertEqual(self.machine.current, PetAction.BLINK)
        finished = self.machine.update(now=now + 0.58, hold_duration=False)
        self.assertIsNotNone(finished)
        self.assertEqual(self.machine.current, PetAction.IDLE)

    def test_walk_stop_exit_holds_duration_and_preserves_queued_followup(self) -> None:
        player = AnimationPlayer()
        walking = AnimationProgram(
            action=PetAction.WALKING,
            body=_make_clip(PetAction.WALKING, "walk_side", frame_count=6, frame_duration_ms=120),
            exit=_make_clip(
                PetAction.WALKING,
                "walk_stop_left",
                frame_count=2,
                frame_duration_ms=150,
                phase=AnimationPhase.EXIT,
                duration_ms=300,
                loop=False,
            ),
        )
        happy = AnimationProgram(
            action=PetAction.HAPPY,
            body=_make_clip(
                PetAction.HAPPY,
                "happy",
                frame_count=6,
                frame_duration_ms=175,
                duration_ms=1050,
                loop=False,
                cycle=True,
            ),
        )
        self.machine.request(PetAction.WALKING, now=0.0, reason="walk", force=True)
        player.play(walking, crossfade=False, immediate=True)

        self.machine.request(PetAction.HAPPY, now=1.0, reason="reward")
        self.machine.queue_after_current(PetAction.WORKING)
        player.play(happy, crossfade=False, immediate=False)
        self.assertTrue(player.in_exit_transition)

        now = 1.0
        for _ in range(14):  # 0.28s
            now += 0.02
            player.tick(0.02)
            self.assertIsNone(self.machine.update(now=now, hold_duration=player.in_exit_transition))
        now += 0.02  # 0.30s -> exit done
        player.tick(0.02)
        self.assertFalse(player.in_exit_transition)
        self.assertIsNone(self.machine.update(now=now, hold_duration=False))

        # Still HAPPY at +0.95s after exit finished, then transitions to queued WORKING.
        self.assertIsNone(self.machine.update(now=now + 0.95, hold_duration=False))
        change = self.machine.update(now=now + 1.08, hold_duration=False)
        self.assertIsNotNone(change)
        self.assertEqual(change.current, PetAction.WORKING)

    def test_immediate_play_bypasses_exit_and_interrupts_running_exit(self) -> None:
        player = AnimationPlayer()
        sleeping = AnimationProgram(
            action=PetAction.SLEEPING,
            body=_make_clip(PetAction.SLEEPING, "sleep"),
            exit=_make_clip(
                PetAction.SLEEPING,
                "sleep_wake",
                phase=AnimationPhase.EXIT,
                duration_ms=900,
                loop=False,
            ),
        )
        wave = AnimationProgram(action=PetAction.WAVE, body=_make_clip(PetAction.WAVE, "wave"))
        poke = AnimationProgram(action=PetAction.POKE_REACT, body=_make_clip(PetAction.POKE_REACT, "poke_react"))

        # Case 1: immediate=True directly from SLEEPING body skips sleep_wake.
        player.play(sleeping, crossfade=False, immediate=True)
        player.play(poke, crossfade=False, immediate=True)
        self.assertFalse(player.in_exit_transition)
        self.assertEqual(player.snapshot().phase, AnimationPhase.BODY)
        self.assertEqual(player.snapshot().current.action, PetAction.POKE_REACT)

        # Case 2: immediate=True mid-exit cancels sleep_wake immediately.
        player.play(sleeping, crossfade=False, immediate=True)
        player.play(wave, crossfade=False, immediate=False)
        self.assertTrue(player.in_exit_transition)
        player.tick(0.20)
        # Re-playing the same pending program non-immediately must not reset exit.
        self.assertFalse(player.play(wave, crossfade=False, immediate=False))
        self.assertAlmostEqual(player.elapsed_seconds, 0.20, places=5)
        # User click with immediate=True bypasses remaining exit immediately.
        self.assertTrue(player.play(poke, crossfade=False, immediate=True))
        self.assertFalse(player.in_exit_transition)
        self.assertEqual(player.snapshot().current.action, PetAction.POKE_REACT)


class DynamicFrameRateScaleTests(unittest.TestCase):
    def test_frame_rate_scale_scales_body_without_affecting_enter_exit_or_crossfade(self) -> None:
        player = AnimationPlayer()
        walking = AnimationProgram(
            action=PetAction.WALKING,
            enter=_make_clip(
                PetAction.WALKING,
                "walk_start_left",
                frame_count=2,
                frame_duration_ms=130,
                phase=AnimationPhase.ENTER,
                duration_ms=260,
                loop=False,
            ),
            body=_make_clip(
                PetAction.WALKING,
                "walk_side",
                frame_count=6,
                frame_duration_ms=100,
                loop=True,
            ),
            exit=_make_clip(
                PetAction.WALKING,
                "walk_stop_left",
                frame_count=2,
                frame_duration_ms=150,
                phase=AnimationPhase.EXIT,
                duration_ms=300,
                loop=False,
            ),
        )
        player.play(walking, crossfade=False)
        # ENTER must still take full 260ms even with frame_rate_scale=3.0.
        player.tick(0.20, frame_rate_scale=3.0)
        self.assertEqual(player.snapshot().phase, AnimationPhase.ENTER)
        self.assertAlmostEqual(player.elapsed_seconds, 0.20, places=5)

        # Crossing ENTER->BODY in a single tick: 0.06s finishes ENTER at 1x,
        # remaining 0.04s advances BODY at 2.0x -> 0.08s BODY elapsed.
        player.tick(0.10, frame_rate_scale=2.0)
        self.assertEqual(player.snapshot().phase, AnimationPhase.BODY)
        self.assertAlmostEqual(player.elapsed_seconds, 0.08, places=5)
        self.assertEqual(player.snapshot().current.frame.source.name, "walk_side_0.png")

        # Advance 0.11s at 2.0x -> 0.08 + 0.22 = 0.30s -> frame index 3.
        player.tick(0.11, frame_rate_scale=2.0)
        self.assertEqual(player.snapshot().current.frame.source.name, "walk_side_3.png")

        # Slow scale (0.5x): 0.10s real -> 0.05s body -> 0.35s -> still frame 3.
        player.tick(0.10, frame_rate_scale=0.5)
        self.assertAlmostEqual(player.elapsed_seconds, 0.35, places=5)
        self.assertEqual(player.snapshot().current.frame.source.name, "walk_side_3.png")

        # EXIT must NOT be accelerated by frame_rate_scale=3.0.
        player.play(_make_clip(PetAction.IDLE, "idle_front"), crossfade=False)
        self.assertTrue(player.in_exit_transition)
        player.tick(0.25, frame_rate_scale=3.0)
        self.assertTrue(player.in_exit_transition)
        self.assertAlmostEqual(player.elapsed_seconds, 0.25, places=5)
        player.tick(0.06, frame_rate_scale=3.0)
        self.assertFalse(player.in_exit_transition)
        self.assertEqual(player.snapshot().current.action, PetAction.IDLE)

    def test_crossfade_timing_is_independent_of_frame_rate_scale(self) -> None:
        player = AnimationPlayer()
        player.play(_make_clip(PetAction.IDLE, "idle_front"), crossfade=False)
        player.play(_make_clip(PetAction.BLINK, "idle_blink"), crossfade=True)
        # Even at 3.0x frame_rate_scale, 0.035s real time is halfway through 0.07s crossfade!
        player.tick(0.035, frame_rate_scale=3.0)
        mid = player.snapshot()
        self.assertIsNotNone(mid.previous)
        self.assertAlmostEqual(mid.current_opacity, 0.5, places=2)
        # And even at 0.25x scale, another 0.04s real time completes the 0.07s crossfade!
        player.tick(0.040, frame_rate_scale=0.25)
        done = player.snapshot()
        self.assertIsNone(done.previous)
        self.assertEqual(done.current_opacity, 1.0)


class CompatibleCrossfadeTests(unittest.TestCase):
    def test_compatible_pose_groups_use_70ms_crossfade(self) -> None:
        for group in COMPATIBLE_CROSSFADE_GROUPS:
            ordered = sorted(group)
            for first, second in zip(ordered, ordered[1:]):
                with self.subTest(pair=(first, second)):
                    player = AnimationPlayer()
                    player.play(_make_clip(PetAction.IDLE, first), crossfade=False)
                    player.play(_make_clip(PetAction.WORKING, second), crossfade=True)
                    start = player.snapshot()
                    self.assertIsNotNone(start.previous)
                    self.assertEqual(start.previous.asset_id, first)
                    self.assertEqual(start.current.asset_id, second)

                    player.tick(COMPATIBLE_POSE_CROSSFADE_SECONDS / 2.0)
                    mid = player.snapshot()
                    self.assertIsNotNone(mid.previous)
                    self.assertAlmostEqual(mid.current_opacity, 0.5, places=2)
                    self.assertAlmostEqual(mid.previous_opacity, 0.5, places=2)

                    player.tick(COMPATIBLE_POSE_CROSSFADE_SECONDS / 2.0 + 0.005)
                    end = player.snapshot()
                    self.assertIsNone(end.previous)
                    self.assertEqual(end.current_opacity, 1.0)

    def test_incompatible_or_mismatched_geometry_never_crossfades(self) -> None:
        incompatible_pairs = [
            ("idle_front", "happy"),
            ("idle_front", "walk_side"),
            ("perch_sit", "idle_front"),
            ("dock_peek", "dock_peek_right"),
            ("dock_work", "perch_work"),
            ("perch_sleep", "dock_sleep"),
        ]
        for first, second in incompatible_pairs:
            with self.subTest(pair=(first, second)):
                player = AnimationPlayer()
                player.play(_make_clip(PetAction.IDLE, first), crossfade=False)
                player.play(_make_clip(PetAction.HAPPY, second), crossfade=True)
                self.assertIsNone(player.snapshot().previous)

        # Mismatched mirrored flag blocks compatible crossfade.
        player = AnimationPlayer()
        player.play(_make_clip(PetAction.IDLE, "idle_front", mirrored=False), crossfade=False)
        player.play(_make_clip(PetAction.BLINK, "idle_blink", mirrored=True), crossfade=True)
        self.assertIsNone(player.snapshot().previous)

        # Mismatched anchor blocks compatible crossfade.
        player = AnimationPlayer()
        player.play(_make_clip(PetAction.IDLE, "idle_front", anchor=Anchor("ground", 0.5, 0.985)), crossfade=False)
        player.play(_make_clip(PetAction.BLINK, "idle_blink", anchor=Anchor("drag", 0.5, 0.5)), crossfade=True)
        self.assertIsNone(player.snapshot().previous)

        # Same-asset crossfade keeps its 90ms duration (still active at 75ms).
        player = AnimationPlayer()
        player.play(_make_clip(PetAction.IDLE, "shared.png"), crossfade=False)
        player.play(_make_clip(PetAction.HAPPY, "shared.png"), crossfade=True)
        player.tick(0.075)
        self.assertIsNotNone(player.snapshot().previous)
        player.tick(SAME_ASSET_CROSSFADE_SECONDS)
        self.assertIsNone(player.snapshot().previous)


class ManifestTimingAndPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))

    def test_all_ground_anchors_unified_to_0_985(self) -> None:
        actions = self.manifest["actions"]
        ground_actions = [
            name for name, raw in actions.items()
            if (raw.get("anchor") or {}).get("type") == "ground"
        ]
        self.assertGreaterEqual(len(ground_actions), 25)
        for name in ground_actions:
            self.assertAlmostEqual(
                actions[name]["anchor"]["y"],
                0.985,
                places=4,
                msg=f"{name} ground anchor.y must be 0.985",
            )

    def test_priority_hierarchy_prevents_perch_and_walking_swallowing_companion_actions(self) -> None:
        registry = AssetRegistry(ROOT / "neon", base_manifest=BASE_MANIFEST)
        specs = registry.specs
        expected = {
            PetAction.PERCH: 20,
            PetAction.WALKING: 28,
            PetAction.WORKING: 31,
            PetAction.TIRED: 32,
            PetAction.STRETCH: 32,
            PetAction.SULK: 33,
            PetAction.WAITING_USER: 34,
            PetAction.PERCH_SLEEP: 35,
            PetAction.DOCK_SLEEP: 35,
            PetAction.REFUSE_FOOD: 66,
            PetAction.PET_PURR: 72,
            PetAction.JUMP_UP: 92,
        }
        for action, prio in expected.items():
            self.assertEqual(specs[action].priority, prio, action)

        # Verify state machine behavior with real priorities.
        for starter in (PetAction.PERCH, PetAction.WALKING):
            for companion in (PetAction.WORKING, PetAction.TIRED, PetAction.STRETCH, PetAction.SULK, PetAction.WAITING_USER):
                machine = ActionStateMachine(specs)
                machine.request(starter, now=0.0, reason="start", force=True)
                self.assertIsNotNone(
                    machine.request(companion, now=1.0, reason="companion"),
                    f"{companion} must preempt {starter}",
                )
                # WALKING must not interrupt higher-priority companion actions.
                self.assertIsNone(
                    machine.request(PetAction.WALKING, now=1.1, reason="wander"),
                    f"WALKING must not swallow {companion}",
                )

    def test_integer_loop_durations_and_dock_pacing(self) -> None:
        # Exact integer-loop actions across all 5 forms (real current frame counts).
        checked_actions = (
            PetAction.TALKING,
            PetAction.TIRED,
            PetAction.STRETCH,
            PetAction.WAVE,
            PetAction.THINKING,
            PetAction.ANGRY,
            PetAction.SWEEPING,
            PetAction.DIZZY,
            PetAction.HAPPY,
        )
        for form in ALL_FORMS:
            registry = AssetRegistry(ROOT / form, base_manifest=BASE_MANIFEST)
            for action in checked_actions:
                spec = registry.specs[action]
                self.assertIsNotNone(spec.frame_ms, (form, action))
                self.assertIsNotNone(spec.duration_ms, (form, action))
                frame_count = registry.manifest["assets"][spec.asset_id]["frame_count"]
                cycle_ms = frame_count * spec.frame_ms
                self.assertEqual(
                    spec.duration_ms % cycle_ms,
                    0,
                    f"{form} {action}: duration_ms={spec.duration_ms} not integer multiple of {frame_count}*{spec.frame_ms}",
                )

        # Batch 2/3 target frame counts also align cleanly.
        actions = self.manifest["actions"]
        self.assertEqual(actions["EATING"]["frame_ms"], 240)
        self.assertEqual(actions["EATING"]["duration_ms"], 2400)  # 2 * 5f * 240ms
        self.assertEqual(actions["REFUSE_FOOD"]["frame_ms"], 210)
        self.assertEqual(actions["REFUSE_FOOD"]["duration_ms"], 1260)  # 2 * 3f * 210ms
        self.assertEqual(actions["DRAGGING"]["frame_ms"], 200)

        # Dock pacing & frame_pick contract (perch_sit=[0] preserved until Batch 2).
        frame_pick = self.manifest["frame_pick"]
        self.assertEqual(frame_pick["perch_sit"], [0])
        self.assertEqual(frame_pick["dock_peek"], [0, 0, 0, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(frame_pick["dock_peek_right"], [0, 0, 0, 0, 0, 0, 0, 0, 0, 1])

        registry = AssetRegistry(ROOT / "neon", base_manifest=BASE_MANIFEST)
        self.assertEqual(registry._frame_duration_ms(registry.specs[PetAction.IDLE], 10, "dock_peek"), 200)
        self.assertEqual(registry._frame_duration_ms(registry.specs[PetAction.IDLE], 10, "dock_peek_right"), 200)
        self.assertEqual(registry._frame_duration_ms(registry.specs[PetAction.WORKING], 7, "dock_work"), 220)
        self.assertEqual(registry._frame_duration_ms(registry.specs[PetAction.WORKING], 7, "dock_work_right"), 220)

    def test_dock_sleep_directional_resolution_and_v31_fallback_to_real_frames(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        self.assertEqual(DOCK_LEFT_ASSETS[PetAction.DOCK_SLEEP], "dock_sleep")
        self.assertEqual(DOCK_RIGHT_ASSETS[PetAction.DOCK_SLEEP], "dock_sleep_right")
        self.assertIn("dock_sleep", BESPOKE_DOCK_ASSETS)
        self.assertIn("dock_sleep_right", BESPOKE_DOCK_ASSETS)
        self.assertEqual(EDGE_ASSETS[PetAction.PERCH_SLEEP], "perch_sleep")

        registry = AssetRegistry(ROOT / "neon", base_manifest=BASE_MANIFEST)
        # Before Batch 3 art lands: DOCK_SLEEP falls back cleanly per dock edge.
        left_clip = registry.clip_for(PetAction.DOCK_SLEEP, height=238, direction="dock_left")
        right_clip = registry.clip_for(PetAction.DOCK_SLEEP, height=238, direction="dock_right")
        self.assertEqual(left_clip.asset_id, "dock_peek")
        self.assertEqual(right_clip.asset_id, "dock_peek_right")

        # When real frames are registered, all v3.1 assets resolve to themselves.
        sample_frames = registry.manifest["assets"]["idle_front"]["frames"]
        v31_cases = [
            (PetAction.PERCH, "edge", "perch_sit"),
            (PetAction.PERCH_SLEEP, "edge", "perch_sleep"),
            (PetAction.DOCK_SLEEP, "dock_left", "dock_sleep"),
            (PetAction.DOCK_SLEEP, "dock_right", "dock_sleep_right"),
            (PetAction.SULK, "down", "sulk"),
            (PetAction.WAITING_USER, "down", "waiting_user"),
            (PetAction.JUMP_UP, "down", "jump_up"),
            (PetAction.PET_PURR, "down", "pet_purr"),
            (PetAction.REFUSE_FOOD, "down", "refuse_food"),
        ]
        for _action, _direction, asset_name in v31_cases:
            if asset_name not in registry._assets:
                registry._assets[asset_name] = {"frames": sample_frames, "frame_count": 1}
        registry._frame_cache.clear()
        for action, direction, asset_name in v31_cases:
            clip = registry.clip_for(action, height=238, direction=direction)
            self.assertEqual(clip.asset_id, asset_name, (action, direction))
            self.assertTrue(clip.frames and not clip.frames[0].pixmap.isNull())


class ProceduralEffectsFluidityTests(unittest.TestCase):
    @staticmethod
    def _sample(effect: str, seconds: float = 2.5, step: float = 1 / 60):
        return [pose_for(effect, i * step) for i in range(int(seconds / step))]

    def test_celebrate_and_happy_do_not_double_hop(self) -> None:
        for effect, decoration in (("bounce", "sparkle"), ("celebrate", "confetti")):
            poses = self._sample(effect, 1.5)
            # No big out-of-phase procedural jump (previously -6px / -14px).
            self.assertGreater(min(p.offset_y for p in poses), -3.0, effect)
            # Still provides subtle squash/stretch/tilt accent and decoration.
            self.assertGreater(max(p.scale_y for p in poses), 1.015, effect)
            self.assertLess(min(p.scale_y for p in poses), 0.985, effect)
            self.assertGreater(max(abs(p.rotation_degrees) for p in poses), 1.5, effect)
            self.assertTrue(all(p.decoration == decoration for p in poses), effect)

    def test_downward_settle_effects_ramp_smoothly_and_feel_grounded(self) -> None:
        # Landing and head_pat must not snap to non-zero offset_y at t=0.
        self.assertAlmostEqual(pose_for("landing", 0.0).offset_y, 0.0, places=5)
        self.assertAlmostEqual(pose_for("head_pat", 0.0).offset_y, 0.0, places=5)
        self.assertAlmostEqual(pose_for("walk_stop", 0.0).offset_y, 0.0, places=5)

        for effect, min_down in (("landing", 2.5), ("head_pat", 1.5), ("tired", 3.0)):
            poses = self._sample(effect, 1.6)
            self.assertGreaterEqual(max(p.offset_y for p in poses), min_down, effect)
            self.assertLessEqual(max(p.offset_y for p in poses), 6.0, effect)

    def test_breath_amplitude_gently_boosted_and_respects_scaling(self) -> None:
        poses = self._sample("breath", 3.0)
        span = max(p.scale_y for p in poses) - min(p.scale_y for p in poses)
        self.assertGreaterEqual(span, 0.05)
        self.assertLessEqual(span, 0.09)
        zero = scaled(poses[15], 0.0)
        self.assertEqual((zero.offset_x, zero.offset_y, zero.scale_x, zero.scale_y, zero.rotation_degrees), (0.0, 0.0, 1.0, 1.0, 0.0))

    def test_v31_new_effects_have_distinct_safe_motion(self) -> None:
        # sulk: gentle pouty sway + huff
        sulk = self._sample("sulk", 4.0)
        self.assertGreater(max(p.offset_x for p in sulk), 0.8)
        self.assertLess(min(p.offset_x for p in sulk), -0.8)
        self.assertGreater(max(p.offset_y for p in sulk), 1.0)

        # jump_up: upward stretch, tilt, and airborne (no floor shadow)
        jump = self._sample("jump_up", 1.0)
        self.assertLess(min(p.offset_y for p in jump), -3.0)
        self.assertGreater(max(p.scale_y for p in jump), 1.05)
        self.assertLess(min(p.scale_x for p in jump), 0.96)
        self.assertTrue(all(p.shadow_opacity == 0.0 for p in jump))

        # pet_purr: cozy side-to-side nuzzle sway with grounded positive lean
        purr = self._sample("pet_purr", 3.0)
        self.assertGreater(max(p.offset_x for p in purr), 1.5)
        self.assertLess(min(p.offset_x for p in purr), -1.5)
        self.assertGreater(min(p.offset_y for p in purr), 0.5)
        self.assertGreater(max(abs(p.rotation_degrees) for p in purr), 2.5)

        # refuse_food: brisk head-shake oscillation that decays cleanly
        refuse = self._sample("refuse_food", 1.5)
        self.assertGreater(max(p.offset_x for p in refuse[:30]), 2.5)
        self.assertLess(min(p.offset_x for p in refuse[:30]), -2.5)
        self.assertLess(max(abs(p.offset_x) for p in refuse[-15:]), 0.6)

        for name in ("sulk", "jump_up", "pet_purr", "refuse_food"):
            for pose in self._sample(name, 3.0):
                self.assertLessEqual(abs(pose.offset_x), 8.0, name)
                self.assertGreaterEqual(pose.offset_y, -24.0, name)
                self.assertLessEqual(pose.offset_y, 6.0, name)
                self.assertTrue(0.85 <= pose.scale_x <= 1.15 and 0.85 <= pose.scale_y <= 1.15, name)
                self.assertLessEqual(abs(pose.rotation_degrees), 13.0, name)
                self.assertTrue(all(math.isfinite(v) for v in (pose.offset_x, pose.offset_y, pose.scale_x, pose.scale_y)))


if __name__ == "__main__":
    unittest.main()
