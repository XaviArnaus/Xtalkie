# tools/battery_check.py -- prints what the power chip really reports, once a second for 20 s.
# Run it (Thonny) on the unit that shows a wrong battery value, once with the USB cable connected and once
# on battery only, and send me the lines. "shows" is what the screen would display: (percent, bolt).
import sys

if "/lib" in sys.path:
    sys.path.remove("/lib")
sys.path.insert(0, "/lib")          # our libraries first
import gc

gc.collect()
import time

import board
from drivers.axp2101 import AXP2101

b = AXP2101(board.i2c())
for i in range(20):
    print(b.debug())
    time.sleep(1)
