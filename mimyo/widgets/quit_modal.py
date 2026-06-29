"""QuitModal — floating quit confirmation widget inside #right-col."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label
from textual.containers import Horizontal, Vertical


class QuitModal(Widget):
    """Floating quit confirmation, positioned above the now-playing bar."""

    DEFAULT_CSS = """
    QuitModal {
        layer: overlay;
        display: none;
        width: 36;
        height: 5;
        background: #1f1f28;
        border: solid #7e9cd8;
        padding: 0 2;
    }

    #quit-title {
        text-align: center;
        color: #e46876;
        text-style: bold;
        width: 1fr;
        margin-bottom: 1;
    }

    #quit-hints {
        align: center middle;
        height: auto;
        width: 1fr;
    }

    #hint-enter {
        color: #727169;
        margin: 0 1;
    }

    #hint-sep {
        color: #2a2a37;
    }

    #hint-esc {
        color: #727169;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Quit Mimyo?", id="quit-title")
            with Horizontal(id="quit-hints"):
                yield Label("Enter  —  quit", id="hint-enter")
                yield Label("·", id="hint-sep")
                yield Label("Esc  —  cancel", id="hint-esc")

    def show(self) -> None:
        self.display = True
        self._reposition()
        self.focus()

    def hide(self) -> None:
        self.display = False

    def _reposition(self) -> None:
        try:
            parent = self.parent
            if parent is None:
                return
            pw = parent.content_size.width
            ph = parent.content_size.height
            self.styles.width = min(36, pw)
            bh = self.outer_size.height or 5
            x = max(0, (pw - min(36, pw)) // 2)
            y = max(0, ph - bh - 6)
            self.styles.offset = (x, y)
        except Exception:
            pass

    def on_resize(self) -> None:
        self._reposition()


