"""
YouTube support: fetch_youtube_audio downloader, search helper, and the
YoutubeBar overlay widget.  All YouTube-related code lives here.
"""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Static, Label, ListView, ListItem

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


# ── Search helper ─────────────────────────────────────────────────────────────

def search_youtube(query: str, max_results: int = 5) -> list[dict] | str:
    """
    Search YouTube for *query* using yt-dlp's ytsearch: prefix.

    Returns a list of dicts with keys: id, title, channel, duration, url
    or an error string on failure.
    """
    if not YTDLP_AVAILABLE:
        return "yt-dlp not installed"
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            entries = result.get("entries", []) if result else []
            results = []
            for e in entries:
                if not e:
                    continue
                vid_id = e.get("id", "")
                results.append({
                    "id": vid_id,
                    "title": e.get("title", "Unknown"),
                    "channel": e.get("uploader") or e.get("channel") or "Unknown",
                    "duration": e.get("duration") or 0,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                })
            return results
    except Exception as e:
        return str(e).strip() or "Search failed"


def _fmt_duration(seconds) -> str:
    try:
        s = int(seconds)
        if s <= 0:
            return "live"
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    except Exception:
        return "?"


# ── Result list item ──────────────────────────────────────────────────────────

class YTResultItem(ListItem):
    """A single search result row in the YoutubeBar results list."""

    def __init__(self, result: dict, number: int):
        super().__init__()
        self.result = result
        self.number = number

    def compose(self) -> ComposeResult:
        dur = _fmt_duration(self.result["duration"])
        title = self.result["title"]
        channel = self.result["channel"]
        num = self.number
        yield Label(
            f" {num}  {title}",
            id=f"yt-result-title-{num}",
            classes="yt-result-title",
        )
        yield Label(
            f"    {channel}  ·  {dur}",
            id=f"yt-result-meta-{num}",
            classes="yt-result-meta",
        )


# ── Widget ────────────────────────────────────────────────────────────────────

class YoutubeBar(Static):
    """
    Floating YouTube bar.  Accepts a song name/search query OR a direct URL.
    - If it looks like a URL → download immediately (original behaviour).
    - Otherwise → search YouTube, show results, let user pick with ↑↓ + Enter.
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Input
        yield Input(
            placeholder="Search or paste a URL…",
            id="yt-input",
        )
        yield Label("", id="yt-hint", classes="yt-hint")
        yield ListView(id="yt-results")

    def on_mount(self) -> None:
        inp = self.query_one("#yt-input")
        inp.border_title = "YouTube"
        inp.border_subtitle = "Enter to search · Esc to cancel"
        self.query_one("#yt-results").display = False
        self._results: list[dict] = []

    def _reposition(self) -> None:
        try:
            parent = self.parent
            if parent is None:
                return
            pw = parent.content_size.width
            w = self.outer_size.width or 60
            x = max(0, (pw - w) // 2)
            self.styles.offset = (x, 2)
        except Exception:
            pass

    def on_resize(self) -> None:
        self._reposition()

    def show(self):
        self.add_class("visible")
        self.call_after_refresh(self._reposition)
        try:
            self.query_one("#yt-input").focus()
        except Exception:
            pass

    def hide(self):
        self.remove_class("visible")
        self._results = []
        try:
            self.query_one("#yt-input").value = ""
        except Exception:
            pass
        try:
            rl = self.query_one("#yt-results", ListView)
            rl.clear()
            rl.display = False
        except Exception:
            pass
        try:
            self.query_one("#yt-hint", Label).update("")
        except Exception:
            pass
        try:
            inp = self.query_one("#yt-input")
            inp.border_subtitle = "Enter to search · Esc to cancel"
        except Exception:
            pass

    def show_results(self, results: list[dict]):
        """Populate the results list and make it visible."""
        self._results = results
        rl = self.query_one("#yt-results", ListView)
        rl.clear()
        for i, r in enumerate(results, 1):
            rl.append(YTResultItem(r, i))
        rl.display = True
        rl.focus()
        try:
            inp = self.query_one("#yt-input")
            inp.border_subtitle = "↑↓ pick · Enter to add · Esc to cancel"
        except Exception:
            pass

    def show_hint(self, msg: str):
        try:
            self.query_one("#yt-hint", Label).update(msg)
        except Exception:
            pass

    def get_selected_result(self) -> dict | None:
        try:
            rl = self.query_one("#yt-results", ListView)
            item = rl.highlighted_child
            if isinstance(item, YTResultItem):
                return item.result
        except Exception:
            pass
        return None

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.hide()
            # Return focus to queue or dir list
            try:
                self.app.query_one("#dir-list").focus()
            except Exception:
                pass
            event.stop()
