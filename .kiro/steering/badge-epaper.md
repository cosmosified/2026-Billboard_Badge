---
inclusion: auto
name: badge-epaper
description: Billboard badge e-paper panel deep dive. Use when changing lib/epd.py, refresh speed, fast refresh / LUT waveforms (0xB0, rendered_luts.py), CoG command sequence, SPI, BUSY timing, hwconf panel variants, or debugging a screen that doesn't update.
---

# E-paper panel and driver

## Panel
- Pervasive Displays E2969JS0B1 (iTC 9.7", "driver B"). Variant E2969JS084 ("driver 8") exists;
  `firmware/bin/test_image_84.bin` / `test_image_B1.bin` are 8 MB flash images for each.
- 960x672 at 121 dpi, black/white/red (Spectra Red R2.0), operating 0-40 C.
- Dual CoG: master (left 480 columns, CS1/BUSY1) and slave (right, CS2/BUSY2). BUSY is low while busy.
- Spec refresh time (B/W/R, 25 C): 31.2 s typical. Measured on this badge: 32.6-33.8 s.
- No partial update. The window bytes come from OTP and are forwarded verbatim.
- Docs: `documentation/1P285_00_01_E2969JS0B1_20210517.pdf` (spec),
  `FlyerE2969JS0B120201013.pdf`, `itc97-driver-reference.pdf` and `itc97-driver-sheets.pdf`
  (detailed driver application note for an ESP32-S3 iTC97 driver). Extracted text is in
  `.kiro/knowledge/`. `SSD1680_v0.14.pdf` is a different controller and doesn't apply.

## Framebuffer format
- Two planes, 1 bpp, MSB first (x=0 at bit 7), rows of 120 bytes: bytes 0-59 go to the master CoG,
  60-119 to the slave. Each plane is 80,640 bytes; each half-plane 40,320.
- Waveform table per pixel = (red << 1) | bw: 0 paper, 1 ink, 2 red, 3 unreachable (never set both).
- Panel bit order: B1 needs each byte bit-reversed (firmware default); 84 doesn't. Selected by
  `/data/hwconf` btree key `display_pn` (`b"84"` or `b"B1"`; file absent on this badge, so B1).

## Command sequence in `lib/epd.py` (`global_update`)
1. `_reset()`: RST high/low/high with ~0.6 s of awaited sleeps.
2. `_send_images()` (blocking): `0x13` DUW `00 3B 00 00 9F 02`, `0x90` DRFW `00 3B 00 A9`, then per
   half: `0x12` RAM_RW `3B 00 14`, `0x10` black plane, `0x12` again, `0x11` red plane.
3. `cog_initial()`: `0x05 7D` / `0x05 00`, `0xD8 80` (MS_SYNC), `0xD6 00` (BVSS), `0xA7 10/00` strobe,
   `0x03 00 11` (OSC); per CoG `0x44 00`, `0x45 80`, strobe, `0x44 06`, `0x45 82`, strobe; then
   `0x60 25` (TCON), `0x61 01` to master (STV_DIR), `0x02 00`.
4. `_dcdc_soft_start()`: stepped `0x09` / `0x51` sequence.
5. `_display_refresh()`: wait BUSY high on both, `0x15 3C`.
6. `_dcdc_soft_shutdown()`: wait BUSY, `0x09 7F`, `0x05 7D`, `0x09 00`, wait BUSY, DC/CS1/RST low.
- The app note says `0x44` is the waveform source pointer and `0x45` the bank select (the code's
  "Temperature 0x82@25C" comment is a guess). `0xA7` latches the OTP waveform.
- The app note's B1 sequence also sends `0x70 71 36` (booster config) to both CoGs; it warns that
  without it the panel can draw ~2 A during refresh. The current firmware doesn't send it.
- `cog_poweroff()` exists but is never called; GPIO48 (panel power switch) is never driven.

## Timing on this badge (SoftSPI 8 MHz)
| Stage | Time | Blocks event loop |
|---|---|---|
| poll latency | 0-100 ms | no |
| reset | ~0.6 s | no |
| bit reversal + send | ~5.3-5.9 s | yes |
| CoG init | ~1.4 s | no |
| refresh waveform | ~32.6 s | no |

## Hardware SPI: failed experiment
- Upstream PR #3 (SPI(1) at 8 MHz) and PR #4 (SPI(1) at 20 MHz, viper split/LUT) send the planes over
  hardware SPI. On this badge the refresh then "completes" in ~1.9-3.6 s with BUSY asserted for only
  ~0.2-0.6 s and the screen unchanged. PR #4 worked on some hard-reset boots (33 s refresh) and failed
  on later refreshes, so the failure is intermittent.
- The iTC97 app note uses hardware SPI at 4 MHz for planes and bitbanged ~50 kHz for registers,
  re-pointing the GPIO matrix between modes, and documents faults where BUSY never goes ready.
  Untested ideas: lower baud (4 MHz), keep registers on SoftSPI and only the planes on SPI, add the
  `0x70` booster config, check SPI mode/CS timing with a logic analyzer.
- Test any driver change with `sh scripts/boot_test.sh 60` and look for ~33 s after "display working".

## Fast refresh (not merged)
- `data/rendered_luts.py` holds custom 0xB0 waveforms: `lut8_*` (180 bytes, driver 8) and `lutb_base`
  (400 bytes, driver B). Nothing imports it on main.
- From the app note: write `0xB0` exactly once per session, after the third `0xA7` strobe and before the
  DC/DC soft start. B1 fast mode re-triggers `0x15` three times (~1.07 s each, ~3.5 s total vs ~34 s).
  Fast mode is black/white only; red fades with each fast frame and needs a full refresh to restore.
- Upstream PR #3 implemented `display.update(fast=True, keep_red=...)` this way, but bundled it with
  hardware SPI. Porting only its fast-refresh logic onto the SoftSPI driver is a promising hack.
