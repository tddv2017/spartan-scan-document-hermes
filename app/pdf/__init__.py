"""PDF Generation Subsystem for Hermes Vision Extractor.

Provides standardized ISO A4 Cargo Handover PDF report generation,
Vietnamese UTF-8 TrueType typography embedding, document preview,
and direct printing utilities.
"""

from app.pdf.generator import (
    generate_cargo_handover_pdf,
    preview_pdf,
    print_pdf,
)

__all__ = [
    "generate_cargo_handover_pdf",
    "preview_pdf",
    "print_pdf",
]
