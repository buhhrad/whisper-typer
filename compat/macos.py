"""macOS platform backend for Whisper Typer.

Uses AppleScript (via ``osascript``) for window management and system
interaction.  macOS has native rounded corners and ANSI support, so
several methods are no-ops.  Window snapping works but is slower than
Windows due to AppleScript overhead (~50-100 ms per call).
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from .base import PlatformBackend

log = logging.getLogger(__name__)

# AppleScript timeout for all subprocess calls (seconds).
_OSASCRIPT_TIMEOUT = 3

# Terminal application names recognised on macOS.
_TERMINAL_APPS = [
    "Terminal",
    "iTerm2",
    "Alacritty",
    "kitty",
    "Warp",
    "Hyper",
]


def _run_osascript(script: str, *, timeout: int = _OSASCRIPT_TIMEOUT) -> str | None:
    """Run an AppleScript snippet and return stripped stdout, or *None* on
    failure."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        log.debug("osascript returned %d: %s", result.returncode, result.stderr.strip())
        return None
    except subprocess.TimeoutExpired:
        log.warning("osascript timed out after %ds", timeout)
        return None
    except FileNotFoundError:
        log.error("osascript not found — is this macOS?")
        return None
    except Exception:
        log.exception("Unexpected error running osascript")
        return None


