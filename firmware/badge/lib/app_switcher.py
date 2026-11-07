"""App Switcher"""

import asyncio as aio  # type: ignore
import json
import os
import sys
import btree

from apps.base_app import BaseApp
from lib.button import MenuMinus, MenuPlus, UserA, UserB, PRESSED_READ
from lib.led_bar import leds

# MENU_TIMEOUT_MILLISECONDS = 1000

# Menu order, by app name. Apps not listed here come after these, sorted by name.
APP_ORDER = [
    "Workshops",
    "Sat Talks",
    "Sun Talks",
    "Gallery",
    "Nametag",
]


APPMOD_DENYLIST = {
    "__init__",
    "base_app",
    "template",
}

LAST_APP_FILE = "/data/last_app.json"
"""Remembers the last app launched from the menu so it can be resumed at boot"""
BOOT_CONFIG_FILE = "/data/boot.json"
"""Optional. {"resume": false} always starts in the menu"""
ACTION_FEEDBACK_MS = 1200
"""How long a menu action's LED feedback shows before the menu redraws"""


class AppSwitcher:
    def __init__(self, initial_idx: int = 0) -> None:
        self.apps = []
        self.active_idx = initial_idx
        self.selecting_mode = True
        self.selection_idx = initial_idx

        # Discover and load apps
        app_mods = []
        for entry in os.ilistdir("/apps"):  # 3- or 4-tuples, depending on the filesystem
            filename = entry[0]
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            app_modname = filename.split(".")[0]
            app_mods.append(app_modname)
        if app_mods:
            print(f"Found app mods: {app_mods}")

        # Import each app module on its own, so one broken app file (syntax
        # error, bad import) is skipped instead of stopping the whole badge.
        for appmod_name in app_mods:
            if appmod_name in APPMOD_DENYLIST:
                continue
            try:
                __import__(f"apps.{appmod_name}")
                appmod = sys.modules[f"apps.{appmod_name}"]
            except Exception as exc:
                print(f"Failed to import app module: apps.{appmod_name}")
                sys.print_exception(exc)
                continue
            try:
                for modattr in appmod.__dict__.values():
                    # Subclasses of an app class count too. _abstract skips the
                    # shared base so only the concrete apps are constructed.
                    if not isinstance(modattr, type) or not issubclass(modattr, BaseApp):
                        continue
                    if modattr is BaseApp or modattr.__dict__.get("_abstract"):
                        continue
                    app = modattr()
                    self.apps.append(app)
                    app._app_module = appmod_name  # for /data/last_app.json
                    print(f"Added app: {app.name}")
            except Exception as exc:
                print(f"Failed to load app module: {appmod}")
                sys.print_exception(exc)

        # Modules and classes are found in an arbitrary order, so sort them.
        # Menu actions (e.g. the Bluetooth toggle) go after all the apps.
        def menu_position(app: BaseApp) -> tuple:
            if app.menu_action:
                return (len(APP_ORDER) + 1, app.name)
            if app.name in APP_ORDER:
                return (APP_ORDER.index(app.name), "")
            return (len(APP_ORDER), app.name)

        self.apps.sort(key=menu_position)
        print(f"Menu order: {[app.name for app in self.apps]}")

        try:
            apps_file = open("/data/app_list", "r+b")
        except OSError:
            apps_file = open("/data/app_list", "w+b")
        # Now open a database itself
        apps_db = btree.open(apps_file)
        for idx, app in enumerate(self.apps):
            apps_db[bytes([idx])] = bytes(app.name, "UTF-8")
        apps_db.flush()
        apps_db.close()
        apps_file.close()

        self._resume_last_app()

    def _resume_last_app(self) -> None:
        """Start the last app launched from the menu instead of the menu.
        Hold Menu+ or Menu- during boot to get the menu instead; it opens with
        that app selected, matching what the e-paper still shows.
        Any problem falls back to the menu."""
        last_idx = self._last_app_idx()
        if last_idx is not None:
            # Even when not resuming, open the menu on the app the e-paper
            # still shows from before the reset
            self.active_idx = last_idx
            self.selection_idx = last_idx
        if MenuPlus.pin.value() or MenuMinus.pin.value():
            print("Menu button held at boot, showing menu")
            # Don't let the held button also move the menu selection: mark it
            # held and already read, so scan() doesn't count it as a new press
            for b in (MenuMinus, MenuPlus):
                if b.pin.value():
                    b._held = True
                    b._pressed_state = PRESSED_READ
            return
        try:
            with open(BOOT_CONFIG_FILE) as f:
                boot = json.load(f)
        except OSError:
            boot = {}  # no boot config, resume is on by default
        except ValueError as exc:
            print(f"Ignoring {BOOT_CONFIG_FILE}: {exc}")
            boot = {}
        if isinstance(boot, dict) and boot.get("resume", True) is False:
            return
        if last_idx is None:
            return
        app = self.apps[last_idx]
        print(f"Resuming {app.name}")
        app.launched = True
        self.selecting_mode = False

    def _last_app_idx(self) -> int | None:
        """Menu index of the app saved in LAST_APP_FILE, or None."""
        try:
            with open(LAST_APP_FILE) as f:
                last = json.load(f)
        except OSError:
            return None  # nothing launched yet
        except ValueError as exc:
            print(f"Could not read {LAST_APP_FILE}: {exc}")
            return None
        if not isinstance(last, dict):
            print(f"Ignoring {LAST_APP_FILE}: not a JSON object")
            return None
        for idx, app in enumerate(self.apps):
            if (not app.menu_action and app._app_module == last.get("module")
                    and app.name == last.get("app")):
                return idx
        print(f"Last app {last} not found, showing menu")
        return None

    def _save_last_app(self) -> None:
        """Remember the active app. Only writes to flash when it changed."""
        app = self.apps[self.active_idx]
        last = {"module": app._app_module, "app": app.name}
        try:
            with open(LAST_APP_FILE) as f:
                if json.load(f) == last:
                    return
        except (OSError, ValueError):
            pass
        try:
            with open(LAST_APP_FILE, "w") as f:
                json.dump(last, f)
        except OSError as exc:
            print(f"Could not save {LAST_APP_FILE}: {exc}")

    async def arun(self):
        while True:
            if self.selecting_mode:
               
                ## Display current app from all installed apps
                leds.menu_display(self.selection_idx, len(self.apps))

                if MenuPlus.pressed():
                    self.selection_idx = (self.selection_idx + 1) % len(self.apps)
                    print(
                        f"Selected app {self.selection_idx}: {self.apps[self.selection_idx].name}"
                    )
                if MenuMinus.pressed():
                    self.selection_idx = (self.selection_idx - 1) % len(self.apps)
                    print(
                        f"Selected app {self.selection_idx}: {self.apps[self.selection_idx].name}"
                    )
                if UserA.pressed() or UserB.pressed():
                    picked = self.apps[self.selection_idx]
                    if picked.menu_action:
                        # Do it and stay in the menu; the current app and the
                        # screen are untouched
                        print(f"Menu action: {picked.name}")
                        try:
                            picked.action()
                        except Exception as exc:
                            print(f"{picked.name} action failed")
                            sys.print_exception(exc)
                        await aio.sleep_ms(ACTION_FEEDBACK_MS)
                        # Taps made while the feedback showed are latched;
                        # drop them so the action doesn't run again
                        UserA.pressed()
                        UserB.pressed()
                        continue
                    print(f"Switching to {picked.name}")
                    self.active_idx = self.selection_idx
                    self.apps[self.active_idx].launched = True
                    self._save_last_app()
                    leds.clear_sequence()
                    leds.fill((0, 0, 0))
                    leds.write()
                    self.selecting_mode = False
                await aio.sleep_ms(10)
            else:
                if MenuMinus.pressed() or MenuPlus.pressed():
                    self.selection_idx = self.active_idx
                    self.selecting_mode = True
                    ## Reset pressed state so that button doesn't advance menu, just enters menu state
                    MenuMinus._pressed_state = PRESSED_READ
                    MenuPlus._pressed_state = PRESSED_READ
                    print("Activated app switching")
                await self.apps[self.active_idx].arun()
                await aio.sleep_ms(0)
                self.apps[self.active_idx].launched = False


switcher = AppSwitcher()
