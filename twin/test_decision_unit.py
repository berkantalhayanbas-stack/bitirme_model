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
        "T_valid", "I_valid", "CAN_ok", "T_meas", "T_amb", "T_anom"]
BASE = dict(I_meas=20.0, V_min=3.65, V_max=3.70, Tc_hat=30.0, Ts_hat=29.0, Ru_hat=9.0,
            SOC_est=0.6, bias_est=0.5, T_valid=1, I_valid=1, CAN_ok=1, T_meas=29.0, T_amb=25.0,
            T_anom=0)
rows, results = [], []


def seq(n, **over):
    """n örneklik sabit girdi; over ile istenen sütunlar dizi veya sabit olarak değiştirilir."""
    d = {k: np.full(n, float(v)) for k, v in BASE.items()}
    for k, v in over.items():
        d[k] = np.broadcast_to(np.asarray(v, float), (n,)).copy()
    return d


N_ZERO = 10      # açılış sıfır akım kontrolü (A9): kontaktör açık, I_allow = 0


def run(test_id, inp, i_zero=0.0):
    """Her testin önüne N_ZERO örneklik açılış kontrolü eklenir (ilk örneğin girdileri, ölçülen
    akım i_zero: kontaktör açıkken akım kesin 0, ölçülen = sensör ofseti). Dönen çıktı bu örnekleri
    içermez (testlerin zaman indeksleri değişmez); test vektörlerine ise girer."""
    dec = Decision()
    pre = {c: np.full(N_ZERO, inp[c][0]) for c in COLS}
    pre["I_meas"][:] = i_zero
    full = {c: np.concatenate([pre[c], inp[c]]) for c in COLS}
    n = len(full["I_meas"])
    out = np.zeros((n, 5))
    for k in range(n):
        out[k] = dec.step(*[full[c][k] for c in COLS])
        rows.append(dict(test=test_id, reset=int(k == 0), **{c: full[c][k] for c in COLS},
                         state=out[k, 0], i_dis=out[k, 1], i_chg=out[k, 2], psi=out[k, 3], cause=out[k, 4]))
    run.pre = out[:N_ZERO]
    return out[N_ZERO:]


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

# U10 soğutma alarmı -> Ψ = 0.3 önleyici derating (sıcaklık yükselmeden); açılış beklemesi (120 s) sonrası
ru = np.full(1500, 9.0); ru[1300:] = 25.0
o = run(10, seq(1500, Ru_hat=ru))
check(10, "cooling alarm -> pre-emptive derate", o[1299, 0] == 1 and (int(o[1300, 4]) & 2) and o[-1, 0] == 2
      and abs(o[-1, 1] - 0.7 * 87.3) < 1e-6, f"I_allow {o[-1, 1]:.2f} A (70 %)")

# U11 derate'den çıkış: neden kalkınca 10 s bekler, sonra en fazla 10 A/s ile artar
ru = np.full(1700, 25.0); ru[1400:] = 9.0
o = run(11, seq(1700, Ru_hat=ru))
k_n = np.argmax(o[1400:, 0] == 1) + 1400
check(11, "derate exit delay and ramp", o[1399, 0] == 2 and abs((k_n - 1400 + 1) * TS - 10.0) < 1e-6
      and np.diff(o[:, 1]).max() <= 1.0 + 1e-9,
      f"NORMAL after {(k_n - 1400 + 1) * TS:.1f} s (100 samples without cause), max increase {np.diff(o[:, 1]).max() * 10:.1f} A/s")

# U12 soğutma alarmı histerezisi: R_u kestirimi 18 K/W çevresinde dalgalanırken (HIL'de görüldü,
# yakınsama sırasında) alarm titremez; 15 K/W altına inince kalkar
ru = np.concatenate([np.linspace(9, 18.5, 300), 18 + 1.2 * np.sin(np.arange(1500) * 0.05)
                     + 0.2 * rng.standard_normal(1500), np.linspace(18, 9, 300), np.full(200, 9.0)])
o = run(12, seq(len(ru), Ru_hat=ru))
cool = (o[:, 4].astype(int) & 2) > 0
tr = int(np.sum(np.diff(cool.astype(int)) != 0))
k_off = np.argmax(~cool[1800:]) + 1800
check(12, "cooling alarm hysteresis (no chatter)", tr == 2 and cool[1799] and ru[k_off] < 15.0 and ru[k_off - 1] >= 15.0,
      f"{tr} alarm transitions; on at R_u = {ru[np.argmax(cool)]:.2f}, off at R_u = {ru[k_off]:.2f} K/W")

# U13 açılış beklemesi: gözlemci sıcak/yüklü pakette başlayınca R_u kestirimi geçici olarak fırlar
# (HIL'de bulundu; Python taramasında sağlam soğutmada 32 başlangıcın 21'inde sahte alarm, sonuncusu
# < 60 s). İlk 120 s alarm yok; gerçek arıza sonrasında yine yakalanır.
ru = np.concatenate([9 + 22 * np.exp(-np.arange(900) / 150.0) * (1 + 0.3 * np.sin(np.arange(900) * 0.1)),
                     np.full(600, 9.0), np.full(600, 36.0)])
