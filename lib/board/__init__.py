# board/__init__.py -- the Waveshare ESP32-S3-Touch-AMOLED-1.8: pins, constants and the shared I2C bus.
# Peripherals built from the chip drivers live next to this file (board/audio.py, board/display.py).

SDA, SCL = 15, 14                       # I2C: codec, expander, PMU, ...
I2S_SCK, I2S_WS, I2S_DOUT, I2S_DIN = 9, 45, 8, 10
PA = 46                                 # speaker amplifier enable (high = on)
BOOT = 0                                # BOOT button

LCD_W, LCD_H = 368, 448
LCD_CS, LCD_CLK = 12, 11
LCD_DATA = (4, 5, 6, 7)
EXP_ADDR = 0x20                         # TCA9554 IO expander
EXIO_EN, EXIO_RST = 1, 2                # panel power enable, panel/touch reset
AXP_ADDR = 0x34                         # AXP2101 power chip (battery)

RATE = 16000
BITS = 32                               # 32-bit slots: the codec derives its clock from BCLK
FRAMES = 320                            # samples per audio frame
FRAME_MS = 20                           # 320 samples at 16 kHz


_i2c = None


def i2c():
    """One shared I2C bus object (codec, expander, power chip)."""
    global _i2c
    if _i2c is None:
        from machine import I2C, Pin
        _i2c = I2C(0, sda=Pin(SDA), scl=Pin(SCL), freq=400000)
    return _i2c
