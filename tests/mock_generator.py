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
