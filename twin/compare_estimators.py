"""
SOC kestirim yöntemlerinin karşılaştırması (6 senaryo, aynı gürültülü CAN ölçümleri).

Yöntemler:
  1. Coulomb counting (50% start)   : EKF ile aynı yanlış başlangıç, düzeltme yok
  2. Coulomb counting (OCV start)   : başlangıç SOC'si ilk ölçümden OCV ile; sonra sadece akım
  3. OCV lookup                     : her örnekte SOC = OCV^-1(V/Ns), yük altında IR düşümü ihmal
  4. OCV lookup, IR-compensated     : SOC = OCV^-1((V + R0·I)/Ns)
  5. EKF, fixed R0                  : 3 durum, sıcaklık düzeltmesi yok
  6. EKF, R0(T)                     : 3 durum, Arrhenius sıcaklık düzeltmesi
  7. EKF, R0(T) + current bias      : 4 durum (önerilen; Simulink'teki EKF bloğu)
Metrikler (60 s sonrası): RMSE, maks. |hata|, son hata; yakınsama: |hata| son kez > %2 anı.
Simulink EKF bloğu ile Python 7. yöntem çapraz doğrulandı (sonuclar.md, 10 Kasım).
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from battery_model import PackTwin, CellParams, PackConfig
from sensors import measure
from ekf import PackEKF

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "..", "simulink", "sonuclar")
DT = 0.1
ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
I_STD = ref.i_pack.values
c0 = CellParams()
mask = c0.soc_tab >= 0.05
coef = np.polyfit(c0.soc_tab[mask], c0.ocv_tab[mask], 7)
PEQ = PackTwin(c0).pack_equivalent()

SC = [("normal", 25, 1, .8, I_STD), ("hot_day", 40, 1, .8, I_STD), ("cooling_fault", 35, 4, .8, I_STD),
      ("aggressive", 25, 1, .8, np.clip(1.6 * I_STD, -40.7, 87.3)), ("deep_discharge", 25, 1, .4, I_STD),
      ("long_charge", 25, 1, .2, -30 * np.ones(36000))]

# OCV^-1: hücre OCV tablosunun tersi (monoton)
def ocv_inv(v_cell):
    return np.interp(v_cell, c0.ocv_tab, c0.soc_tab)


rows, store = [], {}
for name, ta, ruf, s0, I in SC:
    twin = PackTwin(CellParams(ru=c0.ru * ruf), PackConfig(t_amb=ta), soc0=s0)
    d = pd.DataFrame([twin.step(i, DT) for i in I])
    vm, im, tm = measure(d.v_pack.values, d.i_pack.values, d.t_surf.values)
    t = np.arange(len(I)) * DT
    k = DT / (3600 * PEQ["Q_pack_Ah"])
    est = {}
    est["Coulomb counting (50% start)"] = 0.5 - k * np.cumsum(im)
    est["Coulomb counting (OCV start)"] = ocv_inv(vm[0] / 19) - k * np.cumsum(im)
    est["OCV lookup"] = ocv_inv(vm / 19)
    r0T = PEQ["R0_pack"] * np.exp(20000 / 8.314 * (1 / (tm + 273.15) - 1 / 298.15))
    est["OCV lookup, IR-compensated"] = ocv_inv((vm + r0T * im) / 19)
    for lab, nb, ut in [("EKF, fixed R0", False, False), ("EKF, R0(T)", False, True),
                        ("EKF, R0(T) + bias (proposed)", True, True)]:
        e = PackEKF(PEQ, coef, 19, DT, soc0=0.5, estimate_bias=nb, use_temp=ut)
        est[lab] = np.array([e.step(a, b, c)[0][0] for a, b, c in zip(im, vm, tm)])
    after = t > 60
    for lab, s in est.items():
        err = 100 * (s - d.soc.values)
        out = np.nonzero(np.abs(err) > 2)[0]
        rows.append(dict(Scenario=name, Method=lab, RMSE=np.sqrt(np.mean(err[after] ** 2)),
                         MaxErr=np.max(np.abs(err[after])), EndErr=err[-1],
                         Conv_s=(out[-1] + 1) * DT if len(out) else 0.0))
    store[name] = (t, d.soc.values, est)
    print(f"done: {name}")

R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "..", "results", "estimator_comparison.csv"), index=False)
pd.set_option("display.width", 200)
order = list(dict.fromkeys(R.Method))
for metric, lab in [("RMSE", "RMSE after 60 s [%]"), ("MaxErr", "max |error| after 60 s [%]"),
                    ("Conv_s", "last time |error| > 2 % [s]")]:
    print(f"\n=== {lab} ===")
    print(R.pivot(index="Method", columns="Scenario", values=metric).loc[order,
          [s[0] for s in SC]].round(2).to_string())

# ------------------------------------------------------------------ grafikler
t, soc, est = store["normal"]
fig, ax = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True)
ax[0].plot(t / 60, 100 * soc, "k", lw=1.8, label="True SOC")
sty = {"Coulomb counting (50% start)": ("C7", "--"), "Coulomb counting (OCV start)": ("C1", "-"),
       "OCV lookup": ("C0", "-"), "OCV lookup, IR-compensated": ("C9", "-"),
       "EKF, fixed R0": ("C4", "-"), "EKF, R0(T)": ("C5", "-"), "EKF, R0(T) + bias (proposed)": ("C3", "-")}
for lab, s in est.items():
    c, ls = sty[lab]
    ocv = lab.startswith("OCV lookup")          # gürültülü: soluk ve arkada çiz
    kw = dict(c=c, ls=ls, lw=.5 if ocv else 1.1, alpha=.3 if ocv else 1, zorder=1 if ocv else 3)
    ax[0].plot(t / 60, 100 * s, label=lab, **kw)
    ax[1].plot(t / 60, 100 * (s - soc), **kw)
ax[0].set_ylabel("SOC [%]"); ax[0].legend(fontsize=7.5, ncol=2); ax[0].grid(alpha=.3)
ax[0].set_ylim(20, 95)
ax[1].set_ylim(-8, 8); ax[1].set_ylabel("SOC error [%]"); ax[1].set_xlabel("Time [min]"); ax[1].grid(alpha=.3)
ax[0].set_title("SOC estimators on the same noisy CAN data (normal scenario, +0.5 A current-sensor bias)")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "estimator_comparison_normal.png"), dpi=200)

P = R.pivot(index="Method", columns="Scenario", values="RMSE").loc[order, [s[0] for s in SC]]
fig, ax = plt.subplots(figsize=(10, 4.2))
im = ax.imshow(np.log10(P.values), cmap="RdYlGn_r", aspect="auto", vmin=-1, vmax=1.3)
for i in range(P.shape[0]):
    for j in range(P.shape[1]):
        ax.text(j, i, f"{P.values[i, j]:.2f}", ha="center", va="center", fontsize=8)
ax.set_xticks(range(P.shape[1])); ax.set_xticklabels(P.columns, fontsize=8)
ax.set_yticks(range(P.shape[0])); ax.set_yticklabels(P.index, fontsize=8)
ax.set_title("SOC RMSE after 60 s [%] (colour: log scale; target < 1.5 %)", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "estimator_comparison_table.png"), dpi=200)
print("\nSaved: results/estimator_comparison.csv, simulink/sonuclar/estimator_comparison_*.png")

# ------------------------------------------------------------------ kayma durumunun değeri
print("\n=== Value of the bias state: larger current-sensor offsets (normal scenario) ===")
twin = PackTwin(c0, PackConfig(t_amb=25), soc0=.8)
d = pd.DataFrame([twin.step(i, DT) for i in I_STD])
t = np.arange(len(I_STD)) * DT
print(" offset [A]   3-state EKF RMSE / max [%]   4-state EKF RMSE / max [%]   bias estimate [A]")
for bias in (0.5, 2.0, 3.0):
    vm, im, tm = measure(d.v_pack.values, d.i_pack.values, d.t_surf.values, bias_i=bias)
    out = []
    for nb in (False, True):
        e = PackEKF(PEQ, coef, 19, DT, soc0=0.5, estimate_bias=nb)
        x = np.array([e.step(a, b, c)[0] for a, b, c in zip(im, vm, tm)])
        err = 100 * (x[:, 0] - d.soc.values)
        out += [np.sqrt(np.mean(err[t > 60] ** 2)), np.max(np.abs(err[t > 60]))]
    print(f" {bias:9.1f}   {out[0]:10.3f} / {out[1]:5.2f}            {out[2]:10.3f} / {out[3]:5.2f}"
          f"            {x[-1, 3]:6.2f}")
