"""SAO Probe: check the SAO I2C bus and the Sun SAO's UV sensor from a button.

User A or B: run the probe again. Results go to the LEDs right away, the serial
log, and the e-paper (fast refresh, ~7 s).

LEDs (left to right):
  0 SDA idle level    green = high (OK), red = held low
  1 SCL idle level    green = high (OK), red = held low
  2 LTR390 at 0x53    green = found, red = not found
  3 other devices     blue = something else answered, off = nothing
  4-7 UV reading      green bar, one LED per UV index point (dim white = 0)
"""

import asyncio as aio
import sys

from machine import I2C, Pin

from apps.base_app import BaseApp
from lib import pixtext
from lib.button import UserA, UserB
from lib.epd import display
from lib.led_bar import leds
from lib.ltr390 import ADDR as LTR390_ADDR
from lib.ltr390 import LTR390
from lib.sao import SAO_I2C_BUS, SAO_I2C_SCL, SAO_I2C_SDA

OK = (0, 3, 0)
BAD = (3, 0, 0)
OTHER = (0, 0, 3)
OFF = (0, 0, 0)


class SaoProbeApp(BaseApp):
    show_battery_icon = False

    def __init__(self) -> None:
        super().__init__("SAO Probe")
        self.sleep_ms = 50
        self.runs = 0

    async def _probe(self) -> dict:
        # Read the idle levels with the pins as plain inputs, then hand them
        # back to the I2C peripheral (constructing I2C re-routes the pins)
        sda = Pin(SAO_I2C_SDA, Pin.IN).value()
        scl = Pin(SAO_I2C_SCL, Pin.IN).value()
        i2c = I2C(SAO_I2C_BUS, scl=SAO_I2C_SCL, sda=SAO_I2C_SDA, freq=100_000)
        found = i2c.scan()
        uvs = None
        error = ""
        if LTR390_ADDR in found:
            try:
                sensor = LTR390(i2c)
                for _ in range(20):  # first conversion takes ~400 ms
                    await aio.sleep_ms(100)
                    uvs = sensor.read_uvs()
                    if uvs is not None:
                        break
            except OSError as ex:
                error = f"LTR390 {ex}"
        # Leave the shared bus as lib.sao configures it
        I2C(SAO_I2C_BUS, scl=SAO_I2C_SCL, sda=SAO_I2C_SDA, freq=400_000)
        return {"sda": sda, "scl": scl, "found": found, "uvs": uvs, "error": error}

    def _show_leds(self, r: dict) -> None:
        colors = [
            OK if r["sda"] else BAD,
            OK if r["scl"] else BAD,
            OK if LTR390_ADDR in r["found"] else BAD,
            OTHER if [a for a in r["found"] if a != LTR390_ADDR] else OFF,
        ]
        if r["uvs"] is None:
            colors += [OFF] * 4
        else:
            lit = min(4, round(LTR390.uvi(r["uvs"])))
            bars = [OK] * lit + [OFF] * (4 - lit)
            if lit == 0:
                bars[0] = (1, 1, 1)  # read fine, no UV
            colors += bars
        leds.set(colors)

    def _show_screen(self, r: dict) -> None:
        if display.is_busy():
            return  # the LEDs and the log already have the result
        display.clear()
        b = display.black
        pixtext.center(b, f"SAO PROBE #{self.runs}", 40, 6)
        lines = [
            f"SDA {'HIGH OK' if r['sda'] else 'LOW - HELD DOWN'}",
            f"SCL {'HIGH OK' if r['scl'] else 'LOW - HELD DOWN'}",
            "I2C " + (" ".join(f"{a:02X}" for a in r["found"]) or "NONE"),
        ]
        if r["uvs"] is not None:
            lines.append(f"UV {r['uvs']} = UVI {LTR390.uvi(r['uvs']):.2f}")
        elif LTR390_ADDR in r["found"]:
            lines.append("UV NO READING")
        if r["error"]:
            lines.append(r["error"][:24])
        for i, line in enumerate(lines):
            pixtext.text(b, line, 60, 160 + i * 90, 5)
        pixtext.center(b, "A OR B: PROBE AGAIN", 600, 3)
        display.update(fast=True)

    async def arun(self) -> None:
        try:
            if self.launched or UserA.pressed() or UserB.pressed():
                self.runs += 1
                leds.set([(1, 1, 1)] * 8)  # probing
                r = await self._probe()
                print(f"SAO probe #{self.runs}: SDA={r['sda']} SCL={r['scl']} "
                      f"found={[hex(a) for a in r['found']]} uvs={r['uvs']} {r['error']}")
                self._show_leds(r)
                self._show_screen(r)
        except Exception as ex:
            sys.print_exception(ex)
        await aio.sleep_ms(self.sleep_ms)
