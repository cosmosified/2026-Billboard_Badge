---
inclusion: auto
name: badge-toolchain
description: Billboard badge build, flash, and tooling reference. Use for flashing MicroPython images, rebuilding lv_micropython firmware, ESP-IDF, partitions, esptool, mpremote, uv, update.py, boot_test.sh, e-paper test scripts (fast_refresh_demo, ghost_compare, hold_test), the desktop simulator, image conversion with ImageMagick, and repo, branch and PR history of this fork.
---

# Toolchain, flashing, simulator, history

## Host tools (uv)
- `pyproject.toml` at the repo root: deps `esptool`, `mpremote` (pyserial comes with them).
  `uv sync` once, then `uv run ...`. Not managed: ImageMagick (`magick`, via Homebrew), node
  (`npx lv_font_conv` for fonts), pygame (for `scripts/led_demo.py`).

## Scripts (`firmware/scripts/`, run from `firmware/`)
Host-side (CPython, `uv run`):
- `update.py [ls|push|pull] [--reset] [-v]`: SHA-256 diff of `firmware/badge/` vs the badge
  (via `check_filesystem.py` run on the badge). `push` copies new/changed files and deletes badge
  files not present locally (never `/data/*` or `__pycache__`). `pull` copies everything to
  `firmware/badge-backup/`. Without `--reset` the badge is left at the REPL with `main.py` stopped.
- `boot_test.sh [secs=90]`: writes `{"load_counter": 0}` to `/data/panel_config.json` so the splash
  shows, hard resets, and prints timestamped serial output. `soft_reboot_test.sh [secs]`: same via
  Ctrl-C/Ctrl-D. Both use the first `/dev/cu.usbmodem*` (or `PORT=...`) and exit with a message if
  no badge port exists. With resume on, expect a second refresh: the resumed app redraws.
- `copy_assets.py`: remaps every `assets/graphics/*.png` into `firmware/badge/data/graphics/` with
  `palette.gif` (3 colors: FF0000, FFFFFF, 000000).
- `led_demo.py`: pygame preview of LED sequences using the real `led_bar.py`.

Badge-side (MicroPython; `uv run mpremote reset`, wait ~6 s, then
`uv run mpremote soft-reset run scripts/<name>.py`):
- `fast_refresh_demo.py`: one full refresh with a red box, then fast frames moving a black square.
- `ghost_compare.py`: fast-refresh ghosting/color comparison; edit `PASSES` and `FULL_EVERY`.
- `hold_test.py`: 10 fast frames with held black next to a freshly drawn square.
- `check_filesystem.py`: run by `update.py` to list badge files and hashes.

## Image conversion
`magick in.png -background white -alpha remove -alpha off -resize 960x672 -gravity center -extent 960x672 -remap scripts/palette.gif -strip out.png`
Add `-dither None` for flat art; the default Floyd-Steinberg dither suits photos and gradients.

## Flashing prebuilt firmware
- Bootloader mode: hold BOOT while plugging in, or hold BOOT and tap RESET.
- `firmware/bin/`: `bootloader.bin` (0x0), `partition-table.bin` (0x8000), `micropython.bin`
  (0x10000), plus full 8 MB images `supercon26_factory.bin`, `test_image_84.bin`, `test_image_B1.bin`.
- From `firmware/bin`:
  `uv run python -m esptool erase-flash && uv run python -m esptool --chip esp32s3 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 8MB --flash-freq 80m 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 micropython.bin`
  then from `firmware/`: `uv run python scripts/update.py push --reset` (erase wipes the filesystem).
- Full image restore (inferred): `uv run python -m esptool --chip esp32s3 write-flash 0x0 supercon26_factory.bin`.
- Backup: `uv run python -m esptool --no-stub read-flash 0 8M backup.bin`.
- Use 8MB (`esptool flash-id` reports 8 MB; the partition table ends at exactly 8 MB). Only the
  deprecated lvgl_micropython flash command in `firmware/README.md` and
  `lv_files/boards/ESP32_GENERIC_S3/sdkconfig.board` (`FLASHSIZE_16MB`) still say 16MB.
- Partitions: nvs 0x9000 (24 KB), phy_init 0xF000, factory 0x10000 (3 MB), vfs FAT 0x310000 (~4.9 MB).

## Rebuilding MicroPython + LVGL from source
- The shipped binary is lv_micropython commit `44aa2b153` ("dirty"), MicroPython 1.24.1, ESP-IDF
  v5.2.3 (from `strings micropython.bin`; `firmware/README.md` now says so too). lv_micropython
  isn't vendored; clone it yourself.
1. Install ESP-IDF v5.2.3; `. ./export.sh` in the build shell.
2. `git clone https://github.com/lvgl/lv_micropython firmware/lv_micropython && cd firmware/lv_micropython && git checkout 44aa2b153 && git submodule update --init --recursive`.
3. Copy `firmware/lv_files/*` over `firmware/lv_micropython/` (adds the `BILLBOARD_BADGE` variant:
   240 MHz, octal PSRAM, board name). Fix the hard-coded ESP-IDF path in
   `lv_files/scripts/env-variables-esp32.sh`.
4. `cd ports/esp32 && make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=BILLBOARD_BADGE`
   (clean with the same BOARD/BOARD_VARIANT args).
