"""The pet forms and how they map to model families (Gemini Carbon/Hydrogen/Neon/Argon, Claude)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CharacterForm:
    id: str
    name: str
    model_family: str
    accent: str
    tagline: str


FORMS: tuple[CharacterForm, ...] = (
    CharacterForm("carbon", "Carbon", "carbon", "#7dd3fc", "稳重的碳基搭档"),
    CharacterForm("hydergon", "Hydrogen", "hydrogen", "#a7f3d0", "轻快的氢形态"),
    CharacterForm("neon", "Neon", "neon", "#f0abfc", "闪亮的霓虹形态"),
    CharacterForm("argon", "Argon", "argon", "#c4b5fd", "慢悠悠的氩猫"),
    CharacterForm("claude", "Claude", "claude", "#fdba74", "认真优雅的 Claude"),
)
FORM_IDS: tuple[str, ...] = tuple(form.id for form in FORMS)
DEFAULT_FORM = "carbon"
FOLLOW_MODEL = "follow_model"

# Labels look like "Gemini 4 Neon (High)", "Orchestrator (Carbon)" or raw ids
# like "gemini-4-carbon-medium".  "hydergon" is the asset folder's spelling.
_FAMILY_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("neon", "neon"),
    ("carbon", "carbon"),
    ("hydrogen", "hydergon"),
    ("hydergon", "hydergon"),
    ("argon", "argon"),
    ("claude", "claude"),
)


def form_by_id(form_id: str | None) -> CharacterForm:
    for form in FORMS:
        if form.id == form_id:
            return form
    return form_by_id(DEFAULT_FORM)


def normalize_form(value: object) -> str:
    return value if isinstance(value, str) and value in FORM_IDS else DEFAULT_FORM


def form_for_model_label(label: str | None) -> str | None:
    """Return the matching form id, or None for models with no dedicated form."""
    text = (label or "").lower()
    for keyword, form_id in _FAMILY_KEYWORDS:
        if keyword in text:
            return form_id
    return None


def next_form(current: str) -> str:
    index = FORM_IDS.index(normalize_form(current))
    return FORM_IDS[(index + 1) % len(FORM_IDS)]


def character_dir(root: Path, form_id: str) -> Path:
    return Path(root) / normalize_form(form_id)
