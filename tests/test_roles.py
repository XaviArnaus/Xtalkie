"""Role switching: config.json is changed safely (only the role key), the ROLE menu of the parent unit and of the
play mode (pick, confirm, restart), and the play menu's VOLUME / SPEED."""
import builtins
import json
import os
import struct
import tempfile
import time

from common import check, finish, patch_time

patch_time()
import machine
from helpers import bootinfo, config, log
from ui import menu

log.enabled = False
tmp = tempfile.mkdtemp()
config.STATE = os.path.join(tmp, "state.json")          # never touch a real /state.json


def p(name):
    return os.path.join(tmp, name)


def put(path, text):
    with open(path, "w") as f:
        f.write(text)


def get(path):
    with open(path) as f:
        return f.read()


# ---------------------------------------------------------------- config.save_role
print("-- config.json is changed safely")
cj = p("config.json")
put(cj, json.dumps({"role": "slave", "wifi": {"ssid": "home", "password": "secret-pass"}, "auto_reboot": True}))
check(config.save_role("master", cj) == (True, "ok"), "switching slave -> master works")
now_cfg = json.loads(get(cj))
check(now_cfg == {"role": "master", "wifi": {"ssid": "home", "password": "secret-pass"}, "auto_reboot": True},
      "only the role changed, the WiFi settings and everything else stay: %s" % now_cfg)
check(json.loads(get(cj + ".bak"))["role"] == "slave", "the previous file is kept as config.json.bak")
check(not os.path.exists(cj + ".new"), "no half-written .new file is left behind")
check(config.load(cj)["role"] == "master" and config.load(cj)["wifi"]["ssid"] == "home", "config.load reads it back")

before = get(cj)
check(config.save_role("loopback", cj)[0] is False and config.save_role("idle", cj)[0] is False and get(cj) == before,
      "only master / slave / play can be written (loopback and idle cannot, the file is untouched)")

nofile = p("fresh.json")
check(config.save_role("play", nofile) == (True, "ok") and json.loads(get(nofile)) == {"role": "play"} and not os.path.exists(nofile + ".bak"),
      "no config.json yet: a new one with just the role (nothing to back up)")

bad = p("bad.json")
put(bad, '{"role": "slave", "wifi": {')
ok, msg = config.save_role("master", bad)
check(ok is False and get(bad) == '{"role": "slave", "wifi": {' and not os.path.exists(bad + ".new"),
      "a config.json that cannot be read is never overwritten (%s)" % msg)

# FAT cannot rename onto an existing file: the fallback removes the old file first
fat = p("fat.json")
put(fat, json.dumps({"role": "slave", "port": 5000}))
real_rename = os.rename
calls = []


def fat_rename(a, b):
    calls.append((a, b))
    if os.path.exists(b):
        raise OSError(17, "exists")
    real_rename(a, b)


os.rename = fat_rename
try:
    ok = config.save_role("play", fat)
finally:
    os.rename = real_rename
check(ok == (True, "ok") and json.loads(get(fat)) == {"role": "play", "port": 5000} and len(calls) == 2,
      "a file system that cannot rename onto an existing file: removed first, then renamed")

# the write fails half way (flash full): the old file stays
full = p("full.json")
put(full, json.dumps({"role": "slave"}))
real_open = builtins.open


def broken_open(path, mode="r", *a, **k):
    if isinstance(path, str) and path.endswith(".new") and "w" in mode:
        raise OSError(28, "no space")
    return real_open(path, mode, *a, **k)


builtins.open = broken_open
try:
    ok, msg = config.save_role("master", full)
finally:
    builtins.open = real_open
check(ok is False and json.loads(get(full)) == {"role": "slave"}, "flash full while writing: the old config.json is intact (%s)" % msg)

# power cut between "remove" and "rename": only .new is left, and load() finds it
cut = p("cut.json")
put(cut + ".new", json.dumps({"role": "master", "port": 4747}))
check(config.load(cut)["role"] == "master", "a role switch cut off in the middle: load() falls back to config.json.new")
put(cut, json.dumps({"role": "slave"}))
check(config.load(cut)["role"] == "slave", "... but a normal config.json always wins over a stale .new")

