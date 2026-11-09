"""Shows the Cosmotronics CT shield logo, with a random rainbow show on the LED bar.

The image was made from the original PNG with ImageMagick (from firmware/). The
source has a gray checkerboard baked in instead of transparency, so low-saturation
mid-gray pixels are turned white first, and specks under 40 pixels are dropped:
    magick "CosmoTronics CT Superhero Emblem.png" \
        -fx "saturation<0.25 && lightness>0.4 ? 1 : u" \
        -resize 960x672 -gravity center -extent 960x672 -dither None \
        -remap scripts/palette.gif \
        -define connected-components:area-threshold=40 \
        -define connected-components:mean-color=true -connected-components 8 \
        -remap scripts/palette.gif -strip -type palette \
        badge/data/graphics/cosmotronics_logo.png

The LED bar runs one effect at a time (rainbow flowing left/right, middle/edges,
pulse, bouncing comet, sparkle), switching to a random one, at a random
brightness, every few seconds.
The LEDs pause while the e-paper image is being sent, since that blocks.

Fireworks: every few seconds one or two black bursts pop up at random spots on
the logo with a fast refresh (~7 s). The previous bursts are taken out of the
framebuffer at the same time, so the fast waveform only partly whitens them and
they linger as fading ghosts. Every FULL_EVERY bursts a full refresh restores
the clean logo and its red.
"""

import math
import random
import time

from apps.base_app import BaseApp
from lib.epd import display, display_height, display_width
from lib.led_bar import NUM_LEDS, leds

LOGO = "/data/graphics/cosmotronics_logo.png"

MIN_BRIGHTNESS = 20  # peak channel value (0-255) is picked from this range
MAX_BRIGHTNESS = 50  # for each effect. The LEDs are very bright.
FRAME_MS = 30
EFFECT_MIN_MS = 4000
EFFECT_MAX_MS = 9000

FIREWORK_MIN_MS = 3000  # pause after one burst frame finishes before the next
FIREWORK_MAX_MS = 8000
FULL_EVERY = 12  # burst frames between full refreshes
BURST_MARGIN = 120  # keep burst centers this far from the edges

_brightness = MAX_BRIGHTNESS  # set by rainbow_show() for each effect


