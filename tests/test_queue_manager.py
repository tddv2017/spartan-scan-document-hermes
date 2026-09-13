"""Tests for Asynchronous Capture Queue and Snapshot Archiving."""

from pathlib import Path
import time
from PIL import Image
import pytest

from app.capture.queue_manager import CaptureJob, CaptureQueueManager


class TestCaptureQueueManager:
    @pytest.fixture
    def temp_captures_dir(self, tmp_path: Path) -> Path:
        p = tmp_path / "test_captures"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def test_instant_enqueue_and_fifo_order(self, temp_captures_dir: Path):
        processed_jobs = []

        def dummy_processor(job: CaptureJob):
            processed_jobs.append(job.job_id)
            time.sleep(0.05)

        manager = CaptureQueueManager(
            job_processor=dummy_processor,
            captures_base_dir=temp_captures_dir,
            save_to_disk=True,
        )
        manager.start()

        img = Image.new("RGB", (200, 100), color="#112233")

        # Enqueue 5 jobs in rapid succession (<50ms total)
        jobs = []
        for i in range(5):
            j = manager.enqueue(img, window_title="Hermes Test", trigger_source=f"Test_{i}")
            jobs.append(j)

        # Wait for background queue worker to drain
        timeout = time.time() + 5.0
        while len(processed_jobs) < 5 and time.time() < timeout:
            time.sleep(0.05)

        manager.stop()

        assert len(processed_jobs) == 5
        # Verify strict FIFO order
        for idx in range(5):
            assert processed_jobs[idx] == jobs[idx].job_id

        # Verify disk files were created
        for j in jobs:
            assert j.saved_path is not None
            assert Path(j.saved_path).exists()

    def test_rename_snapshot_with_awb(self, temp_captures_dir: Path):
        manager = CaptureQueueManager(
            captures_base_dir=temp_captures_dir,
            save_to_disk=True,
        )
        img = Image.new("RGB", (100, 50), color="#ABCDEF")
        job = manager.enqueue(img, window_title="Hermes", trigger_source="Manual")

        assert job.saved_path is not None
        assert Path(job.saved_path).exists()

        new_path = manager.rename_snapshot_with_awb(job, "020-12345675", "CLEARED")
        assert new_path is not None
        assert "02012345675" in new_path
        assert "CLEARED" in new_path
        assert Path(new_path).exists()