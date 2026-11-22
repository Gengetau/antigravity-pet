"""Keep the test suite away from the user's real Antigravity session.

PetWindow starts a telemetry thread that talks to the local language server.
Tests flip the default off; tests that need telemetry build a collector on a
temporary directory explicitly.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _no_live_telemetry(monkeypatch, tmp_path):
    from settings import config

    agy = dict(config.DEFAULT_CONFIG["agy"])
    agy["telemetry_enabled"] = False
    agy["use_language_server"] = False
    monkeypatch.setitem(config.DEFAULT_CONFIG, "agy", agy)
    yield
