"""Light whole-body motion layered on top of authored sprite frames.

The frames carry gestures, expressions and hair; this layer only adds
continuous whole-body motion (breathing, bobs and squash-and-stretch, sway)
so the pet keeps moving between frames, as the upstream pet does.

Scaling happens around the sprite anchor (the feet for grounded clips), so a
squash never lifts the pet off the floor.  "Reduced motion" bypasses all of it
in the renderer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EffectPose:
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_degrees: float = 0.0
    shadow_scale: float = 1.0
    shadow_opacity: float = 0.22
    decoration: str | None = None


@dataclass(frozen=True, slots=True)
class _Hop:
    y: float
    scale_x: float
    scale_y: float
    shadow_scale: float


def _hop(u: float, height: float, squash: float = 1.0) -> _Hop:
    """One hop over normalised time ``u`` in [0, 1): crouch, air, land."""

    u = u % 1.0
    if u < 0.2:  # anticipation crouch
        k = math.sin(u / 0.2 * math.pi)
        return _Hop(0.0, 1.0 + 0.05 * k * squash, 1.0 - 0.07 * k * squash, 1.0 + 0.06 * k)
    if u < 0.8:  # airborne parabola, stretched while fast
        a = (u - 0.2) / 0.6
        lift = 4.0 * a * (1.0 - a)
        speed = abs(1.0 - 2.0 * a)
        return _Hop(
            -height * lift,
            1.0 - 0.04 * speed * squash,
            1.0 + 0.06 * speed * squash,
            1.0 - 0.35 * lift,
        )
    k = math.sin((u - 0.8) / 0.2 * math.pi)  # landing squash
    return _Hop(0.0, 1.0 + 0.07 * k * squash, 1.0 - 0.09 * k * squash, 1.0 + 0.08 * k)


def _settle(time: float, decay: float, frequency: float) -> float:
    return math.exp(-time * decay) * math.cos(time * frequency)


def pose_for(effect: str, elapsed_seconds: float) -> EffectPose:
    time = max(0.0, elapsed_seconds)
    breath = math.sin(time * 2.35)
    if effect == "breath":
        # Idle: visible breathing plus a slow weight shift from foot to foot.
        shift = math.sin(time * 0.47)
        return EffectPose(
            offset_x=shift * 0.8,
            rotation_degrees=math.sin(time * 0.47 + 0.7) * 0.6,
            scale_x=1.0 - breath * 0.009,
            scale_y=1.0 + breath * 0.019,
        )
    if effect == "micro_idle":
        return EffectPose(
            offset_y=breath * 0.5,
            rotation_degrees=math.sin(time * 3.1) * 1.4,
            scale_x=1.0 - breath * 0.006,
            scale_y=1.0 + breath * 0.012,
            shadow_opacity=0.20,
        )
    if effect == "think":
        tilt = math.sin(time * 1.6)
        return EffectPose(
            offset_x=tilt * 1.2,
            offset_y=-2.0 + breath * 1.4,
            rotation_degrees=tilt * 3.6,
            scale_y=1.0 + breath * 0.014,
            decoration="thought",
        )
    if effect == "walk_placeholder":
        phase = math.sin(time * 12.0)
        return EffectPose(
            offset_y=-abs(phase) * 3.5,
            rotation_degrees=phase * 0.7,
            scale_x=1.0 + phase * 0.006,
            scale_y=1.0 - abs(phase) * 0.012,
            shadow_scale=1.0 - abs(phase) * 0.14,
            shadow_opacity=0.18,
        )
    if effect == "walk_frames":
        # Two steps per four-frame cycle: rise mid-stride, squash on contact,
        # and a gentle side-to-side sway of the hips.
        stride = abs(math.sin(time * math.pi * 2.78))
        contact = 1.0 - stride
        return EffectPose(
            offset_y=-stride * 3.0,
            rotation_degrees=math.sin(time * math.pi * 2.78) * 1.6,
            scale_x=1.0 + contact * 0.014,
            scale_y=1.0 - contact * 0.022,
            shadow_scale=1.0 - stride * 0.10,
            shadow_opacity=0.20,
        )
    if effect == "walk_start":
        progress = min(1.0, time / 0.26)
        crouch = math.sin(min(1.0, progress / 0.6) * math.pi) if progress < 0.6 else 0.0
        push = math.sin(max(0.0, progress - 0.6) / 0.4 * math.pi) if progress >= 0.6 else 0.0
        return EffectPose(
            offset_y=-push * 3.0,
            scale_x=1.0 + crouch * 0.04 - push * 0.02,
            scale_y=1.0 - crouch * 0.06 + push * 0.04,
            shadow_scale=1.0 + crouch * 0.06,
            shadow_opacity=0.20,
        )
    if effect == "walk_stop":
        settle = _settle(time, 9.0, 22.0)
        return EffectPose(
            offset_y=abs(settle) * 1.2,
            rotation_degrees=settle * 2.0,
            scale_x=1.0 + settle * 0.03,
            scale_y=1.0 - settle * 0.045,
            shadow_scale=1.0 + settle * 0.05,
            shadow_opacity=0.20,
        )
    if effect == "bounce":
        # HAPPY: two springy hops in ~1 s.
        # The frames include a jump, so this is only a light springy bob.
        hop = _hop(time / 0.52, 6.0)
        return EffectPose(
            offset_y=hop.y,
            rotation_degrees=math.sin(time * 6.0) * 1.2,
            scale_x=hop.scale_x,
            scale_y=hop.scale_y,
            shadow_scale=hop.shadow_scale,
            decoration="sparkle",
        )
    if effect == "head_pat":
        # Squish under the hand, then a happy wobble.
        press = math.exp(-time * 3.2) * (0.5 + 0.5 * math.cos(time * 8.0))
        return EffectPose(
            offset_y=press * 1.5,
            rotation_degrees=math.sin(time * 5.0) * 2.4 * math.exp(-time * 1.2),
            scale_x=1.0 + press * 0.05,
            scale_y=1.0 - press * 0.07,
            shadow_scale=1.0 + press * 0.05,
            shadow_opacity=0.20,
        )
    if effect == "talk":
        phase = math.sin(time * 7.6)
        nod = math.sin(time * 1.9)
        return EffectPose(
            offset_y=-abs(phase) * 2.6,
            rotation_degrees=phase * 0.8 + nod * 1.0,
            scale_x=1.0 - abs(phase) * 0.008,
            scale_y=1.0 + abs(phase) * 0.016,
            decoration="voice",
        )
    if effect == "angry":
        # Stomping in place with a shake.
        hop = _hop(time / 0.36, 5.0, squash=1.4)
        shake = math.sin(time * 26.0)
        return EffectPose(
            offset_x=shake * 1.6,
            offset_y=hop.y,
            rotation_degrees=shake * 1.0,
            scale_x=hop.scale_x,
            scale_y=hop.scale_y,
            shadow_scale=hop.shadow_scale,
            decoration="anger",
        )
    if effect == "recoil":
        impulse = math.exp(-time * 8.0)
        return EffectPose(offset_x=-impulse * 10.0, scale_x=1.0 - impulse * 0.035, rotation_degrees=-impulse * 3.0)
    if effect == "poke_frames":
        impulse = math.exp(-time * 6.5)
        wobble = _settle(time, 6.0, 18.0)
        return EffectPose(
            offset_x=-impulse * 6.0,
            rotation_degrees=-impulse * 4.0 + wobble * 1.5,
            scale_x=1.0 - impulse * 0.03,
            scale_y=1.0 + impulse * 0.03,
            shadow_opacity=0.20,
        )
    if effect == "tail_react":
        # A startled little jump, then a wobble.
        hop = _hop(min(0.999, time / 0.45), 9.0, squash=1.2) if time < 0.45 else _Hop(0.0, 1.0, 1.0, 1.0)
        wobble = _settle(max(0.0, time - 0.45), 5.0, 14.0) if time >= 0.45 else 0.0
        return EffectPose(
            offset_x=wobble * 1.5,
            offset_y=hop.y,
            rotation_degrees=wobble * 2.5,
            scale_x=hop.scale_x,
            scale_y=hop.scale_y,
            shadow_scale=hop.shadow_scale,
            shadow_opacity=0.20,
        )
    if effect == "eat":
        chew = max(0.0, math.sin(time * 11.0))
        return EffectPose(
            offset_y=-chew * 3.0,
            rotation_degrees=math.sin(time * 3.0) * 1.5,
            scale_x=1.0 + chew * 0.02,
            scale_y=1.0 - chew * 0.025,
            decoration="crumb",
        )
    if effect == "sweep":
        phase = math.sin(time * 4.2)
        return EffectPose(
            offset_x=phase * 2.5,
            offset_y=-abs(math.cos(time * 4.2)) * 1.2,
            rotation_degrees=phase * 2.0,
            decoration="sweep",
        )
    if effect == "sleep":
        slow = math.sin(time * 1.5)
        return EffectPose(
            offset_y=slow * 1.8,
            rotation_degrees=math.sin(time * 0.6) * 1.2,
            scale_x=1.0 - slow * 0.012,
            scale_y=1.0 + slow * 0.022,
            decoration="sleep",
        )
    if effect == "sleep_enter":
        progress = min(1.0, time / 1.05)
        sag = math.sin(progress * math.pi * 0.5)
        return EffectPose(offset_y=sag * 1.5, rotation_degrees=sag * 2.0, scale_y=1.0 - sag * 0.02, shadow_scale=1.0 + progress * 0.04)
    if effect == "sleep_wake":
        progress = min(1.0, time / 0.90)
        stretch = math.sin(progress * math.pi)
        return EffectPose(offset_y=-stretch * 2.0, scale_x=1.0 - stretch * 0.02, scale_y=1.0 + stretch * 0.04, shadow_opacity=0.20)
    if effect == "float":
        # Dangling while dragged: a pendulum swing with a slight stretch.
        swing = math.sin(time * 3.4)
        return EffectPose(
            offset_y=math.sin(time * 6.8) * 1.6,
            rotation_degrees=swing * 6.0,
            scale_x=0.985,
            scale_y=1.03,
            shadow_opacity=0.0,
        )
    if effect == "fall":
        progress = min(1.0, time / 0.42)
        flail = math.sin(time * 15.0)
        return EffectPose(
            rotation_degrees=progress * 10.0 + flail * 3.0,
            scale_x=1.0 - progress * 0.03,
            scale_y=1.0 + progress * 0.05,
            shadow_opacity=0.0,
        )
    if effect == "landing":
        settle = _settle(time, 7.0, 19.0)
        compression = max(0.0, settle)
        return EffectPose(
            offset_y=compression * 2.5,
            rotation_degrees=settle * 1.5,
            scale_x=1.0 + compression * 0.09 - max(0.0, -settle) * 0.03,
            scale_y=1.0 - compression * 0.12 + max(0.0, -settle) * 0.05,
            shadow_scale=1.0 + compression * 0.2,
            shadow_opacity=0.25,
        )
    if effect == "dizzy":
        angle = time * 7.0
        return EffectPose(
            offset_x=math.cos(angle) * 3.0,
            offset_y=math.sin(angle) * 1.2,
            rotation_degrees=math.sin(angle) * 5.0,
            decoration="dizzy",
        )
    # ----- Antigravity companion actions ------------------------------------
    if effect == "work":
        tap = abs(math.sin(time * 15.0))
        lean = math.sin(time * 0.8)
        return EffectPose(
            offset_x=lean * 1.0,
            offset_y=-tap * 1.6 + breath * 0.5,
            rotation_degrees=lean * 1.5,
            scale_y=1.0 - tap * 0.008,
            decoration="code",
        )
    if effect == "celebrate":
        # Three big hops with stretch, twisting a little in the air.
        hop = _hop(time / 0.6, 14.0, squash=1.2)
        return EffectPose(
            offset_y=hop.y,
            scale_x=hop.scale_x,
            scale_y=hop.scale_y,
            rotation_degrees=math.sin(time * 10.5) * 3.5,
            shadow_scale=hop.shadow_scale,
            decoration="confetti",
        )
    if effect == "tired":
        droop = min(1.0, time / 1.2)
        return EffectPose(
            offset_y=droop * 3.0 + breath * 1.0,
            scale_x=1.0 + droop * 0.012,
            scale_y=1.0 - droop * 0.035,
            rotation_degrees=math.sin(time * 0.9) * 2.6,
            decoration="yawn",
        )
    if effect == "stretch":
        reach = math.sin(min(1.0, time / 2.2) * math.pi)
        return EffectPose(
            scale_x=1.0 - reach * 0.045,
            scale_y=1.0 + reach * 0.09,
            offset_y=-reach * 3.5,
            rotation_degrees=math.sin(time * 2.0) * reach * 2.5,
            decoration="sparkle",
        )
    if effect == "transform":
        spin = min(1.0, time / 0.9)
        squash = math.sin(spin * math.pi)
        return EffectPose(
            scale_x=1.0 - squash * 0.35,
            scale_y=1.0 + squash * 0.05,
            offset_y=-squash * 8.0,
            shadow_scale=1.0 - squash * 0.4,
            decoration="glow",
        )
    if effect == "wave":
        phase = math.sin(time * 9.0)
        return EffectPose(
            offset_x=math.sin(time * 4.5) * 1.5,
            rotation_degrees=phase * 3.2,
            offset_y=-abs(phase) * 2.2,
            decoration="wave",
        )
    if effect == "perch":
        swing = math.sin(time * 2.4)
        return EffectPose(offset_y=breath * 0.7, rotation_degrees=swing * 1.6, shadow_opacity=0.12)
    return EffectPose()


def scaled(pose: EffectPose, amount: float) -> EffectPose:
    """Shrink (or grow) every motion delta by ``amount``; 1.0 leaves it as is."""

    if amount == 1.0:
        return pose
    k = max(0.0, amount)
    return EffectPose(
        offset_x=pose.offset_x * k,
        offset_y=pose.offset_y * k,
        scale_x=1.0 + (pose.scale_x - 1.0) * k,
        scale_y=1.0 + (pose.scale_y - 1.0) * k,
        rotation_degrees=pose.rotation_degrees * k,
        shadow_scale=1.0 + (pose.shadow_scale - 1.0) * k,
        shadow_opacity=pose.shadow_opacity,
        decoration=pose.decoration,
    )
