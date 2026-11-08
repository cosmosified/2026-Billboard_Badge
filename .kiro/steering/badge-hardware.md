---
inclusion: auto
name: badge-hardware
description: Billboard badge hardware reference. Use for GPIO pinout, power/battery/charger, e-paper connector wiring, panel power switch (GPIO48), SAO ports, LEDs, buttons, battery sense, BLE radio, BOM, PCB, and schematic vs firmware discrepancies.
---

# Billboard badge hardware

Sources: `hardware/billboard_pcb/*.kicad_sch`, `billboard_pcb.kicad_pcb` (authoritative pad-to-net
map), `billboard_pcb_BOM.csv`, `production/netlist.ipc`. Live probe of a badge on 2026-11-06.

## Board
- 225.6 x 50.0 mm, 2 copper layers, 1.6 mm. Nearly all parts on the back (B.Cu); e-paper on front.
- Mechanical: `hardware/billboard_mockup-Frame.step`, `billboard_pcb.step`, FreeCAD `*.FCStd`,
  dimension SVGs, `billboard_pcb/silkscreen_render.jpg`.

## MCU (U1)
- ESP32-S3-WROOM-1, LCSC C2913202. Confirmed on hardware as the N8R8 variant: 8 MB flash, 8 MB
  embedded octal PSRAM. IO35/36/37 are unconnected (used by the octal PSRAM).
- `esptool flash-id` (2026-11-06): ESP32-S3 (QFN56) rev v0.2, Wi-Fi + BT 5 LE, dual core + LP core,
  240 MHz, embedded PSRAM 8 MB (AP_3v3), 40 MHz crystal, flash manufacturer 0x20 device 0x4017,
  detected flash size 8 MB. MAC 7c:e8:b1:b6:c2:f4 on the probed badge.
- Live probe: ~8.3 MB free GC heap at idle, MicroPython 1.24.1, LVGL 9.3.0. The 8 MB image and
  partition table use the whole flash.
- USB: native USB-Serial-JTAG on IO19/IO20 (no USB-UART chip, no ESD part).
- No RC delay cap on EN (C1 is on 3V3). R2 5.1k pulls EN up; SW1 "Reset" grounds it.

## GPIO map
| GPIO | Net | Connects to | Firmware |
|---|---|---|---|
| 0 | Boot | SW2 "Boot" to GND, strap pin | `button.Boot` |
| 1 | STATUS_LED | D6 yellow LED, active low (3V3, R14, D6, IO1) | `board.status_led` (inverted Signal) |
| 2 | SAO1_GPIO1 | J8 pin 5 | `sao.SAO1` |
| 3 | EPD_CS2 | right CoG CS (strap pin, harmless) | `epd.EPD_CS2_PIN` |
| 4 | SAO2_GPIO1 | J9 pin 5 | |
| 5 | SAO2_GPIO2 | J9 pin 6 | |
| 6 | SAO3_GPIO2 | J10 pin 6 | |
| 7 | SAO3_GPIO1 | J10 pin 5 | |
| 8 | EPD_BUSY2 | right CoG BUSY (low = busy) | |
| 9 | free | TP8 test pad | `board.TP8_GPIO9` |
| 10 | EPD_DC | both CoGs | |
| 11 | EPD_RST | both CoGs | |
| 12 | EPD_BUSY1 | left (master) CoG BUSY | |
| 13 | EPD_CS1 | left (master) CoG CS | |
| 14 | BAT_SENS | 1:2 divider (R9/R10 10k) on regulator input, ADC2_CH3 | `board.reg_in_v_sns` |
| 15 | Button3 | SW6 to GND | `button.MenuPlus` |
| 16 | Button4 | SW7 to GND, silkscreen "User B" | `button.UserB` |
| 17 | SAO_SDA | all 3 SAO pin 3, pull-up R1 | `sao.i2c` (I2C0) |
| 18 | SAO_SCL | all 3 SAO pin 4, pull-up R3 | |
| 19/20 | USB D-/D+ | USB-C | |
| 21 | EPD_SCL | SPI clock, both CoGs | |
| 38 | WS2812_data | LED1 DIN | `led_bar` |
| 39 | Button1 | SW4, silkscreen "User A" | `button.UserA` |
| 40 | Button2 | SW5 to GND | `button.MenuMinus` |
| 41 | free | TP9 test pad | `board.TP9_GPIO41` |
| 42 | SAO1_GPIO2 | J8 pin 6 | |
| 43/44 | U0TXD/U0RXD | TP3 "TX" / TP4 "RX" test pads (TP5 GND) | not used; board.py says UART(1) interferes with EPD |
| 45 | unconnected | strap pin; epd.py uses it as a dummy SPI MISO | |
| 46 | unconnected | strap pin | |
| 47 | EPD_SDA | SPI MOSI (3-wire, write-only), both CoGs | |
| 48 | EPD_PWR_ENABLE | Q2 P-FET gate, active low, no pull-up | `epd.EPD_PWR_EN_PIN`, driven low (panel on) at import |

Truly free pins for hacking: GPIO9 (TP8), GPIO41 (TP9), UART pads 43/44, plus the 6 SAO GPIOs when no
SAO is fitted.

## Power
- USB-C sink (CC 5.1k pull-downs R12/R13). No USB PD, 5 V only.
- Battery: J1 JST-PH-2.0-style 2-pin (pin 1 GND, pin 2 BAT+; check cable polarity) and TP1/TP2 3x3 mm
  pads in parallel. Silkscreen: "BAT+ / BAT- / 3V - 6V". Intended: 1S LiPo.
- Charger U2 MCP73831-2 (4.20 V), R6 2k = 500 mA. Charge LED D4 (yellow) from VBUS.
- Power path: VBUS through D5 (1N5819W Schottky) to the system rail; Q3 DMG2305 P-FET connects the
  battery when VBUS is absent.
