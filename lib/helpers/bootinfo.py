# helpers/bootinfo.py -- why did this board start? A person switching it on, or the board restarting itself?
#
# The child unit must never light the room at 3 a.m. because it restarted after a crash. Two signals are used,
# and the screen is lit only when BOTH say "a person did this":
#   1. A marker kept in RTC memory (survives resets, lost when power is lost). We write it ourselves:
#        RUN     written at every start; still there at the next start = the last run did not end cleanly
#                (crash, watchdog, reset button)
#        AUTO    written just before our own restart after a crash
#        CLEAN   written when the program was stopped on purpose (Thonny stop, KeyboardInterrupt)
#        MANUAL  written by pc/deploy.py and pc/versions.py just before they restart a board
#   2. machine.reset_cause(): a plain power-on is PWRON_RESET; a watchdog or software restart is not.
# Not verified on the boards yet (what each reset really reports): begin() returns both raw values and main.py
# prints and logs them, and config "ui": {"boot_screen": "always" | "never"} overrides the decision.
MAGIC = b"XTK1"
RUN, AUTO, CLEAN, MANUAL = 1, 2, 3, 4
NAMES = {None: "none", RUN: "run (no clean end)", AUTO: "auto restart", CLEAN: "clean stop", MANUAL: "manual"}


def _rtc():
    import machine
    return machine.RTC()


def read():
    """The marker left by the previous run (RUN / AUTO / CLEAN / MANUAL), or None (none, damaged, or power was lost)."""
    try:
        m = bytes(_rtc().memory())
    except Exception:
        return None
    if len(m) == 6 and m[:4] == MAGIC and m[5] == (m[4] ^ 0x5A) and m[4] in NAMES:
        return m[4]
    return None


def mark(state):
    try:
        _rtc().memory(MAGIC + bytes([state, state ^ 0x5A]))
    except Exception:
        pass                      # no RTC memory: the reset cause alone decides


def mark_auto():
    mark(AUTO)


def mark_clean():
    mark(CLEAN)


def mark_manual():
    mark(MANUAL)


def reset_cause():
    try:
        import machine
        return machine.reset_cause()
    except Exception:
        return None


def begin():
    """Call once, first thing at start. Returns {"previous": marker, "cause": raw reset cause, "manual": bool}
    and marks this run as RUN. manual = a person started it (see the rules above)."""
    prev = read()
    cause = reset_cause()
    try:
        import machine
        power = machine.PWRON_RESET
    except Exception:
        power = None
    manual = prev == MANUAL or (prev in (None, CLEAN) and cause is not None and cause == power)
    mark(RUN)
    return {"previous": prev, "cause": cause, "manual": manual}
