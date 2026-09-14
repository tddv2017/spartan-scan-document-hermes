"""Standardized ISO A4 Cargo Handover PDF Report Generator.

Generates professional air cargo handover and shift reconciliation PDF reports
for Lufthansa Cargo / Hermes CMS operations. Fully supports Vietnamese UTF-8
typography using embedded Windows TrueType fonts (Arial), standard ISO A4 dimensions,
and IATA cargo handover formatting.
"""

from datetime import datetime, timezone
import html
import logging
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm, inch

pt = 1.0
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import (
    APP_NAME,
    APP_VERSION,
    Config,
    DEFAULT_AIRLINE_NAME,
    FALLBACK_FONT_PATHS,
    WINDOWS_FONTS_DIR,
)
from app.core.models import AWBRecord, BusinessStatus, SessionSummary

logger = logging.getLogger(__name__)

# Global state for registered font
_FONTS_INITIALIZED = False
_ACTIVE_FONT_NAME = "Helvetica"
_ACTIVE_BOLD_FONT_NAME = "Helvetica-Bold"
_ACTIVE_ITALIC_FONT_NAME = "Helvetica-Oblique"
_ACTIVE_BOLDITALIC_FONT_NAME = "Helvetica-Bold"


def register_vietnamese_fonts() -> str:
    """Register and embed TrueType fonts for flawless Vietnamese UTF-8 rendering.

    Prioritizes Windows Arial (arial.ttf / arialbd.ttf / ariali.ttf / arialbi.ttf).
    Falls back to alternative system fonts (tahoma, segoeui, times) or Helvetica.
    """
    global _FONTS_INITIALIZED, _ACTIVE_FONT_NAME, _ACTIVE_BOLD_FONT_NAME
    global _ACTIVE_ITALIC_FONT_NAME, _ACTIVE_BOLDITALIC_FONT_NAME

    if _FONTS_INITIALIZED:
        return _ACTIVE_FONT_NAME

    # Check Windows fonts directory
    font_candidates = [
        {
            "family": "Arial",
            "normal": str(WINDOWS_FONTS_DIR / "arial.ttf"),
            "bold": str(WINDOWS_FONTS_DIR / "arialbd.ttf"),
            "italic": str(WINDOWS_FONTS_DIR / "ariali.ttf"),
            "boldItalic": str(WINDOWS_FONTS_DIR / "arialbi.ttf"),
        },
        {
            "family": "SegoeUI",
            "normal": str(WINDOWS_FONTS_DIR / "segoeui.ttf"),
            "bold": str(WINDOWS_FONTS_DIR / "segoeuib.ttf"),
            "italic": str(WINDOWS_FONTS_DIR / "segoeuii.ttf"),
            "boldItalic": str(WINDOWS_FONTS_DIR / "segoeuiz.ttf"),
        },
        {
            "family": "Tahoma",
            "normal": str(WINDOWS_FONTS_DIR / "tahoma.ttf"),
            "bold": str(WINDOWS_FONTS_DIR / "tahomabd.ttf"),
            "italic": str(WINDOWS_FONTS_DIR / "tahoma.ttf"),
            "boldItalic": str(WINDOWS_FONTS_DIR / "tahomabd.ttf"),
        },
    ]

    for candidate in font_candidates:
        norm_path = candidate["normal"]
        bold_path = candidate["bold"]
        if os.path.exists(norm_path) and os.path.exists(bold_path):
            try:
                fam = candidate["family"]
                pdfmetrics.registerFont(TTFont(fam, norm_path))
                pdfmetrics.registerFont(TTFont(f"{fam}-Bold", bold_path))

                italic_path = candidate["italic"] if os.path.exists(candidate["italic"]) else norm_path
                bolditalic_path = candidate["boldItalic"] if os.path.exists(candidate["boldItalic"]) else bold_path

                pdfmetrics.registerFont(TTFont(f"{fam}-Italic", italic_path))
                pdfmetrics.registerFont(TTFont(f"{fam}-BoldItalic", bolditalic_path))

                pdfmetrics.registerFontFamily(
                    fam,
                    normal=fam,
                    bold=f"{fam}-Bold",
                    italic=f"{fam}-Italic",
                    boldItalic=f"{fam}-BoldItalic",
                )

                _ACTIVE_FONT_NAME = fam
                _ACTIVE_BOLD_FONT_NAME = f"{fam}-Bold"
                _ACTIVE_ITALIC_FONT_NAME = f"{fam}-Italic"
                _ACTIVE_BOLDITALIC_FONT_NAME = f"{fam}-BoldItalic"
                _FONTS_INITIALIZED = True
                logger.info(f"Registered TrueType font family '{fam}' from {norm_path}")
                return _ACTIVE_FONT_NAME
            except Exception as e:
                logger.warning(f"Failed to register font candidate {candidate['family']}: {e}")

    # Fallback to standard 14 PostScript fonts (will lack some Vietnamese diacritics but won't crash)
    logger.warning("No Windows TrueType font found. Falling back to default Helvetica.")
    _ACTIVE_FONT_NAME = "Helvetica"
    _ACTIVE_BOLD_FONT_NAME = "Helvetica-Bold"
    _ACTIVE_ITALIC_FONT_NAME = "Helvetica-Oblique"
    _ACTIVE_BOLDITALIC_FONT_NAME = "Helvetica-Bold"
    _FONTS_INITIALIZED = True
    return _ACTIVE_FONT_NAME


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to calculate total page count and draw running page numbers and headers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []
        self._generation_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_running_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_running_footer(self, total_pages: int) -> None:
        self.saveState()
        font = _ACTIVE_FONT_NAME
        self.setFont(font, 7.5)
        self.setFillColor(colors.HexColor("#64748B"))

        page_w = 595.28  # ISO A4 width in pt
        margin_x = 36.0  # 0.5 inch

        # Running footer dividing rule
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(margin_x, 30.0, page_w - margin_x, 30.0)

        # Left label: Airline & Software Branding
        left_text = (
            f"Hermes CMS Inbound Reconciliation | Lufthansa Cargo AG | "
            f"Thời điểm xuất: {self._generation_time}"
        )
        self.drawString(margin_x, 20.0, left_text)

        # Right label: Page X of Y
        page_str = f"Trang {self._pageNumber} / {total_pages}"
        self.drawRightString(page_w - margin_x, 20.0, page_str)

        self.restoreState()


