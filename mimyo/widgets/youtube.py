"""
YouTube support: fetch_youtube_audio downloader and the YoutubeBar overlay widget.
Both live here so all YouTube-related code is in one place.
"""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Static

from ..config import YT_CACHE_DIR
from ..deps import YTDLP_AVAILABLE


# ── Downloader ────────────────────────────────────────────────────────────────

def fetch_youtube_audio(url: str, on_progress=None) -> tuple[Path, str, float, Path | None] | str | None:
    """
    Download (or retrieve cached) YouTube audio + thumbnail.

    Returns (audio_path, title, duration, thumbnail_path) on success,
    an error string on failure, or None if yt-dlp is unavailable.
    thumbnail_path is None if the thumbnail could not be fetched.
    Uses yt-dlp to extract the best audio stream and convert to mp3.
    """
    if not YTDLP_AVAILABLE:
        return None
    import yt_dlp  # imported here so the module is importable without yt-dlp
    YT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _progress_hook(d):
        if on_progress is None:
            return
        if d.get("status") == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                pct = int(downloaded / total * 100)
                mb_done = downloaded / 1_048_576
                mb_total = total / 1_048_576
                on_progress(f"Downloading… {pct}% ({mb_done:.1f}/{mb_total:.1f} MB)")
            else:
                mb_done = downloaded / 1_048_576
                on_progress(f"Downloading… {mb_done:.1f} MB")
        elif d.get("status") == "finished":
            on_progress("Converting to mp3…")

    error_log: list[str] = []

    def _ydl_error_logger(msg):
        error_log.append(msg)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(YT_CACHE_DIR / "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "writethumbnail": True,
        "progress_hooks": [_progress_hook],
        "quiet": True,
        "no_warnings": True,
        "logger": type("L", (), {
            "debug": staticmethod(lambda m: None),
            "warning": staticmethod(lambda m: None),
            "error": staticmethod(_ydl_error_logger),
        })(),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "unknown")
            title = info.get("title", video_id)
            duration = float(info.get("duration") or 0)
            mp3_path = YT_CACHE_DIR / f"{video_id}.mp3"
            if not mp3_path.exists():
                return "mp3 not found after download — ffmpeg may be missing or not on PATH"

            # yt-dlp writes the thumbnail as <id>.webp (or .jpg).
            thumb_path: Path | None = None
            for ext in ("webp", "jpg", "jpeg", "png"):
                candidate = YT_CACHE_DIR / f"{video_id}.{ext}"
                if candidate.exists():
                    thumb_path = candidate
                    break

            return mp3_path, title, duration, thumb_path
    except Exception as e:
        msg = str(e).strip()
        if not msg and error_log:
            msg = error_log[-1].strip()
        return msg or "Unknown yt-dlp error"


# ── Widget ────────────────────────────────────────────────────────────────────

class YoutubeBar(Static):
    """Floating YouTube URL input bar, shown/hidden with the Y key."""

    def compose(self) -> ComposeResult:
        from textual.widgets import Input
        yield Input(placeholder="https://www.youtube.com/watch?v=...", id="yt-input")

    def on_mount(self) -> None:
        inp = self.query_one("#yt-input")
        inp.border_title = "YouTube URL"
        inp.border_subtitle = "Enter to add · Esc to cancel"

    def show(self):
        self.add_class("visible")
        try:
            self.query_one("#yt-input").focus()
        except Exception:
            pass

    def hide(self):
        self.remove_class("visible")
        try:
            self.query_one("#yt-input").value = ""
        except Exception:
            pass

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.hide()
            event.stop()
