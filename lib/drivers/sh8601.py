# drivers/sh8601.py -- SH8601 AMOLED panel (QSPI), through the firmware's built-in `amoled` C module.
# This is the original (V1) 1.8" board. Other panels (e.g. CO5300 on newer boards) get their own driver.
# The drawing calls below are the ones used by ui/gfx.py; the full firmware API is on `self.d`.
# NOTE: disp_off()/disp_on() are not offered on purpose: on this firmware the panel stays dark after such
# a cycle. Use brightness(0) with a black picture instead (see board/display.py).


class SH8601:
    def __init__(self, sck, cs, data, width, height, spi_id=2, baudrate=80_000_000, manual=False):
        import amoled
        from machine import Pin, SPI
        spi = SPI(spi_id, baudrate=baudrate, sck=Pin(sck), mosi=None, miso=None, polarity=0, phase=0)
        d = [Pin(n, Pin.OUT) for n in data]
        panel = amoled.QSPIPanel(spi=spi, data=tuple(d), dc=d[1], cs=Pin(cs, Pin.OUT),
                                 pclk=baudrate, width=width, height=height)
        self.width = width
        self.height = height
        self.manual = False
        if manual:                       # draw a whole screen, then refresh() once: much faster
            try:
                self.d = amoled.AMOLED(panel, type=2, bpp=16, auto_refresh=False)
                self.manual = True
            except TypeError:
                self.d = amoled.AMOLED(panel, type=2, bpp=16)
        else:                            # every drawing call refreshes by itself
            self.d = amoled.AMOLED(panel, type=2, bpp=16)

    def reset(self):
        self.d.reset()

    def init(self):
        self.d.init()

    def brightness(self, percent):
        self.d.brightness(percent)

    def refresh(self):
        if self.manual:
            self.d.refresh()

    # drawing primitives (pass-through)
    def colorRGB(self, r, g, b):
        return self.d.colorRGB(r, g, b)

    def fill(self, color):
        self.d.fill(color)

    def fill_rect(self, x, y, w, h, color):
        self.d.fill_rect(x, y, w, h, color)

    def fill_circle(self, x, y, r, color):
        self.d.fill_circle(x, y, r, color)

    def deinit(self):
        self.d.deinit()
