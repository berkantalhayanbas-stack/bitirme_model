"""Hücre modelinin (2-RC + Chen 2020 OCV) Kirkaldy GITT verisine karşı doğrulaması.
Aynı akım profili modele verilir, ölçülen gerilimle karşılaştırılır (RMSE). Üç parametre seti:
  model    : bms_config.h (R1 9,3 mOhm / 10 s, R2 12 mOhm / 180 s)
  darbe    : gitt_fit.py darbe uydurması (40-60 % SOC medyanı)
  dinlenme : gitt_fit.py dinlenme uydurması
R0 her üçünde Kirkaldy 0,1 s değeri. Hücre A-H, RPT0, 25 °C. Şekil: gitt_dogrulama.png
"""
import glob
import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "twin"))
from battery_model import CellParams

cp = CellParams()
SETS = {"model": (26.4, 9.3, 10, 12.0, 180), "darbe": None, "dinlenme": None}
F = pd.read_csv(os.path.join(HERE, "gitt_fit_sonuc.csv"))
mid = F[(F.soc > 0.42) & (F.soc < 0.62)].median(numeric_only=True)
SETS["darbe"] = (mid.pR0, mid.pR1, mid.ptau1, mid.pR2, mid.ptau2)
SETS["dinlenme"] = (mid.R0, mid.R1, mid.tau1, mid.R2, mid.tau2)
ocv = lambda s: np.interp(s, cp.soc_tab, cp.ocv_tab)


def sim(t, i, q0, Q, p):
    R0, R1, t1, R2, t2 = p[0] / 1e3, p[1] / 1e3, p[2], p[3] / 1e3, p[4]
    v1 = v2 = 0.0
    out = np.empty_like(t)
    soc = q0
    for k in range(len(t)):
        dt = t[k] - t[k - 1] if k else 0.0
        a1, a2 = np.exp(-dt / t1), np.exp(-dt / t2)
        v1 = a1 * v1 + R1 * (1 - a1) * i[k]
        v2 = a2 * v2 + R2 * (1 - a2) * i[k]
        soc -= i[k] * dt / 3600 / Q
        out[k] = ocv(soc) - R0 * i[k] - v1 - v2
    return out


res = {k: [] for k in SETS}
keep = None
for f in sorted(glob.glob(os.path.join(HERE, "kirkaldy_ham", "**", "*RPT0 - 25-pulse GITT*.csv"), recursive=True)):
    d = pd.read_csv(f)
    t, v, i = d["Time (s)"].values, d["Voltage (V)"].values, -d["Current (mA)"].values / 1000.0  # + deşarj
    Q = np.abs(d["Charge (mA.h)"].values).max() / 1000.0 / 0.999
    s0 = np.interp(v[0], cp.ocv_tab, cp.soc_tab)          # başlangıç SOC: dinlenmiş gerilimden
    m = v > 2.9                                           # çok düşük SOC (OCV tablosu kaba) hariç
    for k, p in SETS.items():
        vs = sim(t, i, s0, Q, p)
        res[k].append(np.sqrt(np.mean((vs[m] - v[m]) ** 2)) * 1e3)
        if keep is None or k not in keep:
            keep = keep or {"t": t, "v": v}
            keep[k] = vs
print("Gerilim RMSE [mV] (8 hücre, V > 2,9 V):")
for k, r in res.items():
    print(f"  {k:9s} R0 {SETS[k][0]:.1f} R1 {SETS[k][1]:.1f}/{SETS[k][2]:.1f}s R2 {SETS[k][3]:.1f}/{SETS[k][4]:.0f}s"
          f" -> medyan {np.median(r):.1f}, en kötü {max(r):.1f}")
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(10, 6))
    tt = keep["t"] / 3600
    for a, lim in ((ax[0], None), (ax[1], (5.0, 5.6))):
        a.plot(tt, keep["v"], "k", lw=1, label="Measured (Kirkaldy et al. 2024, cell A)")
        for k, c in (("model", "C0"), ("darbe", "C1"), ("dinlenme", "C2")):
            a.plot(tt, keep[k], c, lw=0.8, label=f"2-RC: {k}")
        if lim:
            a.set_xlim(*lim); a.set_ylim(3.9, 4.15)
        a.set_ylabel("Cell voltage [V]")
    ax[0].legend(fontsize=8); ax[1].set_xlabel("time [h]")
    fig.suptitle("LG M50T 25-pulse GITT (0.5C, 25 °C): model vs measurement")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "gitt_dogrulama.png"), dpi=130)
    print("sekil: gitt_dogrulama.png")
except Exception as e:
    print("sekil yok:", e)
