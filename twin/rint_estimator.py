"""
Çevrimiçi iç direnç kestiricisi (sürüş sırasında, CAN ölçümlerinden).

Fikir: akım bir örnekte (0.1 s) aniden değişirse, gerilimdeki ani değişimin
neredeyse tamamı ohmik dirençten gelir (RC dalları 0.1 s'de ~%1 değişir, OCV hiç):
      ΔV ≈ -R_pack · ΔI
Bu, Kirkaldy verisindeki "0.1 s direnci" tanımıyla aynıdır -> ML modeline doğrudan girer.

Adımlar (her örnekte):
  1. |ΔI| >= dI_min (20 A) ise bir "olay" say (küçük basamaklarda gürültü baskın).
  2. Sıcaklık ve SOC etkisini çıkar (25 °C, orta SOC referansına normalize):
       f = exp(Ea/R (1/T - 1/298.15)) · (1 + 0.6 exp(-SOC/0.08))
     T: çekirdek sıcaklığı gözlemcisinin kestirimi; SOC: EKF kestirimi.
  3. En küçük kareler (büyük basamaklar daha çok ağırlık alır):
       R25 = Σ(-ΔV·ΔI / f) / Σ(ΔI²)       (hücre seviyesine: × Np/Ns)
     Unutma çarpanı λ ile (yavaş yaşlanmayı izlemek için) güncellenir.
  4. Kaba aykırı olayları ele: tek olay kestirimi 0.3..4 × R_BoL dışında ise at.
Çıkış: rr = R25 / R_BoL  (ML modelinin girdisi)
"""
import numpy as np


class RintEstimator:
    def __init__(self, r_bol=0.0264, ns=19, np_=12, ea=20000.0, di_min=20.0,
                 soc_min=0.2, lam=0.999):
        self.r_bol, self.k = r_bol, np_ / ns
        self.ea, self.di_min, self.soc_min, self.lam = ea, di_min, soc_min, lam
        self.num = 0.0
        self.den = 0.0
        self.n = 0
        self.prev = None

    def step(self, i_meas, v_meas, t_core_hat, soc_est, valid=True):
        if self.prev is not None and valid:
            di = i_meas - self.prev[0]
            dv = v_meas - self.prev[1]
            if abs(di) >= self.di_min and soc_est > self.soc_min:
                f = (np.exp(self.ea / 8.314 * (1 / (t_core_hat + 273.15) - 1 / 298.15))
                     * (1 + 0.6 * np.exp(-soc_est / 0.08)))
                r_ev = -dv / di * self.k / f
                if 0.3 * self.r_bol < r_ev < 4 * self.r_bol:
                    self.num = self.lam * self.num + (-dv * di / f) * self.k
                    self.den = self.lam * self.den + di * di
                    self.n += 1
        self.prev = (i_meas, v_meas)
        return self.rr()

    def rr(self):
        return self.num / self.den / self.r_bol if self.den > 0 else 1.0
