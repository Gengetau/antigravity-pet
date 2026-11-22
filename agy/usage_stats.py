"""Daily usage statistics for the Token Meter dashboard (pure, Qt-free).

Built from the per-step timestamps Antigravity records, so it only covers the
conversations the meter can read (recent ones from the language server, or
the transcripts on disk).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

METRICS = {
    "total": "Token（含缓存读取）",
    "fresh": "Token（不含缓存）",
    "output": "输出 Token",
    "steps": "步数",
    "cost": "等效金额（USD）",
}
MICRO = 1_000_000  # the "cost" metric counts micro-dollars so totals stay integers
TASK_GAP_MS = 5 * 60 * 1000  # a pause longer than this ends a stretch of work


_PRICE_TABLE = None


def _step_cost_micro(step) -> int:
    global _PRICE_TABLE
    from . import pricing

    if _PRICE_TABLE is None:
        _PRICE_TABLE = pricing.load_table()
    return round(pricing.step_cost(step, _PRICE_TABLE) * MICRO)


def step_value(step, metric: str) -> int:
    if metric == "steps":
        return 1
    if metric == "cost":
        return _step_cost_micro(step)
    if metric == "output":
        return int(step.output_tokens)
    if metric == "fresh":
        return int(step.input_tokens + step.output_tokens)
    return int(step.total_tokens)


def local_day(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000.0).date()


@dataclass
class UsageStats:
    daily: dict[date, int] = field(default_factory=dict)
    total: int = 0
    peak_day: date | None = None
    peak_value: int = 0
    longest_task_ms: int = 0
    longest_streak: int = 0
    current_streak: int = 0
    first_day: date | None = None
    steps_counted: int = 0
    models: tuple[str, ...] = ()


def compute(conversations: Iterable, *, metric: str = "total", model: str = "", today: date | None = None) -> UsageStats:
    """``model`` limits the figures to one model label ("" = all models)."""
    today = today or date.today()
    stats = UsageStats()
    labels: set[str] = set()
    for conversation in conversations:
        stamps: list[int] = []
        for step in conversation.steps:
            if step.model_label:
                labels.add(step.model_label)
            if not step.created_ms or (model and step.model_label != model):
                continue
            value = step_value(step, metric)
            day = local_day(step.created_ms)
            stats.daily[day] = stats.daily.get(day, 0) + value
            stats.total += value
            stats.steps_counted += 1
            stamps.append(step.created_ms)
        stats.longest_task_ms = max(stats.longest_task_ms, _longest_stretch(stamps))
    stats.models = tuple(sorted(labels))
    active = sorted(day for day, value in stats.daily.items() if value > 0)
    if active:
        stats.first_day = active[0]
        stats.peak_day, stats.peak_value = max(stats.daily.items(), key=lambda item: item[1])
        stats.longest_streak = _longest_run(active)
        stats.current_streak = _current_run(set(active), today)
    return stats


def _longest_stretch(stamps: list[int]) -> int:
    if not stamps:
        return 0
    stamps = sorted(stamps)
    best = 0
    start = previous = stamps[0]
    for stamp in stamps[1:]:
        if stamp - previous > TASK_GAP_MS:
            best = max(best, previous - start)
            start = stamp
        previous = stamp
    return max(best, previous - start)


def _longest_run(days: list[date]) -> int:
    best = run = 1
    for previous, current in zip(days, days[1:]):
        run = run + 1 if current - previous == timedelta(days=1) else 1
        best = max(best, run)
    return best


def _current_run(days: set[date], today: date) -> int:
    """Consecutive active days ending today (or yesterday, if today is still empty)."""
    cursor = today if today in days else today - timedelta(days=1)
    run = 0
    while cursor in days:
        run += 1
        cursor -= timedelta(days=1)
    return run


def weekly(daily: dict[date, int]) -> dict[date, int]:
    """Sum by week; the key is that week's Monday."""
    out: dict[date, int] = {}
    for day, value in daily.items():
        monday = day - timedelta(days=day.weekday())
        out[monday] = out.get(monday, 0) + value
    return out


def cumulative(daily: dict[date, int], start: date, end: date) -> dict[date, int]:
    out: dict[date, int] = {}
    running = 0
    day = start
    while day <= end:
        running += daily.get(day, 0)
        out[day] = running
        day += timedelta(days=1)
    return out


def format_tokens_cn(value: float) -> str:
    """113亿 / 9.1亿 / 3.2万 style, like the Claude usage page."""
    value = float(value)
    for unit, size in (("亿", 1e8), ("万", 1e4)):
        if abs(value) >= size:
            scaled = value / size
            return f"{scaled:.0f}{unit}" if scaled >= 100 else f"{scaled:.1f}{unit}".replace(".0" + unit, unit)
    return f"{value:.0f}"


def format_duration(ms: int) -> str:
    minutes = int(ms // 60000)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分"
    return f"{minutes} 分钟" if minutes else "不到 1 分钟"
