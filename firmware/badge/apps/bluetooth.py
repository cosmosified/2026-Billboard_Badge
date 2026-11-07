"""Bluetooth presence on/off, as a menu action.

The last entry in the menu. Picking it with User A or B toggles the BLE
presence broadcast (lib/presence.py) and saves the choice in /data/owner.json,
without leaving the menu or redrawing the screen. The LEDs show the new state
for about a second: all blue = broadcasting, one dim red = off.
"""

from apps.base_app import BaseApp
from lib.led_bar import NUM_LEDS, leds

ON_COLOR = (0, 0, 30)
OFF_COLOR = (8, 0, 0)


class BluetoothToggle(BaseApp):
    menu_action = True

    def __init__(self, name: str | None = None) -> None:
        super().__init__("Bluetooth")

    def action(self):
        from lib import presence
        on = not presence.enabled()
        saved = presence.set_broadcast(on)
        print("Bluetooth presence", "on" if on else "off", "" if saved else "(not saved)")
        if on:
            leds.fill(ON_COLOR)
        else:
            leds.fill((0, 0, 0))
            leds[NUM_LEDS // 2] = OFF_COLOR
            leds.write()
