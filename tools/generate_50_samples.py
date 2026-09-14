import os
import sys
import json
import random
import shutil
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, r"f:\Development\plan\hermes_vision_extractor")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from tests.mock_generator import HermesFixture, generate_hermes_h5_screen

OUTPUT_DIR = Path(r"f:\Development\plan\50_samples_test_hermes")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REAL_USER_PHOTO_PATH = Path(r"C:\Users\Dung\.gemini\antigravity\brain\211cb763-976c-4828-883e-3255e7041975\.user_uploaded\media_1789401552454.png")

AIRLINES = [
    ("160", "Cathay Cargo"),
    ("020", "Lufthansa Cargo"),
    ("738", "Vietnam Airlines Cargo"),
    ("618", "Singapore Airlines"),
    ("157", "Qatar Airways Cargo"),
    ("180", "Korean Air Cargo"),
    ("176", "Emirates SkyCargo"),
    ("057", "Air France Cargo"),
    ("217", "Thai Airways Cargo"),
    ("988", "Asiana Airlines"),
]

CONSIGNEES = [
    "VIETNAM BESTAR TOOLS CO LTD",
    "CONG TY TNHH SAMSUNG ELECTRONICS VIETNAM",
    "SCHENKER VIETNAM CO LTD - SGN BRANCH",
    "EXPEDITORS VIETNAM CO LTD - HAN AIRPORT",
    "DHL GLOBAL FORWARDING VIETNAM",
    "FOXCONN BAC GIANG PRECISION TECHNOLOGY",
    "LG DISPLAY VIETNAM HAI PHONG CO LTD",
    "PANALPINA DSV AIR & SEA VIETNAM",
    "KUEHNE + NAGEL VIETNAM LOGISTICS",
    "NIPPON EXPRESS VIETNAM CO LTD",
    "YUSEN LOGISTICS VIETNAM CO LTD",
    "CONG TY TNHH CANON VIETNAM",
    "CONG TY TNHH PEGATRON VIETNAM",
    "CONG TY CO PHAN GIAO NHAN KHO VAN NGOAI THUONG (VINATRANS)",
    "CONG TY TNHH LOGISTICS TOAN CAU VIETNAM",
    "DB SCHENKER LOGISTICS LOGS-OPS",
]

AGENTS = [
    "IMP - PRIVATE IMPORTER",
    "HAN - NCTS CARGO HANDLING AGENT",
    "SGN - SCSC CARGO TERMINAL SERVICES",
    "SGN - TCS LOGISTICS WAREHOUSE",
    "HAN - ASc CARGO TERMINAL",
    "HAN - EXPEDITORS INTL LOGISTICS",
    "SGN - SCHENKER AIR FREIGHT AGENT",
    "HAN - DHL GLOBAL FORWARDING TEAM",
    "SGN - KINTETSU WORLD EXPRESS",
    "HAN - NIPPON EXPRESS HAN-WHSE",
    "SGN - PANALPINA AIR IMPORT DEPT",
]

REMARKS_CLEARED = [
    "ALL IMP/ACC HAWB - CUSTOMS CLEARED - READY FOR DELIVERY",
    "ALL IMP/ACC HAWB",
    "ALL IMP / ACC HAWB - DOCS RELEASED BY AGENT",
    "ALL IMP/ACC  HAWB - CARGO RELEASE CONFIRMED",
    "ALL IMP/ACC HAWB - GREEN CHANNEL CUSTOMS",
    "ALL IMP / ACC  HAWB - FULL SHIPMENT CLEARED",
    "ALL IMP/ACC HAWB - DO ISSUED BY FORWARDER",
    "ALL IMP/ACC HAWB - AIRPORT WAREHOUSE RELEASE",
]

REMARKS_OTHER = [
    "NO DOCS//CFM//KHACH XIN TBHD 12MAY",
    "DIRECT SHIPMENT - NO HOUSE AWB REQUIRED",
    "PENDING HOUSE AWB CREATION IN SYSTEM",
    "HOLD FOR PHYSICAL INSPECTION (RED CHANNEL)",
    "AWAITING ORIGINAL COMMERCIAL INVOICE",
    "DOCUMENTS WITH CUSTOMS BROKER - NOT YET CLEARED",
    "CARGO ARRIVED - HAWB MANIFEST UNCONFIRMED",
    "SPECIAL PERMIT REQUIRED FROM MINISTRY",
]

def make_iata_mod7_serial(base_7_digits: int, make_valid: bool = True) -> str:
    """Generate 8-digit serial where last digit is base % 7 (or invalid if false)"""
    rem = base_7_digits % 7
    if not make_valid:
        rem = (rem + 1) % 7
    return f"{base_7_digits:07d}{rem}"

