"""Unit tests for Close Utility.

These tests cover the platform-independent logic (state management,
executable path extraction, close-count detection) without requiring
Windows, a real registry, or a display.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to import the module without Windows / GUI dependencies
# ---------------------------------------------------------------------------
import sys
import types


def _patch_unavailable_modules():
    """Insert stub modules so the import succeeds on any platform."""
    if "winreg" not in sys.modules:
        sys.modules["winreg"] = None  # type: ignore[assignment]

    for name in ("psutil", "pystray"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    if "PIL" not in sys.modules:
        pil = types.ModuleType("PIL")
        pil.Image = MagicMock()  # type: ignore[attr-defined]
        pil.ImageDraw = MagicMock()  # type: ignore[attr-defined]
        sys.modules["PIL"] = pil
        sys.modules["PIL.Image"] = pil.Image
        sys.modules["PIL.ImageDraw"] = pil.ImageDraw

    # Stub tkinter if not available (e.g. headless CI)
    if "tkinter" not in sys.modules:
        tkmod = types.ModuleType("tkinter")
        tkmod.Tk = MagicMock()  # type: ignore[attr-defined]
        tkmod.messagebox = MagicMock()  # type: ignore[attr-defined]
        sys.modules["tkinter"] = tkmod
        sys.modules["tkinter.messagebox"] = tkmod.messagebox


_patch_unavailable_modules()

# Now safe to import
import close_utility  # noqa: E402
from close_utility import (  # noqa: E402
    CLOSE_THRESHOLD,
    ProcessMonitor,
    StartupAppsReader,
    StateManager,
)


# ===========================================================================
# StateManager
# ===========================================================================
class TestStateManager:
    def test_initial_state_empty(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        assert sm.get_close_count("app.exe") == 0
        assert not sm.is_ignored("app.exe")

    def test_increment_close_count(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        assert sm.increment_close_count("app.exe") == 1
        assert sm.increment_close_count("app.exe") == 2
        assert sm.get_close_count("app.exe") == 2

    def test_reset_close_count(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.increment_close_count("app.exe")
        sm.increment_close_count("app.exe")
        sm.reset_close_count("app.exe")
        assert sm.get_close_count("app.exe") == 0

    def test_add_ignored(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.add_ignored("app.exe")
        assert sm.is_ignored("app.exe")
        assert not sm.is_ignored("other.exe")

    def test_add_ignored_is_idempotent(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.add_ignored("app.exe")
        sm.add_ignored("app.exe")
        assert sm._data["ignored"].count("app.exe") == 1

    def test_case_insensitive(self, tmp_path):
        sm = StateManager(tmp_path / "state.json")
        sm.increment_close_count("App.EXE")
        assert sm.get_close_count("app.exe") == 1
        sm.add_ignored("DISCORD.EXE")
        assert sm.is_ignored("discord.exe")

    def test_persists_to_disk(self, tmp_path):
        path = tmp_path / "state.json"
        sm = StateManager(path)
        sm.increment_close_count("notepad.exe")
        sm.add_ignored("spotify.exe")

        # Reload from disk
        sm2 = StateManager(path)
        assert sm2.get_close_count("notepad.exe") == 1
        assert sm2.is_ignored("spotify.exe")

    def test_corrupt_file_falls_back_to_empty(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not valid json", encoding="utf-8")
        sm = StateManager(path)
        assert sm.get_close_count("app.exe") == 0


# ===========================================================================
# StartupAppsReader._extract_exe_path
# ===========================================================================
class TestExtractExePath:
    def test_plain_path(self):
        assert StartupAppsReader._extract_exe_path(r"C:\Program Files\App\app.exe") == r"C:\Program Files\App\app.exe"

    def test_quoted_path(self):
        result = StartupAppsReader._extract_exe_path(r'"C:\Program Files\App\app.exe" --minimized')
        assert result == r"C:\Program Files\App\app.exe"

    def test_path_with_args(self):
        result = StartupAppsReader._extract_exe_path(r"C:\tools\app.exe --flag value")
        assert result == r"C:\tools\app.exe"

    def test_empty_string(self):
        assert StartupAppsReader._extract_exe_path("") is None

    def test_whitespace_only(self):
        assert StartupAppsReader._extract_exe_path("   ") is None

    def test_quoted_empty(self):
        # Opening quote but no closing quote — falls back to split
        result = StartupAppsReader._extract_exe_path('"no-closing-quote')
        assert result == '"no-closing-quote'

    def test_single_quoted_exe(self):
        result = StartupAppsReader._extract_exe_path('"C:\\app.exe"')
        assert result == "C:\\app.exe"


# ===========================================================================
# ProcessMonitor — close detection logic
# ===========================================================================
class TestProcessMonitorTick:
    """Tests for the _tick() logic using a fake startup-apps reader and psutil."""

    def _make_monitor(self, state, callback):
        mon = ProcessMonitor(state=state, on_threshold_reached=callback, interval=9999)
        return mon

    def test_first_close_increments_counter(self, tmp_path):
        state = StateManager(tmp_path / "s.json")
        triggered = []

        startup = {"notepad.exe": {"display_name": "Notepad", "exe_path": "notepad.exe"}}

        mon = self._make_monitor(state, triggered.append)

        # Simulate app was running
        mon._prev_pids = {"notepad.exe": {1234}}

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()

        assert state.get_close_count("notepad.exe") == 1
        assert len(triggered) == 0

    def test_threshold_triggers_callback(self, tmp_path):
        state = StateManager(tmp_path / "s.json")
        # Pre-set count to threshold - 1
        for _ in range(CLOSE_THRESHOLD - 1):
            state.increment_close_count("notepad.exe")

        triggered = []
        startup = {"notepad.exe": {"display_name": "Notepad", "exe_path": "notepad.exe"}}
        mon = self._make_monitor(state, triggered.append)
        mon._prev_pids = {"notepad.exe": {1234}}

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()

        assert state.get_close_count("notepad.exe") == CLOSE_THRESHOLD
        assert len(triggered) == 1
        assert triggered[0]["display_name"] == "Notepad"

    def test_ignored_app_not_counted(self, tmp_path):
        state = StateManager(tmp_path / "s.json")
        state.add_ignored("notepad.exe")
        triggered = []

        startup = {"notepad.exe": {"display_name": "Notepad", "exe_path": "notepad.exe"}}
        mon = self._make_monitor(state, triggered.append)
        mon._prev_pids = {"notepad.exe": {1234}}

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()

        assert state.get_close_count("notepad.exe") == 0
        assert len(triggered) == 0

    def test_app_not_in_startup_not_counted(self, tmp_path):
        state = StateManager(tmp_path / "s.json")
        triggered = []

        # Not in startup apps
        startup: dict = {}
        mon = self._make_monitor(state, triggered.append)
        mon._prev_pids = {"notepad.exe": {1234}}

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()

        assert state.get_close_count("notepad.exe") == 0

    def test_still_running_app_not_counted(self, tmp_path):
        state = StateManager(tmp_path / "s.json")
        triggered = []

        startup = {"notepad.exe": {"display_name": "Notepad", "exe_path": "notepad.exe"}}
        mon = self._make_monitor(state, triggered.append)
        mon._prev_pids = {"notepad.exe": {1234}}

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            # App is still running
            with patch.object(mon, "_get_current_pids", return_value={"notepad.exe": {1234}}):
                mon._tick()

        assert state.get_close_count("notepad.exe") == 0

    def test_no_double_popup_while_pending(self, tmp_path):
        """Once an app is pending (popup shown), closing it again must not trigger another popup."""
        state = StateManager(tmp_path / "s.json")
        for _ in range(CLOSE_THRESHOLD - 1):
            state.increment_close_count("notepad.exe")

        triggered = []
        startup = {"notepad.exe": {"display_name": "Notepad", "exe_path": "notepad.exe"}}
        mon = self._make_monitor(state, triggered.append)
        mon._prev_pids = {"notepad.exe": {1234}}

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()  # Should trigger
                mon._prev_pids = {"notepad.exe": {9999}}  # App "runs again"
                mon._tick()  # Closed again — still pending, must NOT trigger twice
                mon._prev_pids = {"notepad.exe": {8888}}
                mon._tick()

        assert len(triggered) == 1  # Only triggered once

    def test_clear_pending_allows_future_trigger(self, tmp_path):
        state = StateManager(tmp_path / "s.json")
        for _ in range(CLOSE_THRESHOLD - 1):
            state.increment_close_count("notepad.exe")

        triggered = []
        startup = {"notepad.exe": {"display_name": "Notepad", "exe_path": "notepad.exe"}}
        mon = self._make_monitor(state, triggered.append)
        mon._prev_pids = {"notepad.exe": {1234}}

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()  # First trigger

        assert len(triggered) == 1

        # Simulate user dismissed popup: counter reset, pending cleared
        state.reset_close_count("notepad.exe")
        mon.clear_pending("notepad.exe")

        # App runs CLOSE_THRESHOLD more times
        for _ in range(CLOSE_THRESHOLD - 1):
            state.increment_close_count("notepad.exe")

        mon._prev_pids = {"notepad.exe": {5678}}
        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()  # Should trigger again

        assert len(triggered) == 2

    def test_prev_pids_empty_no_close_detected(self, tmp_path):
        """If app was not seen running before, closing should not count."""
        state = StateManager(tmp_path / "s.json")
        triggered = []

        startup = {"notepad.exe": {"display_name": "Notepad", "exe_path": "notepad.exe"}}
        mon = self._make_monitor(state, triggered.append)
        mon._prev_pids = {"notepad.exe": set()}  # empty means we never saw it running

        with patch.object(StartupAppsReader, "get_startup_apps", return_value=startup):
            with patch.object(mon, "_get_current_pids", return_value={}):
                mon._tick()

        assert state.get_close_count("notepad.exe") == 0


# ===========================================================================
# ProcessMonitor — start / stop
# ===========================================================================
class TestProcessMonitorStartStop:
    def test_start_and_stop(self, tmp_path):
        state = StateManager(tmp_path / "s.json")
        mon = ProcessMonitor(state=state, on_threshold_reached=lambda _: None, interval=0.05)

        with patch.object(StartupAppsReader, "get_startup_apps", return_value={}):
            mon.start()
            time.sleep(0.15)
            mon.stop()

        # Thread should finish shortly after stop()
        if mon._thread:
            mon._thread.join(timeout=1.0)
            assert not mon._thread.is_alive()
