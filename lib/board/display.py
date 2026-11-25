# board/display.py -- the AMOLED panel of this board: power and reset through the TCA9554 expander,
# the SH8601 panel, and "on / off" by brightness. Drawing is done by the caller (see ui/gfx.py): draw into
# `panel`, then call show(). The panel is dark (brightness 0, black picture) until show() is called.
import time

import board
from drivers.sh8601 import SH8601
from drivers.tca9554 import TCA9554


class Display:
    def __init__(self, i2c, manual=False):
        self.i2c = i2c
        self.want_manual = manual
        self.panel = None
        self.on = False
        self.width = board.LCD_W
        self.height = board.LCD_H

    def init(self):
        exp = TCA9554(self.i2c, board.EXP_ADDR)
        exp.set(board.EXIO_EN, 1)                    # panel power on
        exp.set(board.EXIO_RST, 0)                   # reset pulse
        time.sleep_ms(20)
        exp.set(board.EXIO_RST, 1)
        time.sleep_ms(100)
        self.panel = SH8601(sck=board.LCD_CLK, cs=board.LCD_CS, data=board.LCD_DATA,
                            width=board.LCD_W, height=board.LCD_H, manual=self.want_manual)
        self.panel.reset()
        self.panel.init()
        self.panel.brightness(0)
        self.panel.fill(self.panel.colorRGB(0, 0, 0))
        self.panel.refresh()
        self.on = False
        print("[display] panel initialised (manual refresh: %s)" % self.panel.manual)

    def show(self, brightness):
        """Push what was drawn to the panel, then raise the light (so no stale picture ever flashes)."""
        self.panel.refresh()
        self.panel.brightness(brightness)
        self.on = True

    def hide(self):
        """Dark again: an AMOLED pixel that is black gives no light."""
        if self.on:
            self.panel.brightness(0)
            self.on = False
