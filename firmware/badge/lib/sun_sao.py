"""Sun SAO sensors (UV, smoke, loudness) and their settings.

Settings come from defaults below, overridden by /data/sun_sao.json, e.g.

    {"sensors": {"loud": {"sensor_included": true}}}

Each sensor has "sensor_included": a sensor that is not included is never
touched (no I2C traffic, its pin is never set up as an ADC). Unknown keys and
values of the wrong type are ignored with a message; a missing or invalid file
means "all defaults".

    from lib.sun_sao import load_config, Sensors
    sensors = Sensors(load_config())
    sensors.read()   # {"uv": counts or None, "smoke": mV, "loud": mV}, included ones only
"""

import json

from machine import ADC, Pin

from lib.ltr390 import LTR390
from lib.sao import SAO2_GPIO1, SAO2_GPIO2, i2c

CONFIG_FILE = "/data/sun_sao.json"

DEFAULTS = {
    "sensors": {
        "uv": {"sensor_included": True, "addr": 0x53},
        "smoke": {"sensor_included": True, "pin": SAO2_GPIO2},
        "loud": {"sensor_included": False, "pin": SAO2_GPIO1},
    },
}


def _merge(defaults: dict, data: dict, where: str) -> dict:
    """Copy of defaults with values from data where the key is known and the type matches."""
    out = {}
    for key, default in defaults.items():
        value = data.get(key, default)
        if isinstance(default, dict):
            if not isinstance(value, dict):
                print(f"sun_sao: {where}{key} must be an object, using defaults")
                value = {}
            out[key] = _merge(default, value, f"{where}{key}.")
        elif type(value) is not type(default):
            print(f"sun_sao: {where}{key}={value!r} has the wrong type, using {default!r}")
            out[key] = default
        else:
            out[key] = value
    for key in data:
        if key not in defaults:
            print(f"sun_sao: unknown setting {where}{key} ignored")
    return out


def load_config(path: str = CONFIG_FILE) -> dict:
    """Settings: DEFAULTS overridden by the JSON file at path. Never raises."""
    try:
        with open(path) as f:
            data = json.load(f)
    except OSError:
        data = {}
    except ValueError as ex:
        print(f"sun_sao: {path} is not valid JSON ({ex}), using defaults")
        data = {}
    if not isinstance(data, dict):
        print(f"sun_sao: {path} must hold a JSON object, using defaults")
        data = {}
    return _merge(DEFAULTS, data, "")


class Sensors:
    """The included sensors. A sensor that fails to start is reported and left out."""

    def __init__(self, config: dict) -> None:
        cfg = config["sensors"]
        self.uv = None
        self.smoke = None
        self.loud = None
        if cfg["uv"]["sensor_included"]:
            try:
                self.uv = LTR390(i2c, cfg["uv"]["addr"])
            except OSError as ex:
                print(f"sun_sao: UV sensor not found: {ex}")
        if cfg["smoke"]["sensor_included"]:
            self.smoke = ADC(Pin(cfg["smoke"]["pin"]), atten=ADC.ATTN_11DB)
        if cfg["loud"]["sensor_included"]:
            self.loud = ADC(Pin(cfg["loud"]["pin"]), atten=ADC.ATTN_11DB)

    def read(self) -> dict:
        """One reading per included sensor: UV raw counts (None if not ready), analog ones in mV."""
        out = {}
        if self.uv is not None:
            out["uv"] = self.uv.read_uvs()
        if self.smoke is not None:
            out["smoke"] = self.smoke.read_uv() // 1000
        if self.loud is not None:
            out["loud"] = self.loud.read_uv() // 1000
        return out
