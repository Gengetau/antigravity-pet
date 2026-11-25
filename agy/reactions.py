"""Turn telemetry changes into rate-limited pet reactions, particles, and seasonal greetings."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime

from .characters import form_for_model_label
from .telemetry import LiveSnapshot, format_reset_countdown, format_tokens, parse_iso_ms

TOOL_STATUS_NAMES: dict[str, str] = {
    "reading": "陪你读代码",
    "writing": "陪你写代码",
    "running": "盯终端跑命令",
    "searching": "一起查资料",
    "drawing": "围观画图中",
    "delegating": "指挥子代理",
    "asking": "等你确认啦",
}

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
    "turn_error": (
        "哎呀，刚才那轮出错中断了，我们一起看看报错吧。",
        "好像翻车了……别急，我陪你排查！",
    ),
    "waiting": (
        "喂喂，Antigravity 卡在等你确认或回复啦！",
        "那边有确认弹窗/提问在等你哦～",
    ),
    "subagent_start": (
        "召唤出小分身帮忙干活啦！",
        "子代理小分身就位，人多力量大！",
    ),
    "subagent_many": (
        "哇，同时派出 {count} 个小分身！排面拉满～",
        "{count} 个小分身并行开工，效率起飞！",
    ),
    "fast": ("好快！{rate} tok/s，反重力加速中。", "{rate} tok/s，风都追不上。"),
    "quota_low": ("限额只剩 {quota}% 了，省着点用哦。", "提醒：当前模型限额 {quota}%。"),
    "quota_critical": ("限额快见底了（{quota}%），{reset}。", "只剩 {quota}% 限额！{reset}"),
    "quota_reset_soon": (
        "小鱼干马上补货！限额还有约 {reset} 重置～",
        "坚持一下，再过 {reset} 限额就刷新啦！",
    ),
    "quota_refilled": (
        "限额补满啦（{quota}%）！干活能量回满～",
        "耶！小鱼干到账，限额恢复到 {quota}%！",
    ),
    "context_high": (
        "上下文已经用了 {ctx}%，可以考虑开新会话了。",
        "上下文窗口 {ctx}% 了，我有点挤。",
    ),
    "form": ("检测到 {model}，切换成 {form} 形态！", "{model} 上线，{form} 形态就位。"),
    "offline": ("Antigravity 好像没开，我先自己玩会儿。",),
    "update": ("GitHub 上有新版本 v{version} 啦，可以在侧边栏点一下更新哦～",),
    "update_commit": ("GitHub 主分支有新提交（{sha}）啦，侧边栏可以一键拉取更新～",),
}

# Solar-calendar fixed holidays: (month, day) -> (id, greeting)
_FIXED_FESTIVALS: dict[tuple[int, int], tuple[str, str]] = {
    (1, 1): ("newyear", "元旦快乐！新年新代码，零 bug 起步～"),
    (10, 1): ("national", "国庆快乐！放假也别忘了好好休息哦～"),
    (10, 31): ("halloween", "不给小鱼干就捣蛋！万圣节快乐～"),
    (12, 25): ("christmas", "圣诞快乐！送你一份热乎乎的圣诞礼物～"),
}

# Lunar festivals mapped to solar (year, month, day) for 2025-2030.
_LUNAR_FESTIVALS: dict[tuple[int, int, int], tuple[str, str]] = {
    (2025, 1, 29): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2025, 2, 12): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2025, 5, 31): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2025, 10, 6): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2026, 2, 17): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2026, 3, 3): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2026, 6, 19): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2026, 9, 25): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2027, 2, 6): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2027, 2, 20): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2027, 6, 9): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2027, 9, 15): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2028, 1, 26): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2028, 2, 9): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2028, 5, 28): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2028, 10, 3): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2029, 2, 13): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2029, 2, 27): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2029, 6, 16): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2029, 9, 22): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
    (2030, 2, 3): ("spring", "春节快乐！新年万事顺意，代码一次跑通～"),
    (2030, 2, 17): ("lantern", "元宵节快乐！记得吃碗汤圆再写代码～"),
    (2030, 6, 5): ("dragonboat", "端午安康！甜粽还是咸粽，我都喜欢～"),
    (2030, 9, 12): ("midautumn", "中秋快乐！今晚月亮圆圆的，早点休息哦～"),
}


def greeting_for_moment(dt: datetime | None = None) -> tuple[str, str, str | None]:
    """Return ``(kind, greeting_line, particle_effect)`` for the local clock/festival."""
    now = dt or datetime.now()
    lunar = _LUNAR_FESTIVALS.get((now.year, now.month, now.day))
    if lunar is not None:
        return f"fest_{lunar[0]}", lunar[1], "confetti"
    fixed = _FIXED_FESTIVALS.get((now.month, now.day))
    if fixed is not None:
        return f"fest_{fixed[0]}", fixed[1], "confetti"
    hour = now.hour
    if 1 <= hour < 5:
        return "late_night", "已经凌晨啦，快去睡觉吧，明天再继续～", "sweat"
    if 5 <= hour < 11:
        return "morning", "早安！新的一天，一起把今天的任务稳稳拿下～", "sparkles"
    if 11 <= hour < 14:
        return "noon", "中午好呀，记得按时吃午饭别饿着！", None
    if 14 <= hour < 18:
        return "afternoon", "下午好～泡杯茶或咖啡，状态拉满！", None
    if 18 <= hour < 23:
        return "evening", "晚上好！辛苦一天啦，今晚也陪着你。", "sparkles"
    return "night", "夜深啦，注意保护眼睛，收完这波早点休息哦。", None


@dataclass
class Reaction:
    kind: str
    text: str
    action: str | None = None  # PetAction name
    form: str | None = None
    particle: str | None = None  # sparkles / confetti / hearts / sweat / fish / alert


class ReactionTracker:
    def __init__(self, rng: random.Random | None = None, *, cooldown_seconds: float = 90.0) -> None:
        self.rng = rng or random.Random()
        self.cooldown_seconds = cooldown_seconds
        self._last_running: bool | None = None
        self._last_conversation = ""
        self._last_form: str | None = None
        self._last_at: dict[str, float] = {}
        self._quota_band = 2  # 2 ok, 1 low, 0 critical
        self._last_quota_pct: float | None = None
        self._reset_soon_active = False
        self._was_waiting = False
        self._last_subagent_count = 0
        self._context_warned_for = ""
        self._update_notified_for = ""
        self._last_ai_comment_id = ""
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

    def _effective_quota(self, snapshot: LiveSnapshot) -> tuple[float | None, str | None]:
        q5, reset5 = snapshot.quota_for("5h")
        if q5 is not None:
            return q5, reset5
        return snapshot.quota_remaining_pct, snapshot.quota_reset_time

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
                    Reaction(
                        "form",
                        self._line("form", model=snapshot.model_for_form, form=target.capitalize()),
                        "HAPPY",
                        form=target,
                        particle="sparkles",
                    )
                )
            self._last_form = target or self._last_form

        same_conversation = snapshot.conversation_id == self._last_conversation
        if self._last_running is not None and same_conversation:
            if snapshot.running and not self._last_running and self._ready("started", now, 45):
                reactions.append(Reaction("started", self._line("started"), "WORKING"))
            elif not snapshot.running and self._last_running:
                if snapshot.termination_reason.upper() == "ERROR" and self._ready("turn_error", now, 30):
                    reactions.append(Reaction("turn_error", self._line("turn_error"), "DIZZY", particle="sweat"))
                elif self._ready("finished", now, 30):
                    rate = snapshot.avg_decode_tps or snapshot.display_rate or 0
                    reactions.append(
                        Reaction(
                            "finished",
                            self._line("finished", total=format_tokens(snapshot.cumulative_total_tokens), rate=f"{rate:.0f}"),
                            "CELEBRATE",
                            particle="confetti",
                        )
                    )
        self._last_running = snapshot.running
        self._last_conversation = snapshot.conversation_id

        # Waiting for user confirmation / answer (e.g. approval prompt or ask_question)
        if snapshot.waiting_for_user and not self._was_waiting and self._ready("waiting", now, 60):
            reactions.append(Reaction("waiting", self._line("waiting"), "WAVE", particle="alert"))
        self._was_waiting = bool(snapshot.waiting_for_user)

        # Active subagent clones
        sub_count = len(snapshot.active_subagents)
        if sub_count >= 2 and self._last_subagent_count < 2 and self._ready("subagent_many", now, 180):
            reactions.append(
                Reaction("subagent_many", self._line("subagent_many", count=sub_count), "CELEBRATE", particle="sparkles")
            )
        elif sub_count >= 1 and self._last_subagent_count == 0 and self._ready("subagent_start", now, 120):
            reactions.append(Reaction("subagent_start", self._line("subagent_start"), "HAPPY", particle="sparkles"))
        self._last_subagent_count = sub_count

        rate = snapshot.latest_decode_tps or 0
        if snapshot.running and rate >= 180 and self._ready("fast", now, 300):
            reactions.append(Reaction("fast", self._line("fast", rate=f"{rate:.0f}"), "HAPPY", particle="sparkles"))

        quota, quota_reset = self._effective_quota(snapshot)
        if quota is not None:
            band = 0 if quota <= 10 else 1 if quota <= 25 else 2
            if band < self._quota_band:
                reset = format_reset_countdown(quota_reset) or "等待重置"
                kind = "quota_critical" if band == 0 else "quota_low"
                reactions.append(
                    Reaction(
                        kind,
                        self._line(kind, quota=f"{quota:.0f}", reset=reset),
                        "ANGRY" if band == 0 else None,
                        particle="sweat" if band == 0 else None,
                    )
                )
            elif (
                self._last_quota_pct is not None
                and quota - self._last_quota_pct >= 12.0
                and self._ready("quota_refilled", now, 1800)
            ):
                reactions.append(
                    Reaction(
                        "quota_refilled",
                        self._line("quota_refilled", quota=f"{quota:.0f}"),
                        "CELEBRATE",
                        particle="fish",
                    )
                )

            reset_ms = parse_iso_ms(quota_reset)
            remaining_reset_ms = (reset_ms - time.time() * 1000) if reset_ms else None
            reset_soon = remaining_reset_ms is not None and 0 < remaining_reset_ms <= 20 * 60_000 and quota <= 50.0
            if reset_soon and not self._reset_soon_active and self._ready("quota_reset_soon", now, 1800):
                countdown = format_reset_countdown(quota_reset) or "不到 20 分钟"
                reactions.append(
                    Reaction(
                        "quota_reset_soon",
                        self._line("quota_reset_soon", reset=countdown),
                        "HAPPY",
                        particle="sparkles",
                    )
                )
            self._reset_soon_active = reset_soon
            self._quota_band = band
            self._last_quota_pct = quota

        ctx = snapshot.context_pct
        if ctx >= 80 and self._context_warned_for != snapshot.conversation_id:
            self._context_warned_for = snapshot.conversation_id
            reactions.append(
                Reaction("context_high", self._line("context_high", ctx=f"{ctx:.0f}"), "DIZZY", particle="sweat")
            )

        latest_ver = str(getattr(snapshot, "available_update_version", "") or "").strip()
        latest_sha = str(getattr(snapshot, "available_update_sha", "") or "").strip()
        update_token = latest_ver or latest_sha
        if update_token and update_token != self._update_notified_for:
            self._update_notified_for = update_token
            if latest_ver:
                reactions.append(Reaction("update", self._line("update", version=latest_ver), "WAVE", particle="sparkles"))
            else:
                reactions.append(Reaction("update", self._line("update_commit", sha=latest_sha[:7]), "WAVE", particle="sparkles"))

        ai_id = str(getattr(snapshot, "ai_comment_id", "") or "").strip()
        ai_text = str(getattr(snapshot, "ai_comment_text", "") or "").strip()
        if ai_id and ai_text and ai_id != self._last_ai_comment_id:
            self._last_ai_comment_id = ai_id
            reactions.append(Reaction("ai_comment", ai_text, None, particle="sparkles"))
        return reactions
