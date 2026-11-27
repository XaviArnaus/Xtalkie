"""The clock tools: pc/settime.py (what it sends to the board) and tools/clock_probe.py (decoding the clock chip)."""
import datetime
import importlib.util
import os
import subprocess
import sys

from common import check, finish

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- pc/settime.py -------------------------------------------------------------------------------------------------
st = load("pc/settime.py", "settime")
code = st.board_code(datetime.datetime(2026, 11, 27, 7, 35, 12))
check("t = (2026, 11, 27, 4, 7, 35, 12)" in code and "rtc.set(t)" in code and "machine.RTC().datetime(t + (0,))" in code,
      "settime sends the computer's local time, to the clock chip and to the ESP32's clock (which alone is the fallback)")
compile(code, "<board>", "exec")
check(True, "the code sent to the board is valid Python")
check(st.parse_answer("noise\nXT-CHIP set\nXT-TIME 2026-11-27 07:35:13\n") == ("2026-11-27 07:35:13", "set"), "the board's answer is read back")
check(st.parse_answer("Traceback ...") == (None, None), "no answer is reported as None")
p = subprocess.run([sys.executable, os.path.join(ROOT, "pc", "settime.py"), "COM5", "--dry-run"], capture_output=True, text=True)
check(p.returncode == 0 and "t = (%d," % datetime.datetime.now().year in p.stdout,
      "settime --dry-run shows what it would send and sends nothing")

# ---- tools/clock_probe.py: decoding the PCF85063 -------------------------------------------------------------------
sys.path.insert(0, os.path.join(ROOT, "tests", "stubs"))
sys.path.insert(0, os.path.join(ROOT, "lib"))
pr = load("tools/clock_probe.py", "clock_probe")


class FakeI2C:
    def __init__(self, regs):
        self.regs = regs

    def readfrom_mem(self, addr, reg, n):
        assert addr == 0x51
        return bytes(self.regs[reg:reg + n])


def bcd(n):
    return ((n // 10) << 4) | (n % 10)


regs = [0] * 11
regs[4], regs[5], regs[6], regs[7], regs[8], regs[9], regs[10] = bcd(12), bcd(35), bcd(7), bcd(27), 4, bcd(11), bcd(26)
raw, text, osf = pr.read_chip(FakeI2C(regs))
check(text == "2026-11-27 07:35:12" and not osf, "the clock chip's BCD registers decode to the right date and time")
regs[4] |= 0x80
raw, text, osf = pr.read_chip(FakeI2C(regs))
check(osf and text == "2026-11-27 07:35:12", "the oscillator-stopped flag (bit 7 of the seconds) is reported and does not disturb the time")
check(pr.bcd(0x59) == 59 and pr.bcd(0x00) == 0, "BCD helper")
finish()
