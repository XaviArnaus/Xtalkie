# babymon -- baby monitor on the Waveshare ESP32-S3-Touch-AMOLED-1.8 (MicroPython)

Two boards: a **master** in the child's room (listens, decides with a snore-aware gate, streams when something
needs attention) and a **slave** with the parent (plays the audio, shows a bell, alarms if the link is lost).

## Layout (on the board and in this folder)

```
main.py              starts the role named in config.json
config.json          per board: role, WiFi, settings (not in this folder: deploy.py / you create it)
config.example.json  an example to copy
README.md
lib/                 everything else; each layer only uses the layers above it in this list
  drivers/           ONE MODULE PER CHIP, named after the chip, no application knowledge
    es8311.py          audio codec (I2C control)
    axp2101.py         power management: battery, charger, USB
    tca9554.py         I/O expander (panel power and reset lines)
    sh8601.py          AMOLED panel, through the firmware's `amoled` module
  board/             this board: wiring, and the peripherals built from the drivers
    __init__.py        pin map, constants, the shared I2C bus      (import board)
    audio.py           I2S + ES8311: capture frames, play frames, beep, automatic gain
    display.py         TCA9554 + SH8601: panel power/reset, show / hide by brightness
  helpers/           config.py (config.json + state.json), log.py (rotating log), watchdog.py
  net/               link.py (WiFi access point / station + UDP), proto.py (wire protocol)
  dsp/               gate.py (the detection algorithm; no hardware access)
  ui/                gfx.py (font + icons), screens.py (the screens), hud.py (button, battery, menu, test mode)
  app/               master.py (child room), slave.py (parent)
tools/               run by hand from Thonny (never at boot)
  ui_demo.py  screen_probe.py  battery_check.py  disk.py  record_raw.py  cleanup_old.py
pc/                  runs on the computer, not on the board
  deploy.py          copies the project to a board and writes its config.json
  raw2wav.py         converts a raw recording into a WAV file
  requirements.txt   mpremote (for deploy.py)
tests/               host-side tests: Python 3 only, no hardware (see "Tests")
.gitignore           keeps config.json (WiFi password), state.json, logs and recordings out of Git
```

Rules: `drivers/` imports nothing of ours. `board/` uses `drivers/`. `helpers/`, `net/`, `dsp/` need no hardware.
`ui/` may use `board/`. `app/` may use everything. Modules are imported by package, e.g.
`from drivers.axp2101 import AXP2101`, `from board.audio import Audio`, `from dsp.gate import Gate`.
`/lib` is searched first (main.py and the tools make sure of it), so an old file in `/` can never shadow a library.

### Using the hardware layer in another project

`drivers/` and `board/` are the reusable part. A new project is a new `main.py` (+ its own packages next to `app/`):

```python
import board
from board.audio import Audio          # microphone / speaker
from board.display import Display      # AMOLED, dark until show()
from drivers.axp2101 import AXP2101    # battery

print(AXP2101(board.i2c()).read())     # (percent, external power, usb, battery present)
```

## Firmware

The boards run the MicroPython build with the `amoled` display module from
<https://github.com/dobodu/Lilygo_Waveshare_Amoled_Micropython> (folder `firmware/`). This project was developed with
`firmware_2026_05_02.bin` (MicroPython 1.28 preview, ESP-IDF 5.5.2). The binary is not part of this repository.
Board: Waveshare ESP32-S3-Touch-AMOLED-1.8, original revision (SH8601 panel, FT3168 touch).

## Preparing a board (once per board; Thonny holds only one board at a time)

1. Flash the firmware (Thonny: Tools > Options > Interpreter > Install or update MicroPython; if the board is not
   recognised hold BOOT, tap RESET, release BOOT).
