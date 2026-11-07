---
inclusion: auto
name: badge-epaper
description: Billboard badge e-paper panel deep dive. Use when changing lib/epd.py, refresh speed, fast refresh (update(fast=True), passes, keep_red, FAST_HOLD_BLACK, 0xB0, rendered_luts.py), ghosting or red creep, CoG command sequence, SPI, BUSY timing, panel power (GPIO48), 0x70 booster config, hwconf panel variants, or debugging a screen that doesn't update.
---

# E-paper panel and driver

## Panel
- Pervasive Displays E2969JS0B1 (iTC 9.7", "driver B"). Variant E2969JS084 ("driver 8") exists;
  `firmware/bin/test_image_84.bin` / `test_image_B1.bin` are 8 MB flash images for each
  (inferred from the names; nothing in the repo says so).
- 960x672 at 121 dpi, black/white/red (Spectra Red R2.0), operating 0-40 C.
- Dual CoG: master (left 480 columns, CS1/BUSY1) and slave (right, CS2/BUSY2). BUSY is low while busy.
- Spec refresh time (B/W/R, 25 C): 31.2 s typical. Measured on this badge: 32.6-33.8 s.
- No partial (windowed) update. The window bytes come from OTP and are forwarded verbatim.
- Docs: `documentation/1P285_00_01_E2969JS0B1_20210517.pdf` (spec),
  `FlyerE2969JS0B120201013.pdf`, `itc97-driver-reference.pdf` and `itc97-driver-sheets.pdf`
  (driver application note for an ESP32-S3 iTC97 driver). Extracted text is in
  `.kiro/knowledge/`. `SSD1680_v0.14.pdf` is a different controller and doesn't apply.

## Framebuffer format
- Two planes, 1 bpp, MSB first (x=0 at bit 7), rows of 120 bytes: bytes 0-59 go to the master CoG,
  60-119 to the slave. Each plane is 80,640 bytes; each half-plane 40,320.
- Waveform table per pixel = (red << 1) | bw: 0 paper, 1 ink, 2 red, 3 both bits set. Apps never set
  both bits (LVGL and PNG drawing keep the planes exclusive). The driver uses table 3 in fast mode
  for held black pixels (FAST_HOLD_BLACK); in the B1 fast table it is ground in every phase.
- Panel bit order: B1 needs each byte bit-reversed (firmware default); 84 doesn't. Selected by
  `/data/hwconf` btree key `display_pn` (`b"84"` or `b"B1"`; the file is absent on this badge, so
  B1). The same setting picks driver B vs 8 for the fast LUT and pull count (`_driver_b`).

## Refresh sequence in `lib/epd.py`
1. `run()` (polls every 100 ms): clears `_framebuffer_ready` (so a new `update()` during this refresh
   queues another one), picks the fast waveform if requested, builds the hold mask for fast frames,
   splits both planes into halves with the viper `_split_plane` and the bit-reversal LUT (~33-40 ms,
   blocking), and saves the black plane as `_prev_black`.
2. `_reset()`: RST high/low/high (~0.63 s awaited), then `0x70 71 36` (B1 booster config) to both
   CoGs. The app note warns the panel can draw ~2 A during refresh without it.
3. `_send_images()` (blocking): `0x13` DUW `00 3B 00 00 9F 02`, `0x90` DRFW `00 3B 00 A9`, then per
   half: `0x12` RAM_RW `3B 00 14`, `0x10` black plane, `0x12` again, `0x11` red plane.
4. `cog_initial()`: `0x05 7D` / `0x05 00`, `0xD8 80` (MS_SYNC), `0xD6 00` (BVSS), `0xA7 10/00` strobe,
   `0x03 00 11` (OSC); per CoG `0x44 00`, `0x45 80`, strobe, `0x44 06`, `0x45 82`, strobe; then
   `0x60 25` (TCON), `0x61 01` to master (STV_DIR), `0x02 00`.
5. Fast only: `0xB0` + the fast LUT to both CoGs. This is the only window for a custom waveform:
   after the `0x44/0x45/0xA7` sequence (which loads the OTP waveform into those registers) and
   before the DC/DC soft start.
6. `_dcdc_soft_start()`: stepped `0x09` / `0x51` sequence.
7. `_display_refresh()` x passes (1 for full; 3 for fast on B1, 1 on driver 8): wait while both BUSY
   pins are low (it continues once either half is ready), then `0x15 3C`. Later passes re-trigger the
   latched waveform; nothing is resent.
8. `_dcdc_soft_shutdown()`: same BUSY wait, `0x09 7F`, `0x05 7D`, `0x09 00`, BUSY wait, then DC low,
   CS1 low, RST low, CS1 high.
- The app note says `0x44` is the waveform source pointer and `0x45` the bank select; the code's
  "Temperature 0x82@25C" comment is a guess from the reference driver.
- Panel power: `EPD_PWR_EN_PIN = Pin(48, OUT, value=False)` drives the active-low P-FET on at import
  and nothing turns it off. `cog_poweroff()` exists but is never called.

## Timing on this badge (SoftSPI 8 MHz, measured 2026-11-07)
| Stage | Time | Blocks event loop |
|---|---|---|
| poll latency | 0-100 ms | no |
| plane split (viper) | 33-40 ms (313 ms on the first refresh after boot) | yes |
| reset + 0x70 | ~0.63 s | no |
| send planes | ~1.2-1.5 s | yes |
| CoG init | ~1.4 s | no |
| full waveform | ~32.8 s | no |
| fast frame, total | ~7.6 s (3 pulls, ~3.5 s of waveform) | no, except the send |
| LVGL full-screen flush (viper) | ~0.5 s | yes |

## Fast refresh
- API: `display.update(fast=False, keep_red=False, passes=None)`.
- `_fast_lut()` loads `data/rendered_luts.py` on the first fast update, keeps only the bytes it needs
  (`lutb_base` for driver B: 5 tables x 10 groups x 8 bytes; `lut8_nored_clear` for driver 8:
  5 x 9 x 4) and drops the module. If it is missing, fast requests fall back to a full refresh
  ("EPD: no fast waveform").
- `FAST_HOLD_BLACK = True`: before a fast refresh, pixels black in both the previous and new frame
  also get the red bit (table 3, no drive). `_prev_black` (80 KB) is updated on every refresh, full
  or fast; the scratch plane `hold_red` (80 KB) is allocated on the first fast refresh.
- `keep_red=True` replaces tables 2 and 3 with idle groups (`_keep_red_lut`).
- Results on this B1 badge (photos IMG_0604-0610, 2026-11-07):

| Setting | Result |
|---|---|
| 3 pulls + hold (default) | clean black, no ghosts, 7.6 s/frame |
| 2 pulls | new black gray, blotchy, faint ghost; 6.3 s |
| 4 pulls | black turns dark maroon (red pulled up); 8.8 s |
| without hold | black that stays put turns maroon/red over 1-2 frames |
| keep_red=True | red dims over the frames and ghosts appear; a plain fast frame restores red |
| 10 fast frames held | black from the last full refresh stays neutral black |
| new black from a fast frame | slightly warm (maroon-ish) |

- Guidance for apps: use `fast=True` for frequent updates (games, counters, Life). Do a full refresh
  periodically or when idle to restore neutral black and clean red. Don't use `keep_red`.
- Test scripts: `scripts/fast_refresh_demo.py`, `ghost_compare.py` (edit `PASSES`, `FULL_EVERY`),
  `hold_test.py`. Run with `uv run mpremote reset`, wait ~6 s, then
  `uv run mpremote soft-reset run scripts/<name>.py`. Each prints `RESULT <label> <ms>` lines.

## Hardware SPI: failed experiment
- Upstream PR #3 (SPI(1) at 8 MHz) and PR #4 (SPI(1) at 20 MHz) send the planes over hardware SPI.
  On this badge the refresh then "completes" in ~1.9-3.6 s with BUSY asserted for only ~0.2-0.6 s
  and the screen unchanged. PR #4 worked on some hard-reset boots and failed later, so the failure
  is intermittent. This was tested before the GPIO48 and 0x70 fixes; it has not been retested since.
- The iTC97 app note uses hardware SPI at 4 MHz for planes and bitbanged ~50 kHz for registers.
  Untested ideas: lower baud, registers on SoftSPI and only the planes on SPI, a logic analyzer
  check of SPI mode and CS timing.
- Test any driver change with `sh scripts/boot_test.sh 60` and look for ~33 s after "display working".
