"""Turn telemetry changes into a few rate-limited pet reactions."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .characters import form_for_model_label
from .telemetry import LiveSnapshot, format_tokens

LINES: dict[str, tuple[str, ...]] = {
    "started": (
        "Antigravity 开始干活了，我在旁边盯着 token。",
        "新一轮推理启动，起飞！",
        "模型在思考，我帮你数 token/s。",
    ),
    "finished": (
        "这一轮跑完了，共 {total} tokens。",
        "回复完成～会话累计 {total} tokens。",
        "落地成功！累计 {total} tokens，平均 {rate} tok/s。",
    ),
    "fast": ("好快！{rate} tok/s，反重力加速中。", "{rate} tok/s，风都追不上。"),
    "quota_low": ("限额只剩 {quota}% 了，省着点用哦。", "提醒：当前模型限额 {quota}%。"),
    "quota_critical": ("限额快见底了（{quota}%），{reset}。", "只剩 {quota}% 限额！{reset}"),
    "context_high": (
        "上下文已经用了 {ctx}%，可以考虑开新会话了。",
        "上下文窗口 {ctx}% 了，我有点挤。",
    ),
    "form": ("检测到 {model}，切换成 {form} 形态！", "{model} 上线，{form} 形态就位。"),
    "offline": ("Antigravity 好像没开，我先自己玩会儿。",),
    "update": ("GitHub 上有新版本 v{version} 啦，可以在侧边栏点一下更新哦～",),
}


@dataclass
class Reaction:
    kind: str
    text: str
    action: str | None = None  # PetAction name
    form: str | None = None


class ReactionTracker:
    def __init__(self, rng: random.Random | None = None, *, cooldown_seconds: float = 90.0) -> None:
        self.rng = rng or random.Random()
        self.cooldown_seconds = cooldown_seconds
        self._last_running: bool | None = None
        self._last_conversation = ""
        self._last_form: str | None = None
        self._last_at: dict[str, float] = {}
        self._quota_band = 2  # 2 ok, 1 low, 0 critical
        self._context_warned_for = ""
        self._update_notified_for = ""
        self._was_offline = False
        self.lines: dict[str, tuple[str, ...]] = dict(LINES)

    def set_lines(self, overrides: dict | None) -> None:
        """Per-form voice; unknown kinds are ignored, missing kinds keep defaults."""
        self.lines = dict(LINES)
        for kind, lines in (overrides or {}).items():
            if kind in LINES and isinstance(lines, list) and lines:
                self.lines[kind] = tuple(str(line) for line in lines)

    def reset_follow(self) -> None:
        """Forget the last followed form so re-enabling follow switches again."""
        self._last_form = None

    def _ready(self, kind: str, now: float, cooldown: float | None = None) -> bool:
        last = self._last_at.get(kind)
        if last is not None and now - last < (self.cooldown_seconds if cooldown is None else cooldown):
            return False
        self._last_at[kind] = now
        return True

    def _line(self, kind: str, **values: object) -> str:
        try:
            return self.rng.choice(self.lines[kind]).format(**values)
        except (KeyError, IndexError, ValueError):
            return self.rng.choice(LINES[kind]).format(**values)

    def observe(self, snapshot: LiveSnapshot | None, *, now: float, follow_model: bool, current_form: str) -> list[Reaction]:
        reactions: list[Reaction] = []
        if snapshot is None:
            if not self._was_offline and self._last_running is not None and self._ready("offline", now, 600):
                reactions.append(Reaction("offline", self._line("offline")))
            self._was_offline = True
            return reactions
        self._was_offline = False

        if follow_model:
            target = form_for_model_label(snapshot.model_for_form)
            if target and target != current_form and target != self._last_form:
                reactions.append(
                    Reaction("form", self._line("form", model=snapshot.model_for_form, form=target.capitalize()), "HAPPY", form=target)
                )
            self._last_form = target or self._last_form

        same_conversation = snapshot.conversation_id == self._last_conversation
        if self._last_running is not None and same_conversation:
            if snapshot.running and not self._last_running and self._ready("started", now, 45):
                reactions.append(Reaction("started", self._line("started"), "WORKING"))
            elif not snapshot.running and self._last_running and self._ready("finished", now, 30):
                rate = snapshot.avg_decode_tps or snapshot.display_rate or 0
                reactions.append(
                    Reaction(
                        "finished",
                        self._line("finished", total=format_tokens(snapshot.cumulative_total_tokens), rate=f"{rate:.0f}"),
                        "CELEBRATE",
                    )
                )
        self._last_running = snapshot.running
        self._last_conversation = snapshot.conversation_id

        rate = snapshot.latest_decode_tps or 0
        if snapshot.running and rate >= 180 and self._ready("fast", now, 300):
            reactions.append(Reaction("fast", self._line("fast", rate=f"{rate:.0f}"), "HAPPY"))

        quota = snapshot.quota_remaining_pct
        if quota is not None:
            band = 0 if quota <= 10 else 1 if quota <= 25 else 2
            if band < self._quota_band:
                from .telemetry import format_reset_countdown

                reset = format_reset_countdown(snapshot.quota_reset_time) or "等待重置"
                kind = "quota_critical" if band == 0 else "quota_low"
                reactions.append(Reaction(kind, self._line(kind, quota=f"{quota:.0f}", reset=reset), "ANGRY" if band == 0 else None))
            self._quota_band = band

        ctx = snapshot.context_pct
        if ctx >= 80 and self._context_warned_for != snapshot.conversation_id:
            self._context_warned_for = snapshot.conversation_id
            reactions.append(Reaction("context_high", self._line("context_high", ctx=f"{ctx:.0f}"), "DIZZY"))

        latest_ver = str(getattr(snapshot, "available_update_version", "") or "").strip()
        if latest_ver and latest_ver != self._update_notified_for:
            self._update_notified_for = latest_ver
            reactions.append(Reaction("update", self._line("update", version=latest_ver), "WAVE"))
        return reactions