2. Put the project on the board, either
   - **Thonny:** in the Files panel right-click `main.py`, `lib` and `tools` > *Upload to /* (do not upload a config.json
     over an existing one); then create `/config.json` on the board; or
   - **deploy.py** (Thonny closed, `pip install mpremote`):
     `python pc/deploy.py <port> <role> --ssid <name> --password <8+ chars> [--night] [--clean]`
3. *Coming from the first, flat layout?* Run `tools/cleanup_old.py` on the board once (or use `--clean`), then reset.
   `state.json`, `config.json` and the log files are kept.
4. Same `ssid` / `password` on both boards. `--night` (or `"auto_reboot": true`) restarts a board after a crash or hang.

A board starts by itself at power-up. A board that only needs power can run from a USB charger or power bank.
Role `idle` starts nothing: a clean board for the tools. Role `loopback` tests everything on one board.

## Using it

The BOOT button, and the panel is dark unless something is shown.
- **tap**: status (link icon, battery of this unit and of the other unit), 10 s.
- **hold 1 s** (parent unit): menu. Tap = next item, hold = select.
  TEST LIVE (stream the child's microphone for 10 s: AUDIO OK / NO AUDIO), TEST ALARM, VOLUME n (1..5, remembered),
  MIC n (1..5 = the child unit's sensitivity, set remotely and remembered there), EXIT.
- **alert** (parent): the screen wakes with a bell while the audio plays; a tap dismisses it.
- **no link** (parent): cross + beeps; a tap mutes them for 5 minutes.
- Battery bolt = external power. `USB` = no battery detected.
- A stream longer than 45 s is cut for 8 s (an acoustic feedback loop between the two units would otherwise howl).

## Checks and diagnostics (`tools/`, with config.json `{"role": "idle"}` and a reset)

`ui_demo.py` every screen and the battery; `screen_probe.py` which panel switch-on sequence works (found: do not use
disp_off/disp_on on this firmware); `battery_check.py` raw power-chip readings; `disk.py` free flash and file sizes
(free space is also printed at every boot); `record_raw.py` raw audio to a file, then `python pc/raw2wav.py file.raw`.

## Configuration (`config.json` overrides `lib/helpers/config.py`; only the keys you set are replaced)

`role`, `port`, `cpu_mhz` (80/160/240, default 160), `auto_reboot`, `watchdog_ms`, `log`; `wifi` {ssid, password, channel, mode, master_ip, power_save (station side: none/min/max)};
`audio` {mic_gain, volume, playback_gain, agc, agc_max_gain, volume_level}; `gate` {any `dsp/gate.py` setting};
`master` {sens_level, max_open_s, cooldown_s, preroll_lead_ms}; `slave` {jitter_frames, link_timeout_ms, ...};
`ui` {enabled, manual_refresh, brightness, alarm_brightness, status_s, alert_hold_s, flash_ms, test_s, mute_s}.
Settings changed from the menu live in `state.json`, not in config.json.

## Tests

```
python tests/run_all.py          # about a minute, no hardware, Python 3 only
```
They use stand-ins for `machine` and `amoled` (`tests/stubs/`). They check: imports and the layering rule, the chip
drivers on fake registers, the gate on synthetic snoring / speech / thump, the loopback path, the tools and
`deploy.py`, and two threaded master + slave simulations over real UDP (alerts, menu, live test, link loss, mute,
the stream-length limit, the remote MIC level). Run them after every change; they do not replace a test on the boards.

## Battery

Measured on the master with the first version (240 MHz, master as WiFi access point, screens in use for demos):
100% to 62% in 40 minutes, so under 2 hours from full. The small battery is a backup, not a night supply: keep the
master on USB power. Already in this version: `cpu_mhz` (default 160) and a per-minute battery line in
`events.csv` (`batt=`, `ext=`) on both units, so the real drain per hour can be read after a night. The master's
status line prints `frame<=N ms`, the worst processing time per frame (limit: 20 ms).
Not done: making the battery unit the WiFi *client* with modem sleep and the plugged-in unit the access point; that
would cut the radio's consumption but changes who creates the network, so it needs the link tested again.

## Licence

Not chosen yet; add a LICENSE file before publishing. The `amoled` module and firmware belong to their own project.

## Not done yet

Push-to-talk, touch input, a pitch-based voice cue (needs real recordings), home-router WiFi mode, a nicer single-button UX.
