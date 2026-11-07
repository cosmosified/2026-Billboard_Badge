# Fast-refresh demo (run from firmware/ after a hard reset):
#   uv run mpremote reset; sleep 6; uv run mpremote soft-reset run scripts/fast_refresh_demo.py
# One full refresh with a red box, then fast refreshes moving a black square.
import asyncio as aio
import time
from lib.epd import display
from lib import pixtext


async def refresh(label, **kw):
    t0 = time.ticks_ms()
    display.update(**kw)
    await aio.sleep_ms(200)
    while display._framebuffer_ready.is_set() or not display.is_done_updating():
        await aio.sleep_ms(20)
    print("RESULT %-28s %6d ms" % (label, time.ticks_diff(time.ticks_ms(), t0)))


def frame(text, x):
    display.black.fill(0)  # leave the red plane alone
    pixtext.center(display.black, text, 80, 10)
    display.black.fill_rect(x, 450, 120, 120, 1)


async def main():
    task = aio.create_task(display.run())
    display.clear()
    display.red.fill_rect(700, 260, 200, 120, 1)  # red box, drawn once
    frame("FULL", 60)
    await refresh("1 full")
    for i, x in enumerate((240, 420, 600)):
        frame("FAST %d" % (i + 1), x)
        await refresh("%d fast keep_red" % (i + 2), fast=True, keep_red=True)
    frame("FAST 4 NO KEEP", 780)
    await refresh("5 fast (red driven)", fast=True)
    task.cancel()


aio.run(main())
