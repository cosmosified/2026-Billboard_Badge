"""Sun SAO probe: config handling plus live readings (run on the badge from firmware/):
    uv run mpremote run scripts/sun_probe.py
then `uv run mpremote reset` so main.py runs again.

Prints CHECK lines (PASS/FAIL) for the sensor_included settings, then 10 live
readings of the included sensors. Uses a scratch config file that it deletes.
"""

import json
import os
import time

from lib.sao import i2c
from lib.sun_sao import Sensors, load_config
from lib.ltr390 import LTR390

TEST_FILE = "/sun_probe_test.json"


def check(name: str, ok: bool) -> None:
    print(f"CHECK {'PASS' if ok else 'FAIL'} {name}")


def with_file(data) -> dict:
    with open(TEST_FILE, "w") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))
    try:
        return load_config(TEST_FILE)
    finally:
        os.remove(TEST_FILE)


print("I2C scan:", [hex(a) for a in i2c.scan()])

cfg = load_config("/no_such_file.json")
inc = {k: v["sensor_included"] for k, v in cfg["sensors"].items()}
check(f"defaults uv/smoke on, loud off {inc}", inc == {"uv": True, "smoke": True, "loud": False})

cfg = with_file({"sensors": {"loud": {"sensor_included": True}}})
check("file can include loud", cfg["sensors"]["loud"]["sensor_included"] is True)
check("other sensors keep defaults", cfg["sensors"]["uv"]["sensor_included"] is True)

cfg = with_file({"sensors": {"smoke": {"sensor_included": "yes"}}, "bogus": 1})
check("wrong type falls back to default", cfg["sensors"]["smoke"]["sensor_included"] is True)

cfg = with_file("{not json")
check("bad JSON gives defaults", cfg["sensors"]["loud"]["sensor_included"] is False)

sensors = Sensors(load_config())
first = sensors.read()
check(f"loud not read when excluded, keys {sorted(first)}", "loud" not in first)
check("UV sensor started", sensors.uv is not None)
check("smoke ADC started", sensors.smoke is not None)
check("loud ADC not created", sensors.loud is None)

for i in range(10):
    time.sleep(1)
    r = sensors.read()
    uv = r.get("uv")
    uvi = f"{LTR390.uvi(uv):.2f}" if uv is not None else "-"
    print(f"READ {i} uv_counts={uv} uvi={uvi} smoke_mV={r.get('smoke')}")