class MacOSBackend(PlatformBackend):
    """macOS implementation of :class:`PlatformBackend`."""

    # ── identity ────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "macos"

    # ── capability flags ────────────────────────────────────────────

    @property
    def supports_window_snapping(self) -> bool:
        # Possible via AppleScript, but perf is degraded.
        return True

    @property
    def supports_rounded_corners(self) -> bool:
        # Native on macOS — no custom rendering needed.
        return True

    @property
    def supports_transparency(self) -> bool:
        return True

    @property
    def supports_terminal_finding(self) -> bool:
        return True

    @property
    def snap_poll_interval_ms(self) -> int:
        # AppleScript calls are ~50-100 ms, so polling faster is pointless.
        return 100

    # ── clipboard ───────────────────────────────────────────────────

    def set_clipboard(self, text: str) -> bool:
        """Copy *text* to the macOS pasteboard via ``pbcopy``."""
        try:
            proc = subprocess.Popen(
                ["pbcopy"],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=text.encode("utf-8"), timeout=5)
            return proc.returncode == 0
        except Exception:
            log.exception("Failed to set clipboard via pbcopy")
            return False

    # ── terminal discovery ──────────────────────────────────────────

    def get_terminal_window_classes(self) -> list[str]:
        # macOS doesn't use window classes, but return app names for
        # consistency with the interface.
        return list(_TERMINAL_APPS)

    def get_terminal_title_hints(self) -> list[str]:
        return ["terminal", "iterm", "alacritty", "kitty", "warp"]

    def find_terminal_window(
        self,
        title_hints: list[str] | None = None,
        title_exclude: list[str] | None = None,
    ) -> Any | None:
        """Find a running terminal app and return its name as the handle.

        Queries System Events for visible application processes and matches
        against known terminal app names.  *title_hints* and *title_exclude*
        further filter the results.
        """
        script = (
            'tell application "System Events" to get name of every '
            "application process whose visible is true"
        )
        raw = _run_osascript(script)
        if not raw:
            return None

        # osascript returns a comma-separated list.
        visible_apps = [a.strip() for a in raw.split(",")]

        hints = title_hints or self.get_terminal_title_hints()
        exclude = [e.lower() for e in (title_exclude or [])]

        for app_name in visible_apps:
            lower = app_name.lower()

            # Check exclusion list.
            if any(ex in lower for ex in exclude):
                continue

            # Match against known terminals or title hints.
            is_known = app_name in _TERMINAL_APPS
            matches_hint = any(h in lower for h in hints)

            if is_known or matches_hint:
                log.debug("Found terminal app: %s", app_name)
                return app_name

        return None

    # ── focus management ────────────────────────────────────────────

    def get_foreground_window(self) -> Any | None:
        """Return the name of the frontmost application."""
        script = (
            'tell application "System Events" to get name of first '
            "application process whose frontmost is true"
        )
        return _run_osascript(script)

    def set_foreground_window(self, handle: Any) -> bool:
        """Activate the application named *handle*."""
        if not isinstance(handle, str) or not handle:
            return False
        script = f'tell application "{handle}" to activate'
        result = _run_osascript(script)
        return result is not None

    # ── paste key ───────────────────────────────────────────────────

    def get_paste_modifier(self):
        """macOS uses Cmd+V for paste."""
        from pynput.keyboard import Key
        return Key.cmd

    # ── window styles ───────────────────────────────────────────────

    def apply_tool_window_style(self, tk_root) -> None:
        """Make the tkinter window float above others without a dock icon."""
        try:
            tk_root.attributes("-topmost", True)
        except Exception:
            log.debug("Failed to set -topmost")

        try:
            # Suppress dock/taskbar entry on macOS.  This is an
            # undocumented Tk call that removes the window from the
            # Dock and Cmd-Tab list.
            tk_root.tk.call(
                "::tk::unsupported::MacWindowStyle",
                "style",
                tk_root,
                "plain",
                "none",
            )
        except Exception:
            log.debug("MacWindowStyle unsupported on this Tk build")

    def set_rounded_corners(self, tk_root, radius: int, enable: bool) -> None:
        """No-op — macOS windows have native rounded corners."""
        pass

    def setup_transparency(self, tk_root, transparent: bool) -> None:
        """Set whole-window alpha.

        macOS doesn't support per-pixel transparency colour keying the way
        Windows does.  We fall back to whole-window alpha blending.
        """
        try:
            tk_root.attributes("-alpha", 0.9 if transparent else 1.0)
        except Exception:
            log.debug("Failed to set -alpha attribute")

    # ── screen geometry ─────────────────────────────────────────────

    def get_virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        """Return ``(x, y, width, height)`` of the primary display.

        Attempts to query screen size via AppleScript.  Falls back to a
        generous 3840x2160 default that won't clip on most displays.
        """
        script = (
            'tell application "Finder" to get bounds of window of desktop'
        )
        raw = _run_osascript(script)
        if raw:
            try:
                parts = [int(p.strip()) for p in raw.split(",")]
                if len(parts) == 4:
                    x, y, right, bottom = parts
                    return (x, y, right - x, bottom - y)
            except (ValueError, IndexError):
                log.debug("Could not parse desktop bounds: %s", raw)

        # Safe fallback — large enough for most Retina displays.
        return (0, 0, 3840, 2160)

    # ── window snapping ─────────────────────────────────────────────

    def get_tk_hwnd(self, tk_root) -> Any | None:
        """macOS doesn't use HWNDs.  Return None.

        The snap system should use tkinter geometry methods directly
        on macOS rather than native window handles.
        """
        return None

    def get_window_rect(self, handle: Any) -> tuple[int, int, int, int] | None:
        """Return ``(left, top, right, bottom)`` of *handle*'s front window.

        *handle* is the application name (string).
        """
        if not isinstance(handle, str) or not handle:
            return None

        script = (
            f'tell application "System Events"\n'
            f'  tell process "{handle}"\n'
            f"    set pos to position of front window\n"
            f"    set sz to size of front window\n"
            f'    return (item 1 of pos) & "," & (item 2 of pos) & "," '
            f'& ((item 1 of pos) + (item 1 of sz)) & "," '
            f'& ((item 2 of pos) + (item 2 of sz))\n'
            f"  end tell\n"
            f"end tell"
        )
        raw = _run_osascript(script)
        if not raw:
            return None

        try:
            parts = [int(p.strip()) for p in raw.split(",")]
            if len(parts) == 4:
                return (parts[0], parts[1], parts[2], parts[3])
        except (ValueError, IndexError):
            log.debug("Could not parse window rect for %s: %s", handle, raw)

        return None

    def is_window_valid(self, handle: Any) -> bool:
        """Check whether the application named *handle* is still running."""
        if not isinstance(handle, str) or not handle:
            return False

        script = (
            'tell application "System Events" to (name of every '
            "application process) contains "
            f'"{handle}"'
        )
        raw = _run_osascript(script)
        return raw == "true"

    def is_window_minimized(self, handle: Any) -> bool:
        """Check whether the front window of *handle* is minimized."""
        if not isinstance(handle, str) or not handle:
            return False

        script = (
            f'tell application "System Events"\n'
            f'  tell process "{handle}"\n'
            f"    if (count of windows) is 0 then return true\n"
            f"    return value of attribute \"AXMinimized\" of front window\n"
            f"  end tell\n"
            f"end tell"
        )
        raw = _run_osascript(script)
        return raw == "true"

    def set_window_position(self, tk_hwnd: Any, x: int, y: int) -> None:
        """Move a window to ``(x, y)``.

        On macOS ``tk_hwnd`` is None (no native handle available), so this
        method accepts the tkinter root widget directly as a fallback.  If
        *tk_hwnd* is a tkinter widget (has a ``geometry`` method), we use
        that.  Otherwise this is a no-op.
        """
        if tk_hwnd is not None and hasattr(tk_hwnd, "geometry"):
            try:
                tk_hwnd.geometry(f"+{x}+{y}")
            except Exception:
                log.debug("Failed to set window position via geometry()")

    # ── subprocess helpers ──────────────────────────────────────────

    @property
    def subprocess_no_window_flags(self) -> int:
        # No equivalent needed on macOS.
        return 0

    # ── console / ANSI ──────────────────────────────────────────────

    def enable_ansi_console(self) -> None:
        """No-op — macOS terminals support ANSI natively."""
        pass

    # ── fonts ───────────────────────────────────────────────────────

    def get_ui_font(self) -> str:
        """Return the best available proportional font.

        Prefers SF Pro (macOS 10.15+) then Helvetica Neue then Helvetica.
        """
        try:
            import tkinter.font as tkfont
            available = tkfont.families()
            for font in ("SF Pro", "Helvetica Neue", "Helvetica"):
                if font in available:
                    return font
        except Exception:
            log.debug("Could not enumerate fonts; falling back to Helvetica")
        return "Helvetica"

    def get_mono_font(self) -> str:
        """Return the best available monospace font.

        Prefers SF Mono (macOS 10.15+) then Menlo then Courier.
        """
        try:
            import tkinter.font as tkfont
            available = tkfont.families()
            for font in ("SF Mono", "Menlo", "Courier"):
                if font in available:
                    return font
        except Exception:
            log.debug("Could not enumerate fonts; falling back to Menlo")
        return "Menlo"
