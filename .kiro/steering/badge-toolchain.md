---
inclusion: auto
name: badge-toolchain
description: Billboard badge build, flash, and tooling reference. Use for flashing MicroPython images, rebuilding lv_micropython firmware, ESP-IDF, partitions, esptool, mpremote, update.py, boot test scripts, the desktop simulator, image conversion with ImageMagick, and repo/PR history.
---

# Toolchain, flashing, simulator, history

## Host tools (uv)
- `pyproject.toml` at the repo root: deps `esptool`, `mpremote` (pyserial comes with them).
  `uv sync` once, then `uv run ...`. Not managed: ImageMagick (`magick`, via Homebrew), node
  (`npx lv_font_conv` for fonts), pygame (for `scripts/led_demo.py`).

## Scripts (`firmware/scripts/`, run from `firmware/`)
- `update.py [ls|push|pull] [--reset] [-v]`: SHA-256 diff of `firmware/badge/` vs the badge
  (via `check_filesystem.py` run on the badge). `push` copies new/changed files and deletes badge
  files not present locally (never `/data/*` or `__pycache__`). `pull` copies everything to
  `firmware/badge-backup/`.
- `boot_test.sh [secs]`: sets `load_counter` to 0, hard resets, prints timestamped serial output
  (splash refresh). `soft_reboot_test.sh [secs]`: same via Ctrl-C/Ctrl-D.
- `copy_assets.py`: remaps every `assets/graphics/*.png` into `firmware/badge/data/graphics/` with
  `palette.gif` (3 colors: FF0000, FFFFFF, 000000).
- `led_demo.py`: pygame preview of LED sequences using the real `led_bar.py`.

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
- Use 8MB. Some README lines and `lv_files/.../sdkconfig.board` say 16MB, but the partition table
  ends at exactly 8 MB.
- Partitions: nvs 0x9000 (24 KB), phy_init 0xF000, factory 0x10000 (3 MB), vfs FAT 0x310000 (~4.9 MB).

## Rebuilding MicroPython + LVGL from source
- The shipped binary is lv_micropython commit `44aa2b153` ("dirty"), MicroPython 1.24.1, ESP-IDF
  v5.2.3 (from `strings micropython.bin`). README's "MicroPython 1.27" is stale. lv_micropython isn't
  vendored; clone it yourself.
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
- `sim.py` runs the real firmware on lvgl_micropython's Unix/SDL port with fake `machine`,
  `neopixel`, SPI, I2C. Run `firmware/sim/badge-sim [--scale F] [--real-refresh] [--sao-port P]`.
- Keys: A = User A, B = User B, Left = Menu -, Right = Menu +, Space = Boot.
- SAO emulation over TCP 127.0.0.1:47100 (`sao_example.py` = 24C02 EEPROM at 0x50).
- Build documented only for Ubuntu (see `SIMULATOR.md`). `firmware/sim/lvgl_micropython` is a
  committed symlink to the PR author's machine; delete it before cloning.
- Different bindings from the badge (e.g. no `inv_p`), not speed- or RAM-accurate.

## This fork (github.com/cosmosified/2026-Billboard_Badge)
- Remotes: `origin` = Hack-a-Day upstream, `fork` = cosmosified (SSH).
- Merged and tested on hardware: upstream PRs #9 (soft-reset crash fix), #12 (sao.py), #2 (binfont,
  plus a kerning fix), #13 (Life), #8 (Quick Draw), #7 (menu LED wrap past 48 apps), #11 (simulator +
  fixes); Mandelbrot app from #6 without PR #4's driver.
- Rejected: #4 and #3 (hardware SPI e-paper failure, see `badge-epaper.md`). #5 touched directories
  deleted upstream.
- Local additions: uv setup, Cosmo nametag, boot test scripts, Cosmotronics logo app with LED show.
- `backup/merge-attempt-1` branch holds the first (abandoned) merge attempt.