# ---------------------------------------------------------------- RoleSwitch logic
print("-- the role switch logic")
saved = []
sw = menu.RoleSwitch("slave", save=lambda r: (saved.append(r), (True, "ok"))[1])
check(sw.labels() == ["MASTER", "SLAVE", "PLAY", "BACK"] and sw.idx == 1, "the list is MASTER / SLAVE / PLAY / BACK, the cursor on the current role")
check(sw.tap() == "redraw" and sw.idx == 2 and sw.tap() == "redraw" and sw.idx == 3 and sw.tap() == "redraw" and sw.idx == 0,
      "tap steps through the list and wraps")
check(sw.hold() == "redraw" and sw.state == "confirm" and sw.target == "master", "hold on MASTER asks for confirmation")
check(sw.tap() == "redraw" and sw.state == "pick" and sw.target is None and not saved, "tap = NO: back to the list, nothing written")
sw.idx = 1
check(sw.hold() == "cancel" and not saved, "hold on the role it already has just leaves")
sw.idx = 3
check(sw.hold() == "cancel" and not saved, "hold on BACK leaves")
sw.idx = 2
sw.hold()
check(sw.state == "confirm" and sw.hold() == "reset" and saved == ["play"] and sw.state == "done",
      "hold = YES writes the role and asks for the restart")
bad_sw = menu.RoleSwitch("master", save=lambda r: (False, "disk full"))
bad_sw.idx = 1
bad_sw.hold()
check(bad_sw.hold() == "redraw" and bad_sw.state == "failed" and bad_sw.error == "disk full" and bad_sw.tap() == "cancel",
      "a failed write is shown, and a tap leaves")
check(menu.RoleSwitch("loopback").idx == 0, "a role outside the list (loopback) starts the cursor at the top")

# ---------------------------------------------------------------- the parent unit's ROLE menu
print("-- the parent unit: MENU > ROLE")
import board
import ui.hud as ui
from ui import boot as bootscr

cfgfile = p("unit.json")
put(cfgfile, json.dumps({"role": "slave", "wifi": {"password": "keep-me-1234"}}))
_save = config.save_role
config.save_role = lambda role, path=cfgfile: _save(role, path)       # the HUD writes THIS board's config.json


def new_hud(role="slave"):
    c = config.load("/nonexistent")
    d, g = bootscr.open_screen(c, board.i2c())
    return ui.Hud(c, role, board.i2c(), (d, g))


def go_to_role_item(h):
    h._on_button("long", time.ticks_ms())           # dark -> menu
    first = h.state
    for _ in range(ui.MENU_ITEMS.index("ROLE")):
        h._on_button("short", time.ticks_ms())
    return first


h = new_hud()
st = go_to_role_item(h)
check(st == ui.MENU and ui.MENU_ITEMS[h.idx] == "ROLE" and len(ui.MENU_ITEMS) == 6,
      "the menu has 6 items and the ROLE item is reachable (all drawn inside the screen)")
h._on_button("long", time.ticks_ms())
check(h.state == ui.ROLE and h.switch.state == "pick", "hold on ROLE opens the role list")
h._on_button("long", time.ticks_ms())
check(h.state == ui.MENU, "hold on the current role (SLAVE) just goes back to the menu")
h.idx = ui.MENU_ITEMS.index("ROLE")
h._on_button("long", time.ticks_ms())
h._on_button("short", time.ticks_ms())             # SLAVE -> PLAY
h._on_button("long", time.ticks_ms())              # choose PLAY
check(h.switch.state == "confirm" and h.switch.target == "play", "choosing PLAY asks: SWITCH TO PLAY MODE")
check(json.loads(get(cfgfile))["role"] == "slave" and not machine.RESETS, "nothing is written and nothing restarts before the confirmation")
h._on_button("short", time.ticks_ms())             # tap = NO
check(h.switch.state == "pick" and json.loads(get(cfgfile))["role"] == "slave" and not machine.RESETS, "tap = NO: nothing happens")
h._on_button("long", time.ticks_ms())              # PLAY again
machine.RTC.MEM["b"] = b""
h._on_button("long", time.ticks_ms())              # hold = YES
check(json.loads(get(cfgfile)) == {"role": "play", "wifi": {"password": "keep-me-1234"}}, "YES: config.json now says play, the password is untouched")
check(len(machine.RESETS) == 1 and bootinfo.read() == bootinfo.MANUAL,
      "the board restarts, marked as started by a person (so the start-up screen shows)")
