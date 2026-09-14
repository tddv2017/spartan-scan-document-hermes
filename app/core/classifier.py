"""Business Rule Classification Engine.

Implements domain-specific rule evaluation for air cargo operations in Hermes CMS.
Classifies shipments into CLEARED, PENDING_HAWB, DIRECT_SHIPMENT, or CHECKSUM_ERROR.
"""

import re
from typing import Any, Dict, Optional

from app.core.models import AWBRecord, BusinessStatus, ExtractionResult


class BusinessRuleClassifier:
    """Classifies air cargo records based on IATA checksum, HAWB acceptance flags, and remarks."""

    # Robust regex for ALL IMP/ACC HAWB matching across spacing, slashes, backslashes, pipes, and OCR artifacts
    CANONICAL_CLEARANCE_REGEX = re.compile(
        r"(?i)\b(?:ALL|A[L1I]{2})\s*(?:IMP|[I1L]MP)\s*[\/\\|\-I1l!]?\s*(?:ACC|A[C0]{2})\s*(?:HAWB|HAW[B8])\b"
    )

    # Negation patterns that disqualify clearance even if the words appear
    NEGATION_PREFIX_REGEX = re.compile(
        r"(?i)\b(?:NOT|NON|PARTIAL|UN|WAITING\s+FOR|PENDING)\s+(?:ALL|A[L1I]{2})\s*(?:IMP|[I1L]MP)\s*[\/\\|\-I1l!]?\s*(?:ACC|A[C0]{2})\s*(?:HAWB|HAW[B8])\b"
    )

    # Consolidation keywords indicating a shipment has multiple House Air Waybills
    CONSOLIDATION_KEYWORDS = [
        "HAWB",
        "HOUSE",
        "CONSOL",
        "CONSOLIDATION",
        "MULTI-HOUSE",
        "HOUSE BILL",
        "MASTER/HOUSE",
        "HOUSES",
    ]

    # Exclusion keywords/patterns representing direct single shipments or lack of house bills,
    # preventing phrases like "NO HAWB", "DIRECT", or "DIRECT SHIPMENT" from triggering consolidation.
    DIRECT_EXCLUSION_KEYWORDS = [
        "NO HAWB",
        "DIRECT",
        "DIRECT SHIPMENT",
        "DIRECT MASTER",
        "DIRECT MAWB",
        "WITHOUT HAWB",
    ]
    DIRECT_EXCLUSION_REGEX = re.compile(
        r"(?i)\b(?:NO\s+HAWBS?|WITHOUT\s+HAWBS?|HAWBS?\s+NOT\s+REQUIRED|HAWBS?\s+N\/?A|DIRECT\s+SHIPMENTS?|DIRECT\s+MASTER|DIRECT\s+MAWB|DIRECT)\b"
    )

    @classmethod
    def evaluate_clearance_flag(cls, remark_text: str) -> bool:
        """Determines if the remark contains a genuine, un-negated ALL IMP/ACC HAWB flag."""
        if not remark_text:
            return False

        # If explicitly negated or marked partial, clearance is False
        if cls.NEGATION_PREFIX_REGEX.search(remark_text):
            return False

        # Match the canonical flag
        return bool(cls.CANONICAL_CLEARANCE_REGEX.search(remark_text))

    @classmethod
    def is_consolidation_shipment(cls, remark_text: str) -> bool:
        """Checks whether remarks indicate this is a consolidated shipment requiring HAWBs.

        Excludes phrases like 'NO HAWB', 'DIRECT', or 'DIRECT SHIPMENT' from triggering
        consolidation status even when the word 'HAWB' is present.
        """
        if not remark_text:
            return False

        # Exclude direct shipments and explicit no-HAWB declarations
        if cls.DIRECT_EXCLUSION_REGEX.search(remark_text):
            return False

        upper_text = remark_text.upper()
        return any(keyword in upper_text for keyword in cls.CONSOLIDATION_KEYWORDS)

    @classmethod
    def classify(
        cls,
        has_all_imp_acc_hawb: bool,
        is_valid_checksum: bool,
        remark_text: str = "",
        destination: str = "SGN",
    ) -> BusinessStatus:
        """Classifies a record into discrete business statuses.

        Precedence rules:
        1. Checksum error takes highest operational warning precedence (Red).
        2. Destination mismatch (Destination is NOT SGN) triggers immediate RED alert.
        3. Clearance flag (ALL IMP/ACC HAWB) grants CLEARED status (Green).
        4. Consolidation indicators without clearance flag yield PENDING_HAWB (Orange).
        5. Standard single shipments without consolidation indicators are DIRECT_SHIPMENT (Blue).
        """
        # Rule 1: Modulo-7 checksum failure
        if not is_valid_checksum:
            return BusinessStatus.CHECKSUM_ERROR

        # Rule 2: Destination check - must match SGN (Tan Son Nhat)
        # Any destination other than SGN triggers immediate RED alert ("ngoài SGN báo đỏ hết")
        dest_code = (destination or "SGN").strip().upper()
        if dest_code != "SGN":
            return BusinessStatus.DESTINATION_MISMATCH

        # Rule 3: Re-verify clearance flag with text if provided
        verified_clearance = has_all_imp_acc_hawb
        if remark_text:
            if cls.NEGATION_PREFIX_REGEX.search(remark_text):
                verified_clearance = False
            elif cls.evaluate_clearance_flag(remark_text):
                verified_clearance = True

        if verified_clearance:
            return BusinessStatus.CLEARED

        # Rule 4: Check if this is a consolidation shipment lacking full clearance
        if cls.is_consolidation_shipment(remark_text):
            return BusinessStatus.PENDING_HAWB

        # Rule 5: Direct Master Air Waybill shipment
        return BusinessStatus.DIRECT_SHIPMENT

    @classmethod
    def classify_record(cls, record: AWBRecord) -> BusinessStatus:
        """Classifies an existing AWBRecord."""
        return cls.classify(
            has_all_imp_acc_hawb=record.has_all_imp_acc_hawb,
            is_valid_checksum=record.is_valid_checksum,
            remark_text=record.raw_remarks,
            destination=record.destination,
        )

    @classmethod
    def classify_extraction(cls, result: ExtractionResult) -> BusinessStatus:
        """Classifies an ExtractionResult before conversion to record."""
        return cls.classify(
            has_all_imp_acc_hawb=result.has_all_imp_acc_hawb,
            is_valid_checksum=result.is_valid_checksum,
            remark_text=result.remark,
            destination=result.destination,
        )

    @classmethod
    def get_badge_metadata(cls, status: BusinessStatus) -> Dict[str, Any]:
        """Provides visual UI badge metadata (labels, colors, icons) for each status."""
        badge_configs = {
            BusinessStatus.CLEARED: {
                "label": "ALL IMP/ACC HAWB",
                "label_vn": "ĐÃ DUYỆT HAWB",
                "bg_color": "#28A745",
                "fg_color": "#FFFFFF",
                "symbol": "✓",
                "description": "Toàn bộ HAWB đã duyệt chấp nhận. Đủ điều kiện dỡ và giao hàng.",
            },
            BusinessStatus.PENDING_HAWB: {
                "label": "CHƯA ĐỦ HAWB",
                "label_vn": "CHỜ DUYỆT HAWB",
                "bg_color": "#FD7E14",
                "fg_color": "#FFFFFF",
                "symbol": "!",
                "description": "Lô hàng gom (Consol) chưa hoàn tất duyệt HAWB. Tạm dừng bàn giao.",
            },
            BusinessStatus.DIRECT_SHIPMENT: {
                "label": "VẬN ĐƠN TRỰC TIẾP",
                "label_vn": "HÀNG TRỰC TIẾP",
                "bg_color": "#0D6EFD",
                "fg_color": "#FFFFFF",
                "symbol": "—",
                "description": "Hàng vận đơn đơn lẻ (Direct MAWB), không có House bill phụ.",
            },
            BusinessStatus.CHECKSUM_ERROR: {
                "label": "LỖI SỐ AWB (MOD-7)",
                "label_vn": "SAI SỐ AWB",
                "bg_color": "#DC3545",
                "fg_color": "#FFFFFF",
                "symbol": "✗",
                "description": "Số AWB không khớp thuật toán IATA Mod-7. Cần kiểm tra đối chiếu.",
            },
            BusinessStatus.DESTINATION_MISMATCH: {
                "label": "SAI ĐIỂM ĐẾN (KHÔNG PHẢI SGN)",
                "label_vn": "SAI ĐIỂM ĐẾN (!= SGN)",
                "bg_color": "#DC2626",
                "fg_color": "#FFFFFF",
                "symbol": "⛔",
                "description": "Điểm đến của vận đơn không phải SGN. Báo đỏ cảnh báo nhầm hàng/nhầm trạm!",
            },
        }
        return badge_configs.get(
            status,
            {
                "label": str(status),
                "label_vn": str(status),
                "bg_color": "#6C757D",
                "fg_color": "#FFFFFF",
                "symbol": "?",
                "description": "Trạng thái không xác định",
            },
        )
