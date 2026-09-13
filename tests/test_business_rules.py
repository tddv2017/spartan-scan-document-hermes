"""Comprehensive unit and scenario tests for Business Rule Classification.

Verifies the business rule classification engine according to:
- ORIGINAL_REQUEST.md § R2 & R3
- PROJECT.md F11 & F12
- spec_miner_survey_1 / explorer_survey_3 domain rules

Tests exact, delimiter-variant, OCR-artifact, case-insensitive, negated,
consolidation-pending, direct-shipment, and checksum-error scenarios.
"""

import pytest

from app.core.classifier import BusinessRuleClassifier
from app.core.models import AWBRecord, BusinessStatus, ExtractionResult


class TestClearanceFlagEvaluation:
    """Tests evaluate_clearance_flag for 'ALL IMP/ACC HAWB' pattern matching."""

    @pytest.mark.parametrize(
        "remark_input",
        [
            "ALL IMP/ACC HAWB",
            "all imp/acc hawb",
            "All Imp/Acc Hawb",
            "ALL IMP / ACC HAWB",
            "ALL  IMP  /  ACC  HAWB",
            "ALL IMP\\ACC HAWB",
            "ALL IMP\\ ACC HAWB",
            "ALL IMP|ACC HAWB",
            "ALL IMP | ACC HAWB",
            "ALL IMP-ACC HAWB",
            "ALL IMP - ACC HAWB",
            "NOC RECEIVED. ALL IMP/ACC HAWB. PLS RELEASE CARGO TO BROKER.",
            "ALL IMP/ACC HAWB - DOCS DELIVERED - CUSTOMS CLEARED",
            "CHECKED ON TERMINAL SYSTEM: ALL IMP/ACC HAWB OK",
            "ALL 1MP/ACC HAWB",  # OCR digit 1 substitution for I
            "A11 IMP/ACC HAWB",  # OCR digit 1 substitution for L
            "ALL IMP/ACCHAWB",  # Tightly clustered OCR tokens without whitespace
            "ALLIMP/ACCHAWB",  # Clustered prefix and suffix
            "ALL IMP\\ACCHAWB",  # Clustered backslash variation
            "ALL IMP|ACCHAWB",  # Clustered pipe variation
            "ALL IMP-ACCHAWB",  # Clustered dash variation
        ],
    )
    def test_clearance_flag_positive_matches(self, remark_input: str) -> None:
        """Verifies that all valid variations of ALL IMP/ACC HAWB return True."""
        assert BusinessRuleClassifier.evaluate_clearance_flag(remark_input) is True

    @pytest.mark.parametrize(
        "negated_input",
        [
            "NOT ALL IMP/ACC HAWB",
            "not all imp/acc hawb",
            "NON ALL IMP/ACC HAWB",
            "PARTIAL ALL IMP/ACC HAWB - MISSING HAWB 02",
            "UN ALL IMP/ACC HAWB",
            "WAITING FOR ALL IMP/ACC HAWB",
            "PENDING ALL IMP/ACC HAWB APPROVAL",
        ],
    )
    def test_clearance_flag_negations(self, negated_input: str) -> None:
        """Verifies that explicit negations or partial clearance strings return False."""
        assert BusinessRuleClassifier.evaluate_clearance_flag(negated_input) is False

    @pytest.mark.parametrize(
        "incomplete_input",
        [
            "",
            "   ",
            "ALL IMP/ACC",
            "IMP/ACC HAWB",
            "ALL HAWB CLEARED",
            "HAWB ACCEPTED",
            "DOCS READY",
            "CUSTOMS CLEARED",
            "DIRECT MASTER - NO HAWB",
            "GENERAL CARGO ONLY",
        ],
    )
    def test_clearance_flag_negative_or_incomplete(self, incomplete_input: str) -> None:
        """Verifies that incomplete strings or unrelated remarks return False."""
        assert BusinessRuleClassifier.evaluate_clearance_flag(incomplete_input) is False


class TestConsolidationShipmentDetection:
    """Tests is_consolidation_shipment for identifying shipments requiring HAWBs."""

    @pytest.mark.parametrize(
        "remark_input",
        [
            "CONSOLIDATION SHIPMENT",
            "consol cargo from FRA",
            "MULTI-HOUSE SHIPMENT",
            "5 HOUSE BILLS ATTACHED",
            "MASTER/HOUSE SPLIT",
            "HOUSES UNDER INSPECTION",
            "AWAITING HAWB 01 AND 02",
        ],
    )
    def test_consolidation_positive(self, remark_input: str) -> None:
        """Verifies that consolidation keywords return True."""
        assert BusinessRuleClassifier.is_consolidation_shipment(remark_input) is True

    @pytest.mark.parametrize(
        "remark_input",
        [
            "",
            "DIRECT MASTER SHIPMENT",
            "GENERAL CARGO",
            "PERISHABLE - TEMP CONTROLLED +2 TO +8C",
            "DIPLOMATIC POUCH",
            "DIRECT SHIPMENT - NO HAWB REQUIRED",
            "DIRECT MASTER - NO HAWB",
            "DIRECT SHIPMENT",
            "NO HAWB",
            "HAWB NOT REQUIRED",
            "GENERAL CARGO - NO HAWBS",
            "DIRECT - HAWB NOT APPLICABLE",
        ],
    )
    def test_consolidation_negative(self, remark_input: str) -> None:
        """Verifies that non-consolidation remarks return False."""
        assert BusinessRuleClassifier.is_consolidation_shipment(remark_input) is False


