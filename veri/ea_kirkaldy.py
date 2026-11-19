"""İç direncin aktivasyon enerjisi (Ea), Kirkaldy et al. 2024 ham yaşlandırma verisinden.

Kaynak: Expt 5 (Standard Cycle Aging), Set 1 ham BioLogic .mpr dosyaları (indir_ham.py), hücreler
10 / 25 / 40 °C odalarında döngüleniyor (CC 0.3C şarj, CV 4.2 V, 1C = 5 A deşarj). CC BY 4.0,
doi:10.5281/zenodo.10637534.

Yöntem: her deşarj başlangıcı (CV kuyruğu ~0.05 A -> -5 A) aynı SOC'de (~%100) bir akım basamağı.
İlk örnek basamaktan 0.05 s sonra, sonrakiler 1 s aralıkla. R(tau) = dV(tau) / dI:
  tau = 0.05 s  ohmik kısım (elektron + elektrolit iletimi)
  tau = 1-30 s  + yük transferi ve difüzyon (RC dalları)
Sıcaklık: hücre yüzeyindeki termokupl (dosyadaki Temperature sütunu), basamaktan hemen önce.
Yaşlanmanın etkisini ayırmak için yalnız ilk N_CYC deşarj kullanılır; her hücrenin medyanı alınır.
Arrhenius: R(T) = R_25 exp(Ea/Rg (1/T - 1/298.15 K)), ln R'nin 1/T'ye doğrusal uydurması.

Kullanım: python -I ea_kirkaldy.py   -> ea_kirkaldy.csv, ea_kirkaldy.png
"""
import glob
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from galvani import BioLogic

HERE = os.path.dirname(os.path.abspath(__file__))
RG = 8.314
N_CYC = 10            # her hücreden ilk 10 deşarj (yaşlanma etkisi küçük)
DT_MAX = 1.5          # [s] basamaktan sonraki ilk örnek bu süreden geç ise atla
TAUS = (0.05, 1.0, 10.0, 30.0)


def steps(path):
    d = BioLogic.MPRfile(path).data
    tcol = [n for n in d.dtype.names if n.startswith("Temperature")][0]
    t, v, i, T = d["time/s"], d["Ewe/V"], d["I/mA"] / 1000.0, d[tcol]
    a = np.flatnonzero((i[1:] < -4.0) & (np.abs(i[:-1]) < 0.5) & (v[:-1] > 4.15)) + 1
    out = []
    for k in a:
        if t[k] - t[k - 1] > DT_MAX:
            continue
        t0, j, di = t[k - 1], k + 40, i[k] - i[k - 1]
        rs = [(v[k - 1] - (v[k] if tau < 0.06 else np.interp(t0 + tau, t[k:j], v[k:j]))) / -di
              for tau in TAUS]
        out.append([t[k]] + rs + [T[k - 1]])
    return np.array(out)


rows = []
for f in sorted(glob.glob(os.path.join(HERE, "kirkaldy_ham", "*", "Raw Data", "Degradation Cycling",
                                       "Set 1", "*.mpr"))):
    m = re.search(r"(\d+)degC - cell (\w)", f)
    s = steps(f)[:N_CYC]
    r = dict(cell=m.group(2), T_chamber=int(m.group(1)), n=len(s), T_cell=float(np.median(s[:, -1])))
    for j, tau in enumerate(TAUS):
        r[f"R_{tau:g}s"] = 1e3 * float(np.median(s[:, 1 + j]))
        r[f"sd_{tau:g}s"] = 1e3 * float(np.std(s[:, 1 + j]))
    rows.append(r)
    print(f"cell {r['cell']} {r['T_chamber']:2d} C: {len(s)} steps, T_cell {r['T_cell']:.1f} C, "
          + ", ".join(f"R{tau:g}s {r[f'R_{tau:g}s']:.2f}" for tau in TAUS) + " mOhm")

df = pd.DataFrame(rows)
x = 1.0 / (df.T_cell.values + 273.15) - 1 / 298.15
A = np.vstack([x, np.ones_like(x)]).T


def fit(y_mohm):
    y = np.log(y_mohm)
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    s2 = np.sum((y - A @ c) ** 2) / max(len(y) - 2, 1)
    return c[0] * RG, np.sqrt(s2 * np.linalg.inv(A.T @ A)[0, 0]) * RG, float(np.exp(c[1]))


fits = {f"{tau:g}s": fit(df[f"R_{tau:g}s"].values) for tau in TAUS}
for tau in TAUS[1:]:      # polarizasyon kısmı: ohmik kısım çıkarılmış
    fits[f"pol {tau:g}s"] = fit(df[f"R_{tau:g}s"].values - df["R_0.05s"].values)
print("Arrhenius fits (Ea kJ/mol, R at 25 C mOhm):")
for k, (ea, se, r25) in fits.items():
    print(f"  {k:10s} Ea {ea / 1e3:5.1f} +- {se / 1e3:4.1f}   R25 {r25:6.2f}")
    df[f"Ea_{k}"] = ea
df.to_csv(os.path.join(HERE, "ea_kirkaldy.csv"), index=False)

# ---------------------------------------------------------------- figür
COL = {"0.05s": "#2a78d6", "1s": "#1baf7a", "10s": "#eb6834", "30s": "#e87ba4"}
fig, ax = plt.subplots(figsize=(6.8, 4.2))
Tg = np.linspace(5, 45, 100)
arr = lambda r25, ea, T: r25 * np.exp(ea / RG * (1 / (T + 273.15) - 1 / 298.15))
for tau in TAUS:
    k = f"{tau:g}s"
    ea, se, r25 = fits[k]
    ax.plot(Tg, arr(r25, ea, Tg), color=COL[k], lw=1.8)
    ax.plot(df.T_cell, df[f"R_{k}"], "o", color=COL[k], ms=6, mec="white", mew=1)
    ax.annotate(f"{tau:g} s: Ea {ea / 1e3:.0f} kJ/mol", (45, arr(r25, ea, 45.0)), xytext=(4, 0),
                textcoords="offset points", va="center", fontsize=8, color="#1f1f1e")
ax.plot(Tg, arr(26.4, 20000.0, Tg), color="#9a9990", lw=1.5, ls="--")
ax.annotate("previous model R0, Ea 20 kJ/mol", (6, arr(26.4, 20000.0, 6.0)), xytext=(0, 6),
            textcoords="offset points", fontsize=8, color="#5f5e58")
ax.set_xlim(5, 60)
ax.set_xlabel("cell surface temperature [°C]")
ax.set_ylabel("R = ΔV/ΔI after a 5 A step at ~100 % SOC [mΩ]")
ax.set_title("LG M50T resistance vs temperature, by time after the step (Kirkaldy 2024)",
             loc="left", fontsize=9.5, fontweight="bold")
ax.grid(color="#d6d5cf", lw=0.6)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "ea_kirkaldy.png"), dpi=200)
