"""High-DPI Aware Screen Capture and Window Cropping Engine.

Provides non-intrusive capture of desktop screens, active foreground windows,
or specific application windows (Hermes CMS) without injecting DLLs or hooking
into target process memory.
"""

import ctypes
from ctypes import wintypes
import logging
import os
import platform
import re
from typing import Any, List, Optional, Tuple

from PIL import Image, ImageGrab

from app.core.config import HERMES_WINDOW_TITLE_PATTERNS

logger = logging.getLogger(__name__)

# DwmGetWindowAttribute constants
DWMWA_EXTENDED_FRAME_BOUNDS = 9


def init_dpi_awareness() -> bool:
    """Initialize Windows High-DPI awareness to prevent blurry scaling or coordinate drift."""
    if platform.system() != "Windows":
        return False

    # Attempt 1: Per-monitor DPI aware v2 (Windows 10 1607+)
    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        hr = shcore.SetProcessDpiAwareness(2)
        if hr == 0:
            logger.debug("DPI awareness: Per-Monitor DPI aware v2 set successfully.")
            return True
    except Exception:
        pass

    # Attempt 2: System DPI aware fallback (Windows Vista / 7 / 8)
    try:
        user32 = ctypes.windll.user32
        success = user32.SetProcessDPIAware()
        if success:
            logger.debug("DPI awareness: System DPI aware set successfully.")
            return True
    except Exception as e:
        logger.debug(f"Could not set DPI awareness: {e}")

    return False


# Execute DPI awareness initialization once on module import
init_dpi_awareness()


