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
    COLOR_BLUE,
    COLOR_DROPDOWN_BG,
    COLOR_GREEN,
    COLOR_RED,
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
)
from compat import backend as _platform
from widgets import DropdownButton, MicIcon, VadToggle, LoadingBar, DurationBadge


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

        # Transcription queue — captures overlapping speech segments
        self._pending_audio = []
        self._muted = False

        # Snap-to-window state
        self._snap_hwnd = None
        self._snap_id: str | None = None
        self._snap_last_x: int = -1
        self._snap_last_y: int = -1
        self._snap_bar_w: int = 0
        self._snap_bar_h: int = 0
        self._snap_tk_hwnd: int = 0
        self._platform = _platform

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
        if self._platform.supports_transparency:
            self.root.attributes("-transparentcolor", COLOR_TRANSPARENT)
        self.root.overrideredirect(True)  # no title bar

        # ── Main bar — one unified draggable block ───────────────
        _BAR_BG = COLOR_TRANSPARENT if self._transparent_mode else COLOR_TERMINAL_BG
        _BTN_BG = _BAR_BG
        row = tk.Frame(self.root, bg=_BAR_BG)
        row.pack(fill=tk.BOTH, expand=True)
        self._bar_row = row

        # ── Grip dots (left edge) — visible in transparent mode for grabbing ──
        grip_l = tk.Canvas(
            row, width=8, height=30, bg=_BAR_BG,
            highlightthickness=0,
        )
        # Grip starts hidden — only packed when unsnapped

        # Mic icon (left) — hidden during loading
        self._mic_btn = MicIcon(row, command=self._on_mic_click, bg=_BTN_BG)
        self._mic_btn.set_disabled(True)

        # Loading bar — replaces mic + vad icons during boot
        self._loading_bar = LoadingBar(row, bg=_BTN_BG, color=COLOR_AMBER, track_color="#1a1a2a")
        self._loading_bar.pack(side=tk.LEFT, padx=2)

        # Duration badge — rounded pill between mic and VAD, visible during recording
        # Packed at width=0 initially — animates open/closed smoothly
        self._duration_badge = DurationBadge(
            row, bg=_BTN_BG, pill_color="#1a1a2a", text_color="#ff4444",
            on_resize=self._resize_window,
        )

        # Status label (hidden — kept for compatibility with status update calls)
        self._status = tk.Label(
            row, text="Loading model\u2026", font=(_platform.get_ui_font(), 7),
            fg=COLOR_TEXT_DIM, bg=_BAR_BG, anchor="w",
        )

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

        # VAD toggle — hidden during loading, shown when model ready
        self._vad_btn = VadToggle(
            row, command=self._on_vad_toggle, bg=_BTN_BG,
            off_color=COLOR_TEXT_DIM, on_color=COLOR_GREEN,
        )

        # ── Grip dots — draw and auto-center ──
        self._grips = [grip_l]

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
            self._loading_bar, self._duration_badge,
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
        """Create a system tray icon for show/hide and quit."""
        if not _HAS_TRAY:
            return
        self._tray_icon = pystray.Icon(
            "whisper_typer",
            self._make_tray_image(),
            "Whisper Typer",
            menu=pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.MenuItem("Quit", self._tray_quit),
            ),
        )
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    @staticmethod
    def _make_tray_image():
        """Create a mic tray icon — dark circle with gray mic outline."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill="#1a1a2a")
        draw.ellipse([4, 4, 60, 60], outline="#3a3a50", width=2)
        draw.rounded_rectangle([24, 14, 40, 38], radius=6, outline="#9090a8", width=2)
        draw.arc([20, 28, 44, 50], start=180, end=0, fill="#9090a8", width=2)
        draw.line([32, 50, 32, 56], fill="#9090a8", width=2)
        draw.line([24, 56, 40, 56], fill="#9090a8", width=2)
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

    def _apply_window_styles(self) -> None:
        """Apply tool-window style (no taskbar, no activate, topmost) via platform backend."""
        self._platform.apply_tool_window_style(self.root)
        self._apply_rounded_corners()

    def _apply_rounded_corners(self) -> None:
        """Set window shape to a rounded rectangle via platform backend.

        Only applies when snapped (transparent mode) — unsnapped windows
        use a solid background where clipping would cut off edge widgets.
        """
        self._platform.set_rounded_corners(self.root, radius=10, enable=self._transparent_mode)

    def _resize_window(self, skip_corners: bool = False) -> None:
        """Recalculate and apply window size after widget changes.

        skip_corners: skip rounded-corner update during animation frames (prevents hitbox issues).
        """
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        if not skip_corners:
            self._apply_rounded_corners()
        if self._snap_hwnd:
            self._snap_bar_w = w
            self._snap_bar_h = h

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
            vx, vy, vw, vh = self._platform.get_virtual_screen_bounds()
            x = max(vx, min(x, vx + vw - self.root.winfo_width()))
            y = max(vy, min(y, vy + vh - self.root.winfo_height()))
        except Exception:
            pass  # If get_virtual_screen_bounds fails, allow unclamped drag
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
        c.create_text(cx, cy, text="\u2699", font=(_platform.get_ui_font(), 11), fill=color)

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
                    mute_combo=self._settings.get("mute_hotkey"),
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
                mute_combo=self._settings.get("mute_hotkey"),
            )

    def _on_whisper_setting_changed(self, key: str, value: str, restart_label: tk.Label) -> None:
        """Save a whisper setting and show Apply button."""
        self._settings[key] = value
        import settings as user_settings
        user_settings.save(self._settings)
        restart_label.configure(text="  Apply & Restart  ", bg="#1a1a2a", pady=3)

    def _open_settings(self) -> None:
        """Open settings popup — translucent, rounded, wider."""
        _PANEL_BG = COLOR_TERMINAL_BG  # match the bar background
        _PANEL_ALPHA = 0.90
        _FONT = _platform.get_mono_font()  # matches terminal font
        _FONT_BODY = (_FONT, 8)
        _FONT_LABEL = (_FONT, 7, "bold")
        _FONT_SMALL = (_FONT, 6, "bold")
        _FONT_MONO = (_FONT, 7)
        _FG = "#e8e8f0"  # bright text — stays readable at 90% alpha
        _FG_DIM = "#8888a0"  # labels — brighter than COLOR_TEXT_DIM

        _CORNER_KEY = "#020102"  # transparency key for rounded corners
        _BORDER_CLR = "#222233"
        _CORNER_R = 12
        _INSET = 4  # content inset — must clear corner radius

        self._settings_popup = tk.Toplevel(self.root)
        self._settings_popup.overrideredirect(True)
        self._settings_popup.attributes("-topmost", True)
        self._settings_popup.attributes("-alpha", 0)  # hidden until bg renders
        self._settings_popup.configure(bg=_CORNER_KEY)
        if self._platform.supports_transparency:
            self._settings_popup.attributes("-transparentcolor", _CORNER_KEY)

        bg_canvas = tk.Canvas(self._settings_popup, bg=_CORNER_KEY, highlightthickness=0)
        bg_canvas.pack(fill=tk.BOTH, expand=True)
        content = tk.Frame(bg_canvas, bg=_PANEL_BG)
        panel_inner = tk.Frame(content, bg=_PANEL_BG)
        panel_inner.pack(fill=tk.BOTH, expand=True, padx=7, pady=5)

        # MIC selector
        p = panel_inner
        mic_row = tk.Frame(p, bg=_PANEL_BG)
        mic_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            mic_row, text="MIC", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        device_names = [name for _, name in self._input_devices]
        DropdownButton(
            mic_row, textvariable=self._mic_var, values=device_names,
            bg=COLOR_DROPDOWN_BG, fg=_FG,
            hover_bg="#222244", select_bg="#2a2a50", select_fg=COLOR_AMBER,
            font=_FONT_MONO,
            on_change=lambda: self._on_mic_changed(),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # OUT selector
        out_row = tk.Frame(p, bg=_PANEL_BG)
        out_row.pack(fill=tk.X)
        tk.Label(
            out_row, text="OUT", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        # Filter "Auto Terminal" route if the platform can't find terminals
        _routes = ROUTE_OPTIONS
        if not self._platform.supports_terminal_finding:
            from config import ROUTE_AUTO_TERMINAL
            _routes = [r for r in ROUTE_OPTIONS if r != ROUTE_AUTO_TERMINAL]
        DropdownButton(
            out_row, textvariable=self._route_var, values=_routes,
            bg=COLOR_DROPDOWN_BG, fg=_FG,
            hover_bg="#222244", select_bg="#2a2a50", select_fg=COLOR_AMBER,
            font=_FONT_MONO,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Whisper section ──
        tk.Frame(p, bg="#2a2a3a", height=1).pack(fill=tk.X, pady=(8, 5))
        tk.Label(
            p, text="WHISPER", font=_FONT_SMALL,
            fg=_FG_DIM, bg=_PANEL_BG, anchor="w",
        ).pack(fill=tk.X, pady=(0, 3))

        _MODEL_OPTIONS = [
            "tiny", "base", "small", "medium",
            "large-v3", "large-v3-turbo",
        ]
        _DEVICE_OPTIONS = ["cuda (fast)", "cpu (slow)"]
        _LANG_OPTIONS = [
            "auto", "en", "es", "fr", "de", "pt", "zh",
            "ja", "ko", "it", "nl", "ru", "pl", "ar", "hi",
        ]

        _DEVICE_LABELS = {"cuda": "cuda (fast)", "cpu": "cpu (slow)"}
        _DEVICE_VALUES = {"cuda (fast)": "cuda", "cpu (slow)": "cpu"}

        import config as _cfg
        cur_model = self._settings.get("whisper_model") or _cfg.WHISPER_MODEL
        cur_device = self._settings.get("whisper_device") or _cfg.WHISPER_DEVICE
        cur_lang = self._settings.get("whisper_language") or _cfg.WHISPER_LANGUAGE or "auto"

        model_var = tk.StringVar(value=cur_model)
        device_var = tk.StringVar(value=_DEVICE_LABELS.get(cur_device, cur_device))
        lang_var = tk.StringVar(value=cur_lang)

        # MODEL row
        model_row = tk.Frame(p, bg=_PANEL_BG)
        model_row.pack(fill=tk.X, pady=2)
        tk.Label(
            model_row, text="MODEL", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=5, anchor="w",
        ).pack(side=tk.LEFT)
        DropdownButton(
            model_row, textvariable=model_var, values=_MODEL_OPTIONS,
            bg=COLOR_DROPDOWN_BG, fg=_FG,
            hover_bg="#222244", select_bg="#2a2a50", select_fg=COLOR_AMBER,
            font=_FONT_MONO,
            on_change=lambda: self._on_whisper_setting_changed(
                "whisper_model", model_var.get(), restart_label),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # GPU row
        gpu_row = tk.Frame(p, bg=_PANEL_BG)
        gpu_row.pack(fill=tk.X, pady=2)
        tk.Label(
            gpu_row, text="GPU", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=5, anchor="w",
        ).pack(side=tk.LEFT)
        DropdownButton(
            gpu_row, textvariable=device_var, values=_DEVICE_OPTIONS,
            bg=COLOR_DROPDOWN_BG, fg=_FG,
            hover_bg="#222244", select_bg="#2a2a50", select_fg=COLOR_AMBER,
            font=_FONT_MONO,
            on_change=lambda: self._on_whisper_setting_changed(
                "whisper_device", _DEVICE_VALUES.get(device_var.get(), device_var.get()), restart_label),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # LANG row
        lang_row = tk.Frame(p, bg=_PANEL_BG)
        lang_row.pack(fill=tk.X, pady=2)
        tk.Label(
            lang_row, text="LANG", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=5, anchor="w",
        ).pack(side=tk.LEFT)
        DropdownButton(
            lang_row, textvariable=lang_var, values=_LANG_OPTIONS,
            bg=COLOR_DROPDOWN_BG, fg=_FG,
            hover_bg="#222244", select_bg="#2a2a50", select_fg=COLOR_AMBER,
            font=_FONT_MONO,
            on_change=lambda: self._on_whisper_setting_changed(
                "whisper_language", lang_var.get(), restart_label),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # "Apply" button — hidden until a whisper setting changes
        _APPLY_BG = "#1a1a2a"
        _APPLY_HOVER = "#2a2a40"
        restart_label = tk.Label(
            p, text="", font=(_FONT, 7, "bold"),
            fg=COLOR_AMBER, bg=_PANEL_BG, anchor="center",
            cursor="arrow",
        )
        restart_label.pack(fill=tk.X, pady=(4, 0))
        restart_label.bind("<ButtonRelease-1>", lambda e: self._restart())
        restart_label.bind("<Enter>", lambda e: restart_label.configure(bg=_APPLY_HOVER) if restart_label.cget("text") else None)
        restart_label.bind("<Leave>", lambda e: restart_label.configure(bg=_APPLY_BG) if restart_label.cget("text") else None)

        # ── Keybinds section ──
        tk.Frame(p, bg="#2a2a3a", height=1).pack(fill=tk.X, pady=(8, 5))
        kb_header = tk.Label(
            p, text="KEYBINDS", font=_FONT_SMALL,
            fg=_FG_DIM, bg=_PANEL_BG, anchor="w",
        )
        kb_header.pack(fill=tk.X, pady=(0, 3))

        # PTT keybind
        _KB_BG = "#161620"
        _KB_HOVER = "#1e1e30"
        ptt_row = tk.Frame(p, bg=_PANEL_BG, cursor="arrow")
        ptt_row.pack(fill=tk.X, pady=2)
        tk.Label(
            ptt_row, text="PTT", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        ptt_combo = self._settings.get("ptt_hotkey")
        ptt_label = tk.Label(
            ptt_row, text=self._format_hotkey(ptt_combo),
            font=_FONT_MONO, fg=_FG, bg=_KB_BG,
            padx=6, pady=2, anchor="w",
        )
        ptt_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ptt_clear = tk.Label(
            ptt_row, text="\u00d7", font=_FONT_BODY,
            fg=_FG_DIM, bg=_PANEL_BG, padx=4, cursor="arrow",
        )
        ptt_clear.pack(side=tk.RIGHT)
        ptt_label.bind("<ButtonRelease-1>",
                       lambda e: self._start_keybind_capture(ptt_label, "ptt_hotkey"))
        ptt_clear.bind("<ButtonRelease-1>",
                       lambda e: self._clear_keybind(ptt_label, "ptt_hotkey"))
        ptt_label.bind("<Enter>", lambda e: ptt_label.configure(bg=_KB_HOVER))
        ptt_label.bind("<Leave>", lambda e: ptt_label.configure(bg=_KB_BG))
        ptt_clear.bind("<Enter>", lambda e: ptt_clear.configure(fg=COLOR_RED))
        ptt_clear.bind("<Leave>", lambda e: ptt_clear.configure(fg=_FG_DIM))

        # VAD keybind
        vad_row = tk.Frame(p, bg=_PANEL_BG, cursor="arrow")
        vad_row.pack(fill=tk.X, pady=2)
        tk.Label(
            vad_row, text="VAD", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        vad_combo = self._settings.get("vad_hotkey")
        vad_label = tk.Label(
            vad_row, text=self._format_hotkey(vad_combo),
            font=_FONT_MONO, fg=_FG if vad_combo else _FG_DIM,
            bg=_KB_BG, padx=6, pady=2, anchor="w",
        )
        vad_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        vad_clear = tk.Label(
            vad_row, text="\u00d7", font=_FONT_BODY,
            fg=_FG_DIM, bg=_PANEL_BG, padx=4, cursor="arrow",
        )
        vad_clear.pack(side=tk.RIGHT)
        vad_label.bind("<ButtonRelease-1>",
                       lambda e: self._start_keybind_capture(vad_label, "vad_hotkey"))
        vad_clear.bind("<ButtonRelease-1>",
                       lambda e: self._clear_keybind(vad_label, "vad_hotkey"))
        vad_label.bind("<Enter>", lambda e: vad_label.configure(bg=_KB_HOVER))
        vad_label.bind("<Leave>", lambda e: vad_label.configure(bg=_KB_BG))
        vad_clear.bind("<Enter>", lambda e: vad_clear.configure(fg=COLOR_RED))
        vad_clear.bind("<Leave>", lambda e: vad_clear.configure(fg=_FG_DIM))

        # Mute keybind
        mute_row = tk.Frame(p, bg=_PANEL_BG, cursor="arrow")
        mute_row.pack(fill=tk.X, pady=2)
        tk.Label(
            mute_row, text="MUTE", font=_FONT_LABEL,
            fg=_FG_DIM, bg=_PANEL_BG, width=4, anchor="w",
        ).pack(side=tk.LEFT)
        mute_combo = self._settings.get("mute_hotkey")
        mute_label = tk.Label(
            mute_row, text=self._format_hotkey(mute_combo),
            font=_FONT_MONO, fg=_FG if mute_combo else _FG_DIM,
            bg=_KB_BG, padx=6, pady=2, anchor="w",
        )
        mute_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        mute_clear = tk.Label(
            mute_row, text="\u00d7", font=_FONT_BODY,
            fg=_FG_DIM, bg=_PANEL_BG, padx=4, cursor="arrow",
        )
        mute_clear.pack(side=tk.RIGHT)
        mute_label.bind("<ButtonRelease-1>",
                       lambda e: self._start_keybind_capture(mute_label, "mute_hotkey"))
        mute_clear.bind("<ButtonRelease-1>",
                       lambda e: self._clear_keybind(mute_label, "mute_hotkey"))
        mute_label.bind("<Enter>", lambda e: mute_label.configure(bg=_KB_HOVER))
        mute_label.bind("<Leave>", lambda e: mute_label.configure(bg=_KB_BG))
        mute_clear.bind("<Enter>", lambda e: mute_clear.configure(fg=COLOR_RED))
        mute_clear.bind("<Leave>", lambda e: mute_clear.configure(fg=_FG_DIM))

        # ── Toggles section ──
        tk.Frame(p, bg="#2a2a3a", height=1).pack(fill=tk.X, pady=(8, 5))

        # Snap to Terminal toggle (also controls transparency)
        # Only shown if the platform supports window snapping and terminal finding
        if self._platform.supports_window_snapping and self._platform.supports_terminal_finding:
            snap_on = bool(self._snap_hwnd)
            snap_check = "\u2713" if snap_on else "\u2002"
            snap_fg = COLOR_AMBER if snap_on else _FG_DIM
            snap_row = tk.Frame(p, bg=_PANEL_BG, cursor="arrow")
            snap_row.pack(fill=tk.X, pady=2)
            snap_box = tk.Label(
                snap_row, text=f"[{snap_check}]", font=_FONT_MONO,
                fg=snap_fg, bg=_PANEL_BG, padx=(4),
            )
            snap_box.pack(side=tk.LEFT)
            snap_txt = tk.Label(
                snap_row, text="Snap to Terminal", font=_FONT_BODY,
                fg=snap_fg, bg=_PANEL_BG, anchor="w",
            )
            snap_txt.pack(side=tk.LEFT, padx=(2, 0))
            for w in (snap_row, snap_box, snap_txt):
                w.bind("<Enter>", lambda e, b=snap_box, t=snap_txt: (
                    b.configure(fg=COLOR_AMBER), t.configure(fg=COLOR_AMBER)))
                w.bind("<Leave>", lambda e, b=snap_box, t=snap_txt, on=snap_on: (
                    b.configure(fg=COLOR_AMBER if on else _FG_DIM),
                    t.configure(fg=COLOR_AMBER if on else _FG_DIM)))
                w.bind("<ButtonRelease-1>", lambda e: self._toggle_snap())

        # ── Restart button ──
        tk.Frame(p, bg="#2a2a3a", height=1).pack(fill=tk.X, pady=(8, 5))
        restart_btn = tk.Label(
            p, text="Restart", font=_FONT_BODY,
            fg=_FG_DIM, bg=_PANEL_BG, cursor="arrow", anchor="center",
        )
        restart_btn.pack(fill=tk.X, pady=2)
        restart_btn.bind("<Enter>", lambda e: restart_btn.configure(fg=COLOR_AMBER))
        restart_btn.bind("<Leave>", lambda e: restart_btn.configure(fg=_FG_DIM))
        restart_btn.bind("<ButtonRelease-1>", lambda e: self._restart())

        # Position above or below — dynamically choose based on screen space
        self._settings_popup.update_idletasks()
        content.update_idletasks()
        popup_w = max(self.root.winfo_width(), 220)
        x = self.root.winfo_x()
        h = content.winfo_reqheight() + 2 * _INSET
        bar_bottom = self.root.winfo_y() + self.root.winfo_height()
        screen_h = self.root.winfo_screenheight()
        if bar_bottom + h > screen_h - 48:
            y = self.root.winfo_y() - h
        else:
            y = bar_bottom
        self._settings_popup.geometry(f"{popup_w}x{h}+{x}+{y}")

        # Render rounded background via PIL — no window region, no corner clipping
        def _render_bg():
            try:
                if not (self._settings_popup and self._settings_popup.winfo_exists()):
                    return
                pw = self._settings_popup.winfo_width()
                ph = self._settings_popup.winfo_height()
                def _hex(c):
                    return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
                img = Image.new("RGB", (pw, ph), _hex(_CORNER_KEY))
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle(
                    [0, 0, pw - 1, ph - 1], radius=_CORNER_R,
                    fill=_hex(_PANEL_BG), outline=_hex(_BORDER_CLR), width=1,
                )
                photo = ImageTk.PhotoImage(img)
                bg_canvas.create_image(0, 0, anchor="nw", image=photo)
                bg_canvas._photo = photo
                bg_canvas.create_window(
                    _INSET, _INSET, window=content, anchor="nw",
                    width=pw - 2 * _INSET, height=ph - 2 * _INSET,
                )
                self._settings_popup.attributes("-alpha", _PANEL_ALPHA)
            except Exception:
                pass
        self._settings_popup.after(10, _render_bg)

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
        """Find a visible terminal window to snap to via platform backend."""
        from config import TERMINAL_TITLE_HINTS, TERMINAL_TITLE_EXCLUDE
        return self._platform.find_terminal_window(
            title_hints=TERMINAL_TITLE_HINTS,
            title_exclude=TERMINAL_TITLE_EXCLUDE,
        )

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
            if self._vad_btn._active and not self._vad_btn._recording and not self._vad_btn._processing:
                self._vad_btn._draw_bars(self._vad_btn._REST_HEIGHTS, self._vad_btn._on_color, solid=True)
            elif not self._vad_btn._active:
                self._vad_btn._draw_off()  # outline
        # Re-render duration badge with new bg
        if hasattr(self, '_duration_badge') and self._duration_badge._visible:
            self._duration_badge._render()
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
        self._snap_tk_hwnd = self._platform.get_tk_hwnd(self.root)
        # Enable transparency and hide grips when snapping
        if not self._transparent_mode:
            self._set_transparency(True)
        for g in self._grips:
            g.pack_forget()
        # Resize window after hiding grips, then store snapped dimensions
        self._resize_window()
        self._snap_bar_w = self.root.winfo_width()
        self._snap_bar_h = self.root.winfo_height()
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
        # Clear the window region first — prevents clipping during resize
        self._platform.set_rounded_corners(self.root, radius=10, enable=False)
        # Show grips when unsnapping — pack at left edge before all other widgets
        for g in self._grips:
            g.pack(side=tk.LEFT, fill=tk.Y, padx=2)
            # Move to front of pack order
            first_child = self._bar_row.pack_slaves()[0] if self._bar_row.pack_slaves() else None
            if first_child and first_child is not g:
                g.pack(side=tk.LEFT, fill=tk.Y, padx=2, before=first_child)
        if self._transparent_mode:
            self._set_transparency(False)  # redraws grip dots with solid bg
        else:
            if hasattr(self, '_draw_grip_dots'):
                self._draw_grip_dots()
        # Resize window — geometry must settle before applying rounded corners
        self.root.update_idletasks()
        self._resize_window()

    def _snap_poll(self) -> None:
        """Track the snapped window position via polling."""
        try:
            if not self._snap_hwnd or not self._platform.is_window_valid(self._snap_hwnd):
                self._snap_hwnd = None
                return

            if self._platform.is_window_minimized(self._snap_hwnd):
                self.root.withdraw()
                self._snap_id = self.root.after(200, self._snap_poll)
                return

            self.root.deiconify()

            rect = self._platform.get_window_rect(self._snap_hwnd)
            if rect is None:
                return

            left, top, right, bottom = rect
            # Center horizontally on terminal, vertically in bottom status area
            x = left + (right - left - self._snap_bar_w) // 2
            y = bottom - self._snap_bar_h - 8
            if x != self._snap_last_x or y != self._snap_last_y:
                self._snap_last_x = x
                self._snap_last_y = y
                # Direct platform move — bypasses tkinter string parsing
                self._platform.set_window_position(self._snap_tk_hwnd, x, y)
        except Exception:
            pass

        if self._snap_hwnd:
            self._snap_id = self.root.after(
                self._platform.snap_poll_interval_ms, self._snap_poll)

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
        mute = self._settings.get("mute_hotkey") or ["ctrl", "shift", "m"]
        self._hotkey_listener = HotkeyListener(
            self._event_queue, ptt_combo=ptt, vad_combo=vad,
            mute_combo=mute,
        )
        self._hotkey_listener.start()

        # Apply config overrides BEFORE spawning the preload thread (avoids race)
        # Priority: CLI args > saved settings > config.py defaults
        import config
        model = self._model_override or self._settings.get("whisper_model")
        device = self._device_override or self._settings.get("whisper_device")
        language = self._settings.get("whisper_language")
        if model:
            config.WHISPER_MODEL = model
        if device:
            config.WHISPER_DEVICE = device
            config.WHISPER_COMPUTE = "float16" if device == "cuda" else "int8"
        if language:
            config.WHISPER_LANGUAGE = language if language != "auto" else None

        # Preload whisper model in background
        def _preload():
            try:
                from transcriber import preload
                preload()
                self._event_queue.put(("model_loaded",))
            except Exception as e:
                self._event_queue.put(("model_error", str(e)))

        threading.Thread(target=_preload, daemon=True).start()

        # Don't auto-restore VAD — user must explicitly enable it each session

        # Auto-snap to terminal if one is available (only on supported platforms)
        hwnd = self._find_terminal_hwnd() if self._platform.supports_window_snapping else None
        if hwnd:
            self._snap_hwnd = hwnd
            self._snap_tk_hwnd = self._platform.get_tk_hwnd(self.root)
            # Hide grips when snapped and resize
            for g in self._grips:
                g.pack_forget()
            self._resize_window()
            self._snap_bar_w = self.root.winfo_width()
            self._snap_bar_h = self.root.winfo_height()
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
            # Show duration badge (already packed at width=0 from model load)
            self._duration_badge.show()
            self._update_elapsed()

        elif state == STATE_TRANSCRIBING:
            self._mic_btn.set_state("transcribing", COLOR_BLUE)
            self._status.configure(text="Transcribing\u2026", fg=COLOR_BLUE)
            self._cancel_elapsed_timer()

        elif state == STATE_TYPING:
            self._mic_btn.set_state("typing", COLOR_GREEN)
            self._cancel_elapsed_timer()

    def _update_elapsed(self) -> None:
        """Update duration badge next to mic icon."""
        if self._state != STATE_RECORDING:
            return
        elapsed = time.monotonic() - self._recording_start
        mins, secs = divmod(int(elapsed), 60)
        self._duration_badge.set_time(f"{mins}:{secs:02d}")
        self._elapsed_timer_id = self.root.after(200, self._update_elapsed)

    def _cancel_elapsed_timer(self) -> None:
        if self._elapsed_timer_id:
            self.root.after_cancel(self._elapsed_timer_id)
            self._elapsed_timer_id = None
        self._duration_badge.hide()  # animated collapse

    def _process_next_or_idle(self):
        """Process next queued audio segment, or return to idle."""
        if self._pending_audio:
            audio = self._pending_audio.pop(0)
            self._set_state(STATE_TRANSCRIBING)
            threading.Thread(
                target=self._do_transcribe, args=(audio,), daemon=True
            ).start()
        else:
            if self._recorder and self._recorder.vad_active:
                # Set color first, then fade out (fade uses the new color)
                self._vad_btn._on_color = COLOR_GREEN
                self._vad_btn.set_processing(False)
            self._vad_cooldown_until = time.time() + 0.3
            self.root.after(200, lambda: self._set_state(STATE_IDLE))

    # ── Button handlers ───────────────────────────────────────────

    def _on_mic_click(self) -> None:
        """Toggle mute when VAD active, or toggle recording in manual mode."""
        if not self._model_ready:
            return
        # VAD mode: clicking mic toggles mute
        if self._recorder and self._recorder.vad_active:
            self._muted = not self._muted
            self._mic_btn.set_muted(self._muted)
            if self._muted:
                self._status.configure(text="Muted", fg=COLOR_RED)
            else:
                self._status.configure(text="Listening (VAD)\u2026", fg=COLOR_TEXT)
            return
        # Manual mode: toggle recording
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
            self._muted = False
            self._mic_btn.set_muted(False)
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
            # Swap loading bar for real icons
            self._loading_bar.stop()
            self._loading_bar.pack_forget()
            self._mic_btn.set_disabled(False)
            self._mic_btn.set_state("idle", COLOR_TEXT_DIM)
            self._mic_btn.pack(side=tk.LEFT, padx=(4, 2))
            # Pre-pack badge at width=0 so pack order is: mic → badge → ... → vad
            self._duration_badge.pack(side=tk.LEFT, padx=0)
            self._vad_btn.pack(side=tk.RIGHT, padx=2)
            # Re-render all icons with correct bg (especially in transparent mode)
            self._draw_close_icon(self._close_color)
            self._draw_gear_icon(COLOR_TEXT_DIM)
            self._vad_btn._draw_off()
            if hasattr(self, '_draw_grip_dots'):
                self._draw_grip_dots()
            # Resize window to fit new widgets — defer a second pass
            # so geometry is fully settled before applying rounded corners
            self._resize_window()
            self.root.after(50, self._resize_window)
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

        elif kind == "mute_toggle":
            # Only toggle mute — don't fall through to manual recording
            if self._recorder and self._recorder.vad_active:
                self._muted = not self._muted
                self._mic_btn.set_muted(self._muted)
                if self._muted:
                    self._status.configure(text="Muted", fg=COLOR_RED)
                else:
                    self._status.configure(text="Listening (VAD)\u2026", fg=COLOR_TEXT)

        elif kind == "vad_speech_start":
            if self._muted:
                pass  # ignore speech when muted
            elif self._state == STATE_IDLE and time.time() >= self._vad_cooldown_until:
                self._set_state(STATE_RECORDING)
                self._vad_btn.set_recording(True)
            elif self._state in (STATE_TRANSCRIBING, STATE_TYPING):
                # Override processing animation with energetic recording animation
                self._vad_btn.set_recording(True)

        elif kind == "vad_speech_end":
            if self._state in (STATE_TRANSCRIBING, STATE_TYPING):
                # Back to gentle processing animation (not static)
                self._vad_btn.set_processing(True)

        elif kind == "vad_ready":
            self._vad_btn.set_active(True)
            if self._state == STATE_IDLE:
                self._status.configure(text="Listening (VAD)\u2026", fg=COLOR_TEXT)

        elif kind == "recording_done":
            audio = event[1]
            if self._state in (STATE_TRANSCRIBING, STATE_TYPING):
                # Already processing — queue this audio for later
                self._pending_audio.append(audio)
            else:
                self._set_state(STATE_TRANSCRIBING)
                if self._recorder and self._recorder.vad_active:
                    # Transition to gentle processing animation
                    self._vad_btn.set_processing(True)
                threading.Thread(
                    target=self._do_transcribe, args=(audio,), daemon=True
                ).start()

        elif kind == "recording_empty":
            # Only go idle if nothing is in-flight
            if self._state == STATE_RECORDING:
                self._set_state(STATE_IDLE)
                if self._recorder and self._recorder.vad_active:
                    self._vad_btn.set_processing(False)
            elif self._state in (STATE_TRANSCRIBING, STATE_TYPING):
                # Keep processing animation going
                if self._recorder and self._recorder.vad_active:
                    self._vad_btn.set_processing(True)

        elif kind == "transcription_result":
            text = event[1]
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
                self._process_next_or_idle()

        elif kind == "typing_done":
            self._process_next_or_idle()

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

    def _restart(self) -> None:
        """Restart the application to apply new settings."""
        # Clean up
        if self._recorder:
            try:
                self._recorder.close_stream()
            except Exception:
                pass
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        if hasattr(self, '_tray_icon') and self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()
        # Re-exec the process
        os.execv(sys.executable, [sys.executable] + sys.argv)

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
