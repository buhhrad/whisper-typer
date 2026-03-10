"""Windows platform backend — Win32 API via ctypes.

Implements every abstract method from PlatformBackend using
ctypes.windll.user32, gdi32, and kernel32.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
from typing import Any

from .base import PlatformBackend

# ── Win32 type aliases ───────────────────────────────────────────────

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# ── Win32 constants ──────────────────────────────────────────────────

GWL_EXSTYLE = -20

WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FLAGS = SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE

VK_MENU = 0x12  # ALT key virtual-key code
KEYEVENTF_KEYUP = 0x0002

# ── EnumWindows callback type ────────────────────────────────────────

_WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL,
    ctypes.wintypes.HWND,
    ctypes.wintypes.LPARAM,
)

# ── RECT structure for GetWindowRect ─────────────────────────────────


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


# ── Terminal window classes & title hints ────────────────────────────

_TERMINAL_CLASSES = [
    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
    "ConsoleWindowClass",             # CMD / PowerShell classic
]

_TERMINAL_TITLE_HINTS = ["powershell", "cmd"]


# ═════════════════════════════════════════════════════════════════════
#  WindowsBackend
# ═════════════════════════════════════════════════════════════════════


class WindowsBackend(PlatformBackend):
    """Win32 implementation of the cross-platform interface."""

    # ── identity ─────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "windows"

    # ── capability flags ─────────────────────────────────────────────

    @property
    def supports_window_snapping(self) -> bool:
        return True

    @property
    def supports_rounded_corners(self) -> bool:
        return True

    @property
    def supports_transparency(self) -> bool:
        return True

    @property
    def supports_terminal_finding(self) -> bool:
        return True

    @property
    def snap_poll_interval_ms(self) -> int:
        return 1  # Windows can handle fast polling

    # ── clipboard ────────────────────────────────────────────────────

    def set_clipboard(self, text: str) -> bool:
        """Copy *text* to the system clipboard via clip.exe.

        Uses BOM + UTF-16LE encoding so clip.exe handles full Unicode.
        CREATE_NO_WINDOW prevents a console flash.
        """
        try:
            proc = subprocess.Popen(
                ["clip"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            # BOM + UTF-16LE — clip.exe needs BOM to interpret encoding
            proc.communicate(b"\xff\xfe" + text.encode("utf-16-le"))
            return proc.returncode == 0
        except Exception:
            return False

    # ── terminal discovery ───────────────────────────────────────────

    def get_terminal_window_classes(self) -> list[str]:
        return list(_TERMINAL_CLASSES)

    def get_terminal_title_hints(self) -> list[str]:
        return list(_TERMINAL_TITLE_HINTS)

    def find_terminal_window(
        self,
        title_hints: list[str] | None = None,
        title_exclude: list[str] | None = None,
    ) -> int | None:
        """Find a visible terminal window handle.

        Checks the foreground window first (fast path), then enumerates
        all top-level windows.  Skips windows whose title contains any
        string in *title_exclude*.  Prefers windows matching *title_hints*.
        """
        if title_hints is None:
            title_hints = _TERMINAL_TITLE_HINTS
        if title_exclude is None:
            title_exclude = []

        def _is_valid(hwnd: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return False
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value not in _TERMINAL_CLASSES:
                return False
            title_buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buf, 512)
            title_lower = title_buf.value.lower()
            for excl in title_exclude:
                if excl.lower() in title_lower:
                    return False
            return True

        # Fast path — check the foreground window first
        fg = user32.GetForegroundWindow()
        if fg and _is_valid(fg):
            return fg

        # Enumerate all visible terminals
        candidates: list[tuple[int, str]] = []

        def _enum_cb(hwnd: int, _lparam: int) -> bool:
            if not _is_valid(hwnd):
                return True
            title_buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buf, 512)
            candidates.append((hwnd, title_buf.value.lower()))
            return True

        user32.EnumWindows(_WNDENUMPROC(_enum_cb), 0)

        if not candidates:
            return None

        # Prefer windows whose title matches a hint
        for hint in title_hints:
            hint_lower = hint.lower()
            for hwnd, title in candidates:
                if hint_lower in title:
                    return hwnd

        # Fall back to first terminal found
        return candidates[0][0]

    def find_all_terminal_windows(
        self,
        title_exclude: list[str] | None = None,
    ) -> list[tuple[int, str]]:
        """Enumerate all visible terminal windows.

        Returns a list of (hwnd, title) tuples for the terminal selector UI.
        """
        if title_exclude is None:
            title_exclude = []
        candidates: list[tuple[int, str]] = []

        def _enum_cb(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            if cls_buf.value not in _TERMINAL_CLASSES:
                return True
            title_buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buf, 512)
            title = title_buf.value
            title_lower = title.lower()
            for excl in title_exclude:
                if excl.lower() in title_lower:
                    return True
            candidates.append((hwnd, title))
            return True

        user32.EnumWindows(_WNDENUMPROC(_enum_cb), 0)
        return candidates

    # ── focus management ─────────────────────────────────────────────

    def get_foreground_window(self) -> int | None:
        hwnd = user32.GetForegroundWindow()
        return hwnd if hwnd else None

    def set_foreground_window(self, handle: Any) -> bool:
        """Bring *handle* to the foreground.

        Uses the ALT-key trick to bypass Windows' foreground lock:
        Windows blocks SetForegroundWindow from background processes
        unless the caller recently received input.  Pressing and
        releasing ALT satisfies that requirement.
        """
        try:
            user32.keybd_event(VK_MENU, 0, 0, 0)             # ALT down
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)  # ALT up
            return bool(user32.SetForegroundWindow(int(handle)))
        except Exception:
            return False

    # ── paste key ────────────────────────────────────────────────────

    def get_paste_modifier(self):
        from pynput.keyboard import Key
        return Key.ctrl

    # ── window styles ────────────────────────────────────────────────

    def apply_tool_window_style(self, tk_root) -> None:
        """Make a tkinter root behave as a non-activating tool window.

        Sets WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST so the
        window floats above everything, never appears in the taskbar, and
        never steals focus.
        """
        try:
            hwnd = user32.GetParent(tk_root.winfo_id())
            if not hwnd:
                hwnd = tk_root.winfo_id()
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def set_rounded_corners(self, tk_root, radius: int, enable: bool) -> None:
        """Apply or clear rounded corners via a Win32 region.

        When *enable* is True, creates a rounded-rectangle region with
        ``CreateRoundRectRgn`` and assigns it via ``SetWindowRgn``.
        When False, clears any existing region so the window uses its
        full rectangular shape.
        """
        try:
            hwnd = int(tk_root.wm_frame(), 16)
            if not enable:
                user32.SetWindowRgn(hwnd, 0, True)
                return
            w = tk_root.winfo_width()
            h = tk_root.winfo_height()
            rgn = gdi32.CreateRoundRectRgn(
                0, 0, w + 1, h + 1, radius * 2, radius * 2,
            )
            user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

    def setup_transparency(self, tk_root, transparent: bool) -> None:
        """Configure window transparency.

        On Windows, tkinter's ``-transparentcolor`` attribute handles
        per-pixel transparency.  We also ensure ``-topmost`` is set.
        """
        try:
            tk_root.attributes("-topmost", True)
            if transparent:
                tk_root.attributes("-transparentcolor", tk_root["bg"])
            else:
                tk_root.attributes("-transparentcolor", "")
        except Exception:
            pass

    # ── screen geometry ──────────────────────────────────────────────

    def get_virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height) spanning all monitors."""
        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return (x, y, w, h)

    def get_monitor_rect_for_window(self, handle: Any) -> tuple[int, int, int, int] | None:
        """Return (x, y, width, height) of the monitor containing *handle*."""
        try:
            MONITOR_DEFAULTTONEAREST = 2
            hmon = user32.MonitorFromWindow(int(handle), MONITOR_DEFAULTTONEAREST)
            if not hmon:
                return None

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.wintypes.DWORD),
                    ("rcMonitor", _RECT),
                    ("rcWork", _RECT),
                    ("dwFlags", ctypes.wintypes.DWORD),
                ]

            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                return None
            r = info.rcWork  # work area (excludes taskbar)
            return (r.left, r.top, r.right - r.left, r.bottom - r.top)
        except Exception:
            return None

    # ── window snapping ──────────────────────────────────────────────

    def get_tk_hwnd(self, tk_root) -> int | None:
        """Extract the native HWND from a tkinter root.

        ``wm_frame()`` returns a hex string.  On some Windows configs the
        tkinter widget id needs ``GetParent`` to reach the real top-level
        HWND, but ``wm_frame()`` already gives us the right one.
        """
        try:
            return int(tk_root.wm_frame(), 16)
        except Exception:
            return None

    def get_window_rect(self, handle: Any) -> tuple[int, int, int, int] | None:
        """Return (left, top, right, bottom) for *handle*."""
        try:
            rect = _RECT()
            user32.GetWindowRect(int(handle), ctypes.byref(rect))
            return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            return None

    def is_window_valid(self, handle: Any) -> bool:
        """Check whether *handle* still refers to a live window."""
        try:
            return bool(user32.IsWindow(int(handle)))
        except Exception:
            return False

    def is_window_minimized(self, handle: Any) -> bool:
        """Check whether *handle* is minimized (IsIconic)."""
        try:
            return bool(user32.IsIconic(int(handle)))
        except Exception:
            return False

    def set_window_position(self, tk_hwnd: Any, x: int, y: int) -> None:
        """Move a window to (x, y) without resizing or re-ordering.

        Uses SetWindowPos with SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        for a fast, flicker-free move that bypasses tkinter's geometry
        string parsing.
        """
        try:
            user32.SetWindowPos(int(tk_hwnd), 0, x, y, 0, 0, SWP_FLAGS)
        except Exception:
            pass

    # ── subprocess helpers ───────────────────────────────────────────

    @property
    def subprocess_no_window_flags(self) -> int:
        return subprocess.CREATE_NO_WINDOW  # 0x08000000

    # ── console / ANSI ───────────────────────────────────────────────

    def enable_ansi_console(self) -> None:
        """Enable ANSI escape-code processing on the Windows console.

        Sets the console output mode to ENABLE_VIRTUAL_TERMINAL_PROCESSING
        so escape sequences like ``\\033[31m`` render correctly.
        """
        try:
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    # ── fonts ────────────────────────────────────────────────────────

    def get_ui_font(self) -> str:
        return "Segoe UI"

    def get_mono_font(self) -> str:
        return "Cascadia Code"
