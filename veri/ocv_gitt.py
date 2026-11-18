"""OCV tablosu adayları ve GITT'e karşı çapraz doğrulama (LG M50T, Kirkaldy et al. 2024, BoL, 25 °C).

Adaylar (modelin 23 noktalı SOC ızgarasında):
  chen   : Chen vd. (2020), LG M50 (şimdiki model)
  c10    : C/10 şarj/deşarj ortalaması (ocv_kirkaldy.py)
  gitt   : GITT dinlenme sonu gerilimleri (deşarj kolu, ~gerçek OCV), hücre A-D'den
  karma  : gitt noktaları + aralarında c10 eğrisinin şekli (gitt'e kaydırılmış)
Doğrulama: aynı 2-RC (model parametreleri) ile hücre E-H'nin GITT gerilimi simüle edilir (tabloyu
kuran hücreler doğrulamaya girmez), RMSE (V > 2,9 V). SOC: tam şarjın sonu = 1, sonrası Coulomb sayımı.
Çıktı: ocv_tablolari.csv, ocv_dogrulama.png
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
SOC = cp.soc_tab
R0, R1, T1, R2, T2 = 0.0264, 0.0093, 10.0, 0.012, 180.0


def load(f):
    d = pd.read_csv(f)
    t, v, i = d["Time (s)"].values, d["Voltage (V)"].values, -d["Current (mA)"].values / 1000.0  # + deşarj
    # tam şarjın sonu: deşarj darbelerinden önceki son şarj (i < 0) örneği
    k_dis = np.flatnonzero(i > 0.05)[0]
    k_full = np.flatnonzero(i[:k_dis] < -0.01)[-1] + 1
    ah = np.concatenate([[0], np.cumsum(i[1:] * np.diff(t))]) / 3600
    ah -= ah[k_full]
    Q = ah[-1] if ah[-1] > 4 else ah[np.argmax(v < 2.51)]
    soc = 1 - ah / Q
    return t[k_full:], v[k_full:], i[k_full:], soc[k_full:], Q


cells = sorted(glob.glob(os.path.join(HERE, "kirkaldy_ham", "**", "*RPT0 - 25-pulse GITT*.csv"), recursive=True))
build, test = cells[:4], cells[4:]

# ---- gitt: dinlenme sonu noktaları
pts = []
for f in build:
    t, v, i, soc, Q = load(f)
    on = i > 0.05
    ends = np.flatnonzero(on[:-1] & ~on[1:]) + 1          # darbe bitişi
    starts = np.flatnonzero(~on[:-1] & on[1:]) + 1
    pts.append((1.0, v[starts[0] - 1]))                    # tam şarj sonrası dinlenmiş
    for e in ends:
        nx = starts[starts > e]
        k = (nx[0] if len(nx) else len(v)) - 1
        pts.append((soc[k], v[k]))
P = np.array(sorted(pts))
g_soc = np.round(P[:, 0], 2)
gx = pd.DataFrame(P, columns=["s", "v"]).groupby(np.round(P[:, 0] * 50) / 50).median()
ocv_gitt = np.interp(SOC, gx.s.values, gx.v.values)
c10 = pd.read_csv(os.path.join(HERE, "ocv_kirkaldy.csv")).ocv_kirkaldy.values
# karma: c10 şekli, gitt noktalarına göre kaydırma (kaydırma gitt aralığında yumuşak)
off = np.interp(SOC, gx.s.values, gx.v.values - np.interp(gx.s.values, SOC, c10))
karma = c10 + off
TAB = {"chen": cp.ocv_tab, "c10": c10, "gitt": ocv_gitt, "karma": karma}
pd.DataFrame({"soc": SOC, **TAB}).to_csv(os.path.join(HERE, "ocv_tablolari.csv"), index=False)
print(f"gitt OCV noktalari: {len(P)} (hucre A-D), SOC araligi {P[:, 0].min():.3f}..{P[:, 0].max():.3f}")


def sim(t, i, soc0, Q, tab):
    v1 = v2 = 0.0
    soc = soc0
    out = np.empty_like(t)
    for k in range(len(t)):
        dt = t[k] - t[k - 1] if k else 0.0
        a1, a2 = np.exp(-dt / T1), np.exp(-dt / T2)
        v1 = a1 * v1 + R1 * (1 - a1) * i[k]
        v2 = a2 * v2 + R2 * (1 - a2) * i[k]
        soc -= i[k] * dt / 3600 / Q
        out[k] = np.interp(soc, SOC, tab) - R0 * i[k] - v1 - v2
    return out


res, keep = {k: [] for k in TAB}, {}
for n, f in enumerate(test):
    t, v, i, soc, Q = load(f)
    m = v > 2.9
    for k, tab in TAB.items():
        vs = sim(t, i, 1.0, Q, tab)
        res[k].append(np.sqrt(np.mean((vs[m] - v[m]) ** 2)) * 1e3)
        if n == 0:
            keep[k] = vs
    if n == 0:
        keep["t"], keep["v"] = t, v
print("GITT gerilim RMSE [mV], hucre E-H (tabloyu kurmayan), V > 2,9 V, ayni 2-RC:")
for k, r in res.items():
    print(f"  {k:6s} medyan {np.median(r):5.1f}  en kotu {max(r):5.1f}")
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 1, figsize=(10, 6.5))
    tt = (keep["t"] - keep["t"][0]) / 3600
    ax[0].plot(tt, keep["v"], "k", lw=1, label="Measured (cell E)")
    for k, c in (("chen", "C0"), ("karma", "C3")):
        ax[0].plot(tt, keep[k], c, lw=0.8, label=f"model, OCV: {k} (RMSE {np.median(res[k]):.0f} mV)")
    ax[0].set_ylabel("V"); ax[0].set_xlabel("time [h]"); ax[0].legend(fontsize=8)
    for k, c in (("chen", "C0"), ("c10", "C1"), ("gitt", "C2"), ("karma", "C3")):
        ax[1].plot(SOC, 1e3 * (TAB[k] - ocv_gitt), c, marker=".", lw=0.8, label=k)
    ax[1].plot(P[:, 0], 1e3 * (P[:, 1] - np.interp(P[:, 0], SOC, ocv_gitt)), "k.", ms=2, label="GITT relaxed points")
    ax[1].set_ylim(-80, 120); ax[1].set_xlabel("SOC"); ax[1].set_ylabel("OCV - gitt [mV]"); ax[1].legend(fontsize=8)
    fig.suptitle("OCV table candidates for LG M50T (Kirkaldy et al. 2024) - cross-validated on cells E-H")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "ocv_dogrulama.png"), dpi=130)
    print("sekil: ocv_dogrulama.png")
except Exception as e:
    print("sekil yok:", e)
