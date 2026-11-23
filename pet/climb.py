"""Climb up a window's side edge and pull herself over onto its top; hop
between nearby windows.

Pure geometry so it can be unit-tested; the window owns the widget and asks
``step`` for the next position every tick.

Climb phases: ``approach`` (walk along the floor to the foot of the edge),
``grab`` (a short beat with both hands on the edge), ``climb`` (up the edge in
pulls that follow the 4-frame clip), ``mantle`` (up and over onto the top) and
``done`` — the caller then attaches her to the window directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

WALK_SPEED = 95.0  # px/s along the floor
CLIMB_SPEED = 62.0  # average px/s up the edge
PULL_PERIOD = 0.44  # one pull per two frames of the 4 x 220 ms climb clip
GRAB_SECONDS = 0.22  # hands on the edge before the first pull
MANTLE_SECONDS = 0.5  # up and over the top edge
MAX_APPROACH = 420.0  # farther than this: hop instead
FLOOR_TOLERANCE = 60.0  # the window must reach down to (about) her feet
MIN_CLIMB = 60.0  # nothing worth climbing below this
MOVED_LIMIT = 24.0  # the window moved this much: give up
MIN_TOP_SPAN = 180.0  # shortest uncovered top edge worth standing on


@dataclass(frozen=True, slots=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left


@dataclass(frozen=True, slots=True)
class ClimbPlan:
    handle: int
    side: str  # which window edge: "left" or "right"
    facing: str  # pet faces the wall: "right" on the left edge, "left" on the right edge
    climb_x: float  # widget x while on the wall
    floor_y: float  # widget y standing on the floor
    top_y: float  # widget y with her hands on the top edge
    edge_x: float
    window_top: float
    land_x: float = 0.0  # widget x standing on the top after the mantle
    land_y: float = 0.0  # widget y standing on the top (as attachment places her)


@dataclass(frozen=True, slots=True)
class ClimbStep:
    x: float
    y: float
    phase: str  # approach / grab / climb / mantle / done / aborted
    facing: str


def plan_climb(
    *,
    handle: int,
    window: Rect,
    work_area: Rect,
    widget_x: float,
    widget_y: float,
    widget_width: float,
    widget_height: float,
    feet_offset: float,
    sprite_width: float,
    sprite_height: float,
    reach: float | None = None,
    hand_rise: float | None = None,
) -> ClimbPlan | None:
    """Decide whether (and up which edge) she can climb ``window``.

    ``feet_offset`` is how far her feet are above the widget bottom; the
    sprite size is the current frame's size.  ``reach`` (sprite centre to the
    hands on the wall) and ``hand_rise`` (feet to the highest hand) come from
    the climb frames when known.  Returns None when the window is too far,
    does not reach the floor, is maximized, or leaves no room on top.
    """
    feet = widget_y + widget_height - feet_offset
    if window.bottom < feet - FLOOR_TOLERANCE:
        return None  # floating window: hop instead
    if feet - window.top < MIN_CLIMB:
        return None
    if window.top - (widget_height - feet_offset) < work_area.top:
        return None  # no room above it (maximized / touching the top)
    if window.right - window.left >= (work_area.right - work_area.left) - 40:
        return None  # maximized width: no side to climb
    center = widget_x + widget_width / 2.0
    reach = sprite_width * 0.30 if reach is None else reach  # hands touch the wall
    hand_rise = sprite_height * 0.72 if hand_rise is None else hand_rise
    options = []
    for side, edge in (("left", window.left), ("right", window.right)):
        stand = edge - reach if side == "left" else edge + reach
        if not (work_area.left + sprite_width / 2 <= stand <= work_area.right - sprite_width / 2):
            continue
        distance = abs(stand - center)
        if distance <= MAX_APPROACH:
            options.append((distance, side, edge, stand))
    if not options:
        return None
    _distance, side, edge, stand = min(options)
    climb_x = stand - widget_width / 2.0
    # Stop when her hands reach the top edge.
    top_feet = window.top + hand_rise
    top_y = top_feet - (widget_height - feet_offset)
    # After the mantle she stands a little way in from the edge she came up.
    inward = min(max(40.0, sprite_width * 0.55), max(0.0, window.width / 2.0))
    land_center = edge + inward if side == "left" else edge - inward
    return ClimbPlan(
        handle=handle,
        side=side,
        facing="right" if side == "left" else "left",
        climb_x=climb_x,
        floor_y=widget_y,
        top_y=min(widget_y, top_y),
        edge_x=edge,
        window_top=window.top,
        land_x=land_center - widget_width / 2.0,
        land_y=window.top - widget_height,  # same as attachment: widget bottom on the edge
    )


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


class ClimbController:
    def __init__(self) -> None:
        self.plan: ClimbPlan | None = None
        self.phase = "idle"
        self.sit_after = False
        self.clock = 0.0  # seconds in the current phase

    @property
    def active(self) -> bool:
        return self.plan is not None and self.phase in {"approach", "grab", "climb", "mantle"}

    @property
    def on_wall(self) -> bool:
        return self.plan is not None and self.phase in {"grab", "climb", "mantle"}

    def start(self, plan: ClimbPlan, *, sit_after: bool = False) -> None:
        self.plan = plan
        self.phase = "approach"
        self.sit_after = sit_after
        self.clock = 0.0

    def cancel(self) -> None:
        self.plan = None
        self.phase = "idle"
        self.sit_after = False
        self.clock = 0.0

    def _enter(self, phase: str) -> None:
        self.phase = phase
        self.clock = 0.0

    @staticmethod
    def pull_speed(clock: float) -> float:
        """Speed during a pull: fast mid-pull, nearly still between pulls.

        Averages to ``CLIMB_SPEED`` over every ``PULL_PERIOD``.
        """
        return CLIMB_SPEED * (0.2 + 1.6 * math.sin(math.pi * clock / PULL_PERIOD) ** 2)

    def step(self, dt: float, *, x: float, y: float, window: Rect | None) -> ClimbStep:
        plan = self.plan
        if plan is None:
            return ClimbStep(x, y, "aborted", "down")
        edge_now = None if window is None else (window.left if plan.side == "left" else window.right)
        if window is None or abs(edge_now - plan.edge_x) > MOVED_LIMIT or abs(window.top - plan.window_top) > MOVED_LIMIT:
            self.phase = "aborted"
            return ClimbStep(x, y, "aborted", plan.facing)
        if self.phase == "approach":
            gap = plan.climb_x - x
            # Slow down for the last few steps instead of slamming into the wall.
            speed = WALK_SPEED * (0.55 + 0.45 * min(1.0, abs(gap) / 60.0))
            move = speed * dt
            if abs(gap) <= move:
                self._enter("grab")
                return ClimbStep(plan.climb_x, y, "grab", plan.facing)
            return ClimbStep(x + (move if gap > 0 else -move), y, "approach", "right" if gap > 0 else "left")
        if self.phase == "grab":
            self.clock += dt
            if self.clock >= GRAB_SECONDS:
                self._enter("climb")
                return ClimbStep(plan.climb_x, y, "climb", plan.facing)
            return ClimbStep(plan.climb_x, y, "grab", plan.facing)
        if self.phase == "climb":
            # Integrate the pull speed in small slices so big ticks stay exact.
            new_y, left = y, dt
            while left > 1e-9:
                part = min(left, 0.01)
                new_y -= self.pull_speed(self.clock + part / 2.0) * part
                self.clock += part
                left -= part
            if new_y <= plan.top_y:
                self._enter("mantle")
                return ClimbStep(plan.climb_x, plan.top_y, "mantle", plan.facing)
            return ClimbStep(plan.climb_x, new_y, "climb", plan.facing)
        if self.phase == "mantle":
            self.clock += dt
            t = min(1.0, self.clock / MANTLE_SECONDS)
            # Body rises first, then rolls over the edge onto the top.
            new_y = plan.top_y + (plan.land_y - plan.top_y) * _ease_out(min(1.0, t / 0.75))
            new_x = plan.climb_x + (plan.land_x - plan.climb_x) * _smoothstep((t - 0.15) / 0.85)
            if t >= 1.0:
                self.phase = "done"
                return ClimbStep(plan.land_x, plan.land_y, "done", plan.facing)
            return ClimbStep(new_x, new_y, "mantle", plan.facing)
        return ClimbStep(x, y, self.phase, plan.facing)


def is_exposed(plan: ClimbPlan, window: Rect, above: list[Rect]) -> bool:
    """False when windows stacked above ``window`` hide the side she would
    climb or most of the top edge she would sit on."""
    side_x = window.left if plan.side == "left" else window.right
    height = max(1.0, window.bottom - window.top)
    width = max(1.0, window.right - window.left)
    for other in above:
        # The side she climbs: a thin strip along that edge.
        if other.left <= side_x <= other.right:
            covered = min(window.bottom, other.bottom) - max(window.top, other.top)
            if covered > height * 0.25:
                return False
        # The top edge she ends up on.
        if other.top <= window.top + 4 <= other.bottom:
            covered = min(window.right, other.right) - max(window.left, other.left)
            if covered > width * 0.5:
                return False
    return True


def uncovered_top_span(window: Rect, above: list[Rect]) -> tuple[float, float] | None:
    """The longest stretch of ``window``'s top edge no higher window covers."""
    spans = [(window.left, window.right)]
    for other in above:
        if not (other.top <= window.top + 4 <= other.bottom):
            continue
        cut: list[tuple[float, float]] = []
        for left, right in spans:
            if other.right <= left or other.left >= right:
                cut.append((left, right))
                continue
            if other.left > left:
                cut.append((left, other.left))
            if other.right < right:
                cut.append((other.right, right))
        spans = cut
    spans = [s for s in spans if s[1] - s[0] > 1.0]
    if not spans:
        return None
    return max(spans, key=lambda s: s[1] - s[0])


