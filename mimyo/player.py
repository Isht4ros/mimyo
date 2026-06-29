"""Audio playback via pygame."""
from __future__ import annotations

import threading
import time

from .deps import PYGAME_AVAILABLE, pygame
from .track import Track


class Player:
    def __init__(self):
        self.current: Track | None = None
        self._paused = False
        self._start_time = 0.0
        self._pause_offset = 0.0
        self._lock = threading.Lock()

    def load(self, track: Track) -> bool:
        if not PYGAME_AVAILABLE:
            return False
        # Wait briefly for mixer to finish initialising (it may still be
        # starting up in its background thread on slow machines / Windows).
        for _ in range(20):
            if pygame.mixer.get_init():
                break
            time.sleep(0.05)
        else:
            return False
        with self._lock:
            try:
                pygame.mixer.music.load(str(track.path))
                pygame.mixer.music.play()
            except Exception:
                return False
            self.current = track
            self._paused = False
            self._start_time = time.time()
            self._pause_offset = 0.0
            return True

    def toggle_pause(self):
        if not PYGAME_AVAILABLE:
            return
        with self._lock:
            if self._paused:
                pygame.mixer.music.unpause()
                self._start_time = time.time() - self._pause_offset
                self._paused = False
            else:
                self._pause_offset = time.time() - self._start_time
                pygame.mixer.music.pause()
                self._paused = True

    def stop(self):
        if not PYGAME_AVAILABLE:
            return
        with self._lock:
            pygame.mixer.music.stop()
            self.current = None
            self._paused = False

    def shutdown(self):
        """Fully tear down pygame mixer — call this on app exit only."""
        if not PYGAME_AVAILABLE:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass

    def set_volume(self, vol: float):
        if PYGAME_AVAILABLE:
            pygame.mixer.music.set_volume(max(0.0, min(1.0, vol)))

    def get_volume(self) -> float:
        if PYGAME_AVAILABLE:
            return pygame.mixer.music.get_volume()
        return 1.0

    @property
    def is_playing(self) -> bool:
        if not PYGAME_AVAILABLE:
            return False
        return pygame.mixer.music.get_busy() and not self._paused

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def position(self) -> float:
        if not PYGAME_AVAILABLE or self.current is None:
            return 0.0
        if self._paused:
            return self._pause_offset
        if pygame.mixer.music.get_busy():
            return time.time() - self._start_time
        return 0.0

    def finished(self) -> bool:
        if not PYGAME_AVAILABLE or self.current is None:
            return False
        return not pygame.mixer.music.get_busy() and not self._paused
