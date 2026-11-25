# tools/screen_probe.py -- finds out which way of switching the panel on works on THIS board.
# Use a clean board: config.json = {"role": "idle"}, press RESET, then Run this file in Thonny.
# WATCH THE DEVICE and write down which numbers you actually see (a colour on the screen):
#   1 RED     2 GREEN    3 BLUE    4 YELLOW    5 dim WHITE    6a (nothing should change)    6b ORANGE    7 PURPLE
# Each stage lasts 3 s. Then tell me, e.g.: "I saw 1, 2, 3, 4, 5, 6b, 7" or "I saw 1, 2, 5 only".
import sys

if "/lib" in sys.path:
    sys.path.remove("/lib")
sys.path.insert(0, "/lib")          # our libraries first
import gc

gc.collect()
import time

import board
from drivers.tca9554 import TCA9554
from machine import Pin, SPI
import amoled

i2c = board.i2c()
exp = TCA9554(i2c, board.EXP_ADDR)


def build(auto_refresh):
    exp.set(board.EXIO_EN, 1)
    exp.set(board.EXIO_RST, 0)
    time.sleep_ms(20)
    exp.set(board.EXIO_RST, 1)
    time.sleep_ms(100)
    spi = SPI(2, baudrate=80_000_000, sck=Pin(board.LCD_CLK), mosi=None, miso=None, polarity=0, phase=0)
    d = [Pin(n, Pin.OUT) for n in board.LCD_DATA]
    cs = Pin(board.LCD_CS, Pin.OUT)
    panel = amoled.QSPIPanel(spi=spi, data=tuple(d), dc=d[1], cs=cs, pclk=80_000_000,
                             width=board.LCD_W, height=board.LCD_H)
    if auto_refresh:
        return amoled.AMOLED(panel, type=2, bpp=16)
    return amoled.AMOLED(panel, type=2, bpp=16, auto_refresh=False)


def say(text, seconds=3):
    print(">>> " + text)
    time.sleep(seconds)


# ---- group A: the same way the bring-up test lit the panel (automatic refresh) ----
d = build(True)
d.reset()
d.init()
d.brightness(100)
d.fill(d.colorRGB(215, 25, 25))
say("1  RED     (colour made with colorRGB, panel on)")
d.fill(amoled.GREEN)
say("2  GREEN   (built-in colour constant)")
d.disp_off()
d.fill(d.colorRGB(0, 0, 255))
time.sleep(1)
d.disp_on()
say("3  BLUE    (drawn while the panel was OFF, then switched on)")
d.disp_off()
time.sleep(1)
d.disp_on()
d.fill(d.colorRGB(255, 220, 0))
say("4  YELLOW  (switched on first, then drawn)")
d.fill(d.colorRGB(255, 255, 255))
d.brightness(30)
say("5  dim WHITE (30 % brightness)")
d.brightness(0)
d.disp_off()
try:
    d.deinit()
except Exception as e:
    print("deinit:", e)

# ---- group B: manual refresh (what I used in the first version) ----
try:
    d2 = build(False)
    d2.reset()
    d2.init()
    d2.brightness(100)
    d2.fill(d2.colorRGB(255, 120, 0))
    say("6a  drawn but NOT refreshed yet - the screen should NOT show orange", 2)
    d2.refresh()
    say("6b  ORANGE after refresh()")
    d2.disp_off()
    d2.fill(d2.colorRGB(160, 0, 200))
    d2.refresh()
    d2.disp_on()
    say("7  PURPLE  (drawn while OFF, refreshed, then switched on)")
    d2.brightness(0)
    d2.disp_off()
except Exception as e:
    print("group B failed:", e)
print("done. Which numbers did you see?")
