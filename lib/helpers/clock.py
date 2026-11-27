# helpers/clock.py -- the time stamp for the log. Pure formatting: board/rtc.py makes the clocks right at boot.
import time

MIN_YEAR = 2024


def valid():
    """True when the clock has been set (it says 2000 when it was never set)."""
    return time.localtime()[0] >= MIN_YEAR


def stamp():
    """'YYYY-MM-DD HH:MM:SS' (local time), or '-' when the clock was never set."""
    t = time.localtime()
    if t[0] < MIN_YEAR:
        return "-"
    return "%04d-%02d-%02d %02d:%02d:%02d" % (t[0], t[1], t[2], t[3], t[4], t[5])
