"""Thread-safe Session Records Store for Hermes Vision Extractor.

Maintains in-memory state of scanned and edited AWB records during an operational shift.
Provides CRUD operations, change notification listeners (Observer pattern), deduplication,
and real-time session statistics.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.classifier import BusinessRuleClassifier
from app.core.models import AWBRecord, BusinessStatus, SessionSummary

logger = logging.getLogger(__name__)


class SessionStore:
    """Thread-safe in-memory store for AWB records with change event notifications."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: List[AWBRecord] = []
        self._id_index: Dict[str, AWBRecord] = {}
        self._awb_index: Dict[str, AWBRecord] = {}
        self._listeners: List[Callable[[str, Any], None]] = []
        self._session_start = datetime.now(timezone.utc).isoformat()
        self._session_last_update = self._session_start

    # ---------------------------------------------------------------------
    # Listener Management (Observer Pattern)
    # ---------------------------------------------------------------------
    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Register a callback for session change events.

        Callback signature: `callback(event_type: str, data: Any)`
        Event types: 'record_added', 'record_updated', 'record_deleted', 'session_cleared'
        """
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Unregister a previously registered event listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self, event_type: str, data: Any) -> None:
        """Safely notify all listeners of a state change."""
        # Make a copy of listeners under lock to prevent mutation during iteration
        with self._lock:
            callbacks = list(self._listeners)
            self._session_last_update = datetime.now(timezone.utc).isoformat()

        for cb in callbacks:
            try:
                cb(event_type, data)
            except Exception as e:
                logger.error(f"Error in session store listener {cb}: {e}", exc_info=True)

    # ---------------------------------------------------------------------
    # CRUD Operations
    # ---------------------------------------------------------------------
    def add_record(self, record: AWBRecord) -> AWBRecord:
        """Add a new AWB record to the session.

        If a record with the same AWB number already exists, see `upsert_record`.
        """
        with self._lock:
            # Ensure status is properly classified
            if record.status_tag is None:
                record.status_tag = BusinessRuleClassifier.classify_record(record)

            self._records.append(record)
            self._id_index[record.id] = record
            self._awb_index[record.awb_number] = record

        self._notify("record_added", record)
        return record

    def upsert_record(self, record: AWBRecord) -> Tuple[AWBRecord, bool]:
        """Insert a record or merge with an existing record if the AWB number is identical.

        Returns:
            Tuple[AWBRecord, bool]: (resulting_record, is_new)
        """
        with self._lock:
            existing = self._awb_index.get(record.awb_number)
            if existing is None:
                # Completely new record
                added = self.add_record(record)
                return added, True

            # Merge richer data into existing record
            modified = False
            if existing.pieces is None and record.pieces is not None:
                existing.pieces = record.pieces
                modified = True
            elif record.pieces is not None and record.pieces > 0 and existing.pieces != record.pieces:
                existing.pieces = record.pieces
                modified = True

            if existing.weight_kg is None and record.weight_kg is not None:
                existing.weight_kg = record.weight_kg
                modified = True
            elif record.weight_kg is not None and record.weight_kg > 0 and existing.weight_kg != record.weight_kg:
                existing.weight_kg = record.weight_kg
                modified = True

            if not existing.consignee and record.consignee:
                existing.consignee = record.consignee
                modified = True

            if not existing.agent and record.agent:
                existing.agent = record.agent
                modified = True

            # If new scan has ALL IMP/ACC HAWB flag, elevate status
            if record.has_all_imp_acc_hawb and not existing.has_all_imp_acc_hawb:
                existing.has_all_imp_acc_hawb = True
                existing.raw_remarks = f"{existing.raw_remarks} | {record.raw_remarks}".strip(" |")
                modified = True

            # If remarks are richer in new record
            if len(record.raw_remarks) > len(existing.raw_remarks):
                existing.raw_remarks = record.raw_remarks
                modified = True

            # Update timestamp to latest scan
            existing.timestamp = record.timestamp
            existing.extraction_confidence = max(existing.extraction_confidence, record.extraction_confidence)

            # Re-evaluate status
            existing.status_tag = BusinessRuleClassifier.classify_record(existing)

        self._notify("record_updated", existing)
        return existing, False

    def get_record(self, record_id: str) -> Optional[AWBRecord]:
        """Retrieve a record by its UUID."""
        with self._lock:
            return self._id_index.get(record_id)

    def get_by_awb(self, awb_number: str) -> Optional[AWBRecord]:
        """Retrieve a record by canonical AWB number (e.g. 020-12345674)."""
        with self._lock:
            return self._awb_index.get(awb_number)

    def update_record(self, record_id: str, updates: Dict[str, Any]) -> Optional[AWBRecord]:
        """Update fields of an existing record (e.g. manual operator edit)."""
        with self._lock:
            record = self._id_index.get(record_id)
            if not record:
                return None

            # Track old AWB number in case it is changed
            old_awb = record.awb_number

            # Apply permitted fields
            for key, val in updates.items():
                if hasattr(record, key) and key not in ("id", "timestamp"):
                    setattr(record, key, val)

            # If AWB number changed, update index
            if record.awb_number != old_awb:
                if old_awb in self._awb_index:
                    del self._awb_index[old_awb]
                self._awb_index[record.awb_number] = record

            # Mark as manually edited
            record.is_manually_edited = True

            # Re-evaluate business status tag
            record.status_tag = BusinessRuleClassifier.classify_record(record)

        self._notify("record_updated", record)
        return record

    def delete_record(self, record_id: str) -> bool:
        """Delete an AWB record by UUID."""
        deleted_record: Optional[AWBRecord] = None
        with self._lock:
            record = self._id_index.get(record_id)
            if not record:
                return False

            deleted_record = record
            self._records = [r for r in self._records if r.id != record_id]
            del self._id_index[record_id]
            if record.awb_number in self._awb_index and self._awb_index[record.awb_number].id == record_id:
                del self._awb_index[record.awb_number]

        if deleted_record:
            self._notify("record_deleted", deleted_record)
        return True

    def clear_all(self) -> None:
        """Reset the session, clearing all records."""
        with self._lock:
            self._records.clear()
            self._id_index.clear()
            self._awb_index.clear()
            self._session_start = datetime.now(timezone.utc).isoformat()
            self._session_last_update = self._session_start

        self._notify("session_cleared", None)

    def get_all_records(self) -> List[AWBRecord]:
        """Get a copy list of all current records in chronological scan order."""
        with self._lock:
            return list(self._records)

    def count(self) -> int:
        """Return total number of records."""
        with self._lock:
            return len(self._records)

    # ---------------------------------------------------------------------
    # Aggregate Summary Statistics
    # ---------------------------------------------------------------------
    def get_summary(self) -> SessionSummary:
        """Compute aggregated statistics for the active shift session."""
        with self._lock:
            records = list(self._records)
            start_time = self._session_start
            last_update = self._session_last_update

        total_pcs = 0
        total_wt = 0.0
        cleared_cnt = 0
        pending_cnt = 0
        direct_cnt = 0
        checksum_cnt = 0
        edited_cnt = 0

        for r in records:
            if r.pieces is not None:
                total_pcs += r.pieces
            if r.weight_kg is not None:
                total_wt += r.weight_kg

            if r.status_tag == BusinessStatus.CLEARED:
                cleared_cnt += 1
            elif r.status_tag == BusinessStatus.PENDING_HAWB:
                pending_cnt += 1
            elif r.status_tag == BusinessStatus.DIRECT_SHIPMENT:
                direct_cnt += 1
            elif r.status_tag == BusinessStatus.CHECKSUM_ERROR:
                checksum_cnt += 1

            if r.is_manually_edited:
                edited_cnt += 1

        return SessionSummary(
            total_records=len(records),
            total_pieces=total_pcs,
            total_weight_kg=round(total_wt, 2),
            cleared_count=cleared_cnt,
            pending_hawb_count=pending_cnt,
            direct_count=direct_cnt,
            checksum_error_count=checksum_cnt,
            manually_edited_count=edited_cnt,
            session_start=start_time,
            session_last_update=last_update,
        )

    # ---------------------------------------------------------------------
    # JSON Serialization & Persistence
    # ---------------------------------------------------------------------
    def export_to_dict_list(self) -> List[Dict[str, Any]]:
        """Export all records as a list of primitive dictionaries."""
        with self._lock:
            return [r.model_dump() for r in self._records]

    def export_to_json_file(self, file_path: str) -> str:
        """Save session records to a JSON file."""
        data = {
            "session_start": self._session_start,
            "session_last_update": self._session_last_update,
            "summary": self.get_summary().model_dump(),
            "records": self.export_to_dict_list(),
        }
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(path)

    def load_from_json_file(self, file_path: str) -> int:
        """Load records from a JSON file into the current session."""
        path = Path(file_path)
        if not path.exists():
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_records = data.get("records", [])
        count_loaded = 0
        for item in raw_records:
            try:
                rec = AWBRecord(**item)
                self.upsert_record(rec)
                count_loaded += 1
            except Exception as e:
                logger.warning(f"Skipping invalid record during import: {e}")

        return count_loaded
