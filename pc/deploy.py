#!/usr/bin/env python3
"""Copy the project to a board (main.py, README.md, lib/, tools/) and write its /config.json.

    python deploy.py COM5 loopback
    python deploy.py COM5 master --ssid xtalkie --password MySecret123
    python deploy.py /dev/ttyACM0 slave --ssid xtalkie --password MySecret123 --night
    python deploy.py COM5 slave --clean        (also deletes the files of the old flat layout)

Close Thonny first (only one program can use the serial port). Needs:  pip install mpremote
Use --dry-run to only print what would be done.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

LEGACY = ["audio.py", "board.py", "config.py", "es8311.py", "gate2.py", "gfx.py", "log.py", "master.py",
          "net.py", "power.py", "proto.py", "screen.py", "slave.py", "ui.py", "watchdog.py", "disk.py",
          "ui_demo.py", "screen_probe.py", "battery_check.py", "record_raw.py", "README.txt"]
ROOT_FILES = ["main.py", "README.md"]
DIRS = ["lib", "tools"]


def git_stamp(src):
    """(short commit, modified?) of the project folder, or None when git is not available here.
    'Modified' means tracked files differ from the commit (untracked files are ignored)."""
    try:
        run = lambda *a: subprocess.run(["git", "-C", src] + list(a), capture_output=True, text=True, check=True).stdout
        commit = run("rev-parse", "--short", "HEAD").strip()
        dirty = bool(run("status", "--porcelain", "--untracked-files=no").strip())
        return (commit, dirty) if commit else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="serial port of the board, e.g. COM5 or /dev/ttyACM0")
    ap.add_argument("role", choices=["master", "slave", "loopback", "play", "idle"])
    ap.add_argument("--ssid")
    ap.add_argument("--password")
    ap.add_argument("--night", action="store_true",
                    help="unattended use: auto_reboot on (restart after a crash or a hang)")
    ap.add_argument("--clean", action="store_true", help="delete the old flat-layout files first")
    ap.add_argument("--no-reset", action="store_true", help="do not restart the board afterwards")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project folder

    cfg = {"role": args.role}
    wifi = {}
    if args.ssid:
        wifi["ssid"] = args.ssid
    if args.password:
        wifi["password"] = args.password
    if wifi:
        cfg["wifi"] = wifi
    if args.night:
        cfg["auto_reboot"] = True

    def mp(*a, check=True):
        cmd = [sys.executable, "-m", "mpremote", "connect", args.port] + list(a)
        print(">", " ".join(cmd[3:]))
        if not args.dry_run:
            subprocess.run(cmd, check=check)

    if args.clean:
        for name in LEGACY:
            mp("fs", "rm", ":" + name, check=False)

    for name in ROOT_FILES:
        mp("fs", "cp", os.path.join(src, name), ":" + name)
    for d in DIRS:
        for dp, dn, fn in os.walk(os.path.join(src, d)):
            dn[:] = sorted(x for x in dn if x != "__pycache__")     # pruned before the walk descends
            rel = os.path.relpath(dp, src).replace(os.sep, "/")
            mp("fs", "mkdir", ":" + rel, check=False)           # already there is fine
            for f in sorted(fn):
                if f.endswith(".pyc") or f == "_build.py":      # _build.py is written below, never taken from disk
                    continue
                mp("fs", "cp", os.path.join(dp, f), ":" + rel + "/" + f)

    # version stamp: which commit this upload came from (lib/version.py shows it on the board)
    stamp = git_stamp(src)
    if stamp:
        print("build stamp: %s%s" % (stamp[0], "+ (modified files)" if stamp[1] else ""))
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as t:
            t.write("COMMIT = %r\nDIRTY = %r\n" % stamp)
            tmp_b = t.name
        mp("fs", "cp", tmp_b, ":lib/_build.py")
        os.unlink(tmp_b)
    else:
        print("build stamp: none (no git here); an old stamp on the board is removed")
        mp("fs", "rm", ":lib/_build.py", check=False)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as t:
        json.dump(cfg, t, indent=2)
        tmp = t.name
    print("config.json =", json.dumps(cfg))
    mp("fs", "cp", tmp, ":config.json")
    os.unlink(tmp)

    if not args.no_reset:
        # tell the board a person restarts it (so the child unit shows its start-up screen); old code may lack this
        mp("exec", "import sys; sys.path.insert(0, '/lib'); from helpers import bootinfo; bootinfo.mark_manual()", check=False)
        mp("reset")
    print("done.")


if __name__ == "__main__":
    main()