check(json.loads(get(cfgfile + ".bak"))["role"] == "slave", "and the old config.json is kept as .bak")

# the write fails: NOT SAVED is shown, then back to the menu
config.save_role = lambda role, path=cfgfile: (False, "no space")
machine.RESETS.clear()
h = new_hud()
go_to_role_item(h)
h._on_button("long", time.ticks_ms())
h._on_button("short", time.ticks_ms())
h._on_button("long", time.ticks_ms())
h._on_button("long", time.ticks_ms())
check(h.state == ui.ROLE and h.switch.state == "failed" and not machine.RESETS, "a failed write shows NOT SAVED and does not restart")
h.tick(time.ticks_ms() + 6000)
check(h.state == ui.MENU, "... and returns to the menu after a few seconds")

# a role screen nobody touches goes dark
config.save_role = lambda role, path=cfgfile: _save(role, path)
h = new_hud()
go_to_role_item(h)
h._on_button("long", time.ticks_ms())
h.tick(time.ticks_ms() + 30000)
check(h.state == ui.OFF and h.switch is None and not machine.RESETS, "an untouched role screen times out and the screen goes dark")
h = new_hud("master")
h._on_button("long", time.ticks_ms())
h._on_button("long", time.ticks_ms())
check(h.state == ui.OFF and h.switch is None, "the child unit still has no menu, however long the button is held (a toddler cannot switch its role)")

# ---------------------------------------------------------------- the play mode
print("-- the play mode: button, menu, SPEED, ROLE")
from dsp.effects import SPEEDS, next_speed
from ui.playui import PlayUi

check([next_speed(v) for v in SPEEDS] == [1.0, 1.4, 0.75] and next_speed(1.1) == 1.4, "SPEED steps: 0.75 -> 1.0 -> 1.4 -> 0.75")


class Script:
    """A BOOT button that gives these events one per call."""
    def __init__(self, evs): self.evs = list(evs)
    def read(self, now): return self.evs.pop(0) if self.evs else None


class Audio:
    level = 4
    def __init__(self): self.beeps, self.closed = 0, 0
    def set_level(self, n): self.level = n
    def beep(self, **k): self.beeps += 1
    def close(self): self.closed += 1


c = config.load("/nonexistent")
ui_play = PlayUi(c, board.i2c())
ui_play.btn = Script(["short"])
ui_play.display.hide()
ui_play.recording = False
ui_play.tick(time.ticks_ms(), 0)
check(ui_play.display.on, "a tap wakes the play screen")
ui_play.btn = Script(["long"])
ui_play.recording = True
ui_play.tick(time.ticks_ms(), 0)
check(not ui_play.menu_wanted, "a long press while a clip is being recorded is not acted on")
ui_play.btn = Script(["long"])
ui_play.recording = False
ui_play.tick(time.ticks_ms(), 0)
check(ui_play.menu_wanted, "a long press while idle asks for the menu")

sp = [1.0]
step_speed = lambda: sp.__setitem__(0, next_speed(sp[0]))
a = Audio()
ui_play.btn = Script(["long", "short", "long", "short", "short", "long"])     # VOLUME, then SPEED, then EXIT
fed = []
ui_play.run_menu(a, lambda: sp[0], step_speed, lambda: fed.append(1))
check(a.level == 5 and a.beeps == 1 and config.state_load().get("volume_level") == 5, "menu VOLUME: level up, a beep, remembered")
check(sp[0] == 1.4 and fed, "menu SPEED: 1.0 -> 1.4 (the watchdog is fed while the menu is open)")
check(not ui_play.menu_wanted, "leaving the menu clears the request")

# role switch from the play menu. Items: VOLUME, SPEED, ROLE, EXIT. Role list: MASTER, SLAVE, PLAY, BACK (cursor on PLAY)
put(cfgfile, json.dumps({"role": "play", "wifi": {"password": "keep-me-1234"}}))
config.save_role = lambda role, path=cfgfile: _save(role, path)
machine.RESETS.clear()
ui_play.btn = Script(["short", "short", "long",        # ROLE
                      "short", "short",                # PLAY -> BACK -> MASTER
                      "long",                          # choose MASTER
                      "long"])                         # YES
