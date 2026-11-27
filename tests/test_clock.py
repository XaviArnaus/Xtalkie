"""The clocks: PCF85063 driver on fake registers, board/rtc.py's choice at boot, the log's date and time stamp."""
import os
import tempfile
import time

from common import check, finish, patch_time

patch_time()
import machine
from drivers.pcf85063 import PCF85063
from board import rtc
from helpers import clock, log


class FakeChip:
    """An I2C bus with a PCF85063 on it (registers 0x00..0x0A), or with nothing on it."""

    def __init__(self, present=True):
        self.regs = [0] * 11
        self.regs[4] = 0x80            # a chip that was never set: oscillator-stopped flag
        self.present = present

    def readfrom_mem(self, addr, reg, n):
        if not self.present:
            raise OSError(19)
        return bytes(self.regs[reg:reg + n])

    def writeto_mem(self, addr, reg, data):
        if not self.present:
            raise OSError(19)
        for i, b in enumerate(data):
            self.regs[reg + i] = b


def set_localtime(t):
    time.localtime = lambda: t


REAL_LOCALTIME = time.localtime
NOW = (2026, 11, 27, 8, 15, 28, 4, 331)        # as time.localtime() returns it: (y, m, d, h, mi, s, weekday, yearday)

# ---- driver ----------------------------------------------------------------------------------------------------
bus = FakeChip()
chip = PCF85063(bus)
check(chip.datetime() is None, "a chip that was never set (oscillator-stopped flag) is not trusted")
chip.set((2026, 11, 27, 4, 8, 15, 28))
check(chip.datetime() == (2026, 11, 27, 4, 8, 15, 28), "set then read gives the same date and time")
check(not bus.regs[4] & 0x80, "setting the time clears the oscillator-stopped flag")
check(bus.regs[0] == 0x00 and bus.regs[4] == 0x28 and bus.regs[10] == 0x26, "24 h mode, clock running, BCD registers (seconds 0x%02X, years 0x%02X)" % (bus.regs[4], bus.regs[10]))
bus.regs[4] |= 0x80
check(chip.datetime() is None and chip.read()[0] == (2026, 11, 27, 4, 8, 15, 28), "the flag coming back (power was lost) makes the time untrusted again")
bus.regs[9] = 0x00                                              # month 0: nonsense
check(chip.read()[0] is None, "nonsense registers are rejected")

# ---- stamp -----------------------------------------------------------------------------------------------------
set_localtime((2000, 1, 1, 0, 0, 46, 5, 1))
check(clock.stamp() == "-" and not clock.valid(), "a clock that says 2000 gives '-'")
set_localtime(NOW)
check(clock.stamp() == "2026-11-27 08:15:28" and clock.valid(), "a set clock gives YYYY-MM-DD HH:MM:SS")

# ---- board/rtc.py: which clock wins at boot -----------------------------------------------------------------------
machine.RTC.DT["t"] = (2000, 1, 1, 5, 0, 0, 0, 0)
good = FakeChip()
PCF85063(good).set((2026, 11, 27, 4, 8, 15, 28))
set_localtime((2000, 1, 1, 0, 0, 46, 5, 1))                    # the ESP32 clock was lost (power cut)
check(rtc.init(good) == "chip", "chip trusted, system clock lost: the chip wins")
check(rtc.INFO == {"source": "chip", "system_was_set": False}, "init remembers that the ESP32's clock had been lost (a power cut): %s" % rtc.INFO)
check(machine.RTC().datetime()[:7] == (2026, 11, 27, 4, 8, 15, 28), "... and the ESP32's clock is set from it")

stale = FakeChip()                                              # never set: flag on
machine.RTC.DT["t"] = (2000, 1, 1, 5, 0, 0, 0, 0)
set_localtime(NOW)                                              # the ESP32 clock survived a restart
check(rtc.init(stale) == "system->chip", "chip untrusted, system clock set: the system time is written to the chip")
check(rtc.INFO == {"source": "system->chip", "system_was_set": True}, "... and that the ESP32's clock had been kept (a restart)")
check(PCF85063(stale).datetime() == (2026, 11, 27, 4, 8, 15, 28), "... and the chip is then trusted")

set_localtime((2000, 1, 1, 0, 0, 46, 5, 1))
check(rtc.init(FakeChip()) == "none", "nothing set anywhere: 'none', nothing is written")
set_localtime(NOW)
check(rtc.init(FakeChip(present=False)) == "system", "no chip answering: the system clock alone")
set_localtime((2000, 1, 1, 0, 0, 46, 5, 1))
check(rtc.init(FakeChip(present=False)) == "none", "no chip and no system time: 'none'")

target = FakeChip()
check(rtc.set((2026, 11, 27, 4, 8, 30, 0), target) is True and PCF85063(target).datetime() == (2026, 11, 27, 4, 8, 30, 0)
      and machine.RTC().datetime()[:7] == (2026, 11, 27, 4, 8, 30, 0), "rtc.set sets the chip and the ESP32 clock")
check(rtc.set((2026, 11, 27, 4, 8, 30, 0), FakeChip(present=False)) is False, "rtc.set says so when the chip did not answer")

# ---- the log line ----------------------------------------------------------------------------------------------
tmp = tempfile.mkdtemp()
log.PATH, log.OLD, log.enabled = os.path.join(tmp, "events.csv"), os.path.join(tmp, "events.old.csv"), True
log._limit, log._n, log._ok = None, 0, True
log._free = lambda: 5000000
time.ticks_ms = lambda: 12345
set_localtime(NOW)
log.write("child", "event,0.3,-59.0")
set_localtime((2000, 1, 1, 0, 0, 46, 5, 1))
log.write("boot", "role=child")
lines = open(log.PATH).read().splitlines()
check(lines[0] == "2026-11-27 08:15:28,12,child,event,0.3,-59.0", "a log line starts with the date and time, then the uptime: %s" % lines[0])
check(lines[1] == "-,12,boot,role=child", "without a set clock the date and time is '-': %s" % lines[1])
time.localtime = REAL_LOCALTIME
finish()
