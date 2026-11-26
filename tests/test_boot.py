"""Start-up: why the board started (RTC marker + reset cause), the start-up screen, one shared panel, the child unit
staying dark after an automatic restart, the ready beep, the crash path, and the slave not waiting for WiFi."""
import builtins
import os
import sys
import tempfile
import time
import types

from common import ROOT, check, finish, patch_time

patch_time()
time.sleep = lambda s: None
sys.print_exception = lambda e, *a: print("exception:", repr(e))      # MicroPython only
import machine
from helpers import bootinfo, config

# ---------------------------------------------------------------- bootinfo: marker + reset cause
print("-- why did the board start?")


def begin(marker, cause, raw=None):
    """Pretend the previous run left `marker` (None = nothing / lost power) and the chip reports `cause`."""
    machine.CAUSE["v"] = cause
    machine.RTC.MEM["b"] = raw if raw is not None else b""
    if marker is not None:
        bootinfo.mark(marker)
    return bootinfo.begin()


P, W, S = machine.PWRON_RESET, machine.WDT_RESET, machine.SOFT_RESET
table = [
    (None, P, True, "power switched on (nothing in RTC memory, cause power-on)"),
    (None, W, False, "watchdog restart where the RTC memory was lost: dark (cause says it was not a power-on)"),
    (bootinfo.CLEAN, P, True, "after a clean stop (Thonny) and a power-on"),
    (bootinfo.RUN, P, False, "the last run never ended cleanly (reset button / brownout): dark"),
    (bootinfo.RUN, W, False, "watchdog restart: dark"),
    (bootinfo.AUTO, P, False, "our own restart after a crash: dark even if the chip says power-on"),
    (bootinfo.AUTO, S, False, "our own restart after a crash (software reset)"),
    (bootinfo.MANUAL, S, True, "restarted by deploy.py / versions.py: a person did it"),
    (bootinfo.MANUAL, W, True, "manual marker wins"),
]
for marker, cause, want, text in table:
    got = begin(marker, cause)["manual"]
    check(got == want, "%s -> %s" % (text, "lit" if want else "dark"))
r = begin(None, P, raw=b"garbage!!")
check(r["previous"] is None and r["manual"], "damaged RTC memory reads as 'nothing' (and a power-on is still manual)")
check(bootinfo.read() == bootinfo.RUN, "every start marks itself RUN")
saved = machine.reset_cause
del machine.reset_cause
check(not begin(bootinfo.CLEAN, P)["manual"], "no reset_cause() available: not sure, so not manual")
machine.reset_cause = saved
bootinfo.mark_auto()
check(bootinfo.read() == bootinfo.AUTO, "mark_auto / read")
bootinfo.mark_clean()
check(bootinfo.read() == bootinfo.CLEAN, "mark_clean / read")

from ui import boot as bootscr
check(bootscr.should_show("auto", "master", False) is False and bootscr.should_show("auto", "master", True) is True,
      "auto: the child unit shows the start-up screen only when a person started it")
check(all(bootscr.should_show("auto", r_, False) for r_ in ("slave", "play", "loopback")), "auto: the other units always show it")
check(bootscr.should_show("always", "master", False) and not bootscr.should_show("never", "slave", True), "always / never force it")

# ---------------------------------------------------------------- the Boot screen
print("-- the start-up screen")
import board
from board.display import Display
from ui import screens as S_
from ui.gfx import Gfx

shows = []
_show = Display.show
Display.show = lambda self, b: (shows.append(b), _show(self, b))[1]
inits = []
_init = Display.init
Display.init = lambda self: (inits.append(1), _init(self))[1]


class Out:
    def __enter__(self):
        self.lines, self.real = [], builtins.print
        builtins.print = lambda *a, **k: self.lines.append(" ".join(str(x) for x in a))
        return self

    def __exit__(self, *e):
        builtins.print = self.real

    def has(self, t):
        return any(t in l for l in self.lines)


cfg = config.load("/nonexistent")
with Out() as o:
    disp, gfx = bootscr.open_screen(cfg, board.i2c())