def generate_cargo_handover_pdf(
    records: List[AWBRecord],
    output_path: str,
    shift_name: str = "Ca 1",
    handover_person: str = "Nhân viên xử lý",
    receiver_person: str = "Nhân viên ca kế tiếp",
    summary: Optional[SessionSummary] = None,
    station: str = "HAN / NCTS Cargo Hub",
) -> str:
    """Generate an ISO A4 cargo handover and reconciliation PDF report with Vietnamese UTF-8 text.

    Args:
        records: List of AWB records to include in the handover table.
        output_path: Target PDF file system path.
        shift_name: Name/code of the operational shift (e.g. 'Ca 1 (06:00 - 14:00)').
        handover_person: Operator handing over the shift.
        receiver_person: Operator receiving the shift.
        summary: Optional pre-calculated SessionSummary; if None, computed from records.
        station: Cargo terminal hub name.

    Returns:
        str: Absolute path to the generated PDF file.
    """
    font_name = register_vietnamese_fonts()
    bold_font = _ACTIVE_BOLD_FONT_NAME
    italic_font = _ACTIVE_ITALIC_FONT_NAME

    # Ensure output parent directory exists
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    # Compute metrics if summary not provided
    total_pcs = sum(r.pieces for r in records if r.pieces is not None)
    total_wt = sum(r.weight_kg for r in records if r.weight_kg is not None)
    cleared_cnt = sum(
        1 for r in records if r.has_all_imp_acc_hawb or r.status_tag == BusinessStatus.CLEARED
    )
    total_records = len(records)
    cleared_pct = (cleared_cnt / total_records * 100.0) if total_records > 0 else 0.0

    # Page setup: ISO A4 Portrait (595.28 x 841.89 pt) with 36 pt (12.7mm) margins
    # Printable width: 595.28 - 72 = 523.28 pt
    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=A4,
        leftMargin=36 * pt,
        rightMargin=36 * pt,
        topMargin=36 * pt,
        bottomMargin=42 * pt,
        title="PHIẾU ĐỐI SOÁT & BÀN GIAO VẬN ĐƠN CA TRỰC - HERMES CMS",
        author="Hermes Vision Extractor",
        subject="Lufthansa Cargo Handover Sheet",
    )

    usable_width = 523.28 * pt

    # -------------------------------------------------------------------------
    # Styles Definition
    # -------------------------------------------------------------------------
    styles = getSampleStyleSheet()

    # Brand Colors
    c_primary = colors.HexColor("#00205B")     # Lufthansa Deep Navy
    c_accent = colors.HexColor("#D97706")      # Amber / Gold accent
    c_dark = colors.HexColor("#0F172A")        # Slate 900
    c_gray = colors.HexColor("#475569")        # Slate 600
    c_light_bg = colors.HexColor("#F8FAFC")    # Slate 50
    c_border = colors.HexColor("#CBD5E1")      # Slate 300
    c_cleared = colors.HexColor("#059669")     # Emerald 600
    c_cleared_bg = colors.HexColor("#ECFDF5")  # Emerald 50
    c_error = colors.HexColor("#DC2626")       # Red 600

    style_airline = ParagraphStyle(
        "AirlineBrand",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=10,
        leading=13,
        textColor=c_primary,
    )

    style_station = ParagraphStyle(
        "StationInfo",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        leading=11,
        textColor=c_gray,
        alignment=2,  # Right align
    )

    style_doc_title = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName=bold_font,
        fontSize=14,
        leading=17,
        textColor=c_primary,
        alignment=1,  # Center
        spaceAfter=3,
    )

    style_doc_subtitle = ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontName=italic_font,
        fontSize=8.5,
        leading=11,
        textColor=c_gray,
        alignment=1,  # Center
        spaceAfter=8,
    )

    style_meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=8,
        leading=11,
        textColor=c_dark,
    )

    style_meta_val = ParagraphStyle(
        "MetaVal",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        leading=11,
        textColor=c_dark,
    )

    # Table Cell Styles
    cell_hdr = ParagraphStyle(
        "CellHdr",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1,  # Center
    )

    cell_center = ParagraphStyle(
        "CellCenter",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=7.5,
        leading=10,
        alignment=1,
    )

    cell_awb = ParagraphStyle(
        "CellAWB",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=c_primary,
    )

    cell_right = ParagraphStyle(
        "CellRight",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=7.5,
        leading=10,
        alignment=2,  # Right
    )

    cell_left = ParagraphStyle(
        "CellLeft",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=7.5,
        leading=9.5,
        alignment=0,  # Left
    )

    cell_remark = ParagraphStyle(
        "CellRemark",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=7,
        leading=9,
        alignment=0,
    )

    # -------------------------------------------------------------------------
    # Story Construction
    # -------------------------------------------------------------------------
    story = []

    # 1. Top Organization Header
    top_header_data = [
        [
            Paragraph("<b>LUFTHANSA CARGO AG</b> &bull; HERMES CMS CARGO OPERATIONS", style_airline),
            Paragraph(f"Trạm Khai Thác: <b>{html.escape(station)}</b>", style_station),
        ]
    ]
    top_header_table = Table(top_header_data, colWidths=[330 * pt, 193.28 * pt])
    top_header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(top_header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=3, spaceAfter=8))

    # 2. Main Title & Subtitle
    story.append(Paragraph("PHIẾU ĐỐI SOÁT & BÀN GIAO VẬN ĐƠN CA TRỰC", style_doc_title))
    story.append(
        Paragraph(
            "QUY TRÌNH ĐỐI SOÁT DỮ LIỆU HERMES CMS (LH) - PHỤC VỤ GIAO NHẬN VÀ XỬ LÝ CA KẾ TIẾP",
            style_doc_subtitle,
        )
    )

    # 3. Metadata Information Grid (Shift, Handover, Receiver, Timestamp)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    meta_table_data = [
        [
            Paragraph("<b>Ca làm việc:</b>", style_meta_label),
            Paragraph(html.escape(shift_name), style_meta_val),
            Paragraph("<b>Nhân viên giao ca:</b>", style_meta_label),
            Paragraph(html.escape(handover_person), style_meta_val),
        ],
        [
            Paragraph("<b>Thời gian lập:</b>", style_meta_label),
            Paragraph(now_str, style_meta_val),
            Paragraph("<b>Nhân viên nhận ca:</b>", style_meta_label),
            Paragraph(html.escape(receiver_person), style_meta_val),
        ],
    ]
    meta_table = Table(
        meta_table_data,
        colWidths=[75 * pt, 185 * pt, 95 * pt, 168.28 * pt],
    )
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c_light_bg),
            ("BOX", (0, 0), (-1, -1), 0.75, c_border),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 6))

    # 4. Summary KPI Metrics Box (4 cards)
    summary_box_data = [
        [
            Paragraph("<b>TỔNG SỐ AWB</b>", cell_hdr),
            Paragraph("<b>TỔNG SỐ KIỆN</b>", cell_hdr),
            Paragraph("<b>TỔNG TRỌNG LƯỢNG</b>", cell_hdr),
            Paragraph("<b>ĐÃ DUYỆT HAWB (ALL IMP)</b>", cell_hdr),
        ],
        [
            Paragraph(f"<font size='11' color='#00205B'><b>{total_records}</b></font> vận đơn", cell_center),
            Paragraph(f"<font size='11' color='#00205B'><b>{total_pcs:,}</b></font> Colli", cell_center),
            Paragraph(f"<font size='11' color='#00205B'><b>{total_wt:,.2f}</b></font> kg", cell_center),
            Paragraph(
                f"<font size='11' color='#059669'><b>{cleared_cnt}</b>/{total_records}</font> "
                f"({cleared_pct:.1f}%)",
                cell_center,
            ),
        ],
    ]
    summary_box_table = Table(
        summary_box_data,
        colWidths=[130.82 * pt, 130.82 * pt, 130.82 * pt, 130.82 * pt],
    )
    summary_box_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), c_primary),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
            ("BOX", (0, 0), (-1, -1), 1.0, c_primary),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, c_border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 3),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
            ("TOPPADDING", (0, 1), (-1, 1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
        ])
    )
    story.append(summary_box_table)
    story.append(Spacer(1, 8))

    # 5. Main Cargo Reconciliation Table
    # Columns definition (Total = 523.28 pt):
    # 0: STT (28 pt)
    # 1: Số AWB (78 pt)
    # 2: Số Kiện (42 pt)
    # 3: Trọng Lượng (60 pt)
    # 4: Consignee / Agent (125 pt)
    # 5: Trạng Thái & Remark (130 pt)
    # 6: Ký Nhận / Kiểm Đếm (60.28 pt)
    col_widths = [28 * pt, 78 * pt, 42 * pt, 60 * pt, 125 * pt, 130 * pt, 60.28 * pt]

    table_data = [
        [
            Paragraph("<b>STT</b>", cell_hdr),
            Paragraph("<b>Số AWB</b>", cell_hdr),
            Paragraph("<b>Kiện<br/>(Colli)</b>", cell_hdr),
            Paragraph("<b>Trọng Lượng<br/>(KG)</b>", cell_hdr),
            Paragraph("<b>Người Nhận (Consignee)<br/>& Đại Lý (Agent)</b>", cell_hdr),
            Paragraph("<b>Trạng Thái & Ghi Chú<br/>(ALL IMP/ACC HAWB)</b>", cell_hdr),
            Paragraph("<b>Kiểm Đếm<br/>Ký Nhận</b>", cell_hdr),
        ]
    ]

    tstyle = [
        ("BACKGROUND", (0, 0), (-1, 0), c_primary),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, c_border),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]

    if not records:
        # Empty placeholder row
        table_data.append([
            Paragraph("1", cell_center),
            Paragraph("<i>(Chưa có dữ liệu vận đơn)</i>", cell_center),
            Paragraph("-", cell_center),
            Paragraph("-", cell_center),
            Paragraph("-", cell_center),
            Paragraph("-", cell_center),
            Paragraph("[  ]", cell_center),
        ])
    else:
        for idx, rec in enumerate(records, start=1):
            row_idx = len(table_data)

            # Zebra striping
            bg_color = colors.white if idx % 2 != 0 else colors.HexColor("#F8FAFC")

            # Check for CLEARED status highlight
            is_cleared = rec.has_all_imp_acc_hawb or (rec.status_tag == BusinessStatus.CLEARED)

            # Consignee & Agent formatted paragraph
            cnee_text = html.escape(rec.consignee) if rec.consignee else "<font color='#94A3B8'><i>Chưa có</i></font>"
            agent_text = (
                f"<br/><font size='6.5' color='#64748B'>Đại lý: {html.escape(rec.agent)}</font>"
                if rec.agent else ""
            )
            cnee_cell = Paragraph(f"<b>{cnee_text}</b>{agent_text}", cell_left)

            dest_code = getattr(rec, "destination", "SGN")

            # Status and Remark cell
            if not rec.is_valid_checksum:
                status_badge = "<font color='#DC2626'><b>✖ LỖI CHECKSUM</b></font>"
            elif dest_code != "SGN":
                status_badge = f"<font color='#DC2626'><b>⛔ SAI ĐIỂM ĐẾN ({dest_code})</b></font>"
            elif is_cleared:
                status_badge = "<font color='#059669'><b>✔ ALL IMP/ACC HAWB</b></font>"
            elif rec.status_tag == BusinessStatus.PENDING_HAWB:
                status_badge = "<font color='#D97706'><b>⏳ PENDING HAWB</b></font>"
            else:
                status_badge = "<font color='#2563EB'><b>✈ DIRECT SHIPMENT</b></font>"

            remark_detail = ""
            if rec.raw_remarks:
                clean_rmk = html.escape(rec.raw_remarks)
                # Truncate if exceptionally long to keep table neat
                if len(clean_rmk) > 75:
                    clean_rmk = clean_rmk[:72] + "..."
                remark_detail = f"<br/><font size='6.5' color='#334155'>{clean_rmk}</font>"

            status_cell = Paragraph(f"{status_badge}{remark_detail}", cell_remark)

            # AWB Number cell with destination tag
            awb_display = html.escape(rec.awb_number)
            if not rec.is_valid_checksum:
                awb_display += " <font color='#DC2626' size='6.5'>[ERR]</font>"

            if dest_code == "SGN":
                dest_tag = "<br/><font size='6.5' color='#059669'>Dest: SGN</font>"
            else:
                dest_tag = f"<br/><font size='6.5' color='#DC2626'><b>Dest: {dest_code} (SAI)</b></font>"

            awb_cell = Paragraph(f"<b>{awb_display}</b>{dest_tag}", cell_awb)

            # Pieces & Weight
            pcs_str = f"{rec.pieces:,}" if rec.pieces is not None else "-"
            wt_str = f"{rec.weight_kg:,.2f}" if rec.weight_kg is not None else "-"

            table_data.append([
                Paragraph(str(idx), cell_center),
                awb_cell,
                Paragraph(pcs_str, cell_right),
                Paragraph(wt_str, cell_right),
                cnee_cell,
                status_cell,
                Paragraph("[  ] Đạt", cell_center),
            ])

            # Apply row styling
            if dest_code != "SGN":
                # Soft red accent for wrong destination
                tstyle.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#FEF2F2")))
            elif is_cleared:
                # Soft green accent for cleared rows
                tstyle.append(("BACKGROUND", (0, row_idx), (-1, row_idx), c_cleared_bg))
            else:
                tstyle.append(("BACKGROUND", (0, row_idx), (-1, row_idx), bg_color))

    # Total Summary Table Row
    total_row_idx = len(table_data)
    table_data.append([
        Paragraph(f"<b>TỔNG CỘNG ({total_records} AWB)</b>", cell_center),
        "",  # Spanned
        Paragraph(f"<b>{total_pcs:,}</b>", cell_right),
        Paragraph(f"<b>{total_wt:,.2f}</b>", cell_right),
        Paragraph(f"<b>Đã kiểm đếm: {cleared_cnt} / {total_records}</b>", cell_left),
        Paragraph(f"<b>Tỷ lệ đạt HAWB: {cleared_pct:.1f}%</b>", cell_left),
        Paragraph("<b>[  ] TỔNG</b>", cell_center),
    ])
    tstyle.extend([
        ("SPAN", (0, total_row_idx), (1, total_row_idx)),
        ("BACKGROUND", (0, total_row_idx), (-1, total_row_idx), colors.HexColor("#E2E8F0")),
        ("LINEABOVE", (0, total_row_idx), (-1, total_row_idx), 1.0, c_primary),
        ("FONTNAME", (0, total_row_idx), (-1, total_row_idx), bold_font),
        ("TOPPADDING", (0, total_row_idx), (-1, total_row_idx), 4),
        ("BOTTOMPADDING", (0, total_row_idx), (-1, total_row_idx), 4),
    ])

    cargo_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    cargo_table.setStyle(TableStyle(tstyle))
    story.append(cargo_table)
    story.append(Spacer(1, 14))

    # 6. Notes / Operational Instructions
    notes_text = (
        "<b>LƯU Ý NGHIỆP VỤ BÀN GIAO:</b><br/>"
        "1. Các vận đơn đánh dấu <b>ALL IMP/ACC HAWB</b> đã hoàn tất thủ tục phân tách HAWB và thông quan hàng đến.<br/>"
        "2. Nhân viên nhận ca có trách nhiệm kiểm đếm số kiện vật lý đối chiếu với cột (Colli/KG) trên phiếu trước khi ký xác nhận.<br/>"
        "3. Mọi sai lệch số kiện, rách vỡ hoặc AWB báo lỗi Checksum phải lập biên bản bất thường (Irregularity Report) ngay."
    )
    style_notes = ParagraphStyle(
        "NotesStyle",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#334155"),
    )
    notes_table = Table([[Paragraph(notes_text, style_notes)]], colWidths=[usable_width])
    notes_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ])
    )

    # 7. Signature Blocks (3 columns)
    sig_col_w = usable_width / 3.0
    sig_data = [
        [
            Paragraph("<b>NGƯỜI LẬP PHIẾU</b><br/><font size='7' color='#64748B'>(Ký & ghi rõ họ tên)</font>", cell_center),
            Paragraph("<b>NHÂN VIÊN GIAO CA</b><br/><font size='7' color='#64748B'>(Ký & ghi rõ họ tên)</font>", cell_center),
            Paragraph("<b>NHÂN VIÊN NHẬN CA</b><br/><font size='7' color='#64748B'>(Ký & ghi rõ họ tên)</font>", cell_center),
        ],
        [
            Paragraph("<br/><br/><br/>", cell_center),
            Paragraph("<br/><br/><br/>", cell_center),
            Paragraph("<br/><br/><br/>", cell_center),
        ],
        [
            Paragraph(f"<b>{html.escape(handover_person)}</b>", cell_center),
            Paragraph(f"<b>{html.escape(handover_person)}</b>", cell_center),
            Paragraph(f"<b>{html.escape(receiver_person)}</b>", cell_center),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[sig_col_w, sig_col_w, sig_col_w])
    sig_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ])
    )

    # Wrap notes and signatures in KeepTogether to avoid awkward page breaks
    story.append(KeepTogether([notes_table, Spacer(1, 12), sig_table]))

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)
    logger.info(f"Generated standardized A4 cargo handover PDF at: {out_file}")
    return str(out_file)


