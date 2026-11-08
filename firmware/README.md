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


## Optional B1 gray support

Ordinary `display.update()`, `display.draw_png(...)`, and LVGL flushes keep
upstream black/red/white behavior. Gray is explicitly requested per render and
refresh; its waveform module and tables load only when used.

`display.supports_grayscale` identifies supported B1 panels. The 84 panel keeps
its ordinary rendering; applications must select that fallback before requesting
a gray mode. Gray requests on unsupported panels raise `ValueError`.

For four colors, use `mixed=True` consistently:

```python
from lib.epd import display

# After creating and invalidating your LVGL screen:
if display.supports_grayscale:
    display.refresh_lvgl(mixed=True)
    display.update(mixed=True)
else:
    display.refresh_lvgl()
    display.update()
```

`refresh_lvgl()` calls LVGL's immediate refresh and restores the conversion mode
even if rendering fails. It does not start the physical panel refresh.
`draw_png(path, mixed=True)` supports gray in palette/grayscale PNGs. Match its
mode to the later `update(mixed=True)` call. RGB565 text edges and PNG samples
map to black below 96, gray below 204, and white otherwise; red remains red in mixed
mode. This produces one physical gray tone, not a full grayscale ramp.

Applications drawing directly into the two existing framebuffers can use:

| Color in mixed mode | Black-plane bit | Red-plane bit |
| --- | --- | --- |
| White | 0 | 0 |
| Black | 1 | 0 |
| Red | 0 | 1 |
| Gray | 1 | 1 |

The mixed refresh first draws an ordinary color image with gray sites cleared
to white, then prepares those sites with six white pulls and paints gray with
three pulls while holding other pixels. The app's buffers are not modified.
The existing ordinary interpretation of overlapping black/red bits is unchanged
when mixed mode is not requested.

For pages with no red, `grayscale=True` selects the faster black/white/gray
path: the second plane represents gray instead of red. Use it consistently in
`refresh_lvgl`, `draw_png`, and `update`; do not combine it with `mixed=True`.
Unknown or previously colored panel content receives a full white cleanup first.

Custom waveform waits are bounded and check both display controllers. Updates
queued during a refresh coalesce into the latest requested image and mode.
