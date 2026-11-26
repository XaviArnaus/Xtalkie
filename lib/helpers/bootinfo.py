# helpers/bootinfo.py -- why did this board start? A person switching it on, or the board restarting itself?
#
# The child unit must never light the room at 3 a.m. because it restarted after a crash. Two signals are used,
# and the screen is lit only when BOTH say "a person did this":
#   1. A marker kept in RTC memory (survives resets, lost when power is lost). We write it ourselves:
#        RUN     written at every start; still there at the next start = the last run did not end cleanly
#                (crash, watchdog, reset button)
#        AUTO    written just before our own restart after a crash
#        CLEAN   written when the program was stopped on purpose (Thonny stop, KeyboardInterrupt)
#        MANUAL  written by pc/deploy.py, pc/versions.py and the role switch just before they restart a board
#      The marker also carries a count of crashes in a row. A run that lasts one minute (stable_check) resets it;
#      main.py shows the role chooser instead of starting the same role again when the count reaches the limit.
#   2. machine.reset_cause(): a plain power-on is PWRON_RESET; a watchdog or software restart is not.
# Not verified on the boards yet (what each reset really reports): begin() returns both raw values and main.py
# prints and logs them, and config "ui": {"boot_screen": "always" | "never"} overrides the decision.
import time

MAGIC = b"XTK2"
RUN, AUTO, CLEAN, MANUAL = 1, 2, 3, 4
NAMES = {None: "none", RUN: "run (no clean end)", AUTO: "auto restart", CLEAN: "clean stop", MANUAL: "manual"}

_crashes = 0                  # crashes in a row, as counted at this start
_t0 = None
_stable = False
_info = None                  # what begin() found at this start (kept for the life of this run)


def _rtc():
    import machine
    return machine.RTC()


def read_full():
    """(marker, crash count) left by the previous run, or (None, 0): none, damaged, or power was lost."""
    try:
        m = bytes(_rtc().memory())
    except Exception:
        return None, 0
    if len(m) == 7 and m[:4] == MAGIC and m[6] == (m[4] ^ m[5] ^ 0x5A) and m[4] in NAMES:
        return m[4], m[5]
    return None, 0


def read():
    return read_full()[0]


def mark(state, count=0):
    try:
        count = min(250, max(0, int(count)))
        _rtc().memory(MAGIC + bytes([state, count, state ^ count ^ 0x5A]))
    except Exception:
        pass                      # no RTC memory: the reset cause alone decides


def mark_auto():
    mark(AUTO, _crashes)


def mark_clean():
    mark(CLEAN)


def mark_manual():
    mark(MANUAL)


def mark_stable():
    """This run has lasted long enough: it is not part of a crash loop."""
    global _crashes
    _crashes = 0
    mark(RUN, 0)


def stable_check(now, after_ms=60000):
    """Call from the role's main loop (cheap). After after_ms of running, the crash count is reset to 0."""
    global _t0, _stable
    if _stable:
        return
    if _t0 is None:
        _t0 = now
    elif time.ticks_diff(now, _t0) >= after_ms:
        _stable = True
        mark_stable()


def reset_cause():
    try:
        import machine
        return machine.reset_cause()
    except Exception:
        return None


def begin():
    """Call once, first thing at start. Returns {"previous": marker, "cause": raw reset cause, "manual": bool,
    "crashes": crashes in a row including the one that just ended} and marks this run as RUN.
    manual = a person started it (see the rules above)."""
    global _crashes, _t0, _stable, _info
    prev, count = read_full()
    cause = reset_cause()
    try:
        import machine
        power = machine.PWRON_RESET
    except Exception:
        power = None
    manual = prev == MANUAL or (prev in (None, CLEAN) and cause is not None and cause == power)
    _crashes = count + 1 if prev in (RUN, AUTO) else 0
    _t0, _stable = None, False
    mark(RUN, _crashes)
    _info = {"previous": prev, "cause": cause, "manual": manual, "crashes": _crashes}
    return _info


def summary(info=None):
    """How this run started, as one short line for the status screen (at most 28 characters), or None."""
    info = info or _info
    if info is None:
        return None
    if info["manual"]:
        return "STARTED BY A PERSON"
    n = info["crashes"]
    x = (" X%d" % n) if n > 1 else ""
    if info["previous"] == AUTO:
        return "RESTART: CRASH" + x
    if info["previous"] == RUN:
        return "RESTART: NO CLEAN STOP" + x
    return "RESTART: OTHER"


def restart_code():
    """Sent to the parent unit in every heartbeat: 0 = this run was started by a person (or begin() never ran),
    1 + crashes in a row = the unit restarted by itself. It stays the same for the whole run, so the parent keeps
    telling 'child restarted' until a person restarts the child unit."""
    if _info is None or _info["manual"]:
        return 0
    return 1 + min(200, _info["crashes"])
