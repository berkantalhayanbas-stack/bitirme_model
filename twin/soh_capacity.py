"""
Kapasite SOH'u, park-park arası (ECU: bms_ecu/bms/common/bms_algo.c soh_*; tasarım docs/soh_design.md).

Dinlenmiş gerilim OCV tablosundan kapasiteden bağımsız SOC verir. İki dinlenme arasında sayılan Ah,
iki dinlenme SOC'sinin farkına bölünürse kapasite çıkar:
    Q_ölç = Ah(A -> B) / (SOC_ocv(A) - SOC_ocv(B))
- Dinlenme: süzülmüş (I - b0) mutlak değeri < 0,5 A, 20 dk kesintisiz; nokta son 10 s'nin ortalamasıyla
  alınır (ham gerilim, gevşeme bitmiş). Aynı pencerenin akım ortalaması sensör ofsetini (b0) yeniler;
  açılışta ilk 1 s (kontaktör açık) ofset ölçülür. EKF'nin b_I'si sürüşte kaydığı için kullanılmaz (A7).
- Uç noktada T 10-40 °C ve dOCV/dSOC >= 4 mV/% olmalı. Ölçüm için |dSOC| >= 0,30 ve sonuç nominalin
  0,5-1,1 katı. Kısa park çapayı bozmaz, ölçüm sonrası nokta yeni çapa olur. Arıza çapayı düşürür.
- Güncelleme: soh_c += w / (n + w) (oran - soh_c), w = min(1, |dSOC| / 0,8), n = min(ölçüm, 4) + 1
  (%100 önseli bir ölçüm sayılır). Gösterilen değer: düşüşe uyar, yükselişi güncelleme başına %1, en çok %100.
- Kalıcı kayıt (flash): soh_c, soh_disp, k_R, Ah toplamı, çapa (SOC, Ah), ölçüm sayısı.

Bu dosya C koduyla birebir: tüm durumlar float32 (numpy), aynı işlem sırası. Eşdeğerlik testi
test_soh_capacity.py (C izine karşı).
"""
import numpy as np

f32 = np.float32

BMS_TS = f32(0.1)
BMS_NS = 19
Q_NOM = f32(4.85) * f32(12)          # SOH_Q_NOM = CELL_Q_AH * BMS_NP
DEC_N_ZERO = 10
I_REST = f32(0.5)
I_FILT = f32(0.02)
N_REST = 12000
N_AVG = 100
DSOC_MIN = f32(0.30)
DSOC_W = f32(0.8)
SLOPE_MIN = f32(0.40)
T_MIN, T_MAX = f32(10.0), f32(40.0)
N_ANCHOR = 864000
R_MIN, R_MAX = f32(0.50), f32(1.10)
N_MAX = 5
DISP_UP = f32(0.01)
AH_SAVE = f32(1.0)
KR_SAVE = f32(0.02)
H = BMS_TS / f32(3600.0)

# Kirkaldy vd. (2024) LG M50T GITT dinlenme gerilimleri (battery_model.py / twin_model.c ile aynı veri)
OCV_SOC = np.array([0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
                    0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98, 1.0], dtype=f32)
OCV_V = np.array([2.9414, 3.0161, 3.1444, 3.2871, 3.4047, 3.4646, 3.5055, 3.5621, 3.6086, 3.6418,
                  3.6729, 3.7119, 3.7594, 3.8136, 3.8737, 3.9207, 3.9641, 4.0162, 4.0619, 4.0873,
                  4.112, 4.1519, 4.1845], dtype=f32)

EV_NONE, EV_ANCHOR, EV_ACCEPT, EV_SMALL, EV_RANGE, EV_POINT = range(6)


def soc_from_ocv(ocv_cell):
    """Tablonun tersi, doğrusal ara değer. Dönüş (SOC, dOCV/dSOC [V])."""
    k = 1
    while k < len(OCV_V) - 1 and ocv_cell > OCV_V[k]:
        k += 1
    v0, v1, s0, s1 = OCV_V[k - 1], OCV_V[k], OCV_SOC[k - 1], OCV_SOC[k]
    slope = (v1 - v0) / (s1 - s0)
    soc = s0 + (ocv_cell - v0) * (s1 - s0) / (v1 - v0)
    return f32(min(max(soc, f32(0.0)), f32(1.0))), slope


