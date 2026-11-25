# drivers/es8311.py -- minimal MicroPython driver for the ES8311 audio codec (I2C control only).
# Register sequence ported from ESPHome's es8311 component (itself based on Espressif's driver).
# Only 16 kHz is in the coefficient table for now. I2S itself is set up by the caller.
#
# Clock modes (see COEFF):
#   use_mclk=False : codec derives its clock from BCLK; requires bits=32 at 16 kHz
#   use_mclk=True  : caller must also drive an MCLK of 256 x rate

import time

# (mclk, rate): pre_div, pre_mult, adc_div, dac_div, fs_mode, lrck_h, lrck_l, bclk_div, adc_osr, dac_osr
COEFF = {
    (4096000, 16000): (0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0xFF, 0x04, 0x10, 0x20),
    (1024000, 16000): (0x01, 0x04, 0x01, 0x01, 0x00, 0x00, 0xFF, 0x04, 0x10, 0x20),
}
PRE_MULT_CODE = {1: 0, 2: 1, 4: 2, 8: 3}
RES_CODE = {16: 3 << 2, 24: 0, 32: 4 << 2}


class ES8311:
    ADDR = 0x18

    def __init__(self, i2c):
        self.i2c = i2c

    def rd(self, reg):
        return self.i2c.readfrom_mem(self.ADDR, reg, 1)[0]

    def wr(self, reg, val):
        self.i2c.writeto_mem(self.ADDR, reg, bytes([val & 0xFF]))

    def upd(self, reg, mask, val):
        self.wr(reg, (self.rd(reg) & ~mask) | (val & mask))

    def init(self, rate=16000, use_mclk=False, bits=32, mic_gain=4, volume=0.75):
        # reset
        self.wr(0x00, 0x1F)
        time.sleep_ms(20)
        self.wr(0x00, 0x00)

        # clock source and dividers
        if use_mclk:
            mclk = rate * 256
            self.wr(0x01, 0x3F)
        else:
            mclk = rate * bits * 2          # BCLK frequency
            self.wr(0x01, 0x3F | 0x80)      # bit 7: take internal clock from SCLK pin
        (pre_div, pre_mult, adc_div, dac_div, fs_mode,
         lrck_h, lrck_l, bclk_div, adc_osr, dac_osr) = COEFF[(mclk, rate)]
        self.upd(0x02, 0xF8, ((pre_div - 1) << 5) | (PRE_MULT_CODE[pre_mult] << 3))
        self.wr(0x03, (fs_mode << 6) | adc_osr)
        self.wr(0x04, dac_osr)
        self.wr(0x05, ((adc_div - 1) << 4) | (dac_div - 1))
        self.upd(0x06, 0x3F, bclk_div - 1)
        self.upd(0x07, 0x3F, lrck_h)
        self.wr(0x08, lrck_l)

        # serial format: codec is I2S slave, sample resolution
        self.upd(0x00, 0x40, 0)
        self.wr(0x09, RES_CODE[bits])
        self.wr(0x0A, RES_CODE[bits])

        # analog mic path
        self.wr(0x14, 0x1A)
        self.wr(0x16, mic_gain)
        self.wr(0x17, 0xC8)

        self.set_volume(volume)

        # power-up sequence
        for reg, val in ((0x0D, 0x01), (0x0E, 0x02), (0x12, 0x00), (0x13, 0x10),
                         (0x1C, 0x6A), (0x37, 0x08), (0x00, 0x80)):
            self.wr(reg, val)

    def set_volume(self, v):
        v = min(1.0, max(0.0, v))
        self.wr(0x32, int(v * 255))

    def mute(self, on):
        self.upd(0x31, 0x60, 0x60 if on else 0)


