# Sun SAO wiring guide (option 1)

Option 1: smoke and loudness sensors on the protoboard front, UV sensor on a STEMMA QT cable, wires
on the back. Option 2 (loudness board on a Grove cable, socket on the back) is in
[option2/WIRING.md](option2/WIRING.md); it was set aside because the socket doesn't fit in the gap
between the SAO and the badge.

Plugs into **SAO2 or SAO3** (both GPIO pins are ADC1 there; SAO1's GPIO2 is GPIO42, which has no ADC).

| Front (all parts, faces out) | Back (wires only, faces the badge) |
|---|---|
| ![front](front.jpg) | ![back](back.jpg) |

Hole names are **column letter + row number as seen from the FRONT**: columns A-O left to right,
rows 1-19 top to bottom. On the back photo the letters run O-A because the board is flipped.

## How this protoboard is connected

Measured from the photos; beep it with a meter before soldering (step 1 below).

- **V+ rail**: right edge on the front (column O rows 4-13, N rows 1-3), runs to the V+ pad.
- **GND rail**: left edge on the front (column A rows 4-12, B rows 1-3), runs to the GND pad.
- **Strips**: each column between the rails is a vertical strip, cut into blocks: rows 1-3, 4-8,
  9-13, 14-18. A leg and a wire in the same column and the same block are connected.
- **Pads** (row 19): GND C19, `1` D19/E19, `2` F19/G19, `D` (SDA) H19/I19, `C` (SCL) J19/K19,
  V+ L19/M19.

| Pad | SAO pin | On SAO2 | On SAO3 | Used for |
|---|---|---|---|---|
| V+ | 1 VCC | 3.3 V | 3.3 V | all sensors |
| GND | 2 GND | GND | GND | all sensors |
| D | 3 SDA | GPIO17 | GPIO17 | QT port SDA (UV sensor) |
| C | 4 SCL | GPIO18 | GPIO18 | QT port SCL (UV sensor) |
| 1 | 5 GPIO1 | GPIO4 | GPIO7 | loudness SIG (analog) |
| 2 | 6 GPIO2 | GPIO5 | GPIO6 | smoke A (analog) |

## Parts and placement (all on the front)

| Part | Legs (hole) | Notes |
|---|---|---|
| Adafruit Qwiic / STEMMA QT Breakout (#5961) | SDA H2, SCL I2, GND J2, VIN K2 | QT socket toward the top edge. A STEMMA QT cable runs to the LTR390 (#4831), which can sit anywhere the sun reaches. |
| Seeed Grove Loudness v0.9b | GND B10, VCC C10, NC D10, SIG E10 | Solder a 4-pin 2.54 mm header into the row of holes labeled SIG/NC/VCC/GND (next to the Grove connector, which stays unused). NC unused. |
| DFRobot SEN0570 smoke | GND L10, A M10, VCC N10 | Faces out for airflow. |

- The pin orders above are assumed. Put each part's legs in the listed columns, then **read the
  name printed next to each leg**: the wire from that strip goes to that net (table below). If the
  order on your board differs, swap the wire ends to match the names, not the positions.
- Body outlines in the photos are approximate: dry-fit before soldering.
- The #5961 has its own 10k SDA/SCL pull-ups and a green power LED. With the LTR390's 10k and the
  badge's R1/R3, the bus has several pull-ups in parallel; that is fine at 400 kHz. Cut the LED
  trace on its back if you want to save ~1 mA.

## Jumper wires (all on the back)

Use insulated wire (30 AWG wire-wrap is ideal). Wires may cross each other.

| Wire | From | To | Net |
|---|---|---|---|
| W1 | K1 (QT VIN strip) | N1 (V+ rail) | V+ |
| W2 | J1 (QT GND strip) | B1 (GND rail) | GND |
| W3 | I3 (QT SCL strip) | J19 (pad C) | SCL |
| W4 | H3 (QT SDA strip) | H19 (pad D) | SDA |
| W5 | B11 (Grove GND strip) | A11 (GND rail) | GND |
| W6 | C13 (Grove VCC strip) | M19 (V+ pad) | V+ |
| W7 | E13 (Grove SIG strip) | E19 (pad 1) | loudness |
| W8 | N9 (smoke VCC strip) | O8 (V+ rail) | V+ |
| W9 | M9 (smoke A strip) | G19 (pad 2) | smoke |
| W10 | L9 (smoke GND strip) | A9 (GND rail) | GND |

## Build order

1. **Beep the board** (meter on continuity, nothing soldered yet):
   - N1 to O8 to L19: beep (V+). B1 to A11 to C19: beep (GND). V+ to GND: **no** beep.
   - Each strip used above (H-K rows 1-3, B-E rows 9-13, L-N rows 9-13): beeps along its block,
     not to its neighbours. If N13 or B13 beeps to a rail, that is fine (same net as the leg).
   - The old solder blobs on the front at row 5 (columns E-K): wick them or check they don't
     bridge two strips.
2. **Wires W1-W10** on the back, kept flat.
3. **QT breakout, Grove board and smoke sensor** on the front.
4. **Before plugging in**: V+ to GND must not beep. Each pad (1, 2, D, C) must not beep to V+ or GND.
5. **Dry-fit on the badge**: nothing on the back but flat wires and clipped legs. Plug the LTR390
   into the QT socket with a STEMMA QT cable.

## Electrical notes

- Supply is the badge's 3.3 V. LTR390 and SEN0570 are rated 3.3-5 V. The Grove loudness sensor is
  rated 3.5-10 V; it is expected (not yet measured) to work at 3.3 V with its output capped near 1.8 V.
- All analog outputs stay below 3.3 V, so no divider is needed.
- I2C: LTR390 address `0x53`. Other STEMMA QT sensors can be daisy-chained off the LTR390's second
  socket if their addresses differ.
- The smoke sensor needs at least 300 s of warm-up after power-on before readings mean anything.
- Total draw is under 30 mA.
