"""Button interface for the Billboard Badge"""

import machine
import asyncio as aio
import time

## Note: plus/minus mislabeled on the silkscreen!
MENU_MINUS_PIN = 40  # SW5  BUTTON_2  IO40
MENU_PLUS_PIN = 15  # SW6  BUTTON_3  IO15
USER_A_PIN = 39  # SW4  BUTTON_1  IO39
USER_B_PIN = 16  # SW7  BUTTON_4  IO16
BOOT_PIN = 0

UNPRESSED = 0
PRESSED_UNREAD = 1
PRESSED_READ = 2

# A press that is released before pressed() reads it is kept for this long.
# Without this, a quick tap during a slow app cycle (or a blocking PNG decode
# or display send) is lost. Short enough that a stale tap doesn't fire much
# later, e.g. when an app that never reads a button hands over to the menu.
LATCH_MS = 1000


class Button:
    def __init__(self, pin: int, name: str):
        self.pin = machine.Signal(machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP), invert=True)
        self.name = name
        self.value = False
        self._held = False
        self._pressed_state = UNPRESSED
        self._press_onset_ms = None
        self._release_ms = None

    def scan(self):
        self.value = self.pin.value()
        now = time.ticks_ms()
        if self.value and not self._held:  # new press
            self._held = True
            self._pressed_state = PRESSED_UNREAD
            self._press_onset_ms = now
            self._release_ms = None
        elif not self.value and self._held:  # released
            self._held = False
            self._release_ms = now
            # An unread press stays latched until read or expired
        if not self._held:
            if self._pressed_state == PRESSED_READ:
                self._pressed_state = UNPRESSED
            elif (self._pressed_state == PRESSED_UNREAD
                    and time.ticks_diff(now, self._release_ms) > LATCH_MS):
                self._pressed_state = UNPRESSED

    def pressed(self) -> bool:
        """Was a button pressed? Only returns True once for each press.
        A press released before this is called still counts, for LATCH_MS."""
        if self._pressed_state == PRESSED_UNREAD:
            self._pressed_state = PRESSED_READ
            return True
        return False

    def pressed_ms(self) -> int:
        """Milliseconds since the current press started, while the button is
        held or the press hasn't been handled yet; 0 otherwise."""
        if self._press_onset_ms is not None and (self._held or self._pressed_state != UNPRESSED):
            return time.ticks_diff(time.ticks_ms(), self._press_onset_ms)
        return 0

    def __str__(self):
        if self._pressed_state == UNPRESSED:
            pressed_state_name = "unpressed"
        elif self._pressed_state == PRESSED_UNREAD:
            pressed_state_name = "pressed-unread"
        elif self._pressed_state == PRESSED_READ:
            pressed_state_name = "pressed-read"
        else:
            pressed_state_name = ""
        return f"{self.name}:{self.value}:{pressed_state_name}"

MenuMinus = Button(MENU_MINUS_PIN, "Menu -")
MenuPlus = Button(MENU_PLUS_PIN, "Menu +")
UserA = Button(USER_A_PIN, "User A")
UserB = Button(USER_B_PIN, "User B")
Boot = Button(BOOT_PIN, "Boot")


async def scan():
    """Scan buttons and update persisted state"""
    while True:
        MenuMinus.scan()
        MenuPlus.scan()
        UserA.scan()
        UserB.scan()
        Boot.scan()
        await aio.sleep_ms(1)
