"""Asynchronous Screen Capture Queue & Snapshot Archiving Engine.

Implements a high-throughput Producer-Consumer pipeline:
- Producer: Captures Hermes screen in ~20ms, immediately archives raw snapshot to disk
  (captures/YYYY-MM-DD/), and pushes into thread-safe FIFO queue. Instant feedback.
- Consumer: Background worker pulls jobs sequentially, runs OCR recognition, domain entity
  parsing, Modulo-7 checksum verification, and updates Session Store without blocking operator.
"""

from dataclasses import dataclass
from datetime import datetime
import logging
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable, Dict, Optional
import uuid

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class CaptureJob:
    """Individual capture task queued for background vision recognition."""
    job_id: str
    image: Image.Image
    window_title: str
    trigger_source: str
    timestamp: datetime
    saved_path: Optional[str] = None
    awb_number: str = ""
    status: str = ""


class CaptureQueueManager:
    """Thread-safe FIFO capture queue with automatic disk archiving and sequential consumer."""

    def __init__(
        self,
        job_processor: Optional[Callable[[CaptureJob], None]] = None,
        on_queue_changed: Optional[Callable[[int], None]] = None,
        captures_base_dir: Optional[Path] = None,
        save_to_disk: bool = True,
    ) -> None:
        self.job_processor = job_processor
        self.on_queue_changed = on_queue_changed
        self.captures_base_dir = captures_base_dir or Path("captures")
        self.save_to_disk = save_to_disk

        self._queue: queue.Queue[Optional[CaptureJob]] = queue.Queue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._active_jobs: Dict[str, CaptureJob] = {}
        self._lock = threading.Lock()
        self._total_enqueued = 0
        self._total_processed = 0

    def start(self) -> None:
        """Start the background consumer worker thread."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="CaptureQueueConsumer",
        )
        self._worker_thread.start()
        logger.info("CaptureQueueManager consumer worker started.")

    def stop(self) -> None:
        """Stop worker cleanly."""
        if not self._running:
            return
        self._running = False
        self._queue.put(None)  # Sentinel to unblock get()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self._worker_thread = None
        logger.info("CaptureQueueManager consumer worker stopped.")

    def enqueue(
        self,
        image: Image.Image,
        window_title: str = "",
        trigger_source: str = "manual",
    ) -> CaptureJob:
        """Instantly enqueue a captured screenshot and save to disk in <25ms."""
        now = datetime.now()
        job_id = f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        saved_path = None
        if self.save_to_disk:
            saved_path = self._save_snapshot(image, now, job_id)

        job = CaptureJob(
            job_id=job_id,
            image=image.copy(),
            window_title=window_title,
            trigger_source=trigger_source,
            timestamp=now,
            saved_path=saved_path,
        )

        with self._lock:
            self._active_jobs[job_id] = job
            self._total_enqueued += 1

        self._queue.put(job)
        pending = self.pending_count()
        logger.info(f"Screenshot enqueued [{job_id}] from '{trigger_source}'. Queue depth: {pending}")

        if self.on_queue_changed:
            try:
                self.on_queue_changed(pending)
            except Exception as e:
                logger.debug(f"Error calling on_queue_changed: {e}")

        return job

    def pending_count(self) -> int:
        """Return the number of jobs waiting in queue."""
        return self._queue.qsize()

    def _save_snapshot(self, image: Image.Image, now: datetime, job_id: str) -> Optional[str]:
        """Save screenshot to disk under captures/YYYY-MM-DD/."""
        try:
            day_folder = self.captures_base_dir / now.strftime("%Y-%m-%d")
            day_folder.mkdir(parents=True, exist_ok=True)
            file_name = f"SNAPSHOT_{now.strftime('%H%M%S')}_{job_id}.png"
            file_path = day_folder / file_name
            image.save(str(file_path), format="PNG", optimize=False)
            return str(file_path)
        except Exception as e:
            logger.warning(f"Could not save snapshot to disk: {e}")
            return None

    def rename_snapshot_with_awb(self, job: CaptureJob, awb_number: str, status_str: str) -> Optional[str]:
        """Rename snapshot file to include AWB number and status for instant archiving clarity."""
        if not job.saved_path or not os.path.exists(job.saved_path):
            return None

        try:
            old_path = Path(job.saved_path)
            clean_awb = awb_number.replace("-", "").strip() if awb_number else "UNKNOWN"
            clean_status = status_str.replace(" ", "_").replace("/", "_")
            new_name = f"{job.timestamp.strftime('%H%M%S')}_{clean_awb}_{clean_status}.png"
            new_path = old_path.parent / new_name
            old_path.rename(new_path)
            job.saved_path = str(new_path)
            logger.debug(f"Renamed snapshot to: {new_path.name}")
            return str(new_path)
        except Exception as e:
            logger.debug(f"Could not rename snapshot: {e}")
            return job.saved_path

    def _worker_loop(self) -> None:
        """Continuous FIFO worker thread."""
        while self._running:
            try:
                job = self._queue.get(timeout=0.5)
                if job is None:
                    break  # Sentinel encountered

                # Process job through OCR and extraction pipeline
                if self.job_processor:
                    try:
                        self.job_processor(job)
                    except Exception as e:
                        logger.error(f"Error processing capture job [{job.job_id}]: {e}", exc_info=True)

                with self._lock:
                    self._active_jobs.pop(job.job_id, None)
                    self._total_processed += 1

                self._queue.task_done()
                pending = self.pending_count()

                if self.on_queue_changed:
                    try:
                        self.on_queue_changed(pending)
                    except Exception as e:
                        logger.debug(f"Error calling on_queue_changed: {e}")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Unexpected error in queue worker: {e}", exc_info=True)