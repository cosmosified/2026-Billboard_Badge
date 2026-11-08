"""HTTP Poller App to periodically load an image from the internet.

Wi-Fi networks come from /data/wlan_credentials.json on the badge (not in the
repo), tried in order:

    [{"ssid": "MyNetwork", "key": "password"}]

The image must be a palette or grayscale PNG that lib/large_png.py can decode.
Fetching blocks the badge for up to ~5 s per network while it connects.
"""

import time

import network
import requests

from apps.base_app import BaseApp
from lib.epd import display
from lib.json_configs import load

WLAN_CREDENTIALS_FILE = "data/wlan_credentials.json"
IMAGE_URL = "https://thzinc.com/assets/2026-temporary-supercon-assets/test.png"


class HTTPPollerApp(BaseApp):
    def __init__(self) -> None:
        super().__init__("HTTP Poller App")

        # Time between updates
        self.update_interval_seconds = 300

        # Time to wait after a failed update
        self.retry_interval_seconds = 60

        # Time at (or after) which to update
        self.next_update_time = 0

        self.nic = network.WLAN(network.WLAN.IF_STA)

        # The last downloaded image, waiting to be drawn
        self.image_data: bytes | None = None

    def _connect(self) -> bool:
        try:
            credentials = load(WLAN_CREDENTIALS_FILE)
        except (OSError, ValueError) as ex:
            print(f"HTTP poller: can't read {WLAN_CREDENTIALS_FILE}: {ex}")
            return False
        self.nic.active(True)
        for credential in credentials:
            ssid = credential.get("ssid", "")
            print(f"HTTP poller: connecting to {ssid}")
            try:
                self.nic.connect(ssid, credential.get("key", ""))
            except OSError as ex:
                print(f"HTTP poller: failed connecting to {ssid}: {ex}")
                continue
            for _ in range(20):
                if self.nic.isconnected():
                    return True
                time.sleep(0.250)
        print("HTTP poller: failed to connect to any configured SSID")
        return False

    def fetch_image(self) -> bool:
        try:
            if not self._connect():
                return False
            print(f"HTTP poller: requesting {IMAGE_URL}")
            response = requests.get(IMAGE_URL)
            print(f"HTTP poller: got HTTP {response.status_code}")
            if not 200 <= response.status_code <= 299:
                return False
            self.image_data = response.content
            return True
        except OSError as ex:
            print(f"HTTP poller: request failed: {ex}")
            return False
        finally:
            self.nic.active(False)

    def run(self) -> None:
        if self.image_data is not None:
            print("HTTP poller: drawing image")
            display.clear()
            display.draw_png(self.image_data)
            display.update()
            self.image_data = None
        elif time.time() >= self.next_update_time:
            if self.fetch_image():
                self.next_update_time = time.time() + self.update_interval_seconds
            else:
                print(f"HTTP poller: update failed; retrying in {self.retry_interval_seconds} s")
                self.next_update_time = time.time() + self.retry_interval_seconds
