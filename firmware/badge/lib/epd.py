"""E-Paper Display Driver for Billboard Badge

Ported from Wiring in https://github.com/PervasiveDisplays/EPD_Driver_GU_large/blob/e408154652802a82e520cc25ba04adeb347d0528/src/EPD_Driver.cpp

--COPYRIGHT--
Brief The drivers and functions of development board
Copyright (c) 2012-2021 Pervasive Displays Inc. All rights reserved.
 Authors: Pervasive Displays Inc.
 Redistribution and use in source and binary forms, with or without
 modification, are permitted provided that the following conditions
 are met:
 1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
 2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in
    the documentation and/or other materials provided with the
    distribution.
 THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import asyncio as aio
import btree
import framebuf
import gc
from machine import Pin, SPI, SoftSPI
import micropython
from micropython import const
import sys
import time

import lvgl

from lib.large_png import show_png
from lib.led_bar import leds

EPD_CS1_PIN = Pin(13, mode=Pin.OUT)
EPD_CS2_PIN = Pin(3, mode=Pin.OUT)
EPD_BUSY1_PIN = Pin(12, mode=Pin.IN)
EPD_BUSY2_PIN = Pin(8, mode=Pin.IN)
EPD_DC_PIN = Pin(10, mode=Pin.OUT)  # Data High Command Low
EPD_RST_PIN = Pin(11, mode=Pin.OUT)
EPD_SCL_PIN = Pin(21, mode=Pin.OUT)
EPD_SDA_PIN = Pin(47, mode=Pin.OUT)
EPD_SPI_MISO_PIN = Pin(45, mode=Pin.IN)  # Not connected, signal not needed
EPD_PWR_EN_PIN = Pin(48, mode=Pin.OUT, value=False)


pdi_cp = 0x9608
pdi_size = 0x96  # 9.69"
display_width = const(960)
half_width = const(display_width // 2)
display_height = const(672)
# Frame-buffer size = width * height / 8 * depth, uint32_t
# image_data_size is really only half the panel pixels, of one color
half_frame_one_color_size = const(display_height * display_width // (8 * 2))
# The width of rows in the full-frame and half-frame framebuffers
# Counting bytes, not pixels, since each byte is 8 packed pixels
display_width_bytes = const(display_width // 8)
display_half_width_bytes = const(display_width_bytes // 2)


# Two displays use different bit orders
def reverse_byte(byte: int) -> int:
    byte = (byte & 0xF0) >> 4 | (byte & 0x0F) << 4
    byte = (byte & 0xCC) >> 2 | (byte & 0x33) << 2
    byte = (byte & 0xAA) >> 1 | (byte & 0x55) << 1
    return byte


# Byte lookup tables for _split_plane: bit-reversed (B1 panel) or unchanged (84 panel)
_REVERSE_LUT = bytes(reverse_byte(b) for b in range(256))
_IDENTITY_LUT = bytes(range(256))


@micropython.viper
def _split_plane(src: ptr8, left: ptr8, right: ptr8, lut: ptr8):
    """Split a full-width plane into the two half-width planes sent to each
    CoG, mapping every byte through `lut` (bit reversal or identity)."""
    row = 0
    while row < display_height:
        s = row * display_width_bytes
        d = row * display_half_width_bytes
        c = 0
        while c < display_half_width_bytes:
            left[d + c] = lut[src[s + c]]
            right[d + c] = lut[src[s + display_half_width_bytes + c]]
            c += 1
        row += 1


# Fast refresh: how many times to re-trigger the latched short waveform per
# update. On driver B (E2969JS0B1) each 0x15 runs a fixed ~1 s, so one pull
# can't clear the previous image; on driver 8 one pull runs the whole table.
FAST_PULLS_B = 3
FAST_PULLS_8 = 1
# Fast refresh only: pixels that were black in the previous frame and stay
# black get both plane bits set, which selects waveform table 3 (ground in
# every phase), so they aren't driven again. Re-driving black pixels pulls up
# the red pigment, so black that stays put turns red over a few fast frames.
FAST_HOLD_BLACK = True


@micropython.viper
def _hold_black(black: ptr8, prev: ptr8, red: ptr8, out: ptr8, n: int):
    """out = red | (black & prev): mark pixels black in both frames.
    Apps keep the planes exclusive per pixel (LVGL and PNG drawing do), so a
    pixel with both bits set here is always a held black pixel."""
    i = 0
    while i < n:
        out[i] = red[i] | (black[i] & prev[i])
        i += 1


def _keep_red_lut(lut: bytes, group_size: int, groups: int) -> bytes:
    """Copy of a fast LUT with the red tables (2 and 3) replaced by idle
    groups, so red pixels get no drive. Table index is (red bit << 1) | bw bit;
    the idle group is the table's own last VCOM group (ground, one frame)."""
    b = bytearray(lut)
    idle_at = (4 * groups + groups - 1) * group_size
    idle = bytes(b[idle_at:idle_at + group_size])
    for t in (2, 3):
        for g in range(groups):
            o = (t * groups + g) * group_size
            b[o:o + group_size] = idle
    return bytes(b)


