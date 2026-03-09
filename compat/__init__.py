"""Cross-platform compatibility layer.

Auto-detects the current OS and exposes the appropriate backend as
``backend``.  The rest of the app imports::

    from compat import backend
"""

from __future__ import annotations

import sys

from .base import PlatformBackend  # noqa: F401 — re-export for typing


def _create_backend() -> PlatformBackend:
    if sys.platform == "win32":
        from .windows import WindowsBackend
        return WindowsBackend()

    # macOS and Linux backends exist but are untested.
    # To enable: remove from .gitignore and uncomment below.
    #
    # elif sys.platform == "darwin":
    #     from .macos import MacOSBackend
    #     return MacOSBackend()
    # else:
    #     from .linux import LinuxBackend
    #     return LinuxBackend()

    raise RuntimeError(
        f"Whisper Typer currently supports Windows only. "
        f"Your platform: {sys.platform}"
    )


backend: PlatformBackend = _create_backend()
