"""Live2D-style single-image soft mesh deformation, 2.5D cursor gaze, and springs.

Pure-Python + Pillow C ``Image.Transform.MESH`` implementation:
- Runs at ~1.1-1.5ms/frame on runtime sprites (187-306px) with zero OpenGL
  translucent-window black-box issues and 100% headless offscreen test support.
- Applies an alpha-preserving unsharp mask once on frame cache load so shrunken
  line art stays print-sharp.
- Drives soft anatomical weights (face 2.5D parallax, opposite back-hair shift,
  head tilt & nod, left/right ear flicks & quota droop, ahoge spring, dual-wave
  flowing hair + velocity follow-through springs, chest breathing, skirt lag,
  and tail swish) while keeping soles grounded and edge-dock seams locked flush.
"""

from __future__ import annotations

import math
import random
from collections import OrderedDict
from dataclasses import dataclass

from PIL import Image, ImageFilter
from PySide6.QtGui import QImage, QPixmap

# Poses where vertical standing regions do not apply cleanly.
_LYING_ASSETS = frozenset({"sleep", "sleep_enter", "sleep_wake"})
_DOCK_LEFT_SEAM_ASSETS = frozenset({"dock_peek", "dock_work", "dock_sleep"})
_DOCK_RIGHT_SEAM_ASSETS = frozenset({"dock_peek_right", "dock_work_right", "dock_sleep_right"})
_HANGING_ASSETS = frozenset({"perch_sit", "perch_work", "perch_sleep", "climb_side", "climb_side_right"})
_HUMAN_FORMS = frozenset({"claude"})


def _clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else (hi if value > hi else value)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 1.0 if x >= edge1 else 0.0
    t = _clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _gauss(x: float, y: float, cx: float, cy: float, sx: float, sy: float) -> float:
    dx = (x - cx) / max(1e-4, sx)
    dy = (y - cy) / max(1e-4, sy)
    return math.exp(-0.5 * (dx * dx + dy * dy))


@dataclass(slots=True)
class RigParams:
    """Instantaneous anatomical deformation parameters for one frame."""

    time: float = 0.0
    look_x: float = 0.0        # -1..+1 horizontal gaze (screen-right positive)
    look_y: float = 0.0        # -1..+1 vertical gaze (screen-down positive)
    head_rot: float = 0.0      # radians, positive tilts clockwise
    nod_y: float = 0.0         # normalized pixels (scaled by sprite height)
    ear_l: float = 0.0         # radians around left ear root
    ear_r: float = 0.0         # radians around right ear root
    ahoge: float = 0.0         # radians around crown ahoge root
    hair_sway_l: float = 0.0   # pixels (at 238px reference height)
    hair_sway_r: float = 0.0   # pixels
    hair_wave: float = 1.8     # flowing sine amplitude in pixels
    hair_lift: float = 0.0     # upward lift during hops/drags (0..1.2)
    skirt_sway: float = 0.0    # pixels
    tail_sway: float = 0.0     # pixels
    breath: float = 0.0        # 0..1 smooth chest breath phase
    squash: float = 0.0        # -0.10..+0.10 elastic gesture squash/stretch
    quota_sag: float = 0.0     # 0..1 low-quota energy droop


@dataclass(slots=True)
class _ActiveGesture:
    name: str
    elapsed: float
    duration: float


