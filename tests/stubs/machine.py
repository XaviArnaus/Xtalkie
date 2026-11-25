"""Host-side stand-in for MicroPython's `machine` module (tests only)."""
BUTTON = {"fn": lambda: 1}              # BOOT button: 0 = pressed
_F = {"hz": 240000000}


def freq(hz=None):
    if hz is None:
        return _F["hz"]
    _F["hz"] = hz


class Pin:
    OUT = 1
    IN = 0
    PULL_UP = 2

    def __init__(self, n=0, *a, **k):
        self.n = n
        self.v = 0

    def value(self, v=None):
        if v is not None:
            self.v = v
            return None
        return BUTTON["fn"]() if self.n == 0 else self.v


class I2C:
    # expander registers (0x20) and power chip registers (0x34), shared by all instances
    REGS = {0x01: 0xFF, 0x03: 0xFF}
    AXP = {0x00: 0x28, 0x01: 0x20, 0xA4: 76, 0x30: 0, 0x34: 0x10, 0x35: 0x30}

    def __init__(self, *a, **k):
        pass

    def readfrom_mem(self, addr, reg, n):
        return bytes([(I2C.AXP if addr == 0x34 else I2C.REGS).get(reg, 0)])

    def writeto_mem(self, addr, reg, data):
        (I2C.AXP if addr == 0x34 else I2C.REGS)[reg] = data[0]


class I2S:
    TX = 1
    RX = 0
    STEREO = 1

    def __init__(self, *a, **k):
        pass

    def deinit(self):
        pass


class SPI:
    def __init__(self, *a, **k):
        pass


class WDT:
    def __init__(self, timeout=0):
        pass

    def feed(self):
        pass