check(disp is not None and gfx is not None and o.has("screen ready"), "open_screen opens the panel")
cfg_off = config.load("/nonexistent")
cfg_off["ui"]["enabled"] = False
check(bootscr.open_screen(cfg_off, board.i2c()) == (None, None), "ui disabled: no panel opened")

shows.clear()
b = bootscr.Boot(disp, gfx, "slave", "0.3.0 abc1234", True, 60)
with Out() as o:
    b.step("CONFIG")
    b.step("AUDIO")
    b.step("NETWORK", "SEARCHING")
    b.step("READY")
check(len(shows) == 4 and shows[0] == 60 and disp.on, "four steps, four draws, the panel is lit")
check(sum(1 for l in o.lines if l.startswith("[boot] +")) == 4 and o.has("NETWORK") and o.has("SEARCHING") and o.has("ms since the last step"),
      "every step is printed with its time")
shows.clear()
disp.hide()
dark = bootscr.Boot(disp, gfx, "master", "0.3.0", False)
with Out() as o:
    dark.step("CONFIG")
    dark.step("READY")
check(not shows and not disp.on and sum(1 for l in o.lines if l.startswith("[boot] +")) == 2,
      "dark start (child unit after an automatic restart): nothing drawn, steps still printed")
shows.clear()
_draw = S_.draw_boot
S_.draw_boot = lambda *a, **k: (_ for _ in ()).throw(ValueError("boom"))
bad = bootscr.Boot(disp, gfx, "slave", "0.3.0", True)
with Out() as o:
    bad.step("CONFIG")
    bad.step("AUDIO")
S_.draw_boot = _draw
check(not bad.shown and o.has("start-up screen off") and sum(1 for l in o.lines if l.startswith("[boot] +")) == 2,
      "a drawing error switches the start-up screen off and the steps go on")


class G:
    def __init__(self): self.t = []
    def clear(self, c): pass
    def text_c(self, s, y, scale, rgb): self.t.append(s)
    def text(self, s, x, y, scale, rgb): self.t.append(s)
    def text_w(self, s, scale): return len(s) * 6 * scale
    def rect(self, *a): pass


g = G()
S_.draw_boot(g, "0.3.0 abc1234", "master", [("CONFIG", "OK"), ("AUDIO", None), ("NETWORK", "SEARCHING"), ("READY", "-")])
check(all(t in g.t for t in ("XTALKIE", "0.3.0 abc1234", "CHILD ROOM", "CONFIG", "OK", "SEARCHING")), "the start-up screen shows name, version, role and steps")

# ---------------------------------------------------------------- Hud: hold the start-up screen
print("-- the HUD keeps the start-up screen, then moves on")
import ui.hud as ui

c = config.load("/nonexistent")
for role, after in (("slave", ui.STATUS), ("master", ui.OFF)):
    d2, g2 = bootscr.open_screen(c, board.i2c())
    bootscr.Boot(d2, g2, role, "0.3.0", True).step("READY")
    h = ui.Hud(c, role, board.i2c(), (d2, g2))
    check(h.display is d2 and h.gfx is g2, "%s: the HUD uses the panel it was given" % role)
    h.hold_boot(4000)
    check(h.state == ui.BOOT, "%s: holds the start-up screen" % role)
    h.tick(time.ticks_ms() + 1000)
    check(h.state == ui.BOOT, "%s: still holding after 1 s" % role)
    h.tick(time.ticks_ms() + 5000)
    check(h.state == after, "%s: after the hold: %s" % (role, "status screen" if after == ui.STATUS else "dark"))
d2, g2 = bootscr.open_screen(c, board.i2c())
bootscr.Boot(d2, g2, "slave", "0.3.0", True).step("READY")
h = ui.Hud(c, "slave", board.i2c(), (d2, g2))
h.hold_boot(4000)
h._on_button("short", time.ticks_ms())
check(h.state == ui.STATUS, "a button press during the start-up screen shows the status screen")
h.state = ui.OFF
h.hold_boot(4000)
h.on_alert_start()
check(h.state == ui.ALARM, "an alert during the start-up screen wins")
d3, g3 = bootscr.open_screen(c, board.i2c())
h = ui.Hud(c, "master", board.i2c(), (d3, g3))
h.hold_boot(4000)
check(h.state == ui.OFF, "nothing was drawn: nothing to hold")
h = ui.Hud(c, "master", board.i2c(), (None, None))
h.hold_boot(4000)
check(h.display is None and h.state == ui.OFF, "a HUD without a screen ignores hold_boot")

