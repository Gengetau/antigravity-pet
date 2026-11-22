"""Background polling that keeps network and disk work off the GUI thread."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

from .telemetry import TelemetryCollector

LOGGER = logging.getLogger(__name__)


class TelemetryService(QObject):
    live_updated = Signal(object)  # LiveSnapshot | None
    report_ready = Signal(object)  # MeterReport

    RUNNING_INTERVAL = 1.5
    IDLE_INTERVAL = 5.0
    OFFLINE_INTERVAL = 15.0

    def __init__(self, collector: TelemetryCollector, *, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.collector = collector
        self.pinned_conversation = ""
        self.include_subagents = True
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._report_requested = False
        self._thread: threading.Thread | None = None
        self.last_snapshot = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="agy-telemetry", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def refresh_now(self) -> None:
        self._wake.set()

    def request_report(self) -> None:
        self._report_requested = True
        self._wake.set()

    @classmethod
    def interval_for(cls, snapshot) -> float:
        """Poll fast only while a reply is streaming."""
        if snapshot is None:
            return cls.OFFLINE_INTERVAL
        return cls.RUNNING_INTERVAL if snapshot.running else cls.IDLE_INTERVAL

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                snapshot = self.collector.live_snapshot(self.pinned_conversation)
                self.last_snapshot = snapshot
                self.live_updated.emit(snapshot)
                if self._report_requested:
                    self._report_requested = False
                    report = self.collector.meter_report(
                        include_subagents=self.include_subagents,
                        pinned_id=self.pinned_conversation,
                    )
                    self.report_ready.emit(report)
            except Exception:  # never let telemetry kill the pet
                LOGGER.exception("telemetry poll failed")
            self._wake.wait(self.interval_for(self.last_snapshot))
            self._wake.clear()