class ScreenGrabber:
    """Non-intrusive screen capture and window bounding box grabber."""

    def __init__(self) -> None:
        self._is_windows = platform.system() == "Windows"
        self._mock_image: Optional[Image.Image] = None

    def set_test_mock_image(self, image: Optional[Image.Image]) -> None:
        """Inject a mock image for headless environments or automated unit tests."""
        self._mock_image = image

    def capture_full_screen(self, all_screens: bool = True) -> Optional[Image.Image]:
        """Capture the entire virtual desktop spanning all monitors."""
        if self._mock_image is not None:
            return self._mock_image.copy()

        try:
            # PIL ImageGrab is non-intrusive and respects high DPI
            img = ImageGrab.grab(all_screens=all_screens)
            return img
        except Exception as e:
            logger.warning(f"capture_full_screen failed via ImageGrab: {e}")
            return self._capture_desktop_gdi()

    def _capture_desktop_gdi(self) -> Optional[Image.Image]:
        """Fallback desktop capture via Win32 GDI."""
        if not self._is_windows:
            return None

        try:
            import win32api
            import win32con
            import win32gui
            import win32ui

            hwnd = win32gui.GetDesktopWindow()
            left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
            top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
            width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
            height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)

            if width <= 0 or height <= 0:
                return None

            w_dc = win32gui.GetWindowDC(hwnd)
            dc_obj = win32ui.CreateDCFromHandle(w_dc)
            c_dc = dc_obj.CreateCompatibleDC()
            data_bitmap = win32ui.CreateBitmap()
            data_bitmap.CreateCompatibleBitmap(dc_obj, width, height)
            c_dc.SelectObject(data_bitmap)
            c_dc.BitBlt((0, 0), (width, height), dc_obj, (left, top), win32con.SRCCOPY)

            bmp_info = data_bitmap.GetInfo()
            bmp_str = data_bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGB",
                (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                bmp_str,
                "raw",
                "BGRX",
                0,
                1,
            )

            # Cleanup GDI handles
            dc_obj.DeleteDC()
            c_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, w_dc)
            win32gui.DeleteObject(data_bitmap.GetHandle())

            return img
        except Exception as e:
            logger.error(f"GDI desktop screen grab failed: {e}")
            return None

    def get_window_bounds(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """Get the true pixel bounding rectangle of a window (left, top, right, bottom).

        Uses DwmGetWindowAttribute to remove Windows 10/11 drop-shadow padding margins.
        """
        if not self._is_windows or not hwnd:
            return None

        # Try DWM extended frame bounds first for exact pixel bounds
        try:
            rect = wintypes.RECT()
            dwmapi = ctypes.windll.dwmapi
            hr = dwmapi.DwmGetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            if hr == 0:
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                if right > left and bottom > top:
                    return (left, top, right, bottom)
        except Exception:
            pass

        # Fallback to standard Win32 GetWindowRect
        try:
            import win32gui

            rect = win32gui.GetWindowRect(hwnd)
            if rect and rect[2] > rect[0] and rect[3] > rect[1]:
                return rect
        except Exception as e:
            logger.debug(f"Could not retrieve bounds for hwnd {hwnd}: {e}")

        return None

    def capture_window_hwnd(self, hwnd: int) -> Tuple[Optional[Image.Image], str]:
        """Capture a specific window by its Win32 HWND handle."""
        if self._mock_image is not None:
            return self._mock_image.copy(), "Mock Active Window"

        if not self._is_windows or not hwnd:
            return None, ""

        import win32gui

        try:
            title = win32gui.GetWindowText(hwnd) or f"HWND_{hwnd}"
            bounds = self.get_window_bounds(hwnd)
            if not bounds:
                return None, title

            left, top, right, bottom = bounds
            width = right - left
            height = bottom - top

            if width <= 10 or height <= 10:
                logger.warning(f"Window {title} has near-zero dimensions ({width}x{height})")
                return None, title

            # Grab via ImageGrab bounding box
            try:
                img = ImageGrab.grab(bbox=bounds, all_screens=True)
                return img, title
            except Exception:
                pass

            # Fallback: capture full screen and crop
            full_screen = self.capture_full_screen(all_screens=True)
            if full_screen:
                # Clamp coordinates to image dimensions
                w_full, h_full = full_screen.size
                c_left = max(0, min(left, w_full - 1))
                c_top = max(0, min(top, h_full - 1))
                c_right = max(c_left + 1, min(right, w_full))
                c_bottom = max(c_top + 1, min(bottom, h_full))
                cropped = full_screen.crop((c_left, c_top, c_right, c_bottom))
                return cropped, title

        except Exception as e:
            logger.error(f"Error capturing window hwnd {hwnd}: {e}")

        return None, ""

    def capture_active_window(self) -> Tuple[Optional[Image.Image], str]:
        """Capture the currently focused foreground window.

        If foreground window cannot be captured, gracefully falls back to full screen.
        """
        if self._mock_image is not None:
            return self._mock_image.copy(), "Mock Active Window"

        if not self._is_windows:
            full = self.capture_full_screen()
            return full, "Desktop"

        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                img, title = self.capture_window_hwnd(hwnd)
                if img:
                    return img, title

            # Fallback to full screen if no valid foreground window
            logger.debug("Active window grab returned empty, falling back to full desktop.")
            full = self.capture_full_screen()
            return full, "Desktop"
        except Exception as e:
            logger.warning(f"capture_active_window encountered error: {e}")
            full = self.capture_full_screen()
            return full, "Desktop"

    def find_hermes_windows(self) -> List[Tuple[int, str]]:
        """Locate all top-level windows matching Hermes CMS titles."""
        results: List[Tuple[int, str]] = []
        if not self._is_windows:
            return results

        import win32gui

        patterns = [re.compile(rf"(?i){re.escape(p)}") for p in HERMES_WINDOW_TITLE_PATTERNS]

        def _enum_handler(hwnd: int, extra: Any) -> None:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    for pat in patterns:
                        if pat.search(title):
                            results.append((hwnd, title))
                            break

        try:
            win32gui.EnumWindows(_enum_handler, None)
        except Exception as e:
            logger.debug(f"Window enumeration error: {e}")

        return results

    def capture_window_by_title_pattern(self, pattern: str) -> Tuple[Optional[Image.Image], str]:
        """Search for a window matching pattern regex and capture it."""
        if self._mock_image is not None:
            return self._mock_image.copy(), f"Mock Window ({pattern})"

        if not self._is_windows:
            return None, ""

        import win32gui

        regex = re.compile(rf"(?i){pattern}")
        target_hwnd: Optional[int] = None
        target_title = ""

        def _search_handler(hwnd: int, extra: Any) -> None:
            nonlocal target_hwnd, target_title
            if target_hwnd is not None:
                return
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and regex.search(title):
                    target_hwnd = hwnd
                    target_title = title

        try:
            win32gui.EnumWindows(_search_handler, None)
        except Exception:
            pass

        if target_hwnd:
            return self.capture_window_hwnd(target_hwnd)

        return None, ""

    def capture_region(self, bbox: Tuple[int, int, int, int]) -> Optional[Image.Image]:
        """Capture a designated rectangular screen region (left, top, right, bottom)."""
        if self._mock_image is not None:
            return self._mock_image.crop(bbox)

        try:
            return ImageGrab.grab(bbox=bbox, all_screens=True)
        except Exception:
            full = self.capture_full_screen()
            if full:
                return full.crop(bbox)
        return None
