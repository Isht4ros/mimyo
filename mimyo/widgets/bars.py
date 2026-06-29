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

    def show(self):
        self.add_class("visible")
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

    def show(self):
        self.add_class("visible")
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
