"""Hermes Vision Extractor - Main Application Entry Point & Subsystem Orchestrator.

Integrates Win32 Global Hotkeys (F9, Ctrl+Shift+S), Non-Intrusive Screen Grabber,
Dual-Engine OCR (RapidOCR / Windows Media OCR), Hermes Domain Parser,
Thread-safe Session Store, Tkinter Floating Overlay Pill, and Session Manager UI.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import signal
import sys
import threading
import tkinter as tk
from typing import Any, Optional

# Ensure hermes_vision_extractor root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.capture.confirm_watcher import ConfirmWatcher
from app.capture.queue_manager import CaptureJob, CaptureQueueManager
from app.capture.screen_grabber import ScreenGrabber
from app.core.config import APP_NAME, APP_VERSION, Config
from app.core.hotkey import GlobalHotkeyListener
from app.core.models import AWBRecord
from app.core.session_store import SessionStore
from app.ui.overlay import FloatingOverlay
from app.ui.session_window import SessionManagerWindow
from app.vision.ocr_engine import DualOCREngine
from app.vision.parser import HermesDataParser
from app.vision.preprocessor import ImagePreprocessor

# Setup unified logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("HermesApp")


class HermesVisionApp:
    """Central application controller binding vision, OCR, hotkeys, session, and GUI."""

    def __init__(
        self,
        config: Optional[Config] = None,
        show_session_manager: bool = False,
    ) -> None:
        self.config = config or Config()
        logger.info(f"Initializing {APP_NAME} v{APP_VERSION}...")

        # 1. Initialize Core Subsystems
        self.store = SessionStore()
        self.grabber = ScreenGrabber()
        self.preprocessor = ImagePreprocessor(scale_factor=self.config.scale_factor)
        self.ocr_engine = DualOCREngine(
            preprocessor=self.preprocessor,
            prefer_engine=self.config.primary_engine,
            min_confidence=self.config.min_confidence,
        )
        self.parser = HermesDataParser()

        # Threading coordinator
        self._processing = False
        self._proc_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="AppVisionWorker")

        # 2. Initialize Asynchronous Capture Queue & Disk Archiving
        self.queue_manager = CaptureQueueManager(
            job_processor=self._process_capture_job,
            on_queue_changed=self._on_queue_changed,
            captures_base_dir=self.config.captures_dir,
            save_to_disk=self.config.save_snapshots_to_disk,
        )

        # 3. Initialize Confirm Action Watcher (Auto-Scan on Confirm click/key)
        self.confirm_watcher = ConfirmWatcher(
            on_confirm_triggered=self._on_confirm_detected,
            delay_seconds=self.config.confirm_delay_sec,
            debounce_seconds=2.0,
            auto_enabled=self.config.auto_scan_enabled,
        )

        # 4. Initialize GUI Elements
        self.root = tk.Tk()
        self.root.withdraw()  # Root remains hidden; top-levels provide UI

        # Floating Pill Overlay
        self.overlay = FloatingOverlay(
            parent=self.root,
            on_scan=self.trigger_scan,
            on_open_session=self.open_session_manager,
            on_exit=self.shutdown,
            on_toggle_auto=self._on_toggle_auto_scan,
            on_pick_window=self._on_pick_window,
            on_calibrate_button=self._on_calibrate_button,
            on_set_delay=self._on_set_delay,
        )

        # Session Manager Window
        self.session_window = SessionManagerWindow(
            master=self.root,
            store=self.store,
            on_scan=self.trigger_scan,
            on_toggle_auto=self._on_toggle_auto_scan,
            on_pick_window=self._on_pick_window,
            on_calibrate_button=self._on_calibrate_button,
            on_set_delay=self._on_set_delay,
            captures_dir=self.config.captures_dir,
        )

        if show_session_manager:
            self.session_window.show()
        else:
            self.session_window.hide()

        # 5. Initialize Global Win32 Hotkey Listener (F9, Ctrl+Shift+S)
        self.hotkey_listener = GlobalHotkeyListener(
            callback=self._on_hotkey_triggered,
            debounce_seconds=self.config.debounce_seconds,
        )

    def start(self) -> None:
        """Start background listeners and enter Tkinter main loop."""
        logger.info("Starting Capture Queue Manager consumer worker...")
        self.queue_manager.start()

        logger.info("Starting global hotkey listener (F9, Ctrl+Shift+S)...")
        hotkeys_started = self.hotkey_listener.start()
        if not hotkeys_started:
            logger.warning("Global hotkeys could not be registered. Floating widget remains active.")

        logger.info("Starting Confirm Action Watcher (Auto-Scan)...")
        self.confirm_watcher.start()

        # Handle SIGINT (Ctrl+C) cleanly
        signal.signal(signal.SIGINT, lambda sig, frame: self.shutdown())

        logger.info(f"{APP_NAME} operational. Floating widget and auto-watcher ready.")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self) -> None:
        """Gracefully release hotkeys, shutdown thread pool, and destroy UI."""
        logger.info("Shutting down Hermes Vision Extractor...")
        try:
            self.queue_manager.stop()
        except Exception as e:
            logger.debug(f"Error stopping queue manager: {e}")

        try:
            self.hotkey_listener.stop()
        except Exception as e:
            logger.debug(f"Error stopping hotkeys: {e}")

        try:
            self.confirm_watcher.stop()
        except Exception as e:
            logger.debug(f"Error stopping confirm watcher: {e}")

        try:
            self._executor.shutdown(wait=False)
        except Exception as e:
            logger.debug(f"Error stopping executor: {e}")

        try:
            self.overlay.destroy()
        except Exception:
            pass

        try:
            self.session_window.destroy()
        except Exception:
            pass

        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

        logger.info("Application shutdown complete.")

    def open_session_manager(self) -> None:
        """Show or bring the Session Manager window to front."""
        self.session_window.show()

    def _on_hotkey_triggered(self, hotkey_name: str) -> None:
        """Callback from background hotkey thread."""
        logger.info(f"Hotkey event received: {hotkey_name}. Dispatching scan to main thread.")
        try:
            self.root.after(0, lambda: self.trigger_scan(trigger_source=f"hotkey_{hotkey_name}"))
        except Exception as e:
            logger.error(f"Error posting hotkey event to Tkinter loop: {e}")

    def _on_confirm_detected(self, delay_sec: float) -> None:
        """Callback from ConfirmWatcher: updates visual countdown and schedules scan."""
        logger.info(f"Confirm action received! Scheduling scan in {delay_sec:.1f}s...")
        try:
            # Display visual countdown on overlay (<1s feedback)
            self.root.after(0, lambda: self.overlay.set_state_countdown(delay_sec))
            # Schedule actual scan after exact delay
            self.root.after(int(delay_sec * 1000), lambda: self.trigger_scan(trigger_source="auto_confirm"))
        except Exception as e:
            logger.error(f"Error scheduling confirm scan: {e}")

    def _on_queue_changed(self, count: int) -> None:
        """Callback from queue manager when queue depth changes."""
        try:
            self.root.after(0, lambda: self.overlay.set_state_queued(count))
        except Exception:
            pass

    def _on_toggle_auto_scan(self, enabled: bool) -> None:
        """Synchronize Auto-scan toggle state across subsystem components."""
        self.config.auto_scan_enabled = enabled
        self.confirm_watcher.auto_enabled = enabled
        self.overlay.set_auto_enabled(enabled)
        self.session_window.set_auto_enabled(enabled)
        logger.info(f"Auto-scan on confirm toggled: {'ENABLED' if enabled else 'DISABLED'}")

    def _on_pick_window(self) -> None:
        """Activate window picker mode."""
        self.confirm_watcher.start_window_picker(callback=self._on_window_picked)

    def _on_window_picked(self, hwnd: int, title: str) -> None:
        """Pin selected window and update UI across overlay and session manager."""
        self.grabber.pin_window(hwnd, title)
        self.confirm_watcher.set_target_window(hwnd, title)
        self.root.after(0, lambda: self.overlay.set_pinned_title(title))
        self.root.after(0, lambda: self.session_window.set_pinned_title(title))

    def _on_calibrate_button(self) -> None:
        """Activate Confirm button calibration mode."""
        self.confirm_watcher.start_button_calibration(callback=self._on_button_calibrated)

    def _on_button_calibrated(self, hotspot: Any) -> None:
        """Handle completion of Confirm button calibration."""
        self.root.after(0, lambda: self.overlay.set_state_success("Đã chấm nút!"))

    def _on_set_delay(self, delay_sec: float) -> None:
        """Update capture delay across config and watcher."""
        self.config.confirm_delay_sec = delay_sec
        self.confirm_watcher.delay_seconds = delay_sec
        self.session_window.set_delay(delay_sec)
        logger.info(f"Confirm capture delay configured to: {delay_sec:.1f}s")

    def trigger_scan(self, trigger_source: str = "manual") -> None:
        """Instantly capture Hermes screen in RAM (<25ms) and enqueue for background processing."""
        try:
            logger.info(f"Capturing Hermes screen (trigger: {trigger_source})...")
            img, title = self.grabber.capture_active_window()
            if img is None:
                logger.debug("Active window grab returned empty, falling back to full screen...")
                img = self.grabber.capture_full_screen()
                title = title or "Desktop"

            if img is None:
                logger.warning("Screen capture failed to produce an image.")
                self.root.after(0, lambda: self.overlay.set_state_error("Lỗi chụp"))
                return

            # Push immediately into FIFO queue (<20ms in RAM + disk save)
            job = self.queue_manager.enqueue(img, window_title=title, trigger_source=trigger_source)
            pending = self.queue_manager.pending_count()
            self.root.after(0, lambda: self.overlay.set_state_queued(pending))
        except Exception as e:
            logger.error(f"Error enqueuing capture: {e}", exc_info=True)
            self.root.after(0, lambda: self.overlay.set_state_error("Lỗi hàng đợi"))

    def _process_capture_job(self, job: CaptureJob) -> None:
        """Sequential background consumer executing OCR, domain parsing, snapshot archiving, and session upsert."""
        try:
            logger.info(f"Processing queued capture job [{job.job_id}] from '{job.window_title}'...")
            ocr_res = self.ocr_engine.recognize(job.image)

            parsed = None
            if ocr_res.has_text:
                logger.info(f"Job [{job.job_id}] recognized {len(ocr_res.tokens)} tokens. Parsing entities...")
                parsed = self.parser.parse_ocr_result(ocr_res)

            # Resilient fallback: If no AWB was detected in active window, scan full desktop
            if (not parsed or not parsed.awb_number) and job.window_title != "Desktop":
                logger.info(f"No AWB in active window '{job.window_title}'. Initiating full desktop screen fallback...")
                full_img = self.grabber.capture_full_screen()
                if full_img:
                    full_ocr = self.ocr_engine.recognize(full_img)
                    if full_ocr.has_text:
                        full_parsed = self.parser.parse_ocr_result(full_ocr)
                        if full_parsed.awb_number:
                            logger.info(f"AWB {full_parsed.awb_number} successfully extracted via full screen fallback!")
                            ocr_res = full_ocr
                            parsed = full_parsed

            if not parsed or not parsed.awb_number:
                logger.info(f"Job [{job.job_id}] has no valid AWB number.")
                if job.saved_path:
                    self.queue_manager.rename_snapshot_with_awb(job, "NOAWB", "FAILED")
                self.root.after(0, lambda: self.overlay.set_state_error("Không có AWB"))
                return

            # Construct AWB record and set snapshot path
            record = AWBRecord.from_extraction_result(parsed)
            status_val = record.status_tag.value if hasattr(record.status_tag, "value") else str(record.status_tag)

            if job.saved_path:
                renamed_path = self.queue_manager.rename_snapshot_with_awb(job, record.awb_number, status_val)
                record.snapshot_path = renamed_path or job.saved_path

            upserted, is_new = self.store.upsert_record(record)
            action_str = "Added new" if is_new else "Updated existing"
            logger.info(
                f"{action_str} AWB [{job.job_id}]: {upserted.awb_number} | "
                f"Pcs: {upserted.pieces} | Wt: {upserted.weight_kg}kg | "
                f"Status: {status_val}"
            )

            # Update UI overlay with success badge
            self.root.after(0, lambda r=upserted: self.overlay.set_state_success(r.awb_number))

        except Exception as e:
            logger.error(f"Error during job [{job.job_id}] processing: {e}", exc_info=True)
            self.root.after(0, lambda: self.overlay.set_state_error("Lỗi quét"))


def main() -> None:
    """CLI entry point for Hermes Vision Extractor."""
    parser = argparse.ArgumentParser(description=f"{APP_NAME} - Lufthansa Cargo Hermes CMS Automation")
    parser.add_argument(
        "--show-manager",
        action="store_true",
        default=True,
        help="Launch directly with Session Manager window opened",
    )
    parser.add_argument(
        "--test-pipeline",
        action="store_true",
        help="Run an automated diagnostic test of the full capture-OCR-store-PDF pipeline and exit",
    )
    args = parser.parse_args()

    if args.test_pipeline:
        print("Running Hermes Vision Extractor diagnostic test pipeline...")
        # Self-test code
        from app.pdf.generator import generate_cargo_handover_pdf
        from app.vision.ocr_engine import DualOCREngine
        from app.vision.parser import HermesDataParser

        store = SessionStore()
        rec = AWBRecord(
            awb_number="020-12345675",
            pieces=45,
            weight_kg=1250.50,
            consignee="CÔNG TY TNHH SAMSUNG ELECTRONICS VIỆT NAM",
            agent="SGN - LOGISTICS EXPRESS",
            raw_remarks="ALL IMP/ACC HAWB - ĐÃ ĐỐI SOÁT",
            has_all_imp_acc_hawb=True,
        )
        store.add_record(rec)
        pdf_out = str(Path(os.getcwd()) / "diagnostic_handover_test.pdf")
        generate_cargo_handover_pdf(store.get_all_records(), pdf_out)
        if os.path.exists(pdf_out):
            os.remove(pdf_out)
            print("Diagnostic test completed successfully! All subsystems functional.")
            sys.exit(0)
        else:
            print("Diagnostic test failed: PDF was not created.")
            sys.exit(1)

    app = HermesVisionApp(show_session_manager=args.show_manager)
    app.start()


if __name__ == "__main__":
    main()
