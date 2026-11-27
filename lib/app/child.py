# app/child.py -- the child-room unit: listen, decide with the gate, stream audio when it opens.
#
# Every 20 ms frame goes through Gate. The last RING frames are kept, so when the gate opens the
# audio from just before the alert (pre-roll) is sent first and no word is clipped. Packets go through
# a small queue that is drained a few per frame, so a pre-roll burst cannot overflow the parent's
# receive buffer. The parent's address is learned from its HELLO packets.
#
# In loopback mode (one board, no network) the "sent" packets are collected and, when the stream ends,
# played back on the speaker, so the whole send path can be tested on a single board.
import struct
import time

from dsp.gate import Gate
import version
from helpers import bootinfo, clock, config, log, patterns, watchdog
from helpers.nightclips import NightClips
from net import proto
from ui.hud import NullHud, volume_actions

# sensitivity level -> (activity threshold above the room floor in dB, limit for sharp sounds such as claps in dB)
SENS = {1: (20.0, 55.0), 2: (15.0, 48.0), 3: (12.0, 42.0), 4: (10.0, 38.0), 5: (8.0, 34.0)}

RING = 80                 # 1.6 s of pre-roll history
SKIP = 25                 # frames ignored after the mic stream starts (digital silence)
SEND_PER_FRAME = 4        # packets sent per 20 ms frame (1 live + up to 3 backlog)
OUTQ_MAX = 250
PEER_TIMEOUT_MS = 5000
STATUS_MS = 5000


def _loop_play(audio, packets, gain):
    """Loopback only: play the collected stream on the speaker, then go back to listening."""
    n = 0
    audio.open_tx()
    audio.write_silence()
    audio.set_pa(True)
    for raw in packets:
        watchdog.feed()
        info = proto.parse(raw)
        if info is None:
            continue
        if info[0] == proto.T_AUDIO:
            audio.write_payload(info[3], gain)
            n += 1
    for _ in range(3):
        audio.write_silence()
    audio.set_pa(False)
    audio.open_rx()
    return n


