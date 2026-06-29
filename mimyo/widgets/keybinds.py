"""KeybindOverlay — keyboard shortcut overlay inside #right-col."""
from __future__ import annotations
import re

from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget


NAV = [
    ("↑ ↓",   "Move"),
    ("↵",      "Open / play"),
    ("/",      "Search"),
    ("tab",    "Switch pane"),
    ("esc",    "Back"),
    ("q",      "Quit"),
]

PLAYER = [
    ("space", "Play / pause"),
    ("← →",   "Seek"),
    ("> <",   "Next / prev"),
    ("r",     "Repeat"),
    ("s",     "Shuffle"),
    ("- =",   "Volume"),
    ("y",     "YouTube"),
    ("z",     "Random queue"),
]

LIBRARY = [
    ("a",  "Add to queue"),
    ("x",  "Remove"),
    ("c",  "Clear queue"),
    ("f",  "Save playlist"),
    ("o",  "Home folder"),
]

C_BORDER  = "#e6c384"
C_HEADING = "#e6c384"
C_KEY     = "#e6c384"
C_DESC    = "#727169"
C_BG      = "#1a1a23"
C_HINT    = "#727169"

# These module-level constants are used as fallbacks when the overlay hasn't
# mounted yet (e.g. during the initial _build_markup call). Once mounted,
# KeybindOverlay.show() refreshes the markup via _reposition() which reads
# live colors from the CSS through get_colors_from_widget().

def get_colors_from_widget(widget) -> dict:
    """Read theme colors from a mounted widget's computed styles."""
    def _hex(c, fallback):
        try:
            return f"#{int(c.r):02x}{int(c.g):02x}{int(c.b):02x}"
        except Exception:
            return fallback
    try:
        # #np-title carries the accent/gold color (same as C_BORDER/C_HEADING)
        accent = _hex(widget.app.query_one("#np-title").styles.color, C_BORDER)
        # #np-album carries the muted/dim color (same as C_DESC/C_HINT)
        muted  = _hex(widget.app.query_one("#np-album").styles.color, C_DESC)
        # Screen background for the text color
        fg     = _hex(widget.app.screen.styles.color, C_KEY)
        # #sidebar background for the overlay bg
        bg     = _hex(widget.app.query_one("#sidebar").styles.background, C_BG)
        return {"border": accent, "heading": accent, "key": accent,
                "desc": muted, "bg": bg, "hint": muted}
    except Exception:
        return {"border": C_BORDER, "heading": C_HEADING, "key": C_KEY,
                "desc": C_DESC, "bg": C_BG, "hint": C_HINT}


def _strip(text: str) -> int:
    return len(re.sub(r"\[.*?\]", "", text))


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _strip(text))


def _fmt_col(pairs: list[tuple[str, str]], width_key: int, colors: dict) -> list[str]:
    lines = []
    for key, desc in pairs:
        k = f"[bold {colors['key']}]{key}[/]"
        d = f"[{colors['desc']}]{desc}[/]"
        lines.append(k + " " * max(1, width_key - len(key)) + d)
    return lines


def _build_markup(col_w: int, colors: dict | None = None) -> str:
    """Build markup with given column width."""
    c = colors or {"border": C_BORDER, "heading": C_HEADING, "key": C_KEY,
                   "desc": C_DESC, "bg": C_BG, "hint": C_HINT}
    nav_lines = _fmt_col(NAV,     width_key=11, colors=c)
    pl_lines  = _fmt_col(PLAYER,  width_key=7,  colors=c)
    lb_lines  = _fmt_col(LIBRARY, width_key=5,  colors=c)

    h = max(len(nav_lines), len(pl_lines), len(lb_lines))
    nav_lines += [""] * (h - len(nav_lines))
    pl_lines  += [""] * (h - len(pl_lines))
    lb_lines  += [""] * (h - len(lb_lines))

    heading = f""
    hint    = f"\n[{c['hint']}]press ? or esc to close[/]"

    header = (_pad(f"[{c['desc']}]NAVIGATE[/]", col_w) +
              _pad(f"[{c['desc']}]PLAYER[/]",   col_w) +
              f"[{c['desc']}]LIBRARY[/]")
    rows = [_pad(n, col_w) + _pad(p, col_w) + l
            for n, p, l in zip(nav_lines, pl_lines, lb_lines)]

    return heading + "\n" + header + "\n" + "\n".join(rows) + hint