- LDO U3 AP2112K-3.3, 600 mA. Slide switch SW3 grounds the LDO EN (off = charger still works).
- Voltage sense: GPIO14 reads half of the LDO input (VBUS minus a Schottky drop on USB, or battery).
  Measured 4.83 V on USB power.
  `volts = board.reg_in_v_sns.read_uv() * 2 / 1e6`. GPIO14 is ADC2, which conflicts with active Wi-Fi.
  On USB it reads the USB voltage, not the battery, so the battery can't be measured while plugged in.
  Back silkscreen says to remove the divider resistor for standby; by calculation (3.7 V / 20 kohm)
  it draws ~185 uA, not the silkscreen's "18 uA" (not measured).
- E-paper power: Q2 SK2301 P-FET from 3V3 to VCC_EPD, gate on GPIO48, active low, no gate pull-up.
  Firmware drives GPIO48 low at import (rail on) and leaves it on. Switching it off between refreshes
  is an untested power-saving idea; the app note says the panel needs at least 1.5 s off before
  power-up.
- LEDs run from 3V3, not 5 V, with no per-LED decoupling.

## E-paper interface
- Panel: Pervasive Displays E2969JS0B1, 9.7", 960x672 (121 dpi), black/white/red (E Ink Spectra),
  0-40 C operating. Recycled from retail price tags.
- Two Hirose FH34SRJ-24S-0.5SH 24-pin FFC connectors, EPD_ITC1 (master/left) and EPD_ITC2
  (slave/right). Each CoG drives 480 columns.
- Shared: RST, DC, SCL, SDA, VCC, all high-voltage rails; FSYNC/LNSYNC/CLK tied between connectors.
- Separate: CS1/BUSY1 (IO13/IO12) for ITC1, CS2/BUSY2 (IO3/IO8) for ITC2.
- Only ITC1 drives the external booster (pins 2-4: NGDRV, RESE, VPP). Swapping the FFCs swaps
  master/slave roles.
- Booster: Q1 SI1308 N-FET (gate NGDRV, R4 10k pull-down), L1 47 uH, R5 0 ohm current sense,
  D1/D2/D3 1N5819W, rail caps 1 uF.
- FFC pinout: 1 FSYNC, 2 NGDRV, 3 RESE, 4 VPP, 5 VDHR, 6 LNSYNC, 7 CLK, 8 GND, 9 BUSY, 10 RST, 11 DC,
  12 CS, 13 SCL, 14 SDA, 15-16 VCC_EPD, 17 GND, 18 VDDL, 19 VPP, 20 VDH, 21 VGH, 22 VDL, 23 VGL, 24 VCOM.

## LEDs
- 8x XL-2121RGBC-WS2812B (2.1x2.1 mm), chain GPIO38 to LED1 (left) through LED8 (right). LED8 DOUT
  unconnected, so you can't daisy-chain more without rework.
- D6 yellow status LED on GPIO1 (active low). D4 charge LED (hardware only).

## Buttons
- SW4-SW7: 6x6 mm tact switches to GND, internal pull-ups, active low. SW1 Reset (EN), SW2 Boot (IO0).
- Layout (viewed from the back silkscreen): left column SW5 (IO40, top) and SW4 (IO39 "User A");
  right column SW6 (IO15, top) and SW7 (IO16 "User B").
- Silkscreen says SW5 = "Menu +", SW6 = "Menu -"; firmware calls IO40 `MenuMinus` and IO15 `MenuPlus`.
  Tested: the right button (GPIO15) moves the menu selection right (next), the left one (GPIO40)
  moves it left (previous), so the firmware names match the behavior and the silkscreen is wrong.
  One possibility for the swap: the silkscreen is read from the back, where left and right mirror.

## SAO ports (J8 SAO1, J9 SAO2, J10 SAO3)
- Standard 2x3 SAO v1.69bis: 1 VCC (3V3), 2 GND, 3 SDA, 4 SCL, 5 GPIO1, 6 GPIO2.
- One shared I2C bus on GPIO17/18 with a single pull-up pair (R1/R3, value not specified in the BOM).
- SAO1: GPIO2/GPIO42. SAO2: GPIO4/GPIO5. SAO3: GPIO7/GPIO6.
- No SAOs were fitted on the probed badge (I2C scan empty).

## Other
- No other ICs: no accelerometer, sensors, RTC, or USB-UART. Only U1, U2, U3 plus discretes.
- BOM lists TP6/TP7 (GPIO17/18) that don't exist on the PCB (stale BOM).

## Schematic vs firmware/docs discrepancies
1. Fixed (fork PR #4): the root README said User B was GPIO15; it is GPIO16.
2. Menu +/- naming is swapped between silkscreen and firmware (see Buttons).
3. Battery sense uses an ADC2 pin despite the schematic note preferring ADC1.
4. Q2 gate (GPIO48) has no pull-up; until firmware drives it low at import, the panel rail state
   is undefined.

## BOM highlights (LCSC)
U1 ESP32-S3-WROOM-1 (N8R8) C2913202; U2 MCP73831-2-OT C424093; U3 AP2112K-3.3 C51118; LEDs
XL-2121RGBC-WS2812B C5349957; EPD connectors FH34SRJ-24S-0.5SH C2919499; SAO headers C2897404;
tact switches 1TS009B-2500-5000 C255816; slide switch MST22D18G2 C2906280; USB-C C2765186;
battery connector ZX-PH2.0-WT2P C7429689; Q1 SI1308EDL C469327; Q2 SK2301AA C118153; Q3 DMG2305
C5261054; L1 47 uH FHW1812IF470JST C394129. Full list: `hardware/billboard_pcb/billboard_pcb_BOM.csv`.
