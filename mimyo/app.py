"""PlayerApp — the main Textual application."""
from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
import heapq
from collections import defaultdict
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
    _APP_VERSION = _pkg_version("mimyo")
except Exception:
    import re as _re
    _here = Path(__file__).resolve()
    _toml = next(
        (p / "pyproject.toml" for p in [_here.parent, _here.parent.parent]
         if (p / "pyproject.toml").exists()),
        None,
    )
    _match = _re.search(r'^version\s*=\s*"([^"]+)"', _toml.read_text(), _re.MULTILINE) if _toml else None
    _APP_VERSION = _match.group(1) if _match else "unknown"

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

if "--version" in sys.argv:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError
    try:
        _v = _pkg_version("mimyo")
    except PackageNotFoundError:
        # Fallback: read version from pyproject.toml relative to this file
        import re as _re
        _here = Path(__file__).resolve()
        _toml = next(
            (p / "pyproject.toml" for p in [_here.parent, _here.parent.parent]
             if (p / "pyproject.toml").exists()),
            None,
        )
        _match = _re.search(r'^version\s*=\s*"([^"]+)"', _toml.read_text(), _re.MULTILINE) if _toml else None
        _v = _match.group(1) if _match else "unknown"
    print(f"version {_v}")
    sys.exit(0)

from .config import (
    CONFIG_DIR, PLAYLISTS_FILE, SPINNER_FRAMES, SUPPORTED,
    _restore_terminal, load_settings, save_settings,
)
from .deps import PYGAME_AVAILABLE, PYPRESENCE_AVAILABLE, YTDLP_AVAILABLE, Presence, pygame
from .player import Player
from .rendering.art import AlbumArtWidget
from .widgets.quit_modal import QuitModal
from .track import Track, YouTubeTrack
from .utils import find_music_dir, format_time
from .widgets.bars import PlaylistBar, SearchBar
from .widgets.keybinds import KeybindOverlay
from .widgets.queue import NowPlaying, QueueItem
from .widgets.youtube import YoutubeBar, fetch_youtube_audio


# ── Sidebar helper widgets ────────────────────────────────────────────────────

class DirItem(ListItem):
    def __init__(self, path: Path, label: str):
        super().__init__(Label(label))
        self.path = path


class SidebarTabs(Static):
    """Segmented Library / Playlists tab bar."""
    DEFAULT_CSS = (
        "SidebarTabs { height: 2; width: 1fr; } "
        "SidebarTabs Horizontal { width: 1fr; height: 1; }"
    )

    def compose(self) -> ComposeResult:
        with Horizontal(id="sidebar-tab-row"):
            yield Label(" Library", id="tab-library", classes="sidebar-tab tab-active")
            yield Label(" Playlists", id="tab-playlists", classes="sidebar-tab")


class PlaylistItem(ListItem):
    def __init__(self, name: str, count: int):
        super().__init__(Label(f"♪ {name} ({count} tracks)"))
        self.playlist_name = name


# ── Splash screen ─────────────────────────────────────────────────────────────

