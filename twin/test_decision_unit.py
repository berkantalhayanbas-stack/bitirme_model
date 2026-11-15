"""
Karar mekanizmasının birim testleri (ikiz yok, sentetik girdiler) + MATLAB için test vektörleri.

Her test, karar mekanizmasına doğrudan bir girdi dizisi verir ve beklenen davranışı kontrol eder.
Tüm testlerin girdileri ve Python çıktıları simulink/decision_vectors.csv'ye yazılır;
simulink/test_decision.m aynı girdileri decision_logic.m'ye verip çıktıların birebir aynı
olduğunu doğrular (MATLAB ile Python mantığının eşdeğerliği, SIL testinin ön adımı).
"""
import os
import numpy as np
import pandas as pd
from decision import Decision, NAMES

HERE = os.path.dirname(os.path.abspath(__file__))
TS = 0.1
COLS = ["I_meas", "V_min", "V_max", "Tc_hat", "Ts_hat", "Ru_hat", "SOC_est", "bias_est",
        "T_valid", "I_valid", "CAN_ok"]
BASE = dict(I_meas=20.0, V_min=3.65, V_max=3.70, Tc_hat=30.0, Ts_hat=29.0, Ru_hat=9.0,
            SOC_est=0.6, bias_est=0.5, T_valid=1, I_valid=1, CAN_ok=1)
rows, results = [], []


def seq(n, **over):
    """n örneklik sabit girdi; over ile istenen sütunlar dizi veya sabit olarak değiştirilir."""
    d = {k: np.full(n, float(v)) for k, v in BASE.items()}
    for k, v in over.items():
        d[k] = np.broadcast_to(np.asarray(v, float), (n,)).copy()
    return d


def run(test_id, inp):
    dec = Decision()
    n = len(inp["I_meas"])
    out = np.zeros((n, 5))
    for k in range(n):
        out[k] = dec.step(*[inp[c][k] for c in COLS])
        rows.append(dict(test=test_id, reset=int(k == 0), **{c: inp[c][k] for c in COLS},
                         state=out[k, 0], i_dis=out[k, 1], i_chg=out[k, 2], psi=out[k, 3], cause=out[k, 4]))
    return out


