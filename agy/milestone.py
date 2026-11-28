"""Extract and sanitize milestone progress reports from Antigravity trajectories.

Captures two zero-token, read-only milestone signals within the active turn:
1. Agent milestone prose (``PLANNER_RESPONSE`` text emitted mid-turn or as turn summary)
2. Completed checklist items (``update_steps`` transitions to ``status == "done"``)

When a single ``PLANNER_RESPONSE`` step both marks a checklist item done and
emits a progress message, they are merged into one unified ``MilestoneEvent``.
All extracted text is Markdown-stripped and scrubbed against credentials/secrets
before ever reaching the desktop UI.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

# Secret/credential scrubbing patterns mirroring sidecars/pet-bridge/ai_comment.mjs.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>[\s\S]*?</\1\s*>", re.IGNORECASE)
_SCRIPT_OPEN_RE = re.compile(r"<(script|style)[^>]*>[\s\S]*$", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
_CODE_FENCE_OPEN_RE = re.compile(r"```[\s\S]*$")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_URL_RE = re.compile(
    r"(?:https?|wss?|file|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://\S+",
    re.IGNORECASE,
)
_AUTH_BEARER_RE = re.compile(r"\bAuthorization\s*:\s*Bearer\s+\S+", re.IGNORECASE)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._\-+/=]{8,}", re.IGNORECASE)
_KNOWN_SECRET_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_\-]{12,}|AIza[0-9A-Za-z_\-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}"
    r"|ya29\.[A-Za-z0-9_\-.]{12,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})\b"
)
_KV_SECRET_RE = re.compile(
    r"[A-Za-z0-9_-]*(?:api[_-]?key|token|secret|password|passwd|cookie)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)
_OPAQUE_BLOB_RE = re.compile(r"[A-Za-z0-9+/=_-]{44,}")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_STAR_RE = re.compile(r"\*\*([^*]+)\*\*")
_BOLD_UNDER_RE = re.compile(r"__([^_]+)__")
_HR_LINE_RE = re.compile(r"^\s*[-*_]{3,}\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_QUOTE_RE = re.compile(r"^\s*>\s*")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_TRIVIAL_RE = re.compile(r"^(?:ok|okay|done|yes|no|sure|好的|收到|完成|可以|はい|了解)[.。!！~～]*$", re.IGNORECASE)


@dataclass(frozen=True)
class MilestoneEvent:
    id: str
    kind: str  # "progress" | "summary" | "step_done"
    title: str = ""
    body: str = ""
    created_ms: int = 0
    step_done: int = 0
    step_total: int = 0
    next_step: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "createdMs": self.created_ms,
            "stepDone": self.step_done,
            "stepTotal": self.step_total,
            "nextStep": self.next_step,
        }


def milestone_from_dict(raw: object) -> MilestoneEvent | None:
    if not isinstance(raw, dict):
        return None
    mid = str(raw.get("id") or "").strip()
    kind = str(raw.get("kind") or "").strip().lower()
    if not mid or kind not in {"progress", "summary", "step_done"}:
        return None
    title = str(raw.get("title") or "").strip()
    body = str(raw.get("body") or "").strip()
    if not body and not title:
        return None
    try:
        created_ms = int(raw.get("createdMs") or raw.get("created_ms") or 0)
    except (TypeError, ValueError):
        created_ms = 0
    try:
        step_done = max(0, int(raw.get("stepDone") or raw.get("step_done") or 0))
    except (TypeError, ValueError):
        step_done = 0
    try:
        step_total = max(0, int(raw.get("stepTotal") or raw.get("step_total") or 0))
    except (TypeError, ValueError):
        step_total = 0
    next_step = str(raw.get("nextStep") or raw.get("next_step") or "").strip()
    return MilestoneEvent(
        id=mid,
        kind=kind,
        title=title,
        body=body,
        created_ms=created_ms,
        step_done=step_done,
        step_total=step_total,
        next_step=next_step,
    )


def _has_cjk(text: str) -> bool:
    return any("\u3400" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" for ch in text)


def scrub_sensitive(text: str) -> str:
    s = str(text or "")
    s = _SCRIPT_STYLE_RE.sub(" ", s)
    s = _SCRIPT_OPEN_RE.sub(" ", s)
    s = _AUTH_BEARER_RE.sub("[redacted]", s)
    s = _BEARER_RE.sub("[redacted]", s)
    s = _KNOWN_SECRET_RE.sub("[redacted]", s)
    s = _KV_SECRET_RE.sub("[redacted]", s)
    s = _URL_RE.sub("", s)
    s = _OPAQUE_BLOB_RE.sub("[…]", s)
    return s


def clean_inline_title(text: str, max_chars: int = 64) -> str:
    s = _MD_IMAGE_RE.sub("", str(text or ""))
    s = _MD_LINK_RE.sub(r"\1", s)
    s = scrub_sensitive(s)
    s = _INLINE_CODE_RE.sub(r"\1", s)
    s = _BOLD_STAR_RE.sub(r"\1", s)
    s = _BOLD_UNDER_RE.sub(r"\1", s)
    s = _HTML_TAG_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_chars:
        s = s[: max(1, max_chars - 1)].rstrip() + "…"
    return s


def clean_milestone_text(raw: str, *, max_lines: int = 4, max_chars: int | None = None) -> str:
    """Convert raw agent Markdown output into a crisp, scrubbed multi-line bubble digest."""
    if not raw or not isinstance(raw, str):
        return ""
    s = _SCRIPT_STYLE_RE.sub(" ", raw)
    s = _SCRIPT_OPEN_RE.sub(" ", s)
    s = _CODE_FENCE_RE.sub("\n", s)
    s = _CODE_FENCE_OPEN_RE.sub("\n", s)
    s = _MD_IMAGE_RE.sub("", s)
    s = _MD_LINK_RE.sub(r"\1", s)
    s = scrub_sensitive(s)

    cleaned_lines: list[str] = []
    for raw_line in s.splitlines():
        line = raw_line.strip()
        if not line or _HR_LINE_RE.match(line) or _TABLE_SEP_RE.match(line):
            continue
        is_bullet = bool(_BULLET_RE.match(line))
        line = _HEADING_RE.sub("", line)
        line = _QUOTE_RE.sub("", line)
        if is_bullet:
            line = "· " + _BULLET_RE.sub("", line)
        line = _INLINE_CODE_RE.sub(r"\1", line)
        line = _BOLD_STAR_RE.sub(r"\1", line)
        line = _BOLD_UNDER_RE.sub(r"\1", line)
        line = _HTML_TAG_RE.sub(" ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line in {"·", "-", "|"}:
            continue
        cleaned_lines.append(line)

    if not cleaned_lines:
        return ""

    sample = " ".join(cleaned_lines[:max_lines])
    budget = max_chars if max_chars is not None else (155 if _has_cjk(sample) else 210)

    selected: list[str] = []
    used = 0
    for line in cleaned_lines:
        if len(selected) >= max_lines:
            break
        remaining = budget - used - (1 if selected else 0)
        if remaining <= 12:
            break
        if len(line) <= remaining:
            selected.append(line)
            used += len(line) + (1 if len(selected) > 1 else 0)
        else:
            clipped = line[: max(1, remaining - 1)].rstrip(" ,;·:：-") + "…"
            selected.append(clipped)
            used += len(clipped)
            break

    result = "\n".join(selected).strip()
    if len(result) < 4 or _TRIVIAL_RE.match(result):
        return ""
    return result


def parse_update_steps_items(raw_steps: object) -> list[tuple[str, str]]:
    """Parse ``update_steps`` tool arguments into ``[(title, status), ...]``."""
    data = raw_steps
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except ValueError:
            return []
    if isinstance(data, dict) and "steps" in data:
        return parse_update_steps_items(data.get("steps"))
    if not isinstance(data, list):
        return []
    items: list[tuple[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        title = clean_inline_title(str(entry.get("title") or ""), max_chars=64)
        status = str(entry.get("status") or "").strip().lower()
        if title and status:
            items.append((title, status))
    return items


def _make_milestone_id(cid: str, step_index: int, kind: str, title: str, body: str, step_done: int, step_total: int) -> str:
    sig = f"{kind}|{title}|{body}|{step_done}/{step_total}".encode("utf-8", errors="ignore")
    digest = hashlib.sha1(sig).hexdigest()[:8]
    idx_part = str(step_index) if step_index >= 0 else "x"
    return f"{cid}:{idx_part}:{kind}:{digest}"


def _parse_iso_ms(value: object) -> int:
    if not isinstance(value, str) or not value:
        return 0
    from datetime import datetime

    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def _collect_turn_milestone(
    cid: str,
    turn_entries: Sequence[dict[str, Any]],
    *,
    is_running: bool,
) -> MilestoneEvent | None:
    """Scan normalized PLANNER_RESPONSE entries within the active user turn."""
    prev_done: set[str] = set()
    prev_done_count = 0
    latest: MilestoneEvent | None = None
    last_idx = len(turn_entries) - 1

    for pos, entry in enumerate(turn_entries):
        step_index = int(entry.get("step_index", -1))
        created_ms = int(entry.get("created_ms", 0))
        has_tools = bool(entry.get("has_tools", False))
        step_items = entry.get("update_steps") or []

        step_done_count = 0
        step_total_count = 0
        newly_done_title = ""
        next_step_title = ""

        if step_items:
            done_titles = [t for t, st in step_items if st == "done"]
            in_prog = [t for t, st in step_items if st == "in_progress"]
            step_total_count = len(step_items)
            step_done_count = len(done_titles)
            newly_done = [t for t in done_titles if t not in prev_done]
            if newly_done or (step_done_count > prev_done_count and done_titles):
                newly_done_title = newly_done[-1] if newly_done else done_titles[-1]
                next_step_title = in_prog[0] if in_prog else ""
            prev_done = set(done_titles)
            prev_done_count = step_done_count

        raw_text = str(entry.get("text") or "")
        body = clean_milestone_text(raw_text) if raw_text else ""

        if body:
            is_interim = has_tools or pos < last_idx or is_running
            kind = "progress" if is_interim else "summary"
            title = newly_done_title
            sd = step_done_count if newly_done_title else 0
            st_tot = step_total_count if newly_done_title else 0
            nxt = next_step_title if newly_done_title else ""
            latest = MilestoneEvent(
                id=_make_milestone_id(cid, step_index, kind, title, body, sd, st_tot),
                kind=kind,
                title=title,
                body=body,
                created_ms=created_ms,
                step_done=sd,
                step_total=st_tot,
                next_step=nxt,
            )
        elif newly_done_title:
            latest = MilestoneEvent(
                id=_make_milestone_id(
                    cid,
                    step_index,
                    "step_done",
                    newly_done_title,
                    newly_done_title,
                    step_done_count,
                    step_total_count,
                ),
                kind="step_done",
                title=newly_done_title,
                body=newly_done_title,
                created_ms=created_ms,
                step_done=step_done_count,
                step_total=step_total_count,
                next_step=next_step_title,
            )

    return latest


def extract_milestone_from_rpc_steps(
    cid: str,
    raw_steps: Sequence[object],
    *,
    is_running: bool = False,
    step_offset: int = 0,
) -> MilestoneEvent | None:
    """Extract the latest milestone in the active user turn from LS RPC steps."""
    if not cid or not raw_steps:
        return None
    # Locate the last user input boundary in the provided slice.
    start = 0
    for i in range(len(raw_steps) - 1, -1, -1):
        st = raw_steps[i]
        if isinstance(st, dict) and st.get("type") == "CORTEX_STEP_TYPE_USER_INPUT":
            start = i + 1
            break

    turn_entries: list[dict[str, Any]] = []
    for i in range(start, len(raw_steps)):
        st = raw_steps[i]
        if not isinstance(st, dict):
            continue
        pr = st.get("plannerResponse")
        if not isinstance(pr, dict):
            continue
        meta = st.get("metadata") or {}
        tool_calls = pr.get("toolCalls") if isinstance(pr.get("toolCalls"), list) else []
        step_items: list[tuple[str, str]] = []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            if str(call.get("name") or "") == "update_steps":
                parsed = parse_update_steps_items(call.get("argumentsJson") or call.get("args"))
                if parsed:
                    step_items = parsed
        text = str(pr.get("modifiedResponse") or pr.get("response") or "")
        if not text and not step_items:
            continue
        turn_entries.append(
            {
                "step_index": step_offset + i,
                "created_ms": _parse_iso_ms(meta.get("finishedGeneratingAt") or meta.get("completedAt") or meta.get("createdAt")),
                "has_tools": len(tool_calls) > 0,
                "update_steps": step_items,
                "text": text,
            }
        )
    return _collect_turn_milestone(cid, turn_entries, is_running=is_running)


def extract_milestone_from_transcript_records(
    cid: str,
    records: Sequence[dict[str, Any]],
    *,
    is_running: bool = False,
) -> MilestoneEvent | None:
    """Extract the latest milestone in the active user turn from parsed transcript records."""
    if not cid or not records:
        return None
    start = 0
    for i in range(len(records) - 1, -1, -1):
        rec = records[i]
        if isinstance(rec, dict) and rec.get("type") == "USER_INPUT":
            start = i + 1
            break

    turn_entries: list[dict[str, Any]] = []
    for rec in records[start:]:
        if not isinstance(rec, dict) or rec.get("type") != "PLANNER_RESPONSE":
            continue
        tool_calls = rec.get("tool_calls") if isinstance(rec.get("tool_calls"), list) else []
        step_items: list[tuple[str, str]] = []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            if str(call.get("name") or "") == "update_steps":
                args = call.get("args")
                raw_steps = args.get("steps") if isinstance(args, dict) else args
                parsed = parse_update_steps_items(raw_steps)
                if parsed:
                    step_items = parsed
        text = str(rec.get("content") or "")
        if not text and not step_items:
            continue
        raw_idx = rec.get("step_index")
        try:
            step_index = int(raw_idx) if raw_idx is not None else -1
        except (TypeError, ValueError):
            step_index = -1
        turn_entries.append(
            {
                "step_index": step_index,
                "created_ms": _parse_iso_ms(rec.get("created_at")),
                "has_tools": len(tool_calls) > 0,
                "update_steps": step_items,
                "text": text,
            }
        )
    return _collect_turn_milestone(cid, turn_entries, is_running=is_running)


def read_latest_milestone_from_transcript(
    cid: str,
    path: Path,
    *,
    is_running: bool = False,
    tail_bytes: int = 196 * 1024,
) -> MilestoneEvent | None:
    """Read only the tail of ``transcript.jsonl`` and extract the latest turn milestone."""
    if not cid or not path:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    if st.st_size <= 0:
        return None
    read_len = min(st.st_size, max(8192, int(tail_bytes)))
    try:
        with path.open("rb") as fh:
            if st.st_size > read_len:
                fh.seek(st.st_size - read_len)
            chunk = fh.read(read_len)
    except OSError:
        return None
    text = chunk.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if st.st_size > read_len and lines:
        lines = lines[1:]  # Drop potentially truncated leading line
    records: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return extract_milestone_from_transcript_records(cid, records, is_running=is_running)
