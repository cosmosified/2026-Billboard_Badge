"""LTR-390UV-01 UV and ambient light sensor on I2C (Adafruit #4831).

    from lib.ltr390 import LTR390
    uv = LTR390(i2c)          # raises OSError if nothing answers at 0x53
    counts = uv.read_uvs()    # None until a new conversion is ready
    LTR390.uvi(counts)        # UV index

Runs in UVS mode at gain 18x and 20-bit resolution (400 ms per conversion,
repeated every 500 ms). The datasheet's UV sensitivity at that setting is
2300 counts per UV index.
"""

ADDR = 0x53
PART_ID = 0xB2

_MAIN_CTRL = 0x00
_MEAS_RATE = 0x04
_GAIN = 0x05
_PART_ID = 0x06
_MAIN_STATUS = 0x07
_UVS_DATA = 0x10

_UVS_MODE_ENABLE = 0x0A  # UVS_MODE (bit 3) + LS_EN (bit 1)
_RES20_RATE500 = 0x04  # resolution 20 bit (bits 6:4 = 0), rate 500 ms (bits 2:0 = 4)
_GAIN_18X = 0x04
_DATA_READY = 0x08
_COUNTS_PER_UVI = 2300


class LTR390:
    def __init__(self, i2c, addr: int = ADDR) -> None:
        self.i2c = i2c
        self.addr = addr
        part = self._read(_PART_ID, 1)[0]
        if part != PART_ID:
            raise OSError(f"LTR390 part id {part:#04x} at {addr:#04x}, expected {PART_ID:#04x}")
        self._write(_MEAS_RATE, _RES20_RATE500)
        self._write(_GAIN, _GAIN_18X)
        self._write(_MAIN_CTRL, _UVS_MODE_ENABLE)

    def _read(self, reg: int, n: int) -> bytes:
        return self.i2c.readfrom_mem(self.addr, reg, n)

    def _write(self, reg: int, value: int) -> None:
        self.i2c.writeto_mem(self.addr, reg, bytes((value,)))

    def read_uvs(self) -> int | None:
        """Raw 20-bit UV count of the latest conversion, or None if no new one is ready."""
        if not self._read(_MAIN_STATUS, 1)[0] & _DATA_READY:
            return None
        b = self._read(_UVS_DATA, 3)
        return (b[0] | b[1] << 8 | b[2] << 16) & 0xFFFFF

    @staticmethod
    def uvi(counts: int) -> float:
        """UV index for a raw count at gain 18x, 20 bit."""
        return counts / _COUNTS_PER_UVI
