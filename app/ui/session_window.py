"""Session AWB Manager Desktop UI for Hermes Vision Extractor.

Provides a comprehensive operational window with Treeview list of scanned AWBs,
color-coded status badges (CLEARED, PENDING_HAWB, DIRECT_SHIPMENT, CHECKSUM_ERROR),
action toolbar for editing/deleting/clearing records, real-time aggregate KPI summary bar,
and modal dialogs for record modification and A4 PDF export/preview/printing.
"""

from datetime import datetime
import html
import logging
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from app.core.classifier import BusinessRuleClassifier
from app.core.models import AWBRecord, BusinessStatus, SessionSummary
from app.core.session_store import SessionStore
from app.pdf.generator import generate_cargo_handover_pdf, preview_pdf, print_pdf

logger = logging.getLogger(__name__)


class SessionManagerWindow(tk.Toplevel):
    """Operational window for viewing, filtering, editing, and exporting scanned AWB records."""

    def __init__(
        self,
        master: tk.Tk,
        store: SessionStore,
        on_scan: Optional[Callable[[], None]] = None,
        on_toggle_auto: Optional[Callable[[bool], None]] = None,
        on_pick_window: Optional[Callable[[], None]] = None,
        on_calibrate_button: Optional[Callable[[], None]] = None,
        on_set_delay: Optional[Callable[[float], None]] = None,
    ) -> None:
        super().__init__(master)

        self.store = store
        self.on_scan = on_scan
        self.on_toggle_auto = on_toggle_auto
        self.on_pick_window = on_pick_window
        self.on_calibrate_button = on_calibrate_button
        self.on_set_delay = on_set_delay

        self.title("Quản Lý Vận Đơn Ca Trực - Hermes CMS Vision Extractor")
        self.geometry("1060x640")
        self.minsize(860, 500)

        # Intercept window close button to hide instead of exit app
        self.protocol("WM_DELETE_WINDOW", self.hide)

        # Build UI layout
        self._setup_styles()
        self._build_toolbar()
        self._build_auto_toolbar()
        self._build_treeview()
        self._build_summary_bar()

        # Subscribe to SessionStore observer events
        self.store.subscribe(self._on_store_event)

        # Initial populate
        self.refresh_records()

    def hide(self) -> None:
        """Hide window without destroying it, preserving background state."""
        self.withdraw()

    def show(self) -> None:
        """Show, deiconify and bring window to foreground."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _setup_styles(self) -> None:
        """Configure ttk styles and Treeview color badge tags."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Treeview styling
        style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=26,
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            background="#0F172A",
            foreground="#FFFFFF",
            padding=4,
        )
        style.map("Treeview.Heading", background=[("active", "#1E293B")])

    def _build_toolbar(self) -> None:
        """Construct top action toolbar."""
        toolbar = tk.Frame(self, bg="#F1F5F9", height=42, padx=8, pady=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        # Primary Scan Button
        self.btn_scan = tk.Button(
            toolbar,
            text="🔍 Quét Ngay (F9)",
            font=("Segoe UI", 9, "bold"),
            bg="#0284C7",
            fg="#FFFFFF",
            activebackground="#0369A1",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._handle_scan,
        )
        self.btn_scan.pack(side=tk.LEFT, padx=(0, 6))

        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=2)

        # Edit Button
        self.btn_edit = tk.Button(
            toolbar,
            text="✏️ Chỉnh Sửa",
            font=("Segoe UI", 9),
            bg="#E2E8F0",
            fg="#0F172A",
            activebackground="#CBD5E1",
            relief=tk.FLAT,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._handle_edit,
        )
        self.btn_edit.pack(side=tk.LEFT, padx=4)

        # Delete Button
        self.btn_delete = tk.Button(
            toolbar,
            text="🗑️ Xóa",
            font=("Segoe UI", 9),
            bg="#FEE2E2",
            fg="#991B1B",
            activebackground="#FCA5A5",
            relief=tk.FLAT,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._handle_delete,
        )
        self.btn_delete.pack(side=tk.LEFT, padx=4)

        # Clear Session Button
        self.btn_clear = tk.Button(
            toolbar,
            text="🧹 Xóa Ca",
            font=("Segoe UI", 9),
            bg="#F3F4F6",
            fg="#4B5563",
            activebackground="#E5E7EB",
            relief=tk.FLAT,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._handle_clear,
        )
        self.btn_clear.pack(side=tk.LEFT, padx=4)

        # Separator
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        # Export PDF Button (Primary Action)
        self.btn_export = tk.Button(
            toolbar,
            text="📄 Xuất / In PDF (A4)",
            font=("Segoe UI", 9, "bold"),
            bg="#059669",
            fg="#FFFFFF",
            activebackground="#047857",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._handle_export_dialog,
        )
        self.btn_export.pack(side=tk.LEFT, padx=4)

        # Right Side: Quick Search / Filter
        lbl_filter = tk.Label(toolbar, text="Lọc trạng thái:", bg="#F1F5F9", font=("Segoe UI", 9))
        lbl_filter.pack(side=tk.LEFT, padx=(16, 4))

        self.filter_var = tk.StringVar(value="Tất Cả")
        self.combo_filter = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=["Tất Cả", "CLEARED", "PENDING_HAWB", "DIRECT_SHIPMENT", "CHECKSUM_ERROR"],
            state="readonly",
            width=15,
            font=("Segoe UI", 9),
        )
        self.combo_filter.pack(side=tk.LEFT, padx=2)
        self.combo_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh_records())

    def _build_auto_toolbar(self) -> None:
        """Construct secondary toolbar for Auto-Scan and target Hermes window controls."""
        auto_bar = tk.Frame(self, bg="#E2E8F0", padx=8, pady=4)
        auto_bar.pack(side=tk.TOP, fill=tk.X)

        self.var_auto_scan = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(
            auto_bar,
            text="⚡ Tự động quét khi Confirm (Chuột / Phím)",
            variable=self.var_auto_scan,
            font=("Segoe UI", 9, "bold"),
            bg="#E2E8F0",
            fg="#0F172A",
            activebackground="#E2E8F0",
            command=self._handle_toggle_auto,
        )
        chk.pack(side=tk.LEFT, padx=(0, 10))

        btn_pin = tk.Button(
            auto_bar,
            text="🎯 Ghim Cửa Sổ Hermes...",
            font=("Segoe UI", 8, "bold"),
            bg="#0284C7",
            fg="#FFFFFF",
            activebackground="#0369A1",
            relief=tk.FLAT,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._handle_pick_window,
        )
        btn_pin.pack(side=tk.LEFT, padx=4)

        btn_calib = tk.Button(
            auto_bar,
            text="📍 Chấm Nút Confirm...",
            font=("Segoe UI", 8),
            bg="#475569",
            fg="#FFFFFF",
            activebackground="#334155",
            relief=tk.FLAT,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._handle_calibrate_button,
        )
        btn_calib.pack(side=tk.LEFT, padx=4)

        tk.Label(auto_bar, text="⏱ Độ trễ:", font=("Segoe UI", 8), bg="#E2E8F0", fg="#475569").pack(side=tk.LEFT, padx=(10, 2))
        self.combo_delay = ttk.Combobox(auto_bar, values=["0.5s", "1.0s", "1.5s", "2.0s"], width=6, state="readonly")
        self.combo_delay.set("1.0s")
        self.combo_delay.pack(side=tk.LEFT, padx=2)
        self.combo_delay.bind("<<ComboboxSelected>>", self._handle_delay_selected)

        self.lbl_target_info = tk.Label(
            auto_bar,
            text="🎯 Cửa sổ theo dõi: Tự động nhận diện",
            font=("Segoe UI", 8, "bold"),
            bg="#E2E8F0",
            fg="#0369A1",
        )
        self.lbl_target_info.pack(side=tk.RIGHT, padx=6)

    def _handle_toggle_auto(self) -> None:
        if self.on_toggle_auto:
            self.on_toggle_auto(self.var_auto_scan.get())

    def _handle_pick_window(self) -> None:
        if self.on_pick_window:
            self.on_pick_window()

    def _handle_calibrate_button(self) -> None:
        if self.on_calibrate_button:
            self.on_calibrate_button()

    def _handle_delay_selected(self, event: Any) -> None:
        val_str = self.combo_delay.get().replace("s", "")
        try:
            delay = float(val_str)
            if self.on_set_delay:
                self.on_set_delay(delay)
        except ValueError:
            pass

    def set_pinned_title(self, title: str) -> None:
        """Update toolbar status display showing pinned window."""
        if hasattr(self, "lbl_target_info"):
            if title:
                self.lbl_target_info.config(text=f"🎯 Đang ghim: {title[:28]}", fg="#059669")
            else:
                self.lbl_target_info.config(text="🎯 Cửa sổ: Tự động nhận diện", fg="#0369A1")

    def set_auto_enabled(self, enabled: bool) -> None:
        """Update auto-scan checkbox state."""
        if hasattr(self, "var_auto_scan"):
            self.var_auto_scan.set(enabled)

    def set_delay(self, delay: float) -> None:
        """Update delay combobox value."""
        if hasattr(self, "combo_delay"):
            self.combo_delay.set(f"{delay:.1f}s")

    def _build_treeview(self) -> None:
        """Construct central Treeview table and scrollbars."""
        tree_frame = tk.Frame(self)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(4, 0))

        columns = (
            "stt",
            "awb_number",
            "pieces",
            "weight_kg",
            "consignee",
            "agent",
            "hawb_status",
            "status",
            "remark",
            "time",
        )

        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        # Column Headings & Widths
        self.tree.heading("stt", text="#", anchor=tk.CENTER)
        self.tree.heading("awb_number", text="Số AWB", anchor=tk.CENTER)
        self.tree.heading("pieces", text="Kiện (Colli)", anchor=tk.E)
        self.tree.heading("weight_kg", text="Trọng Lượng (KG)", anchor=tk.E)
        self.tree.heading("consignee", text="Người Nhận (Consignee)", anchor=tk.W)
        self.tree.heading("agent", text="Đại Lý (Agent)", anchor=tk.W)
        self.tree.heading("hawb_status", text="ALL IMP/ACC HAWB", anchor=tk.CENTER)
        self.tree.heading("status", text="Trạng Thái", anchor=tk.CENTER)
        self.tree.heading("remark", text="Ghi Chú (Remark)", anchor=tk.W)
        self.tree.heading("time", text="Thời Điểm", anchor=tk.CENTER)

        self.tree.column("stt", width=36, minwidth=30, anchor=tk.CENTER)
        self.tree.column("awb_number", width=105, minwidth=90, anchor=tk.CENTER)
        self.tree.column("pieces", width=75, minwidth=60, anchor=tk.E)
        self.tree.column("weight_kg", width=95, minwidth=70, anchor=tk.E)
        self.tree.column("consignee", width=190, minwidth=140, anchor=tk.W)
        self.tree.column("agent", width=130, minwidth=100, anchor=tk.W)
        self.tree.column("hawb_status", width=125, minwidth=100, anchor=tk.CENTER)
        self.tree.column("status", width=120, minwidth=90, anchor=tk.CENTER)
        self.tree.column("remark", width=180, minwidth=120, anchor=tk.W)
        self.tree.column("time", width=75, minwidth=65, anchor=tk.CENTER)

        # Scrollbars
        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Define color tags for BusinessStatus
        self.tree.tag_configure("CLEARED", background="#ECFDF5", foreground="#065F46")
        self.tree.tag_configure("PENDING_HAWB", background="#FFFBEB", foreground="#B45309")
        self.tree.tag_configure("DIRECT_SHIPMENT", background="#EFF6FF", foreground="#1D4ED8")
        self.tree.tag_configure("CHECKSUM_ERROR", background="#FEF2F2", foreground="#991B1B")

        # Bind events
        self.tree.bind("<Double-1>", lambda e: self._handle_edit())

    def _build_summary_bar(self) -> None:
        """Construct bottom status summary bar."""
        self.status_bar = tk.Frame(self, bg="#0F172A", height=32, padx=10, pady=4)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_stats = tk.Label(
            self.status_bar,
            text="Đang tải dữ liệu ca trực...",
            font=("Segoe UI", 9),
            fg="#F8FAFC",
            bg="#0F172A",
            anchor="w",
        )
        self.lbl_stats.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # -------------------------------------------------------------------------
    # Event Handlers & Data Binding
    # -------------------------------------------------------------------------
    def _on_store_event(self, event_type: str, data: Any) -> None:
        """Thread-safe event listener from SessionStore."""
        # Dispatch to Tkinter main thread
        try:
            self.after(0, self.refresh_records)
        except Exception:
            pass

    def refresh_records(self) -> None:
        """Reload and render records in Treeview based on current filter."""
        selected_iid = self.tree.focus()

        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        records = self.store.get_all_records()
        filter_val = self.filter_var.get()

        displayed_count = 0
        for idx, rec in enumerate(records, start=1):
            status_val = rec.status_tag.value if hasattr(rec.status_tag, "value") else str(rec.status_tag)

            if filter_val != "Tất Cả" and status_val != filter_val:
                continue

            displayed_count += 1
            pcs_str = f"{rec.pieces:,}" if rec.pieces is not None else "-"
            wt_str = f"{rec.weight_kg:,.2f}" if rec.weight_kg is not None else "-"

            # Time formatting
            time_display = ""
            if rec.timestamp:
                try:
                    dt = datetime.fromisoformat(rec.timestamp.replace("Z", "+00:00"))
                    time_display = dt.strftime("%H:%M:%S")
                except Exception:
                    time_display = rec.timestamp[:8]

            hawb_badge = "✔ ALL IMP/ACC" if rec.has_all_imp_acc_hawb else "-"

            self.tree.insert(
                "",
                "end",
                iid=rec.id,
                values=(
                    str(displayed_count),
                    rec.awb_number,
                    pcs_str,
                    wt_str,
                    rec.consignee or "-",
                    rec.agent or "-",
                    hawb_badge,
                    status_val,
                    rec.raw_remarks or "-",
                    time_display,
                ),
                tags=(status_val,),
            )

        # Restore selection if still exists
        if selected_iid and self.tree.exists(selected_iid):
            self.tree.selection_set(selected_iid)
            self.tree.focus(selected_iid)

        # Update Summary metrics bar
        self._update_summary_bar()

    def _update_summary_bar(self) -> None:
        """Recalculate and display session statistics."""
        summary: SessionSummary = self.store.get_summary()

        stats_text = (
            f"📊 Tổng AWB: {summary.total_records}  │  "
            f"Tổng Kiện: {summary.total_pieces:,} Colli  │  "
            f"Tổng KG: {summary.total_weight_kg:,.2f} kg  │  "
            f"Đã duyệt HAWB (ALL IMP): {summary.cleared_count}/{summary.total_records} ({summary.cleared_ratio:.1f}%)  │  "
            f"Chờ HAWB: {summary.pending_hawb_count}  │  "
            f"Lỗi Checksum: {summary.checksum_error_count}"
        )
        self.lbl_stats.config(text=stats_text)

    # -------------------------------------------------------------------------
    # Action Toolbar Commands
    # -------------------------------------------------------------------------
    def _handle_scan(self) -> None:
        """Trigger instant screen scan."""
        if self.on_scan:
            self.on_scan()

    def _handle_edit(self) -> None:
        """Open edit dialog for selected record."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Chỉnh Sửa", "Vui lòng chọn một dòng vận đơn để chỉnh sửa.", parent=self)
            return

        record_id = selected[0]
        record = self.store.get_record(record_id)
        if not record:
            return

        dialog = EditRecordDialog(self, record)
        self.wait_window(dialog)

        if dialog.result_updates:
            self.store.update_record(record_id, dialog.result_updates)
            self.refresh_records()

    def _handle_delete(self) -> None:
        """Delete selected record with user confirmation."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Xóa Bản Ghi", "Vui lòng chọn một dòng vận đơn để xóa.", parent=self)
            return

        record_id = selected[0]
        record = self.store.get_record(record_id)
        if not record:
            return

        confirm = messagebox.askyesno(
            "Xác Nhận Xóa",
            f"Bạn có chắc muốn xóa vận đơn {record.awb_number} khỏi ca trực?",
            parent=self,
        )
        if confirm:
            self.store.delete_record(record_id)
            self.refresh_records()

    def _handle_clear(self) -> None:
        """Clear all session records with user confirmation."""
        if self.store.count() == 0:
            return

        confirm = messagebox.askyesno(
            "Xóa Toàn Bộ Ca",
            f"Bạn có chắc muốn xóa tất cả {self.store.count()} vận đơn trong ca trực hiện tại?",
            icon="warning",
            parent=self,
        )
        if confirm:
            self.store.clear_all()
            self.refresh_records()

    def _handle_export_dialog(self) -> None:
        """Open PDF Export and Print configuration modal dialog."""
        records = self.store.get_all_records()
        if not records:
            messagebox.showinfo(
                "Xuất PDF",
                "Chưa có bản ghi vận đơn nào trong ca trực để xuất phiếu.",
                parent=self,
            )
            return

        ExportPdfDialog(self, records, self.store.get_summary())


