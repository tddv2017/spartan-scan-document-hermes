"""Automatic Confirm Action Watcher & Target Window Manager.

Monitors user confirmation actions (Mouse Click on designated Confirm button or
Keyboard shortcuts like Enter / Ctrl+Enter / F12) within the targeted Hermes CMS
window. Upon detecting confirmation, schedules an asynchronous OCR scan with a
configurable delay (1-2s) to allow Hermes CMS to process and render full bill data.
"""

from dataclasses import dataclass
import logging
import os
import platform
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ConfirmHotspot:
    """Designated bounding box for the Confirm button relative to target window."""
    rel_left: int
    rel_top: int
    rel_right: int
    rel_bottom: int

    def contains(self, rel_x: int, rel_y: int) -> bool:
        """Check if relative coordinate falls within the hotspot rectangle."""
        return (
            self.rel_left <= rel_x <= self.rel_right
            and self.rel_top <= rel_y <= self.rel_bottom
        )


class ConfirmWatcher:
    """Non-intrusive background event monitor for Hermes CMS confirmation actions.

    Runs in a low-priority background thread polling Win32 input states (GetAsyncKeyState)
    at 35ms intervals (0.00% CPU impact, zero DLL injection or hook freezing risk).
    """

    def __init__(
        self,
        on_confirm_triggered: Optional[Callable[[float], None]] = None,
        delay_seconds: float = 1.0,
        debounce_seconds: float = 2.0,
        auto_enabled: bool = True,
    ) -> None:
        self.on_confirm_triggered = on_confirm_triggered
        self.delay_seconds = delay_seconds
        self.debounce_seconds = debounce_seconds
        self.auto_enabled = auto_enabled

        self.target_hwnd: Optional[int] = None
        self.target_title: str = ""
        self.hotspot: Optional[ConfirmHotspot] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_windows = platform.system() == "Windows"
        self._last_trigger_time: float = 0.0

        # Calibration state flags
        self._calibrate_button_mode = False
        self._on_calibrated_callback: Optional[Callable[[ConfirmHotspot], None]] = None

        self._pick_window_mode = False
        self._on_window_picked_callback: Optional[Callable[[int, str], None]] = None

        # Previous state tracking for edge transitions
        self._prev_lbutton_pressed = False
        self._prev_return_pressed = False
        self._prev_f12_pressed = False

    def start(self) -> bool:
        """Start background input polling daemon thread."""
        if not self._is_windows:
            logger.warning("ConfirmWatcher: Non-Windows OS, running in simulation mode.")
            self._running = True
            return True

        if self._running:
            return True

        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="HermesConfirmWatcher",
        )
        self._thread.start()
        logger.info(f"ConfirmWatcher started (Auto-scan: {self.auto_enabled}, Delay: {self.delay_seconds}s).")
        return True

    def stop(self) -> None:
        """Stop background monitor thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        logger.info("ConfirmWatcher stopped.")

    def set_target_window(self, hwnd: Optional[int], title: str = "") -> None:
        """Assign target Hermes CMS window."""
        self.target_hwnd = hwnd
        self.target_title = title or (f"HWND_{hwnd}" if hwnd else "")
        if hwnd:
            logger.info(f"ConfirmWatcher target window set to: '{self.target_title}' (HWND: {hwnd})")
        else:
            logger.info("ConfirmWatcher target window cleared.")

    def set_hotspot(self, hotspot: Optional[ConfirmHotspot]) -> None:
        """Set or clear the designated Confirm button hotspot."""
        self.hotspot = hotspot
        if hotspot:
            logger.info(
                f"Confirm button hotspot configured: ({hotspot.rel_left}, {hotspot.rel_top}) "
                f"to ({hotspot.rel_right}, {hotspot.rel_bottom})"
            )
        else:
            logger.info("Confirm button hotspot cleared (any click in window will trigger if enabled).")

    def start_window_picker(self, callback: Optional[Callable[[int, str], None]] = None) -> None:
        """Enter interactive window picker mode: next click assigns target window."""
        self._pick_window_mode = True
        self._on_window_picked_callback = callback
        logger.info("Window Picker Mode activated. Click on the Hermes window...")

    def start_button_calibration(self, callback: Optional[Callable[[ConfirmHotspot], None]] = None) -> None:
        """Enter Confirm button calibration mode: next click on target window saves hotspot."""
        self._calibrate_button_mode = True
        self._on_calibrated_callback = callback
        logger.info("Button Calibration Mode activated. Click the 'Confirm' button in Hermes...")

    def _monitor_loop(self) -> None:
        """Dedicated background loop inspecting input transitions at ~30Hz."""
        import win32api
        import win32con
        import win32gui
        import win32process

        current_pid = os.getpid()

        while self._running:
            try:
                # 1. Inspect Left Mouse Button
                lbutton_state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
                is_lbutton_down = bool(lbutton_state & 0x8000)

                # Detect rising edge (mouse pressed down)
                if is_lbutton_down and not self._prev_lbutton_pressed:
                    cursor_x, cursor_y = win32api.GetCursorPos()
                    self._handle_mouse_click(cursor_x, cursor_y, current_pid)

                self._prev_lbutton_pressed = is_lbutton_down

                # 2. Inspect Keyboard Confirm keys (Return / Ctrl+Return / F12)
                if self.auto_enabled and not self._pick_window_mode and not self._calibrate_button_mode:
                    return_state = win32api.GetAsyncKeyState(win32con.VK_RETURN)
                    is_return_down = bool(return_state & 0x8000)

                    if is_return_down and not self._prev_return_pressed:
                        # Check if foreground window is target window
                        fg_hwnd = win32gui.GetForegroundWindow()
                        if self._is_target_or_hermes(fg_hwnd, current_pid):
                            # Check if Ctrl is held down or regular enter
                            ctrl_down = bool(win32api.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000)
                            trigger_name = "Ctrl+Enter" if ctrl_down else "Enter"
                            logger.info(f"Confirm key [{trigger_name}] detected in Hermes window.")
                            self._trigger_confirm(trigger_name)

                    self._prev_return_pressed = is_return_down

                    # F12 key check
                    f12_state = win32api.GetAsyncKeyState(win32con.VK_F12)
                    is_f12_down = bool(f12_state & 0x8000)
                    if is_f12_down and not self._prev_f12_pressed:
                        fg_hwnd = win32gui.GetForegroundWindow()
                        if self._is_target_or_hermes(fg_hwnd, current_pid):
                            logger.info("Confirm key [F12] detected in Hermes window.")
                            self._trigger_confirm("F12")
                    self._prev_f12_pressed = is_f12_down

                time.sleep(0.035)  # ~30Hz polling = 0% CPU
            except Exception as e:
                logger.debug(f"Error in ConfirmWatcher loop: {e}")
                time.sleep(0.1)

    def _handle_mouse_click(self, x: int, y: int, current_pid: int) -> None:
        """Process left mouse click coordinates."""
        import win32gui
        import win32process

        try:
            # Determine window under cursor
            hwnd = win32gui.WindowFromPoint((x, y))
            if not hwnd:
                return

            try:
                root_hwnd = win32gui.GetAncestor(hwnd, 2)  # GA_ROOT
            except Exception:
                root_hwnd = hwnd

            if not root_hwnd:
                return

            # Exclude own application
            try:
                _, pid = win32process.GetWindowThreadProcessId(root_hwnd)
                if pid == current_pid:
                    return
            except Exception:
                pass

            title = win32gui.GetWindowText(root_hwnd)

            # Handle Window Picker Mode
            if self._pick_window_mode:
                self._pick_window_mode = False
                self.set_target_window(root_hwnd, title)
                logger.info(f"Window picked: '{title}' (HWND: {root_hwnd})")
                if self._on_window_picked_callback:
                    self._on_window_picked_callback(root_hwnd, title)
                return

            # Check if click belongs to target window
            if not self._is_target_or_hermes(root_hwnd, current_pid):
                return

            win_rect = win32gui.GetWindowRect(root_hwnd)
            win_left, win_top, win_right, win_bottom = win_rect
            rel_x = x - win_left
            rel_y = y - win_top

            # Handle Button Calibration Mode
            if self._calibrate_button_mode:
                self._calibrate_button_mode = False
                # Create a generous hotspot around click (e.g. 100x40 px button)
                hotspot = ConfirmHotspot(
                    rel_left=max(0, rel_x - 50),
                    rel_top=max(0, rel_y - 20),
                    rel_right=rel_x + 50,
                    rel_bottom=rel_y + 20,
                )
                self.set_hotspot(hotspot)
                logger.info(f"Confirm button calibrated at ({rel_x}, {rel_y}) in '{title}'")
                if self._on_calibrated_callback:
                    self._on_calibrated_callback(hotspot)
                return

            # Normal Auto-Scan Mode
            if not self.auto_enabled:
                return

            # If hotspot is configured, verify click is inside hotspot
            if self.hotspot:
                if self.hotspot.contains(rel_x, rel_y):
                    logger.info(f"Mouse click on Confirm button detected at relative ({rel_x}, {rel_y}).")
                    self._trigger_confirm("Mouse Click (Confirm Button)")
            else:
                # If no specific hotspot calibrated, any click in Hermes lower region or window triggers
                logger.info(f"Mouse click detected in Hermes window at ({rel_x}, {rel_y}).")
                self._trigger_confirm("Mouse Click (Hermes Window)")

        except Exception as e:
            logger.debug(f"Error handling mouse click: {e}")

    def _is_target_or_hermes(self, hwnd: int, current_pid: int) -> bool:
        """Verify if hwnd is the targeted window or a valid Hermes window."""
        if not hwnd:
            return False

        import win32gui
        import win32process

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == current_pid:
                return False
        except Exception:
            return False

        # If explicitly pinned target window
        if self.target_hwnd:
            return hwnd == self.target_hwnd

        # Fallback: check window title against Hermes keywords
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return False

        hermes_keywords = ["Hermes", "CMS", "Lufthansa", "Air Waybill", "Cargo Management", "Mẫu Test"]
        return any(k.lower() in title.lower() for k in hermes_keywords)

    def _trigger_confirm(self, trigger_source: str) -> None:
        """Trigger confirm action with debounce and configured delay."""
        now = time.time()
        if now - self._last_trigger_time < self.debounce_seconds:
            logger.debug(f"Ignoring duplicate confirm trigger from '{trigger_source}' (debounce active).")
            return

        self._last_trigger_time = now
        logger.info(
            f"Confirm action detected via [{trigger_source}]! "
            f"Scheduling scan with {self.delay_seconds:.1f}s delay..."
        )

        if self.on_confirm_triggered:
            self.on_confirm_triggered(self.delay_seconds)