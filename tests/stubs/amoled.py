"""Host-side stand-in for the firmware's `amoled` module: records drawing and checks every shape is on screen."""
W, H = 368, 448
GREEN = (0, 255, 0)


class QSPIPanel:
    def __init__(self, *a, **k):
        pass


class AMOLED:
    GREEN = GREEN
    refreshes = 0

    def __init__(self, panel, type=0, bpp=16, reset=None, auto_refresh=True, **k):
        self.auto_refresh = auto_refresh
        self.br = 100
        self.calls = 0

    def reset(self): pass
    def init(self): pass
    def deinit(self): pass
    def colorRGB(self, r, g, b): return (r, g, b)

    def fill(self, c):
        self.calls += 1

    def fill_rect(self, x, y, w, h, c):
        assert 0 <= x and 0 <= y and w > 0 and h > 0 and x + w <= W and y + h <= H, ("rect outside the screen", x, y, w, h)
        self.calls += 1

    def fill_circle(self, x, y, r, c):
        self.calls += 1

    def refresh(self, *a):
        AMOLED.refreshes += 1

    def brightness(self, b): self.br = b
    def disp_on(self): pass
    def disp_off(self): pass
