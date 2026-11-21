"""
Termal anomali dedektörü testi (thermal_anomaly.py; C: bms_algo.c tanom_step).
  A) Tespit: dış ısı (A2, 0,5 °C/s), açılıştan hemen sonra dış ısı, parkta dış ısı, iç ısı (5 W/hücre)
  B) Yanlış alarm: S1-S7 kapalı çevrim senaryoları (soğutma arızası, derin deşarj, şarj, soğuk) ve
     ortam 0-40 °C, sürüş x0,6-1,6, gerçek parametre sapması (R0, ısı kapasiteleri, Rc, Ru) ile
     40 rastgele koşu
Çıktılar İngilizce: ../results/thermal_anomaly.csv, thermal_anomaly.png
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from closed_loop import run

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
I = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv")).i_pack.values
I_agg = np.clip(1.6 * I, -40.7, 87.3)
I_chg = -40.7 * np.ones(18000)


def summary(name, d, kind, t_fault=None):
    a = d.anom.values > 0
    st = d.state.values
    t_a = float(d.t[a.argmax()]) if a.any() else np.nan
    t_l = float(d.t[(st >= 3).argmax()]) if (st >= 3).any() else np.nan
    m = d.t.values >= (t_fault or 0.0)
    e = (d.tc_hat - d.tc).values[m]
    return dict(Scenario=name, Kind=kind, Fault_s=t_fault if t_fault is not None else np.nan,
                Alarm_s=t_a, Delay_s=t_a - t_fault if t_fault is not None else np.nan,
                LIMP_s=t_l, Tcore_at_alarm=float(d.tc[a.argmax()]) if a.any() else np.nan,
                Tcore_max=float(d.tc.max()), Tc_err_min=float(e.min()), Tc_err_max=float(e.max()))


rows, traces = [], {}
DET = [("ext_heat_600s", I[:9000], dict(fault="heat", t_fault=600.0)),
       ("ext_heat_2s_after_start", I[:3000], dict(fault="heat", t_fault=2.0)),
       ("ext_heat_parked", 0 * I[:3000], dict(fault="heat", t_fault=20.0)),
       ("int_heat_5W_600s", I[:12000], dict(fault="q_int", t_fault=600.0))]
for name, Id, kw in DET:
    d = run(Id, **kw)
    rows.append(summary(name, d, "detection", kw["t_fault"]))
    traces[name] = d
FA = [("S1_normal", I, {}), ("S2_thermal_40C_cooling_x4", I_agg, dict(T_amb=40, ru_factor=4)),
      ("S2b_cooling_x4_25C", I_agg, dict(ru_factor=4)), ("S3_deep_weak", I, dict(soc0=0.4, weak=True)),
      ("S4_charge", I_chg, dict(soc0=0.8, weak=True)), ("S5_cold_charge", I_chg, dict(T_amb=10, soc0=0.3)),
      ("S6_ntc_open", I, dict(fault="t_open")), ("S7_cold_drive", I, dict(T_amb=5))]
for name, Id, kw in FA:
    rows.append(summary(name, run(Id, **kw), "false_alarm"))
rng = np.random.default_rng(5)
for i in range(40):
    Ta = rng.uniform(0, 40)
    kc = rng.uniform(0.6, 1.6)
    tr = {"r0": rng.uniform(0.9, 1.4), "cc": rng.uniform(0.8, 1.1), "cs": rng.uniform(0.8, 1.2),
          "rc": rng.uniform(0.8, 1.3), "ru": rng.uniform(0.7, 4.0)}
    d = run(np.clip(kc * I[:12000], -40.7, 87.3), T_amb=Ta, soc0=rng.uniform(0.4, 0.95), truth=tr, seed=100 + i)
    rows.append(summary(f"random_{i:02d}", d, "false_alarm"))
R = pd.DataFrame(rows)
R.to_csv(os.path.join(RES, "thermal_anomaly.csv"), index=False)

det, fa = R[R.Kind == "detection"], R[R.Kind == "false_alarm"]
n_fa = int(fa.Alarm_s.notna().sum())
print(det[["Scenario", "Delay_s", "Tcore_at_alarm", "Tc_err_min", "Tc_err_max"]].to_string(index=False))
print(f"False-alarm runs: {len(fa)}, alarms: {n_fa}")
ok = det.Alarm_s.notna().all() and (det.Delay_s[det.Scenario != "int_heat_5W_600s"] < 15).all() and n_fa == 0
print(f"Acceptance (all hidden-heat cases detected, external heat < 15 s, no false alarm): {'PASS' if ok else 'FAIL'}")

fig, ax = plt.subplots(2, 1, figsize=(9, 6.5), sharex=False)
for a, name in zip(ax, ("ext_heat_600s", "int_heat_5W_600s")):
    d = traces[name]
    m = (d.t >= 540) & (d.t <= 900)
    a.plot(d.t[m], d.tc[m], label="True core T (twin)")
    a.plot(d.t[m], d.ts[m], label="True surface T (twin)")
    a.plot(d.t[m], d.tc_hat[m], "--", label="ECU core estimate")
    t_al = d.t[(d.anom > 0).values.argmax()]
    a.axvline(600, color="k", lw=0.8, ls=":")
    a.axvline(t_al, color="r", lw=1.0, ls="--", label=f"Anomaly flag ({t_al - 600:.1f} s)")
    a.set_ylabel("°C"); a.set_title(name.replace("_", " ")); a.legend(fontsize=8); a.grid(alpha=0.3)
ax[1].set_xlabel("time [s]")
fig.tight_layout()
fig.savefig(os.path.join(RES, "thermal_anomaly.png"), dpi=150)
