"""Yaşlanmada direnç artışı ile kapasite kaybı ilişkisi, Kirkaldy et al. 2024 özet verisinden.

Kaynak: kirkaldy_ozet/*/Summary Data/Performance Summary/*.csv (indir_ozet.py), 5 deney, 40 hücre,
her RPT'de C/10 kapasitesi ve 0.1 s darbe direnci. CC BY 4.0, doi:10.5281/zenodo.10637534.

Model: k_R = R / R_BoL = 1 + beta (1 - SOH), SOH = Q / Q_BoL; orijinden geçen en küçük kareler
(SOH < 0.995 noktalar). beta ikizlerde yaşlanmayı tek parametreye (SOH) bağlar:
  bms_ecu bms/sim/twin_model.h TW_AGE_BETA, twin/battery_model.py AGE_BETA, simulink P.age_beta.
Değişirse üçü de güncellenmeli. Stres indeksinin Ψ_H eşikleri (DEC_KR_ON / DEC_KR_FULL) de bu
ilişkiyle SOH'ye çevrilir.

Kullanım: python -I age_resistance.py   -> age_resistance.csv, ../results/age_resistance.png
"""
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import thesis_style as ts                       # ortak tez figür stili
ts.apply()

rows = []
for f in sorted(glob.glob(os.path.join(HERE, "kirkaldy_ozet", "*", "Summary Data",
                                       "Performance Summary", "*.csv"))):
    d = pd.read_csv(f)
    q = d["C/10 Capacity [mA h]"].astype(float)
    r = d["0.1s Resistance [Ohms]"].astype(float)
    ok = q.notna() & r.notna()
    q, r = q[ok].values, r[ok].values
    if len(q) < 3:
        continue
    name = os.path.basename(f)
    ex = re.search(r"Expt (\S+)", name).group(1)
    cell = re.search(r"cell (\w)", name).group(1)
    temp = int(re.search(r"\((\d+)degC\)", name).group(1))
    for qi, ri in zip(q, r):
        rows.append((ex, cell, temp, qi / q[0], ri / r[0]))
D = pd.DataFrame(rows, columns=["expt", "cell", "T_C", "soh", "k_R"])
D.to_csv(os.path.join(HERE, "age_resistance.csv"), index=False)

# Expt 5 hücre A (10 °C) bir RPT'de k_R = 6.1 (komşu RPT'ler ~1.1): ölçüm hatası, dışarıda
m = (D.soh < 0.995) & (D.k_R < 3.0)
x, y = 1.0 - D.soh[m], D.k_R[m] - 1.0
beta = float(np.sum(x * y) / np.sum(x * x))
res = y - beta * x
n_cells = D.groupby(["expt", "cell", "T_C"]).ngroups
print(f"cells {n_cells}, RPT points {len(D)} (fit {m.sum()}, outliers {int((D.k_R >= 3.0).sum())})")
print(f"beta = {beta:.2f}  (k_R = 1 + beta (1 - SOH)), residual std {res.std():.3f}")
for soh in (0.9, 0.85, 0.8, 0.7):
    print(f"  SOH {soh:.2f} -> k_R {1 + beta * (1 - soh):.2f}")
for kr in (1.2, 1.29, 1.6):
    print(f"  k_R {kr:.2f} -> SOH {1 - (kr - 1) / beta:.2f}")

# ---------------- figür
fig, ax = plt.subplots(figsize=(5.2, 3.4))
for i, T in enumerate(sorted(D.T_C.unique())):
    s = D[(D.T_C == T) & (D.k_R < 3.0)]
    ax.scatter(100 * s.soh, s.k_R, s=9, color=ts.SERIES[i], alpha=0.75, lw=0, label=f"{T} °C")
xs = np.linspace(0.42, 1.0, 50)
ax.plot(100 * xs, 1 + beta * (1 - xs), color=ts.INK, lw=1.2,
        label=f"fit: $k_R = 1 + {beta:.2f}\\,(1-\\mathrm{{SOH}})$")
ts.ref_line(ax, x=80, label="EoL (SOH 80 %)")
ax.set_xlabel("SOH (C/10 capacity / BoL) [%]")
ax.set_ylabel("$k_R$ (0.1 s resistance / BoL)")
ax.set_xlim(102, 42)
ax.legend(loc="upper left", frameon=False)
ax.set_title(f"LG M50T resistance growth vs capacity fade ({n_cells} cells, Kirkaldy et al. 2024)",
             fontsize=8)
ts.save(fig, os.path.join(HERE, "..", "results", "age_resistance.png"))
