# Billboard Badge Firmware

# Host tools (uv)
The host-side tools (`esptool`, `mpremote`) are managed with [uv](https://docs.astral.sh/uv/) via `pyproject.toml` in the repo root.
Run `uv sync` once, then prefix commands with `uv run`, ex. from `firmware/`:

- Push the badge files: `uv run python scripts/update.py push --reset`
- Test a refresh after a hard reset: `sh scripts/boot_test.sh [seconds]`, or after a soft reboot (Ctrl-C, Ctrl-D, as Thonny does): `sh scripts/soft_reboot_test.sh [seconds]`. Both reset the boot counter so the splash screen shows, and print the serial log with timestamps. A real full refresh takes ~33 s after "display working"; one that finishes in a second or two means the panel never redrew.
- Flash the pre-built bins: `cd bin && uv run python -m esptool erase-flash && uv run python -m esptool --chip esp32s3 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 8MB --flash-freq 80m 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 micropython.bin`


# Micropython
The firmware in `bin/` is lv_micropython (commit 44aa2b153) with LVGL 9: MicroPython 1.24.1, built with ESP-IDF v5.2.3, for the 8 MB flash ESP32-S3-WROOM-1 (N8R8) on the badge.
Stock MicroPython (for example v1.27.0 from https://micropython.org/download/ESP32_GENERIC_S3/, `Firmware (Support for Octal-SPIRAM)`) boots on the badge, but it has no `lvgl` module, so the badge apps won't run on it:
`esptool.py --baud 460800 write_flash 0 ~/Downloads/ESP32_GENERIC_S3-SPIRAM_OCT-20251209-v1.27.0.bin`

# Build notes (lv_micropython)

You should not need to go through this unless you want to modify the LVGL
behavior or add addional compiled C modules. Most hacking is effective just in 
micropython (the .py files), which is much easier.

Install esp-idf: https://github.com/lvgl/lv_micropython/blob/master/ports/esp32/README.md#setting-up-the-toolchain-and-esp-idf
`./install.sh` and `. ./export.sh` in the shell that will be doing builds.

In `firmware/lv_micropython/ports/esp32` run `make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=BILLBOARD_BADGE`  to build and `python -m esptool --chip esp32s3 -b 460800 --before default_reset --after hard_reset write_flash --flash_mode dio --flash_size 8MB --flash_freq 80m 0x0 build-ESP32_GENERIC_S3-BILLBOARD_BADGE/bootloader/bootloader.bin 0x8000 build-ESP32_GENERIC_S3-BILLBOARD_BADGE/partition_table/partition-table.bin 0x10000 build-ESP32_GENERIC_S3-BILLBOARD_BADGE/micropython.bin` to flash.
You will need to `make clean BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=BILLBOARD_BADGE` (yes including the arguments) to rebuild. The BOARD argument defines a build directory, so clean won't clean the correct directory without it.

Flashing the pre-built bin files: From `firmware/` run `python -m esptool --chip esp32s3 -b 460800 --before default_reset --after hard_reset write_flash --flash_mode dio --flash_size 8MB --flash_freq 80m 0x0 bin/bootloader.bin 0x8000 bin/partition-table.bin 0x10000 bin/micropython.bin`. To get into the mode to flash this, you need to hold down the BOOT button while either plugging in or pressing and releasing RESET.

## lv_micropython changes:
Copy the files from `firmware/lv_files/` to their matching paths, ex: `lv_files/foo/` -> `lv_micropython/foo/`.
