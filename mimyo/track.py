"""Track data classes and tag/art helpers."""
from __future__ import annotations

import io
from pathlib import Path

from .deps import (
    MUTAGEN_AVAILABLE, PIL_AVAILABLE,
    MutagenFile, ID3, APIC, FLAC, Picture, MP4,
    Image,
)


def get_tags(path: Path) -> dict:
    tags = {"title": path.stem, "artist": "Unknown", "album": "Unknown", "duration": 0.0}
    if not MUTAGEN_AVAILABLE:
        return tags
    try:
        f = MutagenFile(path, easy=True)
        if f is None:
            return tags
        if hasattr(f, "info") and hasattr(f.info, "length"):
            tags["duration"] = f.info.length
        if f.get("title"):
            tags["title"] = str(f["title"][0])
        if f.get("artist"):
            tags["artist"] = str(f["artist"][0])
        if f.get("album"):
            tags["album"] = str(f["album"][0])
    except Exception:
        pass
    return tags


def extract_album_art(path: Path):
    if not MUTAGEN_AVAILABLE or not PIL_AVAILABLE:
        return None
    try:
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            tags = ID3(str(path))
            for key in tags.keys():
                if key.startswith("APIC"):
                    apic = tags[key]
                    return Image.open(io.BytesIO(apic.data))
        elif suffix == ".flac":
            audio = FLAC(str(path))
            if audio.pictures:
                return Image.open(io.BytesIO(audio.pictures[0].data))
        elif suffix in {".m4a", ".aac", ".mp4"}:
            audio = MP4(str(path))
            if "covr" in audio:
                return Image.open(io.BytesIO(bytes(audio["covr"][0])))
        else:
            f = MutagenFile(str(path))
            if f and hasattr(f, "pictures") and f.pictures:
                return Image.open(io.BytesIO(f.pictures[0].data))
    except Exception:
        pass

    for name in ("cover.jpg", "cover.png", "folder.jpg", "folder.png",
                 "artwork.jpg", "artwork.png", "front.jpg", "front.png"):
        candidate = path.parent / name
        if candidate.exists():
            try:
                return Image.open(candidate)
            except Exception:
                pass
    return None


class Track:
    def __init__(self, path: Path):
        self.path = path
        info = get_tags(path)
        self.title = info["title"]
        self.artist = info["artist"]
        self.album = info["album"]
        self.duration = info["duration"]
        self._art: "Image.Image | None | bool" = False

    def get_art(self):
        if self._art is False:
            self._art = extract_album_art(self.path)
        return self._art


class YouTubeTrack(Track):
    """A Track sourced from YouTube (audio already downloaded to a temp mp3)."""

    def __init__(self, path: Path, title: str, duration: float, thumb_path: Path | None = None):
        # Bypass tag reading — we already have everything from yt-dlp
        self.path = path
        self.title = title
        self.artist = "YouTube"
        self.album = "YouTube"
        self.duration = duration
        self._thumb_path = thumb_path
        self._art: "Image.Image | None | bool" = False  # False = not yet loaded

    def get_art(self):
        if self._art is not False:
            return self._art
        if self._thumb_path and self._thumb_path.exists() and PIL_AVAILABLE:
            try:
                img = Image.open(self._thumb_path).convert("RGB")
                w, h = img.size
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                self._art = img.crop((left, top, left + side, top + side))
                return self._art
            except Exception:
                pass
        self._art = None
        return None
