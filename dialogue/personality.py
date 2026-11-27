from __future__ import annotations

from app.i18n import tr

PERSONALITIES = {
    "standard": "标准小A",
    "sharp": "轻微毒舌",
    "gentle": "温和陪伴",
    "community": "社区梗",
}


def personality_label(value: str, *, lang: str | None = None) -> str:
    key = normalize_personality(value)
    return tr(f"personality.{key}", lang=lang)


def normalize_personality(value: str) -> str:
    return value if value in PERSONALITIES else "standard"