class TestClassificationPrecedence:
    """Tests the 4-state operational precedence rules of BusinessRuleClassifier.classify."""

    def test_rule_1_checksum_error_takes_highest_precedence(self) -> None:
        """Even if 'ALL IMP/ACC HAWB' is present, Mod-7 failure must yield CHECKSUM_ERROR."""
        status = BusinessRuleClassifier.classify(
            has_all_imp_acc_hawb=True,
            is_valid_checksum=False,
            remark_text="ALL IMP/ACC HAWB",
        )
        assert status == BusinessStatus.CHECKSUM_ERROR

    def test_rule_2_valid_clearance_grants_cleared_status(self) -> None:
        """Valid checksum + un-negated clearance flag must yield CLEARED."""
        status = BusinessRuleClassifier.classify(
            has_all_imp_acc_hawb=True,
            is_valid_checksum=True,
            remark_text="ALL IMP/ACC HAWB - DOCS DELIVERED",
        )
        assert status == BusinessStatus.CLEARED

    def test_rule_3_consolidation_without_clearance_yields_pending_hawb(self) -> None:
        """Valid checksum + consolidation keywords - clearance flag must yield PENDING_HAWB."""
        status = BusinessRuleClassifier.classify(
            has_all_imp_acc_hawb=False,
            is_valid_checksum=True,
            remark_text="CONSOL SHIPMENT - 4 HOUSE BILLS",
        )
        assert status == BusinessStatus.PENDING_HAWB

    def test_rule_3_negated_clearance_on_consolidation_yields_pending_hawb(self) -> None:
        """Negated clearance on consolidation must yield PENDING_HAWB, never CLEARED."""
        status = BusinessRuleClassifier.classify(
            has_all_imp_acc_hawb=True,  # Initially flagged True by loose OCR
            is_valid_checksum=True,
            remark_text="PARTIAL ALL IMP/ACC HAWB - CONSOL INCOMPLETE",
        )
        assert status == BusinessStatus.PENDING_HAWB

    def test_rule_4_standard_direct_shipment_yields_direct(self) -> None:
        """Valid checksum + no clearance + no consolidation keywords must yield DIRECT_SHIPMENT."""
        status = BusinessRuleClassifier.classify(
            has_all_imp_acc_hawb=False,
            is_valid_checksum=True,
            remark_text="DIRECT SHIPMENT - GENERAL CARGO ONLY",
        )
        assert status == BusinessStatus.DIRECT_SHIPMENT

    def test_rule_4_direct_shipment_with_no_hawb_remark_yields_direct(self) -> None:
        """Phrases with 'NO HAWB' or 'DIRECT' must never trigger PENDING_HAWB."""
        for remark in [
            "DIRECT SHIPMENT - NO HAWB REQUIRED",
            "DIRECT MASTER - NO HAWB",
            "DIRECT SHIPMENT",
            "NO HAWB",
            "HAWB NOT REQUIRED",
        ]:
            status = BusinessRuleClassifier.classify(
                has_all_imp_acc_hawb=False,
                is_valid_checksum=True,
                remark_text=remark,
            )
            assert status == BusinessStatus.DIRECT_SHIPMENT, f"Failed for remark: {remark}"

    def test_rule_4_empty_remark_yields_direct(self) -> None:
        """Empty remark on valid checksum must yield DIRECT_SHIPMENT."""
        status = BusinessRuleClassifier.classify(
            has_all_imp_acc_hawb=False,
            is_valid_checksum=True,
            remark_text="",
        )
        assert status == BusinessStatus.DIRECT_SHIPMENT


class TestModelClassifiers:
    """Tests classify_record and classify_extraction helper methods."""

    def test_classify_record_cleared(self) -> None:
        rec = AWBRecord(
            awb_number="020-12345675",
            is_valid_checksum=True,
            has_all_imp_acc_hawb=True,
            raw_remarks="ALL IMP/ACC HAWB - PASSED",
        )
        assert BusinessRuleClassifier.classify_record(rec) == BusinessStatus.CLEARED

    def test_classify_record_checksum_error(self) -> None:
        rec = AWBRecord(
            awb_number="020-12345674",
            is_valid_checksum=False,
            has_all_imp_acc_hawb=True,
            raw_remarks="ALL IMP/ACC HAWB",
        )
        assert BusinessRuleClassifier.classify_record(rec) == BusinessStatus.CHECKSUM_ERROR

    def test_classify_extraction_pending(self) -> None:
        ext = ExtractionResult(
            awb_number="020-87654324",
            is_valid_checksum=True,
            has_all_imp_acc_hawb=False,
            remark="CONSOLIDATION CARGO",
        )
        assert BusinessRuleClassifier.classify_extraction(ext) == BusinessStatus.PENDING_HAWB


class TestBadgeMetadata:
    """Tests UI badge color and label metadata generation for all statuses."""

    @pytest.mark.parametrize(
        "status,expected_bg,expected_symbol",
        [
            (BusinessStatus.CLEARED, "#28A745", "✓"),
            (BusinessStatus.PENDING_HAWB, "#FD7E14", "!"),
            (BusinessStatus.DIRECT_SHIPMENT, "#0D6EFD", "—"),
            (BusinessStatus.CHECKSUM_ERROR, "#DC3545", "✗"),
        ],
    )
    def test_badge_metadata_colors_and_symbols(
        self, status: BusinessStatus, expected_bg: str, expected_symbol: str
    ) -> None:
        meta = BusinessRuleClassifier.get_badge_metadata(status)
        assert meta["bg_color"] == expected_bg
        assert meta["symbol"] == expected_symbol
        assert "label" in meta
        assert "label_vn" in meta
        assert "description" in meta
