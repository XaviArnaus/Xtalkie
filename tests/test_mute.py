"""Parent unit: BOOT on the bell screen stops the voice of that alert; 3 quick taps switch the sound off / on (about 25 s)."""
import time

from common import check, finish, patch_time

patch_time(real=True)
import machine
import ui.hud as ui
import board
from app import child, parent
from helpers import config, log
from net.link import Net
from sim import Capture, ChildAudio, ParentAudio, run_pair

log.enabled = False
T0 = [time.monotonic()]
now = lambda: time.monotonic() - T0[0]
PRESSES = []
machine.BUTTON["fn"] = lambda: 0 if any(a <= now() < b for a, b in PRESSES) else 1

NAMES = {0: "OFF", 1: "STATUS", 2: "ALARM", 3: "LINKLOST", 4: "MENU", 5: "TEST", 6: "PREVIEW", 9: "NOTE"}
states = []
orig_go = ui.Hud._go
def go(self, state, nw, hold):
    if self.role == "parent":
        states.append(NAMES.get(state, state))
    return orig_go(self, state, nw, hold)
ui.Hud._go = go


def cfgfor(port):
    c = config.load("/nonexistent")
    c["port"] = port
    c["parent"]["alarm_period_ms"] = 3000
    c["parent"]["link_timeout_ms"] = 3000
    c["ui"].update(alert_hold_s=2, status_s=3)
    return c


def run(port, events, stop_s, parent_s, presses, muted=False):
    """One child + parent run; returns (parent audio, parent hud, captured output)."""
    del states[:]
    PRESSES[:] = presses
    mc, sc = cfgfor(port), cfgfor(port + 10)
    mnet, snet = Net(mc, "child"), Net(sc, "parent")
    mnet.start(wifi=False)
    snet.start(wifi=False)
    snet.child_addr = ("127.0.0.1", port)
    mhud, shud = ui.Hud(mc, "child", board.i2c()), ui.Hud(sc, "parent", board.i2c())
    shud.sound_off = muted
    maudio, saudio = ChildAudio(events, stop_s), ParentAudio()
    T0[0] = time.monotonic()
    with Capture() as cap:
        run_pair(child, parent, mc, sc, maudio, saudio, mhud, shud, mnet, snet, parent_s)
    return saudio, shud, cap


# ---- 1. an alert of about 7 s; a tap on the bell screen after 3 s of it stops the voice -----------------------------
saudio, shud, cap = run(47570, [(2.0, 9.0, -55.0, 45)], 12.0, 14.0, [(5.0, 5.2)])
check("ALARM" in states, "the alert shows the bell (%s)" % states)
check(cap.has("alert dismissed: voice stopped") or cap.has("playing"), "the alert started playing")
check(0 < saudio.frames < 300, "the voice stopped when BOOT dismissed the bell (%d of about 350 frames played)" % saudio.frames)
check(shud.state == ui.OFF and not shud.alert_active, "the screen is dark and no alert is active afterwards")

# ---- 2. sound switched off: the bell shows, nothing is played, no beeps ---------------------------------------------
saudio, shud, cap = run(47590, [(2.0, 4.0, -55.0, 45)], 8.0, 8.0, [], muted=True)
check("ALARM" in states, "sound off: the bell still shows")
check(saudio.frames == 0, "sound off: no voice is played (%d frames)" % saudio.frames)

# ---- 3. the gesture: 3 quick taps toggle, slow taps do not; menu taps never count -----------------------------------
c = cfgfor(47610)
h = ui.Hud(c, "parent", board.i2c())
h.actions["unmute_beep"] = lambda: beeps.append(1)
beeps = []
h.sound_off = False
t = 1000
for k in range(3):
    h._on_button("short", t + k * 300)
check(h.sound_off and h.sound_muted() and h.muted(0), "3 quick taps switch the sound off")
check(h.state == ui.NOTE, "... and say so on the screen")
for k in range(3):
    h._on_button("short", t + 5000 + k * 300)
check(not h.sound_off and beeps == [1], "3 more quick taps switch it on again, with one beep")
h._on_button("short", t + 20000)
h._on_button("short", t + 21500)
h._on_button("short", t + 23000)
check(not h.sound_off, "slow taps (more than %d ms apart) do nothing" % c["ui"]["mute_gap_ms"])
h._on_button("short", t + 30000)
h._on_button("long", t + 30200)
h._on_button("short", t + 30400)
h._on_button("short", t + 30600)
check(not h.sound_off, "a hold in between breaks the sequence")
h.state = ui.MENU
for k in range(3):
    h._on_button("short", t + 40000 + k * 200)
check(not h.sound_off, "taps in the menu only move the cursor")
m = ui.Hud(cfgfor(47620), "child", board.i2c())
for k in range(3):
    m._on_button("short", t + k * 200)
check(not m.sound_off, "the child unit has no such gesture")

# the saved state is left as it was found
try:
    config.state_save("sound_off", False)
except Exception:
    pass
finish()
