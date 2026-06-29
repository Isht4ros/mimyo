"""Queue display widgets: QueueItem list row and NowPlaying bar."""
from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Label, ListItem, Static

from ..track import Track, YouTubeTrack
from ..utils import format_time


class QueueItem(ListItem):
    def __init__(self, track: Track, index: int, playing: bool = False):
        self.track = track
        self.track_index = index
        self._playing = playing
        yt_badge = " ▶YT" if isinstance(track, YouTubeTrack) else ""
        self._yt_badge = yt_badge
        prefix = Label("▶" if playing else " ", classes="queue-item-prefix")
        num = Label(f"{index+1:>2}.", classes="queue-item-num")
        self._title_label = Label(track.title + yt_badge, classes="queue-item-title")
        artist = Label(track.artist[:20], classes="queue-item-artist")
        album = Label(track.album[:20], classes="queue-item-album")
        dur = Label(format_time(track.duration), classes="queue-item-dur")
        row = Horizontal(prefix, num, self._title_label, artist, album, dur)
        super().__init__(row)

    def update_number(self, index: int) -> None:
        """Update the displayed number after reindexing."""
        try:
            self.query_one(".queue-item-num", Label).update(f"{index+1:>2}.")
        except Exception:
            pass

    def update_playing(self, playing: bool) -> None:
        """Toggle the playing state without rebuilding the DOM node."""
        self._playing = playing
        try:
            prefix_label = self.query_one(".queue-item-prefix", Label)
            prefix_label.update("▶" if playing else " ")
        except Exception:
            pass
        if playing:
            self.add_class("playing")
        else:
            self.remove_class("playing")

    def on_resize(self) -> None:
        self._truncate_title()

    def on_mount(self) -> None:
        self._truncate_title()

    def _truncate_title(self) -> None:
        try:
            title_w = self._title_label.content_region.width
            # Guard against unreliable pre-layout measurements. A real title
            # column is at least ~10 cells wide; anything smaller means layout
            # hasn't settled yet and we'd produce spurious "..." prefixes.
            if title_w < 10:
                return
            full = self.track.title + self._yt_badge

            def display_len(s):
                w = 0
                for ch in s:
                    w += 2 if ord(ch) > 0x2E7F else 1
                return w

            def truncate(s, max_w):
                w = 0
                out = []
                for ch in s:
                    cw = 2 if ord(ch) > 0x2E7F else 1
                    if w + cw > max_w - 3:
                        result = "".join(out) + "..."
                        # Only truncate if it actually saves space
                        return result if display_len(result) < display_len(s) else s
                    out.append(ch)
                    w += cw
                return "".join(out)

            if display_len(full) > title_w:
                self._title_label.update(truncate(full, title_w))
            else:
                self._title_label.update(full)
        except Exception:
            pass


class NowPlaying(Static):
    title_text: reactive[str] = reactive("No track playing")
    artist_text: reactive[str] = reactive("")
    album_text: reactive[str] = reactive("")
    status: reactive[str] = reactive("■  stopped")

    def compose(self) -> ComposeResult:
        yield Label("", id="np-title")
        with Horizontal(id="np-meta-row"):
            yield Label("", id="np-artist")
            yield Label("", id="np-album")
        with Horizontal(id="np-progress-row"):
            yield Label("0:00", id="np-time")
            yield Static("", id="np-bar")
            yield Label("0:00", id="np-duration")
            yield Label("■  stopped", id="np-status")
            yield Label("vol 5%", id="np-vol")
            yield Label("", id="yt-progress")

    def watch_title_text(self, val: str):
        try:
            from rich.text import Text
            label = self.query_one("#np-title", Label)
            if val == "No track playing":
                label.update(val)
                label.add_class("placeholder")
            else:
                t = Text()
                t.append(val, style="bold")
                label.update(t)
                label.remove_class("placeholder")
        except NoMatches:
            pass

    def watch_artist_text(self, val: str):
        try:
            self.query_one("#np-artist", Label).update(val + (" · " if val else ""))
        except NoMatches:
            pass

    def watch_album_text(self, val: str):
        try:
            self.query_one("#np-album", Label).update(val if val else "Unknown")
        except NoMatches:
            pass

    def update_progress(self, pos: float, dur: float):
        """Called by the player thread with the authoritative position."""
        self._last_pos = pos
        self._last_dur = dur
        self._anchor_pos = pos
        self._anchor_time = time.monotonic()
        self._playing = (self.status == "▶  playing")
        try:
            self.query_one("#np-time", Label).update(format_time(pos))
            self.query_one("#np-duration", Label).update(format_time(dur))
        except NoMatches:
            pass

    def watch_status(self, val: str):
        try:
            self.query_one("#np-status", Label).update(val)
        except NoMatches:
            pass
        # Pause/resume interpolation when playback state changes
        self._playing = (val == "▶  playing")
        if self._playing:
            self._anchor_pos = getattr(self, "_last_pos", 0)
            self._anchor_time = time.monotonic()

    def _smooth_tick(self) -> None:
        """Fires every 100 ms to interpolate the seek bar between player ticks."""
        dur = getattr(self, "_last_dur", 0)
        if dur <= 0:
            self._render_seek_bar(0, 0)
            return

        if getattr(self, "_playing", False):
            elapsed = time.monotonic() - getattr(self, "_anchor_time", time.monotonic())
            pos = min(getattr(self, "_anchor_pos", 0) + elapsed, dur)
        else:
            pos = getattr(self, "_last_pos", 0)

        self._render_seek_bar(pos, dur)

    def _render_seek_bar(self, pos: float, dur: float):
        try:
            bar = self.query_one("#np-bar", Static)
            width = bar.content_size.width
            if width < 4:
                self.call_after_refresh(self._render_seek_bar, pos, dur)
                return

            track_w = width - 1
            filled = int((pos / dur) * track_w) if dur > 0 else 0
            filled = max(0, min(filled, track_w))
            empty  = track_w - filled

            try:
                def _hex(c, fb):
                    try:
                        return f"#{int(c.r):02x}{int(c.g):02x}{int(c.b):02x}"
                    except Exception:
                        return fb
                fill_color = _hex(bar.app.query_one("#np-title").styles.color, "#89b4fa")
                knob_color = _hex(bar.app.query_one("#np-artist").styles.color, "#cba6f7")
            except Exception:
                fill_color = "#89b4fa"
                knob_color = "#cba6f7"

            if dur > 0:
                markup = (
                    f"[{fill_color}]{'━' * filled}[/]"
                    f"[{knob_color}]╸[/]"
                    f"[#45475a]{'━' * empty}[/]"
                )
            else:
                markup = f"[{knob_color}]╸[/][#45475a]{'━' * (track_w)}[/]"

            bar.update(markup)
        except Exception:
            pass

    def on_mount(self):
        self._anchor_pos  = 0.0
        self._anchor_time = time.monotonic()
        self._playing     = False
        self.call_after_refresh(self._render_seek_bar, 0, 0)
        self.set_interval(0.1, self._smooth_tick)

    def on_resize(self):
        pos = getattr(self, "_last_pos", 0)
        dur = getattr(self, "_last_dur", 0)
        self._render_seek_bar(pos, dur)