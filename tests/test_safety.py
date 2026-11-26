"""An endless sound is cut after max_open_s, and the MIC level set on the parent reaches the child (about 30 s)."""
import json
import os
import tempfile
import threading
import time

from common import check, finish, patch_time

patch_time(real=True)
import ui.hud as ui
import board
from app import child, parent
from helpers import config, log
from net.link import Net
from sim import Capture, ChildAudio, ParentAudio, run_pair

log.enabled = False
config.STATE = os.path.join(tempfile.mkdtemp(), "state.json")


def cfgfor(port):
    c = config.load("/nonexistent")
    c["port"] = port
    c["child"].update(max_open_s=3, cooldown_s=2)
    c["parent"].update(alarm_period_ms=3000, link_timeout_ms=3000)
    c["ui"].update(enabled=False)
    return c


mc, sc = cfgfor(47471), cfgfor(47481)
mnet, snet = Net(mc, "child"), Net(sc, "parent")
mnet.start(wifi=False)
snet.start(wifi=False)
snet.child_addr = ("127.0.0.1", 47471)
mhud, shud = ui.Hud(mc, "child", board.i2c()), ui.Hud(sc, "parent", board.i2c())
maudio, saudio = ChildAudio([(3.0, 11.0, -55.0, 45)], 18.0), ParentAudio()


def step():
    time.sleep(14.0)
    print("[test] MIC step ->", shud.actions["sens_step"]())


with Capture() as cap:
    run_pair(child, parent, mc, sc, maudio, saudio, mhud, shud, mnet, snet, 20, extra=(step,))

check(cap.count("stream longer than 3 s") >= 2, "an 8 s sound is cut twice by the 3 s limit (%d cuts)" % cap.count("stream longer than 3 s"))
check(cap.count("[parent] playing") >= 2, "the stream resumes after each pause (%d playbacks)" % cap.count("[parent] playing"))
check(cap.has("[child] sensitivity level 4"), "MIC step on the parent is applied by the child (level 4)")
check(json.load(open(config.STATE)).get("sens_level") == 4, "the child remembers the level in state.json")
finish()
