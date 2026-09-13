"""Tests for Confirm Action Watcher and Target Window Pinning."""

import time
import pytest
from app.capture.confirm_watcher import ConfirmWatcher, ConfirmHotspot


class TestConfirmHotspot:
    def test_contains(self):
        h = ConfirmHotspot(rel_left=100, rel_top=50, rel_right=200, rel_bottom=90)
        assert h.contains(150, 70) is True
        assert h.contains(100, 50) is True
        assert h.contains(200, 90) is True
        assert h.contains(50, 70) is False
        assert h.contains(150, 100) is False


class TestConfirmWatcherLifecycle:
    def test_start_stop(self):
        watcher = ConfirmWatcher(delay_seconds=1.0)
        started = watcher.start()
        assert started is True
        assert watcher._running is True
        watcher.stop()
        assert watcher._running is False

    def test_set_target_window(self):
        watcher = ConfirmWatcher()
        watcher.set_target_window(12345, "Hermes CMS Main Window")
        assert watcher.target_hwnd == 12345
        assert watcher.target_title == "Hermes CMS Main Window"

        watcher.set_target_window(None)
        assert watcher.target_hwnd is None
        assert watcher.target_title == ""

    def test_set_hotspot(self):
        watcher = ConfirmWatcher()
        h = ConfirmHotspot(10, 20, 110, 60)
        watcher.set_hotspot(h)
        assert watcher.hotspot == h

        watcher.set_hotspot(None)
        assert watcher.hotspot is None

    def test_trigger_confirm_callback_and_debounce(self):
        triggered_delays = []

        def on_triggered(delay: float):
            triggered_delays.append(delay)

        watcher = ConfirmWatcher(
            on_confirm_triggered=on_triggered,
            delay_seconds=1.5,
            debounce_seconds=0.5,
        )

        # First trigger
        watcher._trigger_confirm("Test Key")
        assert len(triggered_delays) == 1
        assert triggered_delays[0] == 1.5

        # Immediate second trigger within debounce window should be ignored
        watcher._trigger_confirm("Test Mouse")
        assert len(triggered_delays) == 1

        # Wait past debounce window
        time.sleep(0.55)
        watcher._trigger_confirm("Test Mouse After Debounce")
        assert len(triggered_delays) == 2

    def test_alt_f_shortcut_trigger(self):
        triggered_sources = []

        def on_triggered(delay: float):
            triggered_sources.append(delay)

        watcher = ConfirmWatcher(
            on_confirm_triggered=on_triggered,
            delay_seconds=1.0,
            debounce_seconds=0.1,
        )
        watcher._trigger_confirm("Alt+F")
        assert len(triggered_sources) == 1
        assert triggered_sources[0] == 1.0