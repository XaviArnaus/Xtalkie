"""Show a board's serial output and keep going across restarts (Thonny loses the port when the board resets).

    python pc/watch.py <port>                 e.g.  python pc/watch.py /dev/cu.usbmodem1101
    python pc/watch.py <port> --log out.txt   also write everything to a file (to send)
    python pc/watch.py                        the first Espressif USB board found

Ctrl+C stops. Close Thonny first (only one program can use the port). It only LISTENS (except with --reset, which
sends one soft reboot at the start), and the DTR / RTS lines are kept low so that opening the port does not restart
the board.
Needs:  pip install mpremote   (it brings pyserial along)
"""
import argparse
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is missing: pip install mpremote")


def find_port():
    for p in sorted(list_ports.comports(), key=lambda p: p.device):
        if p.vid == 0x303A:                                  # Espressif's USB id (the board's own USB)
            return p.device
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", nargs="?", help="serial port (default: the first Espressif USB board)")
    ap.add_argument("--log", help="also write the output to this file")
    ap.add_argument("--reset", action="store_true",
                    help="after the first connection send Ctrl+C, Ctrl+C, Ctrl+B, Ctrl+D (a soft reboot): starts main.py "
                         "on a board that sits idle at the Python prompt (also in raw REPL mode)")
    args = ap.parse_args()
    pending_reset = args.reset
    log = open(args.log, "a", encoding="utf-8") if args.log else None

    def out(text):
        sys.stdout.write(text)
        sys.stdout.flush()
        if log:
            log.write(text)
            log.flush()

    was_open = False
    try:
        while True:
            port = args.port or find_port()
            try:
                if not port:
                    raise serial.SerialException("no board found")
                s = serial.Serial()
                s.port = port
                s.baudrate = 115200
                s.timeout = 0.5
                s.dtr = False                                # must be set before open(): opening must not reset the board
                s.rts = False
                s.open()
            except (serial.SerialException, OSError):
                if was_open:
                    out("\n--- port gone (the board restarted?), waiting ---\n")
                    was_open = False
                time.sleep(0.5)
                continue
            out("--- connected to %s ---\n" % port)
            was_open = True
            if pending_reset:
                pending_reset = False                        # once only: later restarts are the board's own
                try:
                    s.write(b"\x03\x03")                     # interrupt whatever runs
                    time.sleep(0.3)
                    s.write(b"\x02")                         # Ctrl+B: leave the raw REPL (Thonny / mpremote leave it open)
                    time.sleep(0.3)
                    s.write(b"\x04")                         # Ctrl+D: soft reboot, which runs main.py
                    out("--- sent Ctrl+C Ctrl+C Ctrl+B Ctrl+D (soft reboot) ---\n")
                except (serial.SerialException, OSError):
                    pass
            try:
                while True:
                    data = s.read(256)
                    if data:
                        out(data.decode("utf-8", "replace"))
            except (serial.SerialException, OSError):
                out("\n--- port gone (the board restarted?), waiting ---\n")
                was_open = False
                try:
                    s.close()
                except Exception:
                    pass
                time.sleep(0.5)
    except KeyboardInterrupt:
        out("\n--- stopped ---\n")


if __name__ == "__main__":
    main()
