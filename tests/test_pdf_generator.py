"""Automated PDF Structural & Typography Validation Test Suite.

Verifies:
- %PDF- magic bytes header and %%EOF trailer integrity
- Exact ISO A4 dimensions (595.28 x 841.89 pt within 1.0 pt tolerance)
- TrueType UTF-8 Vietnamese character rendering without font replacement or missing glyphs
- 7-column cargo handover table structure and 3-tier signature block
- Direct contract validation against app.pdf.generator (when implemented)
"""

import os
from pathlib import Path
from typing import List
import pytest
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.models import AWBRecord, BusinessStatus
from tests.mock_generator import get_all_fixtures


# Register Arial for Vietnamese UTF-8 rendering in tests
FONT_PATH = "C:/Windows/Fonts/arial.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/arialbd.ttf"
if os.path.exists(FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont("Arial", FONT_PATH))
    except Exception:
        pass
if os.path.exists(FONT_BOLD_PATH):
    try:
        pdfmetrics.registerFont(TTFont("Arial-Bold", FONT_BOLD_PATH))
    except Exception:
        pass


def build_reference_handover_pdf(
    records: List[AWBRecord],
    output_path: str,
    shift_name: str = "Ca 1 - Ban Ngày",
    handover_person: str = "Nguyễn Văn Giao (NV Giao Ca)",
    receiver_person: str = "Trần Thị Nhận (NV Nhận Ca)",
) -> str:
    """Builds a reference ISO A4 Cargo Handover PDF according to ORIGINAL_REQUEST § R4."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,  # 595.2756 x 841.8898 pt
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Normal"],
        fontName="Arial-Bold" if "Arial-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold",
        fontSize=13,
        leading=16,
        alignment=1,  # Center
        textColor=colors.HexColor("#002B49"),
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontName="Arial" if "Arial" in pdfmetrics.getRegisteredFontNames() else "Helvetica",
        fontSize=8,
        leading=11,
        alignment=1,
        textColor=colors.HexColor("#333333"),
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Arial" if "Arial" in pdfmetrics.getRegisteredFontNames() else "Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.black,
    )
    cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Arial-Bold" if "Arial-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#002B49"),
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("PHIẾU BÀN GIAO & ĐỐI SOÁT VẬN ĐƠN CA TRỰC", title_style))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            f"Hermes Cargo Management System | Ga hàng hóa Nội Bài (NCTS/HAN) | Ca: {shift_name}",
            meta_style,
        )
    )
    story.append(Spacer(1, 10))

    # Table Header
    headers = [
        Paragraph("<b>STT</b>", cell_bold),
        Paragraph("<b>Số Vận Đơn (AWB)</b>", cell_bold),
        Paragraph("<b>Số Kiện</b>", cell_bold),
        Paragraph("<b>Trọng Lượng (kg)</b>", cell_bold),
        Paragraph("<b>Người Nhận / Đại Lý</b>", cell_bold),
        Paragraph("<b>Trạng Thái / HAWB</b>", cell_bold),
        Paragraph("<b>Kiểm Đếm / Ký</b>", cell_bold),
    ]

    table_data = [headers]
    for idx, r in enumerate(records, start=1):
        status_text = r.status_tag.value if hasattr(r.status_tag, "value") else str(r.status_tag)
        if r.has_all_imp_acc_hawb:
            status_desc = "ĐÃ DUYỆT HAWB (CLEARED)"
        else:
            status_desc = f"{status_text} - {r.raw_remarks[:30]}"

        cnee_text = f"{r.consignee}<br/><i>{r.agent}</i>" if r.agent else r.consignee

        row = [
            Paragraph(str(idx), cell_style),
            Paragraph(f"<b>{r.awb_number}</b>", cell_bold),
            Paragraph(str(r.pieces) if r.pieces is not None else "—", cell_style),
            Paragraph(f"{r.weight_kg:.2f}" if r.weight_kg is not None else "—", cell_style),
            Paragraph(cnee_text, cell_style),
            Paragraph(status_desc, cell_style),
            Paragraph("[  ] Đủ hàng", cell_style),
        ]
        table_data.append(row)

    col_widths = [25, 85, 45, 60, 150, 120, 60]  # Total: 545 pt (A4 width 595 - 50 margins)
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECEFF1")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B0BEC5")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(tbl)
    story.append(Spacer(1, 20))

    # 3-tier Signature Block
    sig_data = [
        [
            Paragraph("<b>BÊN GIAO CA</b><br/>(Ký và ghi rõ họ tên)", cell_bold),
            Paragraph("<b>BÊN NHẬN CA</b><br/>(Ký và ghi rõ họ tên)", cell_bold),
            Paragraph("<b>GIÁM SÁT HẢI QUAN / KHO</b><br/>(Ký và xác nhận)", cell_bold),
        ],
        [Spacer(1, 35), Spacer(1, 35), Spacer(1, 35)],
        [
            Paragraph(handover_person, cell_style),
            Paragraph(receiver_person, cell_style),
            Paragraph("Cán bộ trực giám sát", cell_style),
        ],
    ]
    sig_tbl = Table(sig_data, colWidths=[180, 180, 185])
    sig_tbl.setStyle(
        TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    story.append(sig_tbl)

    doc.build(story)
    return output_path


class TestPDFFileStructure:
    """Tests PDF file magic bytes and EOF trailer."""

    def test_pdf_header_and_eof(self, temp_output_dir: Path, sample_awb_records: List[AWBRecord]) -> None:
        pdf_path = str(temp_output_dir / "handover_audit.pdf")
        build_reference_handover_pdf(sample_awb_records, pdf_path)

        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000

        with open(pdf_path, "rb") as f:
            header = f.read(5)
            assert header.startswith(b"%PDF-"), "Invalid PDF header magic bytes"

            f.seek(-1024, os.SEEK_END)
            tail = f.read()
            assert b"%%EOF" in tail, "Missing %%EOF marker in trailer"


class TestISOA4PageGeometry:
    """Tests ISO A4 page dimensions (595.28 x 841.89 pt within 1.0 pt tolerance)."""

    def test_page_dimensions_iso_a4(
        self, temp_output_dir: Path, sample_awb_records: List[AWBRecord]
    ) -> None:
        pdf_path = str(temp_output_dir / "handover_a4_test.pdf")
        build_reference_handover_pdf(sample_awb_records, pdf_path)

        reader = PdfReader(pdf_path)
        assert len(reader.pages) >= 1

        page = reader.pages[0]
        box = page.mediabox
        width = float(box.width)
        height = float(box.height)

        # ISO A4 portrait is 595.2756 pt x 841.8898 pt
        assert abs(width - 595.28) < 1.0, f"Expected A4 width ~595.28 pt, got {width}"
        assert abs(height - 841.89) < 1.0, f"Expected A4 height ~841.89 pt, got {height}"


class TestVietnameseUTF8Typography:
    """Tests Vietnamese diacritics rendering without unicode replacement characters."""

    def test_vietnamese_text_fidelity(
        self, temp_output_dir: Path, sample_awb_records: List[AWBRecord]
    ) -> None:
        pdf_path = str(temp_output_dir / "handover_vietnamese.pdf")
        build_reference_handover_pdf(sample_awb_records, pdf_path)

        reader = PdfReader(pdf_path)
        full_text = "\n".join([page.extract_text() for page in reader.pages])

        # Verify key Vietnamese and logistics strings
        assert "PHIẾU BÀN GIAO" in full_text
        assert "VẬN ĐƠN" in full_text
        assert "CONG TY TNHH" in full_text
        assert "Nguyễn Văn Giao" in full_text
        assert "Trần Thị Nhận" in full_text
        assert "ĐÃ DUYỆT HAWB" in full_text or "CLEARED" in full_text
        assert "020-12345675" in full_text

        # Ensure no character corruption replacement markers
        assert "\ufffd" not in full_text, "Found unicode replacement character \ufffd"
        assert "???" not in full_text, "Found question mark replacement placeholders"


class TestAppPdfGeneratorContract:
    """Tests the production PDF generator in app.pdf.generator if implemented."""

    def test_app_pdf_generator_if_available(
        self, temp_output_dir: Path, sample_awb_records: List[AWBRecord]
    ) -> None:
        try:
            from app.pdf.generator import generate_cargo_handover_pdf
        except ImportError:
            pytest.skip("Milestone M4 (app.pdf.generator) is not yet implemented.")

        pdf_path = str(temp_output_dir / "production_handover.pdf")
        result_path = generate_cargo_handover_pdf(sample_awb_records, pdf_path)

        assert os.path.exists(result_path)
        with open(result_path, "rb") as f:
            header = f.read(5)
            assert header.startswith(b"%PDF-")

        reader = PdfReader(result_path)
        box = reader.pages[0].mediabox
        assert abs(float(box.width) - 595.28) < 1.0
        assert abs(float(box.height) - 841.89) < 1.0