def run(cfg, audio, net, hud=None):
    hud = hud or NullHud()
    mc = cfg["child"]
    verbose = mc["verbose"]
    lead = mc["preroll_lead_ms"] // 20
    hb_ms = mc["hb_ms"]
    loop = hasattr(net, "take")
    my_version = version.full()
    my_restart = bootinfo.restart_code()       # 0 = a person started this run, n > 0 = it restarted by itself
    gate = Gate(frame_ms=20, **cfg["gate"])
    gate.stamper = clock.stamp
    lcfg = cfg.get("learning", {})
    pat_path = lcfg.get("path", patterns.PATH)
    persist = bool(lcfg.get("persist", True)) and not loop
    save_ms = int(lcfg.get("save_every_s", 300)) * 1000
    if persist:
        n_loaded = gate.load(patterns.load(pat_path))
        print("[child] %d snore pattern(s) loaded" % n_loaded)
        log.write("child", "patterns loaded,n=%d" % n_loaded)
    nc = None
    ncfg = cfg.get("nightclips", {})
    if ncfg.get("enabled") and bootinfo.crashes() >= 2:
        print("[clips] night clips NOT started: %d crashes in a row (a crash loop must not be made worse)" % bootinfo.crashes())
        log.write("child", "night clips not started,crashes=%d" % bootinfo.crashes())
    elif ncfg.get("enabled"):
        try:
            nc = NightClips(folder=ncfg.get("folder", "/night"), budget=ncfg["budget"], min_free=ncfg["min_free"],
                            window_s=ncfg["window_s"], window_every_s=ncfg["window_every_s"],
                            max_files=ncfg["max_files"], min_gap_s=ncfg["min_gap_s"])
            print("[clips] night clips ON: %d KB kept at most, %d files now" % (ncfg["budget"] // 1024, len(nc.files)))
            log.write("child", "night clips on,files=%d" % len(nc.files))
        except Exception as e:
            nc = None
            print("[clips] night clips could not start:", e)

    sens = min(5, max(1, int(config.state_load().get("sens_level", mc["sens_level"]))))

    def apply_sens(level):
        nonlocal sens
        sens = min(5, max(1, int(level)))
        gate.act_db, gate.impact_db = SENS[sens]
        config.state_save("sens_level", sens)
        return sens

    gate.act_db, gate.impact_db = SENS[sens]
    max_open_ms = mc["max_open_s"] * 1000
    cooldown_ms = mc["cooldown_s"] * 1000
    open_since = 0
    lockout_until = None

    ring = [None] * RING
    w = 0
    outq = []
    seq = 0
    hbseq = 0
    peer = net.peer if loop else None
    now = time.ticks_ms()
    last_hello = now
    last_hb = now
    last_status = now
    streaming = False
    end_pending = False
    live_until = None
    learned_seen = 0
    last_save = now
    n_ignored = 0
    n_alerted = 0
    last_min = now
    worst_us = 0
    frame = 0
    sent = 0
    opens = 0

    if loop:
        hud.on_link(True)
        hud.set_actions(alarm_preview=lambda: audio.beep(), **volume_actions(audio))
        hud.set_actions(sens_step=lambda: apply_sens(sens % 5 + 1), get_sens=lambda: sens)
    audio.open_rx()
    print("[child] listening%s" % (" (loopback test)" if loop else ""))
    try:
        while True:
            payload, lvl, zcr = audio.read_frame()
            t_proc = time.ticks_us()
            watchdog.feed()
            now = time.ticks_ms()
            hud.tick(now)
            bootinfo.stable_check(now)             # after a minute of running, a crash loop is over
            frame += 1
            if frame <= SKIP:
                continue

            ring[w] = payload
            cur = w
            w = (w + 1) % RING

            if nc is not None:
                nc.feed(payload)
            ev = gate.update(lvl, zcr)
            if gate.ended and gate.last_event is not None:
                st_s, d_s, pk, mn, z, verdict = gate.last_event
                if d_s >= 0.08 or verdict.startswith("ALERT"):
                    if verbose:
                        print("  .  event %.1f s long, peak %.1f, zcr %s -> %s" % (
                            d_s, pk, ("%d" % z) if z is not None else "-", verdict))
                    if verdict.startswith("ignored (snore"):
                        n_ignored += 1
                    elif not verdict.startswith("ignored") and not verdict.startswith("noise"):
                        n_alerted += 1
                        log.write("child", "event,%.2f,%.1f,%.1f,%s,%s" % (
                            d_s, pk, mn, ("%d" % z) if z is not None else "-", verdict))
                if nc is not None and d_s >= 0.08:
                    alerted = not verdict.startswith("ignored") and not verdict.startswith("noise")
                    nc.event(d_s, pk, mn, z, verdict, alerted, worthy=not verdict.startswith("noise"))

            if gate.learned != learned_seen:
                learned_seen = gate.learned
                q = gate.patterns[-1]
                log.write("child", "pattern learned,n=%d,dur=%.2f,peak=%.1f,mean=%.1f,zcr=%s,iv=%.1f" % (
                    len(gate.patterns), q["dur"], q["peak"], q["mean"], "-" if q["zcr"] is None else "%d" % q["zcr"], q["iv"]))
                if verbose:
                    print("--- learned snore pattern #%d: %.1f s bursts, peak %.1f dB, every %.1f s ---" % (
                        len(gate.patterns), q["dur"], q["peak"], q["iv"]))
            if persist and gate.pat_dirty and (learned_seen and time.ticks_diff(now, last_save) >= 5000
                                               or time.ticks_diff(now, last_save) >= save_ms):
                last_save = now
                gate.pat_dirty = not patterns.save(gate.export(), pat_path)
            forced = live_until is not None and time.ticks_diff(live_until, now) > 0
            if live_until is not None and not forced:     # a live test just ended
                live_until = None
                if not streaming:
                    outq.append(proto.pack(proto.T_END, seq))
                    seq += 1
            locked = lockout_until is not None and time.ticks_diff(lockout_until, now) > 0
            if lockout_until is not None and not locked:
                lockout_until = None
                if gate.gate_open and not streaming:        # the sound is still going on after the pause
                    streaming = True
                    open_since = now
                    log.write("child", "resume after pause")
            if ev == "open":
                opens += 1
                if not locked:
                    n = min(RING - 2, gate.onset_ms_ago // 20 + lead)
                    for k in range(n, 0, -1):
                        p = ring[(cur - k) % RING]
                        if p is not None:
                            outq.append(proto.pack(proto.T_AUDIO, seq, p, proto.F_PREROLL))
                            seq += 1
                    streaming = True
                    open_since = now
                    if loop:
                        hud.on_alert_start()
                    if verbose:
                        print("*** OPEN (%s), %d pre-roll frames" % (gate.reason, n))
                log.write("child", "open,%s%s" % (gate.reason, ",paused" if locked else ""))
            if streaming and time.ticks_diff(now, open_since) > max_open_ms:
                streaming = False                             # too long: probably the speaker feeding the mic
                outq.append(proto.pack(proto.T_END, seq))
                seq += 1
                lockout_until = time.ticks_add(now, cooldown_ms)
                print("[child] stream longer than %d s: paused %d s (feedback?)" % (max_open_ms // 1000, cooldown_ms // 1000))
                log.write("child", "stream cut after max_open")
            if streaming or forced:
                outq.append(proto.pack(proto.T_AUDIO, seq, payload, proto.F_TEST if forced else 0))
                seq += 1
            if ev == "close":
                if streaming:
                    outq.append(proto.pack(proto.T_END, seq))
                    seq += 1
                    streaming = False
                end_pending = True
                if loop:
                    hud.on_alert_end()
                if verbose:
                    print("*** CLOSE")

            # ---- network ----
            if not loop:
                net.ensure()
                for _ in range(4):
                    r = net.recv()
                    if r is None:
                        break
                    info = proto.parse(r[0])
                    if info is not None and info[0] == proto.T_HELLO:
                        if peer != r[1]:
                            print("[child] parent found at %s:%d" % r[1])
                            log.write("child", "parent found")
                        peer = r[1]
                        last_hello = now
                        pb = proto.parse_hello(info[3])
                        hud.on_peer_status(pb[0], pb[1])
                        hud.on_peer_version(proto.parse_hello_version(info[3]))
                        hud.on_link(True)
                    elif info is not None and info[0] == proto.T_CMD:
                        cmd, arg = proto.parse_cmd(info[3])
                        if cmd == proto.CMD_LIVE:
                            live_until = time.ticks_add(now, min(max(arg, 1), 60) * 1000)
                            print("[child] live test for %d s" % min(max(arg, 1), 60))
                            log.write("child", "live test")
                        elif cmd == proto.CMD_SENS and 1 <= arg <= 5:
                            apply_sens(arg)
                            print("[child] sensitivity level %d (threshold %.0f dB, sharp-sound limit %.0f dB)" % (
                                sens, gate.act_db, gate.impact_db))
                            log.write("child", "sensitivity %d" % sens)
                if peer is not None and time.ticks_diff(now, last_hello) > PEER_TIMEOUT_MS:
                    print("[child] parent lost")
                    log.write("child", "parent lost")
                    peer = None
                    hud.on_link(False)
                if peer is None and outq:
                    del outq[:]                       # nobody listening: do not keep stale audio

            budget = SEND_PER_FRAME if not loop else 10000
            while outq and peer is not None and budget > 0:
                if net.send(outq[0], peer):
                    outq.pop(0)
                    sent += 1
                    budget -= 1
                else:
                    break
            if len(outq) > OUTQ_MAX:
                del outq[:len(outq) - OUTQ_MAX]

            if peer is not None and time.ticks_diff(now, last_hb) >= hb_ms:
                last_hb = now
                hbseq += 1
                bpct, bchg = hud.battery_info(now)
                net.send(proto.pack_hb(hbseq, gate.gate_open, gate.floor_db, bpct, bchg, sens, my_version, my_restart), peer)

            if loop and end_pending and not outq:
                end_pending = False
                pk = net.take()
                n = _loop_play(audio, pk, None)
                print("[child] loopback: played back %d frames" % n)
                frame = 0                              # skip the mic start-up silence again

            if time.ticks_diff(now, last_min) >= 60000 and gate.floor_db is not None:
                last_min = now
                bpct, bext = hud.battery_info(now)
                log.write("child", "minute,ignored=%d,alerts=%d,floor=%.1f,regime=%d,peer=%d,batt=%s,ext=%d" % (
                    n_ignored, n_alerted, gate.floor_db, 1 if gate.regime else 0, 0 if peer is None else 1,
                    "?" if bpct is None else bpct, 1 if bext else 0) + ",patterns=%d" % len(gate.patterns) + (nc.minute() if nc is not None else ""))
                n_ignored = 0
                n_alerted = 0

            dt_us = time.ticks_diff(time.ticks_us(), t_proc)
            if dt_us > worst_us:
                worst_us = dt_us

            if time.ticks_diff(now, last_status) >= STATUS_MS and gate.floor_db is not None:
                last_status = now
                print("[child] %4ds  %6.1f dB  floor %6.1f  %-6s opens=%d sent=%d q=%d peer=%s  frame<=%dms" % (
                    frame // 50, lvl, gate.floor_db, gate.state_name, opens, sent, len(outq),
                    "-" if peer is None else ("%s" % (peer[0],)), worst_us // 1000))
                worst_us = 0
    finally:
        if persist and gate.pat_dirty:
            patterns.save(gate.export(), pat_path)
        audio.close()
