"""
Ön filtre çalışması: gürültü azaltma ile gecikme arasındaki ödünleşim.

İki farklı kullanıcı için ayrı ayrı sorulur:
  A) EKF'nin girdisi: V ve I aynı alçak geçiren filtreden geçirilirse (hizalı kalsınlar diye)
     SOC kestirimi iyileşir mi?  (Beklenti: Kalman zaten optimal süzgeç; iki kez süzmek
     modelle uyumsuz gecikme ve renkli gürültü ekler.)
  B) Eşik tabanlı koruma: ölçülen sinyal bir eşiğin etrafında gürültüyle titreşir (chatter).
     Filtre titreşimi azaltır ama algılamayı geciktirir.
       B1: aşırı sıcaklık, T_surf (CAN) > 45 °C, cooling_fault senaryosu
       B2: alçak gerilim, V_pack/19 (CAN) < 2.8 V, deep_discharge senaryosu
     Referans: gürültüsüz gerçek sinyalin eşiği ilk geçtiği an.
Filtreler 10 Hz örneklemeye göre (simülasyon Ts = 0.1 s). STM32'de 100 Hz'e yeniden tasarlanır;
grup gecikmesi saniye cinsinden aynı kalacak şekilde.
MATLAB karşılığı (designfilt): simulink/prefilter_design.m
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import thesis_style as ts                       # ortak tez figür stili
ts.apply()
from scipy import signal

from battery_model import PackTwin, CellParams, PackConfig
from sensors import measure
from ekf import PackEKF

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "..", "results")
FS, DT = 10.0, 0.1
ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
I_STD = ref.i_pack.values
c0 = CellParams()
mask = c0.soc_tab >= 0.05
coef = np.polyfit(c0.soc_tab[mask], c0.ocv_tab[mask], 7)
PEQ = PackTwin(c0).pack_equivalent()

# ------------------------------------------------------------------ filtre bankası
F = {"None": (np.array([1.0]), np.array([1.0]))}
for n in (3, 5, 10):
    F[f"Moving average, {n} samples"] = (np.ones(n) / n, np.array([1.0]))
for tau in (0.2, 0.5, 2.0):
    a = np.exp(-DT / tau)
    F[f"1st-order IIR, tau {tau:g} s"] = (np.array([1 - a]), np.array([1, -a]))
for fc in (1.0, 0.5, 0.1):
    F[f"Butterworth 2nd order, {fc:g} Hz"] = signal.butter(2, fc, fs=FS)


def props(b, a):
    """DC grup gecikmesi [ms] ve beyaz gürültü için σ_out/σ_in."""
    if len(b) == 1 and len(a) == 1:
        return 0.0, 1.0
    _, gd = signal.group_delay((b, a), w=[1e-4], fs=FS)
    imp = np.zeros(2000); imp[0] = 1.0
    h = signal.lfilter(b, a, imp)                     # dürtü yanıtı
    return 1000 * gd[0] / FS, np.sqrt(np.sum(h ** 2))


def filt(b, a, x):
    """Filtreyi ilk örneğin kalıcı rejimiyle başlat (sıfırdan başlarsa EKF '0 V' görür)."""
    if len(b) == 1 and len(a) == 1:
        return x.copy()
    zi = signal.lfilter_zi(b, a) * x[0]
    return signal.lfilter(b, a, x, zi=zi)[0]


def truth(ta, ruf, soc0, I):
    tw = PackTwin(CellParams(ru=c0.ru * ruf), PackConfig(t_amb=ta), soc0=soc0)
    return pd.DataFrame([tw.step(i, DT) for i in I])


def crossings(x, thr, above):
    s = (x > thr) if above else (x < thr)
    first = np.argmax(s) if s.any() else None
    return first, int(np.sum(np.diff(s.astype(int)) == 1))   # ilk geçiş, kaç kez eşiğe girdi


D = {k: truth(*v) for k, v in {"normal": (25, 1, .8, I_STD), "aggressive":
     (25, 1, .8, np.clip(1.6 * I_STD, -40.7, 87.3)), "cooling_fault": (35, 4, .8, I_STD),
     "deep_discharge": (25, 1, .4, I_STD)}.items()}
M = {k: measure(d.v_pack.values, d.i_pack.values, d.t_surf.values) for k, d in D.items()}
t = np.arange(len(I_STD)) * DT

rows = []
for name, (b, a) in F.items():
    gd, nr = props(b, a)
    r = dict(Filter=name, Delay_ms=gd, Noise_ratio=nr)
    # ---- A) EKF girdisi ----
    for sc in ("normal", "aggressive"):
        vm, im, tm = M[sc]
        vf, if_ = filt(b, a, vm), filt(b, a, im)
        e = PackEKF(PEQ, coef, 19, DT, soc0=0.5)
        s = np.array([e.step(x, y, z)[0][0] for x, y, z in zip(if_, vf, tm)])
        err = 100 * (s - D[sc].soc.values)
        r[f"EKF RMSE {sc}"] = np.sqrt(np.mean(err[t > 60] ** 2))
    # ---- B1) aşırı sıcaklık ----
    tm = M["cooling_fault"][2]
    tf = filt(b, a, tm)
    k_true, _ = crossings(D["cooling_fault"].t_surf.values, 45.0, True)
    k_f, n_f = crossings(tf, 45.0, True)
    r["OT delay_s"] = (k_f - k_true) * DT
    r["OT entries"] = n_f
    # ---- B2) alçak gerilim ----
    vm = M["deep_discharge"][0] / 19
    vf = filt(b, a, vm)
    k_true, _ = crossings(D["deep_discharge"].v_pack.values / 19, 2.8, False)
    k_f, n_f = crossings(vf, 2.8, False)
    r["UV delay_s"] = (k_f - k_true) * DT
    r["UV entries"] = n_f
    rows.append(r)
    print(f"done: {name}")

R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "..", "results", "prefilter_study.csv"), index=False)
pd.set_option("display.width", 220)
print("\n=== Prefilter study (fs = 10 Hz) ===")
print("Delay: group delay at DC. Noise ratio: output/input std for white noise (lower = smoother).")
print("OT/UV delay: first threshold crossing of the filtered measurement minus that of the true signal")
print("(negative = noise triggers it EARLY). Entries: how many times the signal enters the alarm region.\n")
print(R.round(3).to_string(index=False))

# ------------------------------------------------------------------ grafik: titreşim örneği
k0 = np.argmax(D["cooling_fault"].t_surf.values > 45.0)
z = slice(k0 - 600, k0 + 900)
tm = M["cooling_fault"][2]
fig, ax = plt.subplots(1, 2, figsize=(12, 4.3))
ax[0].plot(t[z], tm[z], c=ts.MUTED, alpha=.5, lw=.6, label="Measured (CAN)")
for name, c in [("Moving average, 3 samples", "C0"), ("Butterworth 2nd order, 0.5 Hz", "C1")]:
    b, a = F[name]
    ax[0].plot(t[z], filt(b, a, tm)[z], c=c, lw=1.2, label=name)
ax[0].plot(t[z], D["cooling_fault"].t_surf.values[z], "k--", lw=1.2, label="True T_surf")
ts.ref_line(ax[0], 45, "45 °C")
ax[0].set_xlabel("Time [s]"); ax[0].set_ylabel("T_surf [°C]"); ax[0].legend(fontsize=8)
ax[0].set_title("Over-temperature threshold (45 °C): noise causes chatter", fontsize=10)
ax[0].grid(alpha=.3)
sel = R[R.Filter != "None"]
ax[1].scatter(sel.Delay_ms / 1000, sel["OT entries"], c="C1", label="Over-temperature (45 °C)")
ax[1].scatter(sel.Delay_ms / 1000, sel["UV entries"], c="C0", marker="s", label="Under-voltage (2.8 V)")
n0 = R[R.Filter == "None"]
ax[1].scatter([0, 0], [n0["OT entries"].iloc[0], n0["UV entries"].iloc[0]], c=["C1", "C0"],
              marker="x", s=60, label="No filter")
ax[1].set_xscale("symlog", linthresh=0.05); ax[1].set_yscale("symlog", linthresh=1)
ax[1].set_xlabel("Filter group delay [s]"); ax[1].set_ylabel("Entries into the alarm region")
ax[1].set_title("Trade-off: chatter vs detection delay", fontsize=10)
ax[1].grid(alpha=.3); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "prefilter_tradeoff.png"), dpi=200)
print("\nSaved: results/prefilter_study.csv, results/prefilter_tradeoff.png")
for fc in (0.5, 0.1):
    b, a = signal.butter(2, fc, fs=FS)
    print(f"Butterworth 2nd order {fc} Hz @ 10 Hz: b = {np.round(b, 8)}, a = {np.round(a, 8)}")
