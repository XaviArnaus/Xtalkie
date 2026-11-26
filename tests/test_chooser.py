"""The boot chooser: the crash counter, holding the button at start-up, and the chooser itself."""
import json
import os
import tempfile
import time

from common import check, finish, patch_time

patch_time()
import machine
from helpers import bootinfo, config, log

log.enabled = False
tmp = tempfile.mkdtemp()

# ---------------------------------------------------------------- crash counter in the RTC marker
print("-- crashes in a row")
P = machine.PWRON_RESET


def begin(marker=None, count=0, cause=P, raw=None):
    machine.CAUSE["v"] = cause
    machine.RTC.MEM["b"] = raw if raw is not None else b""
    if marker is not None:
        bootinfo.mark(marker, count)
    return bootinfo.begin()


check(begin()["crashes"] == 0, "a power-on is not a crash")
r = begin(bootinfo.RUN, 0)
check(r["crashes"] == 1, "a run that did not end cleanly: 1 crash")
check(bootinfo.read_full() == (bootinfo.RUN, 1), "... the count is kept in the marker")
r = begin(bootinfo.RUN, 1)
check(r["crashes"] == 2, "again: 2 in a row")
r = begin(bootinfo.RUN, 2)
check(r["crashes"] == 3, "again: 3 in a row")
bootinfo.mark_auto()
check(bootinfo.read_full() == (bootinfo.AUTO, 3), "our own crash restart (AUTO) keeps the count")
check(begin(bootinfo.AUTO, 3)["crashes"] == 4, "... and it keeps counting after an automatic restart")
check(begin(bootinfo.CLEAN, 5)["crashes"] == 0, "a clean stop ends the loop")
check(begin(bootinfo.MANUAL, 5)["crashes"] == 0, "a restart by a person (deploy, role switch) ends the loop")
check(begin(raw=b"XTK1" + bytes([1, 0x5B]))["crashes"] == 0, "the old 6-byte marker format is ignored")
good = b"XTK2" + bytes([bootinfo.RUN, 2, bootinfo.RUN ^ 2 ^ 0x5A])
check(begin(raw=good)["crashes"] == 3, "a valid marker with count 2 -> 3")
check(begin(raw=good[:-1] + bytes([good[-1] ^ 1]))["crashes"] == 0, "a damaged marker counts as nothing")
check(begin(bootinfo.RUN, 400)["crashes"] == 251, "the count is capped (250 + this one)")

# how this run started, for the status screen and for the parent unit
print("-- how this run started")
cases = [
    ((None, 0, P), "STARTED BY A PERSON", 0),
    ((bootinfo.MANUAL, 0, machine.SOFT_RESET), "STARTED BY A PERSON", 0),
    ((bootinfo.AUTO, 0, machine.SOFT_RESET), "RESTART: CRASH", 2),
    ((bootinfo.AUTO, 1, machine.SOFT_RESET), "RESTART: CRASH X2", 3),
    ((bootinfo.RUN, 0, machine.WDT_RESET), "RESTART: NO CLEAN STOP", 2),
    ((bootinfo.RUN, 2, machine.WDT_RESET), "RESTART: NO CLEAN STOP X3", 4),
    ((None, 0, machine.WDT_RESET), "RESTART: OTHER", 1),
]
for (marker, count, cause), text, code in cases:
    info = begin(marker, count, cause)
    check(bootinfo.summary(info) == text and bootinfo.restart_code() == code,
          "%s / count %d / cause %d -> '%s', code %d" % (bootinfo.NAMES[marker], count, cause, bootinfo.summary(info), bootinfo.restart_code()))
begin(bootinfo.RUN, 3, machine.WDT_RESET)
for _ in range(2):
    bootinfo.stable_check(0)
bootinfo.mark_stable()
check(bootinfo.restart_code() == 5 and bootinfo.summary() == "RESTART: NO CLEAN STOP X4",
      "a stable minute resets the crash count in RTC memory, but this run still says how it started (the parent keeps showing it)")
bootinfo._info = None
check(bootinfo.restart_code() == 0 and bootinfo.summary() is None, "begin() never ran (tests, tools): code 0, no note")

# a minute of stable running ends the crash loop
begin(bootinfo.RUN, 2)
real = time.ticks_ms
t = [1000]
time.ticks_ms = lambda: t[0]
bootinfo.stable_check(t[0])
t[0] += 30000
bootinfo.stable_check(t[0])
check(bootinfo.read_full() == (bootinfo.RUN, 3), "after 30 s the crash count is still there")
t[0] += 31000
bootinfo.stable_check(t[0])
check(bootinfo.read_full() == (bootinfo.RUN, 0), "after a minute of running the crash count is back to 0")
bootinfo.mark(bootinfo.RUN, 7)
t[0] += 200000
bootinfo.stable_check(t[0])
check(bootinfo.read_full() == (bootinfo.RUN, 7), "... and it is only done once per start")
time.ticks_ms = real

# ---------------------------------------------------------------- holding the button at start-up
print("-- holding the button")
from ui import menu

clock = [0]
down = []                       # (from_ms, to_ms) intervals in which the button is pressed


class Pin:
    def value(self):
        return 0 if any(a <= clock[0] < b for a, b in down) else 1