@micropython.viper
def _rgb565_to_planes(src: ptr8, stride: int, w: int, h: int, x1: int, y1: int,
                      black: ptr8, red: ptr8):
    """Convert an LVGL RGB565 (little-endian) area into the black/red planes.
    Color rule, by the top bit of each channel: red if R is set and G, B clear;
    black if all clear; otherwise white."""
    row = 0
    while row < h:
        base = (y1 + row) * 960 + x1
        ro = row * stride
        col = 0
        while col < w:
            i = ro + col * 2
            c = src[i] | (src[i + 1] << 8)
            idx = base + col
            byte = idx >> 3
            mask = 128 >> (idx & 7)
            clear = mask ^ 255
            bits = c & 0x8410  # R top bit 0x8000, G top bit 0x0400, B top bit 0x0010
            if bits == 0x8000:
                red[byte] = red[byte] | mask
                black[byte] = black[byte] & clear
            elif bits == 0:
                black[byte] = black[byte] | mask
                red[byte] = red[byte] & clear
            else:
                black[byte] = black[byte] & clear
                red[byte] = red[byte] & clear
            col += 1
        row += 1


class EPaperDisplay:
    width = display_width
    height = display_height

    def __init__(self) -> None:
        print("Initializing E-Paper Display (Fast Hardware SPI + Viper)")
        EPD_DC_PIN.value(True)
        EPD_RST_PIN.value(True)
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)
        try:
            # After a soft reset SPI(1) keeps its settings but the pins lose
            # their routing, and the constructor skips re-init when the
            # settings match: the bus writes nothing (refresh "done" in ~2 s,
            # panel unchanged). Deinit and construct again to force a full init.
            spi_args = dict(baudrate=20_000_000, sck=EPD_SCL_PIN, mosi=EPD_SDA_PIN, miso=EPD_SPI_MISO_PIN)
            SPI(1, **spi_args).deinit()
            self.spi = SPI(1, **spi_args)
        except Exception:
            self.spi = SoftSPI(
                baudrate=8_000_000,
                sck=EPD_SCL_PIN,
                mosi=EPD_SDA_PIN,
                miso=EPD_SPI_MISO_PIN,
            )
            self.spi.init()

        try:
            with open("/data/hwconf", "rb") as f:
                hwconf = btree.open(f)
                display_pn = hwconf.get(b"display_pn", b"B1")
                if display_pn == b"84":
                    self._reverse_fb_bits = False
                else:
                    self._reverse_fb_bits = True
        except OSError:
            self._reverse_fb_bits = True
        # E2969JS084 = "driver 8"; E2969JS0B1 (the default) = "driver B"
        self._driver_b = self._reverse_fb_bits
        self._fast_luts = None  # loaded from data/rendered_luts.py on first fast update
        self._request = (False, False, None)  # fast, keep_red, passes
        # Black plane of the last refresh, for FAST_HOLD_BLACK (None = unknown)
        self._prev_black = None

        # The framebuffers are set and display should be updated.
        self._framebuffer_ready = aio.Event()
        self._png_blink = False
        self._refreshing_hw = False

        """Each byte is a mini-row of 8 bits for pixels of one color (1 sets the color, 0 is white)
        Bytes are in rows across the screen, as seen on the badge
        0 ------------------------> 59 [60 bytes per row]
        60 ----------------------> 119
        ...                        ...
        [672 rows of 60 bytes per row]
        """
        self._framebuffer_black = bytearray(half_frame_one_color_size * 2)
        self._framebuffer_red = bytearray(half_frame_one_color_size * 2)
        # Framebuffers that can be drawn to directly
        self.black = framebuf.FrameBuffer(
            self._framebuffer_black, display_width, display_height, framebuf.MONO_HLSB
        )
        self.red = framebuf.FrameBuffer(
            self._framebuffer_red, display_width, display_height, framebuf.MONO_HLSB
        )

        # Is the display done updating? Start set since the display is not updating before boot.
        self._display_updated = aio.Event()
        self._display_updated.set()
        gc.collect()

        # Set up lvgl (deinit first if soft-rebooted so C pointers don't corrupt)
        if hasattr(lvgl, "is_initialized") and lvgl.is_initialized():
            if hasattr(lvgl, "deinit"):
                lvgl.deinit()
        lvgl.init()
        # Give LVGL a buffer 2-bytes-per-pixel for RGB565 format
        self._lv_draw_buf = bytearray(display_width * display_height * 2)

        self.lv_display = lvgl.display_create(display_width, display_height)
        self.lv_display.set_color_format(lvgl.COLOR_FORMAT.RGB565)
        self.lv_display.set_buffers(
            self._lv_draw_buf,
            None,
            len(self._lv_draw_buf),
            lvgl.DISPLAY_RENDER_MODE.PARTIAL,
        )
        self.lv_display.set_flush_cb(self._lv_flush)
        self.lv_screen = lvgl.screen_active()
        self.lv_screen.set_size(display_width, display_height)

    def _lv_flush(self, disp, area, color_p):
        x1, y1 = area.x1, area.y1
        w = area.x2 - x1 + 1
        h = area.y2 - y1 + 1
        try:
            stride = lvgl.draw_buf_width_to_stride(w, lvgl.COLOR_FORMAT.RGB565)
        except AttributeError:
            stride = w * 2
        src = color_p.__dereference__(stride * h)
        _rgb565_to_planes(src, stride, w, h, x1, y1,
                          self._framebuffer_black, self._framebuffer_red)
        disp.flush_ready()

    def update(self, fast: bool = False, keep_red: bool = False, passes: int | None = None) -> None:
        """Done updating the framebuffer, update the display with the contents.

        Returns right away; display.run() does the refresh in the background.
        An update requested while a refresh runs is queued: one more refresh
        follows, with the framebuffer contents and options at that time.
        - update():          full refresh on the panel's own waveform (~33 s).
                             The only mode that draws red well.
        - update(fast=True): short waveform from data/rendered_luts.py, ~7.7 s
                             from update() to done (~3.5 s of it is the waveform,
                             3 pulls). Same content updates as a full refresh;
                             it still flashes, three short times.
        - update(fast=True, keep_red=True): fast refresh that gives red pixels no
                             drive. On the B1 panel red dims over these frames,
                             and a plain fast refresh restores it.
        `passes` overrides how many times the fast waveform is re-triggered.
        """
        self._request = (fast, keep_red, passes)
        self._framebuffer_ready.set()

    def clear(self):
        """Clear framebuffers to full white"""
        self.black.fill(0)
        self.red.fill(0)

    def is_done_updating(self):
        """Is the display done updating?"""
        return self._display_updated.is_set()

    def draw_image(self, image, height: int, width: int, row: int = 0, col: int = 0):
        for img_r in range(height):
            for img_c in range(width):
                color = image[img_r][img_c]
                red = color[0] > 127
                black = color[0] < 128 and color[1] < 128 and color[2] < 128
                self.black.pixel((col + img_c), (row + img_r), int(black))
                self.red.pixel((col + img_c), (row + img_r), int(red))

    def draw_png(self, filename: str, row: int = 0, col: int = 0):
        gc.collect()
        self._png_blink = not self._png_blink
        leds[0] = (0, 0, 50) if self._png_blink else (0, 0, 10)
        leds.write()
        print(f"Loading {filename} This will take a while... {time.time()}")
        show_png(filename, self._framebuffer_black, self._framebuffer_red, row, col)
        leds[0] = (0, 0, 0)
        leds.write()
        print("Done loading png")
        gc.collect()

    async def _blink_red_while_refreshing(self):
        state = False
        while self._refreshing_hw:
            state = not state
            leds[0] = (40, 0, 0) if state else (0, 0, 0)
            leds.write()
            await aio.sleep_ms(200)

    async def run(self):
        black_left = bytearray(half_frame_one_color_size)
        black_right = bytearray(half_frame_one_color_size)
        red_left = bytearray(half_frame_one_color_size)
        red_right = bytearray(half_frame_one_color_size)
        hold_red = None  # allocated on the first fast refresh that uses it
        while True:
            if self._framebuffer_ready.is_set():
                self._display_updated.clear()
                # Clear before copying the framebuffers: an update() requested
                # while this refresh runs then triggers another refresh,
                # instead of being dropped.
                self._framebuffer_ready.clear()
                fast, keep_red, passes = self._request
                # No fast waveform (missing data/rendered_luts.py) means a full
                # refresh, which must not get the fast-only hold mask
                wave = self._fast_lut(keep_red) if fast else None
                tick = time.ticks_ms()
                lut = _REVERSE_LUT if self._reverse_fb_bits else _IDENTITY_LUT
                red = self._framebuffer_red
                if wave is not None and FAST_HOLD_BLACK and self._prev_black is not None:
                    if hold_red is None:
                        hold_red = bytearray(len(red))
                    _hold_black(self._framebuffer_black, self._prev_black, red,
                                hold_red, len(red))
                    red = hold_red
                _split_plane(self._framebuffer_black, black_left, black_right, lut)
                _split_plane(red, red_left, red_right, lut)
                if self._prev_black is None:
                    self._prev_black = bytearray(self._framebuffer_black)
                else:
                    self._prev_black[:] = self._framebuffer_black
                print("Split planes in", time.ticks_diff(time.ticks_ms(), tick), "ms")
                await self.global_update(black_left, red_left, black_right, red_right,
                                         wave, keep_red, passes)
                gc.collect()
                if self._framebuffer_ready.is_set():
                    print("Another update was requested during the refresh")
                else:
                    self._display_updated.set()
            await aio.sleep_ms(100)

    async def global_update(
        self,
        black_left: bytearray | bytes | memoryview[int],
        red_left: bytearray | bytes | memoryview[int],
        black_right: bytearray | bytes | memoryview[int],
        red_right: bytearray | bytes | memoryview[int],
        wave: bytes | None = None,
        keep_red: bool = False,
        passes: int | None = None,
    ):
        """Send the half planes and refresh: on the panel's OTP waveform when
        `wave` is None, otherwise on `wave` (a fast LUT from _fast_lut())."""
        if wave is None:
            passes = 1
        elif passes is None:
            passes = FAST_PULLS_B if self._driver_b else FAST_PULLS_8
        if wave is None:
            mode = "full"
        else:
            mode = f"fast x{passes}{', keep red' if keep_red else ''}"
        print(f"Updating display to new image ({mode})")
        await self._reset()
        tick = time.ticks_ms()
        self._send_images(black_left, red_left, black_right, red_right)
        tock = time.ticks_ms()
        print(tock-tick)

        print("display working")
        tick = time.ticks_ms()
        await self.cog_initial()
        if wave is not None:
            # The only window for a custom waveform: after the 0x44/0x45/0xA7
            # sequence (which loads the OTP waveform into these registers) and
            # before the DC/DC soft start.
            self._send_index_data(0xB0, wave)
        await self._dcdc_soft_start()
        for _ in range(passes):
            # Later passes re-trigger the latched waveform; nothing is resent.
            await self._display_refresh()
        await self._dcdc_soft_shutdown()
        print("Done updating display")
        tock = time.ticks_ms()
        print(tock-tick)

    def _fast_lut(self, keep_red: bool) -> bytes | None:
        """The short waveform for this panel (normal, keep-red), or None."""
        if self._fast_luts is None:
            try:
                import data.rendered_luts as L
                if self._driver_b:
                    base = bytes(L.lutb_base)
                    self._fast_luts = (base, _keep_red_lut(base, 8, 10))
                else:
                    base = bytes(L.lut8_nored_clear)
                    self._fast_luts = (base, _keep_red_lut(base, 4, 9))
            except (ImportError, AttributeError) as ex:
                print(f"EPD: no fast waveform ({ex}), using a full refresh")
                self._fast_luts = ()
            # The module keeps every table as a list; only the bytes are needed
            sys.modules.pop("data.rendered_luts", None)
            gc.collect()
        if not self._fast_luts:
            return None
        return self._fast_luts[1 if keep_red else 0]


    async def cog_initial(self):
        self._send_index_data(0x05, [0x7D])
        await aio.sleep_ms(200)
        self._send_index_data(0x05, [0x00])
        await aio.sleep_ms(10)
        self._send_index_data(0xD8, [0x80])  # MS_SYNC)
        self._send_index_data(0xD6, [0x00])  # BVSS
        self._send_index_data(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data(0xA7, [0x00])
        await aio.sleep_ms(100)
        self._send_index_data(0x03, [0x00, 0x11])  # OSC

        # Display 1
        self._send_index_data_left(0x44, [0x00])
        self._send_index_data_left(0x45, [0x80])
        self._send_index_data_left(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_left(0xA7, [0x00])
        await aio.sleep_ms(100)
        self._send_index_data_left(0x44, [0x06])
        self._send_index_data_left(0x45, [0x82])  # Temperature 0x82@25C
        self._send_index_data_left(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_left(0xA7, [0x00])
        await aio.sleep_ms(100)

        # Display 2
        self._send_index_data_right(0x44, [0x00])
        self._send_index_data_right(0x45, [0x80])
        self._send_index_data_right(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_right(0xA7, [0x00])
        await aio.sleep_ms(100)
        self._send_index_data_right(0x44, [0x06])
        self._send_index_data_right(0x45, [0x82])  # Temperature 0x82@25C
        self._send_index_data_right(0xA7, [0x10])
        await aio.sleep_ms(100)
        self._send_index_data_right(0xA7, [0x00])
        await aio.sleep_ms(100)

        self._send_index_data(0x60, [0x25])  # TCON
        self._send_index_data_left(0x61, [0x01])  # STV_DIR for Display 1
        self._send_index_data(0x02, [0x00])  # VCOM

    async def cog_poweroff(self):
        """CoG shutdown function
        Shuts down the CoG and DC/DC circuit after all update functions
        """
        self._send_index_data(0x09, [0x7F, 0x7D, 0x00])
        await aio.sleep_ms(200)
        while not EPD_BUSY1_PIN.value() and not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(1)
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        await aio.sleep_ms(150)
        EPD_RST_PIN.value(False)

    def _send_index_data(self, index: int, data: bytes | list):
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes([index]))
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)
        EPD_DC_PIN.value(True)
        EPD_CS1_PIN.value(False)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes(data))
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)

    def _send_index_data_left(self, index: int, data: bytes | list | memoryview[int]):
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        EPD_CS2_PIN.value(True)
        self.spi.write(bytes([index]))
        EPD_CS1_PIN.value(True)
        EPD_DC_PIN.value(True)
        EPD_CS1_PIN.value(False)
        self.spi.write(bytes(data))
        EPD_CS1_PIN.value(True)

    def _send_index_data_right(self, index: int, data: bytes | list | memoryview[int]):
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes([index]))
        EPD_CS2_PIN.value(True)
        EPD_DC_PIN.value(True)
        EPD_CS2_PIN.value(False)
        self.spi.write(bytes(data))
        EPD_CS2_PIN.value(True)

    async def _display_refresh(self):
        while not EPD_BUSY1_PIN.value() and not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(100)
        self._send_index_data(0x15, [0x3C])
        await aio.sleep_ms(5)

    async def _reset(self):
        """CoG driver power-on hard reset"""
        await aio.sleep_ms(200)
        EPD_RST_PIN.value(True)
        await aio.sleep_ms(20)
        EPD_RST_PIN.value(False)
        await aio.sleep_ms(200)
        EPD_RST_PIN.value(True)
        await aio.sleep_ms(200)
        EPD_CS1_PIN.value(True)
        EPD_CS2_PIN.value(True)
        await aio.sleep_ms(5)
        self._send_index_data(0x70, [0x71, 0x36])  # B1 booster config, itc97; Errata 9

    def _send_images(
        self,
        black_left: bytearray | bytes | memoryview[int],
        red_left: bytearray | bytes | memoryview[int],
        black_right: bytearray | bytes | memoryview[int],
        red_right: bytearray | bytes | memoryview[int],
    ):
        assert len(black_left) == half_frame_one_color_size
        assert len(red_left) == half_frame_one_color_size
        assert len(black_right) == half_frame_one_color_size
        assert len(red_right) == half_frame_one_color_size

        # Bit order for the panel variant was already applied by _split_plane in run()

        # DUW for both left and right halves
        self._send_index_data(0x13, [0x00, 0x3B, 0x00, 0x00, 0x9F, 0x02])
        # DRFW for Both left and right halves
        self._send_index_data(0x90, [0x00, 0x3B, 0x00, 0xA9])
        ram_rw_data = [0x3B, 0x00, 0x14]
        self._send_index_data_left(0x12, ram_rw_data)  # RAM_RW for left half
        self._send_index_data_left(0x10, black_left)  # Black frame for left half
        self._send_index_data_left(0x12, ram_rw_data)  # RAM_RW for left half
        self._send_index_data_left(0x11, red_left)  # Red frame for left half
        self._send_index_data_right(0x12, ram_rw_data)  # RAM_RW for right half
        self._send_index_data_right(0x10, black_right)  # black frame for right half
        self._send_index_data_right(0x12, ram_rw_data)  # RAM_RW for right half
        self._send_index_data_right(0x11, red_right)  # Red frame for right half

    async def _dcdc_soft_start(self):
        """DC-DC soft-start command
        Implemented after image data are uploaded to CoG
        Specific to mid-sized EPDs only
        """
        self._send_index_data(0x51, [0x50, 0x01])

        for val in range(1, 5):
            self._send_index_data(0x09, [0x1F])
            self._send_index_data(0x51, [0x50, val])
            self._send_index_data(0x09, [0x9F])
            await aio.sleep_ms(2)

        for val in range(1, 11):
            self._send_index_data(0x09, [0x1F])
            self._send_index_data(0x51, [0x0A, val])
            self._send_index_data(0x09, [0x9F])
            await aio.sleep_ms(2)

        for val in range(3, 11):
            self._send_index_data(0x09, [0x7F])
            self._send_index_data(0x51, [0x0A, val])
            self._send_index_data(0x09, [0xFF])
            await aio.sleep_ms(2)

        for val in range(9, 1, -1):
            self._send_index_data(0x09, [0x7F])
            self._send_index_data(0x51, [val, 0x0A])
            self._send_index_data(0x09, [0xFF])
            await aio.sleep_ms(2)

        self._send_index_data(0x09, [0xFF])
        await aio.sleep_ms(10)

    async def _dcdc_soft_shutdown(self):
        """DC-DC soft-shutdown command
        Implemented after image data are uploaded to CoG
        Specific to mid-sized EPDs only
        """
        while not EPD_BUSY1_PIN.value() and not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(100)
        self._send_index_data(0x09, [0x7F])
        self._send_index_data(0x05, [0x7D])
        self._send_index_data(0x09, [0x00])
        await aio.sleep_ms(200)
        while not EPD_BUSY1_PIN.value() and not EPD_BUSY2_PIN.value():
            await aio.sleep_ms(100)
        EPD_DC_PIN.value(False)
        EPD_CS1_PIN.value(False)
        EPD_RST_PIN.value(False)
        EPD_CS1_PIN.value(True)


display = EPaperDisplay()
