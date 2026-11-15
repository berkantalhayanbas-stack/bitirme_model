"""
Çekirdek sıcaklığı gözlemcisi (thermal observer) — 3 durumlu EKF.

Sorun: Hücre içindeki (çekirdek) sıcaklık ölçülemez; sadece yüzeydeki NTC
okunur (CAN 0x101, 0.1 °C). Yüksek akımda çekirdek yüzeyden birkaç derece
sıcak olabilir; koruma kararları çekirdek sıcaklığına göre verilmeli.

Durum vektörü:  x = [Tc, Ts, g]^T,   g = 1/Ru  [W/K]  (yüzey-ortam iletkenliği)
  g'yi kestirmek, soğutma arızasını (fan durması, tıkanmış kanal) modeli
  bilmeden yakalamayı sağlar: g düşerse soğutma bozulmuştur.

Model (açık Euler, dt = 0.1 s):
  Tc+ = Tc + dt/Cc * ( q + (Ts - Tc)/Rc )
  Ts+ = Ts + dt/Cs * ( g (Ta - Ts) - (Ts - Tc)/Rc )
  g+  = g                                   (rastgele yürüyüş)
  y   = Ts                                  (NTC ölçümü)

Isı girdisi (ölçümlerden, Bernardi tersinmez kısım):
  q = i_cell * ( OCV_poly(SOC_ekf) - V_meas / Ns )
  SOC_ekf: SOC EKF'sinin çıkışı -> iki gözlemci zincir halinde çalışır.

Jacobian:
  A = [[1 - dt/(Cc Rc),  dt/(Cc Rc),                  0              ],
       [dt/(Cs Rc),      1 - dt/Cs (g + 1/Rc),        dt/Cs (Ta - Ts)],
       [0,               0,                           1              ]]
  C = [0, 1, 0]
"""
import numpy as np


class ThermalEKF:
    def __init__(self, cell, ns, np_, ocv_poly, dt, t0=25.0,
                 estimate_g=True, ru_nom=None,
                 q_diag=(1e-4, 1e-4, 1e-9), r_meas=0.3 ** 2 + 0.1 ** 2 / 12):
        self.cc, self.cs, self.rc = cell.cc, cell.cs, cell.rc
        self.g_nom = 1.0 / (ru_nom if ru_nom is not None else cell.ru)
        self.ns, self.np_, self.dt = ns, np_, dt
        self.p = np.poly1d(ocv_poly)
        self.est_g = estimate_g
        self.x = np.array([t0, t0, self.g_nom])
        # g başlangıç belirsizliği: nominalin ±%100'ü (1 sigma ~ g_nom)
        self.P = np.diag([1.0, 0.1, (self.g_nom) ** 2 if estimate_g else 0.0])
        self.Q = np.diag(q_diag if estimate_g else (q_diag[0], q_diag[1], 0.0))
        self.R = r_meas

    def heat(self, i_pack, v_pack_meas, soc_est):
        i = i_pack / self.np_
        return i * (self.p(np.clip(soc_est, 0, 1)) - v_pack_meas / self.ns)

    def step(self, i_pack, v_pack_meas, soc_est, ts_meas, t_amb, t_valid=True):
        dt, cc, cs, rc = self.dt, self.cc, self.cs, self.rc
        tc, ts, g = self.x
        q = self.heat(i_pack, v_pack_meas, soc_est)

        # ---- Tahmin ----
        xp = np.array([
            tc + dt / cc * (q + (ts - tc) / rc),
            ts + dt / cs * (g * (t_amb - ts) - (ts - tc) / rc),
            g,
        ])
        A = np.array([
            [1 - dt / (cc * rc), dt / (cc * rc), 0.0],
            [dt / (cs * rc), 1 - dt / cs * (g + 1 / rc), dt / cs * (t_amb - ts)],
            [0.0, 0.0, 1.0],
        ])
        if not self.est_g:
            A[1, 2] = 0.0
        P = A @ self.P @ A.T + self.Q

        # Sensör geçersizse (teşhis): sadece model ile devam (g'nin tahmini değişmez,
        # çünkü düzeltme olmadan g = sabit; öğrenilmiş soğutma değeri kullanılmaya devam eder)
        if not t_valid:
            self.x, self.P = xp, P
            return xp.copy(), q, 0.0

        # ---- Düzeltme (y = Ts) ----
        S = P[1, 1] + self.R
        K = P[:, 1] / S
        innov = ts_meas - xp[1]
        x = xp + K * innov
        x[2] = max(x[2], 0.2 * self.g_nom)          # fiziksel alt sınır (g > 0)
        C = np.array([0.0, 1.0, 0.0])
        I_KC = np.eye(3) - np.outer(K, C)
        self.P = I_KC @ P @ I_KC.T + self.R * np.outer(K, K)   # Joseph formu
        self.x = x
        return x.copy(), q, innov
