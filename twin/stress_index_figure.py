"""
Stres indeksi Ψ = 1 - Π(1 - Ψ_i): tez figürü (Python ikizi + karar mekanizması, kapalı çevrim).
Altı kriter (2026-11-26): T, C, Tdot gücü kısar (Ψ_P); A yaşlanma hızı şarjı kısar; H ve B gösterge.

(a) Yaşlanmış paket (R0, R1, R2 x1,4), 40 °C ortam, soğutma bozuk (R_u x4), agresif sürüş (x1,6):
    baskın kriter zamanla değişir (sağlık H, yaşlanma hızı A, soğutma C, çekirdek sıcaklığı T).
(b) Nominal paket, 600. s'de modellenmemiş dış ısı (twin_emu A2 butonu, 0,5 °C/s): sıcaklık artış
    hızı kriteri (Tdot) çekirdek kestirimi 45 °C'ye varmadan kısar; sonra anomali LIMP ve SAFE.
Çıktı: ../results/stress_index_drive.png (+ .csv, figürdeki seriler). Etiketler İngilizce.

    python twin/stress_index_figure.py
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))           # thesis_style.py (C:\bitirme)
import thesis_style as ts
from closed_loop import run
from decision import DOM_NAMES
from battery_model import AGE_BETA

ts.apply()
RES = os.path.join(HERE, "..", "results")
ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
I_std = ref.i_pack.values
I_agg = np.clip(1.6 * I_std, -40.7, 87.3)

KR80 = 1.0 + AGE_BETA * (1.0 - 0.80)                  # SOH %80 (ömür sonu), veri/age_resistance.py
A = run(I_agg, T_amb=40, ru_factor=4, soc0=0.95, truth={"capacity_ah": 0.80, "r0": KR80, "r1": KR80, "r2": KR80})
A["I_dem"] = I_agg
B = run(I_std[:9000], fault="heat", t_fault=600.0)
B["I_dem"] = I_std[:9000]
B = B[(B.t >= 540) & (B.t <= 700)].reset_index(drop=True)

CRIT = [("psi_T", "Ψ_T core temperature", ts.BLUE), ("psi_C", "Ψ_C cooling alarm", ts.ORANGE),
        ("psi_D", "Ψ_Tdot temperature-rise rate", ts.AQUA), ("psi_H", "Ψ_H battery health (display)", ts.YELLOW),
        ("psi_A", "Ψ_A ageing rate", ts.MAGENTA), ("psi_B", "Ψ_B cell imbalance (display)", ts.GREEN)]

fig, ax = plt.subplots(3, 2, figsize=(12.5, 7.6), sharex="col",
                       gridspec_kw=dict(width_ratios=[1.6, 1], height_ratios=[1, 1.25, 1], hspace=0.12, wspace=0.18))
for c, (d, title) in enumerate(((A, "(a) aged pack (SOH 80 %: Q x0.8, R x1.26), 40 °C, cooling degraded (R_u x4), aggressive drive"),
                                (B, "(b) unmodelled external heat at t = 600 s (nominal pack)"))):
    t = d.t.values
    # ---- sıcaklıklar
    a = ax[0, c]
    a.plot(t, d.tm, color=ts.LIGHT if c == 0 else ts.MUTED, lw=0.6, label="surface, measured", zorder=1)
    a.plot(t, d.tc, color=ts.INK, lw=1.2, label="core, true", zorder=3)
    a.plot(t, d.tc_hat, color=ts.BLUE, label="core, estimated", zorder=2)
    ts.ref_line(a, 45, "derate 45 °C")
    ts.ref_line(a, 55, "LIMP 55 °C")
    a.set_ylabel("temperature [°C]")
    ts.panel_label(a, title)
    a.legend(loc="upper left", ncol=3)
    # ---- stres alt indeksleri ve Ψ
    a = ax[1, c]
    for k, lab, col in CRIT:
        a.plot(t, d[k], color=col, lw=1.2, label=lab)
    a.plot(t, d.psi_s, color=ts.INK, lw=2.0, label="Ψ = 1 − Π(1 − Ψ_i)")
    a.plot(t, d.psi_p, color=ts.INK, lw=1.2, ls="--", label="Ψ_P (limits power)")
    a.set_ylim(-0.03, 1.62 if c == 0 else 1.14)   # (a): gösterge için üstte boşluk
    a.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    a.set_ylabel("stress index [-]")
    # baskın kriter: üstte ince renkli şerit (kriterin rengiyle)
    dom = d.dom.values.astype(int)
    for k0 in np.r_[0, np.flatnonzero(np.diff(dom) != 0) + 1]:
        k1 = k0
        while k1 + 1 < len(dom) and dom[k1 + 1] == dom[k0]:
            k1 += 1
        if dom[k0]:
            a.fill_between([t[k0], t[min(k1 + 1, len(t) - 1)]], 1.06, 1.12, color=CRIT[dom[k0] - 1][2], lw=0)
    a.annotate("dominant criterion", (0, 1.09), xycoords=("axes fraction", "data"), xytext=(-4, 0),
               textcoords="offset points", ha="right", va="center", fontsize=7, color=ts.INK2)
    if c == 0:
        a.legend(loc="upper left", ncol=3, bbox_to_anchor=(0, 1.0), fontsize=7.5)
    else:
        k_d = int(np.argmax(d.psi_D.values > 0)); k_t = int(np.argmax(d.psi_T.values > 0))
        ts.ref_line(a, x=t[k_d])
        a.annotate(f"Ψ_Tdot > 0\n{t[k_d] - 600:.1f} s", (t[k_d], 0.9), xytext=(3, 0), textcoords="offset points",
                   fontsize=7.5, color=ts.INK2, va="center")
        if k_t > k_d:
            a.annotate(f"Ψ_T > 0\n{t[k_t] - 600:.1f} s", (t[k_t], 0.12), xytext=(6, 0), textcoords="offset points",
                       fontsize=7.5, color=ts.INK2)
    # ---- akım: talep ve izin, durum şeridi
    a = ax[2, c]
    ts.state_band(a, t, d.state.values, legend=(c == 0))
    a.plot(t, d.I_dem, color=ts.MUTED, lw=0.6, label="demanded current")
    a.plot(t, d.i_dis, color=ts.INK, lw=1.4, label="allowed discharge current")
    a.set_ylabel("current [A]")
    a.set_xlabel("time [s]")
    a.legend(loc="lower left", ncol=3 if c == 0 else 1, fontsize=7.5)

fig.suptitle("Battery stress index Ψ (combined load of all conditions) in closed loop (Python digital twin + decision logic)",
             x=0.01, ha="left", fontsize=11, fontweight="bold")
out = os.path.join(RES, "stress_index_drive.png")
ts.save(fig, out)
cols = ["t", "tc", "tc_hat", "tm", "psi_T", "psi_C", "psi_D", "psi_H", "psi_A", "psi_B", "psi_s", "psi_p", "dom",
        "tdot", "kr", "state", "i_dis", "I_dem"]
pd.concat([A[cols].assign(case="a_aged_hot_cooling"), B[cols].assign(case="b_external_heat")]).to_csv(
    os.path.join(RES, "stress_index_drive.csv"), index=False, float_format="%.4g")
# rapor için sayılar
dA = A.dom.values.astype(int)
share = {DOM_NAMES[k]: 100 * np.mean(dA == k) for k in range(7)}
print("(a) dominant share %:", {k: round(v, 1) for k, v in share.items() if v > 0},
      f"| Psi max {A.psi_s.max():.2f}, Psi_P max {A.psi_p.max():.2f}, T_core max {A.tc.max():.1f} °C, states {sorted(set(A.state.astype(int)))}")
print(f"(b) Psi_Tdot > 0 at +{B.t[np.argmax(B.psi_D.values > 0)] - 600:.1f} s, Psi_T > 0 at "
      f"+{B.t[np.argmax(B.psi_T.values > 0)] - 600:.1f} s, LIMP at +{B.t[np.argmax(B.state.values >= 3)] - 600:.1f} s, "
      f"SAFE at +{B.t[np.argmax(B.state.values == 4)] - 600:.1f} s")
print("->", out)
