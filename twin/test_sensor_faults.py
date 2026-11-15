"""
Sensör arıza kütüphanesi ön testi (Python). Arıza anı t_f = 1200 s.
Her arıza için "teşhis yok" ve "teşhis var" sonuçları karşılaştırılır.
Ayrıca 6 normal senaryoda yanlış alarm olmadığı kontrol edilir.
"""
import os
import numpy as np
import pandas as pd

from battery_model import PackTwin, CellParams, PackConfig
from sensors import noisy, can_q
from ekf import PackEKF
from thermal_observer import ThermalEKF
from sensor_faults import inject, SensorDiag, FAULTS

HERE = os.path.dirname(__file__)
DT, T_F = 0.1, 1200.0
import sys
GATE = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
I_STD = ref.i_pack.values
cell0 = CellParams()
mask = cell0.soc_tab >= 0.05
coef = np.polyfit(cell0.soc_tab[mask], cell0.ocv_tab[mask], 7)


def truth(ta, ruf, soc0, I):
    twin = PackTwin(CellParams(ru=cell0.ru * ruf), PackConfig(t_amb=ta), soc0=soc0)
    return pd.DataFrame([twin.step(i, DT) for i in I])


def run(d, ta, mode, use_diag):
    v, i, t = noisy(d.v_pack.values, d.i_pack.values, d.t_surf.values)
    v, i, t = inject(v, i, t, mode, T_F)
    vm, im, tm = can_q(v), can_q(i), can_q(t)
    ekf = PackEKF({"Q_pack_Ah": 4.85 * 12, "R0_pack": .0264 * 19 / 12, "R1_pack": .0093 * 19 / 12,
                   "C1_pack": 1075 * 12 / 19, "R2_pack": .012 * 19 / 12, "C2_pack": 15000 * 12 / 19},
                  coef, 19, DT, soc0=0.5, gate=GATE if use_diag else None)
    th = ThermalEKF(cell0, 19, 12, coef, DT, t0=tm[0])
    diag = SensorDiag()
    n = len(vm)
    out = dict(soc=np.zeros(n), bias=np.zeros(n), tc=np.zeros(n), tv=np.ones(n, bool),
               iv=np.ones(n, bool), rej=np.zeros(n, bool))
    for k in range(n):
        tv, iv = diag.step(im[k], tm[k])
        x, _ = ekf.step(im[k], vm[k], tm[k] if (tv or not use_diag) else th.x[1])
        xt, _, _ = th.step(im[k], vm[k], x[0], tm[k], ta, t_valid=(tv or not use_diag))
        out["soc"][k], out["bias"][k], out["tc"][k] = x[0], x[3], xt[0]
        out["tv"][k], out["iv"][k], out["rej"][k] = tv, iv, ekf.rejected
    return out


t = ref.t.values
post = t >= T_F
rows = []
cases = [(1, "normal", 25, 1), (2, "normal", 25, 1), (3, "cooling_fault", 35, 4),
         (4, "cooling_fault", 35, 4), (5, "normal", 25, 1)]
truths = {"normal": truth(25, 1, 0.8, I_STD), "cooling_fault": truth(35, 4, 0.8, I_STD)}
for mode, sc, ta, ruf in cases:
    d = truths[sc]
    for use_diag in (False, True):
        o = run(d, ta, mode, use_diag)
        e_soc = np.abs(o["soc"] - d.soc.values)[post] * 100
        e_tc = np.abs(o["tc"] - d.t_core.values)[post]
        flag = ~(o["tv"] & o["iv"])
        t_det = t[np.argmax(flag)] - T_F if flag.any() else np.nan
        rows.append(dict(Fault=FAULTS[mode], Scenario=sc, Diagnostics="on" if use_diag else "off",
                         SOC_err_max=e_soc.max(), SOC_err_end=e_soc[-1],
                         Tcore_err_max=e_tc.max(), Detect_delay_s=t_det if use_diag else np.nan,
                         V_rejected=int(o["rej"].sum()), Bias_end=o["bias"][-1]))
res = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(res.round(3).to_string(index=False))

# yanlış alarm kontrolü: arızasız 6 senaryo
print("\nFalse-alarm check (no fault injected):")
SC6 = [("normal", 25, 1, .8, I_STD), ("hot_day", 40, 1, .8, I_STD), ("cooling_fault", 35, 4, .8, I_STD),
       ("aggressive", 25, 1, .8, np.clip(1.6 * I_STD, -40.7, 87.3)), ("deep_discharge", 25, 1, .4, I_STD),
       ("long_charge", 25, 1, .2, -30 * np.ones(36000))]
for name, ta, ruf, s0, I in SC6:
    d = truths.get(name) if name in truths else truth(ta, ruf, s0, I)
    o = run(d, ta, 0, True)
    print(f"  {name:15s} T invalid: {(~o['tv']).sum():5d}  I invalid: {(~o['iv']).sum():5d}  "
          f"V rejected: {o['rej'].sum():3d}")
