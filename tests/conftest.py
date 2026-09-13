"""Pytest fixtures and configuration for Hermes Vision Extractor test suites."""

import os
from pathlib import Path
import tempfile
from typing import Dict, Generator, List
import pytest
from PIL import Image

from app.core.models import AWBRecord, BusinessStatus, ExtractionResult
from tests.mock_generator import HermesFixture, generate_mock_screen, get_all_fixtures


@pytest.fixture(scope="session")
def all_fixtures() -> List[HermesFixture]:
    """Returns all 10 authoritative operational Hermes CMS fixtures."""
    return get_all_fixtures()


@pytest.fixture(scope="session")
def mock_screens(all_fixtures: List[HermesFixture]) -> Dict[str, Image.Image]:
    """Renders all mock screenshots once per session for fast execution."""
    rendered: Dict[str, Image.Image] = {}
    for fix in all_fixtures:
        rendered[fix.fixture_id] = generate_mock_screen(fix)
    return rendered


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """Provides an isolated temporary directory for PDF / export file tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_awb_records() -> List[AWBRecord]:
    """Provides a realistic set of AWBRecords covering all business states for PDF & session store tests."""
    return [
        AWBRecord(
            awb_number="020-12345675",
            prefix="020",
            serial="12345675",
            airline_name="Lufthansa Cargo",
            is_valid_checksum=True,
            pieces=45,
            weight_kg=1250.5,
            consignee="CONG TY TNHH LOGISTICS TOAN CAU",
            agent="HAN - NCTS LOGISTICS AGENT",
            raw_remarks="ALL IMP/ACC HAWB - DOCS DELIVERED",
            remark_agent="HAN/CARGO-OPS-01",
            has_all_imp_acc_hawb=True,
            status_tag=BusinessStatus.CLEARED,
            extraction_confidence=0.98,
        ),
        AWBRecord(
            awb_number="020-98765435",
            prefix="020",
            serial="98765435",
            airline_name="Lufthansa Cargo",
            is_valid_checksum=True,
            pieces=120,
            weight_kg=3450.0,
            consignee="SCHENKER VIETNAM CO LTD",
            agent="SGN - SCHENKER AIR FREIGHT",
            raw_remarks="ALL IMP/ACC HAWB",
            remark_agent="SGN/LH-RAMP",
            has_all_imp_acc_hawb=True,
            status_tag=BusinessStatus.CLEARED,
            extraction_confidence=0.99,
        ),
        AWBRecord(
            awb_number="020-87654324",
            prefix="020",
            serial="87654324",
            airline_name="Lufthansa Cargo",
            is_valid_checksum=True,
            pieces=8,
            weight_kg=95.2,
            consignee="KUEHNE NAGEL VIETNAM LLC",
            agent="HAN - KN AIR CARGO",
            raw_remarks="CONSOLIDATION SHIPMENT - HOLD AWAITING HAWB DOCS",
            remark_agent="HAN/IMPORT-DESK",
            has_all_imp_acc_hawb=False,
            status_tag=BusinessStatus.PENDING_HAWB,
            extraction_confidence=0.95,
        ),
        AWBRecord(
            awb_number="020-33445565",
            prefix="020",
            serial="33445565",
            airline_name="Lufthansa Cargo",
            is_valid_checksum=True,
            pieces=1,
            weight_kg=12.5,
            consignee="INDIVIDUAL IMPORTER NGUYEN VAN A",
            agent="DIRECT IMPORT BROKERAGE",
            raw_remarks="DIRECT MASTER SHIPMENT - SINGLE CONSIGNMENT",
            remark_agent="HAN/EXP-COUNTER",
            has_all_imp_acc_hawb=False,
            status_tag=BusinessStatus.DIRECT_SHIPMENT,
            extraction_confidence=0.97,
        ),
        AWBRecord(
            awb_number="020-24681359",
            prefix="020",
            serial="24681359",
            airline_name="Lufthansa Cargo",
            is_valid_checksum=False,
            pieces=5,
            weight_kg=80.0,
            consignee="TEST AIRLINE TRAINING CARGO",
            agent="TRAINING SIMULATOR AGENT",
            raw_remarks="ALL IMP/ACC HAWB - DEMO TRAINING RUN",
            remark_agent="SIM/STATION-TEST",
            has_all_imp_acc_hawb=True,
            status_tag=BusinessStatus.CHECKSUM_ERROR,
            extraction_confidence=0.92,
        ),
    ]