def preview_pdf(pdf_path: str) -> bool:
    """Open the generated PDF in the system default PDF viewer (e.g. Acrobat Reader, Chrome, Edge).

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        bool: True if successfully launched, False otherwise.
    """
    path = Path(pdf_path).resolve()
    if not path.exists():
        logger.error(f"Cannot preview PDF: File not found at {path}")
        return False

    try:
        if platform.system() == "Windows":
            os.startfile(str(path))
            return True
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
            return True
        else:
            subprocess.Popen(["xdg-open", str(path)])
            return True
    except Exception as e:
        logger.error(f"Failed to launch PDF preview for {path}: {e}")
        # Fallback to webbrowser module
        try:
            import webbrowser
            webbrowser.open(path.as_uri())
            return True
        except Exception as e2:
            logger.error(f"Webbrowser fallback also failed: {e2}")
            return False


def print_pdf(pdf_path: str, printer_name: Optional[str] = None) -> bool:
    """Send the PDF document directly to a Windows printer.

    Args:
        pdf_path: Path to the PDF file.
        printer_name: Specific printer name; if None, uses system default printer.

    Returns:
        bool: True if print job submitted successfully, False otherwise.
    """
    path = Path(pdf_path).resolve()
    if not path.exists():
        logger.error(f"Cannot print PDF: File not found at {path}")
        return False

    if platform.system() != "Windows":
        # Unix / CUPS fallback via lpr
        try:
            cmd = ["lpr"]
            if printer_name:
                cmd.extend(["-P", printer_name])
            cmd.append(str(path))
            res = subprocess.run(cmd, capture_output=True, text=True)
            return res.returncode == 0
        except Exception as e:
            logger.error(f"Unix lpr print failed: {e}")
            return False

    # Windows native printing
    try:
        import win32api
        import win32print

        target_printer = printer_name or win32print.GetDefaultPrinter()
        logger.info(f"Submitting PDF print job for {path.name} to printer '{target_printer}'")

        if printer_name:
            win32api.ShellExecute(
                0,
                "printto",
                str(path),
                f'"{printer_name}"',
                ".",
                0,
            )
        else:
            win32api.ShellExecute(
                0,
                "print",
                str(path),
                None,
                ".",
                0,
            )
        return True
    except Exception as e:
        logger.error(f"Win32 print execution failed: {e}")
        return False
