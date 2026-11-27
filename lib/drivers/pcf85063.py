# drivers/pcf85063.py -- PCF85063A real-time clock chip (I2C 0x51), on the Waveshare ESP32-S3 AMOLED boards.
# It keeps counting while the board is switched off (as long as its supply stays on), so it is the clock that
# survives a power cut. A chip that was never set, or whose oscillator stopped, has the OS flag (bit 7 of the
# seconds register) set: its time is then NOT trustworthy. Writing the time clears that flag.
# Registers: 0x00 control 1 (bit 5 STOP, bit 1 12/24 h), 0x04 seconds .. 0x0A years, all BCD.
REG_CTRL1 = 0x00
REG_SECONDS = 0x04


def _bcd(b):
    return (b >> 4) * 10 + (b & 0x0F)


def _to_bcd(n):
    return ((n // 10) << 4) | (n % 10)


class PCF85063:
    def __init__(self, i2c, addr=0x51):
        self.i2c = i2c
        self.addr = addr

    def read(self):
        """((year, month, day, weekday, hour, minute, second) or None if the registers are nonsense,
        oscillator-stopped flag). The weekday counts from 0; years are 2000 + the chip's two digits."""
        r = self.i2c.readfrom_mem(self.addr, REG_SECONDS, 7)
        os_flag = bool(r[0] & 0x80)
        t = (2000 + _bcd(r[6]), _bcd(r[5] & 0x1F), _bcd(r[3] & 0x3F), r[4] & 0x07,
             _bcd(r[2] & 0x3F), _bcd(r[1] & 0x7F), _bcd(r[0] & 0x7F))
        sane = 1 <= t[1] <= 12 and 1 <= t[2] <= 31 and t[4] < 24 and t[5] < 60 and t[6] < 60
        return (t if sane else None), os_flag

    def datetime(self):
        """The time if the chip can be trusted (flag clear, sane registers), else None."""
        t, os_flag = self.read()
        return None if os_flag else t

    def set(self, t):
        """t = (year, month, day, weekday, hour, minute, second). Starts the clock in 24 h mode, clears the flag."""
        y, mo, d, wd, h, mi, s = t
        self.i2c.writeto_mem(self.addr, REG_CTRL1, bytes([0x00]))
        self.i2c.writeto_mem(self.addr, REG_SECONDS, bytes([_to_bcd(s), _to_bcd(mi), _to_bcd(h), _to_bcd(d),
                                                            wd & 0x07, _to_bcd(mo), _to_bcd(y % 100)]))
