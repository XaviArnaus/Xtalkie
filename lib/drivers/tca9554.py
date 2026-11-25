# drivers/tca9554.py -- TCA9554 8-bit I/O expander (I2C 0x20).
# On the Waveshare ESP32-S3 AMOLED boards its pins control the panel power and the panel / touch reset.
REG_INPUT = 0x00
REG_OUTPUT = 0x01
REG_POLARITY = 0x02
REG_CONFIG = 0x03          # bit = 1: input, 0: output


class TCA9554:
    def __init__(self, i2c, addr=0x20):
        self.i2c = i2c
        self.addr = addr

    def _rd(self, reg):
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def _wr(self, reg, val):
        self.i2c.writeto_mem(self.addr, reg, bytes([val & 0xFF]))

    def set(self, pin, level):
        """Drive ONE pin high or low and make it an output; every other pin is left untouched."""
        out = self._rd(REG_OUTPUT)
        out = (out | (1 << pin)) if level else (out & ~(1 << pin))
        self._wr(REG_OUTPUT, out)                    # set the level first ...
        self._wr(REG_CONFIG, self._rd(REG_CONFIG) & ~(1 << pin))   # ... then make it an output

    def get(self, pin):
        return bool(self._rd(REG_INPUT) & (1 << pin))

    def state(self):
        """(inputs, outputs, config) register values, for diagnostics."""
        return self._rd(REG_INPUT), self._rd(REG_OUTPUT), self._rd(REG_CONFIG)