class SoftRigController:
    """Updates 2.5D gaze, 5 harmonic springs, quota droop, and organic micro-fidgets."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self.params = RigParams()
        self.enabled = True
        self.follow_cursor = True
        self._time = self._rng.uniform(0.0, 50.0)
        # Damped harmonic springs: [position, velocity]
        self._sp_hair_l = [0.0, 0.0]
        self._sp_hair_r = [0.0, 0.0]
        self._sp_ahoge = [0.0, 0.0]
        self._sp_skirt = [0.0, 0.0]
        self._sp_tail = [0.0, 0.0]
        self._look_x = 0.0
        self._look_y = 0.0
        self._head_rot = 0.0
        self._quota_sag = 0.0
        self._tail_phase = 0.0
        self._gestures: list[_ActiveGesture] = []
        self._next_fidget = self._rng.uniform(5.5, 11.5)

    @staticmethod
    def _step_spring(state: list[float], goal: float, k: float, damping: float, dt: float) -> float:
        # Substep keeps stiff springs unconditionally stable even on brief timer hiccups.
        steps = 2 if dt > 0.03 else 1
        h = dt / steps
        pos, vel = state[0], state[1]
        for _ in range(steps):
            acc = (goal - pos) * k - vel * damping
            vel += acc * h
            pos += vel * h
        state[0] = pos
        state[1] = vel
        return pos

    def trigger(self, name: str) -> None:
        """Fire a short organic gesture overlaid on the continuous soft rig."""
        durations = {
            "pop": 0.28,
            "squish": 0.44,
            "ear_flick_l": 0.34,
            "ear_flick_r": 0.34,
            "tail_swish": 1.05,
            "look_around": 2.35,
            "gasp": 0.46,
            "nod": 0.42,
        }
        duration = durations.get(name)
        if duration is None:
            return
        self._gestures = [g for g in self._gestures if g.name != name]
        self._gestures.append(_ActiveGesture(name=name, elapsed=0.0, duration=duration))
        # Physical impulses ring the ahoge and tail gently on non-subtle gestures.
        if name in {"squish", "gasp"}:
            self._sp_ahoge[1] += self._rng.uniform(-1.5, 1.5)
            self._sp_tail[1] += self._rng.uniform(-4.0, 4.0)

    def _fire_fidget(self, *, action_name: str, docked: bool) -> None:
        self._next_fidget = self._rng.uniform(7.5, 16.0)
        if docked or action_name in {"SLEEPING", "PERCH_SLEEP", "DOCK_SLEEP", "SULK", "DRAGGING", "FALLING", "DIZZY"}:
            return
        if action_name == "IDLE":
            pool = ("ear_flick_l", "ear_flick_r", "tail_swish", "look_around", "ear_flick_r")
        else:
            pool = ("ear_flick_l", "ear_flick_r", "tail_swish")
        self.trigger(self._rng.choice(pool))

    def step(
        self,
        dt: float,
        *,
        vx: float = 0.0,
        vy: float = 0.0,
        cursor_dx: float = 0.0,
        cursor_dy: float = 0.0,
        cursor_active: bool = True,
        action_name: str = "IDLE",
        quota_pct: float | None = None,
        is_working: bool = False,
        docked: bool = False,
        reduced_motion: bool = False,
    ) -> RigParams:
        if reduced_motion or not self.enabled:
            self.params = RigParams(time=self._time)
            return self.params

        step_dt = _clamp(float(dt), 0.001, 0.06)
        self._time += step_dt

        # 1. Quota energy droop (low <= 25%, critical <= 10%)
        target_sag = 0.0
        if quota_pct is not None and not docked:
            pct = float(quota_pct)
            if pct <= 10.0:
                target_sag = 1.0
            elif pct <= 25.0:
                target_sag = 0.5
        sag_rate = 1.0 - math.exp(-step_dt * 3.5)
        self._quota_sag += (target_sag - self._quota_sag) * sag_rate

        # 2. 2.5D cursor gaze (or gentle downward reading gaze while working)
        gaze_blocked = action_name in {"SLEEPING", "PERCH_SLEEP", "DOCK_SLEEP", "SULK", "DIZZY"}
        goal_lx = 0.0
        goal_ly = 0.0
        if self.follow_cursor and cursor_active and not gaze_blocked:
            weight = 1.0 if action_name in {"IDLE", "PERCH", "WAITING_USER"} else 0.45
            goal_lx = _clamp(cursor_dx / 380.0, -1.0, 1.0) * weight
            goal_ly = _clamp(cursor_dy / 300.0, -1.0, 1.0) * weight
        elif is_working and not gaze_blocked:
            goal_lx = math.sin(self._time * 1.1) * 0.18
            goal_ly = 0.35

        # 3. Organic micro-fidgets & active gestures
        self._next_fidget -= step_dt
        if self._next_fidget <= 0.0:
            self._fire_fidget(action_name=action_name, docked=docked)

        add_ear_l = 0.0
        add_ear_r = 0.0
        add_ahoge = 0.0
        add_head = 0.0
        add_nod = 0.0
        add_look_x = 0.0
        add_look_y = 0.0
        add_tail_amp = 0.0
        add_squash = 0.0

        remaining: list[_ActiveGesture] = []
        for g in self._gestures:
            g.elapsed += step_dt
            p = g.elapsed / max(0.01, g.duration)
            if p >= 1.0:
                continue
            hump = math.sin(math.pi * p)
            if g.name == "ear_flick_l":
                add_ear_l -= 0.28 * hump
            elif g.name == "ear_flick_r":
                add_ear_r += 0.28 * hump
            elif g.name == "tail_swish":
                add_tail_amp += 4.5 * hump
            elif g.name == "look_around":
                env = min(1.0, min(p, 1.0 - p) * 5.0)
                wave = math.sin(p * math.pi * 3.0)
                add_look_x += wave * 0.85 * env
                add_look_y -= 0.15 * env
                add_head += wave * 0.045 * env
            elif g.name == "pop":
                add_squash += 0.032 * math.sin(p * math.pi * 2.0) * (1.0 - p)
            elif g.name == "squish":
                add_squash -= 0.075 * hump
            elif g.name == "gasp":
                add_squash += 0.055 * hump
                add_ahoge -= 0.22 * hump
            elif g.name == "nod":
                add_nod += 3.2 * math.sin(p * math.pi * 2.0) * (1.0 - p * 0.35)
            remaining.append(g)
        self._gestures = remaining

        gaze_rate = 1.0 - math.exp(-step_dt * 8.5)
        self._look_x += (_clamp(goal_lx + add_look_x, -1.0, 1.0) - self._look_x) * gaze_rate
        self._look_y += (_clamp(goal_ly + add_look_y, -1.0, 1.0) - self._look_y) * gaze_rate
        goal_head = self._look_x * 0.055 + add_head
        if action_name in {"THINKING", "WAITING_USER"}:
            goal_head += math.sin(self._time * 1.25) * 0.025
        self._head_rot += (goal_head - self._head_rot) * gaze_rate

        # 4. Five damped harmonic follow-through springs driven by velocity (vx, vy)
        cvx = _clamp(float(vx), -1800.0, 1800.0)
        cvy = _clamp(float(vy), -1800.0, 1800.0)
        hair_l = self._step_spring(self._sp_hair_l, -cvx * 0.011, 62.0, 7.4, step_dt)
        hair_r = self._step_spring(self._sp_hair_r, -cvx * 0.013, 54.0, 6.6, step_dt)
        ahoge_sp = self._step_spring(self._sp_ahoge, -cvx * 0.00028 + cvy * 0.00018, 115.0, 8.2, step_dt)
        skirt_sp = self._step_spring(self._sp_skirt, -cvx * 0.0085, 78.0, 7.2, step_dt)
        tail_sp = self._step_spring(self._sp_tail, -cvx * 0.012 + cvy * 0.005, 34.0, 7.0, step_dt)

        # 5. Continuous wave rhythms (breathing, hair flow, accumulated tail phase)
        tail_freq = 0.55 if action_name == "IDLE" else (1.15 if action_name in {"HAPPY", "CELEBRATE", "PLAY_DANCE", "HIGH_FIVE", "PET_PURR"} else 0.75)
        tail_freq *= 1.0 - 0.35 * self._quota_sag
        self._tail_phase = (self._tail_phase + step_dt * tail_freq * math.tau) % math.tau
        tail_amp = (2.4 + add_tail_amp) * (1.0 - 0.5 * self._quota_sag)
        tail_sway = math.sin(self._tail_phase) * tail_amp + _clamp(tail_sp, -9.0, 9.0)

        hair_wave = (1.9 if action_name != "DRAGGING" else 3.2) * (1.0 - 0.35 * self._quota_sag)
        if docked:
            hair_wave *= 0.55
        hair_lift = 0.0
        if action_name in {"DRAGGING", "FALLING", "JUMP_UP", "RELEASED_AIRBORNE"}:
            hair_lift = 0.65
        elif cvy > 120.0:
            hair_lift = _clamp(cvy / 900.0, 0.0, 0.75)

        breath = 0.5 + 0.5 * math.sin(self._time * (1.5 if action_name in {"SLEEPING", "PERCH_SLEEP", "DOCK_SLEEP"} else 2.2))
        nod_work = math.sin(self._time * 6.5) * 0.9 if is_working and not docked else 0.0

        self.params = RigParams(
            time=self._time,
            look_x=self._look_x,
            look_y=self._look_y,
            head_rot=_clamp(self._head_rot + cvx * 0.000018, -0.18, 0.18),
            nod_y=add_nod + nod_work,
            ear_l=add_ear_l + 0.16 * self._quota_sag,
            ear_r=add_ear_r - 0.16 * self._quota_sag,
            ahoge=_clamp(ahoge_sp + add_ahoge + 0.28 * self._quota_sag + math.sin(self._time * 2.3) * 0.025, -0.45, 0.48),
            hair_sway_l=_clamp(hair_l, -11.0, 11.0),
            hair_sway_r=_clamp(hair_r, -11.0, 11.0),
            hair_wave=hair_wave,
            hair_lift=hair_lift,
            skirt_sway=_clamp(skirt_sp + math.sin(self._time * 1.15) * 0.9, -9.0, 9.0),
            tail_sway=tail_sway,
            breath=breath,
            squash=_clamp(add_squash, -0.10, 0.10),
            quota_sag=self._quota_sag,
        )
        return self.params


@dataclass(slots=True)
class _GridWeights:
    width: int
    height: int
    pad_x: int
    pad_top: int
    pad_bottom: int
    cols: int
    rows: int
    xs: tuple[float, ...]
    ys: tuple[float, ...]
    # Flat (rows+1)*(cols+1) vertex arrays in source image pixel coordinates
    src_x: tuple[float, ...]
    src_y: tuple[float, ...]
    w_head: tuple[float, ...]
    w_face: tuple[float, ...]
    w_back: tuple[float, ...]
    w_ear_l: tuple[float, ...]
    w_ear_r: tuple[float, ...]
    w_ahoge: tuple[float, ...]
    w_hair_l: tuple[float, ...]
    w_hair_r: tuple[float, ...]
    w_chest: tuple[float, ...]
    w_skirt: tuple[float, ...]
    w_tail: tuple[float, ...]
    w_edge_lock: tuple[float, ...]
    neck_x: float
    neck_y: float
    ear_l_px: float
    ear_l_py: float
    ear_r_px: float
    ear_r_py: float
    ahoge_px: float
    ahoge_py: float


def _build_grid_weights(width: int, height: int, *, mode: str) -> _GridWeights:
    cols, rows = 10, 14
    pad_x = 0 if mode in {"dock_left", "dock_right"} else 12
    pad_top = 10
    pad_bottom = 4
    out_w = width + pad_x * 2
    out_h = height + pad_top + pad_bottom
    xs = tuple(out_w * c / cols for c in range(cols + 1))
    ys = tuple(out_h * r / rows for r in range(rows + 1))

    mx = width * 0.50
    my = height * 0.275
    gap = max(24.0, width * 0.25)
    neck_x, neck_y = mx, height * 0.415
    crown_x, crown_y = mx, height * 0.175
    ear_l_px, ear_l_py = width * 0.37, height * 0.18
    ear_r_px, ear_r_py = width * 0.63, height * 0.18
    ahoge_px, ahoge_py = mx, height * 0.135

    src_x: list[float] = []
    src_y: list[float] = []
    w_head: list[float] = []
    w_face: list[float] = []
    w_back: list[float] = []
    w_ear_l: list[float] = []
    w_ear_r: list[float] = []
    w_ahoge: list[float] = []
    w_hair_l: list[float] = []
    w_hair_r: list[float] = []
    w_chest: list[float] = []
    w_skirt: list[float] = []
    w_tail: list[float] = []
    w_edge_lock: list[float] = []

    for r in range(rows + 1):
        oy = ys[r]
        sy = oy - pad_top
        ny = sy / max(1.0, float(height))
        for c in range(cols + 1):
            ox = xs[c]
            sx = ox - pad_x
            nx = sx / max(1.0, float(width))
            src_x.append(sx)
            src_y.append(sy)

            # Lock wall-facing seam pixels on edge-docked poses so she stays glued to border.
            if mode == "dock_left":
                edge_lock = _smoothstep(0.03, 0.24, nx)
            elif mode == "dock_right":
                edge_lock = _smoothstep(0.97, 0.76, nx)
            else:
                edge_lock = 1.0
            w_edge_lock.append(edge_lock)

            if mode == "lying":
                # Horizontal sleeping poses only breathe gently in the center torso.
                w_head.append(0.0)
                w_face.append(0.0)
                w_back.append(0.0)
                w_ear_l.append(0.0)
                w_ear_r.append(0.0)
                w_ahoge.append(0.0)
                w_hair_l.append(0.0)
                w_hair_r.append(0.0)
                w_chest.append(_gauss(sx, sy, width * 0.50, height * 0.52, width * 0.26, height * 0.20))
                w_skirt.append(0.0)
                w_tail.append(0.0)
                continue

            # Standing / seated / docked vertical chibi weights
            head = 1.0 - _smoothstep(neck_y - height * 0.04, neck_y + height * 0.05 + 0.16 * abs(sx - neck_x), sy)
            face = _gauss(sx, sy, mx, my + gap * 0.08, gap * 0.92, gap * 0.65)
            dist_crown = math.hypot(sx - crown_x, sy - crown_y)
            back = _smoothstep(gap * 1.05, gap * 1.75, dist_crown) * _smoothstep(neck_y + height * 0.05, neck_y - height * 0.16, sy)

            ear_l = _gauss(sx, sy, width * 0.30, height * 0.125, width * 0.11, height * 0.075) * _smoothstep(0.24, 0.14, ny)
            ear_r = _gauss(sx, sy, width * 0.70, height * 0.125, width * 0.11, height * 0.075) * _smoothstep(0.24, 0.14, ny)
            ahoge = _gauss(sx, sy, mx, height * 0.075, width * 0.10, height * 0.065) * _smoothstep(0.16, 0.08, ny)

            torso_core = _gauss(sx, sy, mx, neck_y + height * 0.17, width * 0.22, height * 0.20)
            hair_band = _smoothstep(0.20, 0.42, ny) * _smoothstep(0.84, 0.70, ny) * (1.0 - torso_core)
            hair_l = hair_band * _smoothstep(0.45, 0.22, nx)
            hair_r = hair_band * _smoothstep(0.55, 0.78, nx)

            chest = _gauss(sx, sy, mx, neck_y + height * 0.12, width * 0.22, height * 0.11)
            skirt = _smoothstep(0.58, 0.72, ny) * _smoothstep(0.90, 0.79, ny) if mode == "standing" else 0.0
            tail = (
                _smoothstep(0.52, 0.68, ny)
                * _smoothstep(0.92, 0.80, ny)
                * (_smoothstep(0.32, 0.14, nx) + _smoothstep(0.68, 0.86, nx))
                if mode == "standing"
                else 0.0
            )

            w_head.append(head * edge_lock)
            w_face.append(face * edge_lock)
            w_back.append(back * edge_lock)
            w_ear_l.append(ear_l * edge_lock)
            w_ear_r.append(ear_r * edge_lock)
            w_ahoge.append(ahoge * edge_lock)
            w_hair_l.append(hair_l * edge_lock)
            w_hair_r.append(hair_r * edge_lock)
            w_chest.append(chest * edge_lock)
            w_skirt.append(skirt * edge_lock)
            w_tail.append(tail * edge_lock)

    return _GridWeights(
        width=width,
        height=height,
        pad_x=pad_x,
        pad_top=pad_top,
        pad_bottom=pad_bottom,
        cols=cols,
        rows=rows,
        xs=xs,
        ys=ys,
        src_x=tuple(src_x),
        src_y=tuple(src_y),
        w_head=tuple(w_head),
        w_face=tuple(w_face),
        w_back=tuple(w_back),
        w_ear_l=tuple(w_ear_l),
        w_ear_r=tuple(w_ear_r),
        w_ahoge=tuple(w_ahoge),
        w_hair_l=tuple(w_hair_l),
        w_hair_r=tuple(w_hair_r),
        w_chest=tuple(w_chest),
        w_skirt=tuple(w_skirt),
        w_tail=tuple(w_tail),
        w_edge_lock=tuple(w_edge_lock),
        neck_x=neck_x,
        neck_y=neck_y,
        ear_l_px=ear_l_px,
        ear_l_py=ear_l_py,
        ear_r_px=ear_r_px,
        ear_r_py=ear_r_py,
        ahoge_px=ahoge_px,
        ahoge_py=ahoge_py,
    )


def _pixmap_to_sharpened_pil(pixmap: QPixmap) -> Image.Image:
    """Convert QPixmap -> straight RGBA PIL Image with subtle alpha-safe RGB sharpening."""
    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    bpl = qimg.bytesPerLine()
    buf = bytes(qimg.constBits())
    pil = Image.frombuffer("RGBA", (w, h), buf, "raw", "RGBA", bpl, 1).copy()
    # Sharpen ONLY RGB channels while keeping original A channel bit-exact (zero edge halos!).
    r, g, b, a = pil.split()
    sharp_rgb = Image.merge("RGB", (r, g, b)).filter(
        ImageFilter.UnsharpMask(radius=0.85, percent=52, threshold=4)
    )
    sr, sg, sb = sharp_rgb.split()
    return Image.merge("RGBA", (sr, sg, sb, a))


class SoftRigDeformer:
    """Caches sharpened RGBA frames and warps them cleanly via Pillow C MESH."""

    def __init__(self, *, max_cached_frames: int = 64) -> None:
        self._max_frames = max(8, int(max_cached_frames))
        self._pil_cache: OrderedDict[int, Image.Image] = OrderedDict()
        self._grid_cache: dict[tuple[int, int, str], _GridWeights] = {}

    def clear_cache(self) -> None:
        self._pil_cache.clear()

    def _get_pil(self, pixmap: QPixmap) -> Image.Image:
        key = int(pixmap.cacheKey())
        cached = self._pil_cache.get(key)
        if cached is not None:
            self._pil_cache.move_to_end(key)
            return cached
        pil = _pixmap_to_sharpened_pil(pixmap)
        self._pil_cache[key] = pil
        while len(self._pil_cache) > self._max_frames:
            self._pil_cache.popitem(last=False)
        return pil

    def _get_grid(self, width: int, height: int, mode: str) -> _GridWeights:
        key = (width, height, mode)
        grid = self._grid_cache.get(key)
        if grid is None:
            grid = _build_grid_weights(width, height, mode=mode)
            self._grid_cache[key] = grid
        return grid

    @staticmethod
    def mode_for_asset(asset_id: str) -> str:
        if asset_id in _LYING_ASSETS:
            return "lying"
        if asset_id in _DOCK_LEFT_SEAM_ASSETS:
            return "dock_left"
        if asset_id in _DOCK_RIGHT_SEAM_ASSETS:
            return "dock_right"
        if asset_id in _HANGING_ASSETS:
            return "hanging"
        return "standing"

    def deform(
        self,
        pixmap: QPixmap,
        params: RigParams,
        *,
        form_id: str = "carbon",
        asset_id: str = "idle_front",
        mirrored: bool = False,
    ) -> tuple[QImage, int, int]:
        """Return ``(warped_qimage, pad_x, pad_top)`` ready to draw at ``(-pad_x, -pad_top)``."""

        pil = self._get_pil(pixmap)
        w, h = pil.size
        mode = self.mode_for_asset(asset_id)
        grid = self._get_grid(w, h, mode)
        scale = h / 238.0
        t = params.time
        has_animal = form_id not in _HUMAN_FORMS

        # Mirror horizontal gaze/springs into texture space when the renderer flips scale_x = -1.
        flip_sign = -1.0 if mirrored else 1.0
        look_x = params.look_x * flip_sign
        look_y = params.look_y
        head_rot = params.head_rot * flip_sign
        hair_sway_l = params.hair_sway_l * flip_sign * scale
        hair_sway_r = params.hair_sway_r * flip_sign * scale
        hair_wave = params.hair_wave * scale
        hair_lift = params.hair_lift * scale
        skirt_sway = params.skirt_sway * flip_sign * scale
        tail_sway = (params.tail_sway * flip_sign * scale) if has_animal else 0.0
        ear_l_ang = (params.ear_l * flip_sign) if has_animal else 0.0
        ear_r_ang = (params.ear_r * flip_sign) if has_animal else 0.0
        ahoge_ang = params.ahoge * flip_sign
        nod_y = params.nod_y * scale
        breath_px = params.breath * 2.1 * scale
        squash = params.squash if mode == "standing" else 0.0

        cols, rows = grid.cols, grid.rows
        stride = cols + 1
        n_verts = (rows + 1) * stride
        # Inverse-mapped source coordinates for each destination grid vertex
        inv_x = [0.0] * n_verts
        inv_y = [0.0] * n_verts

        mx = w * 0.5
        lift_y = hair_lift * 6.5
        spread_x = hair_lift * 4.0

        for i in range(n_verts):
            sx = grid.src_x[i]
            sy = grid.src_y[i]

            # Forward displacement (dx, dy) in pixels; inverse-map samples (sx - dx, sy - dy).
            dx = 0.0
            dy = 0.0

            hl = grid.w_hair_l[i]
            if hl > 0.001:
                dx += hl * (
                    hair_sway_l
                    + hair_wave * math.sin(sy * 0.055 + t * 1.35)
                    + hair_wave * 0.45 * math.sin(sy * 0.11 - t * 0.9)
                    - spread_x
                )
                dy -= hl * (lift_y + hair_wave * 0.30 * math.sin(sx * 0.07 + t * 1.0))

            hr = grid.w_hair_r[i]
            if hr > 0.001:
                dx += hr * (
                    hair_sway_r
                    + hair_wave * math.sin(sy * 0.058 + t * 1.25 + 1.6)
                    + hair_wave * 0.45 * math.sin(sy * 0.115 - t * 0.8 + 2.1)
                    + spread_x
                )
                dy -= hr * (lift_y + hair_wave * 0.30 * math.sin(sx * 0.07 + t * 0.95 + 1.0))

            if has_animal:
                el = grid.w_ear_l[i]
                if el > 0.001 and abs(ear_l_ang) > 1e-4:
                    ang = ear_l_ang * el
                    c, s = math.cos(ang), math.sin(ang)
                    rx, ry = sx - grid.ear_l_px, sy - grid.ear_l_py
                    dx += (rx * c - ry * s) - rx
                    dy += (rx * s + ry * c) - ry
                er = grid.w_ear_r[i]
                if er > 0.001 and abs(ear_r_ang) > 1e-4:
                    ang = ear_r_ang * er
                    c, s = math.cos(ang), math.sin(ang)
                    rx, ry = sx - grid.ear_r_px, sy - grid.ear_r_py
                    dx += (rx * c - ry * s) - rx
                    dy += (rx * s + ry * c) - ry

            ah = grid.w_ahoge[i]
            if ah > 0.001 and abs(ahoge_ang) > 1e-4:
                ang = ahoge_ang * ah
                c, s = math.cos(ang), math.sin(ang)
                rx, ry = sx - grid.ahoge_px, sy - grid.ahoge_py
                dx += (rx * c - ry * s) - rx
                dy += (rx * s + ry * c) - ry

            sk = grid.w_skirt[i]
            if sk > 0.001:
                dx += sk * skirt_sway
                dy -= sk * hair_lift * 1.5

            tl = grid.w_tail[i]
            if tl > 0.001 and abs(tail_sway) > 1e-4:
                dx += tl * tail_sway

            ch = grid.w_chest[i]
            if ch > 0.001:
                dy -= ch * breath_px

            # 2.5D head-turn parallax: face moves toward cursor, far back hair slides opposite!
            fc = grid.w_face[i]
            if fc > 0.001:
                dx += fc * look_x * 4.6 * scale
                dy += fc * look_y * 3.1 * scale
            bk = grid.w_back[i]
            if bk > 0.001:
                dx -= bk * look_x * 2.5 * scale
                dy -= bk * look_y * 1.5 * scale

            hd = grid.w_head[i]
            if hd > 0.001:
                if abs(head_rot) > 1e-4:
                    ang = head_rot * hd
                    c, s = math.cos(ang), math.sin(ang)
                    rx, ry = sx - grid.neck_x, sy - grid.neck_y
                    dx += (rx * c - ry * s) - rx
                    dy += (rx * s + ry * c) - ry
                dy += hd * nod_y

            if abs(squash) > 1e-4:
                dx += (sx - mx) * (-squash * 0.55) * grid.w_edge_lock[i]
                dy += (sy - h) * squash * grid.w_edge_lock[i]

            inv_x[i] = sx - dx
            inv_y[i] = sy - dy

        xs, ys = grid.xs, grid.ys
        mesh: list[tuple[tuple[int, int, int, int], tuple[float, ...]]] = []
        for r in range(rows):
            y0 = int(round(ys[r]))
            y1 = int(round(ys[r + 1]))
            row0 = r * stride
            row1 = (r + 1) * stride
            for c in range(cols):
                x0 = int(round(xs[c]))
                x1 = int(round(xs[c + 1]))
                nw = row0 + c
                ne = nw + 1
                sw = row1 + c
                se = sw + 1
                mesh.append(
                    (
                        (x0, y0, x1, y1),
                        (inv_x[nw], inv_y[nw], inv_x[sw], inv_y[sw], inv_x[se], inv_y[se], inv_x[ne], inv_y[ne]),
                    )
                )

        out_w = w + grid.pad_x * 2
        out_h = h + grid.pad_top + grid.pad_bottom
        warped = pil.transform((out_w, out_h), Image.Transform.MESH, mesh, resample=Image.Resampling.BILINEAR)
        raw = warped.tobytes("raw", "RGBA")
        # Copy into an owned QImage buffer so Qt never reads freed memory.
        qimg = QImage(raw, out_w, out_h, out_w * 4, QImage.Format.Format_RGBA8888).copy()
        return qimg, grid.pad_x, grid.pad_top
