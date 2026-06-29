"""Shared utility functions."""
from __future__ import annotations

import os
from pathlib import Path

from .config import SUPPORTED, load_settings


def format_time(seconds: float) -> str:
    if seconds < 0:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02}:{s:02}"
    return f"{m}:{s:02}"


def find_music_dir() -> Path:
    """Find the best music directory on this system.

    Priority:
    1. Path saved via `mimyo --music-dir ...` (persisted in ~/.mimyo/settings.json)
    2. MIMYO_MUSIC_DIR environment variable, for a one-off per-session override
    3. Standard "Music" folder variants under the user's home directory
    4. The home directory itself, as a last resort
    """
    saved = load_settings().get("music_dir")
    if saved:
        p = Path(saved)
        if p.exists() and p.is_dir():
            return p

    env_dir = os.environ.get("MIMYO_MUSIC_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.exists() and p.is_dir():
            return p

    home = Path.home()
    candidates = [
        home / "Music",
        home / "music",
        home / "My Music",
        home,
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return home
