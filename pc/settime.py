#!/usr/bin/env python3
"""Set the clock of a board from this computer's local time (no time zone, no daylight saving: what your watch says).

    python pc/settime.py /dev/cu.usbmodem2101
    python pc/settime.py /dev/cu.usbmodem2101 --dry-run     only print what would be sent

Sets the clock chip and the ESP32's own clock, and prints what the board answers. Needs the board's REPL, which STOPS a running program:
a unit deployed with --night restarts by itself about 15 s later (the watchdog); otherwise restart it
(`python -m mpremote connect <port> reset`). Close Thonny first. pc/deploy.py does this too, unless --no-clock.
Needs:  pip install mpremote
"""
import argparse
import datetime
import subprocess
import sys


def board_code(now=None):
    """The Python the board runs: set both clocks (chip + the ESP32's own), then print what it reads back.
    Falls back to the ESP32's clock alone when the board has no /lib/board/rtc.py yet."""
    n = now or datetime.datetime.now()
    t = "(%d, %d, %d, %d, %d, %d, %d)" % (n.year, n.month, n.day, n.weekday(), n.hour, n.minute, n.second)
    return ("import sys\n"
            "sys.path.insert(0, '/lib')\n"
            "import machine, time\n"
            "t = %s\n"
            "try:\n"
            "    from board import rtc\n"
            "    chip = rtc.set(t)\n"
            "except Exception:\n"
            "    machine.RTC().datetime(t + (0,))\n"
            "    chip = None\n"
            "print('XT-CHIP', {True: 'set', False: 'NOT set (no answer from the chip)', None: 'not available'}[chip])\n"
            "now = time.localtime()\n"
            "print('XT-TIME %%04d-%%02d-%%02d %%02d:%%02d:%%02d' %% now[:6])\n" % t)


def parse_answer(text):
    """('YYYY-MM-DD HH:MM:SS' the board printed or None, what it said about the chip or None)."""
    when, chip = None, None
    for line in text.splitlines():
        if line.startswith("XT-TIME "):
            when = line[len("XT-TIME "):].strip()
        elif line.startswith("XT-CHIP "):
            chip = line[len("XT-CHIP "):].strip()
    return when, chip


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="serial port of the board, e.g. /dev/cu.usbmodem2101 or COM5")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = datetime.datetime.now()
    code = board_code(now)
    cmd = [sys.executable, "-m", "mpremote", "connect", args.port, "exec", code]
    if args.dry_run:
        print("would run: mpremote connect %s exec <<EOF\n%sEOF" % (args.port, code))
        return 0
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    answer, chip = parse_answer(r.stdout)
    if r.returncode or answer is None:
        print("the board did not answer:", (r.stderr or r.stdout).strip()[-300:])
        return 1
    print("computer: %s" % now.strftime("%Y-%m-%d %H:%M:%S"))
    print("board:    %s" % answer)
    print("clock chip: %s" % chip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
