"""Native Desktop GUI Viewer for 50 Hermes CMS Test Samples.

Displays synthetic Hermes CMS mock screen fixtures in a native Windows window
matching the Hermes Cargo Management System title bar. Allows rapid navigation
between 50 test samples for real-time OCR and entity extraction testing.
"""

import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

SAMPLE_DIR = Path(r"f:\Development\plan\50_samples_test_hermes")
MANIFEST_PATH = SAMPLE_DIR / "manifest.json"


class HermesSampleViewer:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("h5 AWB 160-1132 7083")
        self.root.geometry("1060x780+100+40")
        self.root.configure(bg="#0B1120")

        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            self.samples = json.load(f)

        self.current_idx = 0
        self.photo_cache = None

        self._build_ui()
        self.show_sample(0)

        # Bind keyboard shortcuts
        self.root.bind("<Left>", lambda e: self.prev_sample())
        self.root.bind("<Right>", lambda e: self.next_sample())
        self.root.bind("<Alt-f>", lambda e: self.confirm_action())
        self.root.bind("<Alt-F>", lambda e: self.confirm_action())
        self.root.bind("<F12>", lambda e: self.confirm_action())
        self.root.bind("<Control-Return>", lambda e: self.confirm_action())

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self.root, bg="#1E293B", pady=8, padx=12)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        btn_prev = tk.Button(
            toolbar, text="◀ Mẫu trước (←)", font=("Segoe UI", 9, "bold"),
            bg="#0284C7", fg="#FFFFFF", activebackground="#0369A1",
            relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2",
            command=self.prev_sample
        )
        btn_prev.pack(side=tk.LEFT, padx=4)

        self.lbl_counter = tk.Label(
            toolbar, text="1 / 50", font=("Segoe UI", 11, "bold"),
            fg="#FBBF24", bg="#1E293B", padx=10
        )
        self.lbl_counter.pack(side=tk.LEFT)

        btn_next = tk.Button(
            toolbar, text="Mẫu sau (→) ▶", font=("Segoe UI", 9, "bold"),
            bg="#0284C7", fg="#FFFFFF", activebackground="#0369A1",
            relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2",
            command=self.next_sample
        )
        btn_next.pack(side=tk.LEFT, padx=4)

        # Dedicated "Confirm Bill (Alt+F)" button for Lufthansa Cargo Hermes CMS
        self.btn_confirm = tk.Button(
            toolbar, text="💾 Confirm Bill (Alt+F)", font=("Segoe UI", 9, "bold"),
            bg="#059669", fg="#FFFFFF", activebackground="#047857",
            relief=tk.FLAT, bd=0, padx=14, pady=4, cursor="hand2",
            command=self.confirm_action
        )
        self.btn_confirm.pack(side=tk.LEFT, padx=(16, 4))

        # Dropdown
        self.combo_var = tk.StringVar()
        combo_values = [f"#{s['stt']:02d} | {s['awb_number']} - {s['airline']}" for s in self.samples]
        self.combo = ttk.Combobox(toolbar, textvariable=self.combo_var, values=combo_values, width=38, state="readonly")
        self.combo.pack(side=tk.RIGHT, padx=6)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.show_sample(self.combo.current()))

        # Image display container
        self.img_frame = tk.Frame(self.root, bg="#020617", bd=1, relief=tk.SOLID)
        self.img_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 6))

        self.lbl_image = tk.Label(self.img_frame, bg="#000000")
        self.lbl_image.pack(fill=tk.BOTH, expand=True)

        # Info footer
        self.info_frame = tk.Frame(self.root, bg="#1E293B", pady=10, padx=16)
        self.info_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=16, pady=(0, 12))

        self.lbl_info = tk.Label(
            self.info_frame, text="", font=("Segoe UI", 9),
            fg="#F1F5F9", bg="#1E293B", justify=tk.LEFT, anchor="w"
        )
        self.lbl_info.pack(fill=tk.X)

    def show_sample(self, idx: int):
        self.current_idx = (idx + len(self.samples)) % len(self.samples)
        s = self.samples[self.current_idx]

        # Update Hermes H5 window title
        awb = s["awb_number"]
        if "-" in awb:
            prefix, serial = awb.split("-", 1)
        else:
            prefix, serial = awb[:3], awb[3:]
        s_split = f"{serial[:4]} {serial[4:]}" if len(serial) >= 8 else serial
        self.root.title(f"h5 AWB {prefix}-{s_split}")

        # Update counter & combo
        self.lbl_counter.config(text=f"{s['stt']} / {len(self.samples)}")
        self.combo.current(self.current_idx)

        # Load & display image
        img_path = SAMPLE_DIR / s["filename"]
        if img_path.exists():
            pil_img = Image.open(str(img_path))
            self.photo_cache = ImageTk.PhotoImage(pil_img)
            self.lbl_image.config(image=self.photo_cache)

        # Update info text
        status_str = "🟢 ĐÃ DUYỆT (ALL IMP/ACC HAWB)" if s["expected_status"] == "CLEARED" else (
            "🔴 LỖI CHECKSUM MOD-7" if "ERROR" in s["expected_status"] else "🟡 CHƯA DUYỆT HAWB / DIRECT"
        )

        note_str = f" | Ghi chú: {s['note']}" if "note" in s else ""
        info_text = (
            f"Mẫu: {s['id']} | Hãng bay: {s['airline']} | Trạng thái: {status_str}{note_str}\n"
            f"AWB: {s['awb_number']} | Số kiện: {s['pieces']} | Trọng lượng: {s['weight_kg']} KG\n"
            f"Consignee: {s['consignee']} | Agent: {s['agent']}\n"
            f"Remark: {s['remark']}"
        )
        self.lbl_info.config(text=info_text)

    def confirm_action(self):
        """Simulate Hermes Confirm action with brief visual feedback."""
        self.btn_confirm.config(bg="#F59E0B", text="⏳ Đang xử lý Hermes...")
        self.root.after(1000, lambda: self.btn_confirm.config(bg="#059669", text="💾 Confirm Bill (F12)"))

    def next_sample(self):
        self.show_sample(self.current_idx + 1)

    def prev_sample(self):
        self.show_sample(self.current_idx - 1)


def main():
    root = tk.Tk()
    app = HermesSampleViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()