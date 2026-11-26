"""
Gerçek paketin (aracın 19S12P LG M50 paketi, 26 Kasım ölçümü) yaşına göre beklenen SOH: yaşlanma modeliyle tahmin.

Paketin km'si ve yaşı bilinmiyor, bu yüzden tek sayı yerine olası kullanım aralığı taranır:
yaş 0-8 yıl x yıllık 1000-8000 km. Model ECU'nunkiyle aynı (ml/07_stress_model.py -> twin/stress_model.py):
  çevrim kaybı  = STRESS_A (S(T, m, DoD) x EFC) ^ STRESS_Z      (hibrit fizik x exp(r(T)), Kirkaldy 2024)
  takvim kaybı  = alpha(OCV(m), T) x gün ^ 0,75                  (Schmalstieg 2014, NMC; M50T'ye kalibre DEĞİL)
  SOH = 1 - çevrim - takvim;  direnç oranı k_R = 1 + 1,31 (1 - SOH)  (Kirkaldy 40 hücre, veri/age_resistance.py)
Kullanım varsayımları (tahmin, ölçüm değil):
  tüketim 40 Wh/km (3 kW sınıfı scooter; ikizin agresif çevrimi 60-78 Wh/km verir), paket 19 x 3,6 V x 58,2 Ah,
  her gün sürüş + gece tam şarj: yarım çevrim derinliği DoD = günlük enerji / paket, ortalama SOC m = 1 - DoD/2,
  paket günün çoğunu bu SOC'de, 25 °C'de bekler.
Çıktı (İngilizce): ../results/real_pack_age_estimate.csv, .png

    python veri/real_pack_age.py
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "twin"))
import thesis_style as ts                                  # noqa: E402
from stress_model import STRESS_A, STRESS_Z, stress_S, stress_cal_alpha, CAL_EXP   # noqa: E402

OCV_S = [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8,
         0.85, 0.9, 0.95, 0.98, 1.0]
OCV_V = [2.9414, 3.0161, 3.1444, 3.2871, 3.4047, 3.4646, 3.5055, 3.5621, 3.6086, 3.6418, 3.6729, 3.7119,
         3.7594, 3.8136, 3.8737, 3.9207, 3.9641, 4.0162, 4.0619, 4.0873, 4.112, 4.1519, 4.1845]
E_PACK_WH = 19 * 3.6 * 58.2          # ~3980 Wh
WH_KM = 40.0
T_C = 25.0
AGE_BETA = 1.31


def soh(years, km_per_year, wh_km=WH_KM, t=T_C, m_store=None):
    """Beklenen SOH ve bileşenleri (çevrim, takvim kaybı). m_store: beklemedeki SOC (None = sürüş ortalaması)."""
    days = 365.0 * years
    e_day = km_per_year / 365.0 * wh_km
    dod = min(1.0, e_day / E_PACK_WH)
    m = 1.0 - dod / 2.0
    efc = km_per_year * years * wh_km / E_PACK_WH          # enerji / paket enerjisi = eşdeğer tam çevrim
    cyc = STRESS_A * (stress_S(t, m, max(dod, 1e-3)) * efc) ** STRESS_Z if efc > 0 else 0.0
    ms = m if m_store is None else m_store
    cal = stress_cal_alpha(float(np.interp(ms, OCV_S, OCV_V)), t) * days ** CAL_EXP
    return 1.0 - cyc - cal, cyc, cal, efc, dod, m


rows = []
YEARS = np.arange(0, 8.01, 0.25)
KMS = [1000, 3000, 5000, 8000]
for km in KMS:
    for y in YEARS:
        s, cyc, cal, efc, dod, m = soh(y, km)
        rows.append(dict(km_per_year=km, years=round(y, 2), km_total=round(km * y), efc=round(efc, 1),
                         dod=round(dod, 3), mean_soc=round(m, 3), fade_cycle_pct=round(100 * cyc, 2),
                         fade_calendar_pct=round(100 * cal, 2), soh_pct=round(100 * s, 1),
                         k_r=round(1 + AGE_BETA * (1 - s), 3), storage=None))
M_FOUND = 0.56                       # paketin bulunduğu SOC (ölçüm, 3,77 V): uzun bekleme bu SOC'de varsayımı
for km in KMS:
    for y in YEARS:
        s, cyc, cal, efc, dod, m = soh(y, km, m_store=M_FOUND)
        rows.append(dict(km_per_year=km, years=round(y, 2), km_total=round(km * y), efc=round(efc, 1),
                         dod=round(dod, 3), mean_soc=round(M_FOUND, 3), fade_cycle_pct=round(100 * cyc, 2),
                         fade_calendar_pct=round(100 * cal, 2), soh_pct=round(100 * s, 1),
                         k_r=round(1 + AGE_BETA * (1 - s), 3), storage="stored_at_56pct"))
D = pd.DataFrame(rows)
D["storage"] = D["storage"].fillna("charged_nightly")
out_csv = os.path.join(ROOT, "results", "real_pack_age_estimate.csv")
D.to_csv(out_csv, index=False)

# ---------------------------------------------------------------- figür
ts.apply()
fig, ax = plt.subplots(1, 2, figsize=(9.6, 3.6), gridspec_kw=dict(width_ratios=[1.4, 1]))
a = ax[0]
for i, km in enumerate(KMS):
    d = D[(D.km_per_year == km) & (D.storage == "charged_nightly")]
    a.plot(d.years, d.soh_pct, color=ts.SERIES[i], lw=1.6, label=f"{km} km/year, charged nightly")
for i, km in enumerate(KMS):
    d = D[(D.km_per_year == km) & (D.storage == "stored_at_56pct")]
    a.plot(d.years, d.soh_pct, color=ts.SERIES[i], lw=1.2, ls="--", label=f"{km} km/year, stored at 56 %" if i in (0, 3) else None)
a.axhline(80, color=ts.MUTED, lw=0.8, ls="--")
a.annotate("end of life 80 %", (0.2, 80), xytext=(0, 3), textcoords="offset points", fontsize=7.5, color=ts.INK2)
a.set_xlabel("age [years]")
a.set_ylabel("expected SOH [%]")
a.set_ylim(70, 101)
a.legend(loc="lower left", fontsize=7, ncol=2)
ts.panel_label(a, f"(a) expected SOH (model, {WH_KM:.0f} Wh/km, 25 °C)")
# (b) kayıp bileşenleri: 3000 km/yıl
a = ax[1]
d = D[(D.km_per_year == 3000) & (D.storage == "charged_nightly")]
a.stackplot(d.years, d.fade_calendar_pct, d.fade_cycle_pct, colors=[ts.SERIES[3], ts.SERIES[0]],
            labels=["calendar (literature, not M50T)", "cycling (Kirkaldy hybrid)"], alpha=0.85)
a.set_xlabel("age [years]")
a.set_ylabel("capacity fade [%]")
a.legend(loc="upper left")
ts.panel_label(a, "(b) fade split at 3000 km/year, charged nightly")
fig.tight_layout()
out_png = os.path.join(ROOT, "results", "real_pack_age_estimate.png")
ts.save(fig, out_png, pdf=True)

# ---------------------------------------------------------------- özet
print("Expected SOH [%] (rows: km/year, columns: years):")
for st in ("charged_nightly", "stored_at_56pct"):
    piv = D[D.years.isin([1, 2, 3, 4, 6, 8]) & (D.storage == st)].pivot(index="km_per_year", columns="years", values="soh_pct")
    print(st); print(piv.to_string())
for y, km in ((3, 3000), (5, 3000), (4, 5000)):
    s, cyc, cal, efc, dod, m = soh(y, km)
    print(f"{y} y x {km} km/y: EFC {efc:.0f}, DoD {dod:.2f}, mean SOC {m:.2f} -> SOH {100 * s:.1f} % "
          f"(cycling {100 * cyc:.1f} %, calendar {100 * cal:.1f} %), k_R {1 + AGE_BETA * (1 - s):.2f}")
print("->", out_csv, out_png)
