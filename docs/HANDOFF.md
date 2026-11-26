# Xtalkie: handoff for a new chat (2026-11-26, software version 0.6.0)

Paste this into a new chat, then read `docs/BEHAVIOUR.md` (every button press), `docs/HARDWARE_TEST.md` (the checklist
for the first real-board test of this changeset), `CHANGELOG.md` and `README.md` in the repo root.

## Project

MicroPython on two **Waveshare ESP32-S3-Touch-AMOLED-1.8** boards (368x448 SH8601 AMOLED, ES8311 codec, AXP2101 power
chip, FT3168 touch not used yet), dobodu prebuilt firmware `firmware_2026_05_02.bin`. A **baby monitor** for a 3-year-old
who snores: the child unit (role `child`) streams audio to the parent unit (role `parent`) only when the child calls, never
for snoring. A third role `play` is a one-board voice game that saves clips of her voice (for a later pitch-based cue).
UDP over WiFi, the child is the access point. WiFi name default is now `xtalkie` (was `babymon`).

Owner: hobbyist on a Mac with Thonny, little time, prefers stability over cutting edge, short answers, only the changed
files. English. Now moving to a development PC to run the hardware test.

## Repo state

Everything is committed; git tag `live-test-1` = the last state that ran on the boards (rollback: check it out and redeploy
with `pc/deploy.py`). Since then, versions 0.2.0 to 0.6.0, all passing the host tests (`python tests/run_all.py`, 12 test
files, about 90 s, Python 3 only, stubs in `tests/stubs/`) but **none tried on a board yet**. Layout: `main.py`,
`lib/{drivers,board,helpers,net,dsp,ui,app}`, `lib/version.py`, `pc/{deploy,versions,raw2wav}.py`, `tools/`, `tests/`, `docs/`.
Layer rule is checked by `tests/test_layers.py`.

## What was built since live-test-1

- **0.2.0** rename to Xtalkie; software version in `lib/version.py` (+ `lib/_build.py` commit stamp written by `deploy.py`),
  shown at boot, in the log and on the status screen; the units tell each other their version (appended to HELLO and HB,
  older units ignore it); amber `CHILD HAS <v>` on mismatch; `pc/versions.py` lists connected boards (restarts them).
- **0.3.0** start-up screen (CONFIG, AUDIO, NETWORK, READY) with step timings printed; the panel is opened once and shared
  with the HUD / play screen; the parent no longer waits 15 s for WiFi (NETWORK shows SEARCHING); one ready beep on a
  person-started power-on; `ui.boot_screen` auto|always|never. Reboot reason: RTC-memory marker (`helpers/bootinfo.py`:
  RUN / AUTO / CLEAN / MANUAL, written by us before our own resets and by deploy/versions/role switch) AND
  `machine.reset_cause()`; the screen is lit only when both say "a person did it".
- **0.4.0** role switching: parent menu has ROLE (6 items); play mode got a button and a menu (VOLUME, SPEED, ROLE, EXIT);
  `config.save_role()` changes only the `role` key, keeps `config.json.bak`, writes `.new`, reads it back, renames
  (littlefs and FAT), `load()` falls back to `.new`; confirm step (hold = yes, tap = no) then restart marked MANUAL. Shared
  pieces in `lib/ui/menu.py`.
- **0.5.0** boot chooser: hold BOOT 2 s within a 3 s window after READY (hint on the screen) opens the role list before any
  role code runs (`lib/ui/chooser.py`); after 3 crashes in a row (counter in the RTC marker, reset by a stable minute) the
  chooser appears instead of starting the same role, **but never on the child unit**. Watchdog starts after the window.
- **0.6.0** child unit stays dark and silent after any automatic restart or crash loop (decision by the owner: the parent's
  "no link" alarm is the signal). A BOOT tap on the child's status screen shows how it started (`STARTED BY A PERSON`,
  `RESTART: CRASH X2`, ...); the child reports a restart code in every heartbeat and the parent shows amber
  `CHILD RESTARTED (Xn)` until a person restarts the child.

- **0.6.1 to 0.6.4** (first hardware test fixes): ready beep audible (amplifier lead-in), no-link alarm acknowledged by BOOT until
  the link changes, BOOT on the bell stops the voice, 3 quick taps switch the parent's sound off / on (remembered), WiFi
  recovery on the parent after the child restarted. **0.7.0**: roles renamed master/slave -> child/parent (old config.json
  names still read). Hardware test sections 1 to 10 passed; the real night (section 12) is next.

## Decisions to keep

- The child unit has no menu and never lights or beeps on its own (a toddler; do not change without asking).
- Button actions fire on release; hold = 1.2 s or more (start-up chooser: 2 s).
- Stability first: do not change child/parent behaviour without a reason; every new feature behind tests; say clearly what
  is not verified on hardware; never claim a fix works without the owner's report.
- Keep `docs/BEHAVIOUR.md` in step with every behaviour change (the owner cannot remember all the presses).

## Next

1. **Run `docs/HARDWARE_TEST.md`** on the two boards and send back the items marked **[send]**: the first-boot serial output of
   each board (`[boot] last run ended ... reset cause ... crashes in a row`), the `events.csv` boot lines, photos or notes of
   the start-up, status and six-item menu screens, and the crash-loop output.
2. Likely to need fixes after that: the screen layouts (never seen rendered), what each reset really reports and whether RTC
   memory survives them (decides whether the child stays dark), the 3 s chooser window, the play menu feel.
3. Then the real-world run (two nights + naps) with `--night`.
4. Later: step 4 child settings on the child unit (deliberate 3 s hold, confirm, timeout; only after the live test), step 5
   touch (FT3168 at I2C 0x38, pure-Python driver, same menu actions; BOOT must stay as fallback; update BEHAVIOUR.md).
5. Open data work: real recordings of the child (voice and snoring) for a pitch cue (200-450 Hz periodicity); the play mode
   collects voice clips, night clips of snoring still to be planned.

## Facts worth remembering

- Confirmed by the owner: the WiFi start fix cured `Wifi Internal State Error` on the parent.
- Hardware: I2C SDA 15 / SCL 14; I2S SCK 9, WS 45, DOUT 8, DIN 10; amp enable GPIO46; BOOT = GPIO0; TCA9554 at 0x20; AXP2101 at
  0x34. `disp_off/disp_on` break the panel on this firmware: hide with brightness 0. A screen draw takes 130-210 ms; the mic
  buffer holds about 150 ms, so nothing is drawn while recording. Holding BOOT during a reset enters download mode.
- Only `drivers/sh8601.py` and `ui/gfx.py` touch the custom `amoled` module. The font is 5x7 and has no lowercase, `*`, `(`
  or `)`; `+` was added.
- Parked ideas, not for now: Waveshare ESP32-S3-Touch-LCD-4.3C (800x480 RGB, needs a C driver in the firmware) and the
  S3-Touch-AMOLED-2.16 (CO5300 panel, untested in dobodu's firmware); stock MicroPython with a pure-Python panel driver.
- GitHub: this Claude workspace may only write to repositories in the trivago organisations. Do not push this repo or use the
  GitHub connector for it; edit locally, the owner commits and pushes.
