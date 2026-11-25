"""The gate on synthetic signals: silence, snoring it must learn, speech / thump it must not miss."""
import math
import random

from common import check, finish, patch_time

patch_time()
from dsp.gate import Gate


def quiet(n, r):
    return [(-79.0 + r.gauss(0, 1.2), int(r.gauss(115, 15))) for _ in range(n)]


def burst(n, peak, zcr, r):
    out = []
    for i in range(n):
        x = (i + 0.5) / n
        out.append((peak - 9 * (1 - math.sin(math.pi * x)) + r.gauss(0, 1.5), int(r.gauss(zcr, 4))))
    return out


def run(frames, **kw):
    g = Gate(**kw)
    opens, regime_at = [], None
    for i, (lvl, z) in enumerate(frames):
        if g.update(lvl, z) == "open":
            opens.append((i, g.reason))
        if g.regime and regime_at is None:
            regime_at = i
    return g, opens, regime_at


for seed in (1, 2, 3):
    r = random.Random(seed)
    print("seed", seed)
    # 1. a quiet room: no alert
    g, opens, _ = run(quiet(3000, r))
    check(not opens, "a quiet minute gives no alert")

    # 2. regular snoring: learned within a few bursts, then silent
    frames = quiet(100, r)
    starts = []
    for _ in range(25):
        starts.append(len(frames))
        frames += burst(60, -52 + r.uniform(-2, 2), 45, r) + quiet(r.randint(100, 130), r)
    g, opens, regime_at = run(frames)
    learn = [o for o in opens if regime_at is None or o[0] < regime_at]
    after = [o for o in opens if regime_at is not None and o[0] >= regime_at]
    check(regime_at is not None and len(learn) <= 4, "snore rhythm learned within 4 bursts (%d learning alerts)" % len(learn))
    check(len(after) <= 1, "after learning, snoring stays quiet (%d alerts in %d bursts)" % (len(after), 25 - len(learn)))

    # 3. after learning: speech in a gap and a thump must alert
    pos = starts[14] + 60 + 40                       # inside the gap after burst 15
    speech = burst(20, -46, 80, r)                   # 0.4 s, loud, bright
    frames3 = frames[:pos] + speech + frames[pos + 20:]
    g, opens3, _ = run(frames3)
    check(any(pos - 5 <= i <= pos + 60 for i, _ in opens3), "a short loud, bright burst in a snore gap alerts")
    pos2 = starts[18] + 60 + 50
    frames4 = frames[:pos2] + [(-38.0, 100)] + frames[pos2 + 1:]
    g, opens4, _ = run(frames4)
    check(any(i == pos2 and rsn == "impact" for i, rsn in opens4), "a single loud frame alerts at once (impact)")
finish()
