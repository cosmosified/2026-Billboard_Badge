"""Gray refresh test (run from firmware/ after a hard reset):
    uv run mpremote reset; sleep 50; uv run mpremote soft-reset run scripts/gray_test.py
then `uv run mpremote reset` so main.py runs again.

Frame 1: grayscale (white | gray | black bands). Frame 2: mixed (white, red,
gray, black bands). Frame 3: a fast black/white frame, to check the normal
paths still work after gray. Prints RESULT <label> <ms> for each.
"""

import asyncio as aio
import time

from lib.epd import display

BAND = 240


def bands(colors: list) -> None:
    """Fill vertical bands; each color is (black_bit, red_bit)."""
    display.clear()
    for i, (b, r) in enumerate(colors):
        if b:
            display.black.fill_rect(i * BAND, 0, BAND, 672, 1)
        if r:
            display.red.fill_rect(i * BAND, 0, BAND, 672, 1)


async def frame(label: str, **opts) -> None:
    t0 = time.ticks_ms()
    display.update(**opts)
    await aio.sleep_ms(200)
    while display._framebuffer_ready.is_set() or not display.is_done_updating():
        await aio.sleep_ms(20)
    print(f"RESULT {label:<10} {time.ticks_diff(time.ticks_ms(), t0)} ms")


async def main() -> None:
    task = aio.create_task(display.run())
    print("supports_grayscale", display.supports_grayscale)
    bands([(0, 0), (0, 1), (1, 0), (0, 0)])  # white, gray, black, white
    await frame("grayscale", grayscale=True)
    bands([(0, 0), (0, 1), (1, 1), (1, 0)])  # white, red, gray, black
    await frame("mixed", mixed=True)
    display.clear()
    display.black.fill_rect(300, 200, 360, 272, 1)
    await frame("fast", fast=True)
    try:
        display.update(fast=True, grayscale=True)
        print("CHECK FAIL fast+grayscale accepted")
    except ValueError as ex:
        print(f"CHECK PASS fast+grayscale rejected: {ex}")
    task.cancel()


aio.run(main())
