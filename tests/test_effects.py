import math

from animation.effects import pose_for

EFFECTS = [
    "breath", "micro_idle", "think", "walk_frames", "walk_start", "walk_stop", "bounce", "head_pat",
    "talk", "angry", "poke_frames", "tail_react", "eat", "sweep", "sleep", "sleep_enter", "sleep_wake",
    "float", "fall", "landing", "dizzy", "work", "celebrate", "tired", "stretch", "wave", "perch",
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
    for effect, min_height in (("bounce", 5), ("celebrate", 12)):
        poses = _samples(effect, 1.2)
        assert min(p.offset_y for p in poses) <= -min_height, effect
        grounded = [p for p in poses if p.offset_y == 0.0]
        assert any(p.scale_y < 0.95 and p.scale_x > 1.03 for p in grounded), effect


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
