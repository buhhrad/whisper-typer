"""Cross-platform abstraction — base interface.

Each platform backend implements this ABC. Features that aren't available
on a given OS return sensible defaults or no-ops so the app degrades
gracefully instead of crashing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PlatformBackend(ABC):
    """Abstract interface for OS-specific functionality."""

    # ── identity ────────────────────────────────────────────────────
    @property
    @abstractmethod
    def name(self) -> str:
        """'windows', 'macos', or 'linux'."""
        ...

    # ── capability flags ────────────────────────────────────────────
    @property
    def supports_window_snapping(self) -> bool:
        return False

    @property
    def supports_rounded_corners(self) -> bool:
        return False

    @property
    def supports_transparency(self) -> bool:
        return False

    @property
    def supports_terminal_finding(self) -> bool:
        return False

    @property
    def snap_poll_interval_ms(self) -> int:
        """How often to poll the snap target's position (ms)."""
        return 100

    # ── clipboard ───────────────────────────────────────────────────
    @abstractmethod
    def set_clipboard(self, text: str) -> bool:
        """Copy *text* to the system clipboard. Returns success."""
        ...

    # ── terminal discovery ──────────────────────────────────────────
    def get_terminal_window_classes(self) -> list[str]:
        """Window class names used to identify terminal windows."""
        return []

    def get_terminal_title_hints(self) -> list[str]:
        """Title substrings to prefer when multiple terminals exist."""
        return []

    @abstractmethod
    def find_terminal_window(
        self,
        title_hints: list[str] | None = None,
        title_exclude: list[str] | None = None,
    ) -> Any | None:
        """Return a handle/id for a terminal window, or None."""
        ...

    def find_all_terminal_windows(
        self,
        title_exclude: list[str] | None = None,
    ) -> list[tuple[Any, str]]:
        """Return all visible terminal windows as [(handle, title), ...].

        Used by the terminal selector UI when multiple terminals are open.
        """
        return []

    # ── focus management ────────────────────────────────────────────
    @abstractmethod
    def get_foreground_window(self) -> Any | None:
        """Return a handle/id for the currently focused window."""
        ...

    @abstractmethod
    def set_foreground_window(self, handle: Any) -> bool:
        """Bring *handle* to the foreground. Returns success."""
        ...

    # ── paste key ───────────────────────────────────────────────────
    def get_paste_modifier(self):
        """Return the pynput Key for paste (Ctrl on Win/Linux, Cmd on macOS)."""
        from pynput.keyboard import Key
        return Key.ctrl

    # ── window styles ───────────────────────────────────────────────
    @abstractmethod
    def apply_tool_window_style(self, tk_root) -> None:
        """Make a tkinter root behave as a tool window (no taskbar, no
        activate, topmost).  No-op on unsupported platforms."""
        ...

    @abstractmethod
    def set_rounded_corners(self, tk_root, radius: int, enable: bool) -> None:
        """Apply or clear rounded corners on a tkinter root."""
        ...

    @abstractmethod
    def setup_transparency(self, tk_root, transparent: bool) -> None:
        """Configure window transparency appropriate for this platform."""
        ...

    # ── screen geometry ─────────────────────────────────────────────
    @abstractmethod
    def get_virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height) of the full virtual desktop."""
        ...

    def get_monitor_rect_for_window(self, handle: Any) -> tuple[int, int, int, int] | None:
        """Return (x, y, width, height) of the monitor containing *handle*.

        Falls back to virtual screen bounds if not implemented.
        """
        return None

    # ── window snapping ─────────────────────────────────────────────
    def get_tk_hwnd(self, tk_root) -> Any | None:
        """Extract a native window handle from a tkinter root."""
        return None

    @abstractmethod
    def get_window_rect(self, handle: Any) -> tuple[int, int, int, int] | None:
        """Return (left, top, right, bottom) for *handle*, or None."""
        ...

    @abstractmethod
    def is_window_valid(self, handle: Any) -> bool:
        """Check whether *handle* still refers to a live window."""
        ...

    @abstractmethod
    def is_window_minimized(self, handle: Any) -> bool:
        """Check whether *handle* is minimized/iconified."""
        ...

    @abstractmethod
    def set_window_position(self, tk_hwnd: Any, x: int, y: int) -> None:
        """Move a window to (x, y) without resizing or re-ordering."""
        ...

    # ── subprocess helpers ──────────────────────────────────────────
    @property
    def subprocess_no_window_flags(self) -> int:
        """Creation flags for subprocess to suppress console windows."""
        return 0

    # ── console / ANSI ──────────────────────────────────────────────
    def enable_ansi_console(self) -> None:
        """Enable ANSI escape-code support if needed (Windows-only)."""
        pass

    # ── fonts ───────────────────────────────────────────────────────
    @abstractmethod
    def get_ui_font(self) -> str:
        """Return the preferred proportional UI font name."""
        ...

    @abstractmethod
    def get_mono_font(self) -> str:
        """Return the preferred monospace font name."""
        ...
