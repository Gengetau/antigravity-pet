from datetime import date, datetime

from agy import pricing
from agy.telemetry import ConversationUsage, StepUsage


def _ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, 12).timestamp() * 1000)


def step(model_id, label, day, *, fresh=1_000_000, cache=0, out=0):
    return StepUsage(model_id=model_id, model_label=label, input_tokens=fresh, cache_read_tokens=cache,
                     output_tokens=out, created_ms=_ms(day))


def test_official_table_loads_and_matches_thinking_levels():
    table = pricing.load_table()
    assert table.find("gemini-4-hydrogen-xhigh").name == "Gemini 4 Hydrogen"
    assert table.find("MODEL_X", "Gemini 4 Carbon (High)").name == "Gemini 4 Carbon"
    assert table.find("gemini-4-neon-low").at(None).output == 15.0
    assert table.find("claude-sonnet") is None


def test_each_step_uses_the_price_of_its_day():
    table = pricing.load_table()
    before = step("gemini-4-carbon-high", "", date(2026, 11, 30))
    after = step("gemini-4-carbon-high", "", date(2026, 12, 1))
    report = pricing.compute([ConversationUsage("c", "t", steps=[before, after])], table)
    assert abs(report.total_usd - (2.0 + 4.0)) < 1e-9  # 1M fresh input each


def test_cache_output_unknown_and_unpriced():
    table = pricing.load_table()
    day = date(2026, 11, 20)
    steps = [
        step("gemini-4-hydrogen-high", "", day, fresh=0, cache=2_000_000, out=1_000_000),  # 0.15 + 7.5
        step("UNKNOWN_MODEL", "未知模型（离线日志）", day),  # estimated at Carbon: 2.0
        step("claude-opus", "Claude Opus", day),  # no price: listed, not counted
    ]
    report = pricing.compute([ConversationUsage("c", "t", steps=steps)], table)
    assert abs(report.total_usd - (0.15 + 7.5 + 2.0)) < 1e-9
    assert abs(report.estimated_usd - 2.0) < 1e-9
    assert report.unpriced_tokens == 1_000_000
    assert abs(report.cache_saved_usd - 2 * (1.5 - 0.075)) < 1e-9
    names = [row.name for row in report.rows]
    assert names[-1] == "Claude Opus" and not report.rows[-1].priced
    assert any("估算" in name for name in names)
    assert abs(report.daily[day] - report.total_usd) < 1e-9


def test_format_usd():
    assert pricing.format_usd(295.4) == "$295"
    assert pricing.format_usd(2.456) == "$2.46"
    assert pricing.format_usd(0.0421) == "$0.042"
    assert pricing.format_usd(0) == "$0"
