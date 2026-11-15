"""
CAN izleyicisinin birim testleri (STM32 zaman çizelgesiyle: alım 100 ms'de bir, değerlendirme 10 ms'de bir)
+ MATLAB ve C için test vektörleri + kısa kapalı çevrim kontrolü.

Testlerin olay dizisi (rx / tick) ve Python çıktıları simulink/can_monitor_vectors.csv'ye yazılır;
simulink/test_can_monitor.m aynı olayları can_monitor_*.m'ye verip çıktıların birebir aynı olduğunu
doğrular (aynı vektörler STM32'nin bms_can.c'si ile de karşılaştırılabilir).
"""
import os
import numpy as np
import pandas as pd
from can_monitor import CanMonitor, T_FIRST_MS

HERE = os.path.dirname(os.path.abspath(__file__))
RX, TICK = 1, 2
rows, results = [], []


def run(test_id, frames, t_end_ms, rx_offset_ms=3):
    """frames: {ms: (crc_ok, counter)} -> alım olayları; her 10 ms'de bir tick. Olay listesini döndürür."""
    mon = CanMonitor(0)
    ev = []
    for t in range(0, t_end_ms + 1):
        if t in frames:
            crc_ok, cnt = frames[t]
            ok = mon.rx(t, crc_ok, cnt)
            ev.append((RX, t, crc_ok, cnt, ok))
        if t % 10 == 0:
            mon.tick(t)
            ev.append((TICK, t, 0, 0, 0))
    # olayları yeniden oynatıp çıktı sütunlarıyla kaydet (aynı sıra)
    mon = CanMonitor(0)
    out = []
    for i, (op, t, crc_ok, cnt, _) in enumerate(ev):
        ok = mon.rx(t, crc_ok, cnt) if op == RX else (mon.tick(t) or False)
        r = dict(test=test_id, reset=int(i == 0), op=op, now_ms=t, crc_ok=int(crc_ok), counter=cnt,
                 ok=int(ok), fault=int(mon.fault), safe=int(mon.safe), n_ok=mon.n_ok,
                 n_crc_err=mon.n_crc_err, n_cnt_err=mon.n_cnt_err, n_lost=mon.n_lost)
        rows.append(r)
        out.append(r)
    return pd.DataFrame(out)


def stream(t_from, t_to, period=100, offset=3, crc=True, counter0=0, skip=()):
    """t_from..t_to arasında periyodik çerçeveler; skip içindeki sıra numaraları hatta yok (sayaç yine artar)."""
    f = {}
    for i, t in enumerate(range(t_from + offset, t_to, period)):
        if i not in skip:
            f[t] = (crc, (counter0 + i) % 16)
    return f


def first(df, col):
    k = df.index[(df[col] == 1)]
    return int(df.now_ms[k[0]]) if len(k) else None


def check(i, name, ok, info):
    results.append((i, name, ok))
    print(f"U{i:<2} {name:<46} {'PASS' if ok else 'FAIL'}   {info}")


# U1 normal akış: hiç arıza yok
d = run(1, stream(0, 3000), 3000)
check(1, "normal 100 ms stream", d.fault.max() == 0 and d.safe.max() == 0 and d.n_ok.iloc[-1] == 30,
      f"{d.n_ok.iloc[-1]} frames accepted, no fault")

# U2 2 çerçeve kaybı (son geçerli 903 ms): dönüş çerçevesi sayaç farkı 3 -> kabul, 2 kayıp sayılır
d = run(2, stream(0, 3000, skip=range(10, 12)), 3000)
check(2, "2 lost frames -> fault, accepted on return", d.fault.max() == 1 and d.safe.max() == 0
      and d.n_lost.iloc[-1] == 2 and d.fault.iloc[-1] == 0,
      f"fault at {first(d, 'fault')} ms (last valid 903 ms), lost {d.n_lost.iloc[-1]}, cleared afterwards")

# U3 3 çerçeve kaybı: dönüş çerçevesi (1303 ms) fark 4 > 3 -> dizi hatası, red; sonraki (1403 ms) kabul.
#    1400 ms'deki tick'te yaş 497 ms < 500 -> SAFE yok (sınırda)
d = run(3, stream(0, 3000, skip=range(10, 13)), 3000)
check(3, "3 lost frames -> return frame rejected, no SAFE", d.safe.max() == 0 and d.n_cnt_err.iloc[-1] == 1,
      f"fault at {first(d, 'fault')} ms, sequence errors {d.n_cnt_err.iloc[-1]}, no SAFE (age 497 ms at 1400 ms)")

# U9 4 çerçeve kaybı: dönüş çerçevesi (1403 ms) fark 5 > 3 -> red, 1410 ms'de yaş 507 -> SAFE.
#    Yani MAX_DELTA = 3 ile pratikte 4 ardışık kayıp SAFE-STOP'a götürür (5 değil).
d = run(9, stream(0, 3000, skip=range(10, 14)), 3000)
check(9, "4 lost frames -> return rejected -> SAFE", first(d, "safe") == 1410 and d.n_cnt_err.iloc[-1] == 1,
      f"SAFE at {first(d, 'safe')} ms (return frame 1403 ms rejected: counter delta 5 > MAX_DELTA 3)")

