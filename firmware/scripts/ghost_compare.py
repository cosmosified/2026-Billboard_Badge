# Ghosting comparison for fast refresh (run from firmware/ after a hard reset):
#   uv run mpremote reset; sleep 6; uv run mpremote soft-reset run scripts/ghost_compare.py
# Edit PASSES and FULL_EVERY below for each run.
# One full refresh (clean start), then 4 fast frames moving a black square left
# to right. Compare the ghosts the old squares leave at each setting.
import asyncio as aio
import time
from lib.epd import display
from lib import pixtext

PASSES = 3       # fast-waveform pulls per fast frame (driver default is 3)
FULL_EVERY = 0   # >0: do a full refresh instead of every Nth fast frame

POSITIONS = (60, 280, 500, 720)  # square x for frames 1-4 (120 px wide, 100 px gaps)


async def refresh(label, **kw):
    t0 = time.ticks_ms()
    display.update(**kw)
    await aio.sleep_ms(200)
    while display._framebuffer_ready.is_set() or not display.is_done_updating():
        await aio.sleep_ms(20)
    print("RESULT %-24s %6d ms" % (label, time.ticks_diff(time.ticks_ms(), t0)))


def frame(text, x):
    display.clear()
    scale = min(10, display.width // pixtext.width(text, 1))
    pixtext.center(display.black, text, 80, scale)
    display.black.fill_rect(x, 400, 120, 120, 1)


async def main():
    task = aio.create_task(display.run())
    label = "P%d%s" % (PASSES, (" FULL/%d" % FULL_EVERY) if FULL_EVERY else "")
    frame("START " + label, POSITIONS[0])
    await refresh("start (full)")
    for i, x in enumerate(POSITIONS[1:] + (None,)):
        n = i + 1
        full = FULL_EVERY and n % FULL_EVERY == 0
        if x is None:
            frame("END " + label, POSITIONS[-1])  # final frame: square stays put
        else:
            frame("%d %s" % (n, label), x)
        if full:
            await refresh("frame %d (full)" % n)
        else:
            await refresh("frame %d (fast x%d)" % (n, PASSES), fast=True, passes=PASSES)
    task.cancel()


aio.run(main())
