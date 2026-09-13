"""Screen capture and window cropping subsystem.

Provides High-DPI aware screen capture, foreground window detection,
and window bounds cropping without interfering with target applications.
"""

from app.capture.screen_grabber import ScreenGrabber

__all__ = ["ScreenGrabber"]
