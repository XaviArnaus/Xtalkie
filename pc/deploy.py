#!/usr/bin/env python3
"""Copy the project to a board (main.py, README.md, lib/, tools/) and write its /config.json.

    python deploy.py COM5 loopback
    python deploy.py COM5 child --ssid xtalkie --password MySecret123
    python deploy.py /dev/ttyACM0 parent --ssid xtalkie --password MySecret123 --night
    python deploy.py COM5 parent --clean        (also deletes the files of the old flat layout)

Close Thonny first (only one program can use the serial port). Needs:  pip install mpremote
A board running with --night is first restarted without its watchdog (it would reset itself about 15 s into the
copy); the new config.json, written last, turns it back on when --night is given. --no-disarm skips that.
Use --dry-run to only print what would be done. The board's clock is set from this computer's time
(local time); --no-clock leaves it alone.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

from settime import board_code as clock_code

LEGACY = ["audio.py", "board.py", "config.py", "es8311.py", "gate2.py", "gfx.py", "log.py", "master.py",
          "net.py", "power.py", "proto.py", "screen.py", "slave.py", "ui.py", "watchdog.py", "disk.py",
          "ui_demo.py", "screen_probe.py", "battery_check.py", "record_raw.py", "README.txt"]
ROOT_FILES = ["main.py", "README.md"]
STALE = ["lib/app/master.py", "lib/app/slave.py"]      # renamed in 0.7.0 (child.py, parent.py): not left behind on a board
DIRS = ["lib", "tools"]

# A board deployed with --night runs a hardware watchdog (auto_reboot). mpremote stops the program, nobody feeds the
# watchdog, and about 15 s later the board resets in the middle of the copy. The watchdog cannot be switched off
# while it runs, so the first step is to start the board WITHOUT it: auto_reboot is turned off in its config.json
# and it restarts. The final config.json (written last) turns it on again when --night is given.
DISARM = ("import json, machine\n"
          "try:\n"
          "    c = json.load(open('/config.json'))\n"
          "except Exception:\n"
          "    c = None\n"
          "if isinstance(c, dict) and c.get('auto_reboot'):\n"
          "    c['auto_reboot'] = False\n"
          "    open('/config.json', 'w').write(json.dumps(c))\n"
          "    print('XT-DISARM restarting without the watchdog')\n"
          "    machine.reset()\n"
          "print('XT-DISARM not needed')\n")


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


def disarm_watchdog(port, say=print):
    """Make sure the board runs without its watchdog before anything is copied. Returns True when it is safe."""
    base = [sys.executable, "-m", "mpremote", "connect", port]
    try:
        r = subprocess.run(base + ["exec", DISARM], capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        say("the board did not answer: is Thonny closed and the cable connected?")
        return False
    out = r.stdout or ""
    if "XT-DISARM not needed" in out:
        return True
    if "XT-DISARM restarting" not in out:
        say("could not read the board's config (%s)" % (r.stderr or out).strip()[-200:])
        return False
    say("watchdog switched off in the board's config; the board restarts, waiting for it ...")
    for _ in range(30):
        time.sleep(1.5)
        try:
            r = subprocess.run(base + ["exec", "print('XT-UP')"], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            continue
        if "XT-UP" in (r.stdout or ""):
            return True
    say("the board did not come back after the restart")
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="serial port of the board, e.g. COM5 or /dev/ttyACM0")
    ap.add_argument("role", choices=["child", "parent", "loopback", "play", "idle", "master", "slave"],
                    help="master / slave are the old names of child / parent")
    ap.add_argument("--ssid")
    ap.add_argument("--password")
    ap.add_argument("--night", action="store_true",
                    help="unattended use: auto_reboot on (restart after a crash or a hang)")
    ap.add_argument("--clean", action="store_true", help="delete the old flat-layout files first")
    ap.add_argument("--no-reset", action="store_true", help="do not restart the board afterwards")
    ap.add_argument("--no-clock", action="store_true", help="do not set the board's clock from this computer")
    ap.add_argument("--clips", action="store_true",
                    help="child unit only: keep audio clips of the alerted events on the board, for analysis "
                         "(off by default: it is only for gathering data, not for normal use)")
    ap.add_argument("--no-disarm", action="store_true",
                    help="do not switch the board's watchdog off first (a board deployed with --night would reset itself "
                         "about 15 s into the copy)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project folder

    cfg = {"role": {"master": "child", "slave": "parent"}.get(args.role, args.role)}
    wifi = {}
    if args.ssid:
        wifi["ssid"] = args.ssid
    if args.password:
        wifi["password"] = args.password
    if wifi:
        cfg["wifi"] = wifi
    if args.night:
        cfg["auto_reboot"] = True
    if args.clips:
        if cfg["role"] == "child":
            cfg["nightclips"] = {"enabled": True}
        else:
            print("warning: --clips only applies to the child unit (the one that hears the room); ignored for %s" % cfg["role"])

    def mp(*a, check=True):
        cmd = [sys.executable, "-m", "mpremote", "connect", args.port] + list(a)
        print(">", " ".join(a if len(a) <= 60 else a[:57].replace("\n", " ") + "..." for a in cmd[3:]))
        if not args.dry_run:
            subprocess.run(cmd, check=check)

    if args.no_disarm:
        pass
    elif args.dry_run:
        print("> exec <switch the board's watchdog off first (a --night board resets itself 15 s into a copy)>")
    elif not disarm_watchdog(args.port):
        sys.exit("deploy stopped: the board could not be prepared (nothing was copied)")

    if args.clean:
        for name in LEGACY:
            mp("fs", "rm", ":" + name, check=False)

    for name in STALE:
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

    if not args.no_clock:
        print("setting the board's clock to this computer's time (the logs get a date and time)")
        mp("exec", clock_code(), check=False)           # needs /lib/board/rtc.py, which was copied above

    if not args.no_reset:
        # tell the board a person restarts it (so the child unit shows its start-up screen); old code may lack this
        mp("exec", "import sys; sys.path.insert(0, '/lib'); from helpers import bootinfo; bootinfo.mark_manual()", check=False)
        mp("reset")
    print("done.")


if __name__ == "__main__":
    main()
