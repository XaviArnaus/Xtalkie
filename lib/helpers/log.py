# helpers/log.py -- small rotating log on the board's flash, so a night can be reviewed afterwards.
# One CSV-ish line per entry: date and time (local, '-' if the clock was never set), uptime seconds, source, text.
# Lines written before 0.8.0 have no date and time (their first field is the uptime).
# Disk safety: the log can never use more than 1/6 of the free flash (and never more than MAX bytes per
# file; events.old.csv keeps the previous file), and it stops writing if less than 150 KB is free.
import os
import time

from helpers import clock

PATH = "/events.csv"
OLD = "/events.old.csv"
MAX = 150000
MIN_FREE = 150000
enabled = True

_limit = None
_n = 0
_ok = True


def _free():
    st = os.statvfs("/")
    return st[0] * st[3]


def write(source, text):
    global _limit, _n, _ok
    if not enabled:
        return
    try:
        if _limit is None or _n % 50 == 0:
            free = _free()
            _limit = max(20000, min(MAX, free // 6))
            _ok = free > MIN_FREE
        _n += 1
        if not _ok:
            return
        try:
            if os.stat(PATH)[6] > _limit:
                try:
                    os.remove(OLD)
                except OSError:
                    pass
                os.rename(PATH, OLD)
        except OSError:
            pass
        with open(PATH, "a") as f:
            f.write("%s,%d,%s,%s\n" % (clock.stamp(), time.ticks_ms() // 1000, source, text))
    except Exception:
        pass                      # logging must never stop the monitor
