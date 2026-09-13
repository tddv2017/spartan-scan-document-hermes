"""Application configuration, constants, hotkey definitions, and system font mappings.

Hermes Vision Extractor - Core Configuration Subsystem.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, List

# -------------------------------------------------------------------------
# Application Metadata
# -------------------------------------------------------------------------
APP_NAME = "Hermes Vision Extractor"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Lufthansa Cargo Hermes CMS Screen Vision & OCR Extraction System"

# -------------------------------------------------------------------------
# Airline Domain Standards (IATA Resolution 600a / 606)
# -------------------------------------------------------------------------
DEFAULT_AIRLINE_PREFIX = "020"
DEFAULT_AIRLINE_NAME = "Lufthansa Cargo"

# Known Airline 3-digit prefix mapping in Vietnam cargo terminals (NCTS, ACSC, TCS)
AIRLINE_PREFIX_MAP: Dict[str, str] = {
    "020": "Lufthansa Cargo",
    "738": "Vietnam Airlines",
    "160": "Cathay Pacific",
    "016": "United Airlines",
    "618": "Singapore Airlines",
    "074": "KLM Royal Dutch Airlines",
    "057": "Air France",
    "176": "Emirates",
    "180": "Korean Air",
    "205": "All Nippon Airways",
    "695": "EVA Air",
    "406": "UPS Airlines",
    "023": "FedEx Express",
    "297": "China Airlines",
    "131": "Japan Airlines",
    "988": "Asiana Airlines",
    "843": "Vietjet Air",
    "044": "Cargolux Airlines",
}

# -------------------------------------------------------------------------
# Win32 Hotkey Definitions & Virtual Key Constants
# -------------------------------------------------------------------------
# Modifier flags for user32.RegisterHotKey
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Virtual Key Codes
VK_F9 = 0x78
VK_S = 0x53

# Hotkey action identifiers
HOTKEY_ID_F9 = 1001
HOTKEY_ID_CTRL_SHIFT_S = 1002

HOTKEY_DEFINITIONS = [
    {
        "id": HOTKEY_ID_F9,
        "name": "F9",
        "modifiers": MOD_NOREPEAT,
        "vk": VK_F9,
        "description": "Trigger instant screen capture and OCR analysis",
    },
    {
        "id": HOTKEY_ID_CTRL_SHIFT_S,
        "name": "Ctrl+Shift+S",
        "modifiers": MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
        "vk": VK_S,
        "description": "Trigger instant screen capture and OCR analysis",
    },
]

HOTKEY_DEBOUNCE_SECONDS = 0.4

# -------------------------------------------------------------------------
# System Fonts & Vietnamese Typography Paths
# -------------------------------------------------------------------------
WINDOWS_FONTS_DIR = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"

DEFAULT_FONT_NAME = "Arial"
DEFAULT_FONT_PATH = str(WINDOWS_FONTS_DIR / "arial.ttf")
DEFAULT_FONT_BOLD_PATH = str(WINDOWS_FONTS_DIR / "arialbd.ttf")

FALLBACK_FONT_PATHS: List[str] = [
    str(WINDOWS_FONTS_DIR / "arial.ttf"),
    str(WINDOWS_FONTS_DIR / "tahoma.ttf"),
    str(WINDOWS_FONTS_DIR / "segoeui.ttf"),
    str(WINDOWS_FONTS_DIR / "times.ttf"),
]

# -------------------------------------------------------------------------
# Vision & OCR Constants
# -------------------------------------------------------------------------
PREPROCESS_SCALE_FACTOR = 2.0
OCR_PRIMARY_ENGINE = "rapidocr"
OCR_FALLBACK_ENGINE = "windows_media"
OCR_MIN_CONFIDENCE = 0.50

# Critical business flag
FLAG_ALL_IMP_ACC_HAWB = "ALL IMP/ACC HAWB"

# Hermes CMS Window Title Patterns for targeted window capture
HERMES_WINDOW_TITLE_PATTERNS = [
    "Hermes",
    "CMS",
    "Lufthansa",
    "AWB Maintenance",
    "AWB Details",
    "Shipment Maintenance",
    "Cargo Management",
]


@dataclass
class Config:
    """Runtime application configuration."""

    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    default_prefix: str = DEFAULT_AIRLINE_PREFIX
    default_airline: str = DEFAULT_AIRLINE_NAME
    scale_factor: float = PREPROCESS_SCALE_FACTOR
    min_confidence: float = OCR_MIN_CONFIDENCE
    primary_engine: str = OCR_PRIMARY_ENGINE
    fallback_engine: str = OCR_FALLBACK_ENGINE
    font_path: str = DEFAULT_FONT_PATH
    font_bold_path: str = DEFAULT_FONT_BOLD_PATH
    debounce_seconds: float = HOTKEY_DEBOUNCE_SECONDS
    prefix_map: Dict[str, str] = field(default_factory=lambda: dict(AIRLINE_PREFIX_MAP))

    def get_airline_name(self, prefix: str) -> str:
        """Resolve airline name from 3-digit prefix."""
        clean_prefix = prefix.strip()
        return self.prefix_map.get(clean_prefix, f"Unknown Carrier ({clean_prefix})")

    def validate_font_path(self) -> str:
        """Return a verified accessible TrueType font path supporting Vietnamese UTF-8."""
        if os.path.exists(self.font_path):
            return self.font_path
        for candidate in FALLBACK_FONT_PATHS:
            if os.path.exists(candidate):
                return candidate
        return self.font_path
