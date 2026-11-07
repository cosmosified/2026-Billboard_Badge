---
inclusion: auto
name: badge-firmware
description: Billboard badge MicroPython firmware reference. Use when writing or debugging badge apps, or using lib APIs (epd display, LVGL drawing, PNG loading, buttons, LED bar and sequences, SAO I2C, board ADC, fonts, pixtext), the app switcher/menu, boot flow, memory and performance.
---

# Billboard badge firmware (`firmware/badge/`)

Runtime: MicroPython 1.24.1 (lv_micropython fork 44aa2b153, ESP-IDF 5.2.3), LVGL 9.3.0, 240 MHz,
~8 MB GC heap in PSRAM. Filesystem: FAT, ~5 MB, ~2.3 MB free with the stock assets.
Built-in modules worth knowing: `lvgl`, `framebuf`, `deflate`, `btree`, `neopixel`, `network`,
`espnow`/`aioespnow`, `bluetooth`, `socket`/`ssl`/`requests`/`umqtt`, `ntptime`, `uctypes`,
`micropython` (viper/native), `random`, `json`, `onewire`/`ds18x20`/`dht`, `webrepl`, `mip`.
LVGL extras present: canvas, chart, image, qrcode, barcode, lodepng, tjpgd, `binfont_create`
(but no LVGL filesystem driver, so file-based loaders don't work; use `lib/binfont.py`).

## Layout
- `boot.py`: empty (all commented out).
- `main.py`: boot sequence and asyncio tasks.
- `lib/`: drivers and helpers. `apps/`: one or more `BaseApp` subclasses per file.
- `data/`: assets and runtime state (`graphics/`, `gallery/001-044.png`, `schedule.csv`,
  `panel_config.json`, `rendered_luts.py`; generated at runtime: `user_apps.py`, `app_list`,
  `duel_scores.json`; optional `hwconf`).

## Boot flow (`main.py`)
1. If `lvgl.display_get_default()` is not None (LVGL survived a soft reset), `machine.reset()`.
2. Import `lib.app_switcher` (discovers and constructs every app), `lib.button`, `lib.epd`
   (constructs `display`, inits LVGL), `lib.led_bar`, `lib.json_configs`. Import errors are printed
   after a 1 s sleep and re-raised.
3. `main()`: increment `load_counter` in `data/panel_config.json` (flash write every boot). Counter < 2
   shows `supercon-x-splash.png`; counter == 42 shows `never_epd.png`.
4. Tasks: `button.scan()` (1 ms poll), `display.run()` (100 ms poll), `leds.update()` (sequencer),
   `switcher.arun()` (menu + apps). Heartbeat prints `mem_info()` every 60 s.
5. `finally`: delete the LVGL display and `lvgl.deinit()`, so Ctrl-C then Ctrl-D reboots cleanly.
- No LVGL task handler runs. LVGL renders only when code calls `lvgl.refr_now(display.lv_display)`.

## App framework
- `apps/base_app.py` `BaseApp`: `name`, `sleep_ms` (default 100), `launched`.
  `async arun()` calls `self.run()` inside try/except, then sleeps `sleep_ms`. Override `run()`.
  Override `arun()` only when you need `await`; you then lose the exception guard, and an uncaught
  exception kills the switcher (menu stops responding).
- Discovery (`lib/app_switcher.py`): every `/apps/*.py` not starting with `_`; modules
  `base_app`/`template` are denylisted. Every class in the module dict that subclasses
  `apps.base_app.BaseApp` (and isn't `BaseApp` or has `_abstract = True` in its own dict) is
  constructed with no arguments. Importing another app's class into your module creates a duplicate.
- `/data/user_apps.py` is rewritten each boot with `from apps import ...`; that import is unguarded,
  so one broken app file stops the badge from booting.
- Menu order: `APP_ORDER = ["Workshops","Sat Talks","Sun Talks","Gallery","Nametag"]`, then others
  sorted by name. Current menu: Workshops, Sat Talks, Sun Talks, Gallery, Nametag, Cosmotronics,
  Life, Mandelbrot, Quick Draw (9 apps, so page 2 holds Quick Draw).
- Menu mode (at boot): LEDs show the page (one LED per app, page-colored) with the selection lit;
  `MenuPlus` next, `MenuMinus` previous, `UserA` or `UserB` launches. Launch clears the LED sequence
  and blanks the LEDs. The active app does not run while the menu is shown.
- App mode: either menu button returns to the menu (the press doesn't also move the selection).
  `launched` is True for exactly one `arun()` call after launch. Boot (GPIO0) is free for apps.
- Long blocking work in an app delays menu response until it returns.

### Minimal app (`apps/hello.py`)
```python
from apps.base_app import BaseApp
from lib.button import UserA, UserB
from lib.epd import display
from lib.led_bar import leds
from lib import pixtext

class HelloApp(BaseApp):
    def __init__(self, name=None):
        super().__init__("Hello")
        self.sleep_ms = 50
        self.count = 0

    def _busy(self):
        return display._framebuffer_ready.is_set() or not display.is_done_updating()

    def _draw(self):
        display.clear()
        pixtext.center(display.black, "HELLO", 200, 10)
        pixtext.center(display.red, "COUNT %d" % self.count, 400, 6)
        display.update()

    def run(self):
        if self.launched:
            leds.fill((0, 0, 2))
            self._draw()
            return
        if UserA.pressed() and not self._busy():
            self.count += 1
            self._draw()
        if UserB.pressed():
            leds.clear()
```
Deploy: `uv run python scripts/update.py push --reset` from `firmware/`.

## lib APIs

### `lib/epd.py`: `display` (EPaperDisplay singleton)
- `display.black`, `display.red`: `framebuf.FrameBuffer` 960x672 MONO_HLSB over
  `_framebuffer_black`/`_framebuffer_red` (80,640 bytes each). Bit 1 = ink of that color; 0 in both
  planes = white. Keep the planes exclusive per pixel. Use all framebuf methods (`fill_rect`, `line`,
  `text` (8x8), `blit`, `ellipse`, `poly`).
- `clear()`: both planes to white (doesn't touch LVGL).
- `update()`: request a refresh (sets `_framebuffer_ready`); returns immediately.
- `is_done_updating()`: True when idle. Still True for up to 100 ms after `update()`, so check
  `display._framebuffer_ready.is_set() or not display.is_done_updating()` for "busy".
- `await display._display_updated.wait()`: wait for a refresh to finish (async apps).
- `draw_png(path, row=0, col=0)`: decode straight into both planes (blocking). Note row then col.
- `draw_image(image, h, w, row, col)`: nested-list RGB, slow, and turns white pixels red (bug).
- `lv_display`, `lv_screen`: LVGL handles. Constants `display_width`, `display_height` importable.
- Refresh pipeline (`run()` then `global_update()`): row split into left/right halves (Python),
  `_reset` 0.6 s, `_send_images` (Python bit reversal of 161 KB + SoftSPI 8 MHz, ~5 s, BLOCKS the
  event loop), `cog_initial` 1.4 s, DC/DC soft start, `0x15` refresh, wait BUSY (~33 s, non-blocking).
- An `update()` requested during a refresh is dropped (flag cleared after the refresh). Wait for idle.
- `/data/hwconf` (btree, key `display_pn`): `b"84"` disables bit reversal; missing/`B1` reverses bits.

### LVGL on the e-paper
- `_lv_flush` converts RGB565 to the planes per pixel in pure Python (slow; prints every call).
  Color rule by top bit of each channel: red if R hi and G,B lo; black if all lo; else white. It
  overwrites both planes inside the flushed area.
- Pattern from `apps/nametag.py` (LVGL text over a PNG):
  1. `display.draw_png(background)`.
  2. Build `scr = lvgl.obj()`, `remove_style_all()`, transparent bg, add widgets.
  3. `lvgl.screen_load(scr); scr.update_layout()`.
  4. `display.lv_display.inv_p = 0` (forget the full-screen invalidation so the PNG survives;
     `_discard_pending_redraws()` handles bindings without `inv_p`).
  5. `widget.invalidate(); lvgl.refr_now(display.lv_display); display.update()`.
- `apps/schedule.py` does the opposite: one opaque full-screen LVGL render, then PNGs on top.
  Invalidating many small areas overflows LVGL's area list and falls back to a full flush.
- Fonts: built-in Montserrat 14/16/24/28/32/36/40/44/48. Custom: `lib/binfont.py`
  `load_binfont(path)` for LVGL v9 `.bin` fonts made with
  `npx lv_font_conv --font X.ttf --size 72 --bpp 1 --format bin -r 0x20-0x7E --no-compress -o f.bin`
  (pair kerning fixed in this fork; class kerning untested). 72 px ASCII loads in ~0.7 s.

### `lib/large_png.py`: `show_png(path, black_fb, red_fb, row, col)`
- Palette (type 3) or grayscale (type 0), bit depth 1/2/4/8, non-interlaced. No RGB/RGBA/16-bit.
- Palette colors classified like LVGL (red / black / else white). Grayscale: only 0 is black.
- No transparency: the PNG's whole box overwrites both planes. Any size; clipped to the screen.
- Reads the whole file into RAM (peak ~2x file size), viper-accelerated filters. Blocking, a few
  seconds for full-screen images.
- `lib/PNGdecoder.py` and `lib/zlib.py` are unused alternatives.

### `lib/button.py`
- `MenuMinus` (GPIO40), `MenuPlus` (15), `UserA` (39), `UserB` (16), `Boot` (0). Active low.
- `pressed()`: True once per press. `pressed_ms()`: how long it has been held (0 when released).
  `value`: last raw reading.
- No debounce. A press released before `pressed()` is read is lost (release resets the state).
  Presses during blocking work (PNG decode, SPI send) are missed entirely.

### `lib/led_bar.py`: `leds` (LedBar singleton)
- `leds[i] = (r, g, b)`, `leds.set(list)`: buffer only. `leds.write()`: push to LEDs.
- `fill(c)` and `clear()` write immediately. `NUM_LEDS = 8`, LED 0 is leftmost.
- Sequencer: `leds.set_sequence(gen_fn)` where `gen_fn()` yields `(list_of_8_colors, delay_ms)`.
  `clear_sequence()`, `pause()`, `unpause()`, `toggle_pause()`. After `set_sequence`, call
  `leds.unpause()`. Freezes during blocking work.
- `menu_display(idx, total)`, `submenu_display(idx)`: used by the menu (they pause the sequencer).
- Operators: `|` max, `&` min, `+` saturating add (return lists), `+=` in place.
- `bitmask_to_leds(x, r, g, b)` turns a byte into 8 LED values.
- Example rich effect generator: `apps/logo.py` `rainbow_show()`.

### Other libs
- `lib/sao.py`: `i2c = I2C(0, scl=18, sda=17, freq=400_000)` shared by all SAOs; `SAO1/2/3` objects
  with `gpio1`/`gpio2` Pins (no mode set). `set_address(addr)`, `readfrom(n)`, `write(data)`.
  `set_address` also builds a redundant `I2C(0)` at default freq; using `lib.sao.i2c` directly is
  simplest (`i2c.scan()`, `readfrom_mem`, `writeto_mem`).
- `lib/board.py`: `status_led` (`status_led.value(True)` = on), `reg_in_v_sns` ADC on GPIO14
  (`read_uv() * 2 / 1e6` volts), `TP8_GPIO9`, `TP9_GPIO41`.
- `lib/json_configs.py`: `load()`, `store(d)`, `append(entry, name)` on `data/panel_config.json`
  (relative path).
- `lib/pixtext.py`: `text(plane, s, x, y, scale=4, color=1)`, `center(plane, s, y, scale)`,
  `width(s, scale)`. Big blocky text from the 8x8 font, no LVGL.
- `lib/app_list.py`, `lib/base_app.py`: unused / stale.

## Apps (reference implementations)
- `schedule.py` (Workshops, Sat Talks, Sun Talks): `_abstract` base class with three subclasses,
  CSV parser, LVGL layout with precomputed font widths, PNG stage art. Draws once on launch.
- `gallery.py`: random `/data/gallery/NNN.png` every 300 s (`maximage = 44` hard-coded).
- `nametag.py`: `hello_i_am_blank.png` + LVGL plate, name lines at about line 64-71. Reference for
  the `inv_p` trick.
- `game_of_life.py` (Life): A cell size, B new board, Boot pause. Correct "display busy" check.
- `duel.py` (Quick Draw): two-player reaction game, state machine, LED-only gameplay, pixtext
  scoreboard, hall of fame in `/data/duel_scores.json`.
- `mandelbrot.py`: viper fixed-point fractal written straight into the framebuffers; A/B cycle 4
  color modes; overrides `arun` and awaits the refresh.
- `logo.py` (Cosmotronics): full-screen dithered PNG + random rainbow LED show (6 effects, random
  brightness 20-50, switching every 4-9 s).
- `template.py`: skeleton (copy to a new name).

## Performance and memory
- Blocking: PNG decode, row split, bit reversal + SoftSPI send (~5 s), `_lv_flush` (per-pixel Python),
  heavy app compute. Non-blocking: the ~33 s panel waveform.
- Speed-up candidates: viper `_lv_flush` and row split, a 256-byte bit-reversal LUT (PR #4 had these),
  but keep SoftSPI.
- Resident: LVGL draw buffer 1.29 MB, framebuffers 2x80 KB, refresh half-buffers 4x40 KB. Plenty of
  PSRAM remains (~8 MB heap).
- Use `@micropython.viper` with `ptr8` on `display._framebuffer_black/red` for fast pixel work
  (see `mandelbrot.py`).

## Gotchas checklist
- Call `display.clear()` yourself; apps share the framebuffers and the LVGL screen.
- Don't call `update()` while busy; check busy as shown above.
- Every boot writes flash (`panel_config.json`, `user_apps.py`, `app_list`).
- Ctrl-D soft reboot while LVGL is alive forces a hard reset (USB port drops and re-enumerates).
- Running scripts with `mpremote run` that import `lib.epd` after a soft reset can crash with a huge
  `MemoryError` in `lvgl.display_create`; hard-reset first (`uv run mpremote reset`).
- `rendered_luts.py`, `cog_poweroff()`, `EPD_PWR_EN_PIN` are unused groundwork.
