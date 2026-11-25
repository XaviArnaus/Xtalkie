"""An endless sound is cut after max_open_s, and the MIC level set on the slave reaches the master (about 30 s)."""
import json
import os
import tempfile
import threading
import time

from common import check, finish, patch_time

patch_time(real=True)
import ui.hud as ui
import board
from app import master, slave
from helpers import config, log
from net.link import Net
from sim import Capture, MasterAudio, SlaveAudio, run_pair

log.enabled = False
config.STATE = os.path.join(tempfile.mkdtemp(), "state.json")


def cfgfor(port):
    c = config.load("/nonexistent")
    c["port"] = port
    c["master"].update(max_open_s=3, cooldown_s=2)
    c["slave"].update(alarm_period_ms=3000, link_timeout_ms=3000)
    c["ui"].update(enabled=False)
    return c


mc, sc = cfgfor(47471), cfgfor(47481)
mnet, snet = Net(mc, "master"), Net(sc, "slave")
mnet.start(wifi=False)
snet.start(wifi=False)
snet.master_addr = ("127.0.0.1", 47471)
mhud, shud = ui.Hud(mc, "master", board.i2c()), ui.Hud(sc, "slave", board.i2c())
maudio, saudio = MasterAudio([(3.0, 11.0, -55.0, 45)], 18.0), SlaveAudio()


def step():
    time.sleep(14.0)
    print("[test] MIC step ->", shud.actions["sens_step"]())


with Capture() as cap:
    run_pair(master, slave, mc, sc, maudio, saudio, mhud, shud, mnet, snet, 20, extra=(step,))

check(cap.count("stream longer than 3 s") >= 2, "an 8 s sound is cut twice by the 3 s limit (%d cuts)" % cap.count("stream longer than 3 s"))
check(cap.count("[slave] playing") >= 2, "the stream resumes after each pause (%d playbacks)" % cap.count("[slave] playing"))
check(cap.has("[master] sensitivity level 4"), "MIC step on the slave is applied by the master (level 4)")
check(json.load(open(config.STATE)).get("sens_level") == 4, "the master remembers the level in state.json")
finish()