def check(test_id, name, ok, detail):
    results.append((test_id, name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] U{test_id} {name}: {detail}")


# U1 açılış rampası: 0'dan başlar, en fazla 10 A/s artar, NORMAL'de 87.3 A'ya ulaşır
o = run(1, seq(150))
d = np.diff(o[:, 1])
check(1, "start-up ramp", o[0, 1] <= 1.0 + 1e-9 and d.max() <= 1.0 + 1e-9 and abs(o[-1, 1] - 87.3) < 1e-6
      and (o[:, 0] == 1).all(), f"I_allow 0 -> {o[-1, 1]:.1f} A in {np.argmax(o[:, 1] >= 87.3) * TS:.1f} s, max step {d.max():.2f} A")

# U2 SAFE-STOP kilidi: T_core bir örnek 61 °C -> SAFE, sonra 25 °C olsa da SAFE ve I_allow = 0
tc = np.full(200, 30.0); tc[120] = 61.0
o = run(2, seq(200, Tc_hat=tc))
check(2, "SAFE-STOP latch", o[120, 0] == 4 and (o[120:, 0] == 4).all() and (o[120:, 1:3] == 0).all(),
      f"state after spike: {NAMES[int(o[120, 0])]}, still {NAMES[int(o[-1, 0])]} 8 s later, I_allow {o[-1, 1]:.0f} A")

# U3 alçak gerilim sert sınırı süre filtresi: 0.5 s altında kalmak SAFE yapmaz, 1.0 s yapar
v = np.full(300, 3.6); v[100:105] = 2.45; v[200:211] = 2.45
o = run(3, seq(300, V_min=v))
check(3, "under-voltage duration filter", (o[100:200, 0] != 4).all() and o[209, 0] == 4 and o[208, 0] != 4,
      f"0.5 s dip -> {NAMES[int(o[150, 0])]}, 1.0 s dip -> SAFE-STOP at t = {np.argmax(o[:, 0] == 4) * TS:.1f} s")

# U4 sıcaklık histerezisi: 45 °C civarında gürültülü salınım durumu titreştirmez
rng = np.random.default_rng(3)
tc = np.concatenate([np.linspace(40, 45.3, 600), 45 + 0.3 * np.sin(np.arange(1200) * 0.2)
                     + 0.1 * rng.standard_normal(1200), np.linspace(45, 40, 600)])
o = run(4, seq(len(tc), Tc_hat=tc))
tr = int(np.sum(np.diff(o[:, 0]) != 0))
k_in = np.argmax(o[:, 0] == 2)
k_out = len(o) - np.argmax(o[::-1, 0] == 2)
check(4, "thermal hysteresis (no chatter)", tr == 2,
      f"{tr} transitions; DERATE entered at T = {tc[k_in]:.2f} °C, left at T = {tc[min(k_out, len(tc) - 1)]:.2f} °C")

# U5 derating eğrisi: 43 °C -> Ψ 0, 49 °C -> Ψ 0.5, 55 °C -> Ψ 1 (ama LIMP tabanı > 55 °C'de)
for T, psi_exp in ((47.0, (47 - 43) / 12), (49.0, 0.5)):
    tc = np.concatenate([np.linspace(30, T, 300), np.full(300, T)])
    o = run(5, seq(len(tc), Tc_hat=tc))
    check(5, f"derating at {T:.0f} °C", abs(o[-1, 3] - psi_exp) < 1e-6 and o[-1, 0] == 2,
          f"psi {o[-1, 3]:.3f} (expected {psi_exp:.3f}), I_allow {o[-1, 1]:.1f} A")

# U6 sensör arızası -> LIMP-HOME anında, taban akım %25 (21.8 A), bayrak kalıcı olduğundan sürer
tv = np.ones(400); tv[200:] = 0
o = run(6, seq(400, T_valid=tv))
check(6, "sensor fault -> LIMP-HOME", o[200, 0] == 3 and abs(o[201, 1] - 21.825) < 1e-6 and (o[200:, 0] == 3).all(),
      f"state {NAMES[int(o[200, 0])]} at fault sample, I_allow {o[201, 1]:.2f} A")

# U7 akım kayması makullüğü: |b| > 5 A -> akım sensörü şüpheli -> LIMP-HOME
b = np.full(300, 0.5); b[150:] = -11.0
o = run(7, seq(300, bias_est=b))
check(7, "implausible bias -> LIMP-HOME", o[150, 0] == 3, f"state {NAMES[int(o[150, 0])]} when bias = -11 A")

# U8 CAN kesintisi -> SAFE-STOP
c = np.ones(200); c[150:] = 0
o = run(8, seq(200, CAN_ok=c))
check(8, "CAN timeout -> SAFE-STOP", o[150, 0] == 4 and o[150, 1] == 0, f"state {NAMES[int(o[150, 0])]}")

# U9 soğuk hücre: 5 °C'de deşarj 0.5C (29.1 A), şarj 0 (0 °C altı değil ama 0-2 °C geçişte değil: 5 °C -> 0.3C)
o = run(9, seq(300, Tc_hat=6.0, Ts_hat=5.0))
check(9, "cold-cell datasheet limits", abs(o[-1, 1] - 29.1) < 1e-6 and abs(o[-1, 2] - 17.46) < 1e-6 and o[-1, 0] == 2,
      f"I_allow dis {o[-1, 1]:.2f} A (0.5C), chg {o[-1, 2]:.2f} A (0.3C)")

# U10 soğutma alarmı -> Ψ = 0.3 önleyici derating (sıcaklık yükselmeden)
ru = np.full(300, 9.0); ru[100:] = 25.0
o = run(10, seq(300, Ru_hat=ru))
check(10, "cooling alarm -> pre-emptive derate", o[-1, 0] == 2 and abs(o[-1, 1] - 0.7 * 87.3) < 1e-6,
      f"I_allow {o[-1, 1]:.2f} A (70 %)")

# U11 derate'den çıkış: neden kalkınca 10 s bekler, sonra en fazla 10 A/s ile artar
ru = np.full(500, 25.0); ru[200:] = 9.0
o = run(11, seq(500, Ru_hat=ru))
k_n = np.argmax(o[200:, 0] == 1) + 200
check(11, "derate exit delay and ramp", abs((k_n - 200 + 1) * TS - 10.0) < 1e-6 and np.diff(o[:, 1]).max() <= 1.0 + 1e-9,
      f"NORMAL after {(k_n - 200 + 1) * TS:.1f} s (100 samples without cause), max increase {np.diff(o[:, 1]).max() * 10:.1f} A/s")

V = pd.DataFrame(rows)
V.to_csv(os.path.join(HERE, "..", "simulink", "decision_vectors.csv"), index=False)
n_ok = sum(r[2] for r in results)
print(f"\n{n_ok}/{len(results)} unit tests passed. Test vectors: simulink/decision_vectors.csv ({len(V)} rows)")
