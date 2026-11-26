"""List the serial ports on this computer, to find the <port> for pc/deploy.py.

    python pc/ports.py

Run it with the board unplugged, then plugged in: the new line is the board.
Needs:  pip install mpremote   (it brings pyserial along)
"""
import sys

try:
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is missing: pip install mpremote")


def main():
    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    if not ports:
        print("No serial ports found. Check the USB cable (it must carry data) and plug the board in.")
        return
    for p in ports:
        usb = "USB %04X:%04X" % (p.vid, p.pid) if p.vid is not None else "not USB"
        print("%-28s %-14s %s" % (p.device, usb, p.description))
    print("\nUse the board's device name as <port>, e.g.:  python pc/deploy.py %s child --ssid xtalkie --password ..."
          % ports[0].device)


if __name__ == "__main__":
    main()