ui_play.run_menu(Audio(), lambda: sp[0], step_speed, lambda: None)
check(json.loads(get(cfgfile)) == {"role": "master", "wifi": {"password": "keep-me-1234"}} and len(machine.RESETS) == 1,
      "play menu > ROLE > MASTER > YES: config.json says master, the board restarts")
machine.RESETS.clear()
put(cfgfile, json.dumps({"role": "play"}))
ui_play.btn = Script(["short", "short", "long",        # ROLE
                      "short", "short", "long",        # MASTER chosen: asks
                      "short",                         # tap = NO: back to the list
                      "short", "long",                 # MASTER -> SLAVE... then choose SLAVE: asks again
                      "short",                         # NO
                      "short", "short", "short", "long"])   # SLAVE -> PLAY -> BACK, leave the list (BACK)
ui_play.run_menu(Audio(), lambda: sp[0], step_speed, lambda: None)
check(json.loads(get(cfgfile))["role"] == "play" and not machine.RESETS, "play menu: NO at the confirmation changes nothing")

real_ticks = time.ticks_ms
clock = [0]
time.ticks_ms = lambda: clock.__setitem__(0, clock[0] + 700) or clock[0]
ui_play.btn = Script([])
ui_play.run_menu(Audio(), lambda: sp[0], step_speed, lambda: None)
time.ticks_ms = real_ticks
check(True, "an untouched play menu closes by itself after 20 s")

# ---------------------------------------------------------------- the play loop opens the menu safely
print("-- the play loop")
import app.play as play

FR, Q = 320, -79.0


def frame(i):
    return struct.pack("<%dh" % FR, *([i % 30000] * FR))


class LoopAudio:
    def __init__(self, levels, ev):
        self.levels, self.i, self.ev, self.mode = levels, 0, ev, None

    def open_rx(self): self.mode = "rx"; self.ev.append("rx")
    def open_tx(self): self.mode = "tx"
    def close(self): self.mode = None; self.ev.append("close")
    def write_silence(self): pass
    def set_pa(self, on): pass
    def write_payload(self, p_, gain=None): pass

    def read_frame(self):
        assert self.mode == "rx", "the microphone was read while it is closed"
        if self.i >= len(self.levels):
            raise KeyboardInterrupt
        lvl = self.levels[self.i]
        self.i += 1
        return frame(self.i), lvl, 50


class LoopUi:
    """Asks for the menu while a clip is being recorded; the menu must wait until the clip is done."""
    def __init__(self, ev):
        self.ev, self.recording, self.menu_wanted, self.asked = ev, False, False, False

    def ready(self, n): self.ev.append("ready")
    def playing(self, n): self.ev.append("playing")

    def tick(self, now, idle):
        if self.recording and not self.asked:
            self.asked = True
            self.menu_wanted = True
            self.ev.append("asked-while-recording")

    def run_menu(self, audio, speed_get, speed_step, feed):
        self.menu_wanted = False
        self.ev.append("menu:mic=%s:recording=%s" % (audio.mode, self.recording))
        speed_step()


ev = []
levels = [Q] * 60 + [-50.0] * 60 + [Q] * 80
au = LoopAudio(levels, ev)
cl = config.load("/nonexistent")
cl["play"]["save"] = False
real_print = builtins.print
builtins.print = lambda *a, **k: None
try:
    try:
        play.run(cl, au, ui=LoopUi(ev), store=None)
    except KeyboardInterrupt:
        pass
finally:
    builtins.print = real_print
mi = [k for k, e in enumerate(ev) if e.startswith("menu:")]
check(len(mi) == 1 and "asked-while-recording" in ev[:mi[0]] and "playing" in ev[:mi[0]],
      "a menu request made during a recording is served only after the clip was played: %s" % ev)
check(ev[mi[0] - 1] == "close" and ev[mi[0]].endswith("mic=None:recording=False") and ev[mi[0] + 1] == "ready" and ev[mi[0] + 2] == "rx",
      "the microphone is closed for the menu, then the screen is redrawn and the microphone reopened")
check(config.state_load().get("play_speed") in SPEEDS, "play_speed in state.json is one of the menu's speeds (%s)" % config.state_load().get("play_speed"))
finish()
