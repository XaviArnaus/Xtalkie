# drivers/axp2101.py -- AXP2101 power management chip (I2C 0x34): battery, charger, USB. Never raises.
#   reg 0x00 bit 3 = battery connected, bit 5 = USB power good
#   reg 0x01 bits 7..5 = battery current direction (1 charging, 2 discharging, 0 standby)
#   reg 0xA4 = battery percentage (fuel gauge)
#   reg 0x34/0x35 = battery voltage in mV (14 bit; needs the ADC enabled in reg 0x30 bit 0)
# read() returns (percent or None, external_power, usb_power, battery_present):
#   external_power is True while USB power is good OR the battery is charging;
#   if the gauge says 0 while the battery is NOT charging and its voltage is clearly not empty, the percentage
#   is estimated from the voltage (while charging the voltage reads too high, so the gauge value is kept);
#   with no battery detected the percentage is None.
import time

# open-circuit voltage (mV) -> percent, a typical single-cell Li-ion curve
_CURVE = ((3300, 0), (3500, 5), (3600, 12), (3700, 25), (3800, 40), (3900, 60), (4000, 80), (4100, 92), (4200, 100))


def estimate_percent(mv):
    if mv <= _CURVE[0][0]:
        return 0
    for i in range(1, len(_CURVE)):
        v0, p0 = _CURVE[i - 1]
        v1, p1 = _CURVE[i]
        if mv <= v1:
            return int(p0 + (p1 - p0) * (mv - v0) / (v1 - v0))
    return 100


class AXP2101:
    def __init__(self, i2c, addr=0x34):
        self.i2c = i2c
        self.addr = addr
        self._adc_on = False

    def raw(self):
        """Raw register values, for checking the bit meanings on the real board."""
        r = self.i2c
        return (r.readfrom_mem(self.addr, 0x00, 1)[0],
                r.readfrom_mem(self.addr, 0x01, 1)[0],
                r.readfrom_mem(self.addr, 0xA4, 1)[0])

    def vbat_mv(self):
        r = self.i2c
        if not self._adc_on:
            v = r.readfrom_mem(self.addr, 0x30, 1)[0]
            r.writeto_mem(self.addr, 0x30, bytes([v | 0x01]))
            self._adc_on = True
            time.sleep_ms(20)
        h = r.readfrom_mem(self.addr, 0x34, 1)[0]
        lo = r.readfrom_mem(self.addr, 0x35, 1)[0]
        return ((h & 0x3F) << 8) | lo

    def read(self):
        """(percent or None, external_power, usb_power, battery_present)"""
        try:
            st1, st2, gauge = self.raw()
            present = bool(st1 & 0x08)
            usb = bool(st1 & 0x20)
            charging = ((st2 >> 5) & 0x07) == 1
            pct = None
            if present:
                pct = gauge if gauge <= 100 else None
                if not pct and not charging:                 # gauge says 0 (or nothing): look at the voltage
                    try:
                        mv = self.vbat_mv()
                        if mv > 3500:
                            pct = estimate_percent(mv)
                    except OSError:
                        pass
            return pct, (usb or charging), usb, present
        except OSError:
            return None, False, False, False

    def debug(self):
        try:
            st1, st2, gauge = self.raw()
            mv = self.vbat_mv()
            return ("reg00=0x%02X reg01=0x%02X gauge=%d%%  vbat=%d mV  battery_present=%s usb=%s dir=%d  -> shows %s" % (
                st1, st2, gauge, mv, bool(st1 & 0x08), bool(st1 & 0x20), (st2 >> 5) & 7, self.read()[:2]))
        except OSError as e:
            return "power chip not readable: %s" % e
