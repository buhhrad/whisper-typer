"""Custom styled widgets for Whisper Typer.

Canvas-based rounded buttons and dropdown menus that look modern
on the dark theme instead of default tkinter/ttk widgets.
"""

from __future__ import annotations

import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

_SUPERSAMPLE = 4


def _aa_icon(canvas, width, height, draw_fn):
    """Render draw_fn at 4x resolution, downscale with LANCZOS for anti-aliased icons.

    Composites onto the canvas background color. On transparent backgrounds
    (#010101), alpha is thresholded to prevent dark fringe artifacts.
    """
    S = _SUPERSAMPLE
    img = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_fn(draw, S)
    small = img.resize((width, height), Image.LANCZOS)

    # Composite onto canvas background
    bg_hex = canvas.cget("bg")
    r, g, b = _hex_to_rgb(bg_hex)
    bg_img = Image.new("RGBA", (width, height), (r, g, b, 255))

    if bg_hex.lower() == "#010101":
        # Transparent mode: threshold alpha to prevent dark fringe
        alpha = small.split()[3]
        mask = alpha.point(lambda a: 255 if a > 100 else 0)
        bg_img.paste(small, (0, 0), mask)
    else:
        # Solid mode: smooth anti-aliased compositing
        bg_img.paste(small, (0, 0), small)

    photo = ImageTk.PhotoImage(bg_img)
    canvas._photo = photo  # prevent GC
    canvas.delete("all")
    canvas.create_image(width // 2, height // 2, image=photo)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"


def _lighten(hex_color: str, amount: int = 20) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(r + amount, g + amount, b + amount)


def _darken(hex_color: str, amount: int = 15) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(r - amount, g - amount, b - amount)


class PillButton(tk.Canvas):
    """Rounded pill-shaped button drawn on a Canvas.

    Supports hover effects, disabled state, and dynamic color changes.
    """

    def __init__(
        self,
        parent,
        text: str = "",
        bg: str = "#1a1a30",
        fg: str = "#e0e0e0",
        hover_bg: str | None = None,
        font: tuple = ("Segoe UI", 9, "bold"),
        padx: int = 16,
        pady: int = 6,
        radius: int = 12,
        command=None,
        **kwargs,
    ):
        self._bg_color = bg
        self._fg_color = fg
        self._hover_bg = hover_bg or _lighten(bg, 18)
        self._font = font
        self._padx = padx
        self._pady = pady
        self._radius = radius
        self._command = command
        self._disabled = False
        self._text = text

        # Measure text to size the canvas
        _tmp = tk.Label(parent, text=text, font=font)
        tw = _tmp.winfo_reqwidth()
        th = _tmp.winfo_reqheight()
        _tmp.destroy()

        self._width = tw + padx * 2
        self._height = th + pady * 2

        super().__init__(
            parent,
            width=self._width,
            height=self._height,
            bg=kwargs.get("canvas_bg", parent.cget("bg")),
            highlightthickness=0,
            **{k: v for k, v in kwargs.items() if k != "canvas_bg"},
        )

        self._draw(self._bg_color, self._fg_color)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Draw a rounded rectangle on the canvas."""
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r,
            x2, y2, x2 - r, y2,
            x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r,
            x1, y1, x1 + r, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _draw(self, bg: str, fg: str):
        self.delete("all")
        self._rounded_rect(0, 0, self._width, self._height, self._radius, fill=bg, outline="")
        self.create_text(
            self._width // 2, self._height // 2,
            text=self._text, font=self._font, fill=fg,
        )

    def _on_enter(self, e=None):
        if not self._disabled:
            self.configure(cursor="arrow")
            self._draw(self._hover_bg, self._fg_color)

    def _on_leave(self, e=None):
        self.configure(cursor="")
        self._draw(self._bg_color, self._fg_color)

    def _on_press(self, e=None):
        if not self._disabled:
            self._draw(_darken(self._bg_color, 10), self._fg_color)

    def _on_release(self, e=None):
        if not self._disabled:
            self._draw(self._hover_bg, self._fg_color)
            if self._command:
                self._command()

    def set_colors(self, bg: str, fg: str, hover_bg: str | None = None):
        """Update button colors dynamically."""
        self._bg_color = bg
        self._fg_color = fg
        self._hover_bg = hover_bg or _lighten(bg, 18)
        self._draw(bg, fg)

    def set_text(self, text: str):
        """Update button text."""
        self._text = text
        self._draw(self._bg_color, self._fg_color)

    def set_disabled(self, disabled: bool):
        self._disabled = disabled

    def configure_btn(self, **kwargs):
        """Convenience for state changes matching tk.Button-like API."""
        if "bg" in kwargs or "fg" in kwargs or "text" in kwargs:
            if "bg" in kwargs:
                self._bg_color = kwargs["bg"]
                self._hover_bg = _lighten(kwargs["bg"], 18)
            if "fg" in kwargs:
                self._fg_color = kwargs["fg"]
            if "text" in kwargs:
                self._text = kwargs["text"]
            self._draw(self._bg_color, self._fg_color)
        if "state" in kwargs:
            self._disabled = kwargs["state"] == tk.DISABLED


class DropdownButton(tk.Frame):
    """Custom dropdown selector — a styled button that opens a popup list.

    Replaces ttk.Combobox with a fully themed dark dropdown.
    """

    def __init__(
        self,
        parent,
        textvariable: tk.StringVar,
        values: list[str],
        bg: str = "#1a1a32",
        fg: str = "#d0d0e0",
        hover_bg: str = "#222244",
        select_bg: str = "#2a2a50",
        select_fg: str = "#e0a820",
        font: tuple = ("Segoe UI", 8),
        on_change=None,
        **kwargs,
    ):
        super().__init__(parent, bg=parent.cget("bg"), **kwargs)

        self._var = textvariable
        self._values = list(values)
        self._bg = bg
        self._fg = fg
        self._hover_bg = hover_bg
        self._select_bg = select_bg
        self._select_fg = select_fg
        self._font = font
        self._on_change = on_change
        self._popup: tk.Toplevel | None = None
        self._configure_bind_id: str | None = None

        # Main button area
        self._btn_frame = tk.Frame(self, bg=bg)
        self._btn_frame.pack(fill=tk.X)

        self._label = tk.Label(
            self._btn_frame,
            textvariable=self._var,
            font=font,
            fg=fg,
            bg=bg,
            anchor="w",
            padx=8,
            pady=4,
        )
        self._label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._arrow = tk.Label(
            self._btn_frame,
            text="\u25be",  # small down triangle
            font=(font[0], font[1]),
            fg="#6a6a8a",
            bg=bg,
            padx=6,
            pady=4,
        )
        self._arrow.pack(side=tk.RIGHT)

        # Hover + click bindings
        for w in (self._btn_frame, self._label, self._arrow):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<ButtonPress-1>", self._toggle_popup)

    def _on_enter(self, e=None):
        for w in (self._btn_frame, self._label, self._arrow):
            w.configure(bg=self._hover_bg, cursor="arrow")

    def _on_leave(self, e=None):
        for w in (self._btn_frame, self._label, self._arrow):
            w.configure(bg=self._bg, cursor="")

    def _toggle_popup(self, e=None):
        if self._popup and self._popup.winfo_exists():
            self._close_popup()
            return
        self._open_popup()

    def _open_popup(self):
        if not self._values:
            return

        self._popup = tk.Toplevel(self)
        self._popup.overrideredirect(True)
        self._popup.attributes("-topmost", True)
        self._popup.configure(bg="#1a1a32")

        # Position below the button
        x = self._btn_frame.winfo_rootx()
        y = self._btn_frame.winfo_rooty() + self._btn_frame.winfo_height()
        w = self._btn_frame.winfo_width()

        border_frame = tk.Frame(self._popup, bg="#3a3a5a", padx=1, pady=1)
        border_frame.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(border_frame, bg="#14142a")
        inner.pack(fill=tk.BOTH, expand=True)

        current = self._var.get()

        for val in self._values:
            is_selected = val == current
            item_bg = self._select_bg if is_selected else "#14142a"
            item_fg = self._select_fg if is_selected else self._fg

            item = tk.Label(
                inner, text=val, font=self._font,
                fg=item_fg, bg=item_bg, anchor="w", padx=10, pady=3,
            )
            item.pack(fill=tk.X)

            item.bind("<Enter>", lambda e, lbl=item: lbl.configure(bg=self._hover_bg))
            item.bind("<Leave>", lambda e, lbl=item, sel=is_selected:
                      lbl.configure(bg=self._select_bg if sel else "#14142a"))
            item.bind("<ButtonPress-1>", lambda e, v=val: self._select(v))

        self._popup.update_idletasks()
        popup_h = self._popup.winfo_reqheight()
        self._popup.geometry(f"{w}x{popup_h}+{x}+{y}")

        # Close when clicking anywhere outside the popup
        self._popup.grab_set_global()
        self._popup.bind("<ButtonPress-1>", self._popup_click)
        self._popup.focus_set()
        self._popup.bind("<Escape>", lambda e: self._close_popup())
        self._configure_bind_id = self.winfo_toplevel().bind(
            "<Configure>", lambda e: self._close_popup(), add="+",
        )

    def _popup_click(self, event):
        """Close popup if click is outside its bounds."""
        if not self._popup or not self._popup.winfo_exists():
            return
        # event x_root/y_root are screen coords; check if inside popup
        px = self._popup.winfo_rootx()
        py = self._popup.winfo_rooty()
        pw = self._popup.winfo_width()
        ph = self._popup.winfo_height()
        if not (px <= event.x_root <= px + pw and py <= event.y_root <= py + ph):
            self._close_popup()

    def _select(self, value: str):
        self._var.set(value)
        self._close_popup()
        if self._on_change:
            self._on_change()

    def _close_popup(self):
        if self._configure_bind_id:
            try:
                self.winfo_toplevel().unbind("<Configure>", self._configure_bind_id)
            except Exception:
                pass
            self._configure_bind_id = None
        if self._popup and self._popup.winfo_exists():
            try:
                self._popup.grab_release()
            except Exception:
                pass
            self._popup.destroy()
        self._popup = None

    def set_values(self, values: list[str]):
        self._values = list(values)


class MicIcon(tk.Canvas):
    """Canvas-based mic status icon with 4 states.

    IDLE:         microphone outline (amber)
    RECORDING:    filled red circle (record dot)
    TRANSCRIBING: three animated dots (blue)
    TYPING:       upward arrow / send (green)
    """

    SIZE = 30

    def __init__(self, parent, command=None, bg: str = "#0e0e1a", **kwargs):
        super().__init__(
            parent, width=self.SIZE, height=self.SIZE,
            bg=bg, highlightthickness=0, **kwargs,
        )
        self._command = command
        self._bg = bg
        self._state = "idle"
        self._color = "#e0a820"
        self._hover = False
        self._disabled = False
        self._pulse_id: str | None = None
        self._pulse_frame = 0
        self._photo = None  # PIL anti-aliased render reference

        self._draw_mic(self._color)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_click)

    def _draw_mic(self, color: str):
        """Draw a microphone icon with stroke outline, anti-aliased."""
        stroke = _lighten(color, 40)
        if _HAS_PIL:
            def _draw(d, S):
                cx, cy = self.SIZE * S // 2, self.SIZE * S // 2
                w = max(1, round(1.5 * S))
                d.ellipse([cx - 3*S, cy - 8*S, cx + 3*S, cy + 2*S], outline=stroke, width=w)
                d.arc([cx - 6*S, cy - 4*S, cx + 6*S, cy + 5*S],
                      start=0, end=180, fill=stroke, width=w)
                d.line([(cx, cy + 5*S), (cx, cy + 9*S)], fill=stroke, width=w)
                d.line([(cx - 3*S, cy + 9*S), (cx + 3*S, cy + 9*S)], fill=stroke, width=w)
                d.ellipse([cx - 2*S, cy - 7*S, cx + 2*S, cy + 1*S], fill=color)
            _aa_icon(self, self.SIZE, self.SIZE, _draw)
        else:
            self.delete("all")
            cx, cy = self.SIZE // 2, self.SIZE // 2
            self.create_oval(cx - 3, cy - 8, cx + 3, cy + 2, fill="", outline=stroke, width=1.5)
            self.create_arc(cx - 6, cy - 4, cx + 6, cy + 5,
                            start=180, extent=180, style="arc", outline=stroke, width=1.5)
            self.create_line(cx, cy + 5, cx, cy + 9, fill=stroke, width=1.5)
            self.create_line(cx - 3, cy + 9, cx + 3, cy + 9, fill=stroke, width=1.5)
            self.create_oval(cx - 2, cy - 7, cx + 2, cy + 1, fill=color, outline="")

    def _draw_record(self, color: str, scale: float = 1.0):
        """Draw a filled record circle with stroke outline, anti-aliased."""
        stroke = _lighten(color, 40)
        if _HAS_PIL:
            def _draw(d, S):
                cx, cy = self.SIZE * S // 2, self.SIZE * S // 2
                s = self.SIZE * S / 36
                r = 7 * s * scale
                w = max(1, round(1.5 * S))
                d.ellipse([cx - r - S, cy - r - S, cx + r + S, cy + r + S],
                          outline=stroke, width=w)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
            _aa_icon(self, self.SIZE, self.SIZE, _draw)
        else:
            self.delete("all")
            cx, cy = self.SIZE // 2, self.SIZE // 2
            s = self.SIZE / 36
            r = 7 * s * scale
            self.create_oval(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                             fill="", outline=stroke, width=1.5)
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="")

    def _draw_dots(self, color: str, frame: int):
        """Draw animated transcribing dots with stroke outlines, anti-aliased."""
        import math
        stroke = _lighten(color, 40)
        if _HAS_PIL:
            def _draw(d, S):
                cx, cy = self.SIZE * S // 2, self.SIZE * S // 2
                s = self.SIZE * S / 36
                w = max(1, round(S * 0.75))
                for i, dx in enumerate([-8, 0, 8]):
                    sdx = dx * s
                    angle = (frame * 0.4) + (i * 1.8)
                    dy = math.sin(angle) * 4 * s
                    r = (2.5 + math.sin(angle) * 0.5) * s
                    d.ellipse([cx + sdx - r, cy + dy - r, cx + sdx + r, cy + dy + r],
                              fill=color, outline=stroke, width=w)
            _aa_icon(self, self.SIZE, self.SIZE, _draw)
        else:
            self.delete("all")
            cx, cy = self.SIZE // 2, self.SIZE // 2
            s = self.SIZE / 36
            for i, dx in enumerate([-8, 0, 8]):
                sdx = dx * s
                angle = (frame * 0.4) + (i * 1.8)
                dy = math.sin(angle) * 4 * s
                r = (2.5 + math.sin(angle) * 0.5) * s
                self.create_oval(cx + sdx - r, cy + dy - r, cx + sdx + r, cy + dy + r,
                                 fill=color, outline=stroke, width=1)

    def _draw_send(self, color: str):
        """Draw an outbox icon (tray + upward arrow) with stroke, anti-aliased."""
        stroke = _lighten(color, 40)
        if _HAS_PIL:
            def _draw(d, S):
                cx, cy = self.SIZE * S // 2, self.SIZE * S // 2
                w = max(1, round(1.5 * S))
                # Upward arrow shaft
                d.line([(cx, cy + 2*S), (cx, cy - 5*S)], fill=stroke, width=max(1, round(2*S)))
                d.line([(cx, cy + 2*S), (cx, cy - 5*S)], fill=color, width=w)
                # Arrow chevron
                d.line([(cx - 3*S, cy - 2*S), (cx, cy - 5*S)], fill=stroke, width=max(1, round(2*S)))
                d.line([(cx + 3*S, cy - 2*S), (cx, cy - 5*S)], fill=stroke, width=max(1, round(2*S)))
                d.line([(cx - 3*S, cy - 2*S), (cx, cy - 5*S)], fill=color, width=w)
                d.line([(cx + 3*S, cy - 2*S), (cx, cy - 5*S)], fill=color, width=w)
                # Tray — U shape at bottom
                tray_pts = [
                    (cx - 6*S, cy + 1*S), (cx - 6*S, cy + 5*S),
                    (cx + 6*S, cy + 5*S), (cx + 6*S, cy + 1*S),
                ]
                d.line(tray_pts, fill=stroke, width=max(1, round(2*S)), joint="miter")
                d.line(tray_pts, fill=color, width=w, joint="miter")
            _aa_icon(self, self.SIZE, self.SIZE, _draw)
        else:
            self.delete("all")
            cx, cy = self.SIZE // 2, self.SIZE // 2
            # Arrow
            self.create_line(cx, cy + 2, cx, cy - 5, fill=stroke, width=2)
            self.create_line(cx - 3, cy - 2, cx, cy - 5, fill=stroke, width=2)
            self.create_line(cx + 3, cy - 2, cx, cy - 5, fill=stroke, width=2)
            self.create_line(cx, cy + 2, cx, cy - 5, fill=color, width=1.2)
            self.create_line(cx - 3, cy - 2, cx, cy - 5, fill=color, width=1.2)
            self.create_line(cx + 3, cy - 2, cx, cy - 5, fill=color, width=1.2)
            # Tray
            self.create_line(cx - 6, cy + 1, cx - 6, cy + 5, cx + 6, cy + 5, cx + 6, cy + 1,
                             fill=stroke, width=2, joinstyle=tk.MITER)
            self.create_line(cx - 6, cy + 1, cx - 6, cy + 5, cx + 6, cy + 5, cx + 6, cy + 1,
                             fill=color, width=1.2, joinstyle=tk.MITER)

    def set_state(self, state: str, color: str):
        """Set icon state: 'idle', 'recording', 'transcribing', 'typing', 'loading'."""
        self._state = state
        self._color = color
        self._stop_pulse()

        if state == "idle":
            self._draw_mic(color)
        elif state == "recording":
            self._pulse_frame = 0
            self._pulse_mic_breathe()
        elif state == "transcribing":
            self._pulse_frame = 0
            self._pulse_dots()
        elif state == "typing":
            self._draw_send(color)
        elif state == "loading":
            self._draw_mic(color)

    def _pulse_mic_breathe(self):
        """Breathe the mic icon in the recording color."""
        import math
        if self._state != "recording":
            return
        t = self._pulse_frame * 0.1
        brightness = 0.7 + 0.3 * (0.5 + 0.5 * math.sin(t))
        r, g, b = _hex_to_rgb(self._color)
        blended = _rgb_to_hex(int(r * brightness), int(g * brightness), int(b * brightness))
        self._draw_mic(blended)
        self._pulse_frame += 1
        self._pulse_id = self.after(50, self._pulse_mic_breathe)

    def _pulse_dots(self):
        """Animate the transcribing dots smoothly."""
        if self._state != "transcribing":
            return
        self._draw_dots(self._color, self._pulse_frame)
        self._pulse_frame += 1
        self._pulse_id = self.after(50, self._pulse_dots)


    def _stop_pulse(self):
        if self._pulse_id:
            self.after_cancel(self._pulse_id)
            self._pulse_id = None

    def _on_enter(self, e=None):
        if not self._disabled:
            self.configure(cursor="arrow")
            self._hover = True
            if self._state == "idle":
                from config import COLOR_RED
                self._draw_mic(COLOR_RED)

    def _on_leave(self, e=None):
        self.configure(cursor="")
        self._hover = False
        if self._state == "idle":
            self._draw_mic(self._color)

    def _on_click(self, e=None):
        if not self._disabled and self._command:
            self._command()

    def set_disabled(self, disabled: bool):
        self._disabled = disabled


class VadToggle(tk.Canvas):
    """Animated VAD toggle icon — sound bars / equalizer style.

    OFF: 5 vertical bars at resting heights, gray.
    ON:  Bars animate up and down like an equalizer, green.
    """

    WIDTH = 28
    HEIGHT = 30
    _ANIM_MS = 7  # ms between animation frames (~144fps smooth)
    _NUM_BARS = 5
    _BAR_W = 3
    _BAR_GAP = 2
    # Resting bar heights — asymmetrical, stylized
    _REST_HEIGHTS = [4, 9, 16, 7, 11]
    # Animation patterns — organic, uneven movement
    _ANIM_PATTERNS = [
        [5, 14, 8, 16, 6],
        [10, 6, 16, 4, 14],
        [4, 16, 5, 12, 8],
        [14, 4, 11, 16, 5],
        [7, 12, 4, 8, 16],
        [16, 7, 14, 5, 4],
        [8, 16, 6, 14, 10],
        [5, 8, 16, 10, 7],
    ]

    def __init__(self, parent, command=None, bg: str = "#0e0e1a",
                 off_color: str = "#4a4a6a", on_color: str = "#40d060", **kwargs):
        super().__init__(
            parent, width=self.WIDTH, height=self.HEIGHT,
            bg=bg, highlightthickness=0, **kwargs,
        )
        self._command = command
        self._bg = bg
        self._off_color = off_color
        self._on_color = on_color
        self._active = False
        self._recording = False
        self._loading = False
        self._anim_frame = 0
        self._anim_id: str | None = None
        self._last_heights: list[int] | None = None
        self._hover = False
        self._photo = None  # PIL anti-aliased render reference

        self._draw_off()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_click)

    def _draw_bars(self, heights: list[int], color: str):
        """Draw vertical bars with stroke outlines, anti-aliased."""
        stroke = _lighten(color, 40)
        if _HAS_PIL:
            def _draw(d, S):
                total_w = self._NUM_BARS * self._BAR_W + (self._NUM_BARS - 1) * self._BAR_GAP
                start_x = (self.WIDTH - total_w) // 2
                cy = self.HEIGHT // 2
                w = max(1, S)
                for i, h in enumerate(heights):
                    x = (start_x + i * (self._BAR_W + self._BAR_GAP)) * S
                    y1 = (cy - h // 2) * S
                    y2 = (cy + h // 2) * S
                    bw = self._BAR_W * S
                    d.rectangle([x, y1, x + bw, y2], fill=color, outline=stroke, width=w)
            _aa_icon(self, self.WIDTH, self.HEIGHT, _draw)
        else:
            self.delete("all")
            total_w = self._NUM_BARS * self._BAR_W + (self._NUM_BARS - 1) * self._BAR_GAP
            start_x = (self.WIDTH - total_w) // 2
            cy = self.HEIGHT // 2
            for i, h in enumerate(heights):
                x = start_x + i * (self._BAR_W + self._BAR_GAP)
                y1 = cy - h // 2
                y2 = cy + h // 2
                self.create_rectangle(x, y1, x + self._BAR_W, y2, fill=color, outline=stroke, width=1)

    def _draw_off(self):
        """Draw static resting bars — active color on hover."""
        if self._hover:
            color = self._on_color
        else:
            color = self._off_color
        self._draw_bars(self._REST_HEIGHTS, color)

    def _draw_on(self, frame: int):
        """Draw animated equalizer bars."""
        pattern = self._ANIM_PATTERNS[frame % len(self._ANIM_PATTERNS)]
        self._draw_bars(pattern, self._on_color)

    def _blend(self, bg_hex: str, fg_hex: str, alpha: float) -> str:
        """Blend fg over bg by alpha."""
        br, bg_, bb = _hex_to_rgb(bg_hex)
        fr, fg_, fb = _hex_to_rgb(fg_hex)
        return _rgb_to_hex(
            int(br + (fr - br) * alpha),
            int(bg_ + (fg_ - bg_) * alpha),
            int(bb + (fb - bb) * alpha),
        )

    def _on_enter(self, e=None):
        if self._loading:
            return
        self._hover = True
        self.configure(cursor="arrow")
        if not self._active:
            self._draw_off()
        elif not self._recording:
            self._draw_bars(self._REST_HEIGHTS, _lighten(self._on_color, 30))

    def _on_leave(self, e=None):
        if self._loading:
            return
        self._hover = False
        self.configure(cursor="")
        if not self._active:
            self._draw_off()
        elif not self._recording:
            self._draw_bars(self._REST_HEIGHTS, self._on_color)

    def _on_click(self, e=None):
        if self._loading:
            return
        if self._command:
            self._command()

    def set_active(self, active: bool):
        """Turn VAD on/off — flash then settle."""
        self._active = active
        self._recording = False
        self._stop_anim()
        if active:
            # Flash bright on activation
            self._draw_bars(self._REST_HEIGHTS, _lighten(self._on_color, 50))
            self.after(120, lambda: self._draw_bars(self._REST_HEIGHTS, self._on_color)
                       if self._active and not self._recording else None)
        else:
            # Flash dim on deactivation
            self._draw_bars(self._REST_HEIGHTS, _darken(self._off_color, 20))
            self.after(120, lambda: self._draw_off()
                       if not self._active else None)

    _FADE_STEPS = 20  # ~140ms at 7ms/frame

    def set_recording(self, recording: bool):
        """Start/stop the equalizer animation (when speech detected)."""
        self._recording = recording
        self._stop_anim()  # always stop existing animation first
        if recording and self._active:
            self._anim_frame = 0
            self._animate()
        else:
            # Fade out from current heights to resting
            if self._active and hasattr(self, '_last_heights') and self._last_heights:
                self._fade_from = list(self._last_heights)
                self._fade_step = 0
                self._fade_out()
            elif self._active:
                self._draw_bars(self._REST_HEIGHTS, self._on_color)
            else:
                self._draw_off()

    def _fade_out(self):
        """Smoothly lerp bar heights from current to resting."""
        if self._recording:
            return  # new recording started, abort fade
        t = self._fade_step / self._FADE_STEPS
        # Ease-out curve
        t = 1 - (1 - t) ** 2
        heights = []
        for i in range(self._NUM_BARS):
            h = int(self._fade_from[i] + (self._REST_HEIGHTS[i] - self._fade_from[i]) * t)
            heights.append(h)
        self._draw_bars(heights, self._on_color)
        self._fade_step += 1
        if self._fade_step <= self._FADE_STEPS:
            self._anim_id = self.after(self._ANIM_MS, self._fade_out)
        else:
            self._last_heights = None

    def set_color(self, color: str):
        """Change the active color (e.g. blue for transcribing)."""
        self._on_color = color
        if self._active and not self._recording:
            self._draw_bars(self._REST_HEIGHTS, color)

    def set_loading(self, loading: bool, dim_color: str | None = None):
        """Show static dim bars while loading, normal bars when done."""
        self._loading = loading
        self._stop_anim()
        if loading:
            self._draw_bars(self._REST_HEIGHTS, dim_color or "#2a2a3a")
        else:
            self._draw_off()

    def _stop_anim(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    # Per-bar oscillation params for organic, asymmetrical movement
    _BAR_FREQS = [0.08, 0.11, 0.06, 0.09, 0.13]
    _BAR_PHASES = [0.0, 2.1, 0.7, 3.5, 1.3]
    _BAR_AMPS = [7, 9, 6, 8, 7]
    _BAR_BASES = [4, 3, 5, 4, 3]

    def _animate(self):
        """Randomized sine-wave animation — organic with jitter."""
        import math, random
        if not self._recording:
            return

        heights = []
        t = self._anim_frame
        for i in range(self._NUM_BARS):
            f = self._BAR_FREQS[i]
            p = self._BAR_PHASES[i]
            primary = math.sin(t * f + p)
            h2 = math.sin(t * f * 1.7 + p * 0.5) * 0.3
            h3 = math.sin(t * f * 2.9 + p * 1.3) * 0.15
            jitter = random.uniform(-0.15, 0.15)
            combined = (primary + h2 + h3 + jitter) / 1.45
            h = int(self._BAR_BASES[i] + self._BAR_AMPS[i] * (0.5 + 0.5 * combined))
            heights.append(h)
        self._last_heights = heights
        self._draw_bars(heights, self._on_color)
        self._anim_frame += 1
        self._anim_id = self.after(self._ANIM_MS, self._animate)

