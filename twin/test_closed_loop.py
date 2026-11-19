"""
Karar mekanizması, kapalı çevrim senaryoları (Python prototipi). Simulink karşılığı: test_decision.m (B).
Not: Python'da zayıf grup ayrı bir ikiz (kendi zaman sabitleri ve sıcaklığı), Simulink'te ortak
sıcaklıklı; gürültü üreteçleri farklı. Sonuçlar aynı mertebede olmalı, birebir değil.
"""
import os
import numpy as np
import pandas as pd
from closed_loop import run

HERE = os.path.dirname(os.path.abspath(__file__))
ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
I = ref.i_pack.values
I_agg = np.clip(1.6 * I, -40.7, 87.3)
I_chg = -40.7 * np.ones(18000)
S = [("S1_normal", I, {}, [True]),
     ("S2_thermal", I_agg, dict(T_amb=40, ru_factor=4), [False, True]),
     ("S3_deep", I, dict(soc0=0.4, weak=True), [False, True]),
     ("S4_charge", I_chg, dict(soc0=0.8, weak=True), [False, True]),
     ("S5_cold_chg", I_chg, dict(T_amb=10, soc0=0.3), [False, True]),
     ("S6_ntc_open", I, dict(fault="t_open"), [True]),
     ("S7_cold_drive", I, dict(T_amb=5), [True]),
     # A1 (HIL 3. bulgu): modellenmemiş ısı; yalnız Python (Simulink ikizinde ısı enjeksiyonu yok)
     ("S8_ext_heat", I[:9000], dict(fault="heat", t_fault=600.0), [False, True]),
     ("S9_int_heat", I[:12000], dict(fault="q_int", t_fault=600.0), [False, True])]
def _first(d, m):
    return float(d.t[m.values.argmax()]) if m.any() else np.nan


rows = []
for name, Id, kw, decs in S:
    for dec in decs:
        d = run(Id, use_decision=dec, **kw)
        st = d.state.values
        rows.append(dict(Scenario=name, Decision="on" if dec else "off", Tcore_max=d.tc.max(),
                         Vcell_min=d.vmin.min(), Vcell_max=d.vmax.max(), I_dis_max=d.I.max(),
                         I_chg_max=-d.I.min(), pct_NORMAL=100 * np.mean(st == 1),
                         pct_DERATE=100 * np.mean(st == 2), pct_LIMP=100 * np.mean(st == 3),
                         pct_SAFE=100 * np.mean(st == 4), Transitions=int(np.sum(np.diff(st) != 0)),
                         Ah=d.I.sum() * 0.1 / 3600,
                         t_core55=_first(d, d.tc > 55), t_limp=_first(d, d.state >= 3),
                         t_core60=_first(d, d.tc > 60), t_safe=_first(d, d.state == 4)))
        print(f"done: {name} {'on' if dec else 'off'}")
T = pd.DataFrame(rows)
pd.set_option("display.width", 220)
print(T.round(3).to_string(index=False))
T.to_csv(os.path.join(HERE, "..", "results", "closed_loop_python.csv"), index=False)
