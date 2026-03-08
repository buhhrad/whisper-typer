"""Whisper Typer — voice typing desktop app.

Small always-on-top floating widget with push-to-talk, always-on VAD,
and manual mic toggle modes. Transcribes speech via faster-whisper and
routes text to the selected output target.

Usage:
    python whisper_typer.py
    python whisper_typer.py --model small --device cuda
    python whisper_typer.py --list-devices
"""

from __future__ import annotations

import argparse
import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk

import sounddevice as sd

# pythonw sets sys.stdout/stderr to None — torch.hub crashes writing to None.
# Redirect to devnull so libraries don't explode.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

try:
    from PIL import Image, ImageDraw, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import pystray
    _HAS_TRAY = _HAS_PIL
except ImportError:
    _HAS_TRAY = False

import settings as user_settings
from config import (
    COLOR_AMBER,
    COLOR_AMBER_DIM,
    COLOR_BG,
    COLOR_BLUE,
    COLOR_BORDER,
    COLOR_DROPDOWN_BG,
    COLOR_DROPDOWN_FG,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_GRIP,
    COLOR_TERMINAL_BG,
    COLOR_TRANSPARENT,
    POLL_INTERVAL_MS,
    ROUTE_OPTIONS,
    ROUTE_DEFAULT,
    STATE_IDLE,
    STATE_RECORDING,
    STATE_TRANSCRIBING,
    STATE_TYPING,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from widgets import PillButton, DropdownButton, MicIcon, VadToggle

# ── Win32 constants ───────────────────────────────────────────────────
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


def _get_input_devices() -> list[tuple[int, str]]:
    """Return list of (device_index, display_name) for input devices.

    Windows exposes each device 3+ times (MME, DirectSound, WASAPI) with
    slightly different names. MME truncates to 32 chars, WASAPI shows full
    names, and the parenthetical suffix varies. We deduplicate by extracting
    the base name (before the first parenthesis) and keeping the best entry.
    """
    _SKIP = {"Microsoft Sound Mapper - Input", "Primary Sound Capture Driver"}
    raw: list[tuple[int, str]] = []
    try:
        devices = sd.query_devices()
        for i in range(len(devices)):
            d = sd.query_devices(i)
            if d["max_input_channels"] > 0 and d["name"] not in _SKIP:
                raw.append((i, d["name"]))
    except Exception:
        pass

    # Group by base name (part before first '(' or the full string).
    # For each group, keep the entry with the most descriptive name.
    groups: dict[str, tuple[int, str]] = {}  # base -> (idx, full_name)
    for idx, name in raw:
        paren = name.find("(")
        base = name[:paren].rstrip() if paren > 0 else name
        if base in groups:
            # Prefer the longer / more descriptive name
            _, existing = groups[base]
            if len(name) > len(existing):
                groups[base] = (idx, name)
        else:
            groups[base] = (idx, name)

    return list(groups.values())


class WhisperTyper:
    """Main application: tkinter GUI + state machine + orchestration."""

    def __init__(self, model: str | None = None, device: str | None = None):
        self._event_queue: queue.Queue = queue.Queue()
        self._state = STATE_IDLE
        self._recording_start: float = 0
        self._vad_cooldown_until: float = 0  # suppress VAD retrigger after transcription
        self._model_override = model
        self._device_override = device
        self._elapsed_timer_id: str | None = None
        self._model_ready = False
        self._transparent_mode = True  # default to transparent

        # Cairn backend connection state
        self._cairn_connected = False

        # Snap-to-window state
        self._snap_hwnd = None
        self._snap_id: str | None = None
        self._snap_last_x: int = -1
        self._snap_last_y: int = -1
        self._snap_bar_w: int = 0
        self._snap_bar_h: int = 0
        self._snap_tk_hwnd: int = 0
        self._user32 = ctypes.windll.user32

        # Lazy imports — only load heavy modules when needed
        self._recorder = None
        self._hotkey_listener = None

        # Load saved settings
        self._settings = user_settings.load()

        # Device list
        self._input_devices = _get_input_devices()

        self._build_gui()

    # ── GUI Construction ──────────────────────────────────────────

    def _build_gui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Whisper Typer")
        self.root.configure(bg=COLOR_TRANSPARENT)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", COLOR_TRANSPARENT)
        self.root.overrideredirect(True)  # no title bar

        # ── Main bar — one unified draggable block ───────────────
        _BAR_BG = COLOR_TRANSPARENT if self._transparent_mode else COLOR_TERMINAL_BG
        _BTN_BG = _BAR_BG
        row = tk.Frame(self.root, bg=_BAR_BG, cursor="fleur")
        row.pack(fill=tk.BOTH, expand=True)
        self._bar_row = row

        # ── Grip dots (left edge) — visible in transparent mode for grabbing ──
        grip_l = tk.Canvas(
            row, width=8, height=30, bg=_BAR_BG,
            highlightthickness=0, cursor="fleur",
        )
        grip_l.pack(side=tk.LEFT, fill=tk.Y)

        # Mic icon (left) — starts in loading state
        self._mic_btn = MicIcon(row, command=self._on_mic_click, bg=_BTN_BG)
        self._mic_btn.set_disabled(True)
        self._mic_btn.set_state("loading", "#2a2a3a")
        self._mic_btn.pack(side=tk.LEFT, padx=(2, 3))

        # Status label (hidden — kept for compatibility with status update calls)
        self._status = tk.Label(
            row, text="Loading model\u2026", font=("Segoe UI", 7),
            fg=COLOR_TEXT_DIM, bg=_BAR_BG, anchor="w",
        )

        # ── Grip dots (right edge) ──
        grip_r = tk.Canvas(
            row, width=8, height=30, bg=_BAR_BG,
            highlightthickness=0, cursor="fleur",
        )
        grip_r.pack(side=tk.RIGHT, fill=tk.Y)

        # Close × (canvas with outline)
        _ICON_SIZE = 26
        self._close_btn = tk.Canvas(
            row, width=_ICON_SIZE, height=_ICON_SIZE,
            bg=_BTN_BG, highlightthickness=0,
        )
        self._close_btn.pack(side=tk.RIGHT, padx=2)
        self._close_color = COLOR_TEXT_DIM
        self._draw_close_icon(COLOR_TEXT_DIM)
        self._close_btn.bind("<Enter>", lambda e: (self._draw_close_icon(COLOR_RED), self._close_btn.configure(cursor="arrow")))
        self._close_btn.bind("<Leave>", lambda e: (self._draw_close_icon(COLOR_TEXT_DIM), self._close_btn.configure(cursor="")))
        self._close_btn.bind("<ButtonPress-1>", lambda e: self._on_close())

        # Settings gear (canvas with outline)
        self._settings_popup = None
        self._gear_btn = tk.Canvas(
            row, width=_ICON_SIZE, height=_ICON_SIZE,
            bg=_BTN_BG, highlightthickness=0,
        )
        self._gear_btn.pack(side=tk.RIGHT, padx=2)
        self._draw_gear_icon(COLOR_TEXT_DIM)
        self._gear_btn.bind("<Enter>", lambda e: (self._draw_gear_icon(COLOR_AMBER), self._gear_btn.configure(cursor="arrow")))
        self._gear_btn.bind("<Leave>", lambda e: (
            self._draw_gear_icon(COLOR_TEXT_DIM) if not (self._settings_popup and self._settings_popup.winfo_exists()) else None,
            self._gear_btn.configure(cursor=""),
        ))
        self._gear_btn.bind("<ButtonPress-1>", lambda e: self._toggle_settings())

        # VAD toggle — starts in loading state
        self._vad_btn = VadToggle(
            row, command=self._on_vad_toggle, bg=_BTN_BG,
            off_color=COLOR_TEXT_DIM, on_color=COLOR_GREEN,
        )
        self._vad_btn.set_loading(True)
        self._vad_btn.pack(side=tk.RIGHT, padx=(0, 2))

        # ── Grip dots — draw and auto-center ──
        self._grips = [grip_l, grip_r]

        def _draw_grip_dots(event=None):
            for g in self._grips:
                g.delete("dots")
                cx = g.winfo_width() // 2
                cy = g.winfo_height() // 2
                for dy in (-4, 0, 4):
                    g.create_oval(
                        cx - 1, cy + dy - 1, cx + 1, cy + dy + 1,
                        fill=COLOR_GRIP, outline="", tags="dots",
                    )

        self._draw_grip_dots = _draw_grip_dots
        for g in self._grips:
            g.bind("<Configure>", _draw_grip_dots)
            g.bind("<Button-1>", self._on_drag_start)
            g.bind("<B1-Motion>", self._on_drag_motion)

        # Track widgets for transparency toggle
        self._row_bg_widgets = [row]
        self._btn_bg_widgets = [
            self._mic_btn, self._close_btn, self._gear_btn, self._vad_btn,
        ] + self._grips

        # ── Dropdown variables (shown in settings popup) ─────────
        device_names = [name for _, name in self._input_devices]
        self._mic_var = tk.StringVar()
        if device_names:
            saved_mic = self._settings.get("mic_device")
            if saved_mic and saved_mic in device_names:
                self._mic_var.set(saved_mic)
            else:
                try:
                    default_idx = sd.default.device[0]
                    default_name = next(
                        (name for idx, name in self._input_devices if idx == default_idx),
                        device_names[0],
                    )
                    self._mic_var.set(default_name)
                except Exception:
                    self._mic_var.set(device_names[0])
        else:
            self._mic_var.set("No mic found")

        saved_route = self._settings.get("output_route")
        default_route = saved_route if saved_route in ROUTE_OPTIONS else ROUTE_DEFAULT
        self._route_var = tk.StringVar(value=default_route)

        # ── Draggable — grab from anywhere on the bar ──────────
        self._drag_data = {"x": 0, "y": 0}
        row.bind("<Button-1>", self._on_drag_start)
        row.bind("<B1-Motion>", self._on_drag_motion)

        self.root.bind_all("<Escape>", self._on_escape)

        # ── Size and position ─────────────────────────────────────
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()

        saved_x = self._settings.get("window_x")
        saved_y = self._settings.get("window_y")
        if saved_x is not None and saved_y is not None:
            self.root.geometry(f"{w}x{h}+{saved_x}+{saved_y}")
        else:
            self.root.geometry(f"{w}x{h}")

    # ── System Tray Icon ─────────────────────────────────────────

    def _create_tray_icon(self) -> None:
        """Create a system tray icon for show/hide, Cairn launch, and quit."""
        if not _HAS_TRAY:
            return
        self._tray_icon = pystray.Icon(
            "whisper_typer",
            self._make_tray_image(connected=self._cairn_connected),
            f"Whisper Typer — Cairn: {'Connected' if self._cairn_connected else 'Offline'}",
            menu=pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.MenuItem("Open Cairn Desktop", self._tray_open_cairn),
                pystray.MenuItem("Quit", self._tray_quit),
            ),
        )
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    @staticmethod
    def _make_tray_image(connected: bool = True):
        """Create a mic tray icon — amber when Cairn connected, gray when offline."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Circle color: amber if connected, gray if offline
        circle_color = "#d4a030" if connected else "#666666"
        draw.ellipse([4, 4, 60, 60], fill=circle_color)
        # Simple mic shape (dark rectangle + rounded top)
        draw.rounded_rectangle([24, 14, 40, 38], radius=6, fill="#12121f")
        draw.arc([20, 28, 44, 50], start=180, end=0, fill="#12121f", width=3)
        draw.line([32, 50, 32, 56], fill="#12121f", width=3)
        draw.line([24, 56, 40, 56], fill="#12121f", width=3)
        return img

    def _tray_show(self, icon=None, item=None) -> None:
        """Restore the window from tray."""
        self.root.after(0, self._show_window)

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    def _tray_quit(self, icon=None, item=None) -> None:
        """Quit from tray menu."""
        if hasattr(self, "_tray_icon"):
            self._tray_icon.stop()
        self.root.after(0, self._on_close)

    def _tray_open_cairn(self, icon=None, item=None) -> None:
        """Launch Cairn Desktop via cairn-launch.bat."""
        import subprocess
        from config import CAIRN_LAUNCH_BAT
        try:
            subprocess.Popen(
                [CAIRN_LAUNCH_BAT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            )
        except Exception:
            pass

    def _cairn_health_loop(self) -> None:
        """Background thread: poll Cairn backend health every 30s."""
        import urllib.request
        from config import CAIRN_API_URL, CAIRN_HEALTH_INTERVAL
        while True:
            try:
                req = urllib.request.Request(f"{CAIRN_API_URL}/health", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self._cairn_connected = resp.status == 200
            except Exception:
                self._cairn_connected = False
            # Update tray icon
            try:
                if hasattr(self, "_tray_icon") and self._tray_icon:
                    self._tray_icon.icon = self._make_tray_image(connected=self._cairn_connected)
                    self._tray_icon.title = f"Whisper Typer — Cairn: {'Connected' if self._cairn_connected else 'Offline'}"
            except Exception:
                pass
            time.sleep(CAIRN_HEALTH_INTERVAL)

    def _apply_window_styles(self) -> None:
        """Apply WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW and register hwnd for focus tracking."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass
        self._apply_rounded_corners()

    def _apply_rounded_corners(self) -> None:
        """Set window shape to a rounded rectangle via Win32 region."""
        try:
            hwnd = int(self.root.wm_frame(), 16)
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            r = 10
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, r * 2, r * 2)
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

    # ── Drag handling ─────────────────────────────────────────────

    def _on_drag_start(self, event: tk.Event) -> None:
        if self._snap_hwnd:
            return  # locked to terminal — no dragging
        self._close_settings()
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event: tk.Event) -> None:
        if self._snap_hwnd:
            return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        # Use virtual screen bounds (spans all monitors)
        try:
            SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
            SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
            vx = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            vy = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            vw = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            vh = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            x = max(vx, min(x, vx + vw - self.root.winfo_width()))
            y = max(vy, min(y, vy + vh - self.root.winfo_height()))
        except Exception:
            pass  # If GetSystemMetrics fails, allow unclamped drag
        self.root.geometry(f"+{x}+{y}")

    # ── Device change ─────────────────────────────────────────────

    def _on_mic_changed(self, event=None) -> None:
        """Handle mic dropdown change — switch audio device."""
        selected_name = self._mic_var.get()
        device_idx = None
        for idx, name in self._input_devices:
            if name == selected_name:
                device_idx = idx
                break
        if self._recorder:
            self._recorder.set_device(device_idx)
            self._status.configure(text=f"Mic: {selected_name[:30]}", fg=COLOR_TEXT)
            self.root.after(1500, lambda: (
                self._status.configure(text="Ready", fg=COLOR_TEXT)
                if self._state == STATE_IDLE else None
            ))

    # ── Escape handler ─────────────────────────────────────────

    def _on_escape(self, event=None) -> None:
        """Close settings popup first, or close app."""
        if self._settings_popup and self._settings_popup.winfo_exists():
            self._close_settings()
        else:
            self._on_close()

    # ── Settings popup ─────────────────────────────────────────

    def _draw_close_icon(self, color):
        """Draw × icon with anti-aliased stroke, composited onto canvas bg."""
        from widgets import _aa_icon
        c = self._close_btn
        self._close_color = color
        if _HAS_PIL:
            def _draw(d, S):
                cx, cy = 26 * S // 2, 26 * S // 2
                w = max(1, round(2 * S))
                d.line([(cx - 4*S, cy - 4*S), (cx + 4*S, cy + 4*S)], fill=color, width=w)
                d.line([(cx + 4*S, cy - 4*S), (cx - 4*S, cy + 4*S)], fill=color, width=w)
            _aa_icon(c, 26, 26, _draw)
        else:
            c.delete("all")
            cx, cy = 13, 13
            c.create_line(cx - 4, cy - 4, cx + 4, cy + 4, fill=color, width=2)
            c.create_line(cx + 4, cy - 4, cx - 4, cy + 4, fill=color, width=2)

    def _draw_gear_icon(self, color):
        """Draw gear icon with stroke."""
        c = self._gear_btn
        c.delete("all")
        cx, cy = 13, 13
        c.create_text(cx, cy, text="\u2699", font=("Segoe UI", 11), fill=color)

    def _toggle_settings(self) -> None:
        if self._settings_popup and self._settings_popup.winfo_exists():
            self._close_settings()
        else:
            self._open_settings()

    @staticmethod
    def _format_hotkey(combo) -> str:
        """Convert ['ctrl', 'shift', 'space'] → 'Ctrl+Shift+Space'."""
        if not combo:
            return "None"
        _DISPLAY = {
            "ctrl": "Ctrl", "shift": "Shift", "alt": "Alt",
            "space": "Space", "tab": "Tab", "enter": "Enter", "esc": "Esc",
        }
        return "+".join(_DISPLAY.get(k, k.upper()) for k in combo)

    def _start_keybind_capture(self, label: tk.Label, setting_key: str) -> None:
        """Enter keybind capture mode — next key combo gets saved."""
        label.configure(text="...", fg=COLOR_AMBER)
        popup = self._settings_popup
        if not popup or not popup.winfo_exists():
            return
        popup.focus_force()

        def _on_key(event):
            keysym = event.keysym
            # Skip bare modifier presses — wait for the main key
            if keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R",
                          "Alt_L", "Alt_R", "Meta_L", "Meta_R"):
                return
            # Escape cancels
            if keysym == "Escape":
                cur = self._settings.get(setting_key)
                label.configure(text=self._format_hotkey(cur), fg=COLOR_TEXT)
                popup.unbind("<KeyPress>")
                return
            # Build combo from modifier state + key
            combo = []
            if event.state & 0x4:
                combo.append("ctrl")
            if event.state & 0x1:
                combo.append("shift")
            if event.state & 0x20000:
                combo.append("alt")
            combo.append(keysym.lower())
            # Save
            self._settings[setting_key] = combo
            import settings as user_settings
            user_settings.save(self._settings)
            label.configure(text=self._format_hotkey(combo), fg=COLOR_TEXT)
            popup.unbind("<KeyPress>")
            # Update listener
            if self._hotkey_listener:
                self._hotkey_listener.set_combos(
                    ptt_combo=self._settings.get("ptt_hotkey"),
                    vad_combo=self._settings.get("vad_hotkey"),
                )

        popup.bind("<KeyPress>", _on_key)

    def _clear_keybind(self, label: tk.Label, setting_key: str) -> None:
        """Remove a keybind."""
        self._settings[setting_key] = None
        import settings as user_settings
        user_settings.save(self._settings)
        label.configure(text="None", fg=COLOR_TEXT_DIM)
        if self._hotkey_listener:
            self._hotkey_listener.set_combos(
                ptt_combo=self._settings.get("ptt_hotkey"),
                vad_combo=self._settings.get("vad_hotkey"),
            )

    def _open_settings(self) -> None:
        """Open settings popup — translucent, rounded, wider."""
        _PANEL_BG = COLOR_TERMINAL_BG  # match the bar background
        _PANEL_ALPHA = 0.85

        self._settings_popup = tk.Toplevel(self.root)
        self._settings_popup.overrideredirect(True)
        self._settings_popup.attributes("-topmost", True)
        self._settings_popup.attributes("-alpha", _PANEL_ALPHA)
        self._settings_popup.configure(bg="#1a1a2a")

        panel = tk.Frame(self._settings_popup, bg=_PANEL_BG)
        panel.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        panel_inner = tk.Frame(panel, bg=_PANEL_BG)
        panel_inner.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # MIC selector
        p = panel_inner
        mic_row = tk.Frame(p, bg=_PANEL_BG)
        mic_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            mic_row, text="MIC", font=("Segoe UI", 7, "bold"),
            fg=COLOR_TEXT_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        device_names = [name for _, name in self._input_devices]
        DropdownButton(
            mic_row, textvariable=self._mic_var, values=device_names,
            bg=COLOR_DROPDOWN_BG, fg=COLOR_DROPDOWN_FG,
            hover_bg="#222244", select_bg="#2a2a50", select_fg=COLOR_AMBER,
            on_change=lambda: self._on_mic_changed(),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # OUT selector
        out_row = tk.Frame(p, bg=_PANEL_BG)
        out_row.pack(fill=tk.X)
        tk.Label(
            out_row, text="OUT", font=("Segoe UI", 7, "bold"),
            fg=COLOR_TEXT_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        DropdownButton(
            out_row, textvariable=self._route_var, values=ROUTE_OPTIONS,
            bg=COLOR_DROPDOWN_BG, fg=COLOR_DROPDOWN_FG,
            hover_bg="#222244", select_bg="#2a2a50", select_fg=COLOR_AMBER,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Keybinds section ──
        tk.Frame(p, bg=COLOR_BORDER, height=1).pack(fill=tk.X, pady=(6, 4))
        kb_header = tk.Label(
            p, text="KEYBINDS", font=("Segoe UI", 6, "bold"),
            fg=COLOR_TEXT_DIM, bg=_PANEL_BG, anchor="w",
        )
        kb_header.pack(fill=tk.X, pady=(0, 2))

        # PTT keybind
        ptt_row = tk.Frame(p, bg=_PANEL_BG, cursor="arrow")
        ptt_row.pack(fill=tk.X, pady=1)
        tk.Label(
            ptt_row, text="PTT", font=("Segoe UI", 7, "bold"),
            fg=COLOR_TEXT_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        ptt_combo = self._settings.get("ptt_hotkey")
        ptt_label = tk.Label(
            ptt_row, text=self._format_hotkey(ptt_combo),
            font=("Consolas", 7), fg=COLOR_TEXT, bg="#12122a",
            padx=6, pady=1, anchor="w",
        )
        ptt_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ptt_clear = tk.Label(
            ptt_row, text="\u00d7", font=("Segoe UI", 8),
            fg=COLOR_TEXT_DIM, bg=_PANEL_BG, padx=2, cursor="arrow",
        )
        ptt_clear.pack(side=tk.RIGHT)
        ptt_label.bind("<ButtonRelease-1>",
                       lambda e: self._start_keybind_capture(ptt_label, "ptt_hotkey"))
        ptt_clear.bind("<ButtonRelease-1>",
                       lambda e: self._clear_keybind(ptt_label, "ptt_hotkey"))
        ptt_label.bind("<Enter>", lambda e: ptt_label.configure(bg="#1a1a3a"))
        ptt_label.bind("<Leave>", lambda e: ptt_label.configure(bg="#12122a"))
        ptt_clear.bind("<Enter>", lambda e: ptt_clear.configure(fg=COLOR_RED))
        ptt_clear.bind("<Leave>", lambda e: ptt_clear.configure(fg=COLOR_TEXT_DIM))

        # VAD keybind
        vad_row = tk.Frame(p, bg=_PANEL_BG, cursor="arrow")
        vad_row.pack(fill=tk.X, pady=1)
        tk.Label(
            vad_row, text="VAD", font=("Segoe UI", 7, "bold"),
            fg=COLOR_TEXT_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        vad_combo = self._settings.get("vad_hotkey")
        vad_label = tk.Label(
            vad_row, text=self._format_hotkey(vad_combo),
            font=("Consolas", 7), fg=COLOR_TEXT if vad_combo else COLOR_TEXT_DIM,
            bg="#12122a", padx=6, pady=1, anchor="w",
        )
        vad_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        vad_clear = tk.Label(
            vad_row, text="\u00d7", font=("Segoe UI", 8),
            fg=COLOR_TEXT_DIM, bg=_PANEL_BG, padx=2, cursor="arrow",
        )
        vad_clear.pack(side=tk.RIGHT)
        vad_label.bind("<ButtonRelease-1>",
                       lambda e: self._start_keybind_capture(vad_label, "vad_hotkey"))
        vad_clear.bind("<ButtonRelease-1>",
                       lambda e: self._clear_keybind(vad_label, "vad_hotkey"))
        vad_label.bind("<Enter>", lambda e: vad_label.configure(bg="#1a1a3a"))
        vad_label.bind("<Leave>", lambda e: vad_label.configure(bg="#12122a"))
        vad_clear.bind("<Enter>", lambda e: vad_clear.configure(fg=COLOR_RED))
        vad_clear.bind("<Leave>", lambda e: vad_clear.configure(fg=COLOR_TEXT_DIM))

        # ── Toggles section ──
        tk.Frame(p, bg=COLOR_BORDER, height=1).pack(fill=tk.X, pady=(6, 4))

        # Snap to Terminal toggle (also controls transparency)
        snap_on = bool(self._snap_hwnd)
        snap_check = "\u2713" if snap_on else "\u2002"
        snap_fg = COLOR_AMBER if snap_on else COLOR_TEXT_DIM
        snap_row = tk.Frame(p, bg=_PANEL_BG, cursor="arrow")
        snap_row.pack(fill=tk.X, pady=2)
        snap_box = tk.Label(
            snap_row, text=f"[{snap_check}]", font=("Consolas", 8),
            fg=snap_fg, bg=_PANEL_BG, padx=(4),
        )
        snap_box.pack(side=tk.LEFT)
        snap_txt = tk.Label(
            snap_row, text="Snap to Terminal", font=("Segoe UI", 8),
            fg=snap_fg, bg=_PANEL_BG, anchor="w",
        )
        snap_txt.pack(side=tk.LEFT, padx=(2, 0))
        for w in (snap_row, snap_box, snap_txt):
            w.bind("<Enter>", lambda e, b=snap_box, t=snap_txt: (
                b.configure(fg=COLOR_AMBER), t.configure(fg=COLOR_AMBER)))
            w.bind("<Leave>", lambda e, b=snap_box, t=snap_txt, on=snap_on: (
                b.configure(fg=COLOR_AMBER if on else COLOR_TEXT_DIM),
                t.configure(fg=COLOR_AMBER if on else COLOR_TEXT_DIM)))
            w.bind("<ButtonRelease-1>", lambda e: self._toggle_snap())

        # Position above or below — dynamically choose based on screen space
        self._settings_popup.update_idletasks()
        popup_w = max(self.root.winfo_width(), 220)
        x = self.root.winfo_x()
        h = self._settings_popup.winfo_reqheight()
        bar_bottom = self.root.winfo_y() + self.root.winfo_height()
        screen_h = self.root.winfo_screenheight()
        if bar_bottom + h > screen_h - 48:
            y = self.root.winfo_y() - h
        else:
            y = bar_bottom
        self._settings_popup.geometry(f"{popup_w}x{h}+{x}+{y}")

        # Round the popup corners
        def _round_popup():
            try:
                hwnd = int(self._settings_popup.wm_frame(), 16)
                pw = self._settings_popup.winfo_width()
                ph = self._settings_popup.winfo_height()
                rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, pw + 1, ph + 1, 16, 16)
                ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
            except Exception:
                pass
        self._settings_popup.after(10, _round_popup)

        # Escape to close
        self._settings_popup.bind("<Escape>", lambda e: self._close_settings())

        # Highlight gear
        self._draw_gear_icon(COLOR_AMBER)

    def _close_settings(self) -> None:
        if self._settings_popup and self._settings_popup.winfo_exists():
            self._settings_popup.destroy()
        self._settings_popup = None
        try:
            self._draw_gear_icon(COLOR_TEXT_DIM)
        except Exception:
            pass

    # ── Snap to terminal ─────────────────────────────────────────

    def _find_terminal_hwnd(self):
        """Find a visible Windows Terminal window to snap to."""
        from config import TERMINAL_WINDOW_CLASSES, TERMINAL_TITLE_EXCLUDE
        user32 = ctypes.windll.user32

        def _is_valid(hwnd):
            if not user32.IsWindowVisible(hwnd):
                return False
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buf, 256)
            if class_buf.value not in TERMINAL_WINDOW_CLASSES:
                return False
            title_buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buf, 512)
            title_lower = title_buf.value.lower()
            for excl in TERMINAL_TITLE_EXCLUDE:
                if excl.lower() in title_lower:
                    return False
            return True

        # Try foreground window first
        fg = user32.GetForegroundWindow()
        if fg and _is_valid(fg):
            return fg

        # Enumerate all visible terminals
        candidates = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
        )

        def enum_cb(hwnd, _):
            if _is_valid(hwnd):
                candidates.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return candidates[0] if candidates else None

    def _toggle_snap(self) -> None:
        if self._snap_hwnd:
            self._unsnap()
            self._close_settings()
        else:
            self._snap_to_terminal()

    def _set_transparency(self, transparent: bool) -> None:
        """Set transparent or solid bar background and re-render icons."""
        self._transparent_mode = transparent
        bg = COLOR_TRANSPARENT if transparent else COLOR_TERMINAL_BG
        for w in self._row_bg_widgets + self._btn_bg_widgets:
            w.configure(bg=bg)
        self._mic_btn._bg = bg
        self._vad_btn._bg = bg
        # Re-render icons with new background for proper compositing
        if hasattr(self._mic_btn, '_state'):
            self._mic_btn.set_state(self._mic_btn._state, self._mic_btn._color)
        self._draw_close_icon(self._close_color)
        self._draw_gear_icon(COLOR_TEXT_DIM)
        if hasattr(self._vad_btn, '_active'):
            if self._vad_btn._active:
                self._vad_btn._draw_bars(self._vad_btn._REST_HEIGHTS, self._vad_btn._on_color)
            else:
                self._vad_btn._draw_off()
        # Redraw grip dots (they need visible color in transparent mode)
        if hasattr(self, '_draw_grip_dots'):
            self._draw_grip_dots()

    def _toggle_transparency(self) -> None:
        """Toggle between transparent and solid bar background."""
        self._set_transparency(not self._transparent_mode)
        self._close_settings()

    def _snap_to_terminal(self) -> None:
        """Find and snap to a Windows Terminal window. Enables transparency."""
        hwnd = self._find_terminal_hwnd()
        if not hwnd:
            self._status.configure(text="No terminal found", fg=COLOR_TEXT_DIM)
            self.root.after(2000, lambda: (
                self._status.configure(text="Ready", fg=COLOR_TEXT)
                if self._state == STATE_IDLE else None
            ))
            return
        self._snap_hwnd = hwnd
        self._snap_bar_w = self.root.winfo_width()
        self._snap_bar_h = self.root.winfo_height()
        self._snap_tk_hwnd = int(self.root.wm_frame(), 16)
        # Enable transparency when snapping
        if not self._transparent_mode:
            self._set_transparency(True)
        # Defer — we're inside a click handler on the settings popup
        def _do_snap():
            self._close_settings()
            self._snap_poll()
        self.root.after(10, _do_snap)

    def _unsnap(self) -> None:
        """Detach from the snapped window. Disables transparency."""
        self._snap_hwnd = None
        self._snap_last_x = -1
        self._snap_last_y = -1
        if self._snap_id:
            self.root.after_cancel(self._snap_id)
            self._snap_id = None
        # Disable transparency when unsnapping
        if self._transparent_mode:
            self._set_transparency(False)

    # Reusable RECT (avoid recreating every call)
    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                     ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    # SetWindowPos flags for snap — no resize, no z-order change, no activate
    _SWP_NOSIZE = 0x0001
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_FLAGS = _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE

    def _snap_poll(self) -> None:
        """Track the snapped window position via polling (~120fps)."""
        try:
            if not self._snap_hwnd or not self._user32.IsWindow(self._snap_hwnd):
                self._snap_hwnd = None
                return

            if self._user32.IsIconic(self._snap_hwnd):
                self.root.withdraw()
                self._snap_id = self.root.after(200, self._snap_poll)
                return

            self.root.deiconify()

            rect = self._RECT()
            self._user32.GetWindowRect(self._snap_hwnd, ctypes.byref(rect))

            # Center horizontally on terminal, flush with bottom
            x = rect.left + (rect.right - rect.left - self._snap_bar_w) // 2
            y = rect.bottom - self._snap_bar_h - 8
            if x != self._snap_last_x or y != self._snap_last_y:
                self._snap_last_x = x
                self._snap_last_y = y
                # Direct Win32 move — bypasses tkinter string parsing
                self._user32.SetWindowPos(
                    self._snap_tk_hwnd, 0, x, y, 0, 0, self._SWP_FLAGS)
        except Exception:
            pass

        if self._snap_hwnd:
            self._snap_id = self.root.after(8, self._snap_poll)

    # ── Initialization (after mainloop starts) ────────────────────

    def _init_components(self) -> None:
        """Initialize audio, hotkeys, tray icon, and preload model in background."""
        self._apply_window_styles()
        self._create_tray_icon()

        # Get selected device index
        selected_name = self._mic_var.get()
        device_idx = None
        for idx, name in self._input_devices:
            if name == selected_name:
                device_idx = idx
                break

        # Import and set up recorder with selected device
        from audio import Recorder
        self._recorder = Recorder(self._event_queue, device_index=device_idx)
        self._recorder.open_stream()

        # Set up hotkeys (configurable combos from settings)
        from hotkeys import HotkeyListener
        ptt = self._settings.get("ptt_hotkey") or ["ctrl", "shift", "space"]
        vad = self._settings.get("vad_hotkey")
        self._hotkey_listener = HotkeyListener(
            self._event_queue, ptt_combo=ptt, vad_combo=vad,
        )
        self._hotkey_listener.start()

        # Apply config overrides BEFORE spawning the preload thread (avoids race)
        if self._model_override:
            import config
            config.WHISPER_MODEL = self._model_override
        if self._device_override:
            import config
            config.WHISPER_DEVICE = self._device_override
            if self._device_override == "cuda":
                config.WHISPER_COMPUTE = "float16"

        # Preload whisper model in background
        def _preload():
            try:
                from transcriber import preload
                preload()
                self._event_queue.put(("model_loaded",))
            except Exception as e:
                self._event_queue.put(("model_error", str(e)))

        threading.Thread(target=_preload, daemon=True).start()

        # Start Cairn health check background thread
        threading.Thread(target=self._cairn_health_loop, daemon=True).start()

        # Don't auto-restore VAD — user must explicitly enable it each session

        # Auto-snap to terminal if one is available
        hwnd = self._find_terminal_hwnd()
        if hwnd:
            self._snap_hwnd = hwnd
            self._snap_bar_w = self.root.winfo_width()
            self._snap_bar_h = self.root.winfo_height()
            self._snap_tk_hwnd = int(self.root.wm_frame(), 16)
            self._snap_poll()

    # ── State machine ─────────────────────────────────────────────

    def _set_state(self, state: str) -> None:
        self._state = state

        if state == STATE_IDLE:
            self._mic_btn.set_state("idle", COLOR_TEXT_DIM)
            if self._recorder and self._recorder.vad_active:
                self._status.configure(text="Listening (VAD)\u2026", fg=COLOR_TEXT)
            else:
                self._status.configure(text="Ready", fg=COLOR_TEXT)
            self._cancel_elapsed_timer()

        elif state == STATE_RECORDING:
            self._mic_btn.set_state("recording", COLOR_RED)
            self._recording_start = time.monotonic()
            self._update_elapsed()

        elif state == STATE_TRANSCRIBING:
            self._mic_btn.set_state("transcribing", COLOR_BLUE)
            self._status.configure(text="Transcribing\u2026", fg=COLOR_BLUE)
            self._cancel_elapsed_timer()
            self._transcribe_start = time.monotonic()

        elif state == STATE_TYPING:
            self._mic_btn.set_state("typing", COLOR_GREEN)
            self._cancel_elapsed_timer()

    def _update_elapsed(self) -> None:
        """Update status with elapsed recording time."""
        if self._state != STATE_RECORDING:
            return
        elapsed = time.monotonic() - self._recording_start
        self._status.configure(
            text=f"Recording... {elapsed:.1f}s",
            fg=COLOR_RED,
        )
        self._elapsed_timer_id = self.root.after(100, self._update_elapsed)

    def _cancel_elapsed_timer(self) -> None:
        if self._elapsed_timer_id:
            self.root.after_cancel(self._elapsed_timer_id)
            self._elapsed_timer_id = None

    # ── Button handlers ───────────────────────────────────────────

    def _on_mic_click(self) -> None:
        """Toggle recording on mic button click (Manual mode)."""
        if not self._model_ready:
            return
        if self._state == STATE_IDLE:
            if self._recorder:
                self._recorder.start_recording()
                self._set_state(STATE_RECORDING)
        elif self._state == STATE_RECORDING:
            if self._recorder:
                self._recorder.stop_recording()

    def _on_vad_toggle(self) -> None:
        """Toggle always-on VAD mode."""
        if not self._model_ready or not self._recorder:
            return

        if self._recorder.vad_active:
            self._recorder.disable_vad()
            self._vad_btn.set_active(False)
            if self._state == STATE_IDLE:
                self._status.configure(text="Ready", fg=COLOR_TEXT)
        else:
            self._status.configure(text="Loading VAD\u2026", fg=COLOR_TEXT_DIM)

            def _enable():
                try:
                    self._recorder.enable_vad()
                    self._event_queue.put(("vad_ready",))
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    # Write to log file (pythonw has no console)
                    try:
                        from pathlib import Path
                        log = Path(__file__).parent / "vad_error.log"
                        log.write_text(tb, encoding="utf-8")
                    except Exception:
                        pass
                    self._event_queue.put(("audio_error", f"VAD load failed: {e}"))

            threading.Thread(target=_enable, daemon=True).start()

    def _save_settings(self) -> None:
        """Persist current settings to disk."""
        self._settings["mic_device"] = self._mic_var.get()
        self._settings["output_route"] = self._route_var.get()
        self._settings["vad_enabled"] = bool(self._recorder and self._recorder.vad_active)
        try:
            self._settings["window_x"] = self.root.winfo_x()
            self._settings["window_y"] = self.root.winfo_y()
        except Exception:
            pass
        user_settings.save(self._settings)

    def _on_close(self) -> None:
        """Clean shutdown."""
        self._unsnap()
        self._save_settings()
        if hasattr(self, "_tray_icon") and self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        if self._recorder:
            self._recorder.disable_vad()
            self._recorder.close_stream()
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self.root.destroy()

    # ── Event queue processing ────────────────────────────────────

    def _poll_events(self) -> None:
        """Process events from the queue (called every POLL_INTERVAL_MS)."""
        try:
            while True:
                event = self._event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_events)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]

        if kind == "model_loaded":
            self._model_ready = True
            self._mic_btn.set_disabled(False)
            self._mic_btn.set_state("idle", COLOR_TEXT_DIM)
            self._vad_btn.set_loading(False)
            if self._state == STATE_IDLE:
                self._status.configure(text="Ready", fg=COLOR_TEXT)

        elif kind == "model_error":
            self._status.configure(text=f"Model error: {event[1]}", fg=COLOR_RED)

        elif kind == "hotkey_press":
            if self._model_ready and self._state == STATE_IDLE and self._recorder:
                self._recorder.start_recording()
                self._set_state(STATE_RECORDING)

        elif kind == "hotkey_release":
            if self._state == STATE_RECORDING and self._recorder:
                self._recorder.stop_recording()

        elif kind == "vad_toggle":
            self._on_vad_toggle()

        elif kind == "vad_speech_start":
            if self._state == STATE_IDLE and time.time() >= self._vad_cooldown_until:
                self._set_state(STATE_RECORDING)
                self._vad_btn.set_recording(True)
            elif self._state in (STATE_TRANSCRIBING, STATE_TYPING):
                # Show that we're listening again while still processing
                self._vad_btn.set_color(COLOR_GREEN)
                self._vad_btn.set_recording(True)

        elif kind == "vad_speech_end":
            if self._state == STATE_TRANSCRIBING:
                self._vad_btn.set_recording(False)
            elif self._state == STATE_TYPING:
                self._vad_btn.set_recording(False)
                self._vad_btn.set_color(COLOR_GREEN)

        elif kind == "vad_ready":
            self._vad_btn.set_active(True)
            if self._state == STATE_IDLE:
                self._status.configure(text="Listening (VAD)\u2026", fg=COLOR_TEXT)

        elif kind == "recording_done":
            audio = event[1]
            self._set_state(STATE_TRANSCRIBING)
            if self._recorder and self._recorder.vad_active:
                self._vad_btn.set_recording(False)
            threading.Thread(
                target=self._do_transcribe, args=(audio,), daemon=True
            ).start()

        elif kind == "recording_empty":
            self._set_state(STATE_IDLE)
            if self._recorder and self._recorder.vad_active:
                self._vad_btn.set_recording(False)
                self._vad_btn.set_color(COLOR_GREEN)
            self._status.configure(text="No speech detected", fg=COLOR_TEXT_DIM)
            self.root.after(2000, lambda: (
                self._status.configure(text="Ready", fg=COLOR_TEXT)
                if self._state == STATE_IDLE else None
            ))

        elif kind == "transcription_result":
            text = event[1]
            # Ensure transcribing animation shows for at least 400ms
            elapsed_ms = int((time.monotonic() - getattr(self, '_transcribe_start', 0)) * 1000)
            delay = max(0, 400 - elapsed_ms)

            def _finish_transcription():
                # Guard: only proceed if still transcribing (user may have interrupted)
                if self._state != STATE_TRANSCRIBING:
                    return
                if text:
                    self._set_state(STATE_TYPING)
                    self._status.configure(
                        text=text[:40] + ("..." if len(text) > 40 else ""),
                        fg=COLOR_GREEN,
                    )
                    route = self._route_var.get()
                    threading.Thread(
                        target=self._do_type, args=(text, route), daemon=True
                    ).start()
                else:
                    self._set_state(STATE_IDLE)
                    if self._recorder and self._recorder.vad_active:
                        self._vad_btn.set_color(COLOR_GREEN)
                    self._status.configure(text="No speech detected", fg=COLOR_TEXT_DIM)
                    self.root.after(2000, lambda: (
                        self._status.configure(text="Ready", fg=COLOR_TEXT)
                        if self._state == STATE_IDLE else None
                    ))

            if delay > 0:
                self.root.after(delay, _finish_transcription)
            else:
                _finish_transcription()

        elif kind == "typing_done":
            # Always return to idle after typing attempt
            if self._recorder and self._recorder.vad_active:
                self._vad_btn.set_recording(False)
                self._vad_btn.set_color(COLOR_GREEN)
            # 1s cooldown so VAD doesn't immediately retrigger from tail-end audio
            self._vad_cooldown_until = time.time() + 1.0
            self.root.after(600, lambda: self._set_state(STATE_IDLE))

        elif kind == "audio_error":
            self._status.configure(text=f"Error: {event[1]}", fg=COLOR_RED)
            if self._state == STATE_RECORDING:
                self._set_state(STATE_IDLE)

    def _do_transcribe(self, audio) -> None:
        """Run transcription in background thread."""
        try:
            from transcriber import transcribe
            text = transcribe(audio)
            self._event_queue.put(("transcription_result", text))
        except Exception as e:
            self._event_queue.put(("audio_error", f"Transcription failed: {e}"))

    def _do_type(self, text: str, route: str) -> None:
        """Run text output in background thread. Always posts typing_done."""
        try:
            from typer import type_text
            type_text(text, route=route)
        except Exception:
            pass  # text is still on clipboard as fallback
        self._event_queue.put(("typing_done",))

    # ── Main loop ─────────────────────────────────────────────────

    def run(self) -> None:
        """Start the application."""
        self.root.after(100, self._init_components)
        self.root.after(POLL_INTERVAL_MS, self._poll_events)
        self.root.mainloop()


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Whisper Typer — voice typing for any window",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Whisper model size (tiny/base/small/medium/large-v3)",
    )
    parser.add_argument(
        "--device",
        default=None,
        choices=["cpu", "cuda"],
        help="Compute device (default: cpu)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List audio input devices and exit",
    )
    args = parser.parse_args()

    if args.list_devices:
        print("Audio input devices:")
        for idx, name in _get_input_devices():
            d = sd.query_devices(idx)
            ch = d.get("max_input_channels", 0)
            sr = d.get("default_samplerate", 0)
            print(f"  [{idx}] {name} ({ch}ch, {sr:.0f}Hz)")
        sys.exit(0)

    app = WhisperTyper(model=args.model, device=args.device)
    app.run()


if __name__ == "__main__":
    main()
