"""
19S12P LG INR21700 M50T elektro-termal dijital ikiz (hücre etiketi doğrulandı).

Elektriksel model : 2-RC Thevenin eşdeğer devresi (hücre seviyesinde)
Termal model      : 2 düğümlü (çekirdek-yüzey) toplu parametreli model
Isı üretimi       : Bernardi (tersinmez kısım): Q = I * (OCV - V_term)
Paket ölçekleme   : V_pack = Ns * V_cell,  I_cell = I_pack / Np,
                    R_pack = R_cell * Ns / Np,  C_pack = C_cell * Np / Ns

İşaret kuralı: I > 0 deşarj, I < 0 şarj (rejeneratif frenleme).

Parametre kaynakları (ayrıntı: plan/parametre_tablosu.tex):
  - Kapasite, gerilim/akım sınırları, kütle: LG INR21700 M50T veri sayfası (Rev 0, 2018-07-16)
  - R0 = R(0.1 s), R1 (R(10 s) - R(0.1 s) kısıtından): Kirkaldy vd. (2024), %52 SOC, BoL
  - OCV(SOC): Kirkaldy vd. (2024) LG M50T GITT dinlenme sonu gerilimleri (BoL, 25 °C; veri/ocv_gitt.py, hücre A-D, E-H'de doğrulandı)
  - Sıcaklık bağımlılığı (Ea): Kirkaldy vd. (2024) ham döngü verisi, 8 hücre 15-40 °C (veri/ea_kirkaldy.py)
  - Termal yapı: Lin vd. (2014) 2 düğümlü model; ısıl kapasite = kütle x ~1000 J/(kg K)
"""
from dataclasses import dataclass, field
import numpy as np

R_GAS = 8.314  # J/(mol K)
# Yaşlanma: direnç oranı = 1 + AGE_BETA (1 - SOH); Kirkaldy vd. (2024) 40 hücre, 224 RPT
# (veri/age_resistance.py). bms_ecu twin_model.h TW_AGE_BETA ve simulink P.age_beta ile aynı.
AGE_BETA = 1.31
# Karşılaştırma referansı (modelde kullanılmaz): Chen vd. (2020) LG M50 OCV, 2026-11-18'e kadar modelin
# tablosuydu (commit 67129ef öncesi). veri/ocv_kirkaldy.py ve veri/ocv_gitt.py bununla karşılaştırır.
OCV_CHEN2020_SOC = np.array([0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65,
                             0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98, 1.0])
OCV_CHEN2020 = np.array([2.4977, 2.8373, 3.0726, 3.2574, 3.3956, 3.4487, 3.4934, 3.5473, 3.5959, 3.6329, 3.6664,
                         3.7051, 3.7538, 3.8055, 3.859, 3.9203, 3.9671, 4.0165, 4.0658, 4.0927, 4.111, 4.1458, 4.1809])


def arrhenius(ea, t_c):
    """R(T)/R(25 °C) = exp(Ea/Rg (1/T - 1/298.15 K))."""
    return np.exp(ea / R_GAS * (1.0 / (t_c + 273.15) - 1.0 / 298.15))


@dataclass
class CellParams:
    capacity_ah: float = 4.85         # veri sayfası min. (Kirkaldy C/10 BoL: 4.857 Ah)
    v_max: float = 4.20               # veri sayfası şarj sonu gerilimi (79.8 V / 19)
    v_min: float = 2.80               # tasarım alt sınırı (53.2 V / 19); veri sayfası 2.5 V
    i_max_dis: float = 7.275          # veri sayfası sürekli deşarj (1.5C, 25-55 °C)
    i_max_chg: float = 3.395          # veri sayfası maks. şarj (0.7C, 25-45 °C; 0-25 °C: 0.3C)
    # 2-RC parametreleri (25 °C, orta SOC)
    r0: float = 0.0264                # Ohm, Kirkaldy R(0.1 s) %52 SOC
    r1: float = 0.0093                # Ohm, R(10 s) - R(0.1 s) = 6.54 mOhm kısıtından
    c1: float = 1075.0                # F   -> tau1 = 10 s
    r2: float = 0.012                 # Ohm
    c2: float = 15000.0               # F   -> tau2 = 180 s
    # Arrhenius aktivasyon enerjileri [J/mol]: Kirkaldy 2024 Expt 5 ham döngü verisi, 8 hücre,
    # 15/27/40 °C, 5 A basamağı (veri/ea_kirkaldy.py). R0 = 0.05 s ohmik kısım; R1 / R2 = 10 s /
    # 30 s polarizasyonu (ohmik kısım çıkarılmış). Önceki varsayım: yalnız R0, 20 kJ/mol.
    ea_r0: float = 6200.0
    ea_r1: float = 17500.0
    ea_r2: float = 14300.0
    # Termal (Lin et al. 2014 yapısı, 21700'e ölçeklenmiş tahmini değerler)
    cc: float = 64.0                  # çekirdek ısıl kapasitesi [J/K] (toplam 69 J/K: 69 g x ~1000 J/(kg K))
    cs: float = 5.0                   # yüzey ısıl kapasitesi [J/K]
    rc: float = 1.8                   # çekirdek-yüzey ısıl direnci [K/W]
    ru: float = 9.0                   # yüzey-ortam ısıl direnci [K/W] (paket içi, doğal konveksiyon)
    # OCV-SOC tablosu: Kirkaldy vd. (2024) LG M50T GITT dinlenme sonu gerilimleri (BoL, 25 °C; veri/ocv_gitt.py, hücre A-D, E-H'de doğrulandı)
    # (önceki: Chen vd. 2020 LG M50, veri/ocv_chen2020.py; GITT RMSE 64,7 -> 17,0 mV)
    soc_tab: np.ndarray = field(default_factory=lambda: np.array(
        [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98, 1.0]))
    ocv_tab: np.ndarray = field(default_factory=lambda: np.array(
        [2.9414, 3.0161, 3.1444, 3.2871, 3.4047, 3.4646, 3.5055, 3.5621, 3.6086, 3.6418, 3.6729, 3.7119, 3.7594, 3.8136, 3.8737, 3.9207, 3.9641, 4.0162, 4.0619, 4.0873, 4.1120, 4.1519, 4.1845]))


