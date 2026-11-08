---
inclusion: auto
name: badge-firmware
description: Billboard badge MicroPython firmware reference. Use when writing or debugging badge apps, or using lib APIs (epd display, fast refresh in apps, LVGL drawing, PNG loading, buttons and press latching, LED bar and sequences, SAO I2C, board ADC, fonts, pixtext), the app switcher/menu, resume last app (last_app.json, boot.json), menu actions, owner.json profile, BLE presence, boot flow, flash writes, memory and performance.
---

# Billboard badge firmware (`firmware/badge/`)

Runtime: MicroPython 1.24.1 (lv_micropython fork 44aa2b153, ESP-IDF 5.2.3), LVGL 9.3.0, 240 MHz,
~8.3 MB free GC heap in PSRAM at idle (measured 2026-11-06). Filesystem: FAT, ~5 MB.
Built-in modules worth knowing: `lvgl`, `framebuf`, `deflate`, `btree`, `neopixel`, `network`,
`espnow`/`aioespnow`, `bluetooth`, `socket`/`ssl`/`requests`/`umqtt`, `ntptime`, `uctypes`,
`micropython` (viper/native), `random`, `json`, `onewire`/`ds18x20`/`dht`, `webrepl`, `mip`.
LVGL extras present: canvas, chart, image, qrcode, barcode, lodepng, tjpgd, `binfont_create`
(no LVGL filesystem driver, so file-based loaders don't work; use `lib/binfont.py`).

## Layout
- `boot.py`: empty (all commented out).
- `main.py`: boot sequence and asyncio tasks.
- `lib/`: drivers and helpers. `apps/`: one or more `BaseApp` subclasses per file.
- `data/` in the repo: `graphics/`, `gallery/001-044.png`, `schedule.csv`, `panel_config.json`,
  `rendered_luts.py` (fast-refresh waveforms, loaded by `lib/epd.py`).
- `/data/` files created on the badge (never pushed or deleted by `update.py`):
  - `app_list` (btree of the menu, written every boot, read by nothing)
  - `last_app.json` (`{"module", "app"}`, written only when the launched app changes)
  - `boot.json` (optional, user-made: `{"resume": false}`)
  - `owner.json` (optional, user-made profile, see below; `owner.json.tmp` while saving)
  - `presence.json` (`{"id": "<6 hex>"}`, created on the first BLE broadcast)
  - `duel_scores.json` (Quick Draw hall of fame), optional `hwconf` (panel variant)

## Boot flow (`main.py`)
1. If `lvgl.display_get_default()` is not None (LVGL survived a soft reset), `machine.reset()`.
2. `time.sleep(0.5)`, then import `lib.app_switcher` (discovers and constructs every app, then
   decides whether to resume), `lib.button`, `lib.epd` (constructs `display`, drives GPIO48 on,
   inits LVGL), `lib.led_bar`, `lib.json_configs`. An import error in these is printed after a 1 s
   sleep and re-raised, so boot stops. Errors in individual app files are skipped instead.
3. `main()`: increment `load_counter` in `data/panel_config.json` (flash write every boot). Counter < 2
   shows `supercon-x-splash.png`; counter == 42 shows `never_epd.png`.
4. `presence.start()` and the `presence.keep_alive()` task, inside try/except (does nothing unless
   `"broadcast": true`).
5. Tasks: `button.scan()` (1 ms poll), `display.run()` (100 ms poll), `leds.update()` (sequencer),
   `switcher.arun()` (menu + apps). Heartbeat prints `mem_info()` every 60 s.
6. `finally`: delete the LVGL display and `lvgl.deinit()`, so Ctrl-C then Ctrl-D reboots cleanly.
- No LVGL task handler runs. LVGL renders only when code calls `lvgl.refr_now(display.lv_display)`.

## App framework
- `apps/base_app.py` `BaseApp`: `name`, `sleep_ms` (default 100), `launched`, class attributes
  `menu_action = False` and `_app_module` (set by the switcher). `async arun()` calls `self.run()`
  inside try/except (prints the traceback), then sleeps `sleep_ms`. Override `run()`.
- Override `arun()` only when you need `await`. Then add your own try/except with
  `sys.print_exception`: an uncaught exception there ends `switcher.arun()` and the menu stops
  responding. `apps/mandelbrot.py` shows the pattern.
- Discovery (`lib/app_switcher.py`): every `/apps/*.py` not starting with `_`; `__init__`,
  `base_app` and `template` are denylisted. Each module is imported on its own; a failing module
  prints "Failed to import app module" and is skipped. Every class in the module dict that
  subclasses `apps.base_app.BaseApp` (and isn't `BaseApp` or has `_abstract = True` in its own dict)
  is constructed with no arguments. Importing another app's class into your module creates a
  duplicate.
- Menu order: `APP_ORDER = ["Workshops","Sat Talks","Sun Talks","Gallery","Nametag"]`, then other
  apps sorted by name, then menu actions. Current menu (9 entries): Workshops, Sat Talks, Sun Talks,
  Gallery, Nametag, Cosmotronics, Mandelbrot, Quick Draw, Bluetooth. Page 2 holds Bluetooth (LED 1),
  in a different page color. Community apps live in `user_apps/` (Life, KITT) and only appear once
  copied into `/apps/` on the badge.
- Boot: the badge resumes the last app launched from the menu (`/data/last_app.json`, matched by
  module and app name). It shows the menu instead when a Menu button is held at boot,
  `/data/boot.json` has `"resume": false`, or there is no valid saved app. The menu then opens with
  the last app selected, matching what the e-paper still shows. A bad `last_app.json` or
  `boot.json` is ignored with a message.
- Menu mode: LEDs show the page (one LED per entry) with the selection lit; `MenuPlus` (right
  button) next, `MenuMinus` (left) previous, `UserA` or `UserB` picks. Picking an app saves it as
  the last app, clears the LED sequence, blanks the LEDs and launches it. The active app does not run
  while the menu is shown.
- Menu actions (`menu_action = True`, e.g. `apps/bluetooth.py`): picking one calls `action()` and
  stays in the menu; the screen and the current app are untouched and nothing is saved. `action()`
  shows LED feedback; the menu waits `ACTION_FEEDBACK_MS` (1.2 s), drops taps made meanwhile, then
  redraws.
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
    def __init__(self) -> None:
        super().__init__("Hello")
        self.sleep_ms = 50
        self.count = 0

    def _busy(self) -> bool:
        return display._framebuffer_ready.is_set() or not display.is_done_updating()

    def _draw(self) -> None:
        display.clear()
        pixtext.center(display.black, "HELLO", 200, 10)
        pixtext.center(display.black, f"COUNT {self.count}", 400, 6)
        display.update(fast=self.count > 0)  # full refresh on launch, fast after

    def run(self) -> None:
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
  planes = white. Keep the planes exclusive per pixel. All framebuf methods work (`fill_rect`,
  `line`, `text` (8x8), `blit`, `ellipse`, `poly`).
- `clear()`: both planes to white (doesn't touch LVGL).
- `update(fast=False, keep_red=False, passes=None)`: request a refresh; returns immediately.
  Full: ~34 s, the only good red. `fast=True`: ~6.6 s, black/white, 3 short flashes. Requests made
  during a refresh are merged into one more refresh using the last options and the framebuffer at
  that time. See `badge-epaper.md` for fast-refresh results and guidance.
- Busy check: `display._framebuffer_ready.is_set() or not display.is_done_updating()`.
  `is_done_updating()` alone is still True for up to 100 ms after `update()`.
- `await display._display_updated.wait()`: wait for a refresh (and any queued one) to finish.
- `draw_png(path, row=0, col=0)`: decode straight into both planes (blocking). Note row then col.
- `draw_image(image, h, w, row, col)`: nested-list RGB, slow, and turns white pixels red (bug).
- `lv_display`, `lv_screen`: LVGL handles. Constants `display_width`, `display_height` importable.
- `/data/hwconf` (btree, key `display_pn`): `b"84"` disables bit reversal and selects the driver-8
  fast LUT; missing or `B1` is the default.

### LVGL on the e-paper
- `_lv_flush` converts RGB565 to the planes with the viper `_rgb565_to_planes` (~0.5 s full
  screen). Color rule by the top bit of each channel: red if R hi and G,B lo; black if all lo; else
  white. It overwrites both planes inside the flushed area. LVGL only draws into the framebuffers;
  call `display.update()` afterwards.
- Pattern from `apps/nametag.py` (LVGL text over a PNG):
  1. `display.draw_png(background)`.
  2. Build `scr = lvgl.obj()`, `remove_style_all()`, transparent bg, add widgets.
  3. `lvgl.screen_load(scr); scr.update_layout()`.
  4. `_discard_pending_redraws(display.lv_display)` (sets `inv_p = 0`, so the full-screen
     invalidation is forgotten and the PNG survives; falls back for bindings without `inv_p`).
  5. `widget.invalidate(); lvgl.refr_now(display.lv_display); display.update()`.
- `apps/schedule.py` does the opposite: one opaque full-screen LVGL render, then PNGs on top.
  Invalidating many small areas overflows LVGL's area list and falls back to a full flush.
- Fonts: built-in Montserrat 14/16/24/28/32/36/40/44/48. Custom: `lib/binfont.py`
  `load_binfont(path)` for LVGL v9 `.bin` fonts made with
  `npx lv_font_conv --font X.ttf --size 72 --bpp 1 --format bin -r 0x20-0x7E --no-compress -o f.bin`
  (pair kerning fixed in this fork; class kerning untested). A 72 px ASCII font loaded in ~0.7 s.

### `lib/large_png.py`: `show_png(path, black_fb, red_fb, row, col)`
- Palette (type 3) or grayscale (type 0), bit depth 1/2/4/8, non-interlaced. No RGB/RGBA/16-bit.
- Palette colors classified like LVGL (red / black / else white). Grayscale: only 0 is black.
- No transparency: the PNG's whole box overwrites both planes. Any size; clipped to the screen.
- Reads the whole file into RAM (peak ~2x file size), viper-accelerated filters. Blocking, about a
  second for a full-screen palette image.
- `lib/PNGdecoder.py` and `lib/zlib.py` are unused alternatives.

### `lib/button.py`
- `MenuMinus` (GPIO40, left), `MenuPlus` (15, right), `UserA` (39), `UserB` (16), `Boot` (0).
  Active low, internal pull-ups, scanned every 1 ms by an asyncio task.
- `pressed()`: True once per press. A press released before `pressed()` reads it stays latched for
  `LATCH_MS` (1000 ms) after release.
- `pressed_ms()`: ms since the press started, while the button is held or the press is unhandled;
  0 after a handled press is released.
- `value`: last raw reading. No debounce. Two taps closer together than the scan rate can register
  as one. A press that starts and ends entirely inside blocking work is missed.

### `lib/led_bar.py`: `leds` (LedBar singleton)
- `leds[i] = (r, g, b)`: buffer only. `leds.write()`: push to LEDs. `leds.set(list)`, `fill(c)` and
  `clear()` write immediately. `NUM_LEDS = 8`, LED 0 is leftmost.
- Sequencer: `leds.set_sequence(gen_fn)` where `gen_fn()` yields `(list_of_8_colors, delay_ms)`.
  `clear_sequence()`, `pause()`, `unpause()`, `toggle_pause()`. After `set_sequence`, call
  `leds.unpause()`. Freezes during blocking work.
- `menu_display(idx, total)`, `submenu_display(idx)`: used by the menu (they pause the sequencer).
- Operators: `|` max, `&` min, `+` saturating add (return lists), `+=` in place.
- `bitmask_to_leds(x, r, g, b)` turns a byte into 8 LED values.
- Example effect generator: `apps/logo.py` `rainbow_show()`.

### `lib/owner.py` and `/data/owner.json`
- Keys: `maker_handle` (a public handle, not a real name; shown on the Nametag and broadcast),
  `nametag_line2` (optional Nametag second line), `makes` (exposed, unused by apps), `broadcast`
  (bool, BLE presence on/off). Anything that rewrites the file must keep unknown keys.
- `from lib.owner import owner, printable`: `owner.maker_handle`, `owner.makes` ("" if unset),
  `owner.get(key, default)`, `owner.reload()`. It never raises. `printable(v)` makes one line of
  printable text from a value.
- This badge: `{"maker_handle": "Cosmo", "nametag_line2": "@cosmosisjones", "broadcast": true}`.

### `lib/presence.py` (BLE presence)
- Off unless `owner.json` has `"broadcast": true`; Bluetooth isn't even initialized when off.
- Advert: non-connectable, every 400 ms: flags, manufacturer data company 0xFFFF, magic `SC26`,
  version 1, 3 random id bytes (`/data/presence.json`, not the MAC), `maker_handle` (<= 16 ASCII).
- `start()` (boot), `keep_alive()` (task, re-issues the advert every 30 s), `enabled()`,
  `set_broadcast(on)` (saves to owner.json via tmp + rename, returns False if not saved),
  `refresh()`, `badge_id()`, `text()`, `parse(adv)` -> `(id_hex, text)` or None.
- Apps scan themselves (`bluetooth.BLE().gap_scan(...)`, pass `data[4]` of a scan result to
  `parse`). Check `ble.active()` before `ble.active(True)`: re-activating an active stack silently
  drops the advert until `keep_alive` restores it.
- Verified from a Mac with `bleak`: `id=586be5 handle='Cosmo' ver=1 rssi=-40`.

### Other libs
- `lib/sao.py`: `i2c = I2C(0, scl=18, sda=17, freq=400_000)` shared by all SAOs; `SAO1/2/3` objects
  with `gpio1`/`gpio2` Pins (no mode set). `set_address(addr)`, `readfrom(n)`, `write(data)`.
  `set_address` also builds a redundant `I2C(0)` at default freq; using `lib.sao.i2c` directly is
  simplest (`i2c.scan()`, `readfrom_mem`, `writeto_mem`).
- `lib/board.py`: `status_led` (`status_led.value(True)` = on), `reg_in_v_sns` ADC on GPIO14
  (`read_uv() * 2 / 1e6` volts; reads USB, not the battery, while plugged in), `TP8_GPIO9`,
  `TP9_GPIO41`.
- `lib/json_configs.py`: `load()`, `store(d)`, `append(entry, name)` on `data/panel_config.json`
  (relative path).
- `lib/pixtext.py`: `text(plane, s, x, y, scale=4, color=1)`, `center(plane, s, y, scale)`,
  `width(s, scale)`. Big blocky text from the 8x8 font, no LVGL.
- `lib/app_list.py`, `lib/base_app.py`: unused / stale.

## Apps (reference implementations)
- `schedule.py` (Workshops, Sat Talks, Sun Talks): `_abstract` base class with three subclasses,
  CSV parser, LVGL layout with precomputed font widths, PNG stage art. Draws once on launch.
- `gallery.py`: random `/data/gallery/NNN.png` every 300 s (`maximage = 44` hard-coded).
- `nametag.py`: `hello_i_am_blank.png` + LVGL plate with `maker_handle` and `nametag_line2` from
  `/data/owner.json` (re-read on each launch), auto-fitted from Montserrat 48 down to 16 in the band
  y=221-557. Two lines share one font size. Without a handle the sticker stays blank.
- `user_apps/game_of_life_hunter/game_of_life.py` (Life, not installed by default): A cell size,
  B new board, Boot pause. Correct "display busy" check. Uses full refreshes (a candidate for
  `fast=True`). `user_apps/kitt/kitt.py`: image + Larson scanner on the LEDs.
- `duel.py` (Quick Draw): two-player reaction game, state machine, LED-only gameplay, pixtext
  scoreboard, hall of fame in `/data/duel_scores.json`.
- `mandelbrot.py`: viper fixed-point fractal written straight into the framebuffers, computed in
  chunks with awaits; A/B cycle 4 color modes; requests the refresh without waiting; overrides
  `arun` with its own exception guard.
- `logo.py` (Cosmotronics): full-screen CT emblem PNG (flat 3-color, conversion command in the
  docstring) + random rainbow LED show (6 effects, random brightness 20-50, switching every 4-9 s).
- `bluetooth.py` (Bluetooth, menu action): toggles BLE presence; all 8 LEDs blue = on, one dim red
  LED = off.
- `template.py`: skeleton (copy to a new name).

## Performance and memory
- Blocking: PNG decode (about a second full screen), plane split ~33-70 ms, SPI send ~95 ms,
  LVGL full-screen flush ~0.5 s, heavy app compute. Non-blocking: reset, CoG init and the waveform
  (~33 s full, ~3.5 s fast).
- Resident: LVGL draw buffer 1.29 MB, framebuffers 2 x 80 KB, refresh half-buffers 4 x 40 KB,
  `_prev_black` 80 KB (after the first refresh), `hold_red` 80 KB (after the first fast refresh).
  Plenty of PSRAM remains.
- Use `@micropython.viper` with `ptr8` on `display._framebuffer_black/red` for fast pixel work
  (see `mandelbrot.py`).

## Gotchas checklist
- Call `display.clear()` yourself; apps share the framebuffers and the LVGL screen.
- Calling `update()` while busy queues one more refresh (36 s if full); check busy to avoid stacking.
- Flash writes: every boot writes `panel_config.json` and `app_list`; `last_app.json` only when it
  changes; `owner.json` and `presence.json` only when broadcasting is toggled or first used.
- Ctrl-D soft reboot while LVGL is alive forces a hard reset (USB port drops and re-enumerates).
- Running scripts with `mpremote run` that import `lib.epd` after a soft reset can crash with a huge
  `MemoryError` in `lvgl.display_create`; hard-reset first (`uv run mpremote reset`).
- `cog_poweroff()` in `lib/epd.py` is never called.
