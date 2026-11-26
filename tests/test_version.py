"""Software versions: the version text, the wire format (old units must still work), the status screen, pc/versions.py."""
import importlib
import os
import sys

from common import ROOT, check, finish, patch_time

patch_time()
import version
from net import proto
from ui import screens as S
from ui import hud as ui
from ui.gfx import AMBER

# ---- version text
check(version.full() == version.VERSION and " " not in version.full(), "no build stamp: the version is just %r" % version.full())
fake = type(sys)("_build")
fake.COMMIT, fake.DIRTY = "abc1234", True
sys.modules["_build"] = fake
importlib.reload(version)
check(version.full() == version.VERSION + " abc1234+", "stamped and modified: %r" % version.full())
fake.DIRTY = False
importlib.reload(version)
check(version.full() == version.VERSION + " abc1234", "stamped, clean: %r" % version.full())
del sys.modules["_build"]
importlib.reload(version)
check(len(version.full().encode()) <= proto.VER_MAX, "the version text fits the wire format (%d <= %d bytes)" % (len(version.full()), proto.VER_MAX))

# ---- wire format
V = "0.2.0 abc1234+"
h = proto.parse(proto.pack_hello(7, 80, True, V))
check(proto.parse_hello_version(h[3]) == V and proto.parse_hello(h[3]) == (80, True), "HELLO carries the version, battery still reads")
b = proto.parse(proto.pack_hb(3, True, -60.5, 55, False, 4, V))
check(proto.parse_hb_version(b[3]) == V and proto.parse_hb(b[3]) == (True, -60.5, 55, False, 4), "HB carries the version, the old fields still read")
h0 = proto.parse(proto.pack_hello(7, 80, True))
b0 = proto.parse(proto.pack_hb(3, True, -60.5, 55, False, 4))
check(proto.parse_hello_version(h0[3]) is None and proto.parse_hb_version(b0[3]) is None,
      "an old unit (no version in HELLO / HB) reads as None")
check(len(h0[3]) == 2 and len(b0[3]) == 6, "without a version the packets are byte-identical to the old format")
# an OLD unit's parser (reads fixed leading bytes only) is not disturbed by the extra bytes
check(len(h[3]) > 2 and h[3][:2] == h0[3] and b[3][:6] == b0[3], "the version is appended, the leading bytes are unchanged")
check(proto.parse_hello_version(bytes([80, 1, 200, 65])) is None and proto.parse_hb_version(b0[3] + bytes([5, 65])) is None
      and proto.parse_hello_version(bytes([80, 1, 0])) is None, "damaged / empty version fields read as None")
long = proto.parse(proto.pack_hello(1, 1, False, "x" * 100))
check(len(proto.parse_hello_version(long[3])) == proto.VER_MAX, "a too long version is cut to %d bytes" % proto.VER_MAX)


# ---- restart code in the heartbeat
r = proto.parse(proto.pack_hb(3, True, -60.5, 55, False, 4, V, 3))
check(proto.parse_hb_restart(r[3]) == 3 and proto.parse_hb_version(r[3]) == V and proto.parse_hb(r[3]) == (True, -60.5, 55, False, 4),
      "HB carries the restart code after the version; version and old fields still read")
r = proto.parse(proto.pack_hb(3, True, -60.5, 55, False, 4, None, 2))
check(proto.parse_hb_restart(r[3]) == 2 and proto.parse_hb_version(r[3]) is None, "a restart code without a version works (empty version field)")
check(proto.parse_hb_restart(b0[3]) is None and proto.parse_hb_restart(b[3]) is None,
      "an old HB, and an HB with a version but no restart code, read as None")
check(proto.parse_hb_restart(proto.parse(proto.pack_hb(1, False, None, None, False, 0, V, 0))[3]) == 0, "0 = started by a person")
check(proto.parse_hb_restart(proto.parse(proto.pack_hb(1, False, None, None, False, 0, V, 999))[3]) == 255, "a huge code is capped at 255")
check(proto.parse_hb_restart(b0[3] + bytes([99, 1, 2])) is None, "a damaged version length gives None")


# ---- status screen
class G:
    def __init__(self): self.t = []
    def clear(self, c): pass
    def text_c(self, s, y, scale, rgb): self.t.append((s, y, rgb))
    def text(self, *a): pass
    def circle(self, *a): pass
    def check(self, *a): pass
    def cross(self, *a): pass
    def rect(self, *a): pass
    def battery(self, *a): pass


