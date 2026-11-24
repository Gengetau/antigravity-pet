from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication

from agy import speed_stats
from agy.ledger import UsageLedger, hash_account_id
from agy.telemetry import (
    ConversationUsage,
    LiveSnapshot,
    MeterReport,
    StepUsage,
    TelemetryCollector,
    build_model_rows,
)
from agy.token_meter import TokenMeterWindow


def _ms(day: date, hour: int = 12, minute: int = 0) -> int:
    return int(datetime(day.year, day.month, day.day, hour, minute).timestamp() * 1000)


def test_ledger_privacy_dedup_upgrade_retention_and_concurrency(tmp_path: Path):
    ledger_file = tmp_path / "usage_ledger.json"
    raw_email = "Test.User@Example.COM"
    acct_id = hash_account_id(f"  {raw_email}  ")
    assert acct_id == hash_account_id("test.user@example.com")
    assert acct_id.startswith("acct_")

    today = date(2026, 11, 24)
    c1 = ConversationUsage(
        conversation_id="conv-1",
        title="旧对话",
        last_modified_ms=_ms(today, 9, 0),
        steps=[StepUsage("m1", "Gemini 4 Hydrogen (XHigh)", input_tokens=500, cache_read_tokens=1000, output_tokens=200, created_ms=_ms(today, 9, 0), decode_tps=120.0)],
    )
    ledger = UsageLedger(ledger_file)
    assert ledger.ingest([c1]) is True

    # Subsequent batch drops conv-1 (simulating past LS 40-conv window) and adds conv-2 with account attribution.
    c2 = ConversationUsage(
        conversation_id="conv-2",
        title="新对话",
        last_modified_ms=_ms(today, 10, 0),
        is_subagent=True,
        steps=[StepUsage("m2", "Gemini 4 Neon (High)", input_tokens=800, cache_read_tokens=200, output_tokens=300, created_ms=_ms(today, 10, 0), decode_tps=95.0)],
    )
    c1_more = ConversationUsage(
        conversation_id="conv-1",
        title="旧对话-更新",
        last_modified_ms=_ms(today, 9, 30),
        steps=c1.steps + [StepUsage("m1", "Gemini 4 Hydrogen (XHigh)", input_tokens=600, cache_read_tokens=1200, output_tokens=250, created_ms=_ms(today, 9, 30), decode_tps=130.0)],
    )
    ledger.ingest([c1_more, c2], account_id=acct_id, tier_name="Google AI Pro")

    # Never shrink steps when a later empty conversation snapshot arrives.
    ledger.ingest([ConversationUsage(conversation_id="conv-1", title="", steps=[])])
    # Re-ingest only conv-2: conv-1 must still remain in the persisted ledger.
    ledger.ingest([c2], account_id=acct_id, tier_name="Google AI Pro")

    reloaded = UsageLedger(ledger_file)
    all_convs = reloaded.conversations(include_subagents=True)
    assert {c.conversation_id for c in all_convs} == {"conv-1", "conv-2"}
    assert len(next(c for c in all_convs if c.conversation_id == "conv-1").steps) == 2
    assert reloaded.conversations(include_subagents=False)[0].conversation_id == "conv-1"
    assert reloaded.conversations(account_filter=acct_id)
    assert reloaded.accounts() == [(acct_id, "Google AI Pro")]

    raw_text = ledger_file.read_text(encoding="utf-8")
    assert "Test.User" not in raw_text
    assert "test.user@example.com" not in raw_text

    # Concurrent ingest safety + corrupt file recovery
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            ledger.ingest(
                [ConversationUsage(f"par-{i}", f"t{i}", steps=[StepUsage("m1", "Gemini 4 Carbon (High)", input_tokens=10, created_ms=_ms(today, 11, i % 60))])],
                account_id=acct_id,
            )
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(UsageLedger(ledger_file).conversations()) == 8

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{broken json", encoding="utf-8")
    recovered = UsageLedger(corrupt)
    assert recovered.conversations() == []


def test_speed_stats_medians_low_sample_windows_and_sources():
    today = date(2026, 11, 24)
    now_ms = _ms(today, 12, 0)
    old_day = today - timedelta(days=15)

    main_conv = ConversationUsage(
        conversation_id="main",
        title="主对话",
        is_subagent=False,
        steps=[
            StepUsage("h-x", "Gemini 4 Hydrogen (XHigh)", input_tokens=1000, output_tokens=400, created_ms=_ms(today, 10, 0), ttft_ms=800.0, decode_tps=100.0, duration_ms=4200.0),
            StepUsage("h-x", "Gemini 4 Hydrogen (XHigh)", input_tokens=2000, output_tokens=500, created_ms=_ms(today, 10, 5), ttft_ms=1200.0, decode_tps=140.0, duration_ms=5000.0),
            StepUsage("h-x", "Gemini 4 Hydrogen (XHigh)", input_tokens=3000, output_tokens=600, created_ms=_ms(today, 10, 10), ttft_ms=1000.0, decode_tps=120.0, duration_ms=4600.0),
            StepUsage("c-h", "Claude Opus 5.5", input_tokens=500, output_tokens=100, created_ms=_ms(old_day, 10, 0), ttft_ms=0.0, decode_tps=60.0, duration_ms=2000.0),
        ],
    )
    sub_conv = ConversationUsage(
        conversation_id="sub",
        title="子代理",
        is_subagent=True,
        steps=[
            StepUsage("n-m", "Gemini 4 Neon (Medium)", input_tokens=400, output_tokens=200, created_ms=_ms(today, 11, 0), ttft_ms=900.0, decode_tps=160.0, duration_ms=2500.0),
        ],
    )

    groups_7d = speed_stats.compute_speed_groups([main_conv, sub_conv], metric="speed", window_days=7, source_filter="all", now_ms=now_ms)
    assert [g.label for g in groups_7d] == ["Gemini 4 Neon (Medium)", "Gemini 4 Hydrogen (XHigh)"]
    assert groups_7d[0].low_sample is True and groups_7d[0].sample_count == 1
    assert groups_7d[1].low_sample is False and groups_7d[1].median_value == 120.0

    # Zero ttft_ms (truthy trap) must still be counted in 30d window
    groups_30d_ttft = speed_stats.compute_speed_groups([main_conv], metric="ttft", window_days=30, source_filter="main", now_ms=now_ms)
    assert groups_30d_ttft[0].label == "Claude Opus 5.5" and groups_30d_ttft[0].median_value == 0.0
    assert groups_30d_ttft[1].median_value == 1.0

    dur = speed_stats.compute_speed_groups([main_conv], metric="duration", window_days=7, source_filter="main", now_ms=now_ms)
    assert len(dur) == 1 and dur[0].median_value == 4.6

    trend = speed_stats.compute_speed_trend([main_conv], model_label="Gemini 4 Hydrogen (XHigh)", metric="speed", window_days=7, now_ms=now_ms)
    assert [p.value for p in trend] == [100.0, 140.0, 120.0]


def test_collector_persists_transcripts_to_ledger(tmp_path: Path):
    root = tmp_path / "antigravity"
    logs = root / "brain" / "conv-off" / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    now_iso = datetime.now().astimezone().isoformat()
    later_iso = (datetime.now().astimezone() + timedelta(seconds=2)).isoformat()
    (logs / "transcript.jsonl").write_text(
        "\n".join([
            json.dumps({"type": "USER_INPUT", "content": "测试持久账本", "created_at": now_iso}),
            json.dumps({"type": "PLANNER_RESPONSE", "model": "MODEL_PLACEHOLDER_M532", "input_tokens": 1200, "cache_read_tokens": 3600, "output_tokens": 400, "created_at": now_iso}),
            json.dumps({"type": "USER_INPUT", "content": "next", "created_at": later_iso}),
        ]),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "usage_ledger.json"
    collector = TelemetryCollector(root, use_language_server=False, ledger_path=ledger_path)
    report1 = collector.meter_report()
    assert report1.conversation_count == 1
    assert ledger_path.is_file()

    # Delete the transcript file and ensure ledger keeps the historical conversation.
    (logs / "transcript.jsonl").unlink()
    report2 = TelemetryCollector(root, use_language_server=False, ledger_path=ledger_path).meter_report()
    assert report2.conversation_count == 1
    assert report2.grand_total == 5200


def test_token_meter_window_v2_themes_tabs_and_filters():
    QApplication.instance() or QApplication([])
    today = date.today()
    acct = hash_account_id("demo@example.com")
    convs = [
        ConversationUsage(
            conversation_id="c1",
            title="主对话",
            is_subagent=False,
            account_id=acct,
            last_modified_ms=_ms(today, 10, 0),
            steps=[
                StepUsage("gemini-4-hydrogen-xhigh", "Gemini 4 Hydrogen (XHigh)", input_tokens=500_000, cache_read_tokens=2_000_000, output_tokens=50_000, thinking_tokens=10_000, response_tokens=40_000, created_ms=_ms(today, 10, 0), ttft_ms=1100.0, decode_tps=128.0, e2e_tps=95.0, duration_ms=5200.0),
                StepUsage("gemini-4-neon-high", "Gemini 4 Neon (High)", input_tokens=200_000, cache_read_tokens=800_000, output_tokens=20_000, created_ms=_ms(today, 10, 15), ttft_ms=1400.0, decode_tps=92.0, duration_ms=3100.0),
            ],
        ),
        ConversationUsage(
            conversation_id="c2",
            title="子代理任务",
            is_subagent=True,
            account_id="",
            last_modified_ms=_ms(today, 10, 30),
            steps=[
                StepUsage("claude-opus", "Claude Opus", input_tokens=100_000, cache_read_tokens=300_000, output_tokens=15_000, created_ms=_ms(today, 10, 30), ttft_ms=900.0, decode_tps=76.0, duration_ms=2800.0),
            ],
        ),
    ]
    live = LiveSnapshot(
        source="ls",
        conversation_id="c1",
        title="主对话",
        selected_model_label="Gemini 4 Hydrogen (XHigh)",
        last_step_model_label="Gemini 4 Hydrogen (XHigh)",
        latest_decode_tps=128.0,
        quota_remaining_pct=68.0,
        cache_hit_pct=80.0,
        context_used_tokens=120_000,
        cumulative_total_tokens=2_550_000,
        user_tier_name="Google AI Pro",
        account_id=acct,
    )
    report = MeterReport(
        source="ls",
        models=build_model_rows(convs),
        conversation_count=len(convs),
        active=convs[0],
        live=live,
        conversations=convs,
        user_tier_name="Google AI Pro",
        account_id=acct,
        accounts=[(acct, "Google AI Pro")],
    )

    themes_seen: list[str] = []
    defaults_seen: list[str] = []
    win = TokenMeterWindow(
        on_request_report=lambda: None,
        on_toggle_subagents=lambda _b: None,
        initial_theme="light",
        default_tab="overview",
        on_theme_changed=themes_seen.append,
        on_default_tab_changed=defaults_seen.append,
    )
    win.update_report(report)

    assert "Google AI Pro" in win.dashboard.tier_label.text()
    assert "$19.99/月" in win.dashboard.tier_price.text()
    assert win.dashboard.hero_total.value.text() == "4.0M"
    assert win.models.rowCount() == 3
    assert win.steps.rowCount() == 2

    # Switch tabs and set default
    win.switch_tab("speed")
    assert win.current_tab() == "speed"
    win.default_btn.click()
    assert defaults_seen == ["speed"]

    # Toggle dark/light theme
    win.theme_btn.click()
    assert themes_seen == ["dark"]
    assert win.dashboard.heatmap.theme == "dark"

    # Switch back to overview and filter by account
    win.switch_tab("overview")
    acct_idx = win.account_box.findData(acct)
    assert acct_idx > 0
    win.account_box.setCurrentIndex(acct_idx)
    assert win.models.rowCount() == 2  # excludes unattributed subagent
