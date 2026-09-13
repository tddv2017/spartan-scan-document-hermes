"""Comprehensive tests for SessionStore and AWBRecord models.

Verifies thread-safe in-memory session management, CRUD operations,
deduplication/upsert logic, observer event notifications, summary metrics,
and JSON persistence.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest

from app.core.models import AWBRecord, BusinessStatus, ExtractionResult
from app.core.session_store import SessionStore


class TestSessionStoreCRUD:
    """Tests basic CRUD operations on SessionStore."""

    def test_add_and_retrieve_record(self) -> None:
        store = SessionStore()
        rec = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.5,
            consignee="CONG TY TNHH LOGISTICS TOAN CAU",
            has_all_imp_acc_hawb=True,
            is_valid_checksum=True,
            status_tag=BusinessStatus.CLEARED,
        )

        added = store.add_record(rec)
        assert added.id == rec.id
        assert store.count() == 1

        by_id = store.get_record(rec.id)
        assert by_id is not None
        assert by_id.awb_number == "020-12345675"
        assert by_id.status_tag == BusinessStatus.CLEARED

        by_awb = store.get_by_awb("020-12345675")
        assert by_awb is not None
        assert by_awb.id == rec.id

    def test_update_record(self) -> None:
        store = SessionStore()
        rec = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.5,
            consignee="OLD CONSIGNEE",
        )
        store.add_record(rec)

        updated = store.update_record(
            rec.id,
            {"pieces": 50, "consignee": "NEW CONSIGNEE", "weight_kg": 1300.0},
        )
        assert updated is not None
        assert updated.pieces == 50
        assert updated.consignee == "NEW CONSIGNEE"
        assert updated.weight_kg == 1300.0
        assert updated.is_manually_edited is True

    def test_update_awb_number_reindexes(self) -> None:
        store = SessionStore()
        rec = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.5,
        )
        store.add_record(rec)

        # Operator fixes AWB number manually
        store.update_record(rec.id, {"awb_number": "020-98765435"})
        assert store.get_by_awb("020-12345675") is None
        assert store.get_by_awb("020-98765435") is not None

    def test_delete_record(self) -> None:
        store = SessionStore()
        rec = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.5,
        )
        store.add_record(rec)
        assert store.count() == 1

        deleted = store.delete_record(rec.id)
        assert deleted is True
        assert store.count() == 0
        assert store.get_record(rec.id) is None
        assert store.get_by_awb("020-12345675") is None

        # Deleting non-existent returns False
        assert store.delete_record("non-existent-id") is False

    def test_clear_all(self) -> None:
        store = SessionStore()
        for i in range(5):
            store.add_record(
                AWBRecord(
                    awb_number=f"020-000000{i}0",
                    pieces=i + 1,
                    weight_kg=float(100 * (i + 1)),
                )
            )
        assert store.count() == 5

        store.clear_all()
        assert store.count() == 0
        assert len(store.get_all_records()) == 0


class TestSessionStoreDeduplication:
    """Tests upsert behavior for duplicate AWB scans in an operational shift."""

    def test_upsert_creates_new_record_when_absent(self) -> None:
        store = SessionStore()
        rec = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.5,
        )
        result_rec, is_new = store.upsert_record(rec)
        assert is_new is True
        assert store.count() == 1
        assert result_rec.awb_number == "020-12345675"

    def test_upsert_merges_duplicate_scan_and_elevates_clearance(self) -> None:
        store = SessionStore()
        # Scan 1: initial scan without HAWB tab open
        first_scan = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.5,
            consignee="CONG TY TOAN CAU",
            raw_remarks="CONSOL CARGO",
            has_all_imp_acc_hawb=False,
            status_tag=BusinessStatus.PENDING_HAWB,
        )
        store.add_record(first_scan)

        # Scan 2: operator opens HAWB tab and triggers second scan for same AWB
        second_scan = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.5,
            consignee="CONG TY TOAN CAU",
            agent="HAN-AGENT",
            raw_remarks="ALL IMP/ACC HAWB - RELEASED",
            has_all_imp_acc_hawb=True,
            status_tag=BusinessStatus.CLEARED,
        )
        merged_rec, is_new = store.upsert_record(second_scan)

        assert is_new is False
        assert store.count() == 1  # No duplicate record created!
        assert merged_rec.has_all_imp_acc_hawb is True
        assert merged_rec.status_tag == BusinessStatus.CLEARED
        assert merged_rec.agent == "HAN-AGENT"


class TestSessionSummaryMetrics:
    """Tests real-time statistical aggregation in get_summary."""

    def test_summary_calculation(self) -> None:
        store = SessionStore()
        records = [
            AWBRecord(
                awb_number="020-12345675",
                pieces=10,
                weight_kg=100.0,
                has_all_imp_acc_hawb=True,
                status_tag=BusinessStatus.CLEARED,
            ),
            AWBRecord(
                awb_number="020-98765435",
                pieces=20,
                weight_kg=250.5,
                has_all_imp_acc_hawb=True,
                status_tag=BusinessStatus.CLEARED,
            ),
            AWBRecord(
                awb_number="020-87654324",
                pieces=5,
                weight_kg=50.0,
                has_all_imp_acc_hawb=False,
                status_tag=BusinessStatus.PENDING_HAWB,
            ),
            AWBRecord(
                awb_number="020-33445565",
                pieces=2,
                weight_kg=15.0,
                has_all_imp_acc_hawb=False,
                status_tag=BusinessStatus.DIRECT_SHIPMENT,
            ),
            AWBRecord(
                awb_number="020-24681359",
                pieces=1,
                weight_kg=10.0,
                is_valid_checksum=False,
                status_tag=BusinessStatus.CHECKSUM_ERROR,
            ),
        ]
        for r in records:
            store.add_record(r)

        summary = store.get_summary()
        assert summary.total_records == 5
        assert summary.total_pieces == 38
        assert summary.total_weight_kg == 425.5
        assert summary.cleared_count == 2
        assert summary.pending_hawb_count == 1
        assert summary.direct_count == 1
        assert summary.checksum_error_count == 1
        assert summary.cleared_ratio == (2 / 5) * 100.0


class TestObserverPatternSubscriptions:
    """Tests session change notification listeners."""

    def test_listeners_receive_lifecycle_events(self) -> None:
        store = SessionStore()
        events_received = []

        def on_event(event_type: str, data: any) -> None:
            events_received.append((event_type, data))

        store.subscribe(on_event)

        # Event 1: Add
        rec = AWBRecord(awb_number="020-12345675", pieces=10, weight_kg=100.0)
        store.add_record(rec)
        assert len(events_received) == 1
        assert events_received[0][0] == "record_added"

        # Event 2: Update
        store.update_record(rec.id, {"pieces": 15})
        assert len(events_received) == 2
        assert events_received[1][0] == "record_updated"

        # Event 3: Delete
        store.delete_record(rec.id)
        assert len(events_received) == 3
        assert events_received[2][0] == "record_deleted"

        # Event 4: Clear
        store.clear_all()
        assert len(events_received) == 4
        assert events_received[3][0] == "session_cleared"

        # Unsubscribe
        store.unsubscribe(on_event)
        store.add_record(AWBRecord(awb_number="020-98765435", pieces=5, weight_kg=50.0))
        assert len(events_received) == 4  # No further notifications


class TestJsonSerialization:
    """Tests exporting and reloading session state via JSON files."""

    def test_json_export_and_import(self, temp_output_dir: Path) -> None:
        store = SessionStore()
        for i in range(3):
            store.add_record(
                AWBRecord(
                    awb_number=f"020-111111{i}0",
                    pieces=(i + 1) * 10,
                    weight_kg=float((i + 1) * 100),
                    consignee=f"COMPANY {i}",
                )
            )

        json_path = temp_output_dir / "session_dump.json"
        exported = store.export_to_json_file(str(json_path))
        assert Path(exported).exists()

        # Load into clean session store
        new_store = SessionStore()
        loaded_count = new_store.load_from_json_file(exported)
        assert loaded_count == 3
        assert new_store.count() == 3
        assert new_store.get_by_awb("020-11111100") is not None


class TestConcurrentThreadSafety:
    """Tests concurrent additions and reads across multiple worker threads."""

    def test_concurrent_adds_and_reads(self) -> None:
        store = SessionStore()

        def worker_add(idx: int) -> None:
            rec = AWBRecord(
                awb_number=f"020-{idx:08d}",
                pieces=idx,
                weight_kg=float(idx * 10),
            )
            store.add_record(rec)

        # Launch 20 concurrent threads adding records
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(worker_add, range(20)))

        assert store.count() == 20
        all_records = store.get_all_records()
        assert len(all_records) == 20
