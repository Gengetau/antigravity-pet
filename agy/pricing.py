"""Equivalent API cost of the recorded usage (pure, Qt-free).

Prices live in ``assets/pricing.json`` (USD per 1M tokens, with optional
effective dates).  Every step is billed at the price in force on the day it
ran: fresh input, cache-read input and output (which includes thinking).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

PRICING_PATH = Path(__file__).resolve().parents[1] / "assets" / "pricing.json"
UNKNOWN_IDS = {"", "unknown_model"}


@dataclass(frozen=True)
class Price:
    start: date | None
    input: float
    output: float
    cache: float


@dataclass(frozen=True)
class ModelPrice:
    id: str
    name: str
    match: tuple[str, ...]
    prices: tuple[Price, ...]  # oldest first

    def at(self, day: date | None) -> Price:
        current = self.prices[0]
        for price in self.prices:
            if price.start is None or day is None or day >= price.start:
                current = price
        return current


@dataclass(frozen=True)
class SubscriptionPlan:
    id: str
    name: str
    match: tuple[str, ...]
    monthly_usd: float


@dataclass
class PriceTable:
    models: list[ModelPrice]
    unknown_as: str = ""
    source: str = ""
    usd_to_cny: float = 7.25
    subscriptions: tuple[SubscriptionPlan, ...] = ()

    def find(self, model_id: str, label: str = "") -> ModelPrice | None:
        text = f"{model_id} {label}".lower()
        for model in self.models:
            if any(key in text for key in model.match):
                return model
        return None

    def by_id(self, model_id: str) -> ModelPrice | None:
        return next((m for m in self.models if m.id == model_id), None)

    def find_subscription(self, tier_name: str) -> SubscriptionPlan | None:
        text = (tier_name or "").strip().lower()
        if not text:
            return None
        for plan in self.subscriptions:
            if any(key in text for key in plan.match):
                return plan
        return None


def _day(value) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value))


def load_table(path: Path | None = None) -> PriceTable:
    raw = json.loads(Path(path or PRICING_PATH).read_text(encoding="utf-8"))
    models = []
    for item in raw.get("models", []):
        prices = sorted(
            (
                Price(_day(p.get("from")), float(p["input"]), float(p["output"]), float(p.get("cache", p["input"])))
                for p in item.get("prices", [])
            ),
            key=lambda p: p.start or date.min,
        )
        if prices:
            models.append(
                ModelPrice(
                    id=str(item["id"]),
                    name=str(item.get("name") or item["id"]),
                    match=tuple(str(m).lower() for m in item.get("match") or [item["id"]]),
                    prices=tuple(prices),
                )
            )
    subscriptions = tuple(
        SubscriptionPlan(
            id=str(item["id"]),
            name=str(item.get("name") or item["id"]),
            match=tuple(str(m).lower() for m in item.get("match") or [item["id"]]),
            monthly_usd=float(item.get("monthly_usd") or 0.0),
        )
        for item in raw.get("subscriptions", [])
        if isinstance(item, dict) and item.get("id")
    )
    rate_raw = raw.get("usd_to_cny")
    usd_to_cny = float(rate_raw) if isinstance(rate_raw, (int, float)) and rate_raw > 0 else 7.25
    return PriceTable(
        models=models,
        unknown_as=str(raw.get("unknown_as") or ""),
        source=str(raw.get("source") or ""),
        usd_to_cny=usd_to_cny,
        subscriptions=subscriptions,
    )


@dataclass
class CostRow:
    name: str
    priced: bool = True
    estimated: bool = False  # billed at the unknown_as model's price
    input_tokens: int = 0
    cache_tokens: int = 0
    output_tokens: int = 0
    input_usd: float = 0.0
    cache_usd: float = 0.0
    output_usd: float = 0.0
    steps: int = 0

    @property
    def total_usd(self) -> float:
        return self.input_usd + self.cache_usd + self.output_usd


@dataclass
class CostReport:
    rows: list[CostRow] = field(default_factory=list)
    daily: dict[date, float] = field(default_factory=dict)
    total_usd: float = 0.0
    estimated_usd: float = 0.0  # part of total that comes from unknown_as estimates
    cache_saved_usd: float = 0.0  # what the cache reads would have cost as fresh input
    unpriced_tokens: int = 0

    def spent_since(self, start: date) -> float:
        return sum(v for d, v in self.daily.items() if d >= start)


def _step_day(step) -> date | None:
    return datetime.fromtimestamp(step.created_ms / 1000).date() if step.created_ms else None


def step_cost(step, table: PriceTable) -> float:
    """USD for one step (unrecorded models at the ``unknown_as`` price; 0 if unpriced)."""
    model = table.find(step.model_id, step.model_label)
    if model is None and step.model_id.strip().lower() in UNKNOWN_IDS and table.unknown_as:
        model = table.by_id(table.unknown_as)
    if model is None:
        return 0.0
    price = model.at(_step_day(step))
    return (step.input_tokens * price.input + step.cache_read_tokens * price.cache + step.output_tokens * price.output) / 1e6


def compute(conversations: Iterable, table: PriceTable | None = None) -> CostReport:
    table = table or load_table()
    report = CostReport()
    rows: dict[str, CostRow] = {}
    fallback = table.by_id(table.unknown_as) if table.unknown_as else None
    for conversation in conversations:
        for step in conversation.steps:
            model = table.find(step.model_id, step.model_label)
            estimated = False
            if model is None and step.model_id.strip().lower() in UNKNOWN_IDS and fallback is not None:
                model, estimated = fallback, True
            key = (f"未记录模型（按 {fallback.name} 估算）" if estimated else model.name) if model else (step.model_label or step.model_id)
            row = rows.get(key)
            if row is None:
                row = rows[key] = CostRow(key, priced=model is not None, estimated=estimated)
            row.input_tokens += step.input_tokens
            row.cache_tokens += step.cache_read_tokens
            row.output_tokens += step.output_tokens
            row.steps += 1
            if model is None:
                report.unpriced_tokens += step.input_tokens + step.cache_read_tokens + step.output_tokens
                continue
            day = _step_day(step)
            price = model.at(day)
            cost_in = step.input_tokens * price.input / 1e6
            cost_cache = step.cache_read_tokens * price.cache / 1e6
            cost_out = step.output_tokens * price.output / 1e6
            row.input_usd += cost_in
            row.cache_usd += cost_cache
            row.output_usd += cost_out
            cost = cost_in + cost_cache + cost_out
            report.total_usd += cost
            if estimated:
                report.estimated_usd += cost
            report.cache_saved_usd += step.cache_read_tokens * (price.input - price.cache) / 1e6
            if day is not None:
                report.daily[day] = report.daily.get(day, 0.0) + cost
    report.rows = sorted(rows.values(), key=lambda r: (not r.priced, -r.total_usd))
    return report


def format_usd(value: float) -> str:
    if value >= 100:
        return f"${value:,.0f}"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.3f}" if value else "$0"


def format_cny(value_usd: float, rate: float = 7.25) -> str:
    cny = value_usd * (rate if rate > 0 else 7.25)
    if cny >= 1000:
        return f"¥{cny:,.0f}"
    if cny >= 100:
        return f"¥{cny:,.1f}"
    if cny >= 0.01:
        return f"¥{cny:.2f}"
    return f"¥{cny:.3f}" if cny else "¥0"


def format_usd_cny(value_usd: float, rate: float = 7.25) -> str:
    return f"{format_usd(value_usd)} ({format_cny(value_usd, rate)})"
