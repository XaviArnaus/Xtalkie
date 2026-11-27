# tools/clock_probe.py -- what can tell this board the time? Run it by hand, never at boot:
#
#     python -m mpremote connect <port> run tools/clock_probe.py       (runs from the computer, nothing is copied)
#
# It prints (1) every device on the I2C bus, (2) the ESP32's own clock, (3) the PCF85063 clock chip if there is one
# (address 0x51), twice, 2 s apart, to show that it runs. Copy the whole output.
#
# Running it stops the program of the board; a board deployed with --night restarts itself about 15 s later (the
# watchdog), which is normal.
#
# The three questions this answers on the real boards (do them in this order, the output says what to look at):
#   A. Is there a clock chip?                     -> run it once: "0x51 clock chip" in the list.
#   B. Does the time survive a restart?           -> python pc/settime.py <port>, then
#                                                    python -m mpremote connect <port> reset, wait 15 s, run this again:
#                                                    the clocks must show (set time + the minutes that passed).
#   C. Does the time survive switching it off?    -> set the time, unplug USB, hold PWR to switch the board off, wait
#                                                    two minutes, switch it on, connect USB, run this again.
#                                                    (Do it once with the battery in; the chip only keeps the time if
#                                                    its supply stays on.)
import sys

if "/lib" in sys.path:
    sys.path.remove("/lib")
sys.path.insert(0, "/lib")          # our libraries first
import time

import board

KNOWN = {0x18: "ES8311 audio codec", 0x20: "TCA9554 I/O expander", 0x34: "AXP2101 power chip", 0x38: "FT3168 touch",
         0x51: "PCF85063 clock chip", 0x6B: "QMI8658 motion sensor", 0x6A: "QMI8658 motion sensor (alt)"}
PCF = 0x51


def bcd(b):
    return (b >> 4) * 10 + (b & 0x0F)


def read_chip(i2c):
    """(raw bytes 0x00..0x0A, 'YYYY-MM-DD HH:MM:SS' or None, oscillator-stopped flag)."""
    raw = i2c.readfrom_mem(PCF, 0x00, 11)
    os_flag = bool(raw[4] & 0x80)
    try:
        text = "%04d-%02d-%02d %02d:%02d:%02d" % (2000 + bcd(raw[10]), bcd(raw[9] & 0x1F), bcd(raw[7] & 0x3F),
                                                  bcd(raw[6] & 0x3F), bcd(raw[5] & 0x7F), bcd(raw[4] & 0x7F))
    except Exception:
        text = None
    return raw, text, os_flag


def system_time():
    t = time.localtime()
    return "%04d-%02d-%02d %02d:%02d:%02d" % t[:6]


def main():
    i2c = board.i2c()
    found = i2c.scan()
    print("XT-I2C", " ".join("0x%02X" % a for a in found))
    for a in found:
        print("   0x%02X  %s" % (a, KNOWN.get(a, "unknown")))
    has_chip = PCF in found
    print("XT-CHIP", "present (0x51)" if has_chip else "NOT found")

    for i in range(2):
        print("XT-SYSTEM", system_time(), "(year %d: %s)" % (time.localtime()[0],
              "looks SET" if time.localtime()[0] >= 2024 else "NOT set (still the default)"))
        if has_chip:
            raw, text, os_flag = read_chip(i2c)
            print("XT-CHIP-TIME", text, "| oscillator-stopped flag:", "YES (time not trustworthy)" if os_flag else "no",
                  "| raw", " ".join("%02X" % b for b in raw))
        if i == 0:
            time.sleep(2)

    print("XT-DONE")
    if not has_chip:
        print("No clock chip: the time can only come from the ESP32's own clock (set by pc/settime.py, lost when the "
              "power is cut) or from the network later.")


if __name__ == "__main__":      # also true for `mpremote run`; false when a test imports the functions
    main()
