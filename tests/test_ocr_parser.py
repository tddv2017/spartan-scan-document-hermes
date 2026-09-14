"""Comprehensive tests for OCR engine, data parser, and 100% extraction accuracy on Mock Hermes CMS screenshots.

Verifies:
- IATA Resolution 600a Modulo-7 check digit algorithm
- OCR character normalization and international float parsing
- Regex entity extraction (AWB, Pieces/Colli, Gross Weight kg, Consignee, Agent, Remarks)
- 100% extraction accuracy across all 10 synthetic Mock Hermes CMS operational screenshots
"""

import pytest

from app.vision.ocr_engine import DualOCREngine, OCRResult
from app.vision.parser import (
    HermesDataParser,
    clean_ocr_digits,
    normalize_float,
    validate_iata_modulo7,
)
from app.vision.preprocessor import ImagePreprocessor
from tests.mock_generator import HermesFixture, generate_mock_screen, get_all_fixtures


class TestIATAModulo7Algorithm:
    """Unit tests for IATA Resolution 600a Modulo-7 check digit validator."""

    @pytest.mark.parametrize(
        "serial",
        [
            "12345675",  # 1234567 % 7 = 5
            "98765435",  # 9876543 % 7 = 5
            "45678905",  # 4567890 % 7 = 5
            "87654324",  # 8765432 % 7 = 4
            "33445565",  # 3344556 % 7 = 5
            "77889906",  # 7788990 % 7 = 6
            "11223343",  # 1122334 % 7 = 3
            "55667780",  # 5566778 % 7 = 0
            "99887760",  # 9988776 % 7 = 0
            "00000070",  # 7 % 7 = 0
        ],
    )
    def test_valid_iata_modulo7_serials(self, serial: str) -> None:
        assert validate_iata_modulo7(serial) is True

    @pytest.mark.parametrize(
        "invalid_serial",
        [
            "12345674",  # Check digit 4 != 5
            "24681359",  # Check digit 9 > 6 (impossible in mod-7)
            "12345677",  # Check digit 7 > 6
            "12345678",  # Check digit 8 > 6
            "00000001",  # 0 % 7 = 0 != 1
            "1234567",   # 7 digits only
            "123456789", # 9 digits
            "abcdefgh",  # non-numeric
            "",          # empty
        ],
    )
    def test_invalid_iata_modulo7_serials(self, invalid_serial: str) -> None:
        assert validate_iata_modulo7(invalid_serial) is False


class TestNumericCleaningAndNormalization:
    """Tests for OCR character disambiguation and decimal normalization."""

    def test_clean_ocr_digits(self) -> None:
        assert clean_ocr_digits("O2O-l234S67B") == "020-12345678"
        assert clean_ocr_digits("Z0Z") == "202"

    def test_normalize_float_standard_us(self) -> None:
        assert normalize_float("1250.50") == 1250.5
        assert normalize_float("1,250.50") == 1250.5
        assert normalize_float("95.20 KG") == 95.2

    def test_normalize_float_european_comma(self) -> None:
        assert normalize_float("125,50") == 125.5
        assert normalize_float("1.250,50") == 1250.5
        assert normalize_float("3450,00 KG") == 3450.0

    def test_normalize_float_invalid_returns_none(self) -> None:
        assert normalize_float("") is None
        assert normalize_float("ABC") is None


