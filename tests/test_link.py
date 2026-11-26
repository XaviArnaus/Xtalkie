"""Master + slave over real UDP with the HUD on both: alert, menu, live test, link loss and mute (about 30 s)."""
import time

from common import check, finish, patch_time

patch_time(real=True)
import machine
import ui.hud as ui
import board
from app import master, slave
from helpers import config, log
from net.link import Net
from sim import Capture, MasterAudio, SlaveAudio, run_pair

log.enabled = False
T0 = time.monotonic()
now = lambda: time.monotonic() - T0
# BOOT presses (0 = pressed): hold = open the menu, hold = select TEST LIVE, later a tap on the no-link screen
PRESSES = [(8.0, 9.6), (10.5, 12.0), (24.0, 24.2)]
machine.BUTTON["fn"] = lambda: 0 if any(a <= now() < b for a, b in PRESSES) else 1

NAMES = {0: "OFF", 1: "STATUS", 2: "ALARM", 3: "LINKLOST", 4: "MENU", 5: "TEST", 6: "PREVIEW"}
states = []
orig_go = ui.Hud._go
def go(self, state, nw, hold):
    if self.role == "slave":
        states.append(NAMES[state])
    return orig_go(self, state, nw, hold)
ui.Hud._go = go


def cfgfor(port):
    c = config.load("/nonexistent")
    c["port"] = port
    c["slave"]["alarm_period_ms"] = 3000
    c["slave"]["link_timeout_ms"] = 3000
    c["ui"].update(alert_hold_s=2, test_s=6, status_s=3)
    return c


mc, sc = cfgfor(47470), cfgfor(47480)
mnet, snet = Net(mc, "master"), Net(sc, "slave")
mnet.start(wifi=False)
snet.start(wifi=False)
snet.master_addr = ("127.0.0.1", 47470)
mhud, shud = ui.Hud(mc, "master", board.i2c()), ui.Hud(sc, "slave", board.i2c())
maudio, saudio = MasterAudio([(3.0, 4.0, -55.0, 45)], 20.0), SlaveAudio()

with Capture() as cap:
    run_pair(master, slave, mc, sc, maudio, saudio, mhud, shud, mnet, snet, 30)

# collapse repeats, keep the order of the screens the parent saw
seq = [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]
check(seq == ["STATUS", "ALARM", "OFF", "MENU", "TEST", "LINKLOST", "OFF"],
      "parent screens in order: %s" % seq)
check(cap.has("[slave] link up"), "the slave finds the master")
check(cap.has("OPEN (unknown)"), "the first sound opens the gate (learning)")
check(cap.has("live test for 6 s") and cap.has("playing LIVE TEST"), "TEST LIVE reaches the master and the audio comes back")
check(shud.test is not None and shud.test.get("result") is True and shud.test["pkts"] >= 280,
      "live test passes (%s packets of 300)" % (shud.test or {}).get("pkts"))
check(cap.has("[slave] LINK LOST"), "link loss detected after the master stops")
check(len(saudio.beeps) == 1 and shud.muted_until is not None, "the no-link beeps are muted by one tap (%d beep)" % len(saudio.beeps))
check(shud.peer == (76, True) and mhud.peer == (76, True), "each unit sees the other's battery %s / %s" % (shud.peer, mhud.peer))
import version
check(shud.peer_version == version.full() and mhud.peer_version == version.full(),
      "each unit learns the other's software version (%s / %s)" % (shud.peer_version, mhud.peer_version))
check(shud.version_warning() is None and mhud.version_warning() is None, "equal versions raise no warning")
finish()
