from __future__ import annotations

import json
import random
from collections import deque
from pathlib import Path
from typing import Any

from app.i18n import get_language, resolve_language
from behavior.events import EventType
from dialogue.personality import normalize_personality


def load_form_voice(dialogue_dir: Path, form_id: str, lang: str | None = None) -> dict[str, Any]:
    """Load per-form dialogue JSON for ``lang`` (zh default, locales/<lang>/forms/ for en/ja)."""
    code = resolve_language(lang) if lang is not None else get_language()
    base_dir = Path(dialogue_dir)
    candidates: list[Path] = []
    if code != "zh":
        candidates.append(base_dir / "locales" / code / "forms" / f"{form_id}.json")
    candidates.append(base_dir / "forms" / f"{form_id}.json")
    for path in candidates:
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError, TypeError):
            continue
    return {}


class DialogueManager:
    """Loads dialogue JSON and chooses clean local lines without any model call."""

    _category_file = {
        "coding": "coding",
        "github": "github",
        "video": "video",
        "document": "document",
        "paper": "document",
        "browser": "daily",
        "ai_chat": "daily",
    }

    def __init__(self, dialogue_dir: Path, rng: random.Random | None = None, lang: str | None = None) -> None:
        self.dialogue_dir = Path(dialogue_dir)
        self._rng = rng or random.Random()
        self._lang: str | None = resolve_language(lang) if lang is not None else None
        self._cache: dict[str, dict[str, Any]] = {}
        self._recent: deque[str] = deque(maxlen=12)
        # Per-form voice: {filename: {key: [lines]}}; replaces the "standard" personality.
        self._form_lines: dict[str, dict[str, list[str]]] = {}

    def set_language(self, lang: str | None) -> None:
        resolved = resolve_language(lang) if lang is not None else None
        if resolved != self._lang:
            self._lang = resolved
            self._cache.clear()
            self._recent.clear()

    def set_form_lines(self, overrides: dict | None) -> None:
        self._form_lines = overrides if isinstance(overrides, dict) else {}
        self._recent.clear()

    def pick_for_event(self, event_type: EventType, category: str, *, personality: str) -> str | None:
        if event_type == EventType.USER_IDLE:
            return self._pick_named("idle", "idle", personality)
        if event_type == EventType.USER_RETURN:
            return self._pick_named("idle", "return", personality)
        if event_type == EventType.LATE_NIGHT:
            return self._pick_named("late_night", "lines", personality)
        if event_type == EventType.APP_STAY:
            filename = self._category_file.get(category, "daily")
            return self._pick_named(filename, "lines", personality)
        return None

    def pick_interaction(self, kind: str, *, personality: str) -> str | None:
        return self._pick_named("interaction", kind, personality)

    def pick_daily(self, *, personality: str) -> str | None:
        return self._pick_named("daily", "lines", personality)

    def pick_inner_voice(self, *, personality: str) -> str | None:
        return self._pick_named("inner_voice", "lines", personality)

    def pick_state(self, condition: str, *, personality: str) -> str | None:
        return self._pick_named("state", str(condition), personality)

    def pick_routine(self, situation: str, *, personality: str) -> str | None:
        return self._pick_named("routine", str(situation), personality)

    def pick_relationship(self, affinity: float, *, personality: str) -> str | None:
        try:
            value = float(affinity)
        except (TypeError, ValueError):
            value = 0.0
        tier = "close" if value >= 0.76 else ("familiar" if value >= 0.56 else "new")
        return self._pick_named("relationship", tier, personality)

    def _pick_named(self, filename: str, key: str, personality: str) -> str | None:
        payload = self._load(filename)
        choices = payload.get(key, {})
        if not isinstance(choices, dict):
            return None
        personality = normalize_personality(personality)
        form_lines = (self._form_lines.get(filename) or {}).get(key) if personality == "standard" else None
        lines = form_lines or choices.get(personality) or choices.get("standard") or []
        valid_lines = [line for line in lines if isinstance(line, str) and line.strip()]
        if not valid_lines:
            return None
        fresh = [line for line in valid_lines if line not in self._recent]
        if not fresh and self._recent:
            fresh = [line for line in valid_lines if line != self._recent[-1]]
        selected = self._rng.choice(fresh or valid_lines)
        self._recent.append(selected)
        return selected

    def _load(self, filename: str) -> dict[str, Any]:
        code = self._lang or get_language()
        cache_key = f"{code}:{filename}"
        if cache_key not in self._cache:
            candidates: list[Path] = []
            if code != "zh":
                candidates.append(self.dialogue_dir / "locales" / code / f"{filename}.json")
            candidates.append(self.dialogue_dir / f"{filename}.json")
            loaded: dict[str, Any] = {}
            for path in candidates:
                try:
                    if path.is_file():
                        data = json.loads(path.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            loaded = data
                            break
                except (OSError, ValueError, TypeError):
                    continue
            self._cache[cache_key] = loaded
        return self._cache[cache_key]