class TestHermesDataParserEntityExtraction:
    """Isolated string parsing tests for all individual entity extractors."""

    @pytest.fixture
    def parser(self) -> HermesDataParser:
        return HermesDataParser()

    def test_extract_awb_standard(self, parser: HermesDataParser) -> None:
        text = "Lufthansa Cargo AWB: 020-12345675 Status: Ready"
        prefix, serial, awb, valid = parser.extract_awb(text)
        assert prefix == "020"
        assert serial == "12345675"
        assert awb == "020-12345675"
        assert valid is True

    def test_extract_awb_with_ocr_digit_artifacts(self, parser: HermesDataParser) -> None:
        text = "AWB: O2O-l234S675"
        prefix, serial, awb, valid = parser.extract_awb(text)
        assert prefix == "020"
        assert serial == "12345675"
        assert awb == "020-12345675"
        assert valid is True

    def test_extract_pieces_and_weight_compound_dual_label(self, parser: HermesDataParser) -> None:
        text = "Colli / Weight: 45 / 1250.50 KG"
        pcs, wt = parser.extract_pieces_and_weight(text)
        assert pcs == 45
        assert wt == 1250.5

    def test_extract_pieces_and_weight_interleaved(self, parser: HermesDataParser) -> None:
        text = "Pieces: 15 Colli / Gross Wt: 230.75 KG"
        pcs, wt = parser.extract_pieces_and_weight(text)
        assert pcs == 15
        assert wt == 230.75

    def test_extract_consignee(self, parser: HermesDataParser) -> None:
        text = "Consignee: CONG TY TNHH LOGISTICS TOAN CAU Tel: 024-123456"
        cnee = parser.extract_consignee(text)
        assert cnee == "CONG TY TNHH LOGISTICS TOAN CAU"

    def test_extract_agent(self, parser: HermesDataParser) -> None:
        text = "Handling Agent: HAN - NCTS LOGISTICS AGENT IATA Code: 37-4-1234"
        agt = parser.extract_agent(text)
        assert agt == "HAN - NCTS LOGISTICS AGENT"

    def test_extract_remarks_and_clearance(self, parser: HermesDataParser) -> None:
        text = "Special Handling / Remarks: ALL IMP/ACC HAWB - DOCS CLEARED\nAgent Remark: HAN/RAMP-OPS"
        rmk, rmk_agt = parser.extract_remarks(text)
        assert "ALL IMP/ACC HAWB" in rmk
        assert rmk_agt == "HAN/RAMP-OPS"
        assert parser.extract_clearance_flag(text) is True

    @pytest.mark.parametrize(
        "weight_text,expected_weight",
        [
            ("125,50 KG", 125.50),
            ("125,5 kg", 125.50),
            ("Gross Wt: 125,50 KG", 125.50),
            ("Gross Wt: 125,5 kg", 125.50),
            ("Weight: 3450,75 KGS", 3450.75),
        ],
    )
    def test_extract_standalone_european_decimal_weight(
        self, parser: HermesDataParser, weight_text: str, expected_weight: float
    ) -> None:
        """Verifies standalone weights with European decimal commas parse correctly as weight, not pieces."""
        pcs, wt = parser.extract_pieces_and_weight(weight_text)
        assert pcs is None
        assert wt == expected_weight

    @pytest.mark.parametrize(
        "compound_text,expected_pcs,expected_wt",
        [
            ("10 Colli, 125,50 KG", 10, 125.50),
            ("Colli: 10, Weight: 125,50 KG", 10, 125.50),
            ("Pieces: 10, Gross Wt: 125,50 KG", 10, 125.50),
            ("10 PCS, 125,5 kg", 10, 125.50),
        ],
    )
    def test_extract_pieces_and_european_decimal_weight_compound(
        self, parser: HermesDataParser, compound_text: str, expected_pcs: int, expected_wt: float
    ) -> None:
        """Verifies pieces and European decimal comma weights parse cleanly when both fields exist."""
        pcs, wt = parser.extract_pieces_and_weight(compound_text)
        assert pcs == expected_pcs
        assert wt == expected_wt

    @pytest.mark.parametrize(
        "clearance_str",
        [
            "ALL IMP/ACCHAWB",
            "ALLIMP/ACCHAWB",
            "ALL IMP\\ACCHAWB",
            "ALL IMP|ACCHAWB",
            "ALL IMP - ACCHAWB",
        ],
    )
    def test_extract_clearance_flag_tightly_clustered_tokens(
        self, parser: HermesDataParser, clearance_str: str
    ) -> None:
        """Verifies clearance flag matches cleanly even when OCR tightly groups tokens like ACCHAWB."""
        assert parser.extract_clearance_flag(clearance_str) is True


