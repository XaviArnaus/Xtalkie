# tools/ui_demo.py -- check the screen and the battery reading on THIS board, without any network.
# Stop the app first (config.json {"role": "idle"} and a reset is the cleanest), then Run this file.
#   1. prints the raw power-chip registers (plug / unplug the USB charger and run again to see them change)
#   2. shows every screen for a few seconds: status, alert bell, no-link, menu, live test
# Each screen prints how long it took to draw. With "ui": {"flash_ms": 700} in config.json the bell and the
# no-link screen flash. If the screen stays dark, run tools/screen_probe.py next.
import sys

if "/lib" in sys.path:
    sys.path.remove("/lib")
sys.path.insert(0, "/lib")          # our libraries first
import gc

gc.collect()                       # release anything an earlier run left on the display bus
import time

import board
from board.display import Display
from drivers.axp2101 import AXP2101
from helpers import config
from ui import screens as S
from ui.gfx import Gfx

i2c = board.i2c()
bat = AXP2101(i2c)
print("power chip:", bat.debug())

disp = Display(i2c, manual=True)           # same mode as the app
disp.init()
g = Gfx(disp.panel, board.LCD_W, board.LCD_H)
pb, pc = bat.read()[:2]


def show(name, draw, seconds=3, br=60):
    t0 = time.ticks_ms()
    draw(g)
    disp.show(br)
    print("%-22s drawn in %d ms" % (name, time.ticks_diff(time.ticks_ms(), t0)))
    time.sleep(seconds)


show("status connected", lambda g: S.draw_status(g, "PARENT UNIT", True, (pb, pc), (80, False), "CHILD", "HOLD BUTTON: MENU"))
show("status no link", lambda g: S.draw_status(g, "PARENT UNIT", False, (pb, pc), (None, False), "CHILD", "HOLD BUTTON: MENU"))
flash = config.load()["ui"]["flash_ms"]
print("flash_ms from config.json:", flash, "(0 = steady)")
if flash:
    for i in range(8):
        show("alert bell", lambda g, i=i: S.draw_alarm(g, i % 2), flash / 1000, 100)
    for i in range(8):
        show("no link", lambda g, i=i: S.draw_linklost(g, i % 2), flash / 1000, 100)
else:
    show("alert bell", lambda g: S.draw_alarm(g, 0), 4, 100)
    show("no link", lambda g: S.draw_linklost(g, 0), 4, 100)
show("menu", lambda g: S.draw_menu(g, ("TEST LIVE", "TEST ALARM", "VOLUME 4", "MIC 3", "EXIT"), 0), 3)
show("live test", lambda g: S.draw_test(g, 7, 310, -55, None), 3)
show("live test ok", lambda g: S.draw_test(g, 0, 480, -60, True), 3)
disp.hide()
print("done: the screen is dark again")
