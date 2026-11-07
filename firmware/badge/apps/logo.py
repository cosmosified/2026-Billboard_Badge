"""Shows the Cosmotronics CT shield logo.

The image was made from the original PNG with ImageMagick (from firmware/):
    magick "Glossy Cosmotronics CT Shield Logo.png" -background white -alpha remove \
        -alpha off -resize 960x672 -gravity center -extent 960x672 \
        -remap scripts/palette.gif -strip badge/data/graphics/cosmotronics_logo.png
"""

from apps.base_app import BaseApp
from lib.epd import display

LOGO = "/data/graphics/cosmotronics_logo.png"


class LogoApp(BaseApp):
    def __init__(self, name: str | None = None) -> None:
        self.name = "Cosmotronics"
        self.sleep_ms = 100
        self.launched = False

    def run(self):
        if self.launched:
            display.clear()
            display.draw_png(LOGO)
            display.update()
