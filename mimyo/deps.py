"""
Optional-dependency guards.

Every other module imports availability flags and the actual objects from here,
so the try/except noise lives in exactly one place.
"""
from __future__ import annotations

# ── pygame ────────────────────────────────────────────────────────────────────

PYGAME_AVAILABLE = False
PYGAME_ERROR = ""
try:
    import os as _os, sys as _sys, threading as _threading
    _os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    _devnull = open(_os.devnull, "w")
    _real_stdout, _sys.stdout = _sys.stdout, _devnull
    try:
        import pygame
    finally:
        _sys.stdout = _real_stdout
        _devnull.close()

    def _init_mixer():
        try:
            pygame.mixer.pre_init(44100, -16, 2, 2048)
            pygame.mixer.init()
        except Exception:
            pass
    _t = _threading.Thread(target=_init_mixer, daemon=True)
    _t.daemon = True  # never block process exit
    _t.start()
    PYGAME_AVAILABLE = True
except ImportError:
    try:
        import pygame  # pygame-ce uses the same import name
        pygame.mixer.init()
        PYGAME_AVAILABLE = True
    except ImportError:
        PYGAME_ERROR = "No audio: install pygame-ce with:  pip install pygame-ce"
        pygame = None  # type: ignore[assignment]
except Exception as e:
    PYGAME_ERROR = f"Audio init failed: {e}"
    pygame = None  # type: ignore[assignment]

# ── mutagen ───────────────────────────────────────────────────────────────────
MUTAGEN_AVAILABLE = False
MutagenFile = ID3 = APIC = FLAC = Picture = MP4 = None  # type: ignore[assignment]
try:
    from mutagen import File as MutagenFile  # type: ignore[no-redef]
    from mutagen.id3 import ID3, APIC  # type: ignore[no-redef]
    from mutagen.flac import FLAC, Picture  # type: ignore[no-redef]
    from mutagen.mp4 import MP4  # type: ignore[no-redef]
    MUTAGEN_AVAILABLE = True
except ImportError:
    pass

# ── Pillow ────────────────────────────────────────────────────────────────────
PIL_AVAILABLE = False
Image = None  # type: ignore[assignment]
try:
    from PIL import Image  # type: ignore[no-redef]
    PIL_AVAILABLE = True
except ImportError:
    pass

# ── sixel ─────────────────────────────────────────────────────────────────────
SIXEL_AVAILABLE = False
SixelConverter = None  # type: ignore[assignment]
try:
    from sixel.converter import SixelConverter  # type: ignore[no-redef]
    SIXEL_AVAILABLE = True
except ImportError:
    pass

# ── pypresence ────────────────────────────────────────────────────────────────
PYPRESENCE_AVAILABLE = False
Presence = None  # type: ignore[assignment]
try:
    from pypresence import Presence  # type: ignore[no-redef]
    PYPRESENCE_AVAILABLE = True
except ImportError:
    pass

# ── yt-dlp ────────────────────────────────────────────────────────────────────
YTDLP_AVAILABLE = False
try:
    import yt_dlp  # noqa: F401
    YTDLP_AVAILABLE = True
except ImportError:
    pass
