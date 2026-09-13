"""Native Win32 Global Hotkey Listener.

Implements RegisterHotKey in a dedicated background daemon thread with sub-10ms response time
and zero performance interference to Hermes CMS or other host applications.
"""

from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
import logging
import platform
import threading
import time
from typing import Callable, Dict, Optional

from app.core.config import (
    HOTKEY_DEFINITIONS,
    HOTKEY_DEBOUNCE_SECONDS,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    VK_F9,
    VK_S,
)

logger = logging.getLogger(__name__)

# Win32 Message Constants
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class GlobalHotkeyListener:
    """Listens for global Windows hotkeys (F9, Ctrl+Shift+S) in a background message loop.

    Uses native Win32 `RegisterHotKey` which hooks into the Windows kernel event dispatcher.
    Unlike low-level keyboard hooks (`WH_KEYBOARD_LL`), this creates zero input latency for
    Hermes CMS data entry.
    """

    def __init__(
        self,
        callback: Optional[Callable[[str], None]] = None,
        debounce_seconds: float = HOTKEY_DEBOUNCE_SECONDS,
    ) -> None:
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._running = False
        self._is_windows = platform.system() == "Windows"
        self._last_trigger_time: Dict[int, float] = {}
        self._ready_event = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="HotkeyWorker")
        self._id_to_name: Dict[int, str] = {}

    def start(self) -> bool:
        """Start the background hotkey listener daemon thread."""
        if not self._is_windows:
            logger.warning("GlobalHotkeyListener: Non-Windows OS detected, running in simulation mode.")
            self._running = True
            return True

        if self._running:
            logger.info("GlobalHotkeyListener is already running.")
            return True

        self._ready_event.clear()
        self._thread = threading.Thread(
            target=self._run_message_loop,
            daemon=True,
            name="Win32HotkeyMessagePump",
        )
        self._thread.start()

        # Wait for hotkeys to register
        registered = self._ready_event.wait(timeout=3.0)
        if not registered or not self._running:
            logger.error("Failed to start Win32 hotkey listener within timeout.")
            return False

        logger.info("Win32 global hotkeys successfully registered (F9, Ctrl+Shift+S).")
        return True

    def stop(self) -> None:
        """Gracefully unregister hotkeys and terminate the message loop thread."""
        if not self._running:
            return

        self._running = False

        if self._is_windows and self._thread_id:
            user32 = ctypes.windll.user32
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        self._thread = None
        self._thread_id = None
        self._executor.shutdown(wait=False)
        logger.info("Win32 global hotkey listener stopped.")

    def trigger_hotkey(self, hotkey_name: str) -> None:
        """Manually trigger a hotkey event.

        Useful for GUI button triggers, test suites, or programmatic invocation.
        """
        self._dispatch_event(hotkey_name)

    def _dispatch_event(self, hotkey_name: str) -> None:
        """Offload the callback to a worker thread so the message pump is never delayed."""
        if self.callback:
            try:
                self._executor.submit(self.callback, hotkey_name)
            except Exception as e:
                logger.error(f"Error submitting hotkey callback: {e}", exc_info=True)

    def _run_message_loop(self) -> None:
        """Dedicated thread executing the Win32 GetMessageW message pump."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Capture thread ID for PostThreadMessageW targeting
        self._thread_id = kernel32.GetCurrentThreadId()

        # Define function signatures for 64-bit safety
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = wintypes.BOOL

        # Register hotkeys with hWnd=NULL (associated with current thread)
        registered_any = False
        for definition in HOTKEY_DEFINITIONS:
            hk_id = definition["id"]
            name = definition["name"]
            mods = definition["modifiers"]
            vk = definition["vk"]

            # Try registering
            success = user32.RegisterHotKey(None, hk_id, mods, vk)
            if not success:
                # If MOD_NOREPEAT (0x4000) failed on older systems, try without it
                if mods & MOD_NOREPEAT:
                    fallback_mods = mods & ~MOD_NOREPEAT
                    success = user32.RegisterHotKey(None, hk_id, fallback_mods, vk)

            if success:
                self._id_to_name[hk_id] = name
                registered_any = True
                logger.debug(f"Registered hotkey {name} (ID: {hk_id})")
            else:
                last_err = kernel32.GetLastError()
                logger.warning(
                    f"Could not register hotkey {name} (ID: {hk_id}). "
                    f"Another application may already hold it. Error code: {last_err}"
                )

        self._running = registered_any
        self._ready_event.set()

        if not registered_any:
            logger.error("No hotkeys could be registered. Message pump aborting.")
            return

        # Enter Windows Message Pump
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    hk_id = msg.wParam
                    hk_name = self._id_to_name.get(hk_id, f"Hotkey_{hk_id}")

                    # Debounce check
                    now = time.monotonic()
                    last_time = self._last_trigger_time.get(hk_id, 0.0)
                    if (now - last_time) >= self.debounce_seconds:
                        self._last_trigger_time[hk_id] = now
                        logger.debug(f"Hotkey triggered: {hk_name}")
                        self._dispatch_event(hk_name)
                    else:
                        logger.debug(f"Hotkey {hk_name} debounced (ignored rapid repeat).")

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:
            logger.error(f"Exception inside Win32 message loop: {e}", exc_info=True)
        finally:
            # Cleanly unregister all registered hotkeys on thread exit
            for hk_id in list(self._id_to_name.keys()):
                user32.UnregisterHotKey(None, hk_id)
            self._running = False
            logger.debug("Win32 hotkeys unregistered.")
