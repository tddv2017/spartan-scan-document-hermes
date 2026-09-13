"""User Interface Subsystem for Hermes Vision Extractor.

Provides the floating widget overlay for one-click capture,
the session manager window for AWB record curation, and modal dialogs
for record editing and PDF generation/printing.
"""

from app.ui.overlay import FloatingOverlay
from app.ui.session_window import SessionManagerWindow

__all__ = [
    "FloatingOverlay",
    "SessionManagerWindow",
]
