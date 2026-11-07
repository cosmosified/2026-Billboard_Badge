"""Shows the Cosmotronics CT shield logo, with a random rainbow show on the LED bar.

The image was made from the original PNG with ImageMagick (from firmware/):
    magick "Glossy Cosmotronics CT Shield Logo.png" -background white -alpha remove \
        -alpha off -resize 960x672 -gravity center -extent 960x672 \
        -remap scripts/palette.gif -strip badge/data/graphics/cosmotronics_logo.png

The LED bar runs one effect at a time (rainbow flowing left/right, middle/edges,
pulse, bouncing comet, sparkle), switching to a random one, at a random
brightness, every few seconds.
The LEDs pause while the e-paper image is being sent, since that blocks.
"""

import random
import time

from apps.base_app import BaseApp
from lib.epd import display
from lib.led_bar import NUM_LEDS, leds

LOGO = "/data/graphics/cosmotronics_logo.png"

MIN_BRIGHTNESS = 20  # peak channel value (0-255) is picked from this range
MAX_BRIGHTNESS = 50  # for each effect. The LEDs are very bright.
FRAME_MS = 30
EFFECT_MIN_MS = 4000
EFFECT_MAX_MS = 9000

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


class LogoApp(BaseApp):
    def __init__(self) -> None:
        super().__init__("Cosmotronics")

    def run(self):
        if self.launched:
            display.clear()
            display.draw_png(LOGO)
            display.update()
            leds.set_sequence(rainbow_show)
            leds.unpause()  # the menu pauses the sequencer
