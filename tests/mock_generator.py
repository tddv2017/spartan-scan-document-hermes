"""Synthetic Mock Hermes CMS Screenshot Generator.

Generates high-fidelity UI panel screenshots mimicking the Hermes Cargo Management System
(Lufthansa Cargo theme) using Pillow. Produces diverse operational test fixtures covering
standard AWBs, European Colli terminology, compound quantity lines, clearance variations,
delimiter variations, Vietnamese diacritics, decimal commas, and IATA Mod-7 check digit failures.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont


@dataclass
class HermesFixture:
    """Ground truth metadata and visual representation parameters for a Hermes CMS test case."""

    fixture_id: str
    awb_number: str
    pieces: int
    weight_kg: float
    pieces_label: str
    weight_label: str
    consignee: str
    agent: str
    remark: str
    remark_agent: str
    has_all_imp_acc_hawb: bool
    is_valid_mod7: bool
    expected_status: str
    airline_name: str = "Lufthansa Cargo"
    description: str = ""

    @property
    def awb_prefix(self) -> str:
        """3-digit airline prefix."""
        return self.awb_number.split("-")[0] if "-" in self.awb_number else self.awb_number[:3]

    @property
    def awb_serial(self) -> str:
        """8-digit serial component."""
        return self.awb_number.split("-")[1] if "-" in self.awb_number else self.awb_number[3:]


# ---------------------------------------------------------------------------
# Authoritative 10 Operational Fixtures Matrix
# ---------------------------------------------------------------------------

OPERATIONAL_FIXTURES: List[HermesFixture] = [
    HermesFixture(
        fixture_id="FIX-01",
        awb_number="020-12345675",
        pieces=45,
        weight_kg=1250.5,
        pieces_label="45 PCS",
        weight_label="1250.50 KG",
        consignee="CONG TY TNHH LOGISTICS TOAN CAU",
        agent="HAN - NCTS LOGISTICS AGENT",
        remark="ALL IMP/ACC HAWB - DOCS DELIVERED - CUSTOMS CLEARED",
        remark_agent="HAN/CARGO-OPS-01",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=True,
        expected_status="CLEARED",
        description="Clean standard Lufthansa Cargo import shipment with valid Mod-7 and HAWB clearance.",
    ),
    HermesFixture(
        fixture_id="FIX-02",
        awb_number="020-98765435",
        pieces=120,
        weight_kg=3450.0,
        pieces_label="120 Colli",
        weight_label="3450.00 KG",
        consignee="SCHENKER VIETNAM CO LTD",
        agent="SGN - SCHENKER AIR FREIGHT",
        remark="ALL IMP/ACC HAWB",
        remark_agent="SGN/LH-RAMP",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=True,
        expected_status="CLEARED",
        description="European terminology using 'Colli' and clean clearance flag without trailing notes.",
    ),
    HermesFixture(
        fixture_id="FIX-03",
        awb_number="020-45678905",
        pieces=15,
        weight_kg=230.75,
        pieces_label="15 Colli",
        weight_label="230.75 KG",
        consignee="EXPEDITORS VIETNAM CO LTD",
        agent="HAN - EXPEDITORS INTL",
        remark="ALL IMP / ACC HAWB - PRIORITY GENERAL CARGO",
        remark_agent="HAN/DOCS-WHSE",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=True,
        expected_status="CLEARED",
        description="Whitespace variation around slash in 'ALL IMP / ACC HAWB' with fractional kilogram weight.",
    ),
    HermesFixture(
        fixture_id="FIX-04",
        awb_number="020-87654324",
        pieces=8,
        weight_kg=95.2,
        pieces_label="8 PCS",
        weight_label="95.20 KG",
        consignee="KUEHNE NAGEL VIETNAM LLC",
        agent="HAN - KN AIR CARGO",
        remark="CONSOLIDATION SHIPMENT - HOLD AWAITING HAWB DOCS",
        remark_agent="HAN/IMPORT-DESK",
        has_all_imp_acc_hawb=False,
        is_valid_mod7=True,
        expected_status="PENDING_HAWB",
        description="Consolidation cargo missing HAWB clearance flag, requiring PENDING_HAWB operational lock.",
    ),
    HermesFixture(
        fixture_id="FIX-05",
        awb_number="020-33445565",
        pieces=1,
        weight_kg=12.5,
        pieces_label="1 PKG",
        weight_label="12.50 KG",
        consignee="INDIVIDUAL IMPORTER NGUYEN VAN A",
        agent="DIRECT IMPORT BROKERAGE",
        remark="DIRECT MASTER SHIPMENT - SINGLE CONSIGNMENT",
        remark_agent="HAN/EXP-COUNTER",
        has_all_imp_acc_hawb=False,
        is_valid_mod7=True,
        expected_status="DIRECT_SHIPMENT",
        description="Direct single shipment without house bills, classified as DIRECT_SHIPMENT.",
    ),
    HermesFixture(
        fixture_id="FIX-06",
        awb_number="020-77889906",
        pieces=60,
        weight_kg=1800.0,
        pieces_label="60 Colli",
        weight_label="1800.00 KG",
        consignee="DHL GLOBAL FORWARDING VIETNAM",
        agent="DGF - DHL GLOBAL AGENT",
        remark="ALL IMP\\ACC HAWB - RELEASE AUTHORIZED",
        remark_agent="HAN/DGF-SPECIALIST",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=True,
        expected_status="CLEARED",
        description="Backslash delimiter variation in 'ALL IMP\\ACC HAWB'.",
    ),
    HermesFixture(
        fixture_id="FIX-07",
        awb_number="020-11223343",
        pieces=30,
        weight_kg=450.0,
        pieces_label="30 PCS",
        weight_label="450.00 KG",
        consignee="DSV PANALPINA AIR AND SEA",
        agent="HAN - DSV LOGISTICS AGENT",
        remark="ALL IMP|ACC HAWB VERIFIED ON TERMINAL MANIFEST",
        remark_agent="HAN/TERMINAL-TALLY",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=True,
        expected_status="CLEARED",
        description="Pipe delimiter variation representing common OCR slash substitution.",
    ),
    HermesFixture(
        fixture_id="FIX-08",
        awb_number="020-55667780",
        pieces=25,
        weight_kg=620.0,
        pieces_label="25 PCS",
        weight_label="620.00 KG",
        consignee="CONG TY TNHH TIEP VAN SAO BIEN",
        agent="SGN - SAO BIEN FORWARDING",
        remark="ALL IMP/ACC  HAWB - DA DUYET HAWB TOAN BO",
        remark_agent="SGN/CUSTOMS-TEAM",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=True,
        expected_status="CLEARED",
        description="Vietnamese company naming and bilingual Vietnamese operational remarks.",
    ),
    HermesFixture(
        fixture_id="FIX-09",
        awb_number="020-99887760",
        pieces=10,
        weight_kg=125.5,
        pieces_label="10 Colli",
        weight_label="125.50 KG",
        consignee="TRANSIMEX CORPORATION",
        agent="HAN - TRANSIMEX CARGO",
        remark="ALL IMP/ACC HAWB - AIRPORT CLEARANCE PASSED",
        remark_agent="HAN/WHSE-INBOUND",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=True,
        expected_status="CLEARED",
        description="European terminology and decimal kilogram weight representation.",
    ),
    HermesFixture(
        fixture_id="FIX-10",
        awb_number="020-24681359",
        pieces=5,
        weight_kg=80.0,
        pieces_label="5 PCS",
        weight_label="80.00 KG",
        consignee="TEST AIRLINE TRAINING CARGO",
        agent="TRAINING SIMULATOR AGENT",
        remark="ALL IMP/ACC HAWB - DEMO TRAINING RUN",
        remark_agent="SIM/STATION-TEST",
        has_all_imp_acc_hawb=True,
        is_valid_mod7=False,
        expected_status="CHECKSUM_ERROR",
        description="Deliberate IATA Modulo-7 checksum mismatch (2468135 mod 7 = 5 != 9).",
    ),
]


def _get_system_font(font_name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Safely load a Windows system font or fall back to default PIL font."""
    font_candidates = [
        f"C:/Windows/Fonts/{font_name}",
        f"C:/Windows/Fonts/tahoma.ttf",
        f"C:/Windows/Fonts/arial.ttf",
        f"C:/Windows/Fonts/segoeui.ttf",
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_mock_screen(
    fixture: HermesFixture,
    width: int = 1024,
    height: int = 640,
) -> Image.Image:
    """Renders a realistic Hermes CMS desktop application window.

    Replicates Lufthansa Cargo's Hermes Classic WinForms theme:
    - Deep Blue (#002B49) branded title bar with window controls
    - Standard Win32 menu bar and tab strip
    - Sunken 3D groupbox panels with light gray background (#F7F7F7)
    - Input text fields with standard Win32 3D borders (#7F9DB9)
    - High-contrast typography optimized for sub-pixel raster rendering
    """
    img = Image.new("RGB", (width, height), color="#ECE9D8")
    draw = ImageDraw.Draw(img)

    # Typography
    font_title = _get_system_font("tahoma.ttf", 15)
    font_bold = _get_system_font("tahomabd.ttf", 16)
    font_field = _get_system_font("tahoma.ttf", 16)
    font_input = _get_system_font("tahoma.ttf", 17)
    font_input_bold = _get_system_font("tahomabd.ttf", 18)

    # 1. Hermes / Lufthansa Header Titlebar
    draw.rectangle([(0, 0), (width, 34)], fill="#002B49")
    draw.text(
        (12, 8),
        "Hermes Cargo Management System - [Air Waybill Enquiry - Lufthansa Cargo]",
        fill="#FFFFFF",
        font=font_title,
    )

    # Window minimize/maximize/close icons mockup
    draw.rectangle([(width - 75, 8), (width - 55, 26)], outline="#FFFFFF", fill="#00355E")
    draw.text((width - 69, 9), "—", fill="#FFFFFF", font=font_title)
    draw.rectangle([(width - 50, 8), (width - 30, 26)], outline="#FFFFFF", fill="#00355E")
    draw.text((width - 44, 9), "□", fill="#FFFFFF", font=font_title)
    draw.rectangle([(width - 25, 8), (width - 5, 26)], outline="#FFFFFF", fill="#C00000")
    draw.text((width - 19, 8), "✕", fill="#FFFFFF", font=font_title)

    # 2. Window Menu Bar
    draw.rectangle([(0, 34), (width, 60)], fill="#F0F0F0")
    draw.line([(0, 60), (width, 60)], fill="#A0A0A0", width=1)
    menu_items = ["General", "Routing", "House AWB", "Special Cargo", "Remarks", "Customs"]
    mx = 15
    for m in menu_items:
        draw.text((mx, 40), m, fill="#222222", font=font_title)
        mx += 110

    # 3. Main GroupBox Panel
    draw.rectangle([(20, 75), (width - 20, height - 25)], outline="#B5B5B5", fill="#F7F7F7", width=2)
    # Cutout label header
    draw.rectangle([(35, 68), (240, 84)], fill="#F7F7F7")
    draw.text((40, 66), " AWB Shipment Details ", fill="#002B49", font=font_bold)

    # Row 1: AWB Number | Pieces / Colli | Gross Weight
    y_pos = 105
    # AWB Number
    draw.text((45, y_pos), "AWB Number:", fill="#111111", font=font_field)
    draw.rectangle([(170, y_pos - 4), (380, y_pos + 28)], fill="#FFFFFF", outline="#7F9DB9", width=2)
    draw.text((185, y_pos), fixture.awb_number, fill="#000000", font=font_input_bold)

    # Pieces / Colli
    draw.text((420, y_pos), "Pieces / Colli:", fill="#111111", font=font_field)
    draw.rectangle([(550, y_pos - 4), (680, y_pos + 28)], fill="#FFFFFF", outline="#7F9DB9", width=2)
    draw.text((565, y_pos), fixture.pieces_label, fill="#000000", font=font_input_bold)

    # Gross Weight
    draw.text((710, y_pos), "Gross Wt:", fill="#111111", font=font_field)
    draw.rectangle([(800, y_pos - 4), (960, y_pos + 28)], fill="#FFFFFF", outline="#7F9DB9", width=2)
    draw.text((815, y_pos), fixture.weight_label, fill="#000000", font=font_input_bold)

    # Row 2: Consignee Entity Name
    y_pos = 165
    draw.text((45, y_pos), "Consignee:", fill="#111111", font=font_field)
    draw.rectangle([(170, y_pos - 4), (960, y_pos + 28)], fill="#FFFFFF", outline="#7F9DB9", width=2)
    draw.text((185, y_pos), fixture.consignee, fill="#000000", font=font_input)

    # Row 3: Handling Agent & Origin / Destination
    y_pos = 220
    draw.text((45, y_pos), "Handling Agent:", fill="#111111", font=font_field)
    draw.rectangle([(170, y_pos - 4), (960, y_pos + 28)], fill="#FFFFFF", outline="#7F9DB9", width=2)
    draw.text((185, y_pos), fixture.agent, fill="#000000", font=font_input)

    # Row 4: Remarks Text Area & Operational Status
    y_pos = 280
    draw.text((45, y_pos), "Special Handling / Remarks:", fill="#111111", font=font_bold)
    draw.rectangle([(45, y_pos + 28), (960, y_pos + 130)], fill="#FFFFFF", outline="#7F9DB9", width=2)
    draw.text((60, y_pos + 42), fixture.remark, fill="#000000", font=font_input_bold)

    # Row 5: Agent Remarks Line
    if fixture.remark_agent:
        draw.text((60, y_pos + 80), f"Agent Remark: {fixture.remark_agent}", fill="#444444", font=font_field)

    # Bottom Status Bar
    draw.rectangle([(20, height - 55), (width - 20, height - 30)], fill="#EAEAEA")
    draw.text(
        (30, height - 50),
        f"Status: Connected | Station: HAN / NCTS Cargo Hub | Carrier: LH Cargo (020) | Fixture: {fixture.fixture_id}",
        fill="#555555",
        font=font_title,
    )

    return img


def generate_hermes_h5_screen(
    fixture: HermesFixture,
    width: int = 1024,
    height: int = 680,
) -> Image.Image:
    """Renders an authentic Hermes H5 (Hermes 5 Cargo Management System) application window.

    Directly replicates the live Hermes H5 UI layout:
    - Dark title bar with 'h5 AWB {prefix}-{serial[:4]} {serial[4:]}' and 'Q Search'
    - 'AWB Detail' and 'Confirmed' header
    - MAWB: [ {prefix} ] -- [ {serial[:4]} {serial[4:]} ] FWB
    - Tab bar: [Confirmation] [Participants] [Details and Charges]
    - Origin (AOO), Customs Info, Commodity, Special Handle Code (SHC)
    - Consignee, Agent, Required Custom Action
    - Pcs. (NPX) / Rcvd (NPR): [ {pieces} ] [ {pieces} ] Manifested {pieces}
    - Wgt.(GWX) / Rcvd (GWR): [ {weight_kg:.1f} ] [ {weight_kg:.1f} ] {weight_kg:.1f}
    - Chargeable Weight: [ {weight_kg:.1f} ]
    - Consignee Standing Inst.: BESTARTOOLS.VN@GMAIL.COM...
    - Shipment Remarks: [ {remark} ]
    - Hermes H5 Action Buttons: [SR] [Messages] [Charges] [History] [Customs Msgs] [Billable Cust] [Reprint Rel. Note] [Print FWB]
    - Bottom F-keys: F2, F3, F4, F5, F6, F7
    """
    img = Image.new("RGB", (width, height), color="#D6D3CE")
    draw = ImageDraw.Draw(img)

    f_title = _get_system_font("tahomabd.ttf", 14)
    f_header = _get_system_font("tahomabd.ttf", 15)
    f_reg = _get_system_font("tahoma.ttf", 13)
    f_reg_b = _get_system_font("tahomabd.ttf", 13)
    f_input = _get_system_font("tahoma.ttf", 13)

    # 1. Title bar (Dark Slate Gray)
    draw.rectangle([(0, 0), (width, 28)], fill="#4A5568")
    s_split = f"{fixture.awb_serial[:4]} {fixture.awb_serial[4:]}"
    draw.text((10, 5), f"h5 AWB {fixture.awb_prefix}-{s_split}", fill="#FFFFFF", font=f_title)
    # Search box
    draw.rectangle([(width - 150, 4), (width - 15, 24)], fill="#FFFFFF", outline="#CBD5E1")
    draw.text((width - 130, 6), "Q Search", fill="#64748B", font=f_reg)

    # 2. Window Header
    draw.text((15, 34), "AWB Detail", fill="#1E293B", font=f_header)
    draw.text((width - 120, 34), "Confirmed", fill="#0F766E", font=f_header)

    # 3. MAWB row
    draw.text((15, 60), "MAWB:", fill="#000000", font=f_reg_b)
    draw.rectangle([(75, 58), (125, 80)], fill="#FFFFFF", outline="#7F9DB9")
    draw.text((83, 60), fixture.awb_prefix, fill="#000000", font=f_input)
    draw.text((130, 60), "--", fill="#000000", font=f_reg)
    draw.rectangle([(145, 58), (265, 80)], fill="#FFFFFF", outline="#7F9DB9")
    draw.text((155, 60), s_split, fill="#000000", font=f_input)
    draw.text((275, 60), "FWB", fill="#1E293B", font=f_reg)

    # 4. Tab strip
    draw.rectangle([(15, 88), (120, 108)], fill="#FFFFFF", outline="#CBD5E1")
    draw.text((22, 91), "Confirmation", fill="#000000", font=f_reg_b)
    draw.rectangle([(122, 88), (220, 108)], fill="#E2E8F0", outline="#CBD5E1")
    draw.text((130, 91), "Participants", fill="#475569", font=f_reg)
    draw.rectangle([(222, 88), (360, 108)], fill="#E2E8F0", outline="#CBD5E1")
    draw.text((230, 91), "Details and Charges", fill="#475569", font=f_reg)

    # Main Form Panel
    draw.rectangle([(15, 108), (width - 15, height - 90)], fill="#F8FAFC", outline="#CBD5E1")

    y = 120
    def draw_field(label: str, val: str, y_pos: int, w: int = 420) -> None:
        draw.text((30, y_pos), label, fill="#000000", font=f_reg)
        draw.rectangle([(230, y_pos - 2), (230 + w, y_pos + 19)], fill="#FFFFFF", outline="#7F9DB9")
        draw.text((236, y_pos), str(val), fill="#000000", font=f_input)

    draw_field("Origin (AOO)", "HGH   Hangzhou", y, 180)
    y += 28
    draw_field("Customs Information Code", "T Total Consignment Manifested", y, 280)
    y += 28
    draw_field("Commodity", "PLASTIC HANDLE HS", y, 280)
    y += 28
    draw_field("Special Handle Code(SHC)", "EAP,ECC,SPX", y, 200)
    y += 28
    draw_field("Consignee", fixture.consignee, y, 520)
    y += 28
    draw_field("Agent", fixture.agent, y, 520)
    y += 28
    draw_field("Required Custom Action", "Simple entry", y, 180)
    y += 34

    # Pcs. (NPX) / Rcvd (NPR)
    draw.text((30, y), "Pcs. (NPX) / Rcvd (NPR)", fill="#000000", font=f_reg)
    draw.rectangle([(230, y - 2), (300, y + 19)], fill="#FFFFFF", outline="#7F9DB9")
    draw.text((245, y), str(fixture.pieces), fill="#000000", font=f_input)
    draw.rectangle([(310, y - 2), (380, y + 19)], fill="#FFFFFF", outline="#7F9DB9")
    draw.text((325, y), str(fixture.pieces), fill="#000000", font=f_input)
    draw.text((395, y), f"Manifested {fixture.pieces}", fill="#0284C7", font=f_reg)
    y += 28

    # Delivered
    draw.text((30, y), "Delivered", fill="#000000", font=f_reg)
    draw.rectangle([(230, y - 2), (300, y + 19)], fill="#FFFFFF", outline="#7F9DB9")
    draw.text((395, y), str(fixture.pieces), fill="#64748B", font=f_reg)
    y += 28

    # Wgt.(GWX) / Rcvd (GWR)
    draw.text((30, y), "Wgt.(GWX) / Rcvd (GWR)", fill="#000000", font=f_reg)
    draw.rectangle([(230, y - 2), (300, y + 19)], fill="#FFFFFF", outline="#7F9DB9")
    draw.text((238, y), f"{fixture.weight_kg:.1f}", fill="#000000", font=f_input)
    draw.rectangle([(310, y - 2), (380, y + 19)], fill="#FFFFFF", outline="#7F9DB9")
    draw.text((318, y), f"{fixture.weight_kg:.1f}", fill="#000000", font=f_input)
    draw.text((395, y), f"{fixture.weight_kg:.1f}", fill="#0284C7", font=f_reg)
    y += 28

    # Chargeable Weight
    draw_field("Chargeable Weight", f"{fixture.weight_kg:.1f}", y, 100)
    y += 28

    # Consignee Standing Inst.
    draw.text((30, y), "Consignee Standing Inst.", fill="#000000", font=f_reg)
    draw.text((236, y), "BESTARTOOLS.VN@GMAIL.COM, MS LIEN: 0383...", fill="#DC2626", font=f_input)
    y += 28

    # Shipment Remarks
    draw_field("Shipment Remarks", fixture.remark, y, 650)

    # 5. Action Buttons Grid
    by1 = height - 85
    buttons_row1 = ["SR", "Messages", "Charges", "History", "Log Book"]
    bx = 30
    for b in buttons_row1:
        draw.rectangle([(bx, by1), (bx + 85, by1 + 22)], fill="#E2E8F0", outline="#94A3B8")
        draw.text((bx + 12, by1 + 3), b, fill="#0F172A", font=f_reg)
        bx += 95

    by2 = height - 58
    buttons_row2 = ["Customs Msgs", "Billable Cust", "Reprint Rel. Note", "Print FWB"]
    bx = 30
    for b in buttons_row2:
        draw.rectangle([(bx, by2), (bx + 125, by2 + 22)], fill="#E2E8F0", outline="#94A3B8")
        draw.text((bx + 10, by2 + 3), b, fill="#0F172A", font=f_reg)
        bx += 135

    # 6. Bottom F-Keys Bar
    draw.rectangle([(0, height - 30), (width, height)], fill="#1E293B")
    f_keys = ["F2 Info", "F3 Edit", "F4 Copy", "F5 Refresh", "F6 Query", "F7 Exit"]
    fx = 20
    for fk in f_keys:
        draw.text((fx, height - 24), fk, fill="#94A3B8", font=f_reg)
        fx += 110

    return img


def get_all_fixtures() -> List[HermesFixture]:
    """Returns all 10 authoritative Hermes CMS operational fixtures."""
    return list(OPERATIONAL_FIXTURES)


def get_fixture_by_id(fixture_id: str) -> Optional[HermesFixture]:
    """Retrieve an operational fixture by its unique ID (e.g. 'FIX-01')."""
    for fix in OPERATIONAL_FIXTURES:
        if fix.fixture_id.upper() == fixture_id.upper():
            return fix
    return None


if __name__ == "__main__":
    out_dir = Path("./mock_output")
    out_dir.mkdir(exist_ok=True)
    print(f"Generating {len(OPERATIONAL_FIXTURES)} mock Hermes CMS screenshots in {out_dir}...")
    for f in OPERATIONAL_FIXTURES:
        image = generate_mock_screen(f)
        target = out_dir / f"{f.fixture_id}_{f.awb_number.replace('-', '_')}.png"
        image.save(target)
        print(f" - Generated: {target.name} ({image.width}x{image.height})")
    print("Done!")
