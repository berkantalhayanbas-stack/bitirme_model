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
from decision import Decision, NAMES, DecisionParams

HERE = os.path.dirname(os.path.abspath(__file__))
TS = 0.1
COLS = ["I_meas", "V_min", "V_max", "Tc_hat", "Ts_hat", "Ru_hat", "SOC_est", "bias_est",
        "T_valid", "I_valid", "CAN_ok", "T_meas", "T_amb", "T_anom", "k_R", "soh_c"]
BASE = dict(I_meas=20.0, V_min=3.65, V_max=3.69, Tc_hat=30.0, Ts_hat=29.0, Ru_hat=9.0,
            SOC_est=0.6, bias_est=0.5, T_valid=1, I_valid=1, CAN_ok=1, T_meas=29.0, T_amb=25.0,
            T_anom=0, k_R=1.0, soh_c=1.0)
rows, results = [], []


def seq(n, **over):
    """n örneklik sabit girdi; over ile istenen sütunlar dizi veya sabit olarak değiştirilir."""
    d = {k: np.full(n, float(v)) for k, v in BASE.items()}
    for k, v in over.items():
        d[k] = np.broadcast_to(np.asarray(v, float), (n,)).copy()
    return d


N_ZERO = 10      # açılış sıfır akım kontrolü (A9): kontaktör açık, I_allow = 0


def run(test_id, inp, i_zero=0.0, params=None):
    """Her testin önüne N_ZERO örneklik açılış kontrolü eklenir (ilk örneğin girdileri, ölçülen
    akım i_zero: kontaktör açıkken akım kesin 0, ölçülen = sensör ofseti). Dönen çıktı bu örnekleri
    içermez (testlerin zaman indeksleri değişmez); test vektörlerine ise girer."""
    dec = Decision(params)
    pre = {c: np.full(N_ZERO, inp[c][0]) for c in COLS}
    pre["I_meas"][:] = i_zero
    full = {c: np.concatenate([pre[c], inp[c]]) for c in COLS}
    n = len(full["I_meas"])
    out = np.zeros((n, 8))       # durum, I_dis, I_chg, toplam kısıtlama, neden, Ψ, baskın kriter, Ψ_P
    for k in range(n):
        out[k, :5] = dec.step(*[full[c][k] for c in COLS])
        out[k, 5:] = dec.psi_s, dec.dom, dec.psi_p
        if params is None:       # MATLAB vektörleri yalnız varsayılan parametrelerle
            rows.append(dict(test=test_id, reset=int(k == 0), **{c: full[c][k] for c in COLS},
                             state=out[k, 0], i_dis=out[k, 1], i_chg=out[k, 2], psi=out[k, 3], cause=out[k, 4],
                             psi_s=out[k, 5], dom=out[k, 6], psi_p=out[k, 7]))
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

# U17 Ψ_Tdot (sıcaklık artış hızı): Tc_hat 30 °C'de sabit (gözlemci gizli ısıyı görmüyor), ölçülen
# yüzey 6 °C/dk yükselir -> süzülmüş hız ~6 °C/dk, Ψ_Tdot = 0,5 (6-3)/7 = 0,214, DERATE, neden 512+1.
# Nominal sürüşün en hızlısı (2 °C/dk) gürültülü ölçümle (0,3 °C, 0,1 °C kuantalama) hiç tetiklemez.
n = 2200                                  # yüzey 29 -> 45 °C (T_ss < 55: LIMP yok)
tm = 29.0 + np.r_[np.zeros(600), np.arange(n - 600) * 0.01]          # 0,01 °C/örnek = 6 °C/dk
o = run(17, seq(n, T_meas=tm))
psi_exp = 0.5 * (6.0 - 3.0) / 7.0
tm2 = np.round((29.0 + np.arange(n) * 2.0 / 600 + 0.3 * rng.standard_normal(n)) / 0.1) * 0.1
o2 = run(17, seq(n, T_meas=tm2))
ok = (abs(o[-1, 7] - psi_exp) < 0.01 and abs(o[-1, 5] - psi_exp) < 0.01 and o[-1, 0] == 2
      and (int(o[-1, 4]) & 513) == 513 and o[-1, 6] == 3
      and abs(o[-1, 1] - 87.3 * (1 - o[-1, 7])) < 1e-6 and (o[:600, 0] == 1).all()
      and (o2[:, 0] == 1).all() and o2[:, 7].max() == 0)
check(17, "temperature-rise-rate criterion", ok,
      f"6 °C/min -> Psi_P {o[-1, 7]:.3f} (expected {psi_exp:.3f}), dominant {int(o[-1, 6])}, cause {int(o[-1, 4])}, "
      f"DERATE after {(np.argmax(o[:, 0] == 2) - 600) * TS:.0f} s; 2 °C/min with noise -> max Psi_P {o2[:, 7].max():.3f}")

