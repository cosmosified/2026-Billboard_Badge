---
inclusion: always
---

# Supercon 2026 Billboard Badge: quick reference

Hackaday Supercon 2026 badge. ESP32-S3-WROOM-1 N8R8 (8 MB flash, 8 MB PSRAM) + 9.7" 960x672
black/white/red e-paper (Pervasive Displays E2969JS0B1, dual CoG), 8 WS2812 LEDs, 4 user buttons +
Boot, 3 SAO ports, LiPo charger. Firmware is MicroPython 1.24.1 + LVGL 9.3; apps are Python files
in `firmware/badge/apps/`.

Detailed knowledge (loaded on demand):
- `badge-hardware.md`: pinout, power, e-paper wiring, SAO, BOM, schematic-vs-firmware discrepancies
- `badge-firmware.md`: boot flow, app framework, menu/resume/menu actions, lib APIs, owner.json, BLE
  presence, app recipes, gotchas
- `badge-epaper.md`: panel protocol, refresh timing, fast refresh (0xB0), hold-black, test results
- `badge-toolchain.md`: build/flash, uv, scripts, simulator, docs, repo/PR history
- `output-behavior.md` (always loaded): response rules and Python coding standards
- `.kiro/knowledge/*.txt`: extracted text of the panel spec and the iTC97 driver app note
- Semantic search: knowledge bases `billboard-badge-docs` (this folder) and
  `billboard-badge-firmware` (`firmware/badge/`)

## Daily workflow (run from `firmware/`)
- Push code to the badge: `uv run python scripts/update.py push --reset` (diffs by SHA-256; DELETES
  files on the badge that aren't in `firmware/badge/`, except `/data` and `__pycache__`)
- See what differs: `uv run python scripts/update.py ls`. Any `mpremote` command stops `main.py`;
  run `uv run mpremote reset` afterwards or the badge sits at the REPL and ignores the buttons.
- REPL: `uv run mpremote` (Ctrl-C stops main.py; Ctrl-D soft reboot)
- Refresh sanity check: `sh scripts/boot_test.sh 60`. A real full refresh prints ~32-34 s after
  "display working"; ~2 s means the panel never redrew.
- Badge serial port on macOS: `/dev/cu.usbmodem*` (the number changes between reconnects). Only one
  program can hold the port: stop serial loggers before running `mpremote`.

## Rules that bite
- Full refresh: ~34 s end to end (0.6 s reset, ~0.1 s blocking send, 1.4 s CoG init, ~33 s
  waveform). `display.update(fast=True)`: ~6.6 s, 3 short flashes, black stays black with the
  hold-black fix; red needs a full refresh. No partial (windowed) refresh exists.
- `display.update()` only sets an event; `display.run()` does the work. An update requested during a
  refresh is queued (one more refresh follows), not dropped.
- The e-paper uses hardware SPI(1) at 20 MHz (`lib/epd.py`). After a soft reset the bus must be
  constructed, deinited and constructed again, or the refresh "finishes" in ~2 s with the screen
  unchanged (upstream issue #25). Test driver changes after a hard reset and after Ctrl-C/Ctrl-D.
- The badge resumes the last app at boot. Hold a Menu button during reset to get the menu, or
  create `/data/boot.json` with `{"resume": false}`.
- LEDs are very bright: channel values 0-3 for status, 20-50 is already vivid.
- Menu buttons: the right one (GPIO15, `MenuPlus`) moves right/next, the left one (GPIO40,
  `MenuMinus`) moves left/previous. The back silkscreen labels are swapped; ignore them.
- Button presses latch for 1 s after release (`LATCH_MS`), so quick taps aren't lost.
- Apps must subclass `apps.base_app.BaseApp` (not `lib/base_app.py`), take no constructor args, and
  live in a file not named `template.py`/`base_app.py`. A broken app file is skipped at boot; a
  broken `lib/` module, `apps/base_app.py` or `main.py` still stops boot.
- An app using `leds.set_sequence()` must call `leds.unpause()`; the menu pauses the sequencer.
- Per-owner settings live in `/data/owner.json` (`maker_handle`, `nametag_line2`, `broadcast`). It
  is not in the repo, `update.py` never touches it, and reflashing erases it.
- Never call `ble.active(True)` when Bluetooth is already active: it silently kills the presence
  advert. Check `ble.active()` first.
- PNGs must be palette or grayscale, non-interlaced, no alpha. Convert with
  `magick in.png -background white -alpha remove -alpha off -resize 960x672 -gravity center -extent 960x672 -remap scripts/palette.gif -strip out.png`.
- Use `uv run ...`; no system Python packages are needed.
