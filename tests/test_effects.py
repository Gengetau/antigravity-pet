import math

from animation.effects import pose_for

EFFECTS = [
    "breath", "micro_idle", "think", "walk_frames", "walk_start", "walk_stop", "bounce", "head_pat",
    "talk", "angry", "poke_frames", "tail_react", "eat", "sweep", "sleep", "sleep_enter", "sleep_wake",
    "float", "fall", "landing", "dizzy", "work", "celebrate", "tired", "stretch", "wave", "perch",
    "sulk", "jump_up", "pet_purr", "refuse_food",
]


def _samples(effect, seconds=3.0, step=1 / 60):
    return [pose_for(effect, i * step) for i in range(int(seconds / step))]


def test_all_effects_stay_within_safe_bounds():
    for effect in EFFECTS:
        for pose in _samples(effect):
            assert abs(pose.offset_x) <= 8, effect
            assert -24 <= pose.offset_y <= 6, effect
            assert 0.85 <= pose.scale_x <= 1.15 and 0.85 <= pose.scale_y <= 1.15, effect
            assert abs(pose.rotation_degrees) <= 13, effect
            assert all(math.isfinite(v) for v in (pose.offset_x, pose.offset_y, pose.scale_x, pose.scale_y))


def test_hops_lift_off_and_squash_on_the_ground():
    # Drawn frames already carry the jump for bounce/celebrate, so procedural
    # motion stays subtle without an out-of-phase hop.
    for effect in ("bounce", "celebrate"):
        poses = _samples(effect, 1.2)
        assert min(p.offset_y for p in poses) > -3.5, effect
        assert max(p.scale_y for p in poses) > 1.01 and min(p.scale_y for p in poses) < 0.99, effect
        assert max(abs(p.rotation_degrees) for p in poses) > 1.0, effect
    # Ground-settle effects ease smoothly into a positive downward squash.
    for effect in ("landing", "head_pat", "tired"):
        poses = _samples(effect, 1.2)
        assert max(p.offset_y for p in poses) >= 1.5, effect
        assert min(p.scale_y for p in poses) < 0.97, effect


def test_idle_keeps_moving_between_frames():
    poses = _samples("breath", 3.0)
    assert max(p.scale_y for p in poses) - min(p.scale_y for p in poses) >= 0.03
    assert max(abs(p.offset_x) for p in poses) >= 0.5


def test_scaled_shrinks_every_delta():
    from animation.effects import scaled

    pose = pose_for("celebrate", 0.3)
    half = scaled(pose, 0.5)
    assert half.offset_y == pose.offset_y * 0.5
    assert abs((half.scale_y - 1.0) - (pose.scale_y - 1.0) * 0.5) < 1e-9
    assert half.rotation_degrees == pose.rotation_degrees * 0.5
    assert scaled(pose, 1.0) is pose