class EditRecordDialog(tk.Toplevel):
    """Modal dialog for modifying AWB cargo fields."""

    def __init__(self, parent: tk.Widget, record: AWBRecord) -> None:
        super().__init__(parent)
        self.record = record
        self.result_updates: Optional[Dict[str, Any]] = None

        self.title(f"Chỉnh Sửa AWB: {record.awb_number}")
        self.geometry("460x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_form()

    def _build_form(self) -> None:
        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        # AWB Number
        tk.Label(frame, text="Số AWB:", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_awb = tk.Entry(frame, font=("Segoe UI", 9), width=28)
        self.ent_awb.insert(0, self.record.awb_number)
        self.ent_awb.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # Pieces (Colli)
        tk.Label(frame, text="Số Kiện (Colli):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_pcs = tk.Entry(frame, font=("Segoe UI", 9), width=28)
        if self.record.pieces is not None:
            self.ent_pcs.insert(0, str(self.record.pieces))
        self.ent_pcs.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # Weight (KG)
        tk.Label(frame, text="Trọng Lượng (KG):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_wt = tk.Entry(frame, font=("Segoe UI", 9), width=28)
        if self.record.weight_kg is not None:
            self.ent_wt.insert(0, str(self.record.weight_kg))
        self.ent_wt.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # Consignee
        tk.Label(frame, text="Người Nhận (Consignee):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_cnee = tk.Entry(frame, font=("Segoe UI", 9), width=28)
        self.ent_cnee.insert(0, self.record.consignee)
        self.ent_cnee.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # Agent
        tk.Label(frame, text="Đại Lý (Agent):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_agt = tk.Entry(frame, font=("Segoe UI", 9), width=28)
        self.ent_agt.insert(0, self.record.agent)
        self.ent_agt.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # Remarks
        tk.Label(frame, text="Ghi Chú (Remark):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_rmk = tk.Entry(frame, font=("Segoe UI", 9), width=28)
        self.ent_rmk.insert(0, self.record.raw_remarks)
        self.ent_rmk.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # ALL IMP/ACC HAWB Checkbox
        self.var_hawb = tk.BooleanVar(value=self.record.has_all_imp_acc_hawb)
        chk_hawb = tk.Checkbutton(
            frame,
            text="Đạt điều kiện 'ALL IMP/ACC HAWB'",
            variable=self.var_hawb,
            font=("Segoe UI", 9, "bold"),
            fg="#059669",
        )
        chk_hawb.grid(row=row, column=0, columnspan=2, sticky="w", pady=8)
        row += 1

        # Status Tag Override
        tk.Label(frame, text="Trạng Thái Nghiệp Vụ:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        curr_status = self.record.status_tag.value if hasattr(self.record.status_tag, "value") else str(self.record.status_tag)
        self.combo_status = ttk.Combobox(
            frame,
            values=["CLEARED", "PENDING_HAWB", "DIRECT_SHIPMENT", "CHECKSUM_ERROR"],
            state="readonly",
            width=26,
            font=("Segoe UI", 9),
        )
        self.combo_status.set(curr_status)
        self.combo_status.grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        # Buttons
        btn_frame = tk.Frame(frame, pady=10)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="e")

        btn_cancel = tk.Button(btn_frame, text="Hủy", command=self.destroy, padx=12, pady=4)
        btn_cancel.pack(side=tk.RIGHT, padx=4)

        btn_save = tk.Button(
            btn_frame,
            text="Lưu Thay Đổi",
            bg="#0284C7",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            command=self._save,
            padx=14,
            pady=4,
        )
        btn_save.pack(side=tk.RIGHT, padx=4)

    def _save(self) -> None:
        """Validate and construct updates dict."""
        awb = self.ent_awb.get().strip()
        if not awb:
            messagebox.showerror("Lỗi", "Số AWB không được để trống.", parent=self)
            return

        pcs_str = self.ent_pcs.get().strip()
        pcs: Optional[int] = None
        if pcs_str:
            try:
                pcs = int(pcs_str)
                if pcs < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Lỗi", "Số kiện phải là số nguyên không âm.", parent=self)
                return

        wt_str = self.ent_wt.get().strip()
        wt: Optional[float] = None
        if wt_str:
            try:
                wt = float(wt_str.replace(",", "."))
                if wt < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Lỗi", "Trọng lượng phải là số thực không âm.", parent=self)
                return

        status_str = self.combo_status.get()
        try:
            status_enum = BusinessStatus(status_str)
        except Exception:
            status_enum = BusinessStatus.DIRECT_SHIPMENT

        self.result_updates = {
            "awb_number": awb,
            "pieces": pcs,
            "weight_kg": wt,
            "consignee": self.ent_cnee.get().strip(),
            "agent": self.ent_agt.get().strip(),
            "raw_remarks": self.ent_rmk.get().strip(),
            "has_all_imp_acc_hawb": self.var_hawb.get(),
            "status_tag": status_enum,
        }
        self.destroy()


class ExportPdfDialog(tk.Toplevel):
    """Configuration dialog for generating and previewing/printing ISO A4 PDF report."""

    def __init__(
        self,
        parent: tk.Widget,
        records: List[AWBRecord],
        summary: SessionSummary,
    ) -> None:
        super().__init__(parent)
        self.records = records
        self.summary = summary

        self.title("Xuất Phiếu Đối Soát Ca Trực (Khổ A4 Chuẩn)")
        self.geometry("520x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        # Title
        tk.Label(
            frame,
            text="THÔNG TIN PHIẾU BÀN GIAO CA (HERMES CMS)",
            font=("Segoe UI", 10, "bold"),
            fg="#00205B",
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        row += 1

        # Shift Name
        tk.Label(frame, text="Ca trực:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_shift = tk.Entry(frame, font=("Segoe UI", 9), width=32)
        self.ent_shift.insert(0, "Ca 1 - Đội Khai Thác NCTS")
        self.ent_shift.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        row += 1

        # Handover Person
        tk.Label(frame, text="Nhân viên giao ca:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_handover = tk.Entry(frame, font=("Segoe UI", 9), width=32)
        self.ent_handover.insert(0, "Nhân viên xử lý Hermes")
        self.ent_handover.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        row += 1

        # Receiver Person
        tk.Label(frame, text="Nhân viên nhận ca:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_receiver = tk.Entry(frame, font=("Segoe UI", 9), width=32)
        self.ent_receiver.insert(0, "Nhân viên ca kế tiếp")
        self.ent_receiver.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        row += 1

        # Station
        tk.Label(frame, text="Trạm khai thác:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self.ent_station = tk.Entry(frame, font=("Segoe UI", 9), width=32)
        self.ent_station.insert(0, "HAN / NCTS Cargo Hub")
        self.ent_station.grid(row=row, column=1, columnspan=2, sticky="w", pady=4)
        row += 1

        # Output Path
        tk.Label(frame, text="Lưu file PDF tại:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        default_name = f"Phieu_Doi_Soat_Hermes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path(os.getcwd())

        self.path_var = tk.StringVar(value=str(default_dir / default_name))
        self.ent_path = tk.Entry(frame, textvariable=self.path_var, font=("Segoe UI", 9), width=32)
        self.ent_path.grid(row=row, column=1, sticky="w", pady=4)

        btn_browse = tk.Button(frame, text="Chọn...", command=self._browse_path, padx=6)
        btn_browse.grid(row=row, column=2, sticky="w", padx=4, pady=4)
        row += 1

        # Summary Note
        total_recs = len(self.records)
        cleared_cnt = sum(1 for r in self.records if r.has_all_imp_acc_hawb or r.status_tag == BusinessStatus.CLEARED)
        note_text = f"Số lượng vận đơn: {total_recs}  |  Đạt 'ALL IMP/ACC HAWB': {cleared_cnt}"
        tk.Label(frame, text=note_text, font=("Segoe UI", 9, "italic"), fg="#059669").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=8
        )
        row += 1

        # Action Buttons
        btn_frame = tk.Frame(frame, pady=10)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="e")

        btn_close = tk.Button(btn_frame, text="Đóng", command=self.destroy, padx=10, pady=3)
        btn_close.pack(side=tk.RIGHT, padx=4)

        btn_print = tk.Button(
            btn_frame,
            text="🖨️ In Trực Tiếp",
            bg="#334155",
            fg="#FFFFFF",
            font=("Segoe UI", 9),
            command=self._do_print,
            padx=10,
            pady=3,
        )
        btn_print.pack(side=tk.RIGHT, padx=4)

        btn_preview = tk.Button(
            btn_frame,
            text="👁️ Xem Trước",
            bg="#0284C7",
            fg="#FFFFFF",
            font=("Segoe UI", 9),
            command=self._do_preview,
            padx=10,
            pady=3,
        )
        btn_preview.pack(side=tk.RIGHT, padx=4)

        btn_export = tk.Button(
            btn_frame,
            text="📄 Xuất PDF",
            bg="#059669",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            command=self._do_export,
            padx=12,
            pady=3,
        )
        btn_export.pack(side=tk.RIGHT, padx=4)

    def _browse_path(self) -> None:
        """Open file dialog to pick save location."""
        picked = filedialog.asksaveasfilename(
            parent=self,
            title="Chọn Nơi Lưu Phiếu Đối Soát PDF",
            defaultextension=".pdf",
            filetypes=[("PDF Document", "*.pdf")],
            initialfile=Path(self.path_var.get()).name,
        )
        if picked:
            self.path_var.set(picked)

    def _generate(self) -> Optional[str]:
        """Generate PDF and return its path."""
        target_path = self.path_var.get().strip()
        if not target_path:
            messagebox.showerror("Lỗi", "Vui lòng chỉ định đường dẫn lưu file PDF.", parent=self)
            return None

        try:
            generated = generate_cargo_handover_pdf(
                records=self.records,
                output_path=target_path,
                shift_name=self.ent_shift.get().strip(),
                handover_person=self.ent_handover.get().strip(),
                receiver_person=self.ent_receiver.get().strip(),
                station=self.ent_station.get().strip(),
                summary=self.summary,
            )
            return generated
        except Exception as e:
            logger.error(f"Error generating PDF: {e}", exc_info=True)
            messagebox.showerror("Lỗi Xuất PDF", f"Không thể tạo file PDF:\n{e}", parent=self)
            return None

    def _do_export(self) -> None:
        """Generate PDF and notify user."""
        pdf_path = self._generate()
        if pdf_path:
            messagebox.showinfo(
                "Thành Công",
                f"Đã xuất phiếu đối soát A4 thành công tại:\n{pdf_path}",
                parent=self,
            )

    def _do_preview(self) -> None:
        """Generate PDF and launch preview."""
        pdf_path = self._generate()
        if pdf_path:
            success = preview_pdf(pdf_path)
            if not success:
                messagebox.showwarning(
                    "Xem Trước",
                    f"Đã tạo file tại {pdf_path} nhưng không mở được trình xem tự động.",
                    parent=self,
                )

    def _do_print(self) -> None:
        """Generate PDF and send to printer."""
        pdf_path = self._generate()
        if pdf_path:
            success = print_pdf(pdf_path)
            if success:
                messagebox.showinfo("In Phiếu", "Lệnh in đã được gửi đến máy in thành công!", parent=self)
            else:
                messagebox.showwarning("In Phiếu", "Gửi lệnh in thất bại. Vui lòng kiểm tra kết nối máy in.", parent=self)
