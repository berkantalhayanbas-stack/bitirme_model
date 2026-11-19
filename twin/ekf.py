"""
Paket seviyesinde Genişletilmiş Kalman Filtresi (EKF) — SOC kestirimi.

Durum vektörü (3 durumlu):  x = [SOC, V1, V2]^T
Durum vektörü (4 durumlu):  x = [SOC, V1, V2, b_I]^T   (akım sensörü kayması)

Model:
  SOC_k+1 = SOC_k - dt/(3600 Q) * (I_m - b)
  V1_k+1  = a1 V1_k + R1 (1-a1) (I_m - b)
  V2_k+1  = a2 V2_k + R2 (1-a2) (I_m - b)
  b_k+1   = b_k
  y_k     = OCV(SOC) - R0 (I_m - b) - V1 - V2

Jacobianlar:
  A = [[1, 0, 0,  dt/(3600Q)],
       [0, a1, 0, -R1(1-a1)],
       [0, 0, a2, -R2(1-a2)],
       [0, 0, 0,  1]]
  C = [dOCV/dSOC, -1, -1, R0]

OCV(SOC) burada ölçüm tablosundan uydurulmuş 5. derece polinomdur;
dijital ikiz ise tabloyu kullanır -> bilinçli model uyumsuzluğu
("inverse crime" önlenir).
STM32'ye taşınırken bu dosya satır satır C'ye çevrilecek (3x3/4x4 matris).
"""
import numpy as np


class PackEKF:
    def __init__(self, pack_eq, ocv_poly_cell, ns, dt, soc0=0.5,
                 estimate_bias=True, q_diag=None, r_meas=0.25 ** 2,
                 ea_r0=6200.0, ea_r1=17500.0, ea_r2=14300.0, use_temp=True, gate=10.0):
        self.Q_ah = pack_eq["Q_pack_Ah"]
        self.R0_ref = self.R0 = pack_eq["R0_pack"]
        self.ea_r0, self.ea_r1, self.ea_r2, self.use_temp = ea_r0, ea_r1, ea_r2, use_temp
        self.R1_ref = self.R1 = pack_eq["R1_pack"]; self.C1 = pack_eq["C1_pack"]
        self.R2_ref = self.R2 = pack_eq["R2_pack"]; self.C2 = pack_eq["C2_pack"]
        self.ns, self.dt = ns, dt
        self.p = np.poly1d(ocv_poly_cell)
        self.dp = self.p.deriv()
        self.nb = estimate_bias
        self.gate = gate          # normalize inovasyon kapısı [sigma]; None = kapalı
        self.rejected = False
        self.n_rej = 0            # art arda reddedilen örnek sayısı
        self.N_REJ_MAX = 5        # EMI sıçraması tek örnektir; 5 örnek (0.5 s) üst üste
                                  # red = ölçüm değil model yanlış -> kapıyı aç
        n = 4 if estimate_bias else 3
        self.x = np.zeros(n)
        self.x[0] = soc0
        # başlangıç belirsizliği: dinlenme sonrası RC gerilimleri ~0 bilindiği için küçük (0.01 V^2)
        self.P = np.diag([0.1, 0.01, 0.01, 1.0][:n])
        if q_diag is None:
            q_diag = [1e-10, 1e-6, 1e-6, 1e-8][:n]
        self.Qn = np.diag(q_diag)
        self.Rn = r_meas
        self.a1 = np.exp(-dt / (self.R1 * self.C1))
        self.a2 = np.exp(-dt / (self.R2 * self.C2))

    def ocv(self, soc):
        return self.ns * self.p(np.clip(soc, 0, 1))

    def docv(self, soc):
        return self.ns * self.dp(np.clip(soc, 0, 1))

    def step(self, i_meas, v_meas, t_surf=25.0):
        x, dt = self.x, self.dt
        # R0(T): CAN 0x101'den gelen yüzey sıcaklığıyla Arrhenius düzeltmesi
        if self.use_temp:
            f = lambda ea: np.exp(ea / 8.314 * (1 / (t_surf + 273.15) - 1 / 298.15))
            self.R0 = self.R0_ref * f(self.ea_r0)
            self.R1 = self.R1_ref * f(self.ea_r1)          # RC dalları da sıcaklığa bağlı
            self.R2 = self.R2_ref * f(self.ea_r2)          # (Kirkaldy 2024, veri/ea_kirkaldy.py)
            self.a1 = np.exp(-dt / (self.R1 * self.C1))
            self.a2 = np.exp(-dt / (self.R2 * self.C2))
        b = x[3] if self.nb else 0.0
        i = i_meas - b
        k = dt / (3600.0 * self.Q_ah)

        # ---- Tahmin (a priori) ----
        xp = x.copy()
        xp[0] = x[0] - k * i
        xp[1] = self.a1 * x[1] + self.R1 * (1 - self.a1) * i
        xp[2] = self.a2 * x[2] + self.R2 * (1 - self.a2) * i
        A = np.diag([1.0, self.a1, self.a2] + ([1.0] if self.nb else []))
        if self.nb:
            A[0, 3] = k
            A[1, 3] = -self.R1 * (1 - self.a1)
            A[2, 3] = -self.R2 * (1 - self.a2)
        P = A @ self.P @ A.T + self.Qn

        # ---- Düzeltme (a posteriori) ----
        y_hat = self.ocv(xp[0]) - self.R0 * i - xp[1] - xp[2]
        C = np.array([self.docv(xp[0]), -1.0, -1.0] + ([self.R0] if self.nb else []))
        S = C @ P @ C + self.Rn
        K = P @ C / S
        innov = v_meas - y_hat
        # Normalize inovasyon kapısı: fiziksel olarak imkânsız sıçramayı (EMI) reddet
        self.rejected = (self.gate is not None and abs(innov) > self.gate * np.sqrt(S)
                         and self.n_rej < self.N_REJ_MAX)
        self.n_rej = self.n_rej + 1 if self.rejected else 0
        if self.rejected:
            self.x, self.P = xp, P
            return self.x.copy(), innov
        self.x = xp + K * innov
        I_KC = np.eye(len(x)) - np.outer(K, C)
        self.P = I_KC @ P @ I_KC.T + self.Rn * np.outer(K, K)   # Joseph formu
        return self.x.copy(), innov
