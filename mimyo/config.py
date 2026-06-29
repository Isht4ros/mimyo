"""Paths, constants, and terminal-restore logic."""
from __future__ import annotations

import atexit
import json
import os
import platform
import signal
import sys
from pathlib import Path

# ── Supported formats ─────────────────────────────────────────────────────────
SUPPORTED = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".opus"}

# ── Config paths ──────────────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".mimyo"
PLAYLISTS_FILE = CONFIG_DIR / "playlists.json"
YT_CACHE_DIR = CONFIG_DIR / "yt_cache"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def load_settings() -> dict:
    """Load persisted user settings (music_dir, etc). Returns {} if none saved yet."""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(updates: dict) -> None:
    """Merge `updates` into the persisted settings file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    settings.update(updates)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")

# ── UI constants ──────────────────────────────────────────────────────────────
ESC = "\x1b"
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# ── Terminal restore ──────────────────────────────────────────────────────────
# Save tty state at startup so we can always restore it on exit, even if
# Textual's on_unmount never fires (e.g. when pygame threads keep the process
# alive or the app is killed with Ctrl-C / SIGTERM).
_saved_tty_attrs = None
if platform.system() != "Windows":
    try:
        import termios as _termios
        _saved_tty_attrs = _termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass


def _restore_terminal():
    """Restore tty to the attrs captured at startup."""
    if _saved_tty_attrs is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSAFLUSH, _saved_tty_attrs)
    except Exception:
        pass


atexit.register(_restore_terminal)


def _signal_exit(signum, frame):
    _restore_terminal()
    # Force-exit so any lingering pygame/audio threads can't block shutdown
    os._exit(0)


if platform.system() != "Windows":
    try:
        signal.signal(signal.SIGTERM, _signal_exit)
        signal.signal(signal.SIGINT, _signal_exit)
    except Exception:
        pass