# ---------------------------------------------------------------- the slave does not wait for WiFi
print("-- WiFi join does not block")
net_mod = types.ModuleType("network")


class WLAN:
    PM_NONE, PM_PERFORMANCE, PM_POWERSAVE = 0, 1, 2
    joined = False

    def __init__(self, i): self.i = i
    def active(self, on=None): pass
    def connect(self, ssid, pw): pass
    def disconnect(self): pass
    def isconnected(self): return WLAN.joined
    def ifconfig(self): return ("192.168.4.9",)
    def config(self, **k): pass


net_mod.WLAN, net_mod.AP_IF, net_mod.STA_IF, net_mod.AUTH_WPA2_PSK = WLAN, 1, 0, 3
sys.modules["network"] = net_mod
from net.link import Net

nc = config.load("/nonexistent")
nc["port"] = 47510
n = Net(nc, "slave")
t0 = time.monotonic()
with Out() as o:
    n.start(wait=False)
check(time.monotonic() - t0 < 2 and not n.joined() and o.has("searching for"), "start(wait=False) returns at once and says it is searching")
WLAN.joined = True
n._last_try = 0
with Out() as o:
    n.ensure()
check(n.joined() and o.has("joined 'xtalkie'"), "ensure() notices the join later")
n.sock.close()
nc["port"] = 47511
n2 = Net(nc, "master")
n2.start(wait=False)
check(n2.joined(), "the access point counts as joined")
n2.sock.close()

# ---------------------------------------------------------------- main.py end to end
print("-- main.py: the start of each role")
import app.master as app_master
import app.slave as app_slave
import app.play as app_play
from board.audio import Audio

beeps = []
Audio.beep = lambda self, **k: beeps.append(k)
tmp = tempfile.mkdtemp()
src = open(os.path.join(ROOT, "main.py")).read()
_ports = iter(range(47520, 47600))
captured = {}


def run_main(role, marker, cause, ui_over=None, runner=None, auto_reboot=False, wifi_joined=False):
    """Execute main.py as the board would. Returns (printed lines, captured hud / net, number of panel draws, beeps)."""
    import json
    cfgd = {"role": role, "port": next(_ports), "log": False, "auto_reboot": auto_reboot, "ui": dict(ui_over or {})}
    cfgd["ui"].setdefault("ready_s", 1)
    path = os.path.join(tmp, "c%d.json" % cfgd["port"])
    json.dump(cfgd, open(path, "w"))
    machine.CAUSE["v"] = cause
    machine.RTC.MEM["b"] = b""
    if marker is not None:
        bootinfo.mark(marker)
    WLAN.joined = wifi_joined
    captured.clear()
    shows.clear()
    beeps.clear()
    inits.clear()
    machine.RESETS.clear()

    def fake(*a, **k):
        captured["args"] = a
        captured["kw"] = k
        captured["rtc_in_run"] = bootinfo.read()
        if runner:
            runner()

    orig = (app_master.run, app_slave.run, app_play.run)
    app_master.run = app_slave.run = app_play.run = fake
    try:
        with Out() as o:
            exec(compile(src.replace("config.load()", "config.load(%r)" % path), "main.py", "exec"), {"__name__": "__main__"})
    finally:
        app_master.run, app_slave.run, app_play.run = orig
    net = captured["args"][2] if "args" in captured and len(captured["args"]) > 2 else None
    if net is not None and getattr(net, "sock", None) is not None:
        net.sock.close()
    return o.lines, captured, len(shows), len(beeps)


def hud_of(cap):
    return cap["args"][3]


lines, cap, nshow, nbeep = run_main("master", None, P)
check(nshow >= 4 and nbeep == 1 and hud_of(cap).state == ui.BOOT and hud_of(cap).display.on,
      "child unit, switched on by a person: start-up screen (%d draws), one ready beep, screen held" % nshow)
check(cap["rtc_in_run"] == bootinfo.RUN, "the run is marked RUN while it runs")
check(len(inits) == 1, "the panel is initialised once (%d time)" % len(inits))
check(sum(1 for l in lines if l.startswith("[boot] +")) == 4 and any("started by a person: yes" in l for l in lines),
      "the four steps and the decision are printed")