o = run(13, seq(len(ru), Ru_hat=ru))
cool = (o[:, 4].astype(int) & 2) > 0
check(13, "start-up blanking of cooling alarm", not cool[:1500].any() and cool[1500:].any() and ru[:300].max() > 25,
      f"start transient R_u up to {ru[:900].max():.1f} K/W -> no alarm; real fault (36 K/W) at t = 150 s -> alarm")

# U14 ölçüme bağlı çekirdek sınırı (A1, HIL 3. bulgu): gözlemci modellenmemiş ısıyı görmez
# (Tc_hat 30 °C'de kalır); yüzey ölçümü 0,5 °C/s yükselir. T_ss = Tm + 0,2 (Tm - 25) > 55 °C
# -> LIMP (neden 1), > 60 °C -> SAFE; 1 s süre filtresi: 0,5 s'lik sıçrama tetiklemez; sensör
# geçersizse (T_valid = 0) ölçüm kullanılmaz.
tm = np.concatenate([np.full(100, 29.0), np.linspace(29, 62, 660)])
tm_s = np.full(300, 29.0); tm_s[100:105] = 70.0
o = run(14, seq(len(tm), T_meas=tm))
k_l, k_s = np.argmax(o[:, 0] == 3), np.argmax(o[:, 0] == 4)
tss = tm + 0.2 * (tm - 25)
o2 = run(14, seq(300, T_meas=tm_s))
tv = np.ones(300); tv[50:] = 0
tm3 = np.full(300, 29.0); tm3[50:] = 70.0
o3 = run(14, seq(300, T_meas=tm3, T_valid=tv))
check(14, "measurement-anchored core limit",
      tss[k_l - 9] > 55 and tss[k_l - 10] <= 55 and (int(o[k_l, 4]) & 1) and tss[k_s - 9] > 60
      and tss[k_s - 10] <= 60 and (o2[:, 0] != 4).all() and (o2[:, 0] != 3).all() and (o3[:, 0] != 4).all(),
      f"LIMP at T_meas {tm[k_l]:.1f} °C (T_ss {tss[k_l]:.1f}), SAFE at T_meas {tm[k_s]:.1f} °C "
      f"(T_ss {tss[k_s]:.1f}), Tc_hat 30 °C; 0.5 s spike and invalid sensor ignored")

# U15 açılış sıfır akım kontrolü (A9): kontaktör açıkken I_allow = 0; ölçülen ofset 2 A ->
# kabul (NORMAL, sonra rampa), 4 A ya da -4 A -> sensör arızası LIMP (neden 32), kalıcı
res = {}
for i0 in (2.0, 4.0, -4.0):
    o = run(15, seq(100), i_zero=i0)
    res[i0] = (run.pre, o)
p2, o2 = res[2.0]
ok = (all((r[0][:, 1:3] == 0).all() for r in res.values()) and (o2[:, 0] == 1).all() and o2[0, 1] > 0
      and all((r[1][:, 0] == 3).all() and (r[1][:, 4].astype(int) & 32).all() for k, r in res.items() if k != 2.0))
check(15, "start-up zero-current check", ok,
      f"I_allow 0 A for {N_ZERO * TS:.1f} s; offset 2 A -> {NAMES[int(o2[-1, 0])]}, "
      f"4 A -> {NAMES[int(res[4.0][1][-1, 0])]}, -4 A -> {NAMES[int(res[-4.0][1][-1, 0])]} (cause 32)")

# U16 termal anomali (thermal_anomaly.py bayrağı): gelir gelmez LIMP-HOME, neden 256 + 1 (0x201'de
# cause 8 bit: sıcaklık biti de kurulur); bayrak kilitli olduğu için durum kalır
an = np.r_[np.zeros(50), np.ones(150)]
o = run(16, seq(200, T_anom=an))
k_on = int(np.argmax(o[:, 0] == 3))
ok = (o[:50, 0] == 1).all() and k_on == 50 and (o[50:, 0] == 3).all() and (o[50:, 4].astype(int) & 257 == 257).all()
check(16, "thermal anomaly flag", ok,
      f"LIMP-HOME {(k_on - 50) * TS:.1f} s after the flag, cause {int(o[-1, 4])}, I_allow {o[-1, 1]:.1f} A")

V = pd.DataFrame(rows)
V.to_csv(os.path.join(HERE, "..", "simulink", "decision_vectors.csv"), index=False)
n_ok = sum(r[2] for r in results)
print(f"\n{n_ok}/{len(results)} unit tests passed. Test vectors: simulink/decision_vectors.csv ({len(V)} rows)")
