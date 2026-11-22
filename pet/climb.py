"""Climb up a window's side edge, then hop over onto its top.

Pure geometry so it can be unit-tested; the window owns the widget and asks
``step`` for the next position every tick.

Phases: ``approach`` (walk along the floor to the foot of the edge), then
``climb`` (straight up the edge), then ``done`` — the caller launches a small
planned jump inward so the existing landing code attaches her to the window.
"""

from __future__ import annotations

from dataclasses import dataclass

WALK_SPEED = 95.0  # px/s along the floor
CLIMB_SPEED = 62.0  # px/s up the edge; matched to the 4-frame cycle
MAX_APPROACH = 420.0  # farther than this: hop instead
FLOOR_TOLERANCE = 60.0  # the window must reach down to (about) her feet
MIN_CLIMB = 60.0  # nothing worth climbing below this
MOVED_LIMIT = 24.0  # the window moved this much: give up


@dataclass(frozen=True, slots=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True, slots=True)
class ClimbPlan:
    handle: int
    side: str  # which window edge: "left" or "right"
    facing: str  # pet faces the wall: "right" on the left edge, "left" on the right edge
    climb_x: float  # widget x while on the wall
    floor_y: float  # widget y standing on the floor
    top_y: float  # widget y where she stops climbing and hops over
    edge_x: float
    window_top: float


@dataclass(frozen=True, slots=True)
class ClimbStep:
    x: float
    y: float
    phase: str  # approach / climb / done / aborted
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
) -> ClimbPlan | None:
    """Decide whether (and up which edge) she can climb ``window``.

    ``feet_offset`` is how far her feet are above the widget bottom; the
    sprite size is the current frame's size.  Returns None when the window is
    too far, does not reach the floor, is maximized, or leaves no room on top.
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
    reach = sprite_width * 0.30  # hands touch the wall
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
    # Stop when her hands reach the top edge (about 3/4 of the sprite above the feet).
    top_feet = window.top + sprite_height * 0.72
    top_y = top_feet - (widget_height - feet_offset)
    return ClimbPlan(
        handle=handle,
        side=side,
        facing="right" if side == "left" else "left",
        climb_x=climb_x,
        floor_y=widget_y,
        top_y=min(widget_y, top_y),
        edge_x=edge,
        window_top=window.top,
    )


class ClimbController:
    def __init__(self) -> None:
        self.plan: ClimbPlan | None = None
        self.phase = "idle"
        self.sit_after = False

    @property
    def active(self) -> bool:
        return self.plan is not None and self.phase in {"approach", "climb"}

    def start(self, plan: ClimbPlan, *, sit_after: bool = False) -> None:
        self.plan = plan
        self.phase = "approach"
        self.sit_after = sit_after

    def cancel(self) -> None:
        self.plan = None
        self.phase = "idle"
        self.sit_after = False

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
            move = WALK_SPEED * dt
            if abs(gap) <= move:
                self.phase = "climb"
                return ClimbStep(plan.climb_x, y, "climb", plan.facing)
            return ClimbStep(x + (move if gap > 0 else -move), y, "approach", "right" if gap > 0 else "left")
        new_y = y - CLIMB_SPEED * dt
        if new_y <= plan.top_y:
            self.phase = "done"
            return ClimbStep(plan.climb_x, plan.top_y, "done", plan.facing)
        return ClimbStep(plan.climb_x, new_y, "climb", plan.facing)


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