# U18 Ψ_H (sağlık, yalnız gösterge): k_R 1,0 -> 1,25 -> Ψ_H 0,5, neden 1024 (bilgi); Ψ (gösterge) 0,5, baskın 4,
# ama Ψ_P = 0, NORMAL, akım kısılmaz. Kapasite SOH %80 -> Ψ_H 0,5 de (büyüğü). SOP direnci k_R ile ölçeklenir.
n = 2000
kr = np.r_[np.ones(500), np.linspace(1.0, 1.25, 1000), np.full(500, 1.25)]
o = run(18, seq(n, k_R=kr))
pp = DecisionParams()
r0 = pp.r0 * np.exp(pp.ea / pp.rgas * (1 / (30.0 + 273.15) - 1 / 298.15))
v_lo = 3.05                                                  # SOP'un Ψ'den küçük kaldığı gerilim
o3 = run(18, seq(600, V_min=v_lo, k_R=1.4))
sop14 = 20.0 + pp.k_sop * pp.np_ * (v_lo - pp.v_lim_dis) / (1.4 * r0)
o_b = run(18, seq(1500, k_R=2.0))                            # açılıştan k_R tavanda: 120 s Ψ_H yok
o_s = run(18, seq(1500, soh_c=0.80))                         # kapasite SOH %80
ok = (abs(o[-1, 5] - 0.5) < 1e-6 and o[-1, 7] == 0.0 and o[-1, 0] == 1 and (int(o[-1, 4]) & 1024) and o[-1, 6] == 4
      and not (o_b[:1199 - N_ZERO, 4].astype(int) & 1024).any() and (int(o_b[-1, 4]) & 1024)
      and abs(o_s[-1, 5] - 0.5) < 1e-6 and o_s[-1, 0] == 1 and abs(o_s[-1, 1] - 87.3) < 1e-6
      and abs(o[-1, 1] - 87.3) < 1e-6 and abs(o3[-1, 1] - sop14) < 1e-6 and (o[:500, 0] == 1).all())
check(18, "battery-health criterion (display)", ok,
      f"k_R 1.25 -> Psi_H {o[-1, 5]:.3f}, Psi_P {o[-1, 7]:.3f}, cause {int(o[-1, 4])}, state {int(o[-1, 0])}, dominant {int(o[-1, 6])}, "
      f"I_allow {o[-1, 1]:.1f} A; SOH 80 % -> Psi {o_s[-1, 5]:.3f}; k_R 2.0 from start: no Psi_H for 120 s; "
      f"SOP at V_min {v_lo} V: {o3[-1, 1]:.1f} A (k_R-scaled R0, expected {sop14:.1f})")

# U19 toplama (olasılıksal VEYA): Ψ_T 0,5 (49 °C) + soğutma 0,3 -> Ψ_P = 1 - 0,5·0,7 = 0,65, I_allow 0,35·87,3;
# gösterge Ψ = VEYA(altı Ψ_i) = 1 - Π(1 - Ψ_i), baskın kriter en büyük Ψ_i
n = 1800
tc = np.r_[np.linspace(30, 49, 600), np.full(n - 600, 49.0)]
ru = np.r_[np.full(1300, 9.0), np.full(n - 1300, 25.0)]
dec19 = Decision()
inp = seq(n, Tc_hat=tc, Ru_hat=ru, k_R=1.24)
o = run(19, inp)
d = Decision()
for k in range(N_ZERO):
    d.step(*[inp[c][0] if c != "I_meas" else 0.0 for c in COLS])
for k in range(n):
    d.step(*[inp[c][k] for c in COLS])
pi = d.psi_i
or6 = 1 - np.prod([1 - x for x in pi])
ok = (abs(o[-1, 7] - 0.65) < 1e-9 and abs(o[-1, 1] - 0.35 * 87.3) < 1e-6 and abs(o[-1, 5] - or6) < 1e-12
      and o[-1, 6] == 1 + int(np.argmax(pi)) and abs(pi[3] - 0.4) < 1e-6)
check(19, "aggregation (probabilistic OR)", ok,
      f"Psi_i = ({', '.join(f'{x:.3f}' for x in pi)}) -> Psi_P {o[-1, 7]:.3f} (expected 0.650), Psi {o[-1, 5]:.3f}, "
      f"dominant {int(o[-1, 6])}, I_allow {o[-1, 1]:.1f} A")

