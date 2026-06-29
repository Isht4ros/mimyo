"""Album art rendering: PIL helpers, chafa wrappers, and AlbumArtWidget."""
from __future__ import annotations

import os

from textual.widgets import Static

from ..deps import PIL_AVAILABLE, SIXEL_AVAILABLE, Image, SixelConverter
from .sixel_win import _sixel_write_at


def pil_to_rich_text(img, width: int = 24, height: int = 12):
    """Convert PIL image to Rich Text with coloured half-block characters."""
    from rich.text import Text
    from rich.style import Style
    from rich.color import Color
    img = img.convert("RGB").resize((width, height * 2), Image.LANCZOS)
    result = Text()
    for row in range(height):
        for col in range(width):
            tr, tg, tb = img.getpixel((col, row * 2))
            br, bg2, bb = img.getpixel((col, row * 2 + 1))
            style = Style(
                color=Color.from_rgb(br, bg2, bb),
                bgcolor=Color.from_rgb(tr, tg, tb),
            )
            result.append("▄", style=style)
        if row < height - 1:
            result.append("\n")
    return result


def pil_to_sixel(img, size: int = 128) -> str:
    """Convert PIL image to a sixel escape sequence string."""
    import io
    img = img.convert("RGB").resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c = SixelConverter(buf, w=size, h=size, ncolor=256)
    out = io.StringIO()
    c.write(out)
    return out.getvalue()


def render_with_chafa_sixel(img, width_cells, height_cells):
    """Run chafa in sixel mode -> raw bytes. Returns None if unavailable."""
    import subprocess, io, tempfile, os
    try:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG", compress_level=1)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(buf.getvalue())
            tmp = f.name
        try:
            r = subprocess.run(
                ["chafa", "--format=sixel",
                 f"--size={width_cells}x{height_cells}",
                 "--colors=full", "--color-space=din99d",
                 "--dither=fs", "--font-ratio=1/2", "--animate=off", tmp],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                return r.stdout
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    except Exception:
        pass
    return None


def render_with_chafa_symbols(img, width_cells, height_cells):
    """Run chafa in symbols mode -> Rich Text. Used as the Textual-owned fallback layer."""
    import subprocess, io, tempfile, os, re
    from rich.text import Text
    from rich.style import Style
    from rich.color import Color
    try:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG", compress_level=1)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(buf.getvalue())
            tmp = f.name
        try:
            r = subprocess.run(
                ["chafa", "--format=symbols", "--symbols=half",
                 f"--size={width_cells}x{height_cells}",
                 "--colors=256", "--color-space=din99d",
                 "--dither=fs", "--animate=off", tmp],
                capture_output=True, timeout=5,
            )
            if r.returncode != 0:
                return None
            ansi = r.stdout.decode("utf-8", errors="replace")
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    except Exception:
        return None

    ESC = "\x1b"
    # Match any CSI sequence (parameter bytes 0-9;? then one final letter), not
    # just SGR/color codes. chafa's symbols output wraps each frame in cursor
    # hide/show codes ("\x1b[?25l" ... "\x1b[?25h") which don't end in "m" and
    # contain "?" - the old "\[[0-9;]*m"-only pattern skipped right past those,
    # so they fell into the "plain text between matches" branch and got
    # appended into the widget as literal characters. Now we match them too
    # and just discard them below instead of treating them as color codes.
    CSI = re.compile(ESC + r"\[[0-9;?]*[A-Za-z]")

    def color256(n):
        if n < 16:
            tab = [(0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),
                   (0,128,128),(192,192,192),(128,128,128),(255,0,0),(0,255,0),
                   (255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255)]
            return Color.from_rgb(*tab[n])
        if n < 232:
            n -= 16; b = (n % 6) * 51; n //= 6; g = (n % 6) * 51; n //= 6; r = n * 51
            return Color.from_rgb(r, g, b)
        v = 8 + (n - 232) * 10
        return Color.from_rgb(v, v, v)

    rich_text = Text()
    fg = bg = None
    pos = 0
    for m in CSI.finditer(ansi):
        plain = ansi[pos:m.start()]
        if plain:
            rich_text.append(plain, style=Style(color=fg, bgcolor=bg))
        pos = m.end()
        seq = m.group()
        if not seq.endswith("m"):
            continue  # non-SGR control sequence (cursor hide/show, etc.) - discard
        inner = seq[2:-1]
        codes = inner.split(";") if inner else ["0"]
        i = 0
        while i < len(codes):
            c = int(codes[i]) if codes[i] else 0
            if c == 0:
                fg = bg = None
            elif c == 38 and i + 2 < len(codes) and int(codes[i + 1]) == 5:
                fg = color256(int(codes[i + 2])); i += 2
            elif c == 48 and i + 2 < len(codes) and int(codes[i + 1]) == 5:
                bg = color256(int(codes[i + 2])); i += 2
            i += 1
    if pos < len(ansi):
        rich_text.append(ansi[pos:], style=Style(color=fg, bgcolor=bg))
    return rich_text if len(rich_text) > 0 else None


class AlbumArtWidget(Static):
    """Album art: sixel overlay (chafa high quality) with symbols Rich Text underneath.

    The symbols layer is owned by Textual so layout is correct.
    The sixel layer is repainted via post_display_hook after every Textual frame.
    """

    ART_W = 26
    ART_H = 13

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sixel_bytes: bytes | None = None
        self._rich_content = self._placeholder()
        self._sixel_dirty = False

    def _placeholder(self):
        from rich.text import Text
        inner_w = self.ART_W - 2
        lines = (
            ["\u250c" + "\u2500" * inner_w + "\u2510"] +
            ["\u2502" + " " * inner_w + "\u2502"] * 2 +
            ["\u2502" + "\u266b no art".center(inner_w) + "\u2502"] +
            ["\u2502" + " " * inner_w + "\u2502"] * 2 +
            ["\u2514" + "\u2500" * inner_w + "\u2518"]
        )
        return Text("\n".join(lines), style="dim")

    def set_track(self, track):
        self._sixel_bytes = None
        self._sixel_dirty = False
        self._rich_content = self._placeholder()
        if track is None:
            self.refresh()
            return
        art = track.get_art()
        if art and PIL_AVAILABLE:
            sym = render_with_chafa_symbols(art, self.ART_W, self.ART_H)
            if sym is not None:
                self._rich_content = sym
            else:
                self._rich_content = pil_to_rich_text(art, self.ART_W, self.ART_H)
            sixel = render_with_chafa_sixel(art, self.ART_W, self.ART_H)
            if sixel:
                self._sixel_bytes = sixel
                self._sixel_dirty = True
        self.refresh()

    def render(self):
        if self._sixel_bytes:
            self._sixel_dirty = True
            from rich.text import Text
            blank = " " * self.ART_W
            return Text((blank + "\n") * (self.ART_H - 1) + blank)
        return self._rich_content

    def _paint_sixel(self, driver=None):
        if not self._sixel_bytes or not self._sixel_dirty:
            return
        try:
            region = self.content_region
            if region.width == 0 or region.height == 0:
                return
            row = region.y + region.height - self.ART_H + 1
            col = region.x + 1
            row += int(os.environ.get("PLAYER_SIXEL_ROW_OFFSET", 0))
            col += int(os.environ.get("PLAYER_SIXEL_COL_OFFSET", 0))
            _sixel_write_at(row, col, self._sixel_bytes, driver=driver)
            self._sixel_dirty = False
        except Exception:
            pass

    def on_resize(self):
        self._sixel_dirty = True
        self.refresh()