# U10 5 çerçeve kaybı: SAFE son geçerliden 500 ms sonra (ilk tick), mesajlar dönse de kalıcı
d = run(10, stream(0, 3000, skip=range(10, 15)), 3000)
check(10, "5 lost frames -> SAFE, latched", first(d, "safe") == 1410 and d.safe.iloc[-1] == 1,
      f"SAFE at {first(d, 'safe')} ms (last valid 903 ms + 500 -> tick 1410), stays after frames resume")

# U4 açılış: hiç mesaj yok -> SAFE tam 2000 ms'de, öncesinde fault bile yok
d = run(4, {}, 3000)
check(4, "startup, no frames -> SAFE at 2000 ms", first(d, "safe") == T_FIRST_MS and first(d, "fault") == T_FIRST_MS,
      f"SAFE at {first(d, 'safe')} ms")

# U5 ilk mesaj 1903 ms'de (açılış süresi içinde) -> SAFE yok; sonra kesilirse 500 ms kuralı
d = run(5, stream(1900, 2600), 4000)
check(5, "late first frame accepted, then 500 ms rule", first(d, "safe") == 3010 and d.n_ok.iloc[-1] == 7,
      f"first frame 1903 ms, last 2503 ms, SAFE at {first(d, 'safe')} ms")

# U6 baştan CRC'si bozuk çerçeveler: açılış süresini uzatmaz -> SAFE 2000 ms
d = run(6, stream(0, 3000, crc=False), 3000)
check(6, "CRC errors do not extend startup grace", first(d, "safe") == T_FIRST_MS and d.n_crc_err.iloc[-1] == 30,
      f"SAFE at {first(d, 'safe')} ms, CRC errors {d.n_crc_err.iloc[-1]}")

# U7 1 s'den sonra donmuş sayaç (hep 10): 1003 ms'deki çerçeve zaten 10 -> son geçerli; sonrası red
f = stream(0, 3000)
for t in f:
    if t > 1000:
        f[t] = (True, 10)
d = run(7, f, 3000)
check(7, "frozen alive counter -> SAFE", first(d, "safe") == 1510 and d.n_cnt_err.iloc[-1] > 0,
      f"SAFE at {first(d, 'safe')} ms, counter errors {d.n_cnt_err.iloc[-1]}")

# U8 sayaç atlaması: fark 3 kabul (2 kayıp sayılır), fark 6 dizi hatası (red, sonra yeniden eşitlenir)
f = {3: (True, 0), 103: (True, 1), 203: (True, 4), 303: (True, 10), 403: (True, 11), 503: (True, 12)}
d = run(8, f, 1000)
rx = d[d.op == RX]
check(8, "counter jump: delta 3 accepted, 6 rejected", list(rx.ok) == [1, 1, 1, 0, 1, 1] and d.n_lost.iloc[-1] == 2
      and d.n_cnt_err.iloc[-1] == 1, f"accepted {list(rx.ok)}, lost {d.n_lost.iloc[-1]}, sequence errors {d.n_cnt_err.iloc[-1]}")

V = pd.DataFrame(rows)
V.to_csv(os.path.join(HERE, "..", "simulink", "can_monitor_vectors.csv"), index=False)

# ---------------------------------------------------------------- kapalı çevrim (kısa sürüş)
from closed_loop import run as cl_run
I_dem = 30 + 20 * np.sin(np.arange(1200) * 0.1 / 20)          # 120 s
base = cl_run(I_dem, soc0=0.8)
# beklenen SAFE-STOP anı [s] (None = olmamalı); son geçerli mesaj 59.9 s
cases = [("C1 0x101 lost 0.3 s", dict(mode=1, msg=1, t=60.0, dur=0.3), None),
         ("C2 0x101 lost 0.4 s (return rejected)", dict(mode=1, msg=1, t=60.0, dur=0.4), 60.4),
         ("C3 0x101 lost 0.5 s", dict(mode=1, msg=1, t=60.0, dur=0.5), 60.4),
         ("C4 0x102 CRC corrupted", dict(mode=2, msg=2, t=60.0, dur=np.inf), 60.4),
         ("C5 0x101 frozen counter", dict(mode=3, msg=1, t=60.0, dur=np.inf), 60.5),   # 60.0 s'deki çerçeve
         ("C6 no frames from power-up", dict(mode=1, msg=3, t=0.0, dur=np.inf), 2.0)]  # zaten doğru sayaç
print()
i_cl = 11
for name, can, t_safe in cases:
    r = cl_run(I_dem, soc0=0.8, can=can)
    k = np.flatnonzero(r.state.values == 4)
    t_s = float(r.t[k[0]]) if len(k) else None
    ok = (t_s is None and t_safe is None and r.can_fault.max() > 0) or \
         (t_s is not None and t_safe is not None and abs(t_s - t_safe) < 1e-9 and r.i_dis.values[k[0]] == 0
          and (r.state.values[k[0]:] == 4).all())
    check(i_cl, name, ok, f"SAFE-STOP at {t_s} s (expected {t_safe}), fault flag max {int(r.can_fault.max())}")
    i_cl += 1
check(i_cl, "no CAN fault: CAN_ok = 1, no fault flag", base.can_ok.min() == 1 and base.can_fault.max() == 0
      and (base.state.values != 4).all(), "")

n_ok = sum(r[2] for r in results)
print(f"\n{n_ok}/{len(results)} tests passed. Test vectors: simulink/can_monitor_vectors.csv ({len(V)} rows)")
