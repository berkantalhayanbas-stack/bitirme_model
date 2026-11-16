"""
ADIM 1 — Veriyi tanı ve hazırla
================================
Makine öğrenmesinin ilk kuralı: modele geçmeden önce veriye bak.

Ne yapar:
  1. Kirkaldy vd. (2024) LG M50T özet verisini okur (40 hücre, 5 deney, 3 sıcaklık).
  2. Her ölçüm noktası (RPT) için bir satır oluşturur:
       - HEDEF (y)    : soh  = kapasite / ilk kapasite  (C/10 ölçümü)
       - ÖZELLİKLER (X), bir BMS'in araçta bilebileceği şeyler:
           efc   eşdeğer tam çevrim sayısı (BMS Ah sayacından)
           days  geçen gün (BMS saatinden)
           T     ortalama hücre sıcaklığı (BMS sıcaklık kaydından)
           m     ortalama SOC (BMS SOC kaydından)
           dod   tipik deşarj derinliği (BMS SOC kaydından)
           rr    iç direnç / ilk iç direnç (BMS'in çevrimiçi ölçebileceği "sağlık göstergesi")
  3. Aykırı değeri işaretler, kapsam dışı (diz sonrası) noktaları işaretler.
  4. Veriyi ml/dataset.csv olarak kaydeder ve iki grafik çizer.

Çalıştırma:   python 01_veri_hazirla.py
Gerekli:      ../veri/kirkaldy_ozet/ ve ../veri/experiment_metadata.xlsx
              (yoksa hazır ml/dataset.csv ile 2. adımdan devam edebilirsin)
"""
import os
import glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
VERI = os.path.join(HERE, "..", "veri")
FIG = os.path.join(HERE, "..", "simulink", "sonuclar")
os.makedirs(FIG, exist_ok=True)

# Deney koşulları (experiment_metadata.xlsx'teki "SoC range" sütunundan)
SOC_MEAN = {"1": 0.15, "2,2": 0.775, "3": 0.925, "5": 0.50, "4": 0.50}
DOD = {"1": 0.30, "2,2": 0.15, "3": 0.15, "5": 1.00, "4": 1.00}
LABEL = {"1": "0-30% SoC", "2,2": "70-85% SoC", "3": "85-100% SoC",
         "5": "0-100% SoC (CC)", "4": "0-100% SoC (drive cycle)"}

SOH_MIN = 0.75     # kapsam: diz (knee) öncesi; araçta EOL tipik olarak %80
RR_MAX = 2.0       # iki RPT arasında direncin 2 katına çıkması fiziksel değil -> ölçüm hatası

# ------------------------------------------------------------------ 1) oku
meta = pd.read_excel(os.path.join(VERI, "experiment_metadata.xlsx"), sheet_name=None)
rows = []
for _, m in meta.items():
    for _, r in m.iterrows():
        pat = os.path.join(VERI, "kirkaldy_ozet", r["Expt long name"], "Summary Data",
                           "Performance Summary", f"Expt {r['Expt']} - cell {r['Cell']} (*")
        f = glob.glob(pat)
        if not f:
            continue
        d = pd.read_csv(f[0], index_col=0)
        q0 = d["C/10 Capacity [mA h]"].iloc[0] / 1000          # ilk kapasite [Ah]
        r0 = d["0.1s Resistance [Ohms]"].iloc[0]               # ilk direnç [Ohm]
        e = str(r["Expt"])
        for _, x in d.iterrows():
            rows.append(dict(
                expt=e, cell=f"{e}{r['Cell']}", T_set=int(r["Temp"]),
                group=f"{e}_{int(r['Temp'])}C",                 # aynı koşuldaki hücreler
                efc=x["Charge Throughput [A h]"] / (2 * q0),
                days=x["Days of degradation"],
                T=x["Age set av. temperature [°C]"],
                m=SOC_MEAN[e], dod=DOD[e],
                rr=x["0.1s Resistance [Ohms]"] / r0,
                soh=x["C/10 Capacity [mA h]"] / 1000 / q0,
            ))
if not rows:
    raise SystemExit("Veri bulunamadı: ../veri/kirkaldy_ozet/ klasörünü kontrol et "
                     "(veya hazır dataset.csv ile 02_ilk_model.py'den devam et).")
D = pd.DataFrame(rows)

# ------------------------------------------------------------------ 2) temizle
# İlk ölçümde (gün 0) sıcaklık yok: aynı koşuldaki ortalamayla doldur
D["T"] = D["T"].fillna(D.groupby("group")["T"].transform("mean"))
D = D[D.soh.notna() & D.efc.notna()].copy()
D["outlier"] = D.rr > RR_MAX
D["in_scope"] = D.soh >= SOH_MIN
D["has_R"] = D.rr.notna() & ~D.outlier

print("=== Dataset summary ===")
print(f"Rows (measurement points): {len(D)}   cells: {D.cell.nunique()}   "
      f"operating conditions (groups): {D.group.nunique()}")
print(f"Rows with a valid resistance measurement: {D.has_R.sum()}  "
      f"(resistance was measured at every second check-up)")
print(f"Outliers (R ratio > {RR_MAX}): {D.outlier.sum()}")
print(D[D.outlier][["cell", "efc", "rr", "soh"]].to_string(index=False))
print(f"In scope (SOH >= {SOH_MIN}): {D.in_scope.sum()} rows; with resistance: "
      f"{(D.in_scope & D.has_R).sum()} rows  <- 2. ve 3. adımların veri kümesi")
print("\nCorrelation between SOH and resistance ratio, per operating condition:")
c = (D[D.has_R & D.in_scope].groupby("group")
     .apply(lambda g: g[["soh", "rr"]].corr().iloc[0, 1]))
print(c.round(2).to_string())
print(f"Overall (all conditions mixed): "
      f"{D[D.has_R & D.in_scope][['soh', 'rr']].corr().iloc[0, 1]:.2f}")

D.to_csv(os.path.join(HERE, "dataset.csv"), index=False)
print("\nSaved: ml/dataset.csv")

# ------------------------------------------------------------------ 3) grafik
fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
cmap = {"1": "C0", "2,2": "C1", "3": "C2", "4": "C3", "5": "C4"}
mk = {10: "o", 25: "s", 40: "^"}
for (e, t), g in D[D.in_scope].groupby(["expt", "T_set"]):
    g = g.sort_values("efc")
    lab = LABEL[e] if t == 25 else None
    ax[0].plot(g.efc, 100 * g.soh, mk[t], ms=3, c=cmap[e], alpha=.6, label=lab)
    h = g[g.has_R]
    ax[1].plot(h.rr, 100 * h.soh, mk[t], ms=3, c=cmap[e], alpha=.6, label=lab)
ax[0].set_xlabel("Equivalent full cycles"); ax[0].set_ylabel("SOH [%]")
ax[0].set_title("Capacity fade vs usage (marker: o 10 °C, □ 25 °C, △ 40 °C)", fontsize=10)
ax[1].set_xlabel("Resistance ratio R / R_BoL"); ax[1].set_ylabel("SOH [%]")
ax[1].set_title("Capacity fade vs internal resistance", fontsize=10)
for a in ax:
    a.grid(alpha=.3); a.legend(fontsize=8)
fig.suptitle("LG M50T ageing data (Kirkaldy et al. 2024): 40 cells, 15 operating conditions")
fig.tight_layout()
fig.savefig(os.path.join(FIG, "ml_data_overview.png"), dpi=200)
print("Saved: simulink/sonuclar/ml_data_overview.png")
