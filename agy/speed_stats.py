"""Median speed, TTFT, and total-duration analytics per model & thinking tier."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Iterable


DAY_MS = 86_400_000


@dataclass(frozen=True)
class SpeedGroup:
    label: str
    metric: str  # "speed" | "ttft" | "duration"
    median_value: float
    sample_count: int
    low_sample: bool
    first_ms: int
    last_ms: int
    median_output_tokens: int
    median_input_tokens: int


@dataclass(frozen=True)
class TrendPoint:
    created_ms: int
    value: float
    output_tokens: int
    input_tokens: int


def filter_conversations(
    conversations: Iterable,
    *,
    source_filter: str = "all",
    account_filter: str = "all",
) -> list:
    """Filter conversations uniformly by source (main/subagent) and account scope."""
    out = []
    for conv in conversations:
        is_sub = bool(getattr(conv, "is_subagent", False))
        if source_filter == "main" and is_sub:
            continue
        if source_filter == "subagent" and not is_sub:
            continue
        acct = str(getattr(conv, "account_id", "") or "")
        if account_filter == "unattributed":
            if acct:
                continue
        elif account_filter and account_filter != "all":
            if acct != account_filter:
                continue
        out.append(conv)
    return out


def _metric_value(step, metric: str) -> float | None:
    if metric == "ttft":
        ttft = getattr(step, "ttft_ms", None)
        return float(ttft) / 1000.0 if ttft is not None and ttft >= 0 else None
    if metric == "duration":
        dur = getattr(step, "duration_ms", None)
        if dur is not None and dur > 0:
            return float(dur) / 1000.0
        # Fallback if a step only carries e2e_tps and output_tokens.
        e2e = getattr(step, "e2e_tps", None)
        out_tok = int(getattr(step, "output_tokens", 0) or 0)
        if e2e is not None and e2e > 0 and out_tok > 0:
            return float(out_tok) / float(e2e)
        return None
    rate = getattr(step, "decode_tps", None)
    return float(rate) if rate is not None and rate > 0 else None


def _iter_filtered_steps(
    conversations: Iterable,
    *,
    metric: str,
    window_days: int | None,
    source_filter: str,
    now_ms: float | None,
):
    now = now_ms if now_ms is not None else time.time() * 1000.0
    cutoff = now - window_days * DAY_MS if window_days is not None and window_days > 0 else None
    for conv in filter_conversations(conversations, source_filter=source_filter):
        for step in getattr(conv, "steps", ()) or ():
            val = _metric_value(step, metric)
            if val is None:
                continue
            created = int(getattr(step, "created_ms", 0) or 0)
            if cutoff is not None and (not created or created < cutoff):
                continue
            label = str(getattr(step, "model_label", "") or "").strip() or "未知模型"
            yield label, step, val, created


def compute_speed_groups(
    conversations: Iterable,
    *,
    metric: str = "speed",
    window_days: int | None = 7,
    source_filter: str = "all",
    now_ms: float | None = None,
) -> list[SpeedGroup]:
    """Group steps by ``model_label`` (which already includes tier like ``(XHigh)``)."""
    buckets: dict[str, dict[str, list]] = {}
    for label, step, val, created in _iter_filtered_steps(
        conversations,
        metric=metric,
        window_days=window_days,
        source_filter=source_filter,
        now_ms=now_ms,
    ):
        bucket = buckets.setdefault(label, {"vals": [], "out": [], "inp": [], "ts": []})
        bucket["vals"].append(val)
        bucket["out"].append(int(getattr(step, "output_tokens", 0) or 0))
        bucket["inp"].append(int(getattr(step, "input_tokens", 0) or 0) + int(getattr(step, "cache_read_tokens", 0) or 0))
        if created > 0:
            bucket["ts"].append(created)

    groups: list[SpeedGroup] = []
    for label, b in buckets.items():
        vals = b["vals"]
        ts = b["ts"]
        groups.append(
            SpeedGroup(
                label=label,
                metric=metric,
                median_value=float(statistics.median(vals)),
                sample_count=len(vals),
                low_sample=len(vals) < 3,
                first_ms=min(ts) if ts else 0,
                last_ms=max(ts) if ts else 0,
                median_output_tokens=int(round(statistics.median(b["out"]))),
                median_input_tokens=int(round(statistics.median(b["inp"]))),
            )
        )

    reverse = metric == "speed"
    groups.sort(key=lambda g: (g.median_value if reverse else -g.median_value, g.sample_count), reverse=True)
    return groups


def compute_speed_trend(
    conversations: Iterable,
    *,
    model_label: str,
    metric: str = "speed",
    window_days: int | None = 7,
    source_filter: str = "all",
    limit: int = 80,
    now_ms: float | None = None,
) -> list[TrendPoint]:
    """Chronological samples for ``model_label`` (capped at latest ``limit``)."""
    if not model_label:
        return []
    points: list[TrendPoint] = []
    for label, step, val, created in _iter_filtered_steps(
        conversations,
        metric=metric,
        window_days=window_days,
        source_filter=source_filter,
        now_ms=now_ms,
    ):
        if label != model_label:
            continue
        points.append(
            TrendPoint(
                created_ms=created,
                value=val,
                output_tokens=int(getattr(step, "output_tokens", 0) or 0),
                input_tokens=int(getattr(step, "input_tokens", 0) or 0) + int(getattr(step, "cache_read_tokens", 0) or 0),
            )
        )
    points.sort(key=lambda p: p.created_ms)
    return points[-limit:] if limit > 0 else points
