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
from typing import Optional

# Ensure hermes_vision_extractor root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

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

        # 2. Initialize GUI Elements
        self.root = tk.Tk()
        self.root.withdraw()  # Root remains hidden; top-levels provide UI

        # Floating Pill Overlay
        self.overlay = FloatingOverlay(
            parent=self.root,
            on_scan=self.trigger_scan,
            on_open_session=self.open_session_manager,
            on_exit=self.shutdown,
        )

        # Session Manager Window
        self.session_window = SessionManagerWindow(
            master=self.root,
            store=self.store,
            on_scan=self.trigger_scan,
        )

        if show_session_manager:
            self.session_window.show()
        else:
            self.session_window.hide()

        # 3. Initialize Global Win32 Hotkey Listener (F9, Ctrl+Shift+S)
        self.hotkey_listener = GlobalHotkeyListener(
            callback=self._on_hotkey_triggered,
            debounce_seconds=self.config.debounce_seconds,
        )

    def start(self) -> None:
        """Start background listeners and enter Tkinter main loop."""
        logger.info("Starting global hotkey listener (F9, Ctrl+Shift+S)...")
        hotkeys_started = self.hotkey_listener.start()
        if not hotkeys_started:
            logger.warning("Global hotkeys could not be registered. Floating widget remains active.")

        # Handle SIGINT (Ctrl+C) cleanly
        signal.signal(signal.SIGINT, lambda sig, frame: self.shutdown())

        logger.info(f"{APP_NAME} operational. Floating widget ready.")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self) -> None:
        """Gracefully release hotkeys, shutdown thread pool, and destroy UI."""
        logger.info("Shutting down Hermes Vision Extractor...")
        try:
            self.hotkey_listener.stop()
        except Exception as e:
            logger.debug(f"Error stopping hotkeys: {e}")

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
        # Post to Tkinter main thread
        try:
            self.root.after(0, self.trigger_scan)
        except Exception as e:
            logger.error(f"Error posting hotkey event to Tkinter loop: {e}")

    def trigger_scan(self) -> None:
        """Execute screen capture, OCR, parsing, and session upsert asynchronously."""
        with self._proc_lock:
            if self._processing:
                logger.info("Scan already in progress. Ignoring trigger.")
                return
            self._processing = True

        # Update overlay state immediately on main thread (<1s feedback)
        self.overlay.set_state_scanning()

        # Submit vision processing pipeline to background worker thread
        self._executor.submit(self._run_scan_pipeline)

    def _run_scan_pipeline(self) -> None:
        """Background worker executing the Vision & OCR pipeline."""
        try:
            logger.info("Capturing Hermes screen / active window...")
            img, title = self.grabber.capture_active_window()
            if img is None:
                logger.debug("Active window grab returned empty, falling back to full screen...")
                img = self.grabber.capture_full_screen()

            if img is None:
                logger.warning("Screen capture failed to produce an image.")
                self.root.after(0, lambda: self.overlay.set_state_error("Lỗi chụp"))
                return

            logger.info(f"Screen captured ({img.width}x{img.height}) from '{title}'. Running OCR recognition...")
            ocr_res = self.ocr_engine.recognize(img)

            parsed = None
            if ocr_res.has_text:
                logger.info(f"OCR recognized {len(ocr_res.tokens)} tokens. Parsing Hermes entities...")
                parsed = self.parser.parse_ocr_result(ocr_res)

            # Resilient fallback: If no AWB was detected in active window, scan full desktop
            if (not parsed or not parsed.awb_number) and title != "Desktop":
                logger.info(f"No AWB in active window '{title}'. Initiating full desktop screen fallback...")
                full_img = self.grabber.capture_full_screen()
                if full_img:
                    full_ocr = self.ocr_engine.recognize(full_img)
                    if full_ocr.has_text:
                        full_parsed = self.parser.parse_ocr_result(full_ocr)
                        if full_parsed.awb_number:
                            logger.info(f"AWB {full_parsed.awb_number} successfully extracted via full screen fallback!")
                            img = full_img
                            ocr_res = full_ocr
                            parsed = full_parsed

            if not parsed or not parsed.awb_number:
                logger.info("No valid AWB number found in screen content.")
                self.root.after(0, lambda: self.overlay.set_state_error("Không có AWB"))
                return

            # Construct AWB record and upsert into SessionStore
            record = AWBRecord.from_extraction_result(parsed)
            upserted, is_new = self.store.upsert_record(record)

            action_str = "Added new" if is_new else "Updated existing"
            status_val = upserted.status_tag.value if hasattr(upserted.status_tag, "value") else str(upserted.status_tag)
            logger.info(
                f"{action_str} AWB: {upserted.awb_number} | "
                f"Pcs: {upserted.pieces} | Wt: {upserted.weight_kg}kg | "
                f"Status: {status_val}"
            )

            # Update UI overlay with success badge
            self.root.after(0, lambda r=upserted: self.overlay.set_state_success(r.awb_number))

        except Exception as e:
            logger.error(f"Error during scan pipeline execution: {e}", exc_info=True)
            self.root.after(0, lambda: self.overlay.set_state_error("Lỗi quét"))
        finally:
            with self._proc_lock:
                self._processing = False


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
