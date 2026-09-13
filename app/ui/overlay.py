"""Floating Widget Overlay for Hermes Vision Extractor.

Provides a lightweight (<30MB RAM), borderless, always-on-top, semi-transparent
pill widget that floats over Hermes CMS. Supports smooth mouse drag-and-drop,
single-click instant scan trigger, visual pulse animation, and direct access
to the Session Manager window.
"""

import logging
import platform
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class FloatingOverlay(tk.Toplevel):
    """Borderless, draggable, semi-transparent pill overlay for one-touch Hermes screen capture."""

    def __init__(
        self,
        parent: Optional[tk.Tk] = None,
        on_scan: Optional[Callable[[], None]] = None,
        on_open_session: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
        on_toggle_auto: Optional[Callable[[bool], None]] = None,
        on_pick_window: Optional[Callable[[], None]] = None,
        on_calibrate_button: Optional[Callable[[], None]] = None,
        on_set_delay: Optional[Callable[[float], None]] = None,
        initial_x: Optional[int] = None,
        initial_y: Optional[int] = None,
    ) -> None:
        # If no parent Tk instance provided, create hidden master
        self._own_master = False
        if parent is None:
            master = tk.Tk()
            master.withdraw()
            self._own_master = True
        else:
            master = parent

        super().__init__(master)

        self.on_scan = on_scan
        self.on_open_session = on_open_session
        self.on_exit = on_exit
        self.on_toggle_auto = on_toggle_auto
        self.on_pick_window = on_pick_window
        self.on_calibrate_button = on_calibrate_button
        self.on_set_delay = on_set_delay

        # Window state tracking
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_scanning = False
        self._pulse_count = 0
        self._pulse_timer: Optional[str] = None
        self._restore_timer: Optional[str] = None
        self._countdown_timer: Optional[str] = None
        self._auto_enabled = True
        self._current_delay = 1.0
        self._pinned_title = ""

        # Widget Dimensions
        self.widget_width = 390
        self.widget_height = 44

        # Configure window properties
        self._init_window_properties(initial_x, initial_y)

        # Build UI layout
        self._build_ui()

        # Set initial ready state
        self.set_state_ready()

    def _init_window_properties(self, initial_x: Optional[int], initial_y: Optional[int]) -> None:
        """Apply borderless, topmost, semi-transparent, and positioning attributes."""
        # Remove OS window decorations (borderless pill)
        self.overrideredirect(True)

        # Keep always on top of Hermes CMS
        self.wm_attributes("-topmost", True)

        # Apply 88% alpha semi-transparency for sleek modern aesthetic
        try:
            self.wm_attributes("-alpha", 0.88)
        except Exception:
            pass  # Fallback gracefully if platform does not support alpha

        # Calculate initial position (top-right corner of screen)
        screen_w = self.winfo_screenwidth()
        x = initial_x if initial_x is not None else max(10, screen_w - self.widget_width - 40)
        y = initial_y if initial_y is not None else 60

        self.geometry(f"{self.widget_width}x{self.widget_height}+{x}+{y}")
        self.resizable(False, False)

        # Bind mouse events for smooth dragging
        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_motion)

    def _build_ui(self) -> None:
        """Construct the visual elements inside the floating pill."""
        # Main container with dark slate background
        self.bg_frame = tk.Frame(
            self,
            bg="#0F172A",  # Slate 900
            highlightthickness=1,
            highlightbackground="#334155",  # Slate 700 subtle border
            cursor="fleur",  # Move cursor
        )
        self.bg_frame.pack(fill=tk.BOTH, expand=True)

        # Bind drag to container frame
        self.bg_frame.bind("<ButtonPress-1>", self._on_drag_start)
        self.bg_frame.bind("<B1-Motion>", self._on_drag_motion)

        # 1. Grip / Brand Label (Left)
        self.grip_label = tk.Label(
            self.bg_frame,
            text="✈ LH",
            font=("Segoe UI", 9, "bold"),
            fg="#38BDF8",  # Sky blue
            bg="#0F172A",
            padx=6,
            cursor="fleur",
        )
        self.grip_label.pack(side=tk.LEFT, padx=(6, 2))
        self.grip_label.bind("<ButtonPress-1>", self._on_drag_start)
        self.grip_label.bind("<B1-Motion>", self._on_drag_motion)

        # 2. Status / State Indicator Label
        self.status_label = tk.Label(
            self.bg_frame,
            text="Ready (F9)",
            font=("Segoe UI", 8),
            fg="#94A3B8",  # Slate 400
            bg="#0F172A",
            width=14,
            anchor="w",
            cursor="fleur",
        )
        self.status_label.pack(side=tk.LEFT, padx=(2, 4), fill=tk.Y)
        self.status_label.bind("<ButtonPress-1>", self._on_drag_start)
        self.status_label.bind("<B1-Motion>", self._on_drag_motion)

        # 3. Action Buttons Container (Right)
        btn_frame = tk.Frame(self.bg_frame, bg="#0F172A")
        btn_frame.pack(side=tk.RIGHT, padx=(0, 6))

        # Auto-Scan Toggle Button
        self.btn_auto = tk.Button(
            btn_frame,
            text="⚡ Auto",
            font=("Segoe UI", 7, "bold"),
            fg="#FFFFFF",
            bg="#D97706",  # Amber for ON
            activebackground="#B45309",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=2,
            cursor="hand2",
            command=self._handle_toggle_auto,
        )
        self.btn_auto.pack(side=tk.LEFT, padx=1)

        # Pin / Target Window Button
        self.btn_pin = tk.Button(
            btn_frame,
            text="🎯",
            font=("Segoe UI", 8),
            fg="#38BDF8",
            bg="#1E293B",
            activebackground="#0284C7",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=2,
            cursor="hand2",
            command=self._handle_pick_window,
        )
        self.btn_pin.pack(side=tk.LEFT, padx=1)

        # Scan Button (Primary Action)
        self.btn_scan = tk.Button(
            btn_frame,
            text="🔍 Quét",
            font=("Segoe UI", 8, "bold"),
            fg="#FFFFFF",
            bg="#0284C7",  # Sky 600
            activebackground="#0369A1",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            padx=7,
            pady=2,
            cursor="hand2",
            command=self._handle_scan_click,
        )
        self.btn_scan.pack(side=tk.LEFT, padx=2)

        # Session Manager Button (Open Window)
        self.btn_session = tk.Button(
            btn_frame,
            text="📋",
            font=("Segoe UI", 8),
            fg="#E2E8F0",
            bg="#334155",  # Slate 700
            activebackground="#475569",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=2,
            cursor="hand2",
            command=self._handle_open_session,
        )
        self.btn_session.pack(side=tk.LEFT, padx=1)

        # Close / Exit Button
        self.btn_close = tk.Button(
            btn_frame,
            text="✕",
            font=("Segoe UI", 8),
            fg="#94A3B8",
            bg="#1E293B",
            activebackground="#DC2626",  # Red on hover/active
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=2,
            cursor="hand2",
            command=self._handle_exit,
        )
        self.btn_close.pack(side=tk.LEFT, padx=(1, 0))

        # 4. Context Menu (Right Click)
        self._init_context_menu()

    def _init_context_menu(self) -> None:
        """Create right-click context menu for quick auto-scan and calibration settings."""
        self.menu = tk.Menu(self, tearoff=0, bg="#1E293B", fg="#F8FAFC", activebackground="#0284C7", activeforeground="#FFFFFF")
        self.menu.add_command(label="🎯 Ghim cửa sổ Hermes (Click để chọn)", command=self._handle_pick_window)
        self.menu.add_command(label="📍 Chấm vị trí nút Confirm trên Hermes", command=self._handle_calibrate_button)
        self.menu.add_separator()
        self.auto_menu_var = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(label="⚡ Tự động quét khi bấm Confirm", variable=self.auto_menu_var, command=self._handle_toggle_auto)

        delay_menu = tk.Menu(self.menu, tearoff=0, bg="#1E293B", fg="#F8FAFC", activebackground="#0284C7", activeforeground="#FFFFFF")
        for d in [0.5, 1.0, 1.5, 2.0]:
            delay_menu.add_command(label=f"{d}s", command=lambda delay=d: self._handle_set_delay(delay))
        self.menu.add_cascade(label="⏱ Độ trễ chờ Hermes (Delay)", menu=delay_menu)

        self.menu.add_separator()
        self.menu.add_command(label="📋 Mở Quản lý phiên làm việc", command=self._handle_open_session)
        self.menu.add_command(label="✕ Thoát ứng dụng", command=self._handle_exit)

        # Bind right click on all overlay components
        for w in (self, self.bg_frame, self.grip_label, self.status_label):
            w.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event: tk.Event) -> None:
        """Display right-click context menu at cursor position."""
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # -------------------------------------------------------------------------
    # Drag and Drop Handlers
    # -------------------------------------------------------------------------
    def _on_drag_start(self, event: tk.Event) -> None:
        """Record initial mouse coordinates when dragging begins."""
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag_motion(self, event: tk.Event) -> None:
        """Update window position dynamically as mouse moves."""
        delta_x = event.x - self._drag_start_x
        delta_y = event.y - self._drag_start_y
        new_x = self.winfo_x() + delta_x
        new_y = self.winfo_y() + delta_y

        # Clamp within visible screen boundaries
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        new_x = max(0, min(new_x, screen_w - self.widget_width))
        new_y = max(0, min(new_y, screen_h - self.widget_height))

        self.geometry(f"+{new_x}+{new_y}")

    # -------------------------------------------------------------------------
    # State and Animation Transitions
    # -------------------------------------------------------------------------
    def set_state_ready(self) -> None:
        """Reset widget to idle READY state."""
        self._cancel_timers()
        self._is_scanning = False
        self.status_label.config(text="● Ready (F9)", fg="#10B981")  # Emerald
        self.btn_scan.config(state=tk.NORMAL, bg="#0284C7")
        self.bg_frame.config(highlightbackground="#334155")

    def set_state_scanning(self) -> None:
        """Transition widget to animated SCANNING state (<1s feedback)."""
        self._cancel_timers()
        self._is_scanning = True
        self._pulse_count = 0
        self.btn_scan.config(state=tk.DISABLED, bg="#D97706")
        self._animate_pulse()

    def _animate_pulse(self) -> None:
        """Pulse animation loop giving active user feedback while OCR operates."""
        if not self._is_scanning:
            return

        pulse_colors = ["#F59E0B", "#FBBF24", "#D97706", "#B45309"]
        current_color = pulse_colors[self._pulse_count % len(pulse_colors)]
        dots = "." * ((self._pulse_count % 3) + 1)

        self.status_label.config(text=f"Đang quét{dots}", fg=current_color)
        self.bg_frame.config(highlightbackground=current_color)

        self._pulse_count += 1
        self._pulse_timer = self.after(160, self._animate_pulse)

    def set_state_success(self, awb_number: str = "") -> None:
        """Display brief green success toast and schedule auto-reset."""
        self._cancel_timers()
        self._is_scanning = False
        display_text = f"✔ {awb_number}" if awb_number else "✔ Đã quét!"
        self.status_label.config(text=display_text[:14], fg="#34D399")  # Mint green
        self.btn_scan.config(state=tk.NORMAL, bg="#059669")
        self.bg_frame.config(highlightbackground="#059669")

        # Auto restore to READY after 2.5 seconds
        self._restore_timer = self.after(2500, self.set_state_ready)

    def set_state_error(self, message: str = "Không thấy AWB") -> None:
        """Display brief red error toast and schedule auto-reset."""
        self._cancel_timers()
        self._is_scanning = False
        self.status_label.config(text=f"✖ {message[:12]}", fg="#F87171")  # Light red
        self.btn_scan.config(state=tk.NORMAL, bg="#DC2626")
        self.bg_frame.config(highlightbackground="#DC2626")

        # Auto restore to READY after 2.5 seconds
        self._restore_timer = self.after(2500, self.set_state_ready)

    def set_state_countdown(self, seconds: float) -> None:
        """Visual countdown feedback when a Confirm action is detected in Hermes."""
        self._cancel_timers()
        self._is_scanning = False
        remaining = [seconds]

        def _step() -> None:
            if remaining[0] <= 0.1:
                self.set_state_scanning()
            else:
                self.status_label.config(text=f"⏳ Chờ {remaining[0]:.1f}s", fg="#F59E0B")
                self.bg_frame.config(highlightbackground="#F59E0B")
                remaining[0] -= 0.2
                self._countdown_timer = self.after(200, _step)

        _step()

    def set_pinned_title(self, title: str) -> None:
        """Update overlay UI reflecting currently pinned Hermes target window."""
        self._pinned_title = title
        if title:
            short = title[:11] + ".." if len(title) > 11 else title
            self.btn_pin.config(bg="#059669", fg="#FFFFFF")
            self.status_label.config(text=f"🎯 {short}", fg="#38BDF8")
        else:
            self.btn_pin.config(bg="#1E293B", fg="#38BDF8")
            self.set_state_ready()

    def set_auto_enabled(self, enabled: bool) -> None:
        """Synchronize Auto-scan toggle state and update button appearance."""
        self._auto_enabled = enabled
        if hasattr(self, "auto_menu_var"):
            self.auto_menu_var.set(enabled)
        if enabled:
            self.btn_auto.config(text="⚡ Auto", bg="#D97706")
        else:
            self.btn_auto.config(text="⚡ Off", bg="#334155")

    def _cancel_timers(self) -> None:
        """Cancel any running pulse, restore, or countdown timers."""
        if self._pulse_timer:
            self.after_cancel(self._pulse_timer)
            self._pulse_timer = None
        if self._restore_timer:
            self.after_cancel(self._restore_timer)
            self._restore_timer = None
        if self._countdown_timer:
            self.after_cancel(self._countdown_timer)
            self._countdown_timer = None

    # -------------------------------------------------------------------------
    # Button Callbacks
    # -------------------------------------------------------------------------
    def _handle_scan_click(self) -> None:
        """Handle click on 'Quét' button."""
        if self.on_scan and not self._is_scanning:
            self.set_state_scanning()
            self.on_scan()

    def _handle_toggle_auto(self) -> None:
        """Toggle automatic scan on Confirm."""
        new_state = not self._auto_enabled
        self.set_auto_enabled(new_state)
        if self.on_toggle_auto:
            self.on_toggle_auto(new_state)

    def _handle_pick_window(self) -> None:
        """Enter window picker mode."""
        self.status_label.config(text="🎯 Click vào Hermes", fg="#F59E0B")
        if self.on_pick_window:
            self.on_pick_window()

    def _handle_calibrate_button(self) -> None:
        """Enter Confirm button calibration mode."""
        self.status_label.config(text="📍 Click nút Confirm", fg="#F59E0B")
        if self.on_calibrate_button:
            self.on_calibrate_button()

    def _handle_set_delay(self, delay: float) -> None:
        """Set capture delay after confirm action."""
        self._current_delay = delay
        self.status_label.config(text=f"⏱ Delay: {delay}s", fg="#38BDF8")
        if self.on_set_delay:
            self.on_set_delay(delay)
        self.after(1500, self.set_state_ready)

    def _handle_open_session(self) -> None:
        """Handle click on Session Manager button."""
        if self.on_open_session:
            self.on_open_session()

    def _handle_exit(self) -> None:
        """Handle click on Exit button."""
        if self.on_exit:
            self.on_exit()
        else:
            self.destroy()

    def trigger_scan(self) -> None:
        """Programmatic trigger alias (e.g. called from global hotkey handler)."""
        self.after(0, self._handle_scan_click)