class SplashScreen(Static):
    """Full-screen splash shown briefly on startup."""

    LOGO = (
        "                                                                                      \n"
        "     ______  _______    ____      ______  _______    _____      _____        _____    \n"
        "    |      \\/       \\  |    |    |      \\/       \\  |\\    \\    /    /|  ____|\\    \\   \n"
        "   /          /\\     \\ |    |   /          /\\     \\ | \\    \\  /    / | /     /\\    \\  \n"
        "  /     /\\   / /\\     ||    |  /     /\\   / /\\     ||  \\____\\/    /  //     /  \\    \\ \n"
        " /     /\\ \\_/ / /    /||    | /     /\\ \\_/ / /    /| \\ |    /    /  /|     |    |    |\n"
        "|     |  \\|_|/ /    / ||    ||     |  \\|_|/ /    / |  \\|___/    /  / |     |    |    |\n"
        "|     |       |    |  ||    ||     |       |    |  |      /    /  /  |\\     \\  /    /|\n"
        "|\\____\\       |____|  /|____||\\____\\       |____|  /     /____/  /   | \\_____\\/____/ |\n"
        "| |    |      |    | / |    || |    |      |    | /     |`    | /     \\ |    ||    | /\n"
        " \\|____|      |____|/  |____| \\|____|      |____|/      |_____|/       \\|____||____|/ \n"
        "                                                                                      \n"
        "                                                                                      "
    )

    BAR_CHAR = "━"
    BAR_LEN = 32

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-inner"):
            yield Label(self.LOGO, id="splash-logo")
            yield Label(f"terminal music player  ·  v{_APP_VERSION}", id="splash-sub")
            yield Label(self.BAR_CHAR * self.BAR_LEN, id="splash-bar")

    def on_mount(self) -> None:
        self._bar_filled = 0
        self.set_interval(0.05, self._tick_bar)

    @staticmethod
    def _splash_colors() -> tuple[str, str]:
        """Parse splash bar fill color and empty color from theme.css.

        Looks for a $splash-bar-color variable at the top of the file first;
        falls back to reading the #splash-logo color for backwards compat.
        Empty color comes from SplashScreen background.
        Returns (filled_color, empty_color) as hex strings.
        """
        import re
        defaults = ("#7e9cd8", "#2a2a37")
        try:
            css_path = Path(__file__).parent / "theme.css"
            css = css_path.read_text(encoding="utf-8", errors="replace")

            # Prefer the explicit $splash-bar-color variable
            var_match = re.search(
                r"^\$splash-bar-color\s*:\s*(#[0-9a-fA-F]{6})",
                css, re.MULTILINE
            )
            if var_match:
                filled = var_match.group(1)
            else:
                # Fallback: use #splash-logo color
                logo_block = re.search(r"#splash-logo\s*\{([^}]*)\}", css)
                filled = "#7e9cd8"
                if logo_block:
                    m = re.search(r"color\s*:\s*(#[0-9a-fA-F]{6})", logo_block.group(1))
                    if m:
                        filled = m.group(1)

            # Extract background inside SplashScreen { ... } block
            splash_block = re.search(r"SplashScreen\s*\{([^}]*)\}", css)
            empty = "#2a2a37"
            if splash_block:
                m = re.search(r"background\s*:\s*(#[0-9a-fA-F]{6})", splash_block.group(1))
                if m:
                    empty = m.group(1)

            return filled, empty
        except Exception:
            return defaults

    def _tick_bar(self) -> None:
        if self._bar_filled >= self.BAR_LEN:
            return
        # Parse colors once on the first tick and cache them.
        if not hasattr(self, "_bar_colors"):
            self._bar_colors = self._splash_colors()
        self._bar_filled += 1
        try:
            fc, ec = self._bar_colors
            bar_widget = self.query_one("#splash-bar", Label)
            bar_widget.update(
                f"[{fc}]{self.BAR_CHAR * self._bar_filled}[/]"
                f"[{ec}]{self.BAR_CHAR * (self.BAR_LEN - self._bar_filled)}[/]"
            )
        except Exception:
            pass


# ── Main app ──────────────────────────────────────────────────────────────────

