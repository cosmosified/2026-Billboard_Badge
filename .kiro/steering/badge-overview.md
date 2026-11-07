---
inclusion: always
---

# Supercon 2026 Billboard Badge: quick reference

Hackaday Supercon 2026 badge. ESP32-S3 + 9.7" 960x672 black/white/red e-paper (Pervasive Displays
E2969JS0B1, dual-CoG), 8 WS2812 LEDs, 4 user buttons + Boot, 3 SAO ports, LiPo charger.
Firmware is MicroPython + LVGL 9; apps are Python files in `firmware/badge/apps/`.

Detailed knowledge (loaded on demand):
- `badge-hardware.md`: pinout, power, e-paper wiring, SAO, BOM, schematic-vs-firmware discrepancies
- `badge-firmware.md`: boot flow, app framework, every lib API, app recipes, gotchas
- `badge-epaper.md`: panel protocol, refresh timing, fast-refresh LUTs, why hardware SPI failed
- `badge-toolchain.md`: build/flash, uv scripts, simulator, docs, repo/PR history

## Daily workflow (run from `firmware/`)
- Push code to the badge: `uv run python scripts/update.py push --reset` (diffs by SHA-256; DELETES
  files on the badge that aren't in `firmware/badge/`, except `/data` and `__pycache__`)
- See what differs: `uv run python scripts/update.py ls`
- REPL: `uv run mpremote` (Ctrl-C stops main.py; Ctrl-D soft reboot, which the firmware turns into a
  hard reset if LVGL is still alive)
- Refresh sanity check: `sh scripts/boot_test.sh 60`. A real full refresh prints ~32-34 s after
  "display working"; ~2 s means the panel never redrew.
- Badge serial port on macOS: `/dev/cu.usbmodem*` (number changes between reconnects).

## Rules that bite
- Full e-paper refresh is ~40 s end to end (~5 s blocking send + ~33 s panel). There is no partial
  refresh. `display.update()` only sets an event; `display.run()` does the work.
- Keep the e-paper on SoftSPI at 8 MHz (`lib/epd.py`). Hardware SPI (upstream PRs #3, #4) failed
  silently on this badge: refresh "done" in ~2 s, BUSY barely asserted, screen unchanged.
- LEDs are very bright: channel values 0-3 for status, 20-50 is already vivid.
- Menu +/- buttons: firmware names (`MenuPlus`=GPIO15, `MenuMinus`=GPIO40) are the reverse of the
  back silkscreen. The firmware is authoritative for behavior.
- Apps must subclass `apps.base_app.BaseApp` (not `lib/base_app.py`), take no constructor args, and
  live in a file not named `template.py`/`base_app.py`. A syntax error in any app breaks boot.
- An app using `leds.set_sequence()` must call `leds.unpause()`; the menu pauses the sequencer.
- PNGs must be palette or grayscale, non-interlaced, no alpha. Convert with
  `magick in.png -background white -alpha remove -alpha off -resize 960x672 -gravity center -extent 960x672 -remap scripts/palette.gif -strip out.png`.
- Use `uv run ...`; no system Python packages are needed.
