from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

from agy.telemetry import ConversationUsage, LiveSnapshot, QuotaWindow, StepUsage, parse_quota_buckets
from agy import usage_stats


def _ms(day: date, hour: int = 10, minute: int = 0) -> int:
    return int(datetime(day.year, day.month, day.day, hour, minute).timestamp() * 1000)


def _step(day: date, minute: int = 0, *, model: str = "Gemini 4 Neon", tokens: int = 100) -> StepUsage:
    return StepUsage(model_id=model, model_label=model, input_tokens=tokens, cache_read_tokens=0, output_tokens=10, created_ms=_ms(day, 10, minute))


def test_streaks_peak_and_longest_task():
    today = date(2026, 11, 22)
    days = [today - timedelta(days=n) for n in (0, 1, 2, 5, 6, 7, 8)]
    steps = [_step(d) for d in days] + [_step(today, m, tokens=1000) for m in (3, 6, 9)]  # 9 min stretch today
    conv = ConversationUsage(conversation_id="a", title="t", steps=steps)
    stats = usage_stats.compute([conv], today=today)
    assert stats.current_streak == 3
    assert stats.longest_streak == 4
    assert stats.peak_day == today
    assert stats.longest_task_ms == 9 * 60 * 1000
    assert stats.total == sum(s.total_tokens for s in steps)
    only = usage_stats.compute([conv], model="nope", today=today)
    assert only.total == 0 and only.current_streak == 0
    assert usage_stats.compute([conv], metric="steps", today=today).total == len(steps)


def test_current_streak_survives_an_empty_today():
    today = date(2026, 11, 22)
    conv = ConversationUsage(conversation_id="a", title="t", steps=[_step(today - timedelta(days=1)), _step(today - timedelta(days=2))])
    assert usage_stats.compute([conv], today=today).current_streak == 2


def test_weekly_and_cumulative():
    monday = date(2026, 11, 16)
    daily = {monday: 1, monday + timedelta(days=6): 2, monday + timedelta(days=7): 4}
    assert usage_stats.weekly(daily) == {monday: 3, monday + timedelta(days=7): 4}
    cum = usage_stats.cumulative(daily, monday, monday + timedelta(days=7))
    assert cum[monday + timedelta(days=5)] == 1 and cum[monday + timedelta(days=7)] == 7


def test_chinese_number_format():
    assert usage_stats.format_tokens_cn(11_300_000_000) == "113亿"
    assert usage_stats.format_tokens_cn(910_000_000) == "9.1亿"
    assert usage_stats.format_tokens_cn(32_000) == "3.2万"
    assert usage_stats.format_duration(131 * 60_000) == "2 小时 11 分"


def _iso(hours: float) -> str:
    return datetime.fromtimestamp(time.time() + hours * 3600, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_quota_windows_from_buckets():
    buckets = [
        {"name": "Gemini 4", "window": "5h", "remainingPct": 62.0, "resetTime": _iso(1.8)},
        {"name": "Gemini 4", "window": "weekly", "remainingPct": 80.0, "resetTime": _iso(70)},
        {"name": "other", "window": "PT5H", "remainingPct": 40.0, "resetTime": _iso(2)},
        {"name": "off", "window": "7d", "remainingPct": 1.0, "disabled": True},
    ]
    snap = LiveSnapshot(source="hud_live", quota_windows=parse_quota_buckets(buckets), quota_remaining_pct=62.0)
    assert snap.quota_for("5h")[0] == 40.0  # the tightest bucket wins
    assert snap.quota_for("week")[0] == 80.0


def test_single_quota_is_placed_by_reset_distance():
    soon = LiveSnapshot(source="ls", quota_remaining_pct=62.0, quota_reset_time=_iso(1.8))
    assert soon.quota_for("5h") == (62.0, soon.quota_reset_time)
    assert soon.quota_for("week") == (None, None)
    later = LiveSnapshot(source="ls", quota_remaining_pct=70.0, quota_reset_time=_iso(60))
    assert later.quota_for("week")[0] == 70.0 and later.quota_for("5h")[0] is None
    assert LiveSnapshot(source="ls").quota_for("5h") == (None, None)
    unknown = LiveSnapshot(source="ls", quota_remaining_pct=50.0, quota_windows=[QuotaWindow("", "x", 10.0, None)])
    assert unknown.quota_for("5h")[0] == 50.0  # unknown windows fall back to the single quota


def test_dashboard_renders_with_data():
    from PySide6.QtWidgets import QApplication

    from agy.usage_dashboard import UsageDashboard

    QApplication.instance() or QApplication([])
    today = date.today()
    conv = ConversationUsage(conversation_id="a", title="t", steps=[_step(today - timedelta(days=n)) for n in range(5)])
    board = UsageDashboard()
    board.set_conversations([conv])
    board.set_quota((62.0, "1h 50m 后重置"), (None, ""))
    assert board.stat_current.value.text() == "5 天"
    assert board.model_box.count() == 2
    assert "62%" in board.window_5h.detail.text() and board.window_week.detail.text() == "暂无数据"
    for button in board.mode_group.buttons():
        button.click()
    # Default: this month as a calendar; "按年" shows the whole year.
    assert board.heatmap.span == "month" and board.heatmap.month == today.replace(day=1)
    assert board.month_label.text() == f"{today.year} 年 {today.month} 月"
    assert not board.next_month.isEnabled()
    board.prev_month.click()
    assert board.heatmap.month < today.replace(day=1)
    year = next(b for b in board.span_group.buttons() if b.property("span") == "year")
    year.click()
    assert board.heatmap.span == "year" and board.heatmap.sizeHint().width() > 700
    assert board.cost_total.text().startswith("$")
    cost = board.metric_box.findData("cost")
    board.metric_box.setCurrentIndex(cost)
    assert board.stat_total.value.text().startswith("$")


def test_quota_uses_the_group_of_the_current_model():
    from agy.telemetry import parse_quota_buckets

    # Shape returned by RetrieveUserQuotaSummary (via the sidecar), 2026-11-23.
    buckets = parse_quota_buckets([
        {"group": "Gemini Models", "name": "Weekly Limit Remaining", "window": "weekly", "remainingPct": 59.4, "resetTime": "w1"},
        {"group": "Gemini Models", "name": "Five Hour Limit Remaining", "window": "5h", "remainingPct": 49.2, "resetTime": "h1"},
        {"group": "Claude and GPT models", "name": "Weekly Limit Remaining", "window": "weekly", "remainingPct": 53.6, "resetTime": "w2"},
        {"group": "Claude and GPT models", "name": "Five Hour Limit Remaining", "window": "5h", "remainingPct": 100.0, "resetTime": "h2"},
    ])
    gemini = LiveSnapshot(source="hud_live", selected_model_label="Gemini 4 Neon (High)", quota_windows=buckets)
    assert gemini.quota_for("week") == (59.4, "w1")  # not the Claude/GPT group's 53.6
    assert gemini.quota_for("5h") == (49.2, "h1")
    claude = LiveSnapshot(source="hud_live", selected_model_label="Claude Opus 5.5", quota_windows=buckets)
    assert claude.quota_for("week") == (53.6, "w2")
    assert claude.quota_for("5h") == (100.0, "h2")
    unknown = LiveSnapshot(source="hud_live", quota_windows=buckets)
    assert unknown.quota_for("week")[0] == 53.6  # no model known: tightest overall
