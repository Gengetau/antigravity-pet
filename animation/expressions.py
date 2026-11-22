"""Pick which face the pet wears while idling, and fade between faces.

The art for each expression only changes the face of the idle frame, so it is
swapped in for the idle pixmap.  The director keeps a face for a while (no
twitching between faces) except for hover, which reacts at once.
"""

from __future__ import annotations

from dataclasses import dataclass

CALM = "calm"  # the plain idle frame
EXPRESSIONS = ("happy", "focused", "worried", "sleepy", "shy", "pout")
CUE_SECONDS = 20.0  # how long a moment (a pat, a finished task) stays on the face
HOLD_SECONDS = 12.0
FADE_SECONDS = 0.2


@dataclass(frozen=True, slots=True)
class ExpressionInput:
    now: float
    hovered: bool = False
    running: bool = False  # the watched agent is working
    quota_pct: float | None = None
    mood: float = 0.62
    energy: float = 0.78
    annoyance: float = 0.04
    user_idle_seconds: float | None = None


class ExpressionDirector:
    def __init__(self, *, hold_seconds: float = HOLD_SECONDS, fade_seconds: float = FADE_SECONDS) -> None:
        self.hold_seconds = hold_seconds
        self.fade_seconds = fade_seconds
        self.current = CALM
        self.previous = CALM
        self.changed_at = -1e9
        self._cue: tuple[str, float] | None = None  # (expression, until)

    def cue(self, expression: str, now: float, seconds: float = CUE_SECONDS) -> None:
        """A moment that should show on the face (pat, celebrate, scolding)."""
        if expression in EXPRESSIONS:
            self._cue = (expression, now + seconds)

    def clear_cue(self) -> None:
        self._cue = None

    def wanted(self, data: ExpressionInput) -> str:
        if data.hovered:
            return "shy"
        if self._cue is not None and data.now < self._cue[1]:
            return self._cue[0]
        if data.quota_pct is not None and data.quota_pct < 20:
            return "worried"
        if data.running:
            return "focused"
        if data.annoyance >= 0.3 or data.mood < 0.3:
            return "pout"
        if data.energy < 0.25 or (data.user_idle_seconds or 0) >= 600:
            return "sleepy"
        if data.mood >= 0.8:
            return "happy"
        return CALM

    def update(self, data: ExpressionInput) -> str:
        want = self.wanted(data)
        if want != self.current:
            held = data.now - self.changed_at
            urgent = want == "shy" or self.current == "shy" or (self._cue is not None and want == self._cue[0])
            if urgent or held >= self.hold_seconds:
                self.previous, self.current, self.changed_at = self.current, want, data.now
        return self.current

    def fade(self, now: float) -> float:
        """0 → just changed (show previous), 1 → fully the current face."""
        if self.fade_seconds <= 0:
            return 1.0
        return max(0.0, min(1.0, (now - self.changed_at) / self.fade_seconds))
