"""LG M50T için ölçülmüş OCV(SOC) tablosu: Kirkaldy et al. (2024) C/10 eğrilerinden (BoL, 25 °C).

Veri: doi:10.5281/zenodo.10637534 (CC BY 4.0), Expt 5 hücre A-H, RPT0, '0.1C charge/discharge'.
Yöntem: SOC_deşarj = 1 - Q/Q_d, SOC_şarj = Q/Q_c (kendi kapasiteleriyle normalize).
  Sözde OCV = (V_şarj + V_deşarj)/2  -> C/10'daki IR düşümü (~0,5 A x ~40 mOhm) ve histerezis
  ortalanır; yarı fark = IR + histerezis payı. 8 hücrenin medyanı. Chen vd. (2020) tablosuyla
  karşılaştırılır; çıktı ocv_kirkaldy.csv (23 nokta, modelin SOC ızgarası) ve ../results/ocv_kirkaldy.png.
"""
import glob
import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "twin"))
from battery_model import CellParams, OCV_CHEN2020, OCV_CHEN2020_SOC

cp = CellParams()
grid = np.linspace(0, 1, 201)
V = {"c": [], "d": []}
for kind, tag in (("c", "charge"), ("d", "discharge")):
    for f in sorted(glob.glob(os.path.join(HERE, "kirkaldy_ham", "**", f"*RPT0 - 0.1C {tag} data.csv"), recursive=True)):
        d = pd.read_csv(f)
        q = np.abs(d["Charge (mA.h)"].values)
        v = d["Voltage (V)"].values
        soc = q / q.max() if kind == "c" else 1 - q / q.max()
        o = np.argsort(soc)
        V[kind].append(np.interp(grid, soc[o], v[o]))
vc, vd = np.median(V["c"], axis=0), np.median(V["d"], axis=0)
ocv = 0.5 * (vc + vd)
half = 0.5 * (vc - vd)
chen = np.interp(grid, OCV_CHEN2020_SOC, OCV_CHEN2020)
m = (grid >= 0.05) & (grid <= 0.95)
print(f"hucre sayisi: sarj {len(V['c'])}, desarj {len(V['d'])}")
print(f"Kirkaldy sozde-OCV - Chen 2020: ortalama {1e3 * np.mean(ocv[m] - chen[m]):+.1f} mV, "
      f"RMS {1e3 * np.sqrt(np.mean((ocv[m] - chen[m]) ** 2)):.1f} mV, en buyuk {1e3 * np.max(np.abs(ocv[m] - chen[m])):.1f} mV (SOC 5-95 %)")
print(f"yari fark (IR + histerezis) SOC 20-80 %: medyan {1e3 * np.median(half[(grid > .2) & (grid < .8)]):.1f} mV")
tab = np.interp(cp.soc_tab, grid, ocv)
pd.DataFrame({"soc": cp.soc_tab, "ocv_kirkaldy": tab, "ocv_chen2020": np.interp(cp.soc_tab, OCV_CHEN2020_SOC, OCV_CHEN2020),
              "fark_mV": 1e3 * (tab - np.interp(cp.soc_tab, OCV_CHEN2020_SOC, OCV_CHEN2020))}).to_csv(os.path.join(HERE, "ocv_kirkaldy.csv"), index=False)
print(pd.read_csv(os.path.join(HERE, "ocv_kirkaldy.csv")).round(4).to_string(index=False))
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import thesis_style as ts                       # ortak tez figür stili
    ts.apply()
    fig, ax = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    ax[0].plot(grid, vc, "C1", lw=0.8, label="C/10 charge (median, 8 cells)")
    ax[0].plot(grid, vd, "C0", lw=0.8, label="C/10 discharge")
    ax[0].plot(grid, ocv, "k", lw=1.2, label="pseudo-OCV (mean)")
    ax[0].plot(OCV_CHEN2020_SOC, OCV_CHEN2020, "o", ms=3, color="C2", label="Chen et al. 2020 (LG M50)")
    ax[0].set_ylabel("V"); ax[0].legend(fontsize=8)
    ax[1].plot(grid, 1e3 * (ocv - chen), "k", label="pseudo-OCV - Chen 2020")
    ax[1].plot(grid, 1e3 * half, "C2", label="half gap (IR + hysteresis)")
    ax[1].axhline(0, color=ts.AXIS, lw=0.8); ax[1].set_ylim(-80, 80)
    ax[1].set_xlabel("SOC"); ax[1].set_ylabel("mV"); ax[1].legend(fontsize=8)
    fig.suptitle("LG M50T OCV from Kirkaldy et al. (2024) C/10 data vs model table")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "..", "results", "ocv_kirkaldy.png"), dpi=130)
except Exception as e:
    print("sekil yok:", e)