for text, marker, cause in (("after our own crash restart", bootinfo.AUTO, S), ("after a watchdog restart", bootinfo.RUN, W),
                            ("after a restart that lost the RTC memory", None, W)):
    lines, cap, nshow, nbeep = run_main("master", marker, cause)
    check(nshow == 0 and nbeep == 0 and hud_of(cap).state == ui.OFF and not hud_of(cap).display.on,
          "child unit %s: the room stays dark, no beep" % text)
    check(sum(1 for l in lines if l.startswith("[boot] +")) == 4 and any("started by a person: no" in l for l in lines),
          "... and the steps are still printed")
check(len(inits) == 1, "... the panel is still opened once (the HUD needs it)")

lines, cap, nshow, nbeep = run_main("slave", bootinfo.AUTO, S)
check(nshow >= 4 and nbeep == 0 and hud_of(cap).state == ui.BOOT, "parent unit after an automatic restart: screen yes, beep no")
lines, cap, nshow, nbeep = run_main("slave", None, P)
check(nshow >= 4 and nbeep == 1, "parent unit switched on by a person: screen and one beep")
check(any("searching for" in l for l in lines) and not any("not found yet" in l for l in lines)
      and any("SEARCHING" in l for l in lines if l.startswith("[boot] +")),
      "slave: WiFi join is started without waiting, the NETWORK step says SEARCHING")
lines, cap, nshow, nbeep = run_main("slave", None, P, wifi_joined=True)
check(any("NETWORK" in l and " OK" in l for l in lines if l.startswith("[boot] +")), "slave: NETWORK says OK when already joined")

lines, cap, nshow, nbeep = run_main("master", bootinfo.AUTO, S, {"boot_screen": "always"})
check(nshow >= 4 and nbeep == 0, "boot_screen always: lit even after an automatic restart, but no beep")
lines, cap, nshow, nbeep = run_main("slave", None, P, {"boot_screen": "never"})
check(nshow == 0 and nbeep == 0, "boot_screen never: no start-up screen, no beep")
lines, cap, nshow, nbeep = run_main("master", None, P, {"boot_beep": False})
check(nshow >= 4 and nbeep == 0, "boot_beep false: screen but no beep")

lines, cap, nshow, nbeep = run_main("play", None, P)
check(nshow >= 4 and nbeep == 1 and cap["kw"]["ui"].display is not None and len(inits) == 1,
      "play mode: start-up screen, beep, and the play screen shares the one panel")
lines, cap, nshow, nbeep = run_main("loopback", None, P)
check(nshow >= 4 and hud_of(cap).state == ui.BOOT and any("NETWORK" in l and " -" in l for l in lines if l.startswith("[boot] +")),
      "loopback: start-up screen, NETWORK shown as not used")

# ---------------------------------------------------------------- crash and stop paths
print("-- crash restart and clean stop")


def crash():
    raise RuntimeError("boom")


lines, cap, nshow, nbeep = run_main("master", None, P, runner=crash, auto_reboot=True)
check(bootinfo.read() == bootinfo.AUTO and len(machine.RESETS) == 1 and any("restarting in 5 s" in l for l in lines),
      "a crash with auto_reboot: marked AUTO, then the board restarts itself")
check(not begin(bootinfo.AUTO, machine.PWRON_RESET)["manual"], "... and the next start of the child unit stays dark")
lines, cap, nshow, nbeep = run_main("master", None, P, runner=crash, auto_reboot=False)
check(bootinfo.read() == bootinfo.RUN and not machine.RESETS, "a crash without auto_reboot: no restart, the marker stays RUN")


def stop():
    raise KeyboardInterrupt


lines, cap, nshow, nbeep = run_main("master", None, P, runner=stop)
check(bootinfo.read() == bootinfo.CLEAN and any(l == "stopped" for l in lines), "a stop on purpose is marked CLEAN")
check(begin(bootinfo.CLEAN, machine.PWRON_RESET)["manual"], "... so the next power-on is a normal manual start")

Display.show, Display.init = _show, _init
finish()
