# tools/disk.py -- how much flash is free, and what is using it. Run it from Thonny (Run).
import os

st = os.statvfs("/")
block, total, free = st[0], st[2], st[3]
print("flash: %.1f MB total, %.1f MB free (%.0f%%)" % (block * total / 1e6, block * free / 1e6, 100 * free / total))
print()


def walk(path, depth=0):
    used = 0
    for name in sorted(os.listdir(path)):
        full = (path.rstrip("/") + "/" + name)
        try:
            s = os.stat(full)
        except OSError:
            continue
        if s[0] & 0x4000:
            print("  " * depth + name + "/")
            used += walk(full, depth + 1)
        else:
            print("  " * depth + "%-22s %8d bytes" % (name, s[6]))
            used += s[6]
    return used


print("files: %d bytes in total" % walk("/"))
print()
print("Logs: events.csv + events.old.csv are capped (each max 150 KB, and never more than 1/6 of the free space).")
