# ui/gfx.py -- tiny drawing toolkit on top of the amoled display: built-in 5x7 font and icons.
# Uses only fill / fill_rect / fill_circle / colorRGB, and needs no font files on the flash.

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (215, 25, 25)
GREEN = (30, 190, 80)
AMBER = (255, 160, 0)
ORANGE = (255, 110, 0)
GRAY = (150, 150, 150)
DGRAY = (40, 40, 40)

# 5 columns x 7 rows, one int per row, bit 4 = leftmost pixel
FONT = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E), "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F), "3": (0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02), "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E), "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E), "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    "%": (0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03), ":": (0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0),
    "-": (0, 0, 0, 0x1F, 0, 0, 0), ".": (0, 0, 0, 0, 0, 0x0C, 0x0C), "!": (0x04, 0x04, 0x04, 0x04, 0x04, 0, 0x04),
    "?": (0x0E, 0x11, 0x01, 0x02, 0x04, 0, 0x04), ".": (0, 0, 0, 0, 0, 0x0C, 0x0C),
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11), "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E), "D": (0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F), "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F), "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E), "J": (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11), "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11), "N": (0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E), "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D), "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E), "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E), "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11), "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04), "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
}


class Gfx:
    def __init__(self, display, w, h):
        self.d = display
        self.W = w
        self.H = h
        self._cols = {}

    def col(self, rgb):
        c = self._cols.get(rgb)
        if c is None:
            c = self.d.colorRGB(rgb[0], rgb[1], rgb[2])
            self._cols[rgb] = c
        return c

    def clear(self, rgb):
        self.d.fill(self.col(rgb))

    def rect(self, x, y, w, h, rgb):
        x, y, w, h = int(x), int(y), int(w), int(h)
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if x + w > self.W:
            w = self.W - x
        if y + h > self.H:
            h = self.H - y
        if w > 0 and h > 0:
            self.d.fill_rect(x, y, w, h, self.col(rgb))

    def circle(self, cx, cy, r, rgb):
        r = int(r)
        if r > 0:
            self.d.fill_circle(int(cx), int(cy), r, self.col(rgb))

    def line(self, x0, y0, x1, y1, t, rgb):
        """Thick line made of small squares."""
        t = max(1, int(t))
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        n = max(abs(x1 - x0), abs(y1 - y0)) // max(1, t // 2) + 1
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = y0 + (y1 - y0) * i / n
            self.rect(x - t / 2, y - t / 2, t, t, rgb)

    # ---- text ----
    def text(self, s, x, y, scale, rgb):
        for ch in s:
            rows = FONT.get(ch.upper(), FONT[" "])
            for r in range(7):
                bits = rows[r]
                c = 0
                while c < 5:
                    if bits & (0x10 >> c):
                        c2 = c
                        while c2 < 5 and bits & (0x10 >> c2):
                            c2 += 1
                        self.rect(x + c * scale, y + r * scale, (c2 - c) * scale, scale, rgb)
                        c = c2
                    else:
                        c += 1
            x += 6 * scale

    def text_w(self, s, scale):
        return len(s) * 6 * scale - scale

    def text_c(self, s, y, scale, rgb):
        self.text(s, (self.W - self.text_w(s, scale)) // 2, y, scale, rgb)

    # ---- icons ----
    def bell(self, cx, cy, s, rgb):
        self.circle(cx, cy - 0.60 * s, 0.07 * s, rgb)                      # knob
        self.circle(cx, cy - 0.20 * s, 0.38 * s, rgb)                      # dome
        self.rect(cx - 0.38 * s, cy - 0.20 * s, 0.76 * s, 0.32 * s, rgb)   # body
        self.rect(cx - 0.45 * s, cy + 0.12 * s, 0.90 * s, 0.10 * s, rgb)   # flare
        self.rect(cx - 0.52 * s, cy + 0.22 * s, 1.04 * s, 0.10 * s, rgb)
        self.rect(cx - 0.58 * s, cy + 0.32 * s, 1.16 * s, 0.10 * s, rgb)
        self.rect(cx - 0.62 * s, cy + 0.42 * s, 1.24 * s, 0.07 * s, rgb)   # lip
        self.circle(cx, cy + 0.58 * s, 0.09 * s, rgb)                      # clapper
        for side in (-1, 1):                                               # ringing marks
            self.line(cx + side * 0.66 * s, cy - 0.45 * s, cx + side * 0.80 * s, cy - 0.28 * s, 0.045 * s, rgb)
            self.line(cx + side * 0.74 * s, cy - 0.64 * s, cx + side * 0.94 * s, cy - 0.38 * s, 0.045 * s, rgb)

    def check(self, cx, cy, s, rgb):
        t = 0.2 * s
        self.line(cx - 0.45 * s, cy + 0.02 * s, cx - 0.12 * s, cy + 0.36 * s, t, rgb)
        self.line(cx - 0.12 * s, cy + 0.36 * s, cx + 0.50 * s, cy - 0.36 * s, t, rgb)

    def cross(self, cx, cy, s, rgb):
        t = 0.2 * s
        self.line(cx - 0.4 * s, cy - 0.4 * s, cx + 0.4 * s, cy + 0.4 * s, t, rgb)
        self.line(cx - 0.4 * s, cy + 0.4 * s, cx + 0.4 * s, cy - 0.4 * s, t, rgb)

    def battery(self, x, y, w, h, pct, charging):
        t = max(3, h // 12)
        self.rect(x, y, w, h, WHITE)                                       # frame
        self.rect(x + t, y + t, w - 2 * t, h - 2 * t, BLACK)
        self.rect(x + w, y + h // 4, max(5, w // 12), h // 2, WHITE)       # nub
        if pct is None:
            if charging:                                                   # no battery, but external power
                cx, cy, k = x + w // 2, y + h // 2, h // 9
                self.line(cx + k, cy - 3 * k, cx - k, cy, k, AMBER)
                self.line(cx - k, cy, cx + k, cy, k, AMBER)
                self.line(cx + k, cy, cx - k, cy + 3 * k, k, AMBER)
            else:
                self.text("?", x + w // 2 - 15, y + h // 2 - 17, 5, GRAY)
            return
        color = GREEN if pct >= 30 else (AMBER if pct >= 15 else RED)
        inner = w - 2 * t - 6
        self.rect(x + t + 3, y + t + 3, inner * max(0, min(100, pct)) // 100, h - 2 * t - 6, color)
        if charging:                                                       # lightning bolt
            cx, cy = x + w // 2, y + h // 2
            k = h // 9
            self.line(cx + k, cy - 3 * k, cx - k, cy, k, AMBER if pct >= 30 else WHITE)
            self.line(cx - k, cy, cx + k, cy, k, AMBER if pct >= 30 else WHITE)
            self.line(cx + k, cy, cx - k, cy + 3 * k, k, AMBER if pct >= 30 else WHITE)
