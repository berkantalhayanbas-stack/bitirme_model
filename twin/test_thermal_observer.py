"""
Çekirdek sıcaklığı gözlemcisi ön testi (Python): normal, hot_day, cooling_fault.
Karşılaştırılan yöntemler:
  1) Ts_meas           : "çekirdek = yüzey" varsayımı (en basit BMS)
  2) open-loop         : sadece model, nominal Ru, ölçüm düzeltmesi yok
  3) KF (Ru nominal)   : ölçüm düzeltmeli, g sabit
  4) EKF (g kestirimi) : önerilen yöntem
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
from thermal_observer import ThermalEKF

HERE = os.path.dirname(__file__)
DT = 0.1
ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
I = ref.i_pack.values
cell0 = CellParams()
mask = cell0.soc_tab >= 0.05
coef = np.polyfit(cell0.soc_tab[mask], cell0.ocv_tab[mask], 7)

SC = [("normal", 25.0, 1.0), ("hot_day", 40.0, 1.0), ("cooling_fault", 35.0, 4.0)]
rows, store = [], {}
for name, ta, ruf in SC:
    cell = CellParams(ru=cell0.ru * ruf)
    twin = PackTwin(cell, PackConfig(t_amb=ta), soc0=0.8)
    d = pd.DataFrame([twin.step(i, DT) for i in I])
    vm, im, tsm = measure(d.v_pack.values, d.i_pack.values, d.t_surf.values)
    ekf = PackEKF(twin.pack_equivalent(), coef, 19, DT, soc0=0.5)
    soc_est = np.array([ekf.step(a, b, c)[0][0] for a, b, c in zip(im, vm, tsm)])

    obs = {
        "EKF (g estimated)": ThermalEKF(cell0, 19, 12, coef, DT, t0=tsm[0], estimate_g=True),
        "KF (R_u nominal)": ThermalEKF(cell0, 19, 12, coef, DT, t0=tsm[0], estimate_g=False),
    }
    est = {k: [] for k in obs}
    ru_hat = []
    for k_ in range(len(I)):
        for k, o in obs.items():
            x, q, _ = o.step(im[k_], vm[k_], soc_est[k_], tsm[k_], ta)
            est[k].append(x[0])
            if k.startswith("EKF"):
                ru_hat.append(1 / x[2])
    # açık çevrim: aynı model, ölçüm yok
    ol = ThermalEKF(cell0, 19, 12, coef, DT, t0=ta, estimate_g=False)
    tc_ol = []
    for k_ in range(len(I)):
        q = ol.heat(im[k_], vm[k_], soc_est[k_])
        tc, ts, g = ol.x
        ol.x = np.array([tc + DT / ol.cc * (q + (ts - tc) / ol.rc),
                         ts + DT / ol.cs * (g * (ta - ts) - (ts - tc) / ol.rc), g])
        tc_ol.append(ol.x[0])
    est["Open-loop model"] = tc_ol
    est["T_surf measured"] = tsm

    after = ref.t.values > 60
    for k, e in est.items():
        err = np.asarray(e) - d.t_core.values
        rows.append(dict(Scenario=name, Method=k,
                         RMSE_C=np.sqrt(np.mean(err[after] ** 2)),
                         MaxAbs_C=np.max(np.abs(err[after]))))
    store[name] = (d, est, np.array(ru_hat), ta, ruf)

res = pd.DataFrame(rows)
pd.set_option("display.width", 140)
print(res.pivot(index="Method", columns="Scenario", values="MaxAbs_C").round(3))
print(res.pivot(index="Method", columns="Scenario", values="RMSE_C").round(3))
for name, (d, est, ru_hat, ta, ruf) in store.items():
    print(f"{name}: R_u true {cell0.ru*ruf:.1f} K/W, estimated at end {ru_hat[-1]:.2f}, "
          f"at 600 s {ru_hat[6000]:.2f}")

# grafik: cooling_fault
d, est, ru_hat, ta, ruf = store["cooling_fault"]
t = ref.t.values
fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
ax[0].plot(t, d.t_core, "k", lw=1.5, label="True T_core")
for k in ["T_surf measured", "Open-loop model", "KF (R_u nominal)", "EKF (g estimated)"]:
    ax[0].plot(t, est[k], lw=0.8, label=k)
ax[0].set_ylabel("Temperature [°C]"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
for k in ["T_surf measured", "Open-loop model", "KF (R_u nominal)", "EKF (g estimated)"]:
    ax[1].plot(t, np.asarray(est[k]) - d.t_core, lw=0.8, label=k)
ax[1].axhline(1, c="r", ls=":"); ax[1].axhline(-1, c="r", ls=":")
ax[1].set_ylabel("T_core error [°C]"); ax[1].set_ylim(-6, 3); ax[1].grid(alpha=.3)
ax[2].plot(t, ru_hat, label="Estimated R_u"); ax[2].axhline(cell0.ru * ruf, c="k", ls="--", label="True R_u")
ax[2].axhline(cell0.ru, c="g", ls=":", label="Nominal R_u")
ax[2].set_ylabel("R_u [K/W]"); ax[2].set_xlabel("Time [s]"); ax[2].legend(fontsize=8); ax[2].grid(alpha=.3)
fig.suptitle("Thermal observer, cooling fault (35 °C, R_u ×4) — Python prototype")
fig.tight_layout()
fig.savefig(os.path.join(HERE, "..", "results", "thermal_observer_py.png"), dpi=120)

# algılama istatistikleri
for name, (d, est, ru_hat, ta, ruf) in store.items():
    t = ref.t.values; a = t > 60
    above = np.nonzero(ru_hat > 2 * cell0.ru)[0]
    print(f"{name}: max R_u_hat after 60 s = {ru_hat[a].max():.2f}, first > 18 K/W at "
          f"{t[above[0]] if len(above) else float('nan'):.1f} s")
