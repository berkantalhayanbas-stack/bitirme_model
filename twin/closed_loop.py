"""
Kapalı çevrim simülasyonu (Python prototipi): karar mekanizmasının ayarı ve testleri.

  sürücü talebi -> [I_allow ile sınırla] -> ikiz (ortalama + zayıf grup) -> CAN ölçümleri
  -> teşhis, SOC EKF, sıcaklık gözlemcisi -> karar mekanizması -> I_allow (0.1 s gecikmeli)

Simulink karşılığı: build_bms_model (Decision bloğu) + test_decision.m
"""
from dataclasses import replace

import numpy as np
import pandas as pd

from battery_model import PackTwin, CellParams, PackConfig
from ekf import PackEKF
from thermal_observer import ThermalEKF
from thermal_anomaly import ThermalAnomaly
from sensor_faults import SensorDiag
from decision import Decision, DecisionParams
from can_monitor import CanRx

DT = 0.1
c0 = CellParams()
_mask = c0.soc_tab >= 0.05
COEF = np.polyfit(c0.soc_tab[_mask], c0.ocv_tab[_mask], 7)
PEQ = PackTwin(c0).pack_equivalent()


def run(I_dem, T_amb=25.0, ru_factor=1.0, soc0=0.8, weak=False, use_decision=True,
        fault=None, t_fault=1200.0, seed=7, can=None, truth=None, noise=None, zero_check=True):
    """fault: None | 't_open' (NTC kopuk, -40 °C) | 'heat' (t_fault'tan sonra modellenmemiş dış ısı:
           iki düğüm 0,05 °C/örnek, yüzey 62 °C'ye kadar = twin_emu A2 butonu) | 'q_int' (çekirdeğe
           5 W/hücre ek ısı: iç kısa devre başlangıcı benzeri; gözlemcinin modelinde yok).
    can: None (arızasız CAN) | dict(mode, msg, t, dur) -> can_monitor.CanRx arıza enjeksiyonu
         (mode 1 kayıp, 2 CRC bozuk, 3 donmuş sayaç; msg 1 = 0x101, 2 = 0x102, 3 = ikisi).
    truth: duyarlılık analizi için ikizin (gerçeğin) parametre çarpanları, ör. {"r0": 1.2, "ru": 2};
           "ocv_off" [V] OCV tablosuna eklenir. ECU nominal parametrelerle çalışmaya devam eder.
    noise: ölçüm gürültüsü/kayması, varsayılan dict(sv=0.25, si=0.5, bias=0.5, st=0.3, sc=0.005).
    zero_check: açılış sıfır akım kontrolü (A9); False = eski davranış (karşılaştırma için)."""
    rng = np.random.default_rng(seed)
    tr = dict(truth or {})
    ocv_off = tr.pop("ocv_off", 0.0)
    base = replace(c0, **{k: getattr(c0, k) * f for k, f in tr.items()},
                   ocv_tab=c0.ocv_tab + ocv_off)
    nz = {**dict(sv=0.25, si=0.5, bias=0.5, st=0.3, sc=0.005), **(noise or {})}
    cell = replace(base, ru=base.ru * ru_factor)
    avg = PackTwin(cell, PackConfig(t_amb=T_amb), soc0=soc0)
    wk = PackTwin(replace(cell, capacity_ah=base.capacity_ah * 0.9, r0=base.r0 * 1.2,
                          r1=base.r1 * 1.2, r2=base.r2 * 1.2),
                  PackConfig(t_amb=T_amb), soc0=soc0) if weak else None
    ekf = PackEKF(PEQ, COEF, 19, DT, soc0=0.5, estimate_r=True,
                  zero_n=round(1.0 / DT) if use_decision and zero_check else 0)   # A9: kontaktör açıkken ofset
    th = None
    ta = ThermalAnomaly(c0, 19, 12, COEF, DT)
    diag = SensorDiag()
    dec = Decision()
    p = dec.p
    if not zero_check:
        p.t_zero = 0.0
    i_dis, i_chg = (0.0, 0.0) if use_decision else (dec.I_nom_dis, dec.I_nom_chg)
    q = lambda x, lsb: np.round(x / lsb) * lsb
    n = len(I_dem)
    canrx = CanRx(DT, **(can or {}))
    log = {k: np.zeros(n) for k in ("I", "soc", "soc_w", "tc", "ts", "vmin", "vmax", "soc_est",
                                    "tc_hat", "ru_hat", "anom", "state", "i_dis", "i_chg", "psi", "cause",
                                    "can_ok", "can_fault", "im", "vm", "tm", "vmin_m", "vmax_m",
                                    "psi_T", "psi_C", "psi_D", "psi_H", "psi_s", "dom", "tdot", "kr")}
    for k in range(n):
        I = float(np.clip(I_dem[k], -i_chg, i_dis))
        a = avg.step(I, DT)
        if fault in ("heat", "q_int") and k * DT >= t_fault:
            if fault == "q_int":
                avg.t_core += 5.0 / cell.cc * DT
            elif avg.t_surf < 62.0:
                avg.t_core += 0.05; avg.t_surf += 0.05
            a = dict(a, t_core=avg.t_core, t_surf=avg.t_surf)
        if wk is not None:
            w = wk.step(I, DT)
            v_pack = 18 * a["v_cell"] + w["v_cell"]
            vmin, vmax = min(a["v_cell"], w["v_cell"]), max(a["v_cell"], w["v_cell"])
            log["soc_w"][k] = w["soc"]
        else:
            v_pack, vmin, vmax = a["v_pack"], a["v_cell"], a["v_cell"]
            log["soc_w"][k] = a["soc"]
        # ---- CAN 0x101 ölçümleri (gürültü + kuantalama)
        vm = q(v_pack + nz["sv"] * rng.standard_normal(), 0.1)
        im = q(I + nz["bias"] + nz["si"] * rng.standard_normal(), 0.1)
        tm = q(a["t_surf"] + nz["st"] * rng.standard_normal(), 0.1)
        vmin_m = q(vmin + nz["sc"] * rng.standard_normal(), 0.001)
        vmax_m = q(vmax + nz["sc"] * rng.standard_normal(), 0.001)
        if fault == "t_open" and k * DT >= t_fault:
            tm = -40.0
        # ---- ECU CAN alımı: izleyici, kayıpta son geçerli değer
        (vm, im, tm), (vmin_m, vmax_m), can_ok, can_fault = canrx.step((vm, im, tm), (vmin_m, vmax_m))
        # ---- BMS kestirimi
        tv, iv = diag.step(im, tm)
        if th is None:
            th = ThermalEKF(c0, 19, 12, COEF, DT, t0=tm)
        x, _ = ekf.step(im, vm, tm if tv else th.x[1])
        g_prev = th.x[2]
        xt, _, _ = th.step(im, vm, x[0], tm, T_amb, t_valid=tv)
        # termal anomali: g donar (gizli ısı soğutma arızası sanılmasın), Tc ölçüme bağlı kararlı
        # hal sınırının altına inmez (iç kaynakta çekirdek yüzeyden sıcak); C: bms_step
        anom = ta.step(im, vm, x[0], tm, T_amb, xt[0], t_valid=tv)
        if anom:
            th.x[2] = g_prev
            if tv:
                th.x[0] = max(th.x[0], tm + dec.p.k_ss * (tm - T_amb))
            xt = th.x.copy()
        if use_decision:
            st, i_dis, i_chg, psi, cause = dec.step(im, vmin_m, vmax_m, xt[0], xt[1], 1 / xt[2],
                                                    x[0], x[3], tv, iv, can_ok, tm, T_amb, anom,
                                                    x[4] if len(x) > 4 else 1.0)
        else:
            st, psi, cause = 1, 0.0, 0
        for key, val in zip(("psi_T", "psi_C", "psi_D", "psi_H"), dec.psi_i):
            log[key][k] = val
        log["psi_s"][k], log["dom"][k], log["tdot"][k] = dec.psi_s, dec.dom, dec.tdot
        log["kr"][k] = x[4] if len(x) > 4 else 1.0
        for key, val in (("I", I), ("soc", a["soc"]), ("tc", a["t_core"]), ("ts", a["t_surf"]),
                         ("vmin", vmin), ("vmax", vmax), ("soc_est", x[0]), ("tc_hat", xt[0]),
                         ("ru_hat", 1 / xt[2]), ("anom", anom), ("state", st), ("i_dis", i_dis), ("i_chg", i_chg),
                         ("psi", psi), ("cause", cause), ("can_ok", can_ok), ("can_fault", can_fault),
                         ("im", im), ("vm", vm), ("tm", tm), ("vmin_m", vmin_m), ("vmax_m", vmax_m)):
            log[key][k] = val
    df = pd.DataFrame(log)
    df.insert(0, "t", np.arange(n) * DT)
    return df
