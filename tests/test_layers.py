"""Imports, the layering rule, and the chip drivers against fake registers."""
import importlib
import os
import re

from common import ROOT, check, finish, patch_time

patch_time()
MODULES = ["version", "helpers.bootinfo", "ui.boot", "ui.menu", "ui.chooser", "dsp.clipper", "dsp.effects", "helpers.clips", "ui.playui", "app.play", "drivers.es8311", "drivers.axp2101", "drivers.tca9554", "drivers.sh8601",
           "board", "board.audio", "board.display", "helpers.config", "helpers.log", "helpers.watchdog",
           "net.proto", "net.link", "dsp.gate", "ui.gfx", "ui.screens", "ui.hud", "app.child", "app.parent"]
for m in MODULES:
    importlib.import_module(m)
check(True, "all %d library modules import" % len(MODULES))

# each layer may only use layers below it
LAYER = {"drivers": 0, "board": 1, "helpers": 1, "net": 1, "dsp": 1, "ui": 2, "app": 3}
bad = []
for dp, _, files in os.walk(os.path.join(ROOT, "lib")):
    for f in files:
        if not f.endswith(".py"):
            continue
        pkg = os.path.relpath(dp, os.path.join(ROOT, "lib")).split(os.sep)[0]
        src = open(os.path.join(dp, f)).read()
        for imp in re.findall(r"^\s*(?:from|import)\s+(drivers|board|helpers|net|dsp|ui|app)\b", src, re.M):
            if imp != pkg and LAYER[imp] > LAYER[pkg]:
                bad.append("%s/%s imports %s" % (pkg, f, imp))
check(not bad, "layering rule holds %s" % (bad or ""))
check(not any(re.search(r"^\s*(from|import)\s+(board|ui|app|net|helpers|dsp)\b", open(os.path.join(ROOT, "lib/drivers", f)).read(), re.M)
              for f in os.listdir(os.path.join(ROOT, "lib/drivers")) if f.endswith(".py")),
      "drivers/ import nothing of ours")

from drivers.axp2101 import AXP2101, estimate_percent
from drivers.tca9554 import TCA9554


class Chip:
    def __init__(self, regs): self.r = dict(regs)
    def readfrom_mem(self, a, reg, n): return bytes([self.r.get(reg, 0)])
    def writeto_mem(self, a, reg, d): self.r[reg] = d[0]


c = Chip({0: 0xF0, 1: 0xFF, 3: 0xFF})
e = TCA9554(c)
e.set(1, 0)
e.set(2, 1)
check(c.r[1] == 0xFD and c.r[3] == 0xF9, "TCA9554: sets one pin, makes it an output, leaves the others (out=%02x cfg=%02x)" % (c.r[1], c.r[3]))
check(e.get(5) is True, "TCA9554: reads an input pin")


def axp(st1, st2, gauge, mv):
    return AXP2101(Chip({0: st1, 1: st2, 0xA4: gauge, 0x30: 0, 0x34: (mv >> 8) & 0x3F, 0x35: mv & 0xFF})).read()[:2]


check(axp(0x28, 0x14, 100, 4180) == (100, True), "AXP2101: full on USB -> 100% with the bolt")
check(axp(0x28, 0x14, 0, 4100) == (92, True), "AXP2101: gauge not ready, not charging -> estimated from the voltage")
check(axp(0x28, 0x30, 0, 3900) == (0, True), "AXP2101: charging with gauge 0 -> no flattering estimate")
check(axp(0x20, 0x00, 0, 0) == (None, True), "AXP2101: no battery, USB -> None + bolt")
check(axp(0x08, 0x40, 55, 3850) == (55, False), "AXP2101: on battery -> the gauge value")
check(estimate_percent(3300) == 0 and estimate_percent(4200) == 100, "AXP2101: voltage curve end points")
finish()
