"""Data models and schemas for Hermes Vision Extractor.

Defines Pydantic v2 models for OCR extraction results, session records,
business classification statuses, and shift summaries.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class BusinessStatus(str, Enum):
    """Business rule operational status for an AWB record."""

    CLEARED = "CLEARED"                      # Verified ALL IMP/ACC HAWB (Green)
    PENDING_HAWB = "PENDING_HAWB"            # Consolidation missing full HAWB acceptance (Orange)
    DIRECT_SHIPMENT = "DIRECT_SHIPMENT"      # Direct MAWB, no house bills (Blue)
    CHECKSUM_ERROR = "CHECKSUM_ERROR"        # Failed IATA Modulo-7 check digit (Red)


class ExtractionResult(BaseModel):
    """Raw OCR and parsed entity output from vision processing."""

    model_config = ConfigDict(populate_by_name=True)

    raw_text: str = Field(default="", description="Full text extracted by OCR engine")
    awb_prefix: str = Field(default="", description="3-digit airline prefix (e.g. 020)")
    awb_serial: str = Field(default="", description="8-digit serial and check digit")
    awb_number: str = Field(default="", description="Canonical AWB number (e.g. 020-12345674)")
    pieces: Optional[int] = Field(default=None, description="Number of pieces/colli")
    weight_kg: Optional[float] = Field(default=None, description="Gross weight in kilograms")
    consignee: str = Field(default="", description="Consignee company/recipient name")
    agent: str = Field(default="", description="Freight forwarder or handling agent")
    remark: str = Field(default="", description="Extracted handling/operational remarks")
    remark_agent: str = Field(default="", description="Remarks specific to agent")
    has_all_imp_acc_hawb: bool = Field(default=False, description="True if 'ALL IMP/ACC HAWB' flag is present")
    is_valid_checksum: bool = Field(default=False, description="True if IATA Modulo-7 check digit matches")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall OCR confidence score")
    raw_ocr_tokens: List[str] = Field(default_factory=list, description="Raw OCR token strings")
    snapshot_path: Optional[str] = Field(default="", description="Absolute path to saved PNG screenshot on disk")

    @property
    def is_complete(self) -> bool:
        """Returns True if essential cargo fields are populated."""
        return bool(self.awb_number and self.pieces is not None and self.weight_kg is not None)


class AWBRecord(BaseModel):
    """Auditable session record representing a scanned or manually modified AWB."""

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique record UUID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of creation or scan",
    )
    awb_number: str = Field(..., description="Canonical hyphenated AWB number (e.g. 020-12345674)")
    prefix: str = Field(default="020", description="3-digit airline prefix")
    serial: str = Field(default="", description="8-digit serial component")
    airline_name: str = Field(default="Lufthansa Cargo", description="Airline carrier identity")
    is_valid_checksum: bool = Field(default=True, description="IATA Modulo-7 check digit validity")
    pieces: Optional[int] = Field(default=None, ge=0, description="Package / Colli count")
    weight_kg: Optional[float] = Field(default=None, ge=0.0, description="Gross weight in kilograms")
    consignee: str = Field(default="", description="Recipient / Consignee entity name")
    agent: str = Field(default="", description="Handling or forwarding agent")
    raw_remarks: str = Field(default="", description="Full remark text as observed on screen")
    remark_agent: str = Field(default="", description="Agent-specific remark line")
    has_all_imp_acc_hawb: bool = Field(default=False, description="Flag for ALL IMP/ACC HAWB")
    status_tag: BusinessStatus = Field(
        default=BusinessStatus.DIRECT_SHIPMENT,
        description="Business classification status",
    )
    is_manually_edited: bool = Field(default=False, description="True if modified by user")
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="OCR confidence")
    snapshot_path: Optional[str] = Field(default="", description="Path to archived screen image on disk")

    @classmethod
    def from_extraction_result(
        cls,
        result: ExtractionResult,
        airline_name: Optional[str] = None,
        status_tag: Optional[BusinessStatus] = None,
    ) -> "AWBRecord":
        """Factory method to construct an AWBRecord from an ExtractionResult."""
        from app.core.config import DEFAULT_AIRLINE_PREFIX, DEFAULT_AIRLINE_NAME, AIRLINE_PREFIX_MAP

        prefix = result.awb_prefix or (result.awb_number.split("-")[0] if "-" in result.awb_number else DEFAULT_AIRLINE_PREFIX)
        serial = result.awb_serial or (result.awb_number.split("-")[1] if "-" in result.awb_number else "")
        carrier = airline_name or AIRLINE_PREFIX_MAP.get(prefix, DEFAULT_AIRLINE_NAME)

        # Determine status if not explicitly passed
        if status_tag is None:
            if not result.is_valid_checksum:
                computed_status = BusinessStatus.CHECKSUM_ERROR
            elif result.has_all_imp_acc_hawb:
                computed_status = BusinessStatus.CLEARED
            elif any(k in result.remark.upper() for k in ["HAWB", "HOUSE", "CONSOL", "PARTIAL"]):
                computed_status = BusinessStatus.PENDING_HAWB
            else:
                computed_status = BusinessStatus.DIRECT_SHIPMENT
        else:
            computed_status = status_tag

        return cls(
            awb_number=result.awb_number,
            prefix=prefix,
            serial=serial,
            airline_name=carrier,
            is_valid_checksum=result.is_valid_checksum,
            pieces=result.pieces,
            weight_kg=result.weight_kg,
            consignee=result.consignee,
            agent=result.agent,
            raw_remarks=result.remark,
            remark_agent=result.remark_agent,
            has_all_imp_acc_hawb=result.has_all_imp_acc_hawb,
            status_tag=computed_status,
            extraction_confidence=result.confidence,
            snapshot_path=result.snapshot_path or "",
        )


class SessionSummary(BaseModel):
    """Aggregated metrics for the active operational shift session."""

    model_config = ConfigDict(populate_by_name=True)

    total_records: int = 0
    total_pieces: int = 0
    total_weight_kg: float = 0.0
    cleared_count: int = 0
    pending_hawb_count: int = 0
    direct_count: int = 0
    checksum_error_count: int = 0
    manually_edited_count: int = 0
    session_start: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_last_update: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def cleared_ratio(self) -> float:
        """Percentage of records that are CLEARED."""
        if self.total_records == 0:
            return 0.0
        return (self.cleared_count / self.total_records) * 100.0
