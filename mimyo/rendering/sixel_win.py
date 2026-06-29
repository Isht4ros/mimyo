"""
Windows-only Win32 console helpers for sixel rendering.

This module uses ctypes.windll and will raise AttributeError on non-Windows
platforms. All callers guard with `import platform; platform.system() == "Windows"`
or catch the error at the call site. If you want to run linting / CI on Linux,
either mock this module or run with `windows-latest` on GitHub Actions.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys


def _open_conout():
    """Open a direct handle to the Windows console output, bypassing Textual's stdout."""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            "CONOUT$",
            0x40000000,  # GENERIC_WRITE
            3,           # FILE_SHARE_READ | FILE_SHARE_WRITE
            None, 3, 0, None  # OPEN_EXISTING
        )
        if handle and handle != -1:
            return handle
    except Exception:
        pass
    return None


def _write_conout(handle, text: str) -> None:
    """Write a string directly to the console handle."""
    kernel32 = ctypes.windll.kernel32
    written = ctypes.wintypes.DWORD(0)
    kernel32.WriteConsoleW(handle, text, len(text), ctypes.byref(written), None)


def _set_cursor_pos(handle, col: int, row: int) -> None:
    """Move the Windows console cursor to (col, row) using Win32 API directly.

    More reliable than ANSI escape sequences which WriteConsoleW may ignore.
    """
    try:
        # COORD is a struct of two SHORTs: X (col), Y (row), both 0-based
        coord = ctypes.wintypes.DWORD((row << 16) | (col & 0xFFFF))
        ctypes.windll.kernel32.SetConsoleCursorPosition(handle, coord)
    except Exception:
        pass


def _sixel_write_at(row: int, col: int, sixel_bytes: bytes, driver=None) -> None:
    """Write sixel at (row, col) so the cursor-move escape and sixel data arrive
    as one atomic unit and the position is honoured.

    IMPORTANT: this must go through Textual's own writer, not a second handle.
    Textual's WindowsDriver flushes frames on a background WriterThread that
    writes straight to sys.__stdout__ on its own schedule. If we ALSO open a
    raw CONOUT$ handle and WriteFile to it from this thread, the two writers
    race for the same console: our cursor-save/move escape can land in the
    middle of a still-in-flight SGR code from Textual's frame (e.g.
    "\x1b[48;5;240m"), which makes the terminal abandon that half-parsed
    escape. The orphaned tail ("40m") then prints as literal text - this is
    almost certainly the source of the random leaked fragments. Enqueuing
    through driver.write() puts our payload on the SAME serial queue as every
    other frame write, so it can never be torn or interleaved.
    """
    payload = (
        f"\x1b7"              # DECSC: save VT cursor
        f"\x1b[{row};{col}H"  # CUP: move VT cursor to target
        f"\x1b[?80l"          # DECSDM reset: draw sixel at cursor pos, not home
    ).encode("latin-1") + sixel_bytes + b"\x1b8"  # DECRC: restore cursor

    if driver is not None and hasattr(driver, "write"):
        try:
            # Sixel data is pure 7-bit ASCII (raster header, color defs,
            # and sixel chars in 0x3F-0x7E), so this round-trips losslessly.
            driver.write(payload.decode("latin-1"))
            return
        except Exception:
            pass  # fall through to the raw-handle path below

    # Fallback for contexts with no driver (e.g. early startup, testing).
    # Still racy against Textual's writer thread - only used if the above
    # path is unavailable.
    handle = _open_conout()
    if handle:
        try:
            written = ctypes.wintypes.DWORD(0)
            ctypes.windll.kernel32.WriteFile(
                handle, payload, len(payload), ctypes.byref(written), None)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        sys.__stdout__.buffer.write(payload)
        sys.__stdout__.flush()