class TestMockScreens100PercentAccuracy:
    """Critical Acceptance Test: 100% extraction accuracy across all 10 synthetic Mock Hermes CMS screenshots."""

    @pytest.fixture(scope="module")
    def ocr_engine(self) -> DualOCREngine:
        prep = ImagePreprocessor(scale_factor=2.0, apply_sharpening=True)
        engine = DualOCREngine(preprocessor=prep, prefer_engine="rapidocr")
        return engine

    @pytest.fixture(scope="module")
    def parser(self) -> HermesDataParser:
        return HermesDataParser()

    @pytest.mark.parametrize(
        "fixture",
        get_all_fixtures(),
        ids=[f.fixture_id for f in get_all_fixtures()],
    )
    def test_100_percent_mock_screen_extraction(
        self,
        fixture: HermesFixture,
        ocr_engine: DualOCREngine,
        parser: HermesDataParser,
    ) -> None:
        """Verifies that OCR + Parser achieves 100% precision on AWB, pieces, weight, and HAWB flag."""
        # Step 1: Render synthetic Hermes CMS UI screen
        img = generate_mock_screen(fixture)

        # Step 2: Execute OCR pipeline
        ocr_res = ocr_engine.recognize(img)
        assert ocr_res.has_text, f"OCR returned empty text on {fixture.fixture_id}"

        # Step 3: Parse extracted text
        parsed = parser.parse_ocr_result(ocr_res)

        # Assertion 1: AWB Number must match 100%
        assert parsed.awb_number == fixture.awb_number, (
            f"[{fixture.fixture_id}] AWB mismatch: expected '{fixture.awb_number}', got '{parsed.awb_number}'\n"
            f"Raw text:\n{ocr_res.full_text}"
        )

        # Assertion 2: Pieces count must match 100%
        assert parsed.pieces == fixture.pieces, (
            f"[{fixture.fixture_id}] Pieces mismatch: expected {fixture.pieces}, got {parsed.pieces}\n"
            f"Raw text:\n{ocr_res.full_text}"
        )

        # Assertion 3: Gross Weight (kg) must match within 0.05kg tolerance
        assert parsed.weight_kg is not None, f"[{fixture.fixture_id}] Weight was not extracted"
        assert abs(parsed.weight_kg - fixture.weight_kg) < 0.05, (
            f"[{fixture.fixture_id}] Weight mismatch: expected {fixture.weight_kg}, got {parsed.weight_kg}\n"
            f"Raw text:\n{ocr_res.full_text}"
        )

        # Assertion 4: Clearance flag ('ALL IMP/ACC HAWB') presence must match
        assert parsed.has_all_imp_acc_hawb == fixture.has_all_imp_acc_hawb, (
            f"[{fixture.fixture_id}] Clearance flag mismatch: expected {fixture.has_all_imp_acc_hawb}, got {parsed.has_all_imp_acc_hawb}"
        )

        # Assertion 5: Modulo-7 check digit validity must match
        assert parsed.is_valid_checksum == fixture.is_valid_mod7, (
            f"[{fixture.fixture_id}] Mod-7 validity mismatch: expected {fixture.is_valid_mod7}, got {parsed.is_valid_checksum}"
        )

        # Assertion 6: Destination airport code must match
        assert parsed.destination == fixture.destination, (
            f"[{fixture.fixture_id}] Destination mismatch: expected {fixture.destination}, got {parsed.destination}\n"
            f"Raw text:\n{ocr_res.full_text}"
        )

    def test_extract_destination_explicit_labels(self, parser: HermesDataParser) -> None:
        """Tests parsing destination from various Hermes screen formats."""
        assert parser.extract_destination("Dest (AOD): SGN Ho Chi Minh") == "SGN"
        assert parser.extract_destination("Dest (AOD)\nHAN\nHa Noi") == "HAN"
        assert parser.extract_destination("Destination: DAD") == "DAD"
        assert parser.extract_destination("Dest: PQC") == "PQC"
        assert parser.extract_destination("Routing: HGH-SGN") == "SGN"
        assert parser.extract_destination("FRA/HAN") == "HAN"
        assert parser.extract_destination("AWB 020-12345675") == "SGN"  # Default fallback