time.ticks_ms = lambda: clock[0]
time.sleep_ms = lambda ms: clock.__setitem__(0, clock[0] + ms)


def held(intervals, window=3000, hold=2000):
    clock[0] = 0
    down[:] = intervals
    b = menu.Button()
    b.pin = Pin()
    return b.held_for(window, hold), clock[0]


check(held([])[0] is False and held([])[1] >= 3000, "never pressed: false after the 3 s window")
check(held([(500, 900)])[0] is False, "a tap is not enough")
check(held([(500, 2200)])[0] is False, "1.7 s is not enough")
ok, at = held([(500, 4000)])
check(ok and 2500 <= at <= 2600, "held from 0.5 s: true as soon as 2 s are reached (%d ms)" % at)
check(held([(2900, 6000)])[0] is True, "a press that began inside the window is followed to the end")
check(held([(3500, 7000)])[0] is False, "a press after the window is too late")
check(held([(0, 9000)])[0] is True, "held from the very start counts")
down[:] = [(0, 1500)]
clock[0] = 0
b = menu.Button()
b.pin = Pin()
b._t = 5
b.wait_release()
check(clock[0] >= 1500 and b.pin.value() == 1 and b._t is None, "wait_release waits until the button is up")
time.ticks_ms, time.sleep_ms = real, (lambda ms: None)

# ---------------------------------------------------------------- the chooser
print("-- the chooser")
import board
from ui import boot as bootscr
from ui import chooser
from ui import screens as S

cfgfile = os.path.join(tmp, "unit.json")
with open(cfgfile, "w") as f:
    json.dump({"role": "master", "wifi": {"password": "keep-me-1234"}}, f)
_save = config.save_role
config.save_role = lambda role, path=cfgfile: _save(role, path)


class Script:
    def __init__(self, evs): self.evs = list(evs)
    def read(self, now): return self.evs.pop(0) if self.evs else None
    def wait_release(self): pass


def panel():
    return bootscr.open_screen(config.load("/nonexistent"), board.i2c())


titles = []
_menu = S.draw_menu
S.draw_menu = lambda g, items, idx, title="MENU": (titles.append(title), _menu(g, items, idx, title))[1]

d, g = panel()
# list: MASTER, SLAVE, PLAY, BACK. current = master (cursor 0). tap, hold -> SLAVE asks; hold = yes
machine.RESETS.clear()
machine.RTC.MEM["b"] = b""
r = chooser.choose(d, g, 60, "master", "hold", btn=Script(["short", "long", "long"]))
data = json.load(open(cfgfile))
check(data == {"role": "slave", "wifi": {"password": "keep-me-1234"}} and len(machine.RESETS) == 1 and bootinfo.read() == bootinfo.MANUAL,
      "chooser: SLAVE + yes writes config.json (password kept), restarts, marked as started by a person")
check(titles[0] == "ROLE", "the list is titled ROLE when you asked for it")

machine.RESETS.clear()
with open(cfgfile, "w") as f:
    json.dump({"role": "slave"}, f)
r = chooser.choose(d, g, 60, "slave", "hold", btn=Script(["long"]))
check(r is True and not machine.RESETS and json.load(open(cfgfile))["role"] == "slave", "hold on the current role: carry on, nothing changes")
r = chooser.choose(d, g, 60, "slave", "hold", btn=Script(["short", "short", "long"]))
check(r is True and not machine.RESETS, "BACK: carry on, nothing changes")
r = chooser.choose(d, g, 60, "slave", "hold", btn=Script(["short", "long",       # PLAY chosen: asks
                                                           "short",              # tap = NO: back to the list
                                                           "short", "long"]))    # PLAY -> BACK, leave
check(r is True and not machine.RESETS and json.load(open(cfgfile))["role"] == "slave",
      "tap = NO at the confirmation changes nothing")
titles.clear()
chooser.choose(d, g, 60, "master", "crash", btn=Script(["long"]))
check(titles and titles[0] == "CRASHES", "after a crash loop the list says CRASHES")

real_ticks = time.ticks_ms
clk = [0]
time.ticks_ms = lambda: clk.__setitem__(0, clk[0] + 900) or clk[0]
r = chooser.choose(d, g, 60, "slave", "crash", timeout_s=120, btn=Script([]))
time.ticks_ms = real_ticks
check(r is True and not machine.RESETS, "nobody answers: after the timeout the unit starts with its current role")

config.save_role = lambda role, path=cfgfile: (False, "no space")
with open(cfgfile, "w") as f:
    json.dump({"role": "slave"}, f)
clk[0] = 0
time.ticks_ms = lambda: clk.__setitem__(0, clk[0] + 900) or clk[0]
r = chooser.choose(d, g, 60, "slave", "hold", timeout_s=30, btn=Script(["short", "long", "long"]))
time.ticks_ms = real_ticks
check(r is True and not machine.RESETS and json.load(open(cfgfile))["role"] == "slave",
      "a failed write: NOT SAVED, no restart, and the unit starts as before")
config.save_role = lambda role, path=cfgfile: _save(role, path)
check(chooser.choose(None, None, 60, "slave", "hold") is True, "no screen: nothing to choose with, carry on")
S.draw_menu = _menu
finish()
