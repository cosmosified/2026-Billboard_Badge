# Sun SAO, UV only (DigiKey SolderFul BreadBoard)

A fresh start with one sensor: the Adafruit LTR390 (#4831) on a DigiKey SolderFul BreadBoard
(SOLDERBREAD#01-ND), with a keyed 2x3 box header on the back. Plugs into SAO2 (middle port). The
earlier three-sensor layouts are in [WIRING.md](WIRING.md) and [option2/](option2/WIRING.md).

![front](uv_only_front.jpg)

## Board layout

Breadboard pattern: 17 columns. In each column, rows F-J are joined and rows A-E are joined. The
`+`/`-` rails along the top and bottom are joined across, and top and bottom rails are separate.
This layout uses no rails.

## Header pinout (seen from the front of the SAO)

Standard SAO pinout, with VCC top left as checked on the badge. **GND is directly below VCC.**

| | col 1 | col 2 | col 3 |
|---|---|---|---|
| row B (top) | VCC | SDA | GPIO1 |
| row A (bottom) | GND | SCL | GPIO2 |

The header goes on the **back**, with its pins in B1-B3 and A1-A3, soldered on the front.

## Build

1. **Cut 3 links** on the front, between rows A and B in columns 1, 2 and 3 (red X in the photo).
   Without the cuts, VCC/GND, SDA/SCL and GPIO1/GPIO2 would be shorted in pairs.
   Check: B1-A1, B2-A2 and B3-A3 must **not** beep.
2. **Box header** on the back: VCC pin in **B1**, GND in **A1**, key facing the same way as on the
   badge. Solder on the front.
3. **LTR390** on the front, sensor side up, pins in row **J**: VIN 6, 3Vo 7, GND 8, SCL 9, SDA 10,
   INT 11. Its board overhangs the top edge.
4. **4 wires** on the front:

| Wire | From | To | Net |
|---|---|---|---|
| W1 | D1 (column 1 strip, header VCC) | G6 (LTR VIN) | 3.3 V |
| W2 | A1 (header GND pin) | H8 (LTR GND) | GND |
| W3 | D2 (column 2 strip, header SDA) | G10 (LTR SDA) | SDA |
| W4 | A2 (header SCL pin) | H9 (LTR SCL) | SCL |

```mermaid
flowchart LR
    subgraph HDR["Box header (back), SAO2"]
        VCC["VCC B1 (3.3V)"]
        GND["GND A1"]
        SDA["SDA B2 (GPIO17)"]
        SCL["SCL A2 (GPIO18)"]
    end
    subgraph UV["LTR390 #4831, addr 0x53"]
        VIN["VIN col 6"]
        UG["GND col 8"]
        UD["SDA col 10"]
        UC["SCL col 9"]
    end
    VCC -- "W1" --- VIN
    GND -- "W2" --- UG
    SDA -- "W3" --- UD
    SCL -- "W4" --- UC
```

## Checks before plugging in (continuity, nothing powered)

1. A1 to B1, A2 to B2, A3 to B3: **no** beep (cuts done).
2. VCC (B1) to GND (A1): **no** beep.
3. SDA (B2) to SCL (A2): **no** beep.
4. B1 to the LTR's VIN pin, A1 to its GND pin, B2 to its SDA pin, A2 to its SCL pin: beep.

## After plugging in

The LTR390's power LED (if fitted) lights. `uv run mpremote run scripts/sun_probe.py` shows `0x53` in
the I2C scan and `CHECK PASS UV sensor started`. Set the smoke sensor to
`"sensor_included": false` in `/data/sun_sao.json`, since it isn't on this board.
