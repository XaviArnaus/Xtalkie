# board/audio.py -- ES8311 codec + I2S: read mic frames (with level / zero-crossing analysis), play frames, beep.
# The I2S peripheral works in ONE direction at a time here (half duplex): open_rx() or open_tx().
import math
import struct
import time
from array import array
from machine import Pin, I2S

import board
from drivers.es8311 import ES8311

_FMT = "<%dh" % board.FRAMES
FRAMES = board.FRAMES

# Volume levels 1..5 = the peak (of 32767) the playback is raised to by the automatic gain.
LEVELS = {1: 3000, 2: 6000, 3: 10000, 4: 16000, 5: 26000}
NOISE_PEAK = 60        # a frame whose peak is below this is room noise: the gain is not raised for it
IDLE_GAIN = 8.0        # the gain the automatic control relaxes to while there is only noise


class Audio:
    def __init__(self, mic_gain=4, volume=0.75, playback_gain=2.0, agc=True, agc_max_gain=150, level=4):
        self.mic_gain = mic_gain
        self.volume = volume
        self.playback_gain = playback_gain      # fixed gain, used only when agc is off
        self.agc = agc                          # automatic gain: quiet sound is lifted, loud sound held back
        self.agc_max = agc_max_gain
        self.level = 4
        self.agc_target = LEVELS[4]
        self.set_level(level)
        self._g = None
        self._beep_amp = None
        self.pa = Pin(board.PA, Pin.OUT)
        self.pa.value(0)
        self._i2s = None
        self._rx = array('h', [0] * (FRAMES * 4))       # 32-bit stereo slots as half-words
        self._tx = array('h', [0] * (FRAMES * 4))
        self._silence = array('h', [0] * (FRAMES * 4))
        self._beep = None
        self.codec = None

    # ---- setup ---------------------------------------------------------
    def _make(self, mode):
        return I2S(0, sck=Pin(board.I2S_SCK), ws=Pin(board.I2S_WS),
                   sd=Pin(board.I2S_DOUT if mode == I2S.TX else board.I2S_DIN),
                   mode=mode, bits=board.BITS, format=I2S.STEREO, rate=board.RATE, ibuf=20000)

    def start(self):
        """Configure the codec. A clock must be running while the codec registers are written."""
        self.codec = ES8311(board.i2c())
        clk = self._make(I2S.TX)
        time.sleep_ms(50)
        self.codec.init(rate=board.RATE, use_mclk=False, bits=board.BITS,
                        mic_gain=self.mic_gain, volume=self.volume)
        time.sleep_ms(50)
        clk.deinit()

    def open_rx(self):
        self.close()
        self._i2s = self._make(I2S.RX)

    def set_level(self, n):
        self.level = min(5, max(1, int(n)))
        self.agc_target = LEVELS[self.level]

    def open_tx(self):
        self.close()
        self._i2s = self._make(I2S.TX)
        self._g = None                          # the automatic gain starts fresh with every stream

    def close(self):
        if self._i2s is not None:
            self._i2s.deinit()
            self._i2s = None

    def set_pa(self, on):
        self.pa.value(1 if on else 0)

    # ---- capture ---------------------------------------------------------
    def read_frame(self):
        """Block for one 20 ms frame. Returns (payload bytes, level dBFS, zero crossings)."""
        buf = self._rx
        self._i2s.readinto(buf)
        vals = [buf[i] for i in range(1, FRAMES * 4, 4)]      # left slot, high half-word
        acc = 0
        zc = 0
        prev = vals[0]
        for s in vals:
            acc += s * s
            if (s >= 0) != (prev >= 0):
                zc += 1
            prev = s
        r = math.sqrt(acc / FRAMES)
        level = 20 * math.log10(r / 32768) if r > 0 else -99.0
        return struct.pack(_FMT, *vals), level, zc

    # ---- playback --------------------------------------------------------
    def write_payload(self, payload, gain=None):
        vals = struct.unpack(_FMT, payload)
        if gain is not None:
            g = gain
        elif self.agc:
            peak = max(max(vals), -min(vals), 1)
            d = self.agc_target / peak
            if d > self.agc_max:
                d = self.agc_max
            elif d < 0.25:
                d = 0.25
            g = self._g
            if peak < NOISE_PEAK:               # only room noise: do not amplify it, relax to a modest gain
                if g is None:
                    g = IDLE_GAIN
                else:
                    g += (IDLE_GAIN - g) * 0.03
            elif g is None or d < g:
                g = d                           # loud: reduce at once
            else:
                g += (d - g) * 0.5              # a voice: lifted to the target within about 7 frames
            self._g = g
        else:
            g = self.playback_gain
        out = self._tx
        j = 1
        if g == 1.0:
            for v in vals:
                out[j] = v
                out[j + 2] = v
                j += 4
        else:
            for v in vals:
                v = int(v * g)
                if v > 32767:
                    v = 32767
                elif v < -32768:
                    v = -32768
                out[j] = v
                out[j + 2] = v
                j += 4
        self._i2s.write(out)

    def write_silence(self):
        self._i2s.write(self._silence)

    def beep(self, n=3, hz=880, tone_frames=8, gap_frames=6, amp=None):
        """Alarm: n short beeps on the speaker (opens and closes I2S itself); as loud as the volume level."""
        if amp is None:
            amp = max(8000, self.agc_target)
        if self._beep is None or self._beep_amp != amp:
            self._beep_amp = amp
            samples = [int(amp * math.sin(2 * math.pi * hz * i / board.RATE))
                       for i in range(tone_frames * FRAMES)]
            self._beep = [struct.pack(_FMT, *samples[k * FRAMES:(k + 1) * FRAMES])
                          for k in range(tone_frames)]
        self.open_tx()
        self.write_silence()
        self.set_pa(True)
        for _ in range(n):
            for f in self._beep:
                self.write_payload(f, 1.0)
            for _ in range(gap_frames):
                self.write_silence()
        self.write_silence()
        self.set_pa(False)
        self.close()
