"""Antigravity-aware autonomy: what the pet decides to do on its own.

This layer sits above the original ActivityDirector (stroll / tidy / nap ...)
and only takes over when Antigravity gives it a reason:

* **陪你干活** — while a reply streams, stop wandering and play WORKING.  If the
  Antigravity window is a reachable platform, hop onto its top edge first and
  sit there (PERCH) watching.
* **醒来** — a run that starts while the pet sleeps wakes it with a WAVE.
* **打盹** — Antigravity untouched for a long while and the user away: nap.
* **没精神 / 满血** — low quota makes it yawn now and then (TIRED); a quota
  reset is celebrated.
* **提醒休息** — a long unbroken working session ends with a STRETCH and a nudge.
* **打招呼** — Antigravity coming online after being closed gets a WAVE.

Pure logic: the window feeds observations in and executes commands out.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .telemetry import LiveSnapshot

# Actions the autonomy layer may override; anything else (being dragged,
# eating, angry, a panel preview ...) is the user's moment and is left alone.
CALM_ACTIONS = frozenset({"IDLE", "BLINK", "GLANCE", "THINKING", "WALKING", "PERCH"})

LINES: dict[str, tuple[str, ...]] = {
    "hop": ("我去 Antigravity 窗口上面看着！", "跳上去盯着模型干活～"),
    "wake": ("嗯？开工了？我醒啦！", "Antigravity 动起来了，我也起床！"),
    "nap": ("Antigravity 好久没动静了，我先眯一会儿。", "没人写代码……那我睡个午觉。"),
    "tired": ("限额只剩 {quota}% 了，有点没力气……", "哈啊——限额 {quota}%，省着点用吧。"),
    "recharged": ("限额回满啦，又能放开用了！", "满血复活！限额已经重置。"),
    "stretch": ("已经连续忙了 {minutes} 分钟，起来伸个懒腰吧～", "{minutes} 分钟没休息了，喝口水再继续？"),
    "greet": ("Antigravity 上线啦，今天写点什么？", "看到 Antigravity 了，我准备好陪你了！"),
}


@dataclass(frozen=True)
class WindowTarget:
    """A window the pet can hop onto (logical Qt coordinates)."""

    handle: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left


@dataclass
class AutonomyInput:
    now: float
    snapshot: LiveSnapshot | None
    pet_action: str
    busy: bool  # dragging, falling, a panel open ...
    perched: bool = False  # currently attached to a window top
    user_idle_seconds: float | None = None
    window: WindowTarget | None = None
    can_hop: bool = True


@dataclass
class AutonomyCommand:
    kind: str  # "action" | "hop" | "say"
    action: str | None = None
    text: str = ""
    window: WindowTarget | None = None
    force: bool = False
    reason: str = ""


@dataclass
class AutonomySettings:
    nap_after_seconds: float = 25 * 60
    nap_requires_user_idle: float = 5 * 60
    tired_quota_pct: float = 25.0
    recharged_quota_pct: float = 90.0
    tired_interval: tuple[float, float] = (6 * 60, 11 * 60)
    stretch_after_seconds: float = 90 * 60
    session_gap_seconds: float = 10 * 60
    hop_cooldown_seconds: float = 10 * 60
    settle_after_busy_seconds: float = 2.5
    greet_after_offline_seconds: float = 60.0
    perch_linger_seconds: float = 6 * 60


@dataclass
class _State:
    was_running: bool = False
    last_activity_at: float | None = None
    last_tokens: int = -1
    napped_for_activity: float | None = None
    session_start: float | None = None
    last_stretch_at: float = -1e9
    next_tired_at: float = 0.0
    low_quota: bool = False
    last_hop_at: float = -1e9
    hopped_this_run: bool = False
    last_busy_at: float = -1e9
    offline_since: float | None = None
    seen_online: bool = False
    perch_idle_since: float | None = None


class AgyAutonomy:
    def __init__(self, rng: random.Random | None = None, settings: AutonomySettings | None = None) -> None:
        self.rng = rng or random.Random()
        self.settings = settings or AutonomySettings()
        self.state = _State()
        self.lines: dict[str, tuple[str, ...]] = dict(LINES)

    def set_lines(self, overrides: dict | None) -> None:
        """Per-form voice; unknown kinds are ignored, missing kinds keep defaults."""
        self.lines = dict(LINES)
        for kind, lines in (overrides or {}).items():
            if kind in LINES and isinstance(lines, list) and lines:
                self.lines[kind] = tuple(str(line) for line in lines)

    def _line(self, key: str, **values: object) -> str:
        try:
            return self.rng.choice(self.lines[key]).format(**values)
        except (KeyError, IndexError, ValueError):
            return self.rng.choice(LINES[key]).format(**values)

    def _say(self, key: str, **values: object) -> AutonomyCommand:
        return AutonomyCommand("say", text=self._line(key, **values), reason=key)

    def update(self, inp: AutonomyInput) -> list[AutonomyCommand]:
        cfg = self.settings
        st = self.state
        now = inp.now
        out: list[AutonomyCommand] = []
        if inp.busy:
            st.last_busy_at = now
        settled = not inp.busy and now - st.last_busy_at >= cfg.settle_after_busy_seconds
        snap = inp.snapshot

        # ----- online / offline ------------------------------------------------
        if snap is None:
            if st.offline_since is None:
                st.offline_since = now
            if st.was_running:
                st.was_running = False
                if inp.pet_action in {"WORKING", "PERCH"}:
                    out.append(AutonomyCommand("action", "IDLE", force=True, reason="agy_offline"))
            return out
        if st.offline_since is not None or not st.seen_online:
            away = now - st.offline_since if st.offline_since is not None else None
            if st.seen_online and away is not None and away >= cfg.greet_after_offline_seconds and settled:
                out.append(AutonomyCommand("action", "WAVE", reason="greet"))
                out.append(self._say("greet"))
            st.offline_since = None
            st.seen_online = True

        # ----- activity bookkeeping -------------------------------------------
        running = snap.running
        tokens = snap.cumulative_total_tokens
        if running or (st.last_tokens >= 0 and tokens != st.last_tokens):
            if st.session_start is None or (
                st.last_activity_at is not None and now - st.last_activity_at > cfg.session_gap_seconds
            ):
                st.session_start = now
            st.last_activity_at = now
        st.last_tokens = tokens
        if st.last_activity_at is None:
            st.last_activity_at = now

        # ----- run start / stop -----------------------------------------------
        if running and not st.was_running:
            st.hopped_this_run = False
            if inp.pet_action == "SLEEPING":
                out.append(AutonomyCommand("action", "WAVE", force=True, reason="wake"))
                out.append(self._say("wake"))
        if not running and st.was_running and inp.pet_action == "WORKING":
            out.append(AutonomyCommand("action", "PERCH" if inp.perched else "IDLE", force=True, reason="run_done"))
        st.was_running = running

        if running and settled and inp.pet_action in CALM_ACTIONS | {"WORKING"}:
            if (
                inp.can_hop
                and not inp.perched
                and not st.hopped_this_run
                and inp.window is not None
                and now - st.last_hop_at >= cfg.hop_cooldown_seconds
            ):
                st.hopped_this_run = True
                st.last_hop_at = now
                out.append(AutonomyCommand("hop", window=inp.window, reason="hop"))
                out.append(self._say("hop"))
                return out
            if inp.pet_action != "WORKING":
                out.append(AutonomyCommand("action", "WORKING", reason="work_along"))
            return out

        # After a run the pet keeps sitting on the window edge for a while, then
        # resumes its ordinary life (which can stroll along the window top).
        if inp.perched and not running:
            if st.perch_idle_since is None:
                st.perch_idle_since = now
            lingering = now - st.perch_idle_since < cfg.perch_linger_seconds
            if lingering and settled and inp.pet_action in {"IDLE", "BLINK", "GLANCE"}:
                out.append(AutonomyCommand("action", "PERCH", reason="perch_idle"))
            elif not lingering and inp.pet_action == "PERCH":
                out.append(AutonomyCommand("action", "IDLE", force=True, reason="perch_done"))
        else:
            st.perch_idle_since = None

        # ----- quota mood -------------------------------------------------------
        quota = snap.quota_remaining_pct
        if quota is not None:
            if quota <= cfg.tired_quota_pct:
                if not st.low_quota:
                    st.low_quota = True
                    st.next_tired_at = now + 20.0
                elif settled and now >= st.next_tired_at and inp.pet_action in {"IDLE", "PERCH"}:
                    st.next_tired_at = now + self.rng.uniform(*cfg.tired_interval)
                    out.append(AutonomyCommand("action", "TIRED", reason="tired"))
                    out.append(self._say("tired", quota=f"{quota:.0f}"))
                    return out
            elif quota >= cfg.recharged_quota_pct and st.low_quota:
                st.low_quota = False
                out.append(AutonomyCommand("action", "CELEBRATE", reason="recharged"))
                out.append(self._say("recharged"))
                return out

        # ----- long session -> stretch -----------------------------------------
        if (
            st.session_start is not None
            and settled
            and now - st.session_start >= cfg.stretch_after_seconds
            and now - st.last_stretch_at >= cfg.stretch_after_seconds
            and inp.pet_action in {"IDLE", "PERCH", "WALKING"}
        ):
            minutes = int((now - st.session_start) // 60)
            st.last_stretch_at = now
            st.session_start = now
            out.append(AutonomyCommand("action", "STRETCH", reason="stretch"))
            out.append(self._say("stretch", minutes=minutes))
            return out

        # ----- nap when Antigravity and the user are both quiet -----------------
        quiet = now - st.last_activity_at
        user_away = inp.user_idle_seconds is None or inp.user_idle_seconds >= cfg.nap_requires_user_idle
        if (
            quiet >= cfg.nap_after_seconds
            and user_away
            and settled
            and inp.pet_action == "IDLE"
            and st.napped_for_activity != st.last_activity_at
        ):
            st.napped_for_activity = st.last_activity_at
            out.append(AutonomyCommand("action", "SLEEPING", reason="nap"))
            out.append(self._say("nap"))
        return out


def plan_hop(
    *,
    start_x: float,
    start_y: float,
    widget_width: float,
    widget_height: float,
    target: WindowTarget,
    gravity: float,
    max_speed: float,
    work_area_top: float,
    landing_fraction: float = 0.78,
    apex_clearance: float = 60.0,
) -> tuple[float, float] | None:
    """Velocity for a ballistic jump that lands the pet on ``target``'s top edge.

    Returns None when the window is not a usable platform (too narrow, no room
    above it — e.g. maximized) or the jump would exceed the throw speed limit.
    """
    if target.width < max(180.0, widget_width * 0.8):
        return None
    land_y = target.top - widget_height  # widget top when feet are on the edge
    if land_y < work_area_top:
        return None
    land_x = target.left + target.width * landing_fraction - widget_width / 2.0
    land_x = max(target.left + 8.0 - widget_width * 0.3, min(land_x, target.right - 8.0 - widget_width * 0.7))
    apex_y = min(start_y, land_y) - apex_clearance
    if apex_y < work_area_top - widget_height * 0.5:
        apex_y = work_area_top - widget_height * 0.5
    rise = start_y - apex_y
    drop = land_y - apex_y
    if rise <= 0 or drop <= 0:
        return None
    vy = -((2.0 * gravity * rise) ** 0.5)
    t_total = (-vy / gravity) + (2.0 * drop / gravity) ** 0.5
    vx = (land_x - start_x) / t_total
    if (vx * vx + vy * vy) ** 0.5 > max_speed:
        return None
    return vx, vy