class PlayerApp(App):
    CSS_PATH = str(Path(__file__).parent / "theme.css")
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+c", "noop", show=False),
        Binding("q", "confirm_quit", show=False),
        Binding("space", "toggle_pause"),
        Binding(">", "next_track"),
        Binding("<", "prev_track"),
        Binding("enter", "play_selected"),
        Binding("a", "add_to_queue"),
        Binding("x", "remove_from_queue"),
        Binding("c", "clear_queue"),
        Binding("r", "toggle_repeat"),
        Binding("s", "toggle_shuffle"),
        Binding("right", "seek_forward"),
        Binding("left", "seek_backward"),
        Binding("y", "youtube"),
        Binding("-", "vol_down"),
        Binding("=", "vol_up"),
        Binding("tab", "switch_panel"),
        Binding("o", "open_home"),
        Binding("z", "random_queue"),
        Binding("f", "save_playlist"),
        Binding("1", "sidebar_library", "Library"),
        Binding("2", "sidebar_playlists", "Playlists"),
        Binding("/", "search_library"),
        Binding("question_mark", "show_keybinds", "Guide"),
    ]

    TITLE = "Mimyo — Terminal Music player"

    def __init__(self):
        super().__init__()
        # Instance attributes (avoids mutable class-level defaults)
        self.queue: list[Track] = []
        self.current_index: int = -1
        self.repeat: bool = False
        self.shuffle: bool = False
        self.active_panel: str = "dirs"
        self.music_dir: Path = find_music_dir()
        self.dirs_listing: list[Path] = []
        self.sidebar_tab: str = "library"
        self.playlists: dict = {}

        self.player = Player()
        self._yt_spinner_timer = None
        self._yt_spinner_idx = 0
        self._yt_status_suffix = ""
        self._shuffle_order: list[int] = []
        self._shuffle_pos: int = 0
        self.rpc: "Presence | None" = None
        if PYPRESENCE_AVAILABLE:
            threading.Thread(target=self._connect_rpc, daemon=True).start()

    def _connect_rpc(self):
        try:
            rpc = Presence("1517665697998831726")
            rpc.connect()
            self.rpc = rpc
        except Exception:
            self.rpc = None

    def compose(self) -> ComposeResult:
        yield SplashScreen(id="splash")
        yield Header(show_clock=True)
        with Horizontal(id="layout"):
            with Vertical(id="left-col"):
                with Vertical(id="art-panel"):
                    yield AlbumArtWidget(id="album-art")
                    yield Label("no art", id="art-label")
                    yield Static("", id="art-mouse-shield")
                with Vertical(id="sidebar"):
                    yield SidebarTabs(id="sidebar-tabs")
                    yield ListView(id="dir-list")
            with Vertical(id="right-col"):
                yield Label(" 🎵 Queue", id="queue-title")
                with Horizontal(id="queue-header"):
                    yield Label(" ", id="qh-prefix")
                    yield Label(" # ", id="qh-num")
                    yield Label("Title", id="qh-title")
                    yield Label("Artist", id="qh-artist")
                    yield Label("Album", id="qh-album")
                    yield Label("  ◷", id="qh-dur")
                yield ListView(id="queue-list")
                yield NowPlaying(id="now-playing")
                yield PlaylistBar(id="playlist-bar")
                yield YoutubeBar(id="yt-bar")
                yield SearchBar(id="search-bar")
                yield KeybindOverlay(id="keybind-overlay")
                yield QuitModal(id="quit-modal")
        yield Footer()

    def on_mount(self):
        settings = load_settings()
        initial_volume = settings.get("volume", 0.5)
        self.player.set_volume(initial_volume)
        self._load_playlists()
        self._load_dir(self.music_dir)
        self.set_interval(0.5, self._tick)
        self.query_one("#dir-list").focus()
        self.query_one("#np-vol", Label).display = False
        self.set_timer(1.8, self._dismiss_splash)

    def _dismiss_splash(self):
        try:
            self.query_one("#splash", SplashScreen).remove()
        except NoMatches:
            pass

    # ── Directory / library ───────────────────────────────────────────────────

    def _load_dir(self, path: Path):
        self.music_dir = path
        lv = self.query_one("#dir-list", ListView)
        lv.clear()
        self.dirs_listing = []

        if path.parent != path:
            lv.append(DirItem(path.parent, "📁 .."))
            self.dirs_listing.append(path.parent)

        try:
            entries = sorted(path.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if entry.is_dir():
                lv.append(DirItem(entry, f"📁 {entry.name}"))
                self.dirs_listing.append(entry)

        for entry in entries:
            if entry.suffix.lower() in SUPPORTED:
                lv.append(DirItem(entry, f"🎵 {entry.stem[:20]}"))
                self.dirs_listing.append(entry)

    # ── Queue ─────────────────────────────────────────────────────────────────

    def _rebuild_queue_list(self):
        lv = self.query_one("#queue-list", ListView)
        lv.clear()
        for i, track in enumerate(self.queue):
            playing = i == self.current_index
            item = QueueItem(track, i, playing=playing)
            if playing:
                item.add_class("playing")
            lv.append(item)

    def _update_queue_playing(self):
        """Update the playing indicator in-place without clearing the list.

        Falls back to a full rebuild only when the number of items in the
        ListView no longer matches the queue (i.e. tracks were added/removed).
        """
        lv = self.query_one("#queue-list", ListView)
        items = list(lv.query(QueueItem))
        if len(items) != len(self.queue):
            self._rebuild_queue_list()
            return
        for i, item in enumerate(items):
            item.update_playing(i == self.current_index)

    def _update_art(self, track: Track | None):
        art_widget = self.query_one("#album-art", AlbumArtWidget)
        art_label = self.query_one("#art-label", Label)
        art_widget.set_track(track)
        if track:
            img = track.get_art()
            art_label.update(track.album[:22] if img else "no album art")
        else:
            art_label.update("no art")

    def _play_index(self, idx: int, _skips: int = 0):
        if not self.queue or idx < 0 or idx >= len(self.queue):
            return
        track = self.queue[idx]

        if not track.path.exists() or not self.player.load(track):
            self.notify(f"Skipping (file not found): {track.title}", severity="warning")
            next_idx = idx + 1
            if _skips < len(self.queue) and next_idx < len(self.queue):
                self._play_index(next_idx, _skips + 1)
            else:
                self.player.stop()
                self.current_index = idx
                self._rebuild_queue_list()
                self.query_one("#now-playing", NowPlaying).status = "■  stopped"
            return

        self.current_index = idx
        np = self.query_one("#now-playing", NowPlaying)
        np.title_text = track.title
        np.artist_text = track.artist
        np.album_text = track.album
        np.status = "▶  playing"
        self._update_queue_playing()
        threading.Thread(target=self._load_art_bg, args=(track,), daemon=True).start()

        def _delayed_rpc():
            time.sleep(2)
            self._update_rpc(force=True)
        threading.Thread(target=_delayed_rpc, daemon=True).start()

    def _load_art_bg(self, track: Track):
        track.get_art()
        self.call_from_thread(self._update_art, track)
        self.call_from_thread(self._clear_unused_art, track)

    def _clear_unused_art(self, current_track: Track):
        for t in self.queue:
            if t is not current_track and t._art is not False and t._art is not None:
                t._art = False

    def _tick(self):
        try:
            art = self.query_one("#album-art", AlbumArtWidget)
            if art._sixel_bytes:
                art._sixel_dirty = True
        except Exception:
            pass
        # Reposition keybind overlay if visible and parent width changed
        try:
            overlay = self.query_one("#keybind-overlay", KeybindOverlay)
            if overlay.display:
                right_col = self.query_one("#right-col")
                pw = right_col.content_size.width
                if pw != getattr(self, "_last_right_col_w", None):
                    self._last_right_col_w = pw
                    overlay.call_after_refresh(overlay._reposition)
        except Exception:
            pass
        if self.player.current is None:
            return
        np = self.query_one("#now-playing", NowPlaying)
        np.update_progress(self.player.position, self.player.current.duration)
        if self.player.finished():
            self._auto_next()
        self._update_rpc()

    # ── Shuffle ───────────────────────────────────────────────────────────────

    def _build_shuffle_order(self):
        """
        Generate a shuffled playthrough order covering every track exactly once,
        avoiding same-artist adjacency whenever it's mathematically possible.

        Uses a round-robin/max-heap approach (same family as LeetCode's "Task
        Scheduler" / "Reorganize String" problem): tracks are bucketed by
        artist, shuffled within each bucket, then interleaved by always
        pulling from the artist with the most remaining tracks (skipping the
        one just played). A naive "shuffle then swap adjacent forward" approach
        fails whenever same-artist tracks get pushed to the tail with nothing
        left to swap against — this guarantees correctness instead.
        """
        n = len(self.queue)
        if n == 0:
            self._shuffle_order = []
            self._shuffle_pos = 0
            return
        if n == 1:
            self._shuffle_order = [0]
            self._shuffle_pos = 0
            return

        buckets: dict[str, list[int]] = defaultdict(list)
        for i, t in enumerate(self.queue):
            key = t.artist.lower() if t.artist else f"__blank_{i}"
            buckets[key].append(i)
        for b in buckets.values():
            random.shuffle(b)

        heap = [(-len(idxs), artist, idxs) for artist, idxs in buckets.items()]
        heapq.heapify(heap)

        result: list[int] = []
        prev_artist: str | None = None
        deferred = None

        while heap or deferred:
            if deferred:
                heapq.heappush(heap, deferred)
                deferred = None
            if not heap:
                break

            count, artist, idxs = heapq.heappop(heap)
            if artist == prev_artist and heap:
                deferred = (count, artist, idxs)
                count, artist, idxs = heapq.heappop(heap)

            chosen = idxs.pop(0)
            result.append(chosen)
            prev_artist = artist
            if idxs:
                heapq.heappush(heap, (count + 1, artist, idxs))

        self._shuffle_order = result
        self._shuffle_pos = 0

    def _smart_shuffle_pick(self) -> int:
        """Return next index from the pre-built shuffle order, reshuffling when exhausted."""
        if not self._shuffle_order or self._shuffle_pos >= len(self._shuffle_order):
            self._build_shuffle_order()
        idx = self._shuffle_order[self._shuffle_pos]
        self._shuffle_pos += 1
        return idx

    def _auto_next(self):
        if not self.queue:
            return
        if self.shuffle:
            idx = self._smart_shuffle_pick()
        elif self.repeat:
            idx = self.current_index
        else:
            idx = self.current_index + 1
            if idx >= len(self.queue):
                return
        self._play_index(idx)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_toggle_pause(self):
        if self.player.current is None and self.queue:
            self._play_index(0)
            return
        self.player.toggle_pause()
        np = self.query_one("#now-playing", NowPlaying)
        np.status = "⏸  paused" if self.player.is_paused else "▶  playing"
        self._update_rpc(force=True)

    def action_seek_forward(self):
        if not PYGAME_AVAILABLE or self.player.current is None:
            return
        pos = min(self.player.position + 5, self.player.current.duration - 1)
        pygame.mixer.music.set_pos(pos)
        self.player._start_time = time.time() - pos

    def action_seek_backward(self):
        if not PYGAME_AVAILABLE or self.player.current is None:
            return
        pos = max(self.player.position - 5, 0)
        pygame.mixer.music.set_pos(pos)
        self.player._start_time = time.time() - pos

    def action_next_track(self):
        idx = self._smart_shuffle_pick() if self.shuffle else self.current_index + 1
        if idx < len(self.queue):
            self._play_index(idx)

    def action_prev_track(self):
        if self.current_index - 1 >= 0:
            self._play_index(self.current_index - 1)

    def action_play_selected(self):
        pass

    def action_add_to_queue(self):
        lv = self.query_one("#dir-list", ListView)
        if lv.highlighted_child is None:
            return
        item = lv.highlighted_child
        if isinstance(item, DirItem) and item.path.suffix.lower() in SUPPORTED:
            track = Track(item.path)
            self.queue.append(track)
            self._rebuild_queue_list()
            self.notify(f"Added: {track.title}")
            if self.shuffle:
                self._build_shuffle_order()

    def action_remove_from_queue(self):
        focused = self.focused
        dir_lv = self.query_one("#dir-list", ListView)
        queue_lv = self.query_one("#queue-list", ListView)

        if focused is dir_lv:
            item = dir_lv.highlighted_child
            if isinstance(item, PlaylistItem):
                name = item.playlist_name
                del self.playlists[name]
                self._save_playlists()
                self._rebuild_playlists_list()
                self.notify(f"Deleted playlist: {name}")
            return

        if queue_lv.highlighted_child is None:
            return
        item = queue_lv.highlighted_child
        if isinstance(item, QueueItem):
            idx = item.track_index
            if idx < 0 or idx >= len(self.queue):
                return
            was_playing_this = (idx == self.current_index)
            removed = self.queue.pop(idx)
            removed._art = False
            if self.current_index >= idx:
                self.current_index = max(-1, self.current_index - 1)
            if was_playing_this:
                self.player.stop()
                self._update_art(None)
                np = self.query_one("#now-playing", NowPlaying)
                if self.queue:
                    self._play_index(min(idx, len(self.queue) - 1))
                else:
                    self.current_index = -1
                    np.title_text = "No track playing"
                    np.artist_text = ""
                    np.album_text = ""
                    np.status = "■  stopped"
                    np.update_progress(0, 0)
            new_idx = min(idx, len(self.queue) - 1)
            if self.shuffle:
                self._build_shuffle_order()
            if was_playing_this:
                # Full rebuild needed since playing state changed substantially
                self._rebuild_queue_list()
                if new_idx >= 0:
                    def _restore_playing(i=new_idx, lv=queue_lv):
                        lv.focus()
                        lv.index = i
                    self.set_timer(0.05, _restore_playing)
            else:
                # Remove just the one item — no full clear/rebuild so no blink
                queue_lv.remove_items([idx])
                # Update track_index on remaining items so they stay in sync
                for child in queue_lv.query(QueueItem):
                    if child.track_index > idx:
                        child.track_index -= 1
                    child.update_number(child.track_index)
                    child.update_playing(child.track_index == self.current_index)
                if new_idx >= 0:
                    def _restore(i=new_idx, lv=queue_lv):
                        lv.focus()
                        lv.index = i
                    self.set_timer(0.05, _restore)

    def action_clear_queue(self):
        self.player.stop()
        for t in self.queue:
            t._art = False
        self.queue.clear()
        self.current_index = -1
        self._shuffle_order.clear()
        self._shuffle_pos = 0
        self._rebuild_queue_list()
        self._update_art(None)
        np = self.query_one("#now-playing", NowPlaying)
        np.title_text = "No track playing"
        np.artist_text = ""
        np.album_text = ""
        np.status = "■  stopped"
        np.update_progress(0, 0)
        self._clear_rpc()

    def action_toggle_repeat(self):
        self.repeat = not self.repeat
        self.notify(f"Repeat: {'on' if self.repeat else 'off'}")

    def action_toggle_shuffle(self):
        self.shuffle = not self.shuffle
        if self.shuffle:
            self._build_shuffle_order()
        else:
            self._shuffle_order.clear()
            self._shuffle_pos = 0
        self.notify(f"Shuffle: {'on' if self.shuffle else 'off'}")

    def action_random_queue(self):
        pool = [p for p in self.music_dir.rglob("*") if p.suffix.lower() in SUPPORTED]
        if not pool:
            self.notify("No tracks found in this folder")
            return
        picks = random.sample(pool, min(25, len(pool)))
        self.player.stop()
        self.queue = [Track(p) for p in picks]
        self.current_index = -1
        self._rebuild_queue_list()
        if not self.shuffle:
            self.shuffle = True
            self.notify(f"Queued {len(self.queue)} random tracks · Shuffle on")
        else:
            self.notify(f"Queued {len(self.queue)} random tracks")
        self._play_index(0)

    def action_vol_up(self):
        v = min(1.0, self.player.get_volume() + 0.05)
        self.player.set_volume(v)
        save_settings({"volume": v})
        self._show_vol(v)

    def action_vol_down(self):
        v = max(0.0, self.player.get_volume() - 0.05)
        self.player.set_volume(v)
        save_settings({"volume": v})
        self._show_vol(v)

    def _show_vol(self, v: float):
        try:
            label = self.query_one("#np-vol", Label)
            label.update(f"vol {int(v*100)}%")
            label.display = True
            if hasattr(self, "_vol_timer") and self._vol_timer:
                self._vol_timer.stop()
            self._vol_timer = self.set_timer(2.0, self._hide_vol)
        except NoMatches:
            pass

    def _hide_vol(self):
        try:
            self.query_one("#np-vol", Label).display = False
        except NoMatches:
            pass

    def action_switch_panel(self):
        if self.active_panel == "dirs":
            self.active_panel = "queue"
            self.query_one("#queue-list").focus()
        else:
            self.active_panel = "dirs"
            self.query_one("#dir-list").focus()

    def action_open_home(self):
        self._load_dir(find_music_dir())
        self.query_one("#dir-list").focus()
        self.active_panel = "dirs"

    def action_sidebar_library(self):
        self._switch_sidebar_tab("library")

    def action_sidebar_playlists(self):
        self._switch_sidebar_tab("playlists")

    def _switch_sidebar_tab(self, tab: str):
        self.sidebar_tab = tab
        try:
            lib = self.query_one("#tab-library", Label)
            fav = self.query_one("#tab-playlists", Label)
            if tab == "library":
                lib.add_class("tab-active")
                fav.remove_class("tab-active")
                self._load_dir(self.music_dir)
            else:
                fav.add_class("tab-active")
                lib.remove_class("tab-active")
                self._rebuild_playlists_list()
        except NoMatches:
            pass

    def action_save_playlist(self):
        if not self.queue:
            self.notify("Queue is empty — nothing to save", severity="warning")
            return
        bar = self.query_one("#playlist-bar", PlaylistBar)
        if "visible" in bar.classes:
            bar.hide()
        else:
            bar.show()

    def action_search_library(self):
        bar = self.query_one("#search-bar", SearchBar)
        if "visible" in bar.classes:
            bar.hide()
        else:
            bar.show()

    def action_show_keybinds(self) -> None:
        overlay = self.query_one("#keybind-overlay", KeybindOverlay)
        if overlay.display:
            overlay.hide()
        else:
            overlay.show()

    def action_noop(self) -> None:
        pass

    def action_confirm_quit(self) -> None:
        modal = self.query_one("#quit-modal", QuitModal)
        modal.show()

    def on_key(self, event) -> None:
        # Handle quit modal keys first
        try:
            modal = self.query_one("#quit-modal", QuitModal)
            if modal.display:
                if event.key == "enter":
                    modal.hide()
                    self.exit()
                    event.stop()
                    return
                elif event.key == "escape":
                    modal.hide()
                    event.stop()
                    return
        except NoMatches:
            pass

        if event.key == "escape":
            try:
                overlay = self.query_one("#keybind-overlay", KeybindOverlay)
                if overlay.display:
                    overlay.hide()
                    event.stop()
            except NoMatches:
                pass

    def action_youtube(self):
        if not YTDLP_AVAILABLE:
            self.notify("yt-dlp not installed — run: pip install yt-dlp", severity="error")
            return
        bar = self.query_one("#yt-bar", YoutubeBar)
        if "visible" in bar.classes:
            bar.hide()
        else:
            bar.show()

    # ── Playlists ─────────────────────────────────────────────────────────────

    def _load_playlists(self):
        try:
            data = json.loads(PLAYLISTS_FILE.read_text(encoding="utf-8"))
            self.playlists = data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.playlists = {}

    def _save_playlists(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            PLAYLISTS_FILE.write_text(json.dumps(self.playlists, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _rebuild_playlists_list(self):
        lv = self.query_one("#dir-list", ListView)
        lv.clear()
        if not self.playlists:
            lv.append(ListItem(Label(" ♪ No playlists yet — press F to save queue")))
            return
        for name, paths in self.playlists.items():
            lv.append(PlaylistItem(name, len(paths)))

    # ── Discord RPC ───────────────────────────────────────────────────────────

    def _update_rpc(self, force: bool = False):
        if not self.rpc or not self.player.current:
            return
        t = self.player.current
        now = time.time()
        last_title = getattr(self, "_rpc_last_title", None)
        last_update = getattr(self, "_rpc_last_update", 0)
        track_changed = last_title != t.title
        if not force and not track_changed and (now - last_update) < 15:
            return

        def _do_update():
            try:
                if self.player.is_paused:
                    self.rpc.update(
                        details=t.title,
                        state=f"{t.artist} · {t.album}",
                        large_image="player_logo",
                        large_text="mimyo",
                        small_image="pause",
                        small_text="Paused",
                    )
                else:
                    self.rpc.update(
                        details=t.title,
                        state=f"{t.artist} · {t.album}",
                        large_image="player_logo",
                        large_text="mimyo",
                        start=int(time.time() - self.player.position),
                        end=int(time.time() + (t.duration - self.player.position)),
                        small_image="play",
                        small_text="Playing",
                    )
                self._rpc_last_title = t.title
                self._rpc_last_update = time.time()
            except Exception:
                pass

        threading.Thread(target=_do_update, daemon=True).start()

    def _clear_rpc(self):
        if not self.rpc:
            return
        self._rpc_last_title = None
        self._rpc_last_update = 0

        def _do_clear():
            try:
                self.rpc.clear()
            except Exception:
                pass

        threading.Thread(target=_do_clear, daemon=True).start()

    # ── YouTube spinner ───────────────────────────────────────────────────────

    def _yt_spinner_start(self):
        self._yt_spinner_idx = 0
        if self._yt_spinner_timer is None:
            self._yt_spinner_timer = self.set_interval(0.08, self._yt_spinner_tick)

    def _yt_spinner_stop(self):
        if self._yt_spinner_timer is not None:
            self._yt_spinner_timer.stop()
            self._yt_spinner_timer = None

    def _yt_spinner_tick(self):
        self._yt_spinner_idx = (self._yt_spinner_idx + 1) % len(SPINNER_FRAMES)
        self._render_yt_status()

    def _yt_download(self, url: str):
        """Download a YouTube URL in a background thread and add it to the queue."""
        def _set_status(msg: str):
            self._yt_status_suffix = msg
            if msg:
                self._yt_spinner_start()
                self._render_yt_status()
            else:
                self._yt_spinner_stop()
                try:
                    self.query_one("#yt-progress", Label).update("")
                except Exception:
                    pass

        _set_status("Starting download…")

        def _download():
            def _progress(msg: str):
                self.call_from_thread(_set_status, msg)

            result = fetch_youtube_audio(url, on_progress=_progress)
            if result is None or isinstance(result, str):
                err = result or "Failed to fetch YouTube audio"
                self.call_from_thread(_set_status, "")
                self.call_from_thread(self.notify, f"YouTube error: {err}", severity="error")
                return
            path, title, duration, thumb_path = result
            track = YouTubeTrack(path, title, duration, thumb_path)

            def _add():
                _set_status("")
                self.queue.append(track)
                self._rebuild_queue_list()
                self.notify(f"Added: {title}")
                if self.player.current is None:
                    self._play_index(len(self.queue) - 1)

            self.call_from_thread(_add)

        threading.Thread(target=_download, daemon=True).start()

    def _render_yt_status(self):
        try:
            label = self.query_one("#yt-progress", Label)
            if self._yt_status_suffix:
                frame = SPINNER_FRAMES[self._yt_spinner_idx]
                label.update(f"{frame} {self._yt_status_suffix}")
            else:
                label.update("")
        except NoMatches:
            pass

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "queue-list":
            return
        for child in event.list_view.query(QueueItem):
            child.styles.background = None
        item = event.item
        if item is None:
            return
        if isinstance(item, QueueItem) and "playing" in item.classes:
            try:
                bg = self.query_one("ListView > ListItem.playing.--highlight").styles.background
                item.styles.background = f"#{int(bg.r):02x}{int(bg.g):02x}{int(bg.b):02x}"
            except Exception:
                item.styles.background = "#2d4f67"

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        from .widgets.youtube import YTResultItem
        if event.list_view.id == "yt-results":
            item = event.item
            if isinstance(item, YTResultItem):
                result = item.result
                url = result["url"]
                self.query_one("#yt-bar", YoutubeBar).hide()
                try:
                    self.query_one("#queue-list", ListView).focus()
                except Exception:
                    pass
                self._yt_download(url)
            return

        item = event.item
        if isinstance(item, PlaylistItem):
            paths = self.playlists.get(item.playlist_name, [])
            tracks = []
            for p in paths:
                path = Path(p)
                if path.exists():
                    try:
                        tracks.append(Track(path))
                    except Exception:
                        pass
            if not tracks:
                self.notify("Playlist is empty or files missing", severity="warning")
                return
            self.player.stop()
            for t in self.queue:
                t._art = False
            self.queue = tracks
            self.current_index = -1
            self._rebuild_queue_list()
            self.notify(f"Loaded playlist: {item.playlist_name} ({len(tracks)} tracks)")
            self._play_index(0)
            return
        if isinstance(item, DirItem):
            if item.path.is_dir():
                self._load_dir(item.path)
            elif item.path.suffix.lower() in SUPPORTED:
                track = Track(item.path)
                self.queue.append(track)
                self._rebuild_queue_list()
                self._play_index(len(self.queue) - 1)
        elif isinstance(item, QueueItem):
            self._play_index(item.track_index)

    def on_input_submitted(self, event) -> None:
        if event.input.id == "search-input":
            query = event.value.strip()
            self.query_one("#search-bar", SearchBar).hide()
            if query:
                self._do_library_search(query)
                self.active_panel = "dirs"
                self.query_one("#dir-list").focus()
            return

        if event.input.id == "pl-input":
            name = event.value.strip()
            self.query_one("#playlist-bar", PlaylistBar).hide()
            if not name:
                return
            self.playlists[name] = [str(t.path) for t in self.queue]
            self._save_playlists()
            self.notify(f"Saved playlist: {name} ({len(self.queue)} tracks)")
            if self.sidebar_tab == "playlists":
                self._rebuild_playlists_list()
            return

        if event.input.id != "yt-input":
            return

        raw = event.value.strip()
        if not raw:
            return

        # Detect URL vs search query
        is_url = raw.startswith("http://") or raw.startswith("https://") or "youtu.be/" in raw

        if is_url:
            # --- Direct URL: clean and download immediately ---
            url = raw
            if "youtube.com/watch" in url and "v=" in url:
                from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                parsed = urlparse(url)
                qs = parse_qs(parsed.query, keep_blank_values=True)
                if "v" in qs:
                    clean_query = urlencode({"v": qs["v"][0]})
                    url = urlunparse(parsed._replace(query=clean_query))
            self.query_one("#yt-bar", YoutubeBar).hide()
            try:
                self.query_one("#queue-list", ListView).focus()
            except Exception:
                pass
            self._yt_download(url)
        else:
            # --- Search query: fetch results and show picker ---
            bar = self.query_one("#yt-bar", YoutubeBar)
            bar.show_hint("Searching…")

            def _search():
                from .widgets.youtube import search_youtube
                results = search_youtube(raw, max_results=5)
                if isinstance(results, str):
                    self.call_from_thread(self.notify, f"Search error: {results}", severity="error")
                    self.call_from_thread(bar.show_hint, "")
                    return
                if not results:
                    self.call_from_thread(self.notify, "No results found", severity="warning")
                    self.call_from_thread(bar.show_hint, "")
                    return
                self.call_from_thread(bar.show_results, results)
                self.call_from_thread(bar.show_hint, "")

            threading.Thread(target=_search, daemon=True).start()

    # ── Library search ────────────────────────────────────────────────────────

    def _do_library_search(self, query: str):
        """Recursively search the music root for a matching file or folder."""
        query = query.lower().strip()
        if not query:
            return

        lv = self.query_one("#dir-list", ListView)
        for i, p in enumerate(self.dirs_listing):
            if p.suffix.lower() in SUPPORTED and query in p.name.lower():
                self._highlight_index(lv, i)
                return

        search_root = find_music_dir()
        found_dir: Path | None = None
        found_file: Path | None = None
        try:
            for p in search_root.rglob("*"):
                if query not in p.name.lower():
                    continue
                if p.is_dir():
                    found_dir = p
                    break
                if p.suffix.lower() in SUPPORTED and found_file is None:
                    found_file = p
        except Exception:
            pass

        found = found_dir or found_file
        if found is None:
            self.notify(f"No match found for: {query}", severity="warning")
            return

        self._load_dir(found.parent)
        self.active_panel = "dirs"
        lv = self.query_one("#dir-list", ListView)
        target = 0
        for i, p in enumerate(self.dirs_listing):
            if p == found:
                target = i
                break
        self._highlight_index(lv, target)

    def _highlight_index(self, lv: ListView, i: int):
        def _set():
            lv.focus()
            lv.index = i
            self.call_after_refresh(lambda: setattr(lv, "index", i))
        self.call_after_refresh(_set)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_unmount(self) -> None:
        try:
            self.action_clear_queue()
        except Exception:
            pass
        try:
            self.player.shutdown()
        except Exception:
            pass
        if self.rpc:
            try:
                self.rpc.close()
            except Exception:
                pass
        try:
            from .config import YT_CACHE_DIR
            if YT_CACHE_DIR.exists():
                files = [f for f in YT_CACHE_DIR.iterdir() if f.is_file()]
                total = sum(f.stat().st_size for f in files)
                if total > 250 * 1024 * 1024:
                    for f in files:
                        f.unlink(missing_ok=True)
        except Exception:
            pass
        _restore_terminal()

    def on_resize(self) -> None:
        try:
            overlay = self.query_one("#keybind-overlay", KeybindOverlay)
            if overlay.display:
                overlay.call_after_refresh(overlay._reposition)
        except Exception:
            pass
        try:
            yt_bar = self.query_one("#yt-bar", YoutubeBar)
            if "visible" in yt_bar.classes:
                yt_bar.call_after_refresh(yt_bar._reposition)
        except Exception:
            pass
        try:
            pl_bar = self.query_one("#playlist-bar", PlaylistBar)
            if "visible" in pl_bar.classes:
                pl_bar.call_after_refresh(pl_bar._reposition)
        except Exception:
            pass
        try:
            sb = self.query_one("#search-bar", SearchBar)
            if "visible" in sb.classes:
                sb.call_after_refresh(sb._reposition)
        except Exception:
            pass

    def on_app_focus(self) -> None:
        """Repaint sixel art immediately when the terminal window regains focus."""
        try:
            art = self.query_one("#album-art", AlbumArtWidget)
            if art._sixel_bytes:
                art._sixel_dirty = True
                art.refresh()
        except Exception:
            pass

    def post_display_hook(self) -> None:
        """Repaint sixel art after every Textual frame."""
        try:
            art = self.query_one("#album-art", AlbumArtWidget)
            if art._sixel_dirty:
                art._paint_sixel(driver=self._driver)
        except Exception:
            pass


def main() -> None:
    """Console-script / `python -m mimyo` entry point."""
    parser = argparse.ArgumentParser(prog="mimyo", description="A terminal-based music player.")
    parser.add_argument(
        "-p", "--path",
        type=str,
        default=None,
        dest="music_dir",
        metavar="PATH",
        help="Set your music library folder and remember it for future launches "
             "(e.g. --path \"D:\\Music\").",
    )
    args = parser.parse_args()

    if args.music_dir:
        path = Path(args.music_dir).expanduser()
        if not path.exists() or not path.is_dir():
            print(f"Error: '{path}' is not a valid directory.")
            sys.exit(1)
        save_settings({"music_dir": str(path.resolve())})
        print(f"Music folder set to: {path.resolve()}")
        print("Config: music path saved.")

    app = PlayerApp()
    try:
        app.run()
    finally:
        _restore_terminal()


if __name__ == "__main__":
    main()
