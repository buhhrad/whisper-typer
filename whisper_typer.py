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
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import sounddevice as sd

from config import (
    COLOR_AMBER,
    COLOR_BG,
    COLOR_BLUE,
    COLOR_DROPDOWN_BG,
    COLOR_DROPDOWN_FG,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
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

# ── Win32 constants for WS_EX_NOACTIVATE ─────────────────────────────
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


def _get_input_devices() -> list[tuple[int, str]]:
    """Return list of (device_index, display_name) for input devices."""
    result = []
    try:
        devices = sd.query_devices()
        for i in range(len(devices)):
            d = sd.query_devices(i)
            if d["max_input_channels"] > 0:
                result.append((i, d["name"]))
    except Exception:
        pass
    return result


class WhisperTyper:
    """Main application: tkinter GUI + state machine + orchestration."""

    def __init__(self, model: str | None = None, device: str | None = None):
        self._event_queue: queue.Queue = queue.Queue()
        self._state = STATE_IDLE
        self._recording_start: float = 0
        self._model_override = model
        self._device_override = device
        self._elapsed_timer_id: str | None = None
        self._model_ready = False

        # Lazy imports — only load heavy modules when needed
        self._recorder = None
        self._hotkey_listener = None

        # Device list
        self._input_devices = _get_input_devices()

        self._build_gui()

    # ── GUI Construction ──────────────────────────────────────────

    def _build_gui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Whisper Typer")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)  # no title bar

        # Style ttk comboboxes for dark theme
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=COLOR_DROPDOWN_BG,
            background=COLOR_SURFACE,
            foreground=COLOR_DROPDOWN_FG,
            arrowcolor=COLOR_TEXT_DIM,
            borderwidth=0,
            padding=2,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", COLOR_DROPDOWN_BG)],
            foreground=[("readonly", COLOR_DROPDOWN_FG)],
            selectbackground=[("readonly", COLOR_DROPDOWN_BG)],
            selectforeground=[("readonly", COLOR_DROPDOWN_FG)],
        )
        # Dropdown listbox colors
        self.root.option_add("*TCombobox*Listbox.background", COLOR_DROPDOWN_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", COLOR_DROPDOWN_FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", COLOR_SURFACE)
        self.root.option_add("*TCombobox*Listbox.selectForeground", COLOR_AMBER)

        # ── Row 1: Mic device selector ────────────────────────────
        row1 = tk.Frame(self.root, bg=COLOR_BG)
        row1.pack(fill=tk.X, padx=6, pady=(6, 2))

        tk.Label(
            row1, text="Mic:", font=("Segoe UI", 8), fg=COLOR_TEXT_DIM, bg=COLOR_BG,
        ).pack(side=tk.LEFT, padx=(0, 4))

        device_names = [name for _, name in self._input_devices]
        self._mic_var = tk.StringVar()
        if device_names:
            # Default to the system default input device
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

        self._mic_combo = ttk.Combobox(
            row1,
            textvariable=self._mic_var,
            values=device_names,
            state="readonly",
            style="Dark.TCombobox",
            font=("Segoe UI", 8),
            width=36,
        )
        self._mic_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._mic_combo.bind("<<ComboboxSelected>>", self._on_mic_changed)

        # Close button (top-right)
        close_btn = tk.Button(
            row1,
            text="\u00d7",  # x
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_TEXT_DIM,
            bg=COLOR_BG,
            activebackground=COLOR_RED,
            activeforeground=COLOR_TEXT,
            bd=0,
            padx=4,
            cursor="hand2",
            command=self._on_close,
        )
        close_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # ── Row 2: Output routing selector ────────────────────────
        row2 = tk.Frame(self.root, bg=COLOR_BG)
        row2.pack(fill=tk.X, padx=6, pady=(0, 4))

        tk.Label(
            row2, text="Out:", font=("Segoe UI", 8), fg=COLOR_TEXT_DIM, bg=COLOR_BG,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self._route_var = tk.StringVar(value=ROUTE_DEFAULT)
        self._route_combo = ttk.Combobox(
            row2,
            textvariable=self._route_var,
            values=ROUTE_OPTIONS,
            state="readonly",
            style="Dark.TCombobox",
            font=("Segoe UI", 8),
            width=36,
        )
        self._route_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Row 3: Controls bar ───────────────────────────────────
        row3 = tk.Frame(self.root, bg=COLOR_BG)
        row3.pack(fill=tk.X, padx=6, pady=(0, 6))

        # Mic button (disabled until model loads)
        self._mic_btn = tk.Button(
            row3,
            text="\u25cf MIC",  # bullet MIC
            font=("Segoe UI", 9, "bold"),
            fg=COLOR_TEXT_DIM,
            bg=COLOR_SURFACE,
            activebackground=COLOR_SURFACE,
            activeforeground=COLOR_TEXT_DIM,
            bd=0,
            padx=8,
            pady=3,
            state=tk.DISABLED,
            command=self._on_mic_click,
        )
        self._mic_btn.pack(side=tk.LEFT, padx=(0, 6))

        # Status label
        self._status = tk.Label(
            row3,
            text="Loading model...",
            font=("Segoe UI", 9),
            fg=COLOR_TEXT,
            bg=COLOR_BG,
            anchor="w",
        )
        self._status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # VAD toggle button
        self._vad_btn = tk.Button(
            row3,
            text="VAD",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_DIM,
            bg=COLOR_SURFACE,
            activebackground=COLOR_SURFACE,
            activeforeground=COLOR_TEXT,
            bd=0,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self._on_vad_toggle,
        )
        self._vad_btn.pack(side=tk.LEFT)

        # Draggable window — bind to status label and rows
        self._drag_data = {"x": 0, "y": 0}
        for widget in (row3, self._status):
            widget.bind("<Button-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)

        # Escape to quit (overrideredirect hides from Alt+Tab, so we need this)
        self.root.bind_all("<Escape>", lambda e: self._on_close())

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

    # ── Drag handling ─────────────────────────────────────────────

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event: tk.Event) -> None:
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        # Clamp to screen bounds
        scr_w = self.root.winfo_screenwidth()
        scr_h = self.root.winfo_screenheight()
        x = max(0, min(x, scr_w - self.root.winfo_width()))
        y = max(0, min(y, scr_h - self.root.winfo_height()))
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

    # ── Initialization (after mainloop starts) ────────────────────

    def _init_components(self) -> None:
        """Initialize audio, hotkeys, and preload model in background."""
        self._apply_window_styles()

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

        # Set up hotkeys
        from hotkeys import HotkeyListener
        self._hotkey_listener = HotkeyListener(self._event_queue)
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

    # ── State machine ─────────────────────────────────────────────

    def _set_state(self, state: str) -> None:
        self._state = state

        if state == STATE_IDLE:
            self._mic_btn.configure(bg=COLOR_AMBER, fg=COLOR_BG, text="\u25cf MIC")
            if self._recorder and self._recorder.vad_active:
                self._status.configure(text="Listening (VAD)...", fg=COLOR_TEXT)
            else:
                self._status.configure(text="Ready", fg=COLOR_TEXT)
            self._cancel_elapsed_timer()

        elif state == STATE_RECORDING:
            self._mic_btn.configure(bg=COLOR_RED, fg=COLOR_TEXT, text="\u25cf REC")
            self._recording_start = time.monotonic()
            self._update_elapsed()

        elif state == STATE_TRANSCRIBING:
            self._mic_btn.configure(bg=COLOR_BLUE, fg=COLOR_TEXT, text="...")
            self._status.configure(text="Transcribing...", fg=COLOR_BLUE)
            self._cancel_elapsed_timer()

        elif state == STATE_TYPING:
            self._mic_btn.configure(bg=COLOR_GREEN, fg=COLOR_BG, text="\u2713")
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
        if not self._recorder:
            return

        if self._recorder.vad_active:
            self._recorder.disable_vad()
            self._vad_btn.configure(fg=COLOR_TEXT_DIM, bg=COLOR_SURFACE)
            if self._state == STATE_IDLE:
                self._status.configure(text="Ready", fg=COLOR_TEXT)
        else:
            self._vad_btn.configure(fg=COLOR_BG, bg=COLOR_GREEN)
            self._status.configure(text="Loading VAD...", fg=COLOR_TEXT_DIM)

            def _enable():
                try:
                    self._recorder.enable_vad()
                    self._event_queue.put(("vad_ready",))
                except Exception as e:
                    self._event_queue.put(("audio_error", f"VAD load failed: {e}"))

            threading.Thread(target=_enable, daemon=True).start()

    def _on_close(self) -> None:
        """Clean shutdown."""
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
            self._mic_btn.configure(
                state=tk.NORMAL, fg=COLOR_BG, bg=COLOR_AMBER,
                activebackground=COLOR_AMBER, activeforeground=COLOR_BG,
                cursor="hand2",
            )
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

        elif kind == "vad_speech_start":
            if self._state == STATE_IDLE:
                self._set_state(STATE_RECORDING)

        elif kind == "vad_speech_end":
            pass  # recording_done will follow

        elif kind == "vad_ready":
            if self._state == STATE_IDLE:
                self._status.configure(text="Listening (VAD)...", fg=COLOR_TEXT)

        elif kind == "recording_done":
            audio = event[1]
            self._set_state(STATE_TRANSCRIBING)
            threading.Thread(
                target=self._do_transcribe, args=(audio,), daemon=True
            ).start()

        elif kind == "recording_empty":
            self._set_state(STATE_IDLE)
            self._status.configure(text="No speech detected", fg=COLOR_TEXT_DIM)
            self.root.after(2000, lambda: (
                self._status.configure(text="Ready", fg=COLOR_TEXT)
                if self._state == STATE_IDLE else None
            ))

        elif kind == "transcription_result":
            text = event[1]
            if text:
                self._set_state(STATE_TYPING)
                self._status.configure(
                    text=text[:40] + ("..." if len(text) > 40 else ""),
                    fg=COLOR_GREEN,
                )
                # Route text in background thread so it can't block/crash mainloop
                route = self._route_var.get()
                threading.Thread(
                    target=self._do_type, args=(text, route), daemon=True
                ).start()
            else:
                self._set_state(STATE_IDLE)
                self._status.configure(text="No speech detected", fg=COLOR_TEXT_DIM)
                self.root.after(2000, lambda: (
                    self._status.configure(text="Ready", fg=COLOR_TEXT)
                    if self._state == STATE_IDLE else None
                ))

        elif kind == "typing_done":
            # Always return to idle after typing attempt
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