class SohCapacity:
    def __init__(self, rec=None):
        r = dict(soh_c=f32(1.0), soh_disp=f32(1.0), k_r=f32(1.0), ah_total=f32(0.0),
                 soc_a=f32(0.0), ah_a=f32(0.0), n_meas=0, anchor=0)
        if rec:
            r.update({k: (f32(v) if isinstance(v, float) else v) for k, v in rec.items()})
        self.r = r
        self.b0 = f32(0.0)
        self.n_zero = 0
        self.i_f = f32(0.0)
        self.n_rest = 0
        self.ocv_sum = f32(0.0)
        self.i_sum = f32(0.0)
        self.n_anchor = 0
        self.ah_saved = r["ah_total"]
        self.kr_saved = r["k_r"]
        self.persist = 0
        self.event = EV_NONE
        self.last_ratio = f32(0.0)
        self.last_soc = f32(0.0)

    def reset_anchor(self):
        if self.r["anchor"]:
            self.persist = 1
        self.r["anchor"] = 0
        self.n_rest = 0
        self.ocv_sum = f32(0.0)
        self.i_sum = f32(0.0)

    def _point(self, T_meas, k_r):
        r = self.r
        soc, slope = soc_from_ocv(self.ocv_sum / f32(N_AVG))
        self.b0 = self.i_sum / f32(N_AVG)
        ok = T_MIN <= T_meas <= T_MAX and slope >= SLOPE_MIN
        self.last_soc = soc
        if not ok:
            self.event = EV_POINT
        elif not r["anchor"]:
            r["anchor"], r["soc_a"], r["ah_a"] = 1, soc, f32(0.0)
            self.n_anchor = 0
            self.persist = 1
            self.event = EV_ANCHOR
        else:
            dsoc = r["soc_a"] - soc
            if abs(dsoc) < DSOC_MIN:
                self.event = EV_SMALL
            else:
                ratio = r["ah_a"] / dsoc / Q_NOM
                self.last_ratio = ratio
                if R_MIN <= ratio <= R_MAX:
                    w = min(f32(1.0), abs(dsoc) / DSOC_W)
                    n = f32(min(r["n_meas"], N_MAX - 1)) + f32(1.0)
                    r["soh_c"] = r["soh_c"] + w / (n + w) * (ratio - r["soh_c"])
                    up = r["soh_c"] if r["soh_c"] < r["soh_disp"] else min(r["soh_c"], r["soh_disp"] + DISP_UP)
                    r["soh_disp"] = min(f32(1.0), up)
                    r["n_meas"] += 1
                    self.event = EV_ACCEPT
                else:
                    self.event = EV_RANGE
                r["soc_a"], r["ah_a"] = soc, f32(0.0)
                self.n_anchor = 0
                self.persist = 1
        r["k_r"] = f32(k_r)
        if abs(r["ah_total"] - self.ah_saved) >= AH_SAVE or abs(r["k_r"] - self.kr_saved) >= KR_SAVE:
            self.persist = 1

    def step(self, I, V, T, k_r, t_valid, i_valid, can_ok):
        """Bir örnek (0,1 s): paket akımı [A, deşarj +], paket gerilimi [V], ölçülen T [°C],
        EKF k_R, geçerlilik bayrakları. Dönüş: olay kodu (EV_*)."""
        I, V, T = f32(I), f32(V), f32(T)
        self.event = EV_NONE
        if self.n_zero < DEC_N_ZERO:
            self.b0 = self.b0 + I
            self.n_zero += 1
            if self.n_zero == DEC_N_ZERO:
                self.b0 = self.b0 / f32(DEC_N_ZERO)
            return self.event
        r = self.r
        i = I - self.b0
        valid = bool(t_valid and i_valid and can_ok)
        r["ah_total"] = r["ah_total"] + abs(i) * H
        if not valid:
            self.reset_anchor()
        if r["anchor"]:
            r["ah_a"] = r["ah_a"] + i * H
            self.n_anchor += 1
            if self.n_anchor > N_ANCHOR:
                self.reset_anchor()
        self.i_f = self.i_f + I_FILT * (i - self.i_f)
        if valid and abs(self.i_f) < I_REST:
            if self.n_rest < N_REST:
                self.n_rest += 1
                if self.n_rest > N_REST - N_AVG:
                    self.ocv_sum = self.ocv_sum + V / f32(BMS_NS)
                    self.i_sum = self.i_sum + I
                if self.n_rest == N_REST:
                    self._point(T, k_r)
        else:
            self.n_rest = 0
            self.ocv_sum = f32(0.0)
            self.i_sum = f32(0.0)
        return self.event
