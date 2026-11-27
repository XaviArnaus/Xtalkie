"""The tools, main.py (idle role, legacy-file warning) and the deploy script, on stub hardware."""
import builtins
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import types

from common import ROOT, check, finish, patch_time

patch_time()
time.sleep = lambda s: None
TOOLS = os.path.join(ROOT, "tools")
tmp = tempfile.mkdtemp()


def run(path, patch=lambda s: s):
    out = []
    real = builtins.print
    builtins.print = lambda *a, **k: out.append(" ".join(map(str, a)))
    try:
        exec(compile(patch(open(path).read()), os.path.basename(path), "exec"), {"__name__": "__main__"})
    finally:
        builtins.print = real
    return out


flash = os.path.join(tmp, "flash.json")
open(flash, "w").write('{"ui": {"flash_ms": 50}}')
o = run(os.path.join(TOOLS, "ui_demo.py"), lambda s: s.replace("config.load()", "config.load(%r)" % flash))
check(o[-1] == "done: the screen is dark again", "tools/ui_demo.py shows every screen (%d lines)" % len(o))
o = run(os.path.join(TOOLS, "screen_probe.py"))
check(sum(1 for l in o if l.startswith(">>>")) == 8, "tools/screen_probe.py runs its 8 stages")
o = run(os.path.join(TOOLS, "battery_check.py"))
check(len(o) == 20 and "reg00=" in o[0], "tools/battery_check.py prints 20 readings")
o = run(os.path.join(TOOLS, "disk.py"), lambda s: s.replace('walk("/")', "walk(%r)" % os.path.join(ROOT, "lib", "drivers")))
check(any("es8311.py" in l for l in o) and o[0].startswith("flash:"), "tools/disk.py lists free space and files")

# cleanup_old on a pretend board
root = os.path.join(tmp, "board")
os.makedirs(root)
for f in ("board.py", "audio.py", "slave.py", "disk.py", "README.txt", "main.py", "config.json", "state.json"):
    open(os.path.join(root, f), "w").write("x")
run(os.path.join(TOOLS, "cleanup_old.py"), lambda s: s.replace('os.listdir("/")', "os.listdir(%r)" % root).replace('os.remove("/" + name)', "os.remove(%r + '/' + name)" % root))
check(sorted(os.listdir(root)) == ["config.json", "main.py", "state.json"], "tools/cleanup_old.py removes the old flat files and keeps main.py / config.json / state.json")

# record_raw with a fake Audio
fake = types.ModuleType("board.audio")
class Audio:
    def __init__(self, **k): self.i = 0
    def start(self): pass
    def open_rx(self): pass
    def close(self): pass
    def read_frame(self):
        self.i += 1
        return struct.pack("<320h", *([self.i % 30000] * 320)), -60.0, 40
fake.Audio = Audio
real_mod = sys.modules.get("board.audio")
sys.modules["board.audio"] = fake
real_open = builtins.open
raw = os.path.join(tmp, "raw_child_snore.raw")
builtins.open = lambda p, *a, **k: real_open(raw if isinstance(p, str) and p.startswith("/raw_") else p, *a, **k)
try:
    run(os.path.join(TOOLS, "record_raw.py"), lambda s: s.replace("SECONDS = 120", "SECONDS = 2").replace("START_DELAY_S = 5", "START_DELAY_S = 1"))
finally:
    builtins.open = real_open
    if real_mod: sys.modules["board.audio"] = real_mod
    else: del sys.modules["board.audio"]
check(os.path.getsize(raw) == 100 * 640, "tools/record_raw.py writes 16-bit mono frames (%d bytes)" % os.path.getsize(raw))

# main.py: idle role, legacy warning
idle = os.path.join(tmp, "idle.json")
open(idle, "w").write('{"role": "idle"}')
src = open(os.path.join(ROOT, "main.py")).read()
o = run(os.path.join(ROOT, "main.py"), lambda s: s.replace("config.load()", "config.load(%r)" % idle))
check(any("role 'idle'" in l for l in o) and any("nothing started" in l for l in o), "main.py with role idle starts nothing")
g = {"__name__": "x"}
exec(compile(src.replace('os.listdir("/")', "os.listdir(%r)" % root).split("try:\n    main()")[0], "main", "exec"), g)
open(os.path.join(root, "net.py"), "w").write("x")
out = []
real = builtins.print
builtins.print = lambda *a, **k: out.append(" ".join(map(str, a)))
g["_warn_legacy"]()
builtins.print = real
check(any("net.py" in l for l in out), "main.py warns about old flat-layout files")
check(sys.path[0] == "/lib" or "/lib" in sys.path[:3], "/lib comes first in the module search path")

# main.py starts the play role
playcfg = os.path.join(tmp, "play.json")
open(playcfg, "w").write('{"role": "play", "ui": {"chooser_window_s": 0}}')
import app.play as _play
called = []
_real_run = _play.run
_play.run = lambda cfg, audio, **k: called.append(cfg["role"])
try:
    run(os.path.join(ROOT, "main.py"), lambda s: s.replace("config.load()", "config.load(%r)" % playcfg))
finally:
    _play.run = _real_run
check(called == ["play"], "main.py with role play starts the play mode (before the monitor's screen is set up)")

# deploy dry run
files = []
for d in ("lib", "tools"):
    for dp, dn, fn in os.walk(os.path.join(ROOT, d)):
        dn[:] = [x for x in dn if x != "__pycache__"]
        files += [f for f in fn if not f.endswith(".pyc")]
expected = len(files) + 2 + 1                       # + main.py, README.md, config.json (+ the build stamp, below)
p = subprocess.run([sys.executable, os.path.join(ROOT, "pc", "deploy.py"), "COM5", "parent", "--ssid", "x", "--password", "y" * 8,
                    "--night", "--clean", "--dry-run"], capture_output=True, text=True)
copies = p.stdout.count("fs cp")
stamped = any("fs cp" in l and l.endswith(":lib/_build.py") for l in p.stdout.splitlines())
expected += 1 if stamped else 0                     # the stamp is one more copy when git is available
check(p.returncode == 0 and copies == expected and "__pycache__" not in p.stdout,
      "pc/deploy.py plans %d file copies (expected %d), no __pycache__" % (copies, expected))
check("build stamp:" in p.stdout and (stamped or "fs rm :lib/_build.py" in p.stdout),
      "deploy.py stamps the commit on the board (or removes an old stamp when git is missing)")
p2 = subprocess.run([sys.executable, os.path.join(ROOT, "pc", "deploy.py"), "COM5", "play", "--dry-run"], capture_output=True, text=True)
check(p2.returncode == 0 and '"role": "play"' in p2.stdout, "pc/deploy.py accepts the play role")
check("switch the board's watchdog off first" in p.stdout, "deploy.py switches the watchdog off before copying (a --night board resets itself 15 s in)")
check('"auto_reboot": true' in p.stdout and "fs rm :board.py" in p.stdout, "deploy.py --night writes auto_reboot and --clean removes the old files")
shutil.rmtree(tmp, ignore_errors=True)
finish()