def hue(h, v=255):
    """Hue 0-255 around the color wheel -> (r, g, b), scaled by v/255 and the
    current effect's brightness."""
    h &= 0xFF
    if h < 85:
        r, g, b = 255 - h * 3, h * 3, 0
    elif h < 170:
        h -= 85
        r, g, b = 0, 255 - h * 3, h * 3
    else:
        h -= 170
        r, g, b = h * 3, 0, 255 - h * 3
    s = v * _brightness
    return (r * s // 65025, g * s // 65025, b * s // 65025)


def _triangle(t, period):
    """0 -> 255 -> 0 over `period` steps."""
    x = (t % period) * 510 // period
    return x if x <= 255 else 510 - x


# Each effect is a function of (frame, start hue, speed, direction) -> 8 colors.
def flow_left_right(t, h0, speed, d):
    return [hue(h0 + d * (t * speed - i * 32)) for i in range(NUM_LEDS)]


def flow_middle_edges(t, h0, speed, d):
    # Distance from the center: 0 for the middle two LEDs, 3 for the ends
    return [hue(h0 + d * (t * speed - (abs(2 * i - (NUM_LEDS - 1)) // 2) * 48))
            for i in range(NUM_LEDS)]


def pulse(t, h0, speed, d):
    v = 40 + _triangle(t, 60) * 215 // 255
    return [hue(h0 + t * speed // 2, v)] * NUM_LEDS


def rainbow_breathe(t, h0, speed, d):
    v = 40 + _triangle(t, 80) * 215 // 255
    return [hue(h0 + i * 32 + d * t * speed // 2, v) for i in range(NUM_LEDS)]


def comet(t, h0, speed, d):
    span = 2 * (NUM_LEDS - 1)
    p = (t // 3) % span
    head = p if p < NUM_LEDS else span - p
    out = []
    for i in range(NUM_LEDS):
        dist = abs(i - head)
        v = (255, 90, 30)[dist] if dist < 3 else 0
        out.append(hue(h0 + t * speed, v))
    return out


class Sparkle:
    """Random LEDs flash a random hue and fade out."""

    def __init__(self):
        self.levels = [0] * NUM_LEDS
        self.hues = [0] * NUM_LEDS

    def __call__(self, t, h0, speed, d):
        for i in range(NUM_LEDS):
            self.levels[i] = self.levels[i] * 7 // 8
        if random.getrandbits(3) < 3:
            i = random.getrandbits(3) % NUM_LEDS
            self.levels[i] = 255
            self.hues[i] = h0 + random.getrandbits(8)
        return [hue(self.hues[i], self.levels[i]) for i in range(NUM_LEDS)]


def rainbow_show():
    """Generator for leds.set_sequence(): random effects, forever."""
    global _brightness
    effects = [flow_left_right, flow_middle_edges, pulse, rainbow_breathe, comet, Sparkle()]
    effect = None
    while True:
        last = effect
        while effect is last:
            effect = random.choice(effects)
        _brightness = random.randint(MIN_BRIGHTNESS, MAX_BRIGHTNESS)
        h0 = random.getrandbits(8)
        speed = random.choice((2, 3, 4, 6))
        d = random.choice((1, -1))
        until = time.ticks_add(time.ticks_ms(), random.randint(EFFECT_MIN_MS, EFFECT_MAX_MS))
        t = 0
        while time.ticks_diff(until, time.ticks_ms()) > 0:
            yield effect(t, h0, speed, d), FRAME_MS
            t += 1


def _spark(x: int, y: int, size: int) -> None:
    """A black square of sparks, clipped to the screen; red under it is cleared."""
    x0 = max(0, x - size // 2)
    y0 = max(0, y - size // 2)
    w = min(display_width, x0 + size) - x0
    h = min(display_height, y0 + size) - y0
    if w > 0 and h > 0:
        display.black.fill_rect(x0, y0, w, h, 1)
        display.red.fill_rect(x0, y0, w, h, 0)


def draw_burst(cx: int, cy: int) -> None:
    """One firework: dotted rays from (cx, cy), ending in a bigger spark."""
    rays = random.randint(10, 16)
    radius = random.randint(50, 110)
    turn = random.random() * 2 * math.pi
    for i in range(rays):
        a = turn + i * 2 * math.pi / rays + (random.random() - 0.5) * 0.3
        length = radius * random.randint(75, 100) // 100
        dx, dy = math.cos(a), math.sin(a)
        for r in range(length * 35 // 100, length, 9):
            _spark(int(cx + dx * r), int(cy + dy * r), 3)
        _spark(int(cx + dx * length), int(cy + dy * length), 6)
    _spark(cx, cy, 5)


class LogoApp(BaseApp):
    def __init__(self) -> None:
        super().__init__("Cosmotronics")
        self._base_black = None
        self._base_red = None
        self._next_burst_ms = 0
        self._bursts = 0

    def _show_logo(self) -> None:
        if self._base_black is None:
            display.clear()
            display.draw_png(LOGO)
            self._base_black = bytearray(display._framebuffer_black)
            self._base_red = bytearray(display._framebuffer_red)
        else:
            self._restore_logo()
        display.update()

    def _restore_logo(self) -> None:
        display._framebuffer_black[:] = self._base_black
        display._framebuffer_red[:] = self._base_red

    def _schedule_burst(self) -> None:
        wait = random.randint(FIREWORK_MIN_MS, FIREWORK_MAX_MS)
        self._next_burst_ms = time.ticks_add(time.ticks_ms(), wait)

    def run(self):
        if self.launched:
            self._bursts = 0
            self._show_logo()
            leds.set_sequence(rainbow_show)
            leds.unpause()  # the menu pauses the sequencer
            self._schedule_burst()
            return
        if display.is_busy():
            self._schedule_burst()  # count the pause from the end of the refresh
            return
        if time.ticks_diff(time.ticks_ms(), self._next_burst_ms) < 0:
            return
        self._bursts += 1
        if self._bursts > FULL_EVERY:
            self._bursts = 0
            self._show_logo()
            return
        # Dropping the last bursts here lets the fast waveform fade them to ghosts
        self._restore_logo()
        for _ in range(random.randint(1, 2)):
            draw_burst(random.randint(BURST_MARGIN, display_width - BURST_MARGIN),
                       random.randint(BURST_MARGIN, display_height - BURST_MARGIN))
        display.update(fast=True)