# U21 Ψ_A çevrim payı: aynı akımla (0,3C) tam derinlikte şarj, 15 °C ve 26 °C. Veride soğukta tam çevrim daha hızlı
# yaşlandırır (NMC811/SiOx, Li kaplama) -> çevrim oranı R_cyc soğukta büyük; 0,3C'de ikisi de referansın (0,5C,
# 25 °C) altında kalabilir (veri C oranını değiştirmiyor: tez sınırlaması). Ölçek 0,5 ile zorlanmış hızlı şarj
# (26 °C, 60 A) şarjı kısar ama 0,3C tabanının altına indirmez; deşarj ve durum etkilenmez.
n = 3000
soc_up = np.linspace(0.10, 0.90, n)


def r_cyc_end(T, I, params=None):
    d = Decision(params)
    inp = seq(n, I_meas=I, Tc_hat=T, Ts_hat=T, T_meas=T, T_amb=T, SOC_est=soc_up)
    for k in range(n):
        d.step(*[inp[c][k] for c in COLS])
    return d.r_cyc


rc15, rc26 = r_cyc_end(15.0, -17.0), r_cyc_end(26.0, -17.0)
pf = DecisionParams(); pf.age_log2_full = 0.5
of = run(21, seq(n, I_meas=-60.0, Tc_hat=26.0, Ts_hat=26.0, T_meas=26.0, T_amb=25.0, SOC_est=soc_up), params=pf)
floor = pp.age_floor * pp.np_
ok = (rc15 > rc26 and abs(of[-1, 2] - floor) < 1e-6 and of[-1, 0] == 1 and (int(of[-1, 4]) & 4096)
      and abs(of[-1, 1] - 87.3) < 1e-6 and of[-1, 7] == 0.0)
check(21, "ageing-rate criterion (cycle, charge only)", ok,
      f"0.3C full-depth charge: R_cyc 15 C {rc15:.2f} vs 26 C {rc26:.2f}; forced fast charge -> I_chg {of[-1, 2]:.2f} A "
      f"(floor {floor:.2f}), cause {int(of[-1, 4])}, state {int(of[-1, 0])}, discharge {of[-1, 1]:.1f} A")

# U22 Ψ_A takvim payı: sıcak (42 °C) ve dolu (SOC %95) park, akım 0 -> Ψ_A ~0,5 gösterge, akım sınırları ve durum
# değişmez; ılık (30 °C) yarı dolu (%60) pakette 0 (takvim oranı < 2x)
n = 1500
o = run(22, seq(n, I_meas=0.0, Tc_hat=42.0, Ts_hat=41.5, T_meas=41.5, T_amb=40.0, SOC_est=0.95))
o2 = run(22, seq(n, I_meas=0.0, Tc_hat=30.0, Ts_hat=30.0, T_meas=30.0, T_amb=28.0, SOC_est=0.60))
ok = (0.4 < o[-1, 5] < 0.7 and o[-1, 6] == 5 and o[-1, 0] == 1 and abs(o[-1, 1] - 87.3) < 1e-6
      and abs(o[-1, 2] - 40.74) < 0.01 and o2[-1, 5] == 0.0)
check(22, "ageing-rate criterion (calendar, display)", ok,
      f"42 C / SOC 95 % park -> Psi_A {o[-1, 5]:.3f}, state {int(o[-1, 0])}, I_dis {o[-1, 1]:.1f} / I_chg {o[-1, 2]:.2f} A; "
      f"30 C / 60 % -> Psi {o2[-1, 5]:.3f}")

# U23 Ψ_B dengesizlik (gösterge): düşük akımda V_max - V_min 100 mV -> Ψ_B 0,5 (10 s süzgeç), NORMAL, akım
# kısılmaz; sürüşte (|I| > 2 A) süzgeç güncellenmez (IR düşümü dengesizlik sanılmasın)
n = 2400
o = run(23, seq(n, I_meas=0.5, V_min=3.65, V_max=3.75))
o2 = run(23, seq(n, I_meas=40.0, V_min=3.55, V_max=np.r_[3.58, np.full(n - 1, 3.75)]))
ok = (abs(o[-1, 5] - 0.5) < 0.01 and o[-1, 6] == 6 and (int(o[-1, 4]) & 8192) and o[-1, 0] == 1
      and abs(o[-1, 1] - 87.3) < 1e-6 and not (int(o2[-1, 4]) & 8192))
check(23, "cell-imbalance criterion (display)", ok,
      f"dV 100 mV at 0.5 A -> Psi_B {o[-1, 5]:.3f}, dominant {int(o[-1, 6])}, state {int(o[-1, 0])}; "
      f"dV 200 mV at 40 A -> cause {int(o2[-1, 4])} (not updated)")

V = pd.DataFrame(rows)
V.to_csv(os.path.join(HERE, "..", "simulink", "decision_vectors.csv"), index=False)
n_ok = sum(r[2] for r in results)
print(f"\n{n_ok}/{len(results)} unit tests passed. Test vectors: simulink/decision_vectors.csv ({len(V)} rows)")