g = G()
S.draw_status(g, "PARENT UNIT", True, (80, False), (80, False), "CHILD", "", "0.2.0 abc1234", None)
check(any(t[0] == "0.2.0 abc1234" for t in g.t) and not any(t[2] == AMBER for t in g.t), "status screen: own version, no warning when equal")
g = G()
S.draw_status(g, "PARENT UNIT", True, (80, False), (80, False), "CHILD", "", "0.2.0", "0.1.0")
check(("CHILD HAS 0.1.0", 246, AMBER) in g.t, "status screen: amber warning when the other unit differs")
g = G()
S.draw_status(g, "PARENT UNIT", True, (80, False), (80, False), "CHILD", "")
check(g.t and not any(t[2] == AMBER for t in g.t), "status screen still works with the old arguments")

g = G()
S.draw_status(g, "PARENT UNIT", True, (80, False), (80, False), "CHILD", "", "0.6.0", None, 1)
check(("CHILD RESTARTED", 246, AMBER) in g.t, "status screen (parent): 'CHILD RESTARTED' when the child unit restarted by itself")
g = G()
S.draw_status(g, "PARENT UNIT", True, (80, False), (80, False), "CHILD", "", "0.6.0", "0.5.0", 4)
check(("CHILD RESTARTED X3", 246, AMBER) in g.t and ("CHILD HAS 0.5.0", 268, AMBER) in g.t,
      "... with the crash count, and the version warning on the line below")
g = G()
S.draw_status(g, "PARENT UNIT", True, (80, False), (80, False), "CHILD", "", "0.6.0", None, 0)
check(not any(t[2] == AMBER for t in g.t), "restart code 0 (started by a person): no warning")
g = G()
S.draw_status(g, "CHILD ROOM", True, (80, False), (80, False), "PARENT", "", "0.6.0", None, None, "RESTART: CRASH X2")
check(("RESTART: CRASH X2", 424, S.GRAY) in g.t, "status screen (child): how this unit started, at the bottom")
g = G()
S.draw_status(g, "PARENT UNIT", True, (80, False), (80, False), "CHILD", "HOLD BUTTON: MENU", "0.6.0", None, None, "RESTART: CRASH")
check(not any(t[0] == "RESTART: CRASH" for t in g.t) and any(t[0] == "HOLD BUTTON: MENU" for t in g.t), "... but never over the menu hint")
check(max(len(x) for x in ("RESTART: NO CLEAN STOP X250", "STARTED BY A PERSON", "RESTART: CRASH X250")) <= 28, "the start notes fit the screen")

# ---- Hud decision
import board
from helpers import config
from ui.hud import Hud

hud = Hud(config.load("/nonexistent"), "slave", board.i2c())
check(hud.version == version.full() and hud.version_warning() is None, "Hud: own version known, no warning before the other unit is heard")
hud.on_peer_version(version.full())
check(hud.version_warning() is None, "Hud: same version, no warning")
hud.on_peer_version("0.1.0")
check(hud.version_warning() == "0.1.0", "Hud: different version, warning text")
hud.on_peer_version(None)
check(hud.version_warning() is None, "Hud: an older unit that reports nothing gives no warning")
draws = []
hud._draw = lambda now: draws.append(1)
hud.state = ui.STATUS
hud.on_peer_restart(3)
hud.on_peer_restart(3)
hud.on_peer_version("9.9.9")
hud.on_peer_version("9.9.9")
check(len(draws) == 2 and hud.peer_restart == 3, "Hud: an open status screen is redrawn once when the other unit's restart code or version arrives")
hud.state = ui.OFF
hud.on_peer_restart(0)
check(len(draws) == 2, "... and not when the screen is off")

# ---- pc/versions.py
sys.path.insert(0, os.path.join(ROOT, "pc"))
import versions
check(versions.parse_devs("/dev/cu.usbmodem1101 303a:1001 x\n/dev/cu.Bluetooth-Incoming-Port 0000:0000 y\nCOM5 303a:1001 z\n\n")
      == ["/dev/cu.usbmodem1101", "COM5"], "versions.py: ports out of `mpremote devs`, Bluetooth ignored")
check(versions.parse_answer("XT-VERSION 0.2.0 abc1234\nXT-ROLE master\n") == ("0.2.0 abc1234", "master"), "versions.py: reads the board's answer")
check(versions.parse_answer("XT-VERSION unknown\nXT-ROLE ?\n") == ("unknown", "?"), "versions.py: old code is 'unknown'")
check(versions.parse_answer("Traceback ...")[0] == "unreadable", "versions.py: no answer is 'unreadable'")
finish()
