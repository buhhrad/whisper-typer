"""Custom styled widgets for Whisper Typer.

Canvas-based rounded buttons and dropdown menus that look modern
on the dark theme instead of default tkinter/ttk widgets.
"""

from __future__ import annotations

import math
import random
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageTk
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
        font: tuple | None = None,
        padx: int = 16,
        pady: int = 6,
        radius: int = 12,
        command=None,
        **kwargs,
    ):
        if font is None:
            from compat import backend
            font = (backend.get_ui_font(), 9, "bold")
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
        font: tuple | None = None,
        on_change=None,
        **kwargs,
    ):
        if font is None:
            from compat import backend
            font = (backend.get_ui_font(), 8)
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
        self._muted = False
        self._pulse_id: str | None = None
        self._pulse_frame = 0
        self._photo = None  # PIL anti-aliased render reference
        self._mic_base_img: Image.Image | None = None  # cached for brightness pulse
        self._mic_base_color: str | None = None
        self._mic_base_bg: str | None = None

        self._draw_mic(self._color)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_click)

    def _draw_mic(self, color: str, _brightness: float | None = None, solid: bool = False):
        """Draw a microphone icon with stroke outline, anti-aliased.

        solid=False: outline only (no capsule fill) — used for idle/hover.
        solid=True:  filled capsule — used for recording.
        """
        bg_hex = self.cget("bg")

        # Fast path: brightness adjustment on cached RGBA icon layer
        if (_brightness is not None and _HAS_PIL
                and self._mic_base_img is not None
                and self._mic_base_color == color
                and self._mic_base_bg == bg_hex):
            adjusted = ImageEnhance.Brightness(self._mic_base_img).enhance(_brightness)
            r, g, b = _hex_to_rgb(bg_hex)
            bg_img = Image.new("RGBA", (self.SIZE, self.SIZE), (r, g, b, 255))
            if bg_hex.lower() == "#010101":
                alpha = adjusted.split()[3]
                mask = alpha.point(lambda a: 255 if a > 100 else 0)
                bg_img.paste(adjusted, (0, 0), mask)
            else:
                bg_img.paste(adjusted, (0, 0), adjusted)
            photo = ImageTk.PhotoImage(bg_img)
            self._photo = photo
            self.delete("all")
            self.create_image(self.SIZE // 2, self.SIZE // 2, image=photo)
            return

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
                if solid:
                    d.ellipse([cx - 2*S, cy - 7*S, cx + 2*S, cy + 1*S], fill=color)
            _aa_icon(self, self.SIZE, self.SIZE, _draw)
            self._mic_base_color = color
            self._mic_base_bg = bg_hex
            S = _SUPERSAMPLE
            img = Image.new("RGBA", (self.SIZE * S, self.SIZE * S), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            _draw(d, S)
            self._mic_base_img = img.resize((self.SIZE, self.SIZE), Image.LANCZOS)
        else:
            self.delete("all")
            cx, cy = self.SIZE // 2, self.SIZE // 2
            self.create_oval(cx - 3, cy - 8, cx + 3, cy + 2, fill=color if solid else "", outline=stroke, width=1.5)
            self.create_arc(cx - 6, cy - 4, cx + 6, cy + 5,
                            start=180, extent=180, style="arc", outline=stroke, width=1.5)
            self.create_line(cx, cy + 5, cx, cy + 9, fill=stroke, width=1.5)
            self.create_line(cx - 3, cy + 9, cx + 3, cy + 9, fill=stroke, width=1.5)
            if solid:
                self.create_oval(cx - 2, cy - 7, cx + 2, cy + 1, fill=color, outline="")

    def _draw_mic_muted(self, color: str):
        """Draw mic icon with a diagonal slash indicating mute."""
        stroke = _lighten(color, 40)
        slash_color = "#e84040"  # red slash
        if _HAS_PIL:
            def _draw(d, S):
                cx, cy = self.SIZE * S // 2, self.SIZE * S // 2
                w = max(1, round(1.5 * S))
                # Draw the mic outline (dimmed)
                d.ellipse([cx - 3*S, cy - 8*S, cx + 3*S, cy + 2*S], outline=stroke, width=w)
                d.arc([cx - 6*S, cy - 4*S, cx + 6*S, cy + 5*S],
                      start=0, end=180, fill=stroke, width=w)
                d.line([(cx, cy + 5*S), (cx, cy + 9*S)], fill=stroke, width=w)
                d.line([(cx - 3*S, cy + 9*S), (cx + 3*S, cy + 9*S)], fill=stroke, width=w)
                # Diagonal slash (bottom-left to top-right)
                sw = max(2, round(2 * S))
                d.line([(cx - 7*S, cy + 7*S), (cx + 7*S, cy - 7*S)],
                       fill=slash_color, width=sw)
            _aa_icon(self, self.SIZE, self.SIZE, _draw)
            self._mic_base_img = None  # don't cache muted state
        else:
            self.delete("all")
            cx, cy = self.SIZE // 2, self.SIZE // 2
            self.create_oval(cx - 3, cy - 8, cx + 3, cy + 2, fill="", outline=stroke, width=1.5)
            self.create_arc(cx - 6, cy - 4, cx + 6, cy + 5,
                            start=180, extent=180, style="arc", outline=stroke, width=1.5)
            self.create_line(cx, cy + 5, cx, cy + 9, fill=stroke, width=1.5)
            self.create_line(cx - 3, cy + 9, cx + 3, cy + 9, fill=stroke, width=1.5)
            self.create_line(cx - 7, cy + 7, cx + 7, cy - 7, fill=slash_color, width=2)

    def set_muted(self, muted: bool):
        """Toggle mute state — draws slash over mic."""
        self._muted = muted
        self._stop_pulse()
        self._mic_base_img = None
        if muted:
            self._state = "muted"
            self._draw_mic_muted(self._color)
        else:
            self._state = "idle"
            self._draw_mic(self._color, solid=False)

    def _draw_dots(self, color: str, frame: int):
        """Draw animated transcribing dots with stroke outlines, anti-aliased."""
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
                d.line([(cx, cy + 2*S), (cx, cy - 5*S)], fill=stroke, width=max(1, round(2*S)))
                d.line([(cx, cy + 2*S), (cx, cy - 5*S)], fill=color, width=w)
                d.line([(cx - 3*S, cy - 2*S), (cx, cy - 5*S)], fill=stroke, width=max(1, round(2*S)))
                d.line([(cx + 3*S, cy - 2*S), (cx, cy - 5*S)], fill=stroke, width=max(1, round(2*S)))
                d.line([(cx - 3*S, cy - 2*S), (cx, cy - 5*S)], fill=color, width=w)
                d.line([(cx + 3*S, cy - 2*S), (cx, cy - 5*S)], fill=color, width=w)
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
            self.create_line(cx, cy + 2, cx, cy - 5, fill=stroke, width=2)
            self.create_line(cx - 3, cy - 2, cx, cy - 5, fill=stroke, width=2)
            self.create_line(cx + 3, cy - 2, cx, cy - 5, fill=stroke, width=2)
            self.create_line(cx, cy + 2, cx, cy - 5, fill=color, width=1.2)
            self.create_line(cx - 3, cy - 2, cx, cy - 5, fill=color, width=1.2)
            self.create_line(cx + 3, cy - 2, cx, cy - 5, fill=color, width=1.2)
            self.create_line(cx - 6, cy + 1, cx - 6, cy + 5, cx + 6, cy + 5, cx + 6, cy + 1,
                             fill=stroke, width=2, joinstyle=tk.MITER)
            self.create_line(cx - 6, cy + 1, cx - 6, cy + 5, cx + 6, cy + 5, cx + 6, cy + 1,
                             fill=color, width=1.2, joinstyle=tk.MITER)

    def set_state(self, state: str, color: str):
        """Set icon state: 'idle', 'recording', 'transcribing', 'typing', 'loading'."""
        self._state = state
        self._color = color
        self._stop_pulse()
        self._mic_base_img = None  # invalidate brightness cache

        if state == "idle":
            self._fade_to_idle_step = 0
            self._fade_to_idle()
        elif state == "recording":
            self._draw_mic(color, solid=True)
            self._pulse_frame = 0
            self._pulse_mic_breathe()
        elif state == "transcribing":
            self._pulse_frame = 0
            self._pulse_dots()
        elif state == "typing":
            self._draw_send(color)
        elif state == "loading":
            self._draw_mic(color, solid=False)

    _FADE_IDLE_STEPS = 6  # ~240ms fade

    def _fade_to_idle(self):
        """Smooth brightness fade-down to idle outline mic."""
        if self._state != "idle":
            return
        t = self._fade_to_idle_step / self._FADE_IDLE_STEPS
        t = 1 - (1 - t) ** 2  # ease-out
        brightness = 1.0 - t * 0.6  # 1.0 → 0.4
        self._draw_mic(self._color, _brightness=brightness, solid=False)
        self._fade_to_idle_step += 1
        if self._fade_to_idle_step <= self._FADE_IDLE_STEPS:
            self._pulse_id = self.after(40, self._fade_to_idle)
        else:
            self._mic_base_img = None
            self._draw_mic(self._color, solid=False)

    def _pulse_mic_breathe(self):
        """Pulse the solid mic icon — gentle brightness breathing."""
        if self._state != "recording":
            return
        t = self._pulse_frame * 0.1
        brightness = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t))  # 0.6 – 1.0
        self._draw_mic(self._color, _brightness=brightness, solid=True)
        self._pulse_frame += 1
        self._pulse_id = self.after(40, self._pulse_mic_breathe)

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
                self._draw_mic(COLOR_RED, solid=False)  # brighter outline on hover

    def _on_leave(self, e=None):
        self.configure(cursor="")
        self._hover = False
        if self._state == "idle":
            self._draw_mic(self._color, solid=False)  # dim outline

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

    WIDTH = 32
    HEIGHT = 30
    _ANIM_MS = 16  # ms between animation frames (~60fps)
    _NUM_BARS = 5
    _BAR_W = 3
    _BAR_GAP = 2
    # Resting bar heights — asymmetrical, stylized
    _REST_HEIGHTS = [4, 9, 16, 7, 11]

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
        self._processing = False
        self._loading = False
        self._anim_frame = 0
        self._anim_id: str | None = None
        self._last_heights: list[int] | None = None
        # Unified animation intensity: 0.0 = static rest, 0.3 = processing, 1.0 = recording
        self._intensity = 0.0
        self._target_intensity = 0.0
        self._hover = False
        self._photo = None  # PIL anti-aliased render reference
        self._bars_cache: dict[tuple, ImageTk.PhotoImage] = {}  # static frame cache

        self._draw_off()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_click)

    def _draw_bars(self, heights: list[int], color: str, fast: bool = False, solid: bool = True):
        """Draw vertical bars. solid=False draws outline-only bars.

        Uses consistent 1x render for all frames to prevent thickness shifts
        between animated and static states. Caches static frames.
        """
        stroke = _lighten(color, 40)
        fill = color if solid else ""
        if _HAS_PIL:
            bg_hex = self.cget("bg")
            cache_key = (tuple(heights), color, bg_hex, solid)

            # Check cache for static frames (hover, toggle, loading)
            if not fast:
                cached = self._bars_cache.get(cache_key)
                if cached is not None:
                    self._photo = cached
                    self.delete("all")
                    self.create_image(self.WIDTH // 2, self.HEIGHT // 2, image=cached)
                    return

            pil_fill = _hex_to_rgb(color) + (255,) if solid else None

            # Consistent 1x render for all frames (no thickness shift)
            img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            total_w = self._NUM_BARS * self._BAR_W + (self._NUM_BARS - 1) * self._BAR_GAP
            start_x = (self.WIDTH - total_w) // 2
            cy = self.HEIGHT // 2
            for i, h in enumerate(heights):
                x = start_x + i * (self._BAR_W + self._BAR_GAP)
                y1 = cy - h // 2
                y2 = cy + h // 2
                d.rectangle([x, y1, x + self._BAR_W, y2], fill=pil_fill, outline=stroke, width=1)
            r, g, b = _hex_to_rgb(bg_hex)
            bg_img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (r, g, b, 255))
            if bg_hex.lower() == "#010101":
                alpha = img.split()[3]
                mask = alpha.point(lambda a: 255 if a > 100 else 0)
                bg_img.paste(img, (0, 0), mask)
            else:
                bg_img.paste(img, (0, 0), img)
            photo = ImageTk.PhotoImage(bg_img)
            self._photo = photo
            self.delete("all")
            self.create_image(self.WIDTH // 2, self.HEIGHT // 2, image=photo)

            # Cache static frames (limit 16)
            if not fast and len(self._bars_cache) < 16:
                self._bars_cache[cache_key] = self._photo
        else:
            self.delete("all")
            total_w = self._NUM_BARS * self._BAR_W + (self._NUM_BARS - 1) * self._BAR_GAP
            start_x = (self.WIDTH - total_w) // 2
            cy = self.HEIGHT // 2
            for i, h in enumerate(heights):
                x = start_x + i * (self._BAR_W + self._BAR_GAP)
                y1 = cy - h // 2
                y2 = cy + h // 2
                self.create_rectangle(x, y1, x + self._BAR_W, y2, fill=fill, outline=stroke, width=1)

    def _draw_off(self):
        """Draw static resting bars — dim color, bright on hover."""
        if self._hover:
            color = self._on_color
        else:
            color = self._off_color
        self._draw_bars(self._REST_HEIGHTS, color, solid=True)

    def _on_enter(self, e=None):
        if self._loading:
            return
        self._hover = True
        self.configure(cursor="arrow")
        if not self._active:
            self._draw_off()
        elif not self._recording and not self._processing and self._anim_id is None:
            self._draw_bars(self._REST_HEIGHTS, _lighten(self._on_color, 30), solid=True)

    def _on_leave(self, e=None):
        if self._loading:
            return
        self._hover = False
        self.configure(cursor="")
        if not self._active:
            self._draw_off()
        elif not self._recording and not self._processing and self._anim_id is None:
            self._draw_bars(self._REST_HEIGHTS, self._on_color, solid=True)

    def _on_click(self, e=None):
        if self._loading:
            return
        if self._command:
            self._command()

    _POP_STEPS = 6  # ~96ms at 16ms/frame
    _POP_PEAK_H = 24  # max bar height during pop

    def set_active(self, active: bool):
        """Turn VAD on/off."""
        self._active = active
        self._recording = False
        self._processing = False
        self._stop_anim()
        if active:
            # Static rest bars — no animation while just listening
            self._intensity = 0.0
            self._target_intensity = 0.0
            self._draw_bars(self._REST_HEIGHTS, self._on_color, solid=True)
        else:
            self._intensity = 0.0
            self._target_intensity = 0.0
            self._pop_step = 0
            self._pop_deactivate()

    def _pop_activate(self):
        """Cascade-pop: bars shoot up staggered left-to-right, then settle."""
        if not self._active or self._recording:
            return
        t = self._pop_step / self._POP_STEPS
        heights = []
        for i in range(self._NUM_BARS):
            # Stagger: each bar starts slightly later
            bar_t = max(0.0, min(1.0, (t - i * 0.08) / 0.7))
            # Overshoot bounce
            if bar_t < 0.5:
                h = self._REST_HEIGHTS[i] + (self._POP_PEAK_H - self._REST_HEIGHTS[i]) * (bar_t * 2)
            else:
                h = self._POP_PEAK_H + (self._REST_HEIGHTS[i] - self._POP_PEAK_H) * ((bar_t - 0.5) * 2)
            heights.append(int(h))
        self._draw_bars(heights, self._on_color, fast=True, solid=True)
        self._pop_step += 1
        if self._pop_step <= self._POP_STEPS:
            self._anim_id = self.after(self._ANIM_MS, self._pop_activate)
        else:
            self._anim_id = None
            # Transition into gentle listening animation
            self._target_intensity = 0.15
            self._animate_unified()

    def _pop_deactivate(self):
        """Bars shrink down then settle to outline resting."""
        if self._active:
            return
        t = self._pop_step / self._POP_STEPS
        # Ease-out: bars shrink from current to smaller, then back to rest
        heights = []
        for i in range(self._NUM_BARS):
            bar_t = max(0.0, min(1.0, (t - i * 0.06) / 0.7))
            if bar_t < 0.4:
                h = self._REST_HEIGHTS[i] * (1.0 - bar_t * 1.5)  # shrink
            else:
                shrunk = self._REST_HEIGHTS[i] * 0.4
                h = shrunk + (self._REST_HEIGHTS[i] - shrunk) * ((bar_t - 0.4) / 0.6)  # recover
            heights.append(max(2, int(h)))
        self._draw_bars(heights, self._off_color, fast=True, solid=True)
        self._pop_step += 1
        if self._pop_step <= self._POP_STEPS:
            self._anim_id = self.after(self._ANIM_MS, self._pop_deactivate)
        else:
            self._anim_id = None
            self._draw_off()

    # Intensity lerp speed — how fast intensity transitions per frame
    _LERP_SPEED = 0.12  # smooth ~10-frame blend

    _LISTEN_INTENSITY = 0.15  # gentle breathing when VAD is listening

    def set_recording(self, recording: bool):
        """Start/stop the equalizer animation (when speech detected)."""
        self._recording = recording
        if recording:
            self._processing = False
            self._target_intensity = 1.0
        elif self._processing and self._active:
            self._target_intensity = 0.3
        elif self._active:
            self._target_intensity = 0.0
        else:
            self._target_intensity = 0.0
        self._stop_anim()
        self._animate_unified()

    def set_processing(self, processing: bool):
        """Start/stop gentle processing animation (transcribing/typing)."""
        self._processing = processing
        self._recording = False
        if processing and self._active:
            self._target_intensity = 0.3
        elif self._active:
            self._target_intensity = 0.0
        else:
            self._target_intensity = 0.0
        self._stop_anim()
        self._animate_unified()

    def set_color(self, color: str):
        """Change the active color — takes effect on next animation frame."""
        self._on_color = color

    def _animate_unified(self):
        """Single animation loop — smoothly blends between intensity levels.

        intensity 0.0 = static rest, 0.3 = gentle processing, 1.0 = energetic recording.
        Lerps toward _target_intensity each frame for seamless transitions.
        """
        # Lerp intensity toward target
        diff = self._target_intensity - self._intensity
        if abs(diff) < 0.01:
            self._intensity = self._target_intensity
        else:
            self._intensity += diff * self._LERP_SPEED

        # If fully at rest and target is rest, stop the loop
        if self._intensity <= 0.005 and self._target_intensity <= 0.0:
            self._intensity = 0.0
            self._anim_id = None
            self._last_heights = None
            if self._active:
                self._draw_bars(self._REST_HEIGHTS, self._on_color, solid=True)
            else:
                self._draw_off()
            return

        # Calculate heights based on current intensity
        heights = self._calc_blended_heights(self._anim_frame, self._intensity)
        self._last_heights = heights
        self._draw_bars(heights, self._on_color, fast=True, solid=True)
        self._anim_frame += 1
        self._anim_id = self.after(self._ANIM_MS, self._animate_unified)

    _MAX_BAR_H = max(_REST_HEIGHTS)  # 16 — hard ceiling for all animations

    def _calc_blended_heights(self, t: int, intensity: float) -> list[int]:
        """Calculate bar heights blended by intensity.

        At intensity 0 = rest heights, at 1.0 = full recording animation.
        Bars oscillate both above and below rest position but never exceed
        the tallest idle bar (_MAX_BAR_H). Uses layered sine waves with
        heavy randomness for organic movement.
        """
        heights = []
        for i in range(self._NUM_BARS):
            f = self._BAR_FREQS[i]
            p = self._BAR_PHASES[i]
            # Multiple sine layers at different frequencies
            primary = math.sin(t * f + p)
            h2 = math.sin(t * f * 1.7 + p * 0.5) * 0.35
            h3 = math.sin(t * f * 2.9 + p * 1.3) * 0.2
            h4 = math.sin(t * f * 0.3 + p * 2.7) * 0.25  # slow drift
            # Subtle random jitter — organic variation without flickering
            jitter = random.uniform(-0.12, 0.12) * intensity
            combined = (primary + h2 + h3 + h4 + jitter) / 1.8
            # Amplitude scales with intensity — oscillates both directions
            amp = self._BAR_AMPS[i] * intensity
            h = int(self._REST_HEIGHTS[i] + amp * combined)
            heights.append(max(2, min(self._MAX_BAR_H, h)))
        return heights

    def set_loading(self, loading: bool, dim_color: str | None = None):
        """Show static dim bars while loading, normal bars when done."""
        self._loading = loading
        self._stop_anim()
        if loading:
            self._draw_bars(self._REST_HEIGHTS, dim_color or "#2a2a3a", solid=True)
        else:
            self._draw_off()

    def _stop_anim(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    # Per-bar oscillation params for organic, asymmetrical movement
    _BAR_FREQS = [0.08, 0.11, 0.06, 0.09, 0.13]
    _BAR_PHASES = [0.0, 2.1, 0.7, 3.5, 1.3]
    # Proportional to headroom — bars stay within idle silhouette (max 16px)
    _BAR_AMPS = [3, 6, 4, 5, 4]

class LoadingBar(tk.Canvas):
    """Indeterminate loading bar — rounded pill shape, sliding highlight."""

    WIDTH = 56
    HEIGHT = 30
    _BAR_H = 4
    _BAR_R = 2  # pill radius
    _HIGHLIGHT_W = 18
    _TRACK_PAD = 4  # padding from canvas edge to track

    def __init__(self, parent, bg: str = "#0e0e1a",
                 color: str = "#e0a820", track_color: str = "#1a1a2a", **kwargs):
        super().__init__(
            parent, width=self.WIDTH, height=self.HEIGHT,
            bg=bg, highlightthickness=0, **kwargs,
        )
        self._color = color
        self._track_color = track_color
        self._frame = 0
        self._anim_id: str | None = None
        self._photo = None
        self._start()

    def _start(self):
        self._frame = 0
        self._render()

    def _render(self):
        # Ping-pong position with smooth easing
        cycle = 80
        t = (self._frame % cycle) / cycle
        if t > 0.5:
            t = 1 - t
        t *= 2
        t = t * t * (3 - 2 * t)  # smoothstep

        track_l = self._TRACK_PAD
        track_r = self.WIDTH - self._TRACK_PAD
        track_w = track_r - track_l
        hl_x = track_l + t * (track_w - self._HIGHLIGHT_W)

        cy = self.HEIGHT // 2
        bar_t = cy - self._BAR_H // 2
        bar_b = cy + self._BAR_H // 2

        bg_hex = self.cget("bg")
        r, g, b = _hex_to_rgb(bg_hex)

        if _HAS_PIL:
            img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Track
            tr, tg, tb = _hex_to_rgb(self._track_color)
            draw.rounded_rectangle(
                [track_l, bar_t, track_r, bar_b],
                radius=self._BAR_R, fill=(tr, tg, tb),
            )
            # Highlight
            cr, cg, cb = _hex_to_rgb(self._color)
            draw.rounded_rectangle(
                [int(hl_x), bar_t, int(hl_x + self._HIGHLIGHT_W), bar_b],
                radius=self._BAR_R, fill=(cr, cg, cb),
            )

            # Composite onto background
            bg_img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (r, g, b, 255))
            if bg_hex.lower() == "#010101":
                alpha = img.split()[3]
                mask = alpha.point(lambda a: 255 if a > 100 else 0)
                bg_img.paste(img, (0, 0), mask)
            else:
                bg_img.paste(img, (0, 0), img)

            photo = ImageTk.PhotoImage(bg_img)
            self._photo = photo
            self.delete("all")
            self.create_image(self.WIDTH // 2, self.HEIGHT // 2, image=photo)
        else:
            self.delete("all")
            self.create_rectangle(
                track_l, bar_t, track_r, bar_b,
                fill=self._track_color, outline="",
            )
            self.create_rectangle(
                int(hl_x), bar_t, int(hl_x + self._HIGHLIGHT_W), bar_b,
                fill=self._color, outline="",
            )

        self._frame += 1
        self._anim_id = self.after(16, self._render)

    def stop(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None


class DurationBadge(tk.Canvas):
    """Rounded pill badge showing recording duration — 0:00 format.

    Renders via PIL for anti-aliased rounded rectangle + text.
    Hidden when not recording (draws only canvas bg).
    Animates width smoothly on show/hide for a polished pop-out effect.
    """

    WIDTH = 38
    HEIGHT = 18
    _PILL_R = 6
    _FONT_NAME = None  # resolved lazily from compat backend
    _FONT_SIZE = 9
    _ANIM_STEPS = 16  # ~256ms at 16ms/frame
    _ANIM_MS = 16

    def __init__(self, parent, bg: str = "#0e0e1a",
                 pill_color: str = "#1a1a2a", text_color: str = "#ff4444",
                 on_resize=None, **kwargs):
        super().__init__(
            parent, width=0, height=self.HEIGHT,
            bg=bg, highlightthickness=0, **kwargs,
        )
        if self._FONT_NAME is None:
            from compat import backend
            self.__class__._FONT_NAME = backend.get_mono_font()
        self._pill_color = pill_color
        self._text_color = text_color
        self._text = ""
        self._photo = None
        self._visible = False
        self._on_resize = on_resize  # callback to resize parent window
        self._anim_id: str | None = None
        self._anim_step = 0
        self._anim_expanding = True
        self._current_width = 0

    def set_time(self, text: str) -> None:
        """Update the displayed time (e.g. '0:05'). Pass '' to hide."""
        if text == self._text:
            return
        self._text = text
        self._visible = bool(text)
        if self._current_width == self.WIDTH:
            self._render()

    def show(self) -> None:
        """Start the expand animation."""
        self._visible = True
        self._stop_anim()
        self._anim_step = 0
        self._anim_expanding = True
        self._animate_width()

    def hide(self) -> None:
        """Start the collapse animation."""
        self._stop_anim()
        if self._current_width > 0:
            self._anim_step = 0
            self._anim_expanding = False
            self._animate_width()
        else:
            self._text = ""
            self._visible = False
            self.delete("all")

    def hide_immediate(self) -> None:
        """Instantly hide without animation."""
        self._stop_anim()
        self._text = ""
        self._visible = False
        self._current_width = 0
        self.configure(width=0)
        self.delete("all")

    def _stop_anim(self) -> None:
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _animate_width(self) -> None:
        t = self._anim_step / self._ANIM_STEPS
        if self._anim_expanding:
            # Ease-out: fast start, gentle settle
            t = 1 - (1 - t) ** 3
            w = int(self.WIDTH * t)
        else:
            # Ease-in: gentle start, fast close
            t = t * t * t
            w = int(self.WIDTH * (1 - t))

        self._current_width = max(0, min(self.WIDTH, w))
        self.configure(width=self._current_width)

        # Render content once wide enough to show text
        if self._anim_expanding and self._current_width >= self.WIDTH * 0.5:
            self._render()

        if self._on_resize:
            self._on_resize(skip_corners=True)  # skip rounded-corner update during animation

        self._anim_step += 1
        if self._anim_step <= self._ANIM_STEPS:
            self._anim_id = self.after(self._ANIM_MS, self._animate_width)
        else:
            # Animation complete
            if not self._anim_expanding:
                self._text = ""
                self._visible = False
                self._current_width = 0
                self.configure(width=0)
                self.delete("all")
            else:
                self._current_width = self.WIDTH
                self.configure(width=self.WIDTH)
                self._render()
            if self._on_resize:
                self._on_resize()  # final resize WITH rounded corners

    def _render(self) -> None:
        self.delete("all")
        if not self._visible or not _HAS_PIL:
            return

        render_w = max(self._current_width, 1)
        bg_hex = self.cget("bg")
        r, g, b = _hex_to_rgb(bg_hex)

        img = Image.new("RGBA", (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Rounded pill background
        pr, pg, pb = _hex_to_rgb(self._pill_color)
        draw.rounded_rectangle(
            [0, 1, self.WIDTH - 1, self.HEIGHT - 2],
            radius=self._PILL_R, fill=(pr, pg, pb),
        )

        # Timer text
        try:
            from PIL import ImageFont
            font = ImageFont.truetype(self._FONT_NAME, self._FONT_SIZE)
        except Exception:
            font = ImageFont.load_default()
        tr, tg, tb = _hex_to_rgb(self._text_color)
        bbox = draw.textbbox((0, 0), self._text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (self.WIDTH - tw) // 2
        ty = (self.HEIGHT - th) // 2 - 1
        draw.text((tx, ty), self._text, fill=(tr, tg, tb), font=font)

        # Crop to current animated width
        if render_w < self.WIDTH:
            img = img.crop((0, 0, render_w, self.HEIGHT))

        # Composite onto bg
        bg_img = Image.new("RGBA", (render_w, self.HEIGHT), (r, g, b, 255))
        if bg_hex.lower() == "#010101":
            alpha = img.split()[3]
            mask = alpha.point(lambda a: 255 if a > 100 else 0)
            bg_img.paste(img, (0, 0), mask)
        else:
            bg_img.paste(img, (0, 0), img)

        photo = ImageTk.PhotoImage(bg_img)
        self._photo = photo
        self.create_image(render_w // 2, self.HEIGHT // 2, image=photo)

