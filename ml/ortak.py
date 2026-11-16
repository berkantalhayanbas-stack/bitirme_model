"""
Ortak yardımcılar: veri yükleme ve fizik tabanlı yaşlanma modeli (karşılaştırma için).

Fizik modeli, veri/aging_calibration.py'deki modelin aynısıdır:
  fade = a·(S(DoD, m, T)·EFC)^z + α_cal(V, T)·days^0.75
Adil karşılaştırma için 3. adımda her test katmanında YENİDEN kalibre edilir
(test hücreleri kalibrasyona hiç girmez).
"""
import os
import json
import numpy as np
import pandas as pd
from scipy.optimize import least_squares

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "..", "simulink", "sonuclar")
os.makedirs(FIG, exist_ok=True)

# Her deneyin ortalama hücre gerilimi (takvim yaşlanması terimi için), aging_params.json'dan
V_MEAN = {"1": 3.5850, "2,2": 3.9690, "3": 4.1299, "4": 3.7758, "5": 3.9016}


def load(with_R=True):
    D = pd.read_csv(os.path.join(HERE, "dataset.csv"), dtype={"expt": str})
    D = D[D.in_scope]
    if with_R:
        D = D[D.has_R]
    D = D.copy()
    D["V"] = D.expt.map(V_MEAN)
    return D.reset_index(drop=True)


def _alpha(V, T):
    return np.maximum(0, 7.543 * V - 23.75) * 1e6 * np.exp(-6976 / (T + 273.15))


def _stress(p, dod, m, T):
    a, z, Kex, Ksoc, Klow, kh, kc, kSi = p
    main = np.exp(Ksoc * (m - .5) / .25) * np.exp(kh * np.maximum(0, T - 25)) \
        * np.exp(kc * np.maximum(0, 25 - T) * m)
    si = Klow * np.exp(-m / .1) * np.exp(kSi * (T - 25))
    ext = np.exp(np.log(2) / 10 * np.maximum(0, T - 42.3))
    return np.exp((dod - 1) / Kex) * (main + si) / (1 + Klow * np.exp(-5)) * ext


def physics_predict(p, d):
    S = _stress(p, d.dod.values, d.m.values, d["T"].values)
    return 1 - (p[0] * (S * d.efc.values) ** p[1] + _alpha(d.V.values, d["T"].values) * d.days.values ** .75)


def physics_fit(d):
    best = None
    for a0 in (.002, .004, .008):
        for ks0 in (.5, 1.5):
            r = least_squares(lambda p: physics_predict(p, d) - d.soh.values,
                              [a0, .57, .3, ks0, 20, .01, .05, .05],
                              bounds=([1e-6, .3, .02, -5, 0, 0, 0, 0], [1, 1.2, 5, 10, 1000, .2, .5, .3]),
                              x_scale="jac")
            if best is None or r.cost < best.cost:
                best = r
    return best.x
