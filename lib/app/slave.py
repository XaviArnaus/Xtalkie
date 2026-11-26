# app/slave.py -- the parent unit: play what the master sends, and raise an alarm if the link is lost.
#
# Idle: no I2S, speaker amplifier off; the unit only listens on the network and sends a HELLO every
# second. When audio arrives it waits for a few frames (jitter buffer), switches the speaker on and
# plays; when the stream ends (END packet, or silence on the network) it switches the speaker off again.
# If no packet from the master arrives for link_timeout_ms the alarm beeps every alarm_period_ms.
import time

import version
from helpers import log, watchdog
from net import proto
from ui.hud import NullHud, volume_actions

SILENCE = bytes(640)
QUEUE_MAX = 200           # 4 s
HELLO_MS = 1000
UNDERRUN_STOP_MS = 600


def run(cfg, audio, net, hud=None):
    hud = hud or NullHud()
    sc = cfg["slave"]
    verbose = sc["verbose"]
    jitter = sc["jitter_frames"]
    link_timeout = sc["link_timeout_ms"]
    alarm_period = sc["alarm_period_ms"]
    my_version = version.full()
    gain = None                      # the audio object decides (automatic gain or fixed gain)
    master = net.master_addr

    queue = []
    end_flag = False
    playing = False
    expected = None
    lost = 0
    underruns = 0
    played = 0
    link_up = False
    last_hb = None
    master_state = None
    now = time.ticks_ms()
    last_hello = now - HELLO_MS
    last_alarm = now - alarm_period
    last_audio_rx = now
    last_status = now
    last_min = now
    hseq = 0
    cseq = 0
    test_seen = False
    stream_test = False
    t_start = now

    def _act_test(seconds):
        nonlocal cseq
        cseq += 1
        return net.send(proto.pack_cmd(cseq, proto.CMD_LIVE, seconds), master)

    sens_known = 3

    def _sens_step():
        nonlocal cseq, sens_known
        sens_known = sens_known % 5 + 1
        cseq += 1
        net.send(proto.pack_cmd(cseq, proto.CMD_SENS, sens_known), master)
        return sens_known

    hud.set_actions(test_live=_act_test, alarm_preview=lambda: audio.beep(),
                    sens_step=_sens_step, get_sens=lambda: sens_known, **volume_actions(audio))

    audio.close()
    print("[slave] waiting for the master")
    try:
        while True:
            watchdog.feed()
            now = time.ticks_ms()
            hud.tick(now)
            net.ensure()

            # ---- receive everything that is waiting ----
            for _ in range(10):
                r = net.recv()
                if r is None:
                    break
                info = proto.parse(r[0])
                if info is None:
                    continue
                ptype, flags, seq, body = info
                last_hb = now
                if not link_up:
                    link_up = True
                    print("[slave] link up")
                    log.write("slave", "link up")
                    hud.on_link(True)
                if ptype == proto.T_HB:
                    master_state = proto.parse_hb(body)
                    if master_state is not None:
                        hud.on_peer_status(master_state[2], master_state[3])
                        hud.on_peer_version(proto.parse_hb_version(body))
                        if master_state[4]:
                            sens_known = master_state[4]
                elif ptype == proto.T_AUDIO:
                    last_audio_rx = now
                    if flags & proto.F_TEST:
                        test_seen = True
                    if expected is not None:
                        gap = (seq - expected) & 0xFFFFFFFF
                        if gap >= 0x80000000:
                            continue                     # old or duplicate packet
                        if 0 < gap <= 5:
                            queue.extend([SILENCE] * gap)
                            lost += gap
                        elif gap > 5:
                            lost += gap
                            queue.append(SILENCE)
                    expected = (seq + 1) & 0xFFFFFFFF
                    queue.append(body)
                    if len(queue) > QUEUE_MAX:
                        del queue[:len(queue) - QUEUE_MAX]
                elif ptype == proto.T_END:
                    last_audio_rx = now
                    expected = (seq + 1) & 0xFFFFFFFF
                    end_flag = True

            # ---- say hello ----
            if time.ticks_diff(now, last_hello) >= HELLO_MS:
                last_hello = now
                hseq += 1
                bpct, bchg = hud.battery_info(now)
                net.send(proto.pack_hello(hseq, bpct, bchg, my_version), master)

            # ---- playback ----
            if not playing and queue and (len(queue) >= jitter or end_flag):
                audio.open_tx()
                audio.write_silence()
                audio.write_silence()
                audio.set_pa(True)
                playing = True
                last_audio_rx = now
                stream_test = test_seen
                test_seen = False
                if not stream_test:
                    hud.on_alert_start()
                if verbose:
                    print("[slave] playing%s (%d frames buffered)" % (" LIVE TEST" if stream_test else "", len(queue)))
            if playing:
                if queue:
                    frame_payload = queue.pop(0)
                    if stream_test:
                        hud.on_test_audio(proto.level_db(frame_payload))
                    audio.write_payload(frame_payload, gain)
                    played += 1
                elif end_flag or time.ticks_diff(now, last_audio_rx) > UNDERRUN_STOP_MS:
                    for _ in range(3):
                        audio.write_silence()
                    audio.set_pa(False)
                    audio.close()
                    playing = False
                    end_flag = False
                    expected = None
                    if stream_test:
                        hud.on_test_end()
                    else:
                        hud.on_alert_end()
                    stream_test = False
                    log.write("slave", "stream finished,played=%d,lost=%d,underruns=%d" % (played, lost, underruns))
                    if verbose:
                        print("[slave] stream finished (played=%d lost=%d underruns=%d)" % (
                            played, lost, underruns))
                else:
                    audio.write_silence()               # waiting for the next packet
                    underruns += 1
                continue

            # ---- idle: link supervision ----
            if link_up and last_hb is not None and time.ticks_diff(now, last_hb) > link_timeout:
                link_up = False
                print("[slave] LINK LOST")
                log.write("slave", "LINK LOST")
                hud.on_link(False)
                last_alarm = now - alarm_period          # alarm right away
            if not link_up and (last_hb is not None or sc["alarm_before_first_link"]):
                if time.ticks_diff(now, last_alarm) >= alarm_period and not hud.muted(now):
                    last_alarm = now
                    print("[slave] ALARM: no signal from the master")
                    log.write("slave", "alarm")
                    audio.beep()

            if time.ticks_diff(now, last_min) >= 60000:
                last_min = now
                bpct, bext = hud.battery_info(now)
                log.write("slave", "minute,link=%d,batt=%s,ext=%d,played=%d,lost=%d" % (
                    1 if link_up else 0, "?" if bpct is None else bpct, 1 if bext else 0, played, lost))

            if verbose and time.ticks_diff(now, last_status) >= 10000:
                last_status = now
                ms = "-" if master_state is None else ("gate %s, floor %.1f" % (
                    "OPEN" if master_state[0] else "closed", master_state[1]))
                print("[slave] %4ds link=%s master: %s  played=%d lost=%d" % (
                    time.ticks_diff(now, t_start) // 1000, "up" if link_up else "DOWN", ms, played, lost))

            time.sleep_ms(5)
    finally:
        audio.set_pa(False)
        audio.close()
