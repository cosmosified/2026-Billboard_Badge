"""Nametag app

Shows the "HELLO I AM" sticker. If /data/owner.json has a "maker_handle"
(see lib/owner.py), it is written in the sticker's white band, with an
optional "nametag_line2" (e.g. a Discord name) under it.
"""

import lvgl

from apps.base_app import BaseApp
from lib.button import MenuMinus, MenuPlus, UserA, UserB, Boot
from lib.epd import display, display_height, display_width
from lib.led_bar import leds
from lib.owner import owner, printable


_WHITE = lvgl.color_hex(0xFFFFFF)
_RED = lvgl.color_hex(0xFF0000)
_BLACK = lvgl.color_hex(0x000000)
_FONT = lvgl.font_montserrat_48
# White name band on hello_i_am_blank.png. Center the plate there.
_NAME_TOP = 221
_NAME_BOTTOM = 557
_NAME_DY = (_NAME_TOP + _NAME_BOTTOM) // 2 - display_height // 2
_PAD = 8
# Room for the handle inside the band (the plate adds _PAD on each side).
_TEXT_W = display_width - 2 * 32
_TEXT_H = _NAME_BOTTOM - _NAME_TOP - 2 * 16
_MAX_LINES = 2
_SIZES = (48, 46, 44, 42, 40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16)


def _wrap(words, size, width, max_w):
    """Greedy word wrap. None if a single word is wider than max_w."""
    lines = []
    cur = ""
    for w in words:
        if width(w, size) > max_w:
            return None
        t = cur + " " + w if cur else w
        if not cur or width(t, size) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _ellipsize(text, size, width, max_w):
    while text and width(text + "...", size) > max_w:
        text = text[:-1]
    return text.rstrip() + "..."


def fit_text(text, sizes, width, line_h, max_w, max_h, max_lines):
    """Pick the biggest font size where text wraps into max_lines lines.

    width(text, size) and line_h(size) measure in pixels. Returns
    (size, [lines]). Falls back to the smallest size, cutting with "..."
    so the result never exceeds max_w / max_h / max_lines.
    """
    words = text.split()
    for size in sizes:
        lim = min(max_lines, max_h // max(1, line_h(size)))
        lines = _wrap(words, size, width, max_w)
        if lines is not None and 0 < len(lines) <= lim:
            return size, lines
    size = sizes[-1]
    lim = max(1, min(max_lines, max_h // max(1, line_h(size))))
    words = [w if width(w, size) <= max_w else _ellipsize(w, size, width, max_w)
             for w in words]
    lines = _wrap(words, size, width, max_w) or [_ellipsize(text, size, width, max_w)]
    if len(lines) > lim:
        lines = lines[:lim]
        lines[-1] = _ellipsize(lines[-1], size, width, max_w)
    return size, lines


def _discard_pending_redraws(disp):
    """Forget the areas LVGL is waiting to redraw, without drawing them."""
    try:
        disp.inv_p = 0
    except AttributeError:
        # LVGL bindings that don't expose the display's private fields (e.g. the
        # simulator's): redraw them into a flush that throws the pixels away.
        disp.set_flush_cb(lambda d, area, px: d.flush_ready())
        lvgl.refr_now(disp)
        disp.set_flush_cb(display._lv_flush)


class NametagApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        self.name = "Nametag"
        self.sleep_ms = 100
        self.launched = False

    def run(self):
        if self.launched:
            leds.fill((0,1,1))
            owner.reload()
            # maker_handle, plus an optional second line (e.g. a Discord name)
            lines = [t for t in (owner.maker_handle,
                                 printable(owner.get("nametag_line2", ""))) if t]
            display.draw_png("/data/graphics/hello_i_am_blank.png")

            scr = lvgl.obj()
            scr.remove_style_all()
            scr.set_size(lvgl.pct(100), lvgl.pct(100))
            scr.set_style_bg_opa(lvgl.OPA.TRANSP, 0)

            plate = lvgl.obj(scr)
            plate.remove_style_all()
            plate.set_size(lvgl.SIZE_CONTENT, lvgl.SIZE_CONTENT)
            plate.align(lvgl.ALIGN.CENTER, 0, _NAME_DY)
            plate.set_flex_flow(lvgl.FLEX_FLOW.COLUMN)
            plate.set_flex_align(
                lvgl.FLEX_ALIGN.CENTER,
                lvgl.FLEX_ALIGN.CENTER,
                lvgl.FLEX_ALIGN.CENTER,
            )
            plate.set_style_bg_color(_WHITE, 0)
            plate.set_style_bg_opa(lvgl.OPA.COVER, 0)
            plate.set_style_pad_all(_PAD, 0)

            if lines:
                label = lvgl.label(plate)
                label.set_style_text_color(_BLACK, 0)
                label.set_style_text_align(lvgl.TEXT_ALIGN.CENTER, 0)

                def width(text, size):
                    label.set_style_text_font(getattr(lvgl, "font_montserrat_%d" % size), 0)
                    label.set_text(text)
                    label.update_layout()
                    return label.get_width()

                def line_h(size):
                    width("Ag", size)
                    return label.get_height()

                sizes = [s for s in _SIZES if hasattr(lvgl, "font_montserrat_%d" % s)]
                if len(lines) == 1:
                    size, out = fit_text(lines[0], sizes, width, line_h,
                                         _TEXT_W, _TEXT_H, _MAX_LINES)
                else:
                    # Handle and second line: one line each, same font size,
                    # the biggest at which both fit
                    size = min(fit_text(t, sizes, width, line_h, _TEXT_W,
                                        _TEXT_H // 2, 1)[0] for t in lines)
                    fits = [s for s in sizes if s <= size]
                    out = [fit_text(t, fits, width, line_h, _TEXT_W,
                                    _TEXT_H // 2, 1)[1][0] for t in lines]
                label.set_style_text_font(getattr(lvgl, "font_montserrat_%d" % size), 0)
                label.set_text("\n".join(out))
            else:
                hello = lvgl.label(plate)
                hello.set_text("")
                hello.set_style_text_color(_BLACK, 0)
                hello.set_style_text_font(_FONT, 0)

                world = lvgl.label(plate)
                world.set_text("")
                world.set_style_text_color(_BLACK, 0)
                world.set_style_text_font(_FONT, 0)

            lvgl.screen_load(scr)
            scr.update_layout()
            # screen_load dirties the whole panel. Keep the PNG everywhere else.
            _discard_pending_redraws(display.lv_display)
            plate.invalidate()
            lvgl.refr_now(display.lv_display)
            display.update()
            leds.fill((0,1,0))