def aged_cell(cell: "CellParams" = None, soh: float = 1.0, k_r: float = None) -> "CellParams":
    """Yaşlanmış hücre: kapasite SOH katı, R0/R1/R2 k_r katı (verilmezse 1 + AGE_BETA (1 - SOH));
    kapasitanslar sabit (bms_ecu twin_model.c ve simulink battery_twin.m Age_Q / Age_R ile aynı)."""
    from dataclasses import replace
    c = cell or CellParams()
    k = 1.0 + AGE_BETA * (1.0 - soh) if k_r is None else k_r
    return replace(c, capacity_ah=c.capacity_ah * soh, r0=c.r0 * k, r1=c.r1 * k, r2=c.r2 * k)


@dataclass
class PackConfig:
    ns: int = 19
    np_: int = 12
    t_amb: float = 25.0               # °C


class PackTwin:
    """Tüm hücrelerin özdeş olduğu varsayımıyla toplu paket modeli."""

    def __init__(self, cell: CellParams = None, pack: PackConfig = None,
                 soc0: float = 0.8):
        self.cell = cell or CellParams()
        self.pack = pack or PackConfig()
        self.soc = soc0
        self.v1 = 0.0      # hücre RC1 gerilimi
        self.v2 = 0.0      # hücre RC2 gerilimi
        self.t_core = self.pack.t_amb
        self.t_surf = self.pack.t_amb

    # ---------- yardımcı fonksiyonlar ----------
    def ocv_cell(self, soc):
        c = self.cell
        return np.interp(np.clip(soc, 0, 1), c.soc_tab, c.ocv_tab)

    def r0_cell(self, soc, t_c):
        """R0(T, SOC): Arrhenius sıcaklık bağımlılığı + düşük SOC artışı."""
        c = self.cell
        tk, tref = t_c + 273.15, 298.15
        f_t = np.exp(c.ea_r0 / R_GAS * (1.0 / tk - 1.0 / tref))
        f_soc = 1.0 + 0.6 * np.exp(-soc / 0.08)
        return c.r0 * f_t * f_soc

    # ---------- bir zaman adımı ----------
    def step(self, i_pack: float, dt: float):
        c, p = self.cell, self.pack
        i = i_pack / p.np_                      # hücre akımı

        ocv = self.ocv_cell(self.soc)
        r0 = self.r0_cell(self.soc, self.t_core)

        # RC dalları: kesin ayrıklaştırma (ZOH); R1, R2 sıcaklığa bağlı (Arrhenius), C sabit
        r1 = c.r1 * arrhenius(c.ea_r1, self.t_core)
        r2 = c.r2 * arrhenius(c.ea_r2, self.t_core)
        a1 = np.exp(-dt / (r1 * c.c1))
        a2 = np.exp(-dt / (r2 * c.c2))
        self.v1 = a1 * self.v1 + r1 * (1 - a1) * i
        self.v2 = a2 * self.v2 + r2 * (1 - a2) * i

        v_cell = ocv - r0 * i - self.v1 - self.v2

        # Bernardi tersinmez ısı (entropik terim ihmal)
        q = i * (ocv - v_cell)

        # 2 düğümlü termal model (açık Euler, dt << termal zaman sabitleri)
        dtc = (q + (self.t_surf - self.t_core) / c.rc) / c.cc
        dts = ((p.t_amb - self.t_surf) / c.ru
               - (self.t_surf - self.t_core) / c.rc) / c.cs
        self.t_core += dtc * dt
        self.t_surf += dts * dt

        # Coulomb sayımı (gerçek SOC)
        self.soc -= i * dt / (3600.0 * c.capacity_ah)

        return {
            "soc": self.soc,
            "v_pack": p.ns * v_cell,
            "v_cell": v_cell,
            "i_pack": i_pack,
            "ocv_pack": p.ns * ocv,
            "t_core": self.t_core,
            "t_surf": self.t_surf,
            "q_cell": q,
        }

    # ---------- paket seviyesi eşdeğer parametreler ----------
    def pack_equivalent(self):
        c, p = self.cell, self.pack
        k = p.ns / p.np_
        return {
            "Q_pack_Ah": c.capacity_ah * p.np_,
            "E_nom_kWh": c.capacity_ah * p.np_ * 3.63 * p.ns / 1000,   # veri sayfası 3.63 V nominal
            "R0_pack": c.r0 * k, "R1_pack": c.r1 * k, "C1_pack": c.c1 / k,
            "R2_pack": c.r2 * k, "C2_pack": c.c2 / k,
            "V_max": c.v_max * p.ns, "V_min": c.v_min * p.ns,
            "I_max_dis": c.i_max_dis * p.np_,
        }