def _build_markup_2col(col_w: int, colors: dict | None = None) -> str:
    """Nav + Player stacked left, Library right."""
    c = colors or {"border": C_BORDER, "heading": C_HEADING, "key": C_KEY,
                   "desc": C_DESC, "bg": C_BG, "hint": C_HINT}
    nav_lines = _fmt_col(NAV,     width_key=11, colors=c)
    pl_lines  = _fmt_col(PLAYER,  width_key=7,  colors=c)
    lb_lines  = _fmt_col(LIBRARY, width_key=5,  colors=c)

    heading = f""
    hint    = f"\n[{c['hint']}]press ? or esc to close[/]"

    left = (
        [_pad(f"[{c['desc']}]NAVIGATE[/]", col_w)] + nav_lines +
        [""] +
        [_pad(f"[{c['desc']}]PLAYER[/]", col_w)]   + pl_lines
    )
    right = (
        [f"[{c['desc']}]LIBRARY[/]"] + lb_lines
    )

    h = max(len(left), len(right))
    left  += [""] * (h - len(left))
    right += [""] * (h - len(right))

    rows = [_pad(l, col_w) + r for l, r in zip(left, right)]
    return heading + "\n" + "\n".join(rows) + hint


def _build_markup_1col(colors: dict | None = None) -> str:
    """Single column fallback."""
    c = colors or {"border": C_BORDER, "heading": C_HEADING, "key": C_KEY,
                   "desc": C_DESC, "bg": C_BG, "hint": C_HINT}
    nav_lines = _fmt_col(NAV,     width_key=11, colors=c)
    pl_lines  = _fmt_col(PLAYER,  width_key=7,  colors=c)
    lb_lines  = _fmt_col(LIBRARY, width_key=5,  colors=c)

    heading = f""
    hint    = f"\n[{c['hint']}]press ? or esc to close[/]"

    lines = (
        [f"[{c['desc']}]NAVIGATE[/]"] + nav_lines + [""] +
        [f"[{c['desc']}]PLAYER[/]"]   + pl_lines  + [""] +
        [f"[{c['desc']}]LIBRARY[/]"]  + lb_lines
    )
    return heading + "\n" + "\n".join(lines) + hint


# Width thresholds (box outer width including border+padding)
W_3COL = 72
W_2COL = 44


class KeybindOverlay(Widget):
    """Absolutely-positioned overlay inside #right-col, dynamically centered."""

    def compose(self) -> ComposeResult:
        yield Static("", markup=True, id="kb-static")

    def _reposition(self) -> None:
        try:
            parent = self.parent
            if parent is None:
                return
            pw = parent.content_size.width
            ph = parent.content_size.height

            colors = get_colors_from_widget(self)

            if pw >= W_3COL:
                col_w = (pw - 6) // 3
                col_w = min(col_w, 26)
                markup = _build_markup(col_w, colors)
                box_w  = min(pw, col_w * 3 + 6)
            elif pw >= W_2COL:
                col_w = (pw - 6) // 2
                col_w = min(col_w, 30)
                markup = _build_markup_2col(col_w, colors)
                box_w  = min(pw, col_w * 2 + 6)
            else:
                markup = _build_markup_1col(colors)
                box_w  = pw

            static = self.query_one("#kb-static", Static)
            static.update(markup)

            self.styles.width = box_w
            bh = self.outer_size.height or 16
            x = max(0, (pw - box_w) // 2)
            y = max(0, (ph - bh) // 2)
            self.styles.offset = (x, y)

            # Apply theme colors to the overlay box itself
            self.styles.background = colors["bg"]
            self.styles.border = ("solid", colors["border"])
            self.border_title = "Keybinds"
            self.border_title_align = "left"
        except Exception:
            pass

    def on_mount(self) -> None:
        self.call_after_refresh(self._reposition)

    def on_resize(self) -> None:
        self._reposition()

    def show(self) -> None:
        self.display = True
        self.call_after_refresh(self._reposition)
        self.focus()

    def hide(self) -> None:
        self.display = False

    def on_key(self, event) -> None:
        self.hide()
        event.stop()
