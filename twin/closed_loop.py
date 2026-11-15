"""
Kapalı çevrim simülasyonu (Python prototipi): karar mekanizmasının ayarı ve testleri.

  sürücü talebi -> [I_allow ile sınırla] -> ikiz (ortalama + zayıf grup) -> CAN ölçümleri
  -> teşhis, SOC EKF, sıcaklık gözlemcisi -> karar mekanizması -> I_allow (0.1 s gecikmeli)

Simulink karşılığı: build_bms_model (Decision bloğu) + test_decision.m
"""
import numpy as np
import pandas as pd

from battery_model import PackTwin, CellParams, PackConfig
from ekf import PackEKF
from thermal_observer import ThermalEKF
from sensor_faults import SensorDiag
from decision import Decision, DecisionParams
from can_monitor import CanRx

DT = 0.1
c0 = CellParams()
_mask = c0.soc_tab >= 0.05
COEF = np.polyfit(c0.soc_tab[_mask], c0.ocv_tab[_mask], 7)
PEQ = PackTwin(c0).pack_equivalent()


def run(I_dem, T_amb=25.0, ru_factor=1.0, soc0=0.8, weak=False, use_decision=True,
        fault=None, t_fault=1200.0, seed=7, can=None):
    """fault: None | 't_open' (NTC kopuk, -40 °C).
    can: None (arızasız CAN) | dict(mode, msg, t, dur) -> can_monitor.CanRx arıza enjeksiyonu
         (mode 1 kayıp, 2 CRC bozuk, 3 donmuş sayaç; msg 1 = 0x101, 2 = 0x102, 3 = ikisi)."""
    rng = np.random.default_rng(seed)
    cell = CellParams(ru=c0.ru * ru_factor)
    avg = PackTwin(cell, PackConfig(t_amb=T_amb), soc0=soc0)
    wk = PackTwin(CellParams(ru=c0.ru * ru_factor, capacity_ah=c0.capacity_ah * 0.9,
                             r0=c0.r0 * 1.2, r1=c0.r1 * 1.2, r2=c0.r2 * 1.2),
                  PackConfig(t_amb=T_amb), soc0=soc0) if weak else None
    ekf = PackEKF(PEQ, COEF, 19, DT, soc0=0.5)
    th = None
    diag = SensorDiag()
    dec = Decision()
    p = dec.p
    i_dis, i_chg = (0.0, 0.0) if use_decision else (dec.I_nom_dis, dec.I_nom_chg)
    q = lambda x, lsb: np.round(x / lsb) * lsb
    n = len(I_dem)
    canrx = CanRx(DT, **(can or {}))
    log = {k: np.zeros(n) for k in ("I", "soc", "soc_w", "tc", "ts", "vmin", "vmax", "soc_est",
                                    "tc_hat", "ru_hat", "state", "i_dis", "i_chg", "psi", "cause",
                                    "can_ok", "can_fault")}
    for k in range(n):
        I = float(np.clip(I_dem[k], -i_chg, i_dis))
        a = avg.step(I, DT)
        if wk is not None:
            w = wk.step(I, DT)
            v_pack = 18 * a["v_cell"] + w["v_cell"]
            vmin, vmax = min(a["v_cell"], w["v_cell"]), max(a["v_cell"], w["v_cell"])
            log["soc_w"][k] = w["soc"]
        else:
            v_pack, vmin, vmax = a["v_pack"], a["v_cell"], a["v_cell"]
            log["soc_w"][k] = a["soc"]
        # ---- CAN 0x101 ölçümleri (gürültü + kuantalama)
        vm = q(v_pack + 0.25 * rng.standard_normal(), 0.1)
        im = q(I + 0.5 + 0.5 * rng.standard_normal(), 0.1)
        tm = q(a["t_surf"] + 0.3 * rng.standard_normal(), 0.1)
        vmin_m = q(vmin + 0.005 * rng.standard_normal(), 0.001)
        vmax_m = q(vmax + 0.005 * rng.standard_normal(), 0.001)
        if fault == "t_open" and k * DT >= t_fault:
            tm = -40.0
        # ---- ECU CAN alımı: izleyici, kayıpta son geçerli değer
        (vm, im, tm), (vmin_m, vmax_m), can_ok, can_fault = canrx.step((vm, im, tm), (vmin_m, vmax_m))
        # ---- BMS kestirimi
        tv, iv = diag.step(im, tm)
        if th is None:
            th = ThermalEKF(c0, 19, 12, COEF, DT, t0=tm)
        x, _ = ekf.step(im, vm, tm if tv else th.x[1])
        xt, _, _ = th.step(im, vm, x[0], tm, T_amb, t_valid=tv)
        if use_decision:
            st, i_dis, i_chg, psi, cause = dec.step(im, vmin_m, vmax_m, xt[0], xt[1], 1 / xt[2],
                                                    x[0], x[3], tv, iv, can_ok)
        else:
            st, psi, cause = 1, 0.0, 0
        for key, val in (("I", I), ("soc", a["soc"]), ("tc", a["t_core"]), ("ts", a["t_surf"]),
                         ("vmin", vmin), ("vmax", vmax), ("soc_est", x[0]), ("tc_hat", xt[0]),
                         ("ru_hat", 1 / xt[2]), ("state", st), ("i_dis", i_dis), ("i_chg", i_chg),
                         ("psi", psi), ("cause", cause), ("can_ok", can_ok), ("can_fault", can_fault)):
            log[key][k] = val
    df = pd.DataFrame(log)
    df.insert(0, "t", np.arange(n) * DT)
    return df
