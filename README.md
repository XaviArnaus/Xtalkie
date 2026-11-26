# Xtalkie -- baby monitor on the Waveshare ESP32-S3-Touch-AMOLED-1.8 (MicroPython)

Two boards: a **master** in the child's room (listens, decides with a snore-aware gate, streams when something
needs attention) and a **slave** with the parent (plays the audio, shows a bell, alarms if the link is lost).

## Layout (on the board and in this folder)

```
main.py              starts the role named in config.json
config.json          per board: role, WiFi, settings (not in this folder: deploy.py / you create it)
config.example.json  an example to copy
README.md
CHANGELOG.md         what changed in each version (bump VERSION in lib/version.py for every change put on a board)
lib/version.py       the software version of this code (and the commit stamp written by deploy.py)
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
  helpers/           config.py (config.json + state.json), log.py (rotating log), watchdog.py, clips.py (WAV clips, capped)
  net/               link.py (WiFi access point / station + UDP), proto.py (wire protocol)
  dsp/               gate.py (the detection algorithm), clipper.py (level trigger for the play mode), effects.py (speed); no hardware access
  ui/                gfx.py (font + icons), screens.py (the screens), hud.py (button, battery, menu, test mode), playui.py (play screen)
  app/               master.py (child room), slave.py (parent), play.py (voice game)
tools/               run by hand from Thonny (never at boot)
  ui_demo.py  screen_probe.py  battery_check.py  disk.py  record_raw.py  cleanup_old.py
pc/                  runs on the computer, not on the board
  deploy.py          copies the project to a board and writes its config.json
  versions.py        lists the software version and role of every connected board (restarts them afterwards)
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

### Start-up

At power-up a unit shows the start-up screen (name, version, role; steps CONFIG, AUDIO, NETWORK, READY), gives one short
beep, and after `ui.ready_s` seconds moves on (the parent unit shows its status screen). The same steps are printed
with their times (`[boot] +123 ms ...`). The slave does not wait for WiFi: NETWORK shows SEARCHING and the unit is
usable at once.

**The child unit never lights the room after an automatic restart** (crash, watchdog, reset button): it lights its
screen and beeps only when a person started it. The decision uses a marker in RTC memory plus `machine.reset_cause()`;
both raw values are printed and logged at every boot (`[boot] last run ended: ...; reset cause: ...`, and
`boot,...,prev=,cause=,manual=` in `events.csv`). `deploy.py` and `versions.py` mark their restarts as manual. If a
board behaves differently from this on the real hardware, `"ui": {"boot_screen": "always"}` (or `"never"`) in its
`config.json` forces the screen on (or off) and `"boot_beep": false` silences the beep.

**Role chooser.** While the start-up screen says `HOLD BUTTON 2 S: CHOOSE ROLE` (about 3 s, right after READY), hold the
BOOT button for 2 s: the list MASTER / SLAVE / PLAY / BACK appears (tap = next, hold = select, then hold = yes, tap = no).
It works before any role code runs, so a role that crashes at start can still be switched. Do not hold BOOT while
the board is being reset: that enters the chip's download mode. If the parent unit crashes 3 times in a row (each run
shorter than a minute) the chooser appears by itself instead of starting the same role once more; it starts the unit
with its current role if nobody answers for 2 minutes. **The child unit never lights its screen or makes a sound on
its own, not even in a crash loop**: the parent unit's "no link" alarm is the signal, and a person power-cycles the
child unit (which then shows the start-up screen and the chooser). The child unit does not wait for the button after an
automatic restart. Settings: `ui.chooser_window_s`, `chooser_hold_s`,
`chooser_timeout_s`, `crash_limit`.

### Software version

Every board knows its version (`lib/version.py`): printed at boot, in the log (`boot,...,ver=`), and in small text under
the title of the status screen. `deploy.py` adds the git commit (`0.2.0 6f14f8d`; a `+` means tracked files differed
from the commit); a hand-flashed board shows just `0.2.0`. The two units send each other their version; when they
differ the status screen shows an amber `<OTHER> HAS <version>` line. Units from before versions existed report
nothing, so no warning appears for them. `python pc/versions.py` lists the connected boards.

A board starts by itself at power-up. A board that only needs power can run from a USB charger or power bank.
Role `idle` starts nothing: a clean board for the tools. Role `loopback` tests everything on one board.

## Using it

The BOOT button, and the panel is dark unless something is shown.
- **tap**: status (link icon, battery of this unit and of the other unit), 10 s. On the child unit the bottom line says
  how it started (`STARTED BY A PERSON`, `RESTART: CRASH X2`, ...). On the parent unit an amber `CHILD RESTARTED` line
  means the child unit restarted by itself (it stays until a person restarts it); an amber `CHILD HAS <version>` line
  means the two units run different software.
- **hold 1 s** (parent unit): menu. Tap = next item, hold = select.
  TEST LIVE (stream the child's microphone for 10 s: AUDIO OK / NO AUDIO), TEST ALARM, VOLUME n (1..5, remembered),
  MIC n (1..5 = the child unit's sensitivity, set remotely and remembered there), ROLE, EXIT.
- **ROLE** (parent unit menu, and the play menu): MASTER / SLAVE / PLAY / BACK. Choose one (hold), confirm with hold =
  YES (tap = NO), and the unit writes `config.json` (only the `role` key; the old file stays as `config.json.bak`) and
  restarts in the new role. The child unit has no menu on purpose: a toddler cannot switch its role. To change the
  child unit's role, edit `config.json` or run `pc/deploy.py`.
- **alert** (parent): the screen wakes with a bell while the audio plays; a tap dismisses it.
- **no link** (parent): cross + beeps; a tap mutes them for 5 minutes.
- Battery bolt = external power. `USB` = no battery detected.
- A stream longer than 45 s is cut for 8 s (an acoustic feedback loop between the two units would otherwise howl).

## Play mode (the voice game, and a way to collect voice clips)

One board, no network. She speaks, the device plays it back to her, and every clip is kept as a WAV file for later
analysis. The clips use the same microphone chain (same mic gain) as the monitor, so they are directly comparable
with what the monitor hears at night.

**Switch a board to it** (either board; it replaces the monitor role on that board while it runs):
`python pc/deploy.py <port> play`, or in Thonny open `/config.json` on the board, set `"role": "play"` and reset.
**Switch back before the night:** hold the button while it is idle > ROLE > MASTER or SLAVE > hold = YES (or edit
`config.json` / deploy again). The same menu has VOLUME and SPEED (0.75 deep / 1.0 as spoken / 1.4 chipmunk, remembered).
The menu opens only when no clip is being recorded, and the microphone is closed while it is open.

What she sees: a green ring and "SPEAK" while it listens, a blue disc and "LISTEN" while it plays her voice back,
and the number of clips kept. The screen switches itself off after `idle_off_s` without a sound. It is never drawn
while a clip is being recorded (a draw would punch a hole in the recording).

Clips: `/clips/c0001_2.4s.wav`, `c0002_0.9s.wav`, ... (16-bit mono 16 kHz, plays on any computer). At most
`max_total_kb` (6000 KB, about 3 minutes) are kept: the oldest clips are deleted first. If the flash is short
for any other reason, nothing is saved and no clip is deleted. Copy them to the computer with Thonny (View > Files,
right-click `/clips` > Download) or `mpremote connect <port> fs cp -r :clips .` (a recent mpremote), and delete them
from the board afterwards if you want room for more (`mpremote connect <port> fs rm -r :clips`).
The clips stay on the board's flash; nothing leaves it unless you copy it.

Tuning (`play` in config.json): `trig_db` (12) how far above the room a sound must be to start a clip, lower it
for whispers; `hang_ms` (800) the pause that ends a clip; `speed` 1.4 makes her voice a chipmunk, 0.75 a giant;
`"save": false` plays only, keeps nothing.

## Checks and diagnostics (`tools/`, with config.json `{"role": "idle"}` and a reset)

`ui_demo.py` every screen and the battery; `screen_probe.py` which panel switch-on sequence works (found: do not use
disp_off/disp_on on this firmware); `battery_check.py` raw power-chip readings; `disk.py` free flash and file sizes
(free space is also printed at every boot); `record_raw.py` raw audio to a file, then `python pc/raw2wav.py file.raw`.

## Configuration (`config.json` overrides `lib/helpers/config.py`; only the keys you set are replaced)

`role`, `port`, `cpu_mhz` (80/160/240, default 160), `auto_reboot`, `watchdog_ms`, `log`; `wifi` {ssid, password, channel, mode, master_ip, power_save (station side: none/min/max)};
`audio` {mic_gain, volume, playback_gain, agc, agc_max_gain, volume_level}; `gate` {any `dsp/gate.py` setting}; `play` {trig_db, end_db, hang_ms, pre_ms, tail_ms, min_ms, max_s, speed, save, dir, max_total_kb, min_free_kb, idle_off_s};
`master` {sens_level, max_open_s, cooldown_s, preroll_lead_ms}; `slave` {jitter_frames, link_timeout_ms, ...};
`ui` {enabled, manual_refresh, brightness, alarm_brightness, status_s, alert_hold_s, flash_ms, test_s, mute_s,
boot_screen, boot_beep, ready_s, chooser_window_s, chooser_hold_s, chooser_timeout_s, crash_limit}.
Settings changed from the menu live in `state.json`, not in config.json.

## Tests

```
python tests/run_all.py          # about a minute, no hardware, Python 3 only
```
They use stand-ins for `machine` and `amoled` (`tests/stubs/`). They check: imports and the layering rule, the chip
drivers on fake registers, the gate on synthetic snoring / speech / thump, the loopback path, the tools and
`deploy.py` (with its version stamp), the version exchange and `pc/versions.py`, and two threaded master + slave simulations over real UDP (alerts, menu, live test, link loss, mute,
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
