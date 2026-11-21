"""
Termal anomali dedektörü: açıklanamayan ısı (HIL A2 bulgusu, 2026-11-21). C karşılığı:
bms_ecu/bms/common/bms_algo.c tanom_step; sabitler bms_config.h TA_* ile birebir aynı.

Sıcaklık gözlemcisi yalnız yüzeyi (Ts) ölçer ve ısıyı I^2R + ortamla açıklar. Gizli bir kaynak
(dış ısı, iç kısa devre başlangıcı) soğutma iletkenliğini (g) alt sınıra iter, Tc düşük kalır.
"Adyabatik zarf": bilinen ısının üst sınırı (q_k * q + q_off) ve SOĞUTMA YOK (ortam yüzeyden
sıcaksa en güçlü ısıtma g_max) varsayımıyla Ts'nin çıkabileceği en yüksek değer. İki kaydırmalı
pencere (win, yarım periyot kayık) ölçümden yeniden başlar. Süzülmüş ölçüm zarfı r_th aşar ve
n örnek sürerse anomali; bayrak kilitlenir (yeniden başlatmaya kadar).
"""
import numpy as np


class ThermalAnomaly:
    def __init__(self, cell, ns, np_, ocv_poly, dt, win=1200, age_min=100, r_th=1.5, n=10,
                 alpha=0.1, q_k=1.5, q_off=0.2, tc0=1.0, ts0=0.5, g_max=None):
        self.cc, self.cs, self.rc = cell.cc, cell.cs, cell.rc
        self.g_max = 4.0 / cell.ru if g_max is None else g_max
        self.ns, self.np_, self.dt = ns, np_, dt
        self.p = np.poly1d(ocv_poly)
        self.win, self.age_min, self.r_th, self.n_al = win, age_min, r_th, n
        self.alpha, self.q_k, self.q_off, self.tc0, self.ts0 = alpha, q_k, q_off, tc0, ts0
        self.tc, self.ts, self.age = [0.0, 0.0], [0.0, 0.0], [0, 0]
        self.k = self.n = 0
        self.t_f = 0.0
        self.started = False
        self.flag = False

    def step(self, i_pack, v_pack, soc_est, t_meas, t_amb, tc_hat, t_valid=True):
        if not t_valid:                       # ölçüm dönünce baştan
            self.started, self.n = False, 0
            return self.flag
        if not self.started:                  # ilk adımda iki zarf da başlar
            self.t_f, self.k, self.started, self.age = t_meas, 0, True, [-1, -1]
        self.t_f += self.alpha * (t_meas - self.t_f)
        i = i_pack / self.np_
        q = max(i * (self.p(np.clip(soc_est, 0, 1)) - v_pack / self.ns), 0.0) * self.q_k + self.q_off
        r = None
        for j in range(2):
            if self.k == j * (self.win // 2) or self.age[j] < 0:   # kaydırmalı yeniden başlatma
                self.tc[j], self.ts[j], self.age[j] = max(tc_hat, self.t_f) + self.tc0, self.t_f + self.ts0, 0
            tc, ts = self.tc[j], self.ts[j]
            g = self.g_max if t_amb > ts else 0.0
            self.tc[j] = tc + self.dt / self.cc * (q + (ts - tc) / self.rc)
            self.ts[j] = ts + self.dt / self.cs * (g * (t_amb - ts) - (ts - tc) / self.rc)
            self.age[j] += 1
            if self.age[j] >= self.age_min:
                r = self.t_f - self.ts[j] if r is None else max(r, self.t_f - self.ts[j])
        self.k = (self.k + 1) % self.win
        if r is not None:
            self.n = self.n + 1 if r > self.r_th else 0
            if self.n >= self.n_al:
                self.flag = True
        return self.flag
