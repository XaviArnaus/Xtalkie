#!/usr/bin/env python3
"""List the software version (and role) of every connected board.

    python pc/versions.py                      all boards that mpremote finds
    python pc/versions.py COM5 /dev/ttyACM0    only these ports
    python pc/versions.py --no-reset           leave the boards stopped at the prompt

Reads nothing but the version and the role; changes no file. Reading needs the board's REPL, which STOPS a
running program, so by default each board is restarted afterwards (a unit that runs a night test restarts
and comes back by itself). Close Thonny first. "unknown" = code from before version numbers.
Needs:  pip install mpremote
"""
import argparse
import subprocess
import sys

CODE = (
    "import sys\n"
    "sys.path.insert(0, '/lib')\n"
    "try:\n"
    "    import version\n"
    "    print('XT-VERSION', version.full())\n"
    "except Exception:\n"
    "    print('XT-VERSION unknown')\n"
    "try:\n"
    "    import json\n"
    "    print('XT-ROLE', json.load(open('/config.json')).get('role', '?'))\n"
    "except Exception:\n"
    "    print('XT-ROLE ?')\n"
)


def parse_devs(text):
    """Serial ports out of `mpremote devs` (first column), without the Bluetooth / console pseudo-ports."""
    ports = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        p = parts[0]
        if (p.startswith("/dev/") or p.upper().startswith("COM")) and "bluetooth" not in p.lower() \
                and "debug-console" not in p.lower():
            ports.append(p)
    return ports


def parse_answer(text):
    """(version, role) from the board's printed answer; ('unreadable', '?') when it did not answer."""
    ver, role = "unreadable", "?"
    for line in text.splitlines():
        if line.startswith("XT-VERSION "):
            ver = line[len("XT-VERSION "):].strip()
        elif line.startswith("XT-ROLE "):
            role = line[len("XT-ROLE "):].strip()
    return ver, role


def mpremote(*args):
    return subprocess.run([sys.executable, "-m", "mpremote"] + list(args), capture_output=True, text=True, timeout=40)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ports", nargs="*", help="serial ports (default: every board mpremote finds)")
    ap.add_argument("--no-reset", action="store_true", help="do not restart the boards afterwards")
    args = ap.parse_args()

    ports = args.ports
    if not ports:
        ports = parse_devs(mpremote("devs").stdout)
    if not ports:
        print("no board found (is Thonny closed? is the USB cable a data cable?)")
        return 1
    print("%-28s %-26s %s" % ("PORT", "VERSION", "ROLE"))
    for port in ports:
        try:
            r = mpremote("connect", port, "exec", CODE)
            ver, role = parse_answer(r.stdout)
            if not args.no_reset:
                mpremote("connect", port, "reset")
        except Exception as e:
            ver, role = "unreadable (%s)" % type(e).__name__, "?"
        print("%-28s %-26s %s" % (port, ver, role))
    return 0


if __name__ == "__main__":
    sys.exit(main())
