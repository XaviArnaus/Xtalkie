# board/rtc.py -- the board's clocks: the ESP32's own clock (survives a restart, lost when the power is cut) and the
# PCF85063 chip (keeps counting while the board is off). At boot init() makes them agree; set() sets both.
# The time is the local time as the person set it (pc/deploy.py, pc/settime.py): no time zone, no daylight saving.
import time

import board
from drivers.pcf85063 import PCF85063

MIN_YEAR = 2024            # a clock that still says 2000 was never set
INFO = {"source": "?", "system_was_set": None}     # what init() found, for the boot line (serial and events.csv)


def _system_valid():
    return time.localtime()[0] >= MIN_YEAR


def _system_tuple():
    t = time.localtime()
    return (t[0], t[1], t[2], t[6], t[3], t[4], t[5])


def _set_system(t):
    from machine import RTC
    RTC().datetime((t[0], t[1], t[2], t[3], t[4], t[5], t[6], 0))


def _chip(i2c):
    return PCF85063(i2c if i2c is not None else board.i2c())


def init(i2c=None):
    """Make the two clocks agree. The chip wins when it can be trusted. Returns where the time came from:
    "chip" (chip -> system clock), "system" (no chip, or it could not be written: the system clock was already
    set), "system->chip" (the chip was untrusted, so the surviving system clock set it) or "none" (not set anywhere)."""
    INFO["system_was_set"] = _system_valid()           # False after a power cut (the ESP32's clock starts at 2000)
    INFO["source"] = _decide(i2c)
    return INFO["source"]


def _decide(i2c):
    chip = None
    try:
        chip = _chip(i2c)
        t = chip.datetime()
    except Exception:
        chip, t = None, None                            # no chip answering: the system clock alone
    if t is not None and t[0] >= MIN_YEAR:
        _set_system(t)
        return "chip"
    if _system_valid():
        if chip is not None:
            try:
                chip.set(_system_tuple())
                return "system->chip"
            except Exception:
                pass
        return "system"
    return "none"


def set(t, i2c=None):
    """Set both clocks to t = (year, month, day, weekday, hour, minute, second). Returns True if the chip took it."""
    _set_system(t)
    try:
        _chip(i2c).set(t)
        return True
    except Exception:
        return False
