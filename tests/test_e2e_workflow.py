"""Comprehensive End-to-End Pipeline Integration Test Suite.

Verifies the complete 6-stage operational pipeline:
Mock Screen -> Capture -> Preprocessor -> OCR Engine -> Data Parser -> Business Classifier -> Session Store -> PDF Generation
"""

import os
from pathlib import Path
from typing import List
from pypdf import PdfReader
import pytest

from app.capture.screen_grabber import ScreenGrabber
from app.core.classifier import BusinessRuleClassifier
from app.core.models import AWBRecord, BusinessStatus, ExtractionResult
from app.core.session_store import SessionStore
from app.vision.ocr_engine import DualOCREngine
from app.vision.parser import HermesDataParser
from app.vision.preprocessor import ImagePreprocessor
from tests.mock_generator import (
    HermesFixture,
    generate_mock_screen,
    get_fixture_by_id,
)
from tests.test_pdf_generator import build_reference_handover_pdf


class TestE2EWorkflowPipeline:
    """End-to-End pipeline execution tests."""

    @pytest.fixture(scope="module")
    def preprocessor(self) -> ImagePreprocessor:
        return ImagePreprocessor(scale_factor=2.0, apply_sharpening=True)

    @pytest.fixture(scope="module")
    def ocr_engine(self, preprocessor: ImagePreprocessor) -> DualOCREngine:
        return DualOCREngine(preprocessor=preprocessor, prefer_engine="rapidocr")

    @pytest.fixture(scope="module")
    def parser(self) -> HermesDataParser:
        return HermesDataParser()

    def test_single_scan_pipeline_e2e(
        self,
        ocr_engine: DualOCREngine,
        parser: HermesDataParser,
        temp_output_dir: Path,
    ) -> None:
        """Executes full lifecycle for a single Lufthansa Cargo shipment (FIX-01)."""
        # Step 1: Synthesize Hermes CMS screen
        fixture = get_fixture_by_id("FIX-01")
        assert fixture is not None
        mock_img = generate_mock_screen(fixture)

        # Step 2: Screen Grabber with mock injection
        grabber = ScreenGrabber()
        grabber.set_test_mock_image(mock_img)
        captured_img, win_title = grabber.capture_active_window()
        assert captured_img is not None
        assert captured_img.size == mock_img.size

        # Step 3: Vision Preprocessing & OCR
        ocr_res = ocr_engine.recognize(captured_img)
        assert ocr_res.has_text

        # Step 4: Domain Data Parser
        extraction = parser.parse_ocr_result(ocr_res)
        assert extraction.awb_number == "020-12345675"
        assert extraction.pieces == 45
        assert abs(extraction.weight_kg - 1250.5) < 0.05
        assert extraction.has_all_imp_acc_hawb is True
        assert extraction.is_valid_checksum is True

        # Step 5: Business Rule Classification
        status = BusinessRuleClassifier.classify_extraction(extraction)
        assert status == BusinessStatus.CLEARED

        # Step 6: Session Store Registration
        store = SessionStore()
        record = AWBRecord.from_extraction_result(extraction, status_tag=status)
        store.add_record(record)
        assert store.count() == 1

        summary = store.get_summary()
        assert summary.total_records == 1
        assert summary.cleared_count == 1
        assert summary.total_pieces == 45

        # Step 7: A4 PDF Handover Generation & Verification
        pdf_path = str(temp_output_dir / "single_scan_handover.pdf")
        build_reference_handover_pdf(store.get_all_records(), pdf_path)

        assert os.path.exists(pdf_path)
        reader = PdfReader(pdf_path)
        box = reader.pages[0].mediabox
        assert abs(float(box.width) - 595.28) < 1.0
        assert abs(float(box.height) - 841.89) < 1.0

        pdf_text = reader.pages[0].extract_text()
        assert "020-12345675" in pdf_text
        assert "45" in pdf_text
        assert "1250.50" in pdf_text
        assert "CLEARED" in pdf_text or "ĐÃ DUYỆT HAWB" in pdf_text

    def test_full_shift_multi_awb_handover_e2e(
        self,
        ocr_engine: DualOCREngine,
        parser: HermesDataParser,
        temp_output_dir: Path,
    ) -> None:
        """Simulates an entire operational shift with 5 diverse shipments."""
        shift_fixture_ids = ["FIX-01", "FIX-02", "FIX-04", "FIX-05", "FIX-10"]
        store = SessionStore()
        grabber = ScreenGrabber()

        for fid in shift_fixture_ids:
            fix = get_fixture_by_id(fid)
            assert fix is not None

            # Capture mock screen
            mock_img = generate_mock_screen(fix)
            grabber.set_test_mock_image(mock_img)
            img, _ = grabber.capture_active_window()

            # OCR & Parse
            ocr_res = ocr_engine.recognize(img)
            extraction = parser.parse_ocr_result(ocr_res)

            # Classify & Upsert into session store
            status = BusinessRuleClassifier.classify_extraction(extraction)
            rec = AWBRecord.from_extraction_result(extraction, status_tag=status)
            store.upsert_record(rec)

        # Verify aggregate shift metrics
        assert store.count() == 5
        summary = store.get_summary()
        assert summary.total_records == 5
        assert summary.cleared_count == 2          # FIX-01, FIX-02
        assert summary.pending_hawb_count == 1     # FIX-04
        assert summary.direct_count == 1           # FIX-05
        assert summary.checksum_error_count == 1   # FIX-10

        # Simulate manual correction on FIX-05 by operator
        rec_fix05 = store.get_by_awb("020-33445565")
        assert rec_fix05 is not None
        store.update_record(rec_fix05.id, {"pieces": 2, "weight_kg": 25.0})
        updated_fix05 = store.get_by_awb("020-33445565")
        assert updated_fix05.pieces == 2
        assert updated_fix05.weight_kg == 25.0
        assert updated_fix05.is_manually_edited is True

        # Export full shift handover PDF
        pdf_path = str(temp_output_dir / "full_shift_handover.pdf")
        build_reference_handover_pdf(
            store.get_all_records(),
            pdf_path,
            shift_name="Ca 2 - Trực Đêm",
            handover_person="Lê Văn Giao (Trưởng Ca)",
            receiver_person="Phạm Thị Nhận (Trưởng Ca Sáng)",
        )

        assert os.path.exists(pdf_path)
        reader = PdfReader(pdf_path)
        assert len(reader.pages) >= 1
        full_text = "\n".join([p.extract_text() for p in reader.pages])

        # Assert all 5 AWBs appear in handover report
        assert "020-12345675" in full_text
        assert "020-98765435" in full_text
        assert "020-87654324" in full_text
        assert "020-33445565" in full_text
        assert "020-24681359" in full_text

        # Assert 3-tier signature block
        assert "BÊN GIAO CA" in full_text
        assert "BÊN NHẬN CA" in full_text
        assert "GIÁM SÁT HẢI QUAN / KHO" in full_text
        assert "Lê Văn Giao" in full_text

    def test_duplicate_scan_rescan_behavior_e2e(
        self,
        ocr_engine: DualOCREngine,
        parser: HermesDataParser,
    ) -> None:
        """Verifies deduplication when an operator rescans an AWB after HAWB clearance."""
        store = SessionStore()

        # First scan: Consolidation prior to HAWB clearance
        fix_pending = get_fixture_by_id("FIX-04")
        img_pending = generate_mock_screen(fix_pending)
        ocr_1 = ocr_engine.recognize(img_pending)
        ext_1 = parser.parse_ocr_result(ocr_1)
        rec_1 = AWBRecord.from_extraction_result(
            ext_1, status_tag=BusinessRuleClassifier.classify_extraction(ext_1)
        )
        store.upsert_record(rec_1)

        assert store.count() == 1
        assert store.get_by_awb(fix_pending.awb_number).status_tag == BusinessStatus.PENDING_HAWB

        # Second scan: Operator rescans the same AWB once HAWBs are accepted
        # Create an updated fixture with ALL IMP/ACC HAWB
        updated_fix = HermesFixture(
            fixture_id="FIX-04-UPDATED",
            awb_number=fix_pending.awb_number,
            pieces=fix_pending.pieces,
            weight_kg=fix_pending.weight_kg,
            pieces_label=fix_pending.pieces_label,
            weight_label=fix_pending.weight_label,
            consignee=fix_pending.consignee,
            agent=fix_pending.agent,
            remark="ALL IMP/ACC  HAWB - CARGO RELEASED BY CUSTOMS",
            remark_agent="HAN/DOCS-TEAM",
            has_all_imp_acc_hawb=True,
            is_valid_mod7=True,
            expected_status="CLEARED",
        )
        img_updated = generate_mock_screen(updated_fix)
        ocr_2 = ocr_engine.recognize(img_updated)
        ext_2 = parser.parse_ocr_result(ocr_2)
        rec_2 = AWBRecord.from_extraction_result(
            ext_2, status_tag=BusinessRuleClassifier.classify_extraction(ext_2)
        )
        merged, is_new = store.upsert_record(rec_2)

        # Assert no duplicate record created, and status is elevated to CLEARED
        assert is_new is False
        assert store.count() == 1
        assert merged.status_tag == BusinessStatus.CLEARED
        assert merged.has_all_imp_acc_hawb is True
