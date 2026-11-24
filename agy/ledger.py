"""Local persistent usage ledger so historical stats and heatmaps survive
beyond Antigravity's recent-40 conversation cache or deleted sessions.

Privacy guarantee: account identities are normalized (strip + lower) and
one-way hashed with SHA-256 (``acct_<12hex>``); raw emails or tokens are
never persisted.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable


LEDGER_VERSION = 1


def hash_account_id(raw_identity: str) -> str:
    """Return a non-reversible opaque account ID from an email or handle."""
    norm = str(raw_identity or "").strip().lower()
    if not norm:
        return ""
    if norm.startswith("acct_") and len(norm) == 17 and all(c in "0123456789abcdef" for c in norm[5:]):
        return norm
    digest = hashlib.sha256(f"agy-pet:{norm}".encode("utf-8")).hexdigest()[:12]
    return f"acct_{digest}"


def _encode_step(step: Any) -> list[Any]:
    return [
        int(getattr(step, "created_ms", 0) or 0),
        str(getattr(step, "model_id", "") or ""),
        str(getattr(step, "model_label", "") or ""),
        int(getattr(step, "input_tokens", 0) or 0),
        int(getattr(step, "cache_read_tokens", 0) or 0),
        int(getattr(step, "output_tokens", 0) or 0),
        int(getattr(step, "thinking_tokens", 0) or 0),
        int(getattr(step, "response_tokens", 0) or 0),
        getattr(step, "ttft_ms", None),
        getattr(step, "decode_tps", None),
        getattr(step, "e2e_tps", None),
        getattr(step, "duration_ms", None),
    ]


def _decode_step(row: list[Any], step_cls: type) -> Any | None:
    if not isinstance(row, list) or len(row) < 8:
        return None
    try:
        return step_cls(
            model_id=str(row[1] or "UNKNOWN_MODEL"),
            model_label=str(row[2] or ""),
            input_tokens=int(row[3] or 0),
            cache_read_tokens=int(row[4] or 0),
            output_tokens=int(row[5] or 0),
            thinking_tokens=int(row[6] or 0),
            response_tokens=int(row[7] or 0),
            created_ms=int(row[0] or 0),
            ttft_ms=float(row[8]) if len(row) > 8 and row[8] is not None else None,
            decode_tps=float(row[9]) if len(row) > 9 and row[9] is not None else None,
            e2e_tps=float(row[10]) if len(row) > 10 and row[10] is not None else None,
            duration_ms=float(row[11]) if len(row) > 11 and row[11] is not None else None,
        )
    except (TypeError, ValueError):
        return None


def _token_sum(encoded_steps: list[list[Any]]) -> int:
    total = 0
    for row in encoded_steps:
        if isinstance(row, list) and len(row) >= 6:
            total += int(row[3] or 0) + int(row[4] or 0) + int(row[5] or 0)
    return total


class UsageLedger:
    """Thread-safe JSON-backed incremental conversation usage ledger."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._accounts: dict[str, dict[str, Any]] = {}
        self._conversations: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        accts = raw.get("accounts")
        if isinstance(accts, dict):
            for k, v in accts.items():
                if isinstance(k, str) and isinstance(v, dict):
                    acct_key = hash_account_id(k) if "@" in k else k.strip()
                    if acct_key:
                        self._accounts[acct_key] = {
                            "tier_name": str(v.get("tier_name") or ""),
                            "updated_ms": int(v.get("updated_ms") or 0),
                        }
        convs = raw.get("conversations")
        if isinstance(convs, dict):
            for cid, rec in convs.items():
                if not isinstance(cid, str) or not cid or not isinstance(rec, dict):
                    continue
                acct = str(rec.get("account_id") or "").strip()
                if "@" in acct:
                    acct = hash_account_id(acct)
                steps = [s for s in (rec.get("steps") or []) if isinstance(s, list) and len(s) >= 8]
                self._conversations[cid] = {
                    "title": str(rec.get("title") or ""),
                    "status": str(rec.get("status") or ""),
                    "last_modified_ms": int(rec.get("last_modified_ms") or 0),
                    "is_subagent": bool(rec.get("is_subagent")),
                    "account_id": acct,
                    "steps": steps,
                }

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": LEDGER_VERSION,
            "accounts": self._accounts,
            "conversations": self._conversations,
        }
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(self.path)

    def ingest(
        self,
        conversations: Iterable[Any],
        *,
        account_id: str = "",
        tier_name: str = "",
    ) -> bool:
        """Merge a fresh batch of conversations into the persistent ledger."""
        safe_acct = hash_account_id(account_id) if account_id else ""
        tier = str(tier_name or "").strip()
        dirty = False
        now_ms = int(time.time() * 1000)

        with self._lock:
            if safe_acct:
                prev_acct = self._accounts.get(safe_acct)
                effective_tier = tier or (prev_acct.get("tier_name", "") if prev_acct else "")
                if prev_acct is None or prev_acct.get("tier_name") != effective_tier:
                    self._accounts[safe_acct] = {"tier_name": effective_tier, "updated_ms": now_ms}
                    dirty = True

            for conv in conversations:
                cid = str(getattr(conv, "conversation_id", "") or "").strip()
                if not cid:
                    continue
                conv_acct = hash_account_id(getattr(conv, "account_id", "") or "") or safe_acct
                new_steps = [_encode_step(s) for s in (getattr(conv, "steps", None) or [])]
                title = str(getattr(conv, "title", "") or "")
                status = str(getattr(conv, "status", "") or "")
                mod_ms = int(getattr(conv, "last_modified_ms", 0) or 0)
                is_sub = bool(getattr(conv, "is_subagent", False))

                existing = self._conversations.get(cid)
                if existing is None:
                    if not new_steps:
                        continue
                    self._conversations[cid] = {
                        "title": title,
                        "status": status,
                        "last_modified_ms": mod_ms,
                        "is_subagent": is_sub,
                        "account_id": conv_acct,
                        "steps": new_steps,
                    }
                    dirty = True
                    continue

                old_steps = existing.get("steps") or []
                old_tokens = _token_sum(old_steps)
                new_tokens = _token_sum(new_steps)
                updated_steps = old_steps
                if new_steps and (
                    len(new_steps) > len(old_steps)
                    or (len(new_steps) == len(old_steps) and new_tokens > old_tokens)
                    or (len(new_steps) == len(old_steps) and new_tokens == old_tokens and new_steps != old_steps)
                ):
                    updated_steps = new_steps

                next_acct = existing.get("account_id") or conv_acct
                next_title = title or existing.get("title", "")
                next_status = status or existing.get("status", "")
                next_mod = max(int(existing.get("last_modified_ms") or 0), mod_ms)
                next_sub = bool(existing.get("is_subagent")) or is_sub

                if (
                    updated_steps is not old_steps
                    or next_acct != existing.get("account_id", "")
                    or next_title != existing.get("title", "")
                    or next_status != existing.get("status", "")
                    or next_mod != int(existing.get("last_modified_ms") or 0)
                    or next_sub != bool(existing.get("is_subagent"))
                ):
                    existing["steps"] = updated_steps
                    existing["account_id"] = next_acct
                    existing["title"] = next_title
                    existing["status"] = next_status
                    existing["last_modified_ms"] = next_mod
                    existing["is_subagent"] = next_sub
                    dirty = True

            if dirty:
                self._save_locked()
        return dirty

    def conversations(
        self,
        *,
        include_subagents: bool = True,
        account_filter: str = "all",
    ) -> list[Any]:
        """Return stored conversations reconstructed as ``ConversationUsage``."""
        from .telemetry import ConversationUsage, StepUsage

        out: list[ConversationUsage] = []
        with self._lock:
            records = list(self._conversations.items())
        for cid, rec in records:
            is_sub = bool(rec.get("is_subagent"))
            if not include_subagents and is_sub:
                continue
            acct = str(rec.get("account_id") or "")
            if account_filter == "unattributed":
                if acct:
                    continue
            elif account_filter and account_filter != "all":
                if acct != account_filter:
                    continue
            steps: list[StepUsage] = []
            for row in rec.get("steps") or []:
                decoded = _decode_step(row, StepUsage)
                if decoded is not None:
                    steps.append(decoded)
            out.append(
                ConversationUsage(
                    conversation_id=cid,
                    title=str(rec.get("title") or f"会话 {cid[:8]}"),
                    status=str(rec.get("status") or ""),
                    last_modified_ms=int(rec.get("last_modified_ms") or 0),
                    is_subagent=is_sub,
                    account_id=acct,
                    steps=steps,
                )
            )
        out.sort(key=lambda c: c.last_modified_ms, reverse=True)
        return out

    def accounts(self) -> list[tuple[str, str]]:
        """Return attributed accounts as ``[(account_id, tier_name), ...]``."""
        with self._lock:
            items = [(acct_id, str(meta.get("tier_name") or "")) for acct_id, meta in self._accounts.items()]
        items.sort(key=lambda pair: pair[0])
        return items