5. Flash the three images from `build-ESP32_GENERIC_S3-BILLBOARD_BADGE/` with `--flash-size 8MB`.
- `firmware/user_c_modules/badge_utils/` (C PNG decode + C flush callback) is NOT compiled in (the
  cmake line is commented out) and has bugs (`red_data[...] = 0xff` in the flush loop, debug prints).
- `firmware/lvgl_billboard_badge/` and `billboard_badge_lvgl.toml` are the deprecated
  lvgl_micropython path (inconsistent 16/32 MB settings; the toml is an unrelated ST7796 template).

## Desktop simulator (`firmware/sim/`, from upstream PR #11)
- `sim.py` runs the real firmware on lv_micropython's Unix/SDL port (the same MicroPython + LVGL as
  the badge) with fake `machine`, `neopixel`, SPI, I2C. Run `firmware/sim/badge-sim [--scale F]
  [--real-refresh] [--sao-port P] [--no-repl]`; `LV_MICROPYTHON` points it at another interpreter.
- Keys: A = User A, B = User B, Left = Menu -, Right = Menu +, Space = Boot.
- SAO emulation over TCP 127.0.0.1:47100 (`sao_example.py` = 24C02 EEPROM at 0x50).
- Writable state in `firmware/sim/data/` (git-ignored, copied from `firmware/badge/data/`); delete it
  to reset. Build steps in `SIMULATOR.md` (untested on this Mac).
- Different bindings from the badge (e.g. no `inv_p`), not speed- or RAM-accurate.

## This fork (github.com/cosmosified/2026-Billboard_Badge)
- Remotes: `origin` = Hack-a-Day upstream, `fork` = cosmosified (SSH). Work goes on a branch, then a
  tracking PR on the fork, squash-merged into `main` (upstream syncs: real merge commits).
- Upstream PRs merged and tested on the badge: #9 (soft-reset crash fix), #12 (sao.py), #2 (binfont,
  plus a kerning fix), #13 (Life), #8 (Quick Draw), #7 (menu LED wrap past 48 apps), #11 (simulator +
  fixes), #18 (resume last app, fork PR #6), #19 (owner.json nametag, fork PR #7), #21 (BLE
  presence, fork PR #8); the Mandelbrot app from #6.
- Upstream maintainer commits cherry-picked (a76b08d): GPIO48 panel power on, 0x70 booster config,
  BUSY wait on either half, `LedBar.set()` writes.
- Upstream `main` 52c2ee8 merged in fork PR #11 (`sync/upstream-main`, 2026-11-07): hardware SPI +
  viper driver (#4, merged upstream), KITT (#24) and Game of Life (#13) moved to `user_apps/`,
  printable back cover (#17), README fixes (#16). `epd.py` kept the fork's split, queued updates,
  fast refresh and hold-black on top of upstream's SPI; upstream's per-flush print and LED flash in
  `_lv_flush` were dropped. Same PR: soft-reset SPI re-init (3c3c079, reported upstream as issue #25)
  and the new CT emblem logo.
- Upstream wants community apps in `user_apps/<name>/`, installed by hand with `mpremote cp`. Since
  the sync, Life and KITT are not in `firmware/badge/apps/`, so not in the menu.
- Upstream `main` 87a635e (gray support #22) merged on `sync/upstream-gray` (2026-11-08): `epd.py`
  kept the fork driver and dispatches gray/mixed refreshes to upstream's `lib/epd_grayscale.py`;
  README kept the fork's Menu GPIO line and owner/presence sections.
- Upstream `main` 2668f6b (#23 smooth text, #27 Photo Upload, #29 Spiral) merged on
  `sync/upstream-3` (2026-11-08), plus open PRs #30 (OTP read, fixed: GPIO21 re-routed after SPI
  deinit), #15 (battery overlay, ported into the fork's `run()`) and #26 (HTTP poller, without its
  committed Wi-Fi credentials; key no longer logged, failures retried after 60 s).
- Upstream syncs now use real merge commits (2026-11-08, `sync/upstream-ancestry`): an `-s ours`
  merge recorded upstream 2668f6b as merged (content was already in via squashes), then upstream
  43b1564 (final simulator #11) merged normally. Fork `main` now contains upstream `main` as an
  ancestor, so future syncs only conflict where both sides really changed. Keep merging upstream
  with `git merge origin/main` (no squash); fork feature PRs can still be squashed.
- Open upstream PRs not merged as a whole (as of 2026-11-08): #3 (Etch-A-Sketch + input/fast-refresh
  changes), #6 (only its Mandelbrot app is in), #20 (app grid). #15, #26 and #30 are in the fork
  but still open upstream.
- Fork work: uv setup, viper e-paper driver with queued updates (dfa823e), fast refresh (708105e),
  fork PRs #1 button latch, #2 Mandelbrot non-blocking, #3 safe app import, #4 README fixes,
  #5 fast-refresh hold-black, #9 Bluetooth menu toggle; Cosmotronics logo app; boot/e-paper test
  scripts; this knowledge base and `output-behavior.md`.
- `backup/merge-attempt-1` holds the first (abandoned) merge attempt. Feature branches are kept after
  merging.