@dataclass(frozen=True, slots=True)
class JumpPlan:
    handle: int
    land_center_x: float  # where her centre lands on the top edge
    window: Rect


def pick_jump(
    *,
    windows: list[tuple[int, Rect]],
    work_area: Rect,
    feet_y: float,
    center_x: float,
    sprite_width: float,
    sprite_height: float,
    exclude: int | None,
    max_gap: float,
    max_up: float,
    max_down: float,
) -> JumpPlan | None:
    """The nearby window top she can jump onto, if any.

    ``windows`` is topmost first.  The landing spot is on the uncovered part
    of the top edge, as close to her as the edge allows.  ``max_gap`` limits
    the sideways distance to that spot's edge, ``max_up`` / ``max_down`` the
    height difference between her feet and the top edge.
    """
    above: list[Rect] = []
    best: tuple[float, JumpPlan] | None = None
    for handle, rect in windows:
        covered = list(above)
        above.append(rect)
        if handle == exclude:
            continue
        if rect.width < MIN_TOP_SPAN or rect.bottom - rect.top < 120.0:
            continue
        if rect.width >= (work_area.right - work_area.left) - 40:
            continue  # maximized: its top is the screen top
        if rect.top - sprite_height < work_area.top:
            continue  # no room to stand on it
        span = uncovered_top_span(rect, covered)
        if span is None or span[1] - span[0] < max(MIN_TOP_SPAN * 0.6, sprite_width * 0.9):
            continue
        rise = feet_y - rect.top  # > 0: the top is above her feet
        if rise > max_up or -rise > max_down:
            continue
        left, right = span
        if center_x < left:
            gap, land = left - center_x, left + sprite_width * 0.6
        elif center_x > right:
            gap, land = center_x - right, right - sprite_width * 0.6
        else:
            if abs(rise) < 12.0:
                continue  # that is the surface she is standing on
            gap, land = 0.0, center_x
        land = max(left + sprite_width * 0.5, min(right - sprite_width * 0.5, land))
        if gap > max_gap:
            continue
        score = gap + abs(rise) * 0.6
        if best is None or score < best[0]:
            best = (score, JumpPlan(handle, land, rect))
    return best[1] if best is not None else None
