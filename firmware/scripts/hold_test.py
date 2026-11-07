# Long hold test for FAST_HOLD_BLACK (run from firmware/ after a hard reset):
#   uv run mpremote reset; sleep 6; uv run mpremote soft-reset run scripts/hold_test.py
# A full refresh draws a black heading and a black square on the left. Then
# FRAMES fast refreshes change only a small counter, so the heading and the
# left square stay black (and undriven) the whole time. The last frame adds a
# freshly driven black square on the right: compare the two squares.
import asyncio as aio
import time
from lib.epd import display
from lib import pixtext

FRAMES = 10
PASSES = 3


async def refresh(label, **kw):
    t0 = time.ticks_ms()
    display.update(**kw)
    await aio.sleep_ms(200)
    while display._framebuffer_ready.is_set() or not display.is_done_updating():
        await aio.sleep_ms(20)
    print("RESULT %-22s %6d ms" % (label, time.ticks_diff(time.ticks_ms(), t0)))


def frame(counter, fresh_square=False):
    display.clear()
    pixtext.center(display.black, "HOLD", 60, 12)
    display.black.fill_rect(120, 330, 220, 220, 1)  # held square
    if fresh_square:
        display.black.fill_rect(620, 330, 220, 220, 1)  # freshly driven square
    pixtext.text(display.black, "%02d" % counter, 430, 400, 6)


async def main():
    task = aio.create_task(display.run())
    frame(0)
    await refresh("start (full)")
    for n in range(1, FRAMES + 1):
        frame(n, fresh_square=(n == FRAMES))
        await refresh("frame %d (fast x%d)" % (n, PASSES), fast=True, passes=PASSES)
    task.cancel()


aio.run(main())
