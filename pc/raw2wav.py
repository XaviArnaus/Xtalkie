#!/usr/bin/env python3
"""Convert a raw recording from the board (16-bit mono, 16 kHz) into a WAV file you can play.

    python raw2wav.py raw_child_snore.raw            -> raw_child_snore.wav
    python raw2wav.py raw_child_snore.raw --gain 8   (louder, for quiet recordings)
"""
import argparse
import array
import sys
import wave


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--rate", type=int, default=16000)
    args = ap.parse_args()

    data = open(args.raw, "rb").read()
    samples = array.array("h")
    samples.frombytes(data[: len(data) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    if args.gain != 1.0:
        samples = array.array("h", (max(-32768, min(32767, int(s * args.gain))) for s in samples))
    out = args.raw.rsplit(".", 1)[0] + ".wav"
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(args.rate)
        w.writeframes(samples.tobytes() if sys.byteorder == "little" else (samples.byteswap() or samples).tobytes())
    print("%s: %.1f s, peak %d -> %s" % (args.raw, len(samples) / args.rate, max(abs(s) for s in samples) if samples else 0, out))


if __name__ == "__main__":
    main()
