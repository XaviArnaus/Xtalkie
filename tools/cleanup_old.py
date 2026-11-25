# tools/cleanup_old.py -- deletes the files of the first, flat layout that are still in / (they are not used any more).
# Run it once (Thonny) after uploading the new lib/, tools/ and main.py, then reset the board.
import os

LEGACY = ("audio.py", "board.py", "config.py", "es8311.py", "gate2.py", "gfx.py", "log.py", "master.py",
          "net.py", "power.py", "proto.py", "screen.py", "slave.py", "ui.py", "watchdog.py",
          "disk.py", "ui_demo.py", "screen_probe.py", "battery_check.py", "record_raw.py", "README.txt")
removed = []
for name in os.listdir("/"):
    if name in LEGACY:
        os.remove("/" + name)
        removed.append(name)
print("removed:", ", ".join(removed) if removed else "nothing (already clean)")
print("kept: main.py, config.json, state.json, events*.csv, lib/, tools/")
