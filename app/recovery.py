"""Crash markers, rotating logs and safe recovery for the desktop pet."""

from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    unclean_exit: bool = False
    consecutive_crashes: int = 0
    safe_mode: bool = False


def configure_logging(path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if any(getattr(handler, "baseFilename", None) == str(path) for handler in root.handlers):
        return
    handler = RotatingFileHandler(
        path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)


class CrashRecovery:
    """Detect unclean exits and keep a small atomic session marker."""

    STABLE_SESSION_SECONDS: float = 60.0

    def __init__(
        self,
        marker_path: Path,
        crash_reports_dir: Path,
        *,
        version: str,
        clock: Callable[[], float] = time.time,
        stable_session_seconds: float = STABLE_SESSION_SECONDS,
    ) -> None:
        self.marker_path = Path(marker_path)
        self.crash_reports_dir = Path(crash_reports_dir)
        self.version = str(version)
        self.clock = clock
        self.stable_session_seconds = max(1.0, float(stable_session_seconds))
        self.session_id = uuid.uuid4().hex
        self.status = RecoveryStatus()
        self._fatal = False
        self._last_report: Path | None = None

    @property
    def fatal(self) -> bool:
        return self._fatal

    @property
    def last_report(self) -> Path | None:
        return self._last_report

    def begin(self) -> RecoveryStatus:
        previous = self._read_marker()
        unclean = bool(previous.get("active"))
        previous_count = self._safe_int(previous.get("consecutive_crashes"))
        was_real_crash = False
        if unclean:
            has_error = bool(previous.get("last_error"))
            prev_started = self._safe_float(previous.get("started_at"))
            prev_hb = self._safe_float(previous.get("last_heartbeat"))
            lived_seconds = (
                max(0.0, prev_hb - prev_started)
                if (prev_started > 0.0 and prev_hb >= prev_started)
                else 0.0
            )
            # Only treat an unclean exit as a crash-loop step if an unhandled
            # exception was recorded or the previous process died before running
            # stably for ``stable_session_seconds`` (e.g. startup crash).
            was_real_crash = has_error or lived_seconds < self.stable_session_seconds
        count = previous_count + 1 if was_real_crash else 0
        self.status = RecoveryStatus(
            unclean_exit=unclean,
            consecutive_crashes=count,
            safe_mode=count >= 2,
        )
        now = self.clock()
        self._write_marker(
            {
                "active": True,
                "session_id": self.session_id,
                "version": self.version,
                "started_at": now,
                "last_heartbeat": now,
                "consecutive_crashes": count,
                "safe_mode": self.status.safe_mode,
            }
        )
        return self.status

    def heartbeat(self) -> None:
        marker = self._read_marker()
        if marker.get("session_id") != self.session_id:
            return
        now = self.clock()
        marker["last_heartbeat"] = now
        started = self._safe_float(marker.get("started_at"))
        if (
            not self._fatal
            and started > 0.0
            and now - started >= self.stable_session_seconds
            and marker.get("safe_mode")
        ):
            marker["consecutive_crashes"] = 0
            marker["safe_mode"] = False
        self._write_marker(marker)

    def record_exception(
        self,
        exc_type: type[BaseException],
        error: BaseException,
        tb: object,
    ) -> Path:
        self._fatal = True
        if self._last_report is not None:
            return self._last_report
        self.crash_reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.clock()))
        report = self.crash_reports_dir / f"crash-{timestamp}.log"
        formatted = "".join(traceback.format_exception(exc_type, error, tb))
        report.write_text(
            f"Antigravity Desktop Pet {self.version}\n"
            f"session={self.session_id}\n"
            f"time={self.clock():.3f}\n\n{formatted}",
            encoding="utf-8",
        )
        marker = self._read_marker()
        marker.update(
            {
                "active": True,
                "last_error": f"{exc_type.__name__}: {error}",
                "last_error_at": self.clock(),
                "crash_report": str(report),
            }
        )
        self._write_marker(marker)
        self._last_report = report
        logging.getLogger(__name__).critical("Unhandled exception\n%s", formatted)
        return report

    def finish(self) -> None:
        if self._fatal:
            return
        marker = self._read_marker()
        if marker.get("session_id") != self.session_id:
            return
        marker.update(
            {
                "active": False,
                "clean_exit_at": self.clock(),
                "consecutive_crashes": 0,
                "safe_mode": False,
            }
        )
        self._write_marker(marker)

    def _read_marker(self) -> dict[str, object]:
        try:
            value = json.loads(self.marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_marker(self, value: dict[str, object]) -> None:
        self.marker_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False, indent=2)
        temporary = self.marker_path.with_suffix(f"{self.marker_path.suffix}.{uuid.uuid4().hex[:6]}.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            for attempt in range(5):
                try:
                    temporary.replace(self.marker_path)
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass

    @staticmethod
    def _safe_int(value: object) -> int:
        return max(0, int(value)) if isinstance(value, int) and not isinstance(value, bool) else 0

    @staticmethod
    def _safe_float(value: object) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return 0.0
