"""Overlay input bar widgets: PlaylistBar and SearchBar."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static


class PlaylistBar(Static):
    """Floating playlist name input bar, shown/hidden with the F key."""

    def compose(self) -> ComposeResult:
        from textual.widgets import Input
        yield Input(placeholder="Playlist name…", id="pl-input")

    def on_mount(self) -> None:
        inp = self.query_one("#pl-input")
        inp.border_title = "Save Playlist"
        inp.border_subtitle = "Enter to save · Esc to cancel"

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
            self.query_one("#pl-input").focus()
        except Exception:
            pass

    def hide(self):
        self.remove_class("visible")
        try:
            self.query_one("#pl-input").value = ""
        except Exception:
            pass

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.hide()
            event.stop()


class SearchBar(Static):
    """Floating library search bar, shown/hidden with the / key."""

    def compose(self) -> ComposeResult:
        from textual.widgets import Input
        yield Input(placeholder="Search library…", id="search-input")

    def on_mount(self) -> None:
        inp = self.query_one("#search-input")
        inp.border_title = "Search Library"
        inp.border_subtitle = "Enter to jump · Esc to cancel"

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
            self.query_one("#search-input").focus()
        except Exception:
            pass

    def hide(self):
        self.remove_class("visible")
        try:
            self.query_one("#search-input").value = ""
        except Exception:
            pass

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.hide()
            event.stop()
