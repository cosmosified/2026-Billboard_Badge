"""Checks for the upstream #15/#26/#30 additions (run from firmware/ after a hard reset):
    uv run mpremote reset; sleep 50; uv run mpremote soft-reset run scripts/sync3_test.py
then `uv run mpremote reset` so main.py runs again.

Frame 1 (fast): a black box with the battery icon top right. Frame 2 (full): a
PNG drawn from bytes, with the icon. Prints CHECK PASS/FAIL lines.
"""

import asyncio as aio
import time

from lib.battery import battery_icon, read_reg_in_volts, voltage_to_pct, is_usb
from lib.epd import display


def check(name: str, ok: bool) -> None:
    print(f"CHECK {'PASS' if ok else 'FAIL'} {name}")


async def wait_done() -> int:
    t0 = time.ticks_ms()
    await aio.sleep_ms(200)
    while display.is_busy():
        await aio.sleep_ms(20)
    return time.ticks_diff(time.ticks_ms(), t0)


def icon_bytes(fb: bytearray) -> bytes:
    o = battery_icon
    return b"".join(bytes(fb[r * 120 + o.x // 8 : r * 120 + (o.x + o.w) // 8]) for r in range(o.y, o.y + o.h))


async def main() -> None:
    task = aio.create_task(display.run())
    volts = read_reg_in_volts()
    print(f"reg_in {volts:.3f} V usb={is_usb(volts)} pct={voltage_to_pct(volts)}")
    check("regulator input reads 3-5.5 V", 3.0 < volts < 5.5)

    display.overlay = battery_icon  # wanted() is True outside main.py
    display.clear()
    display.black.fill_rect(300, 200, 360, 272, 1)
    before = icon_bytes(display._framebuffer_black)
    display.update(fast=True)
    print(f"RESULT fast+icon {await wait_done()} ms")
    check("app framebuffer restored after the icon", icon_bytes(display._framebuffer_black) == before)
    check("panel copy (_prev_black) has the icon", icon_bytes(display._prev_black) != before)

    with open("/data/graphics/cosmotronics_logo.png", "rb") as f:
        data = f.read()
    display.clear()
    display.draw_png(data)
    check("PNG from bytes drew something", any(display._framebuffer_red))
    display.update()
    print(f"RESULT png-bytes {await wait_done()} ms")
    try:
        display.draw_png(b"not a png")
        check("bad PNG bytes rejected", False)
    except ValueError as ex:
        check(f"bad PNG bytes rejected ({ex})", True)
    task.cancel()


aio.run(main())