def generate_50_fixtures():
    fixtures = []
    
    # ---------------------------------------------------------
    # SMP-01: Exact Real Hermes H5 Fixture from User Photo
    # ---------------------------------------------------------
    smp01 = HermesFixture(
        fixture_id="SMP-01",
        awb_number="160-11327083",
        pieces=129,
        weight_kg=2406.0,
        pieces_label="129",
        weight_label="2406.0",
        consignee="VIETNAM BESTAR TOOLS CO LTD",
        agent="IMP - PRIVATE IMPORTER",
        remark="NO DOCS//CFM//KHACH XIN TBHD 12MAY",
        remark_agent="HGH/OPS",
        has_all_imp_acc_hawb=False,
        is_valid_mod7=True,
        expected_status="PENDING_HAWB",
        airline_name="Cathay Cargo",
        description="Mẫu thực tế Hermes H5 (Cathay Cargo 160-11327083, 129 pcs, 2406.0 kg, Vietnam Bestar Tools)"
    )
    fixtures.append(smp01)

    for i in range(2, 51):
        f_id = f"SMP-{i:02d}"
        prefix, airline = random.choice(AIRLINES)
        
        # Determine case type:
        # 2-35: Valid Mod7 + ALL IMP/ACC HAWB (CLEARED)
        # 36-45: Valid Mod7 + Other Remarks (PENDING_HAWB / DIRECT)
        # 46-50: Invalid Mod7 checksum (CHECKSUM_WARNING)
        if i <= 35:
            is_valid = True
            has_cleared = True
            remark = random.choice(REMARKS_CLEARED)
            expected_status = "CLEARED"
        elif i <= 45:
            is_valid = True
            has_cleared = False
            remark = random.choice(REMARKS_OTHER)
            expected_status = "PENDING_HAWB" if ("HAWB" in remark or "DOCS" in remark) else "DIRECT"
        else:
            is_valid = False
            has_cleared = random.choice([True, False])
            remark = random.choice(REMARKS_CLEARED if has_cleared else REMARKS_OTHER)
            expected_status = "CHECKSUM_ERROR"

        # Unique 7 digits
        base_num = 1000000 + i * 13579 + random.randint(100, 999)
        serial = make_iata_mod7_serial(base_num, make_valid=is_valid)
        awb_number = f"{prefix}-{serial}"

        pieces = random.choice([1, 2, 5, 12, 25, 45, 80, 120, 129, 250, 380, 500])
        use_colli = random.random() > 0.6
        pieces_label = f"{pieces} Colli" if use_colli else f"{pieces} PCS"

        weight = round(pieces * random.uniform(8.5, 42.0) + random.uniform(0.1, 0.9), 1)
        weight_label = f"{weight:.1f} KG"

        consignee = random.choice(CONSIGNEES)
        agent = random.choice(AGENTS)
        remark_agent = f"{agent[:3]}/OPS-STAFF-{random.randint(10, 99)}"

        fixture = HermesFixture(
            fixture_id=f_id,
            awb_number=awb_number,
            pieces=pieces,
            weight_kg=weight,
            pieces_label=pieces_label,
            weight_label=weight_label,
            consignee=consignee,
            agent=agent,
            remark=remark,
            remark_agent=remark_agent,
            has_all_imp_acc_hawb=has_cleared,
            is_valid_mod7=is_valid,
            expected_status=expected_status,
            airline_name=airline,
            description=f"Mẫu số {i:02d} - Hãng {airline} - Trạng thái: {expected_status}"
        )
        fixtures.append(fixture)
        
    return fixtures

def main():
    print("Bắt đầu khởi tạo 50 mẫu ảnh giao diện Hermes 5 (H5) CMS...")
    fixtures = generate_50_fixtures()
    manifest = []

    # Copy real photo from user if available
    real_photo_dest = OUTPUT_DIR / "SMP-01_REAL_H5_PHOTO.png"
    if REAL_USER_PHOTO_PATH.exists():
        shutil.copy2(REAL_USER_PHOTO_PATH, real_photo_dest)
        print(f"Đã sao chép ảnh chụp thực tế H5 sang: {real_photo_dest}")

    for idx, fix in enumerate(fixtures, 1):
        img = generate_hermes_h5_screen(fix, width=1024, height=680)
        img_filename = f"{fix.fixture_id}_{fix.awb_number.replace('-', '_')}.png"
        img_path = OUTPUT_DIR / img_filename
        img.save(str(img_path), format="PNG")

        entry = {
            "stt": idx,
            "id": fix.fixture_id,
            "filename": img_filename,
            "awb_number": fix.awb_number,
            "airline": fix.airline_name,
            "pieces": fix.pieces,
            "weight_kg": fix.weight_kg,
            "consignee": fix.consignee,
            "agent": fix.agent,
            "remark": fix.remark,
            "has_all_imp_acc_hawb": fix.has_all_imp_acc_hawb,
            "is_valid_mod7": fix.is_valid_mod7,
            "expected_status": fix.expected_status,
            "file_path": str(img_path)
        }
        if fix.fixture_id == "SMP-01":
            entry["real_photo"] = "SMP-01_REAL_H5_PHOTO.png"
            entry["note"] = "Mẫu gốc chụp trực tiếp từ màn hình Hermes 5 (H5)"

        manifest.append(entry)

    # Save manifest JSON
    manifest_path = OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Đã tạo thành công 50 mẫu ảnh chuẩn Hermes 5 (H5) tại: {OUTPUT_DIR}")
    print(f"Tạo file danh mục đối chiếu: {manifest_path}")

if __name__ == "__main__":
    main()
