"""
Ana senaryo: dijital ikiz + sensör hatası + EKF.
Çıktılar: results/*.png, results/twin_run.csv, results/summary.txt
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from battery_model import PackTwin, CellParams, PackConfig
from drive_cycle import synthetic_cycle, speed_to_current
from sensors import measure
from ekf import PackEKF

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(OUT, exist_ok=True)
DT = 0.1
SOC_TRUE0, SOC_EKF0 = 0.80, 0.50

# ---------------- 1) OCV polinomu (5. derece) ----------------
cell = CellParams()
mask = cell.soc_tab >= 0.05                      # polinom çok düşük SOC'yi iyi temsil edemez
coef = np.polyfit(cell.soc_tab[mask], cell.ocv_tab[mask], 7)   # 7. derece: Chen2020 eğrisinde maks. hata ~15 mV
fit = np.polyval(coef, cell.soc_tab[mask])
ss_res = np.sum((cell.ocv_tab[mask] - fit) ** 2)
ss_tot = np.sum((cell.ocv_tab[mask] - cell.ocv_tab[mask].mean()) ** 2)
r2 = 1 - ss_res / ss_tot

# ---------------- 2) Sürüş çevrimi ----------------
t, v = synthetic_cycle(dt=DT, repeats=4)
i_pack = speed_to_current(v, DT)

# ---------------- 3) Dijital ikiz ----------------
twin = PackTwin(cell, PackConfig(t_amb=25.0), soc0=SOC_TRUE0)
rows = [twin.step(i, DT) for i in i_pack]
df = pd.DataFrame(rows)
df.insert(0, "t", t)
df.insert(1, "speed_kmh", v * 3.6)

# ---------------- 4) Sensör + EKF ----------------
vm, im, tsm = measure(df.v_pack.values, df.i_pack.values, df.t_surf.values)
df["v_meas"], df["i_meas"], df["ts_meas"] = vm, im, tsm

results = {}
for name, nb, ut in [("ekf3_noT", False, False), ("ekf3", False, True),
                     ("ekf4_bias", True, True)]:
    ekf = PackEKF(twin.pack_equivalent(), coef, 19, DT, soc0=SOC_EKF0,
                  estimate_bias=nb, use_temp=ut)
    est = np.array([ekf.step(i, vv, ts)[0] for i, vv, ts in zip(im, vm, tsm)])
    df[f"soc_{name}"] = est[:, 0]
    if nb:
        df["bias_est"] = est[:, 3]
    err = est[:, 0] - df.soc.values
    out = np.nonzero(np.abs(err) > 0.02)[0]            # |hata| > %2 olan son an
    conv = (out[-1] + 1) * DT if len(out) else 0.0
    after = t > 60.0
    results[name] = dict(
        rmse_all=np.sqrt(np.mean(err ** 2)) * 100,
        rmse_after60=np.sqrt(np.mean(err[after] ** 2)) * 100,
        maxerr_after60=np.max(np.abs(err[after])) * 100,
        t_conv=conv,
    )

# Ham Coulomb sayımı (karşılaştırma için, doğru başlangıçla bile kayar)
cc = SOC_TRUE0 - np.cumsum(im) * DT / (3600 * 4.85 * 12)
df["soc_cc"] = cc
results["coulomb"] = dict(final_err=(cc[-1] - df.soc.values[-1]) * 100)

df.iloc[::10].to_csv(os.path.join(OUT, "twin_run.csv"), index=False)  # 1 Hz

# ---------------- 5) Grafikler ----------------
fig, ax = plt.subplots(5, 1, figsize=(11, 13), sharex=True)
ax[0].plot(t, v * 3.6, lw=0.8); ax[0].set_ylabel("Hız [km/h]")
ax[1].plot(t, i_pack, lw=0.6); ax[1].set_ylabel("I_pack [A]")
ax[1].axhline(0, c="k", lw=0.5)
ax[2].plot(t, vm, lw=0.4, alpha=0.5, label="Ölçülen (gürültülü)")
ax[2].plot(t, df.v_pack, lw=0.8, label="Gerçek")
ax[2].plot(t, df.ocv_pack, lw=0.8, ls="--", label="OCV")
ax[2].set_ylabel("V_pack [V]"); ax[2].legend(loc="lower left")
ax[3].plot(t, df.soc * 100, "k", lw=1.2, label="Gerçek SOC")
ax[3].plot(t, df.soc_ekf3_noT * 100, lw=0.8, alpha=0.6, label="EKF (sabit R0)")
ax[3].plot(t, df.soc_ekf3 * 100, lw=0.8, label="EKF (R0(T))")
ax[3].plot(t, df.soc_ekf4_bias * 100, lw=0.8, label="EKF (+akım kayması)")
ax[3].plot(t, cc * 100, lw=0.8, ls=":", label="Coulomb sayımı")
ax[3].set_ylabel("SOC [%]"); ax[3].legend(loc="upper right")
ax[4].plot(t, df.t_core, label="T_core"); ax[4].plot(t, df.t_surf, label="T_surf")
ax[4].set_ylabel("T [°C]"); ax[4].set_xlabel("Zaman [s]"); ax[4].legend()
for a in ax: a.grid(alpha=0.3)
fig.suptitle("19S12P LG 21700 Dijital İkiz + EKF")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "01_twin_overview.png"), dpi=130)

fig, ax = plt.subplots(1, 2, figsize=(12, 4))
s = np.linspace(0.05, 1, 200)
ax[0].plot(cell.soc_tab, cell.ocv_tab, "o", label="Tablo")
ax[0].plot(s, np.polyval(coef, s), label=f"7. derece polinom (R²={r2:.5f})")
ax[0].set_xlabel("SOC"); ax[0].set_ylabel("OCV hücre [V]"); ax[0].legend(); ax[0].grid(alpha=.3)
z = t < 180
ax[1].plot(t[z], df.soc[z] * 100, "k", label="Gerçek")
ax[1].plot(t[z], df.soc_ekf3_noT[z] * 100, alpha=0.6, label="EKF sabit R0")
ax[1].plot(t[z], df.soc_ekf3[z] * 100, label="EKF 3")
ax[1].plot(t[z], df.soc_ekf4_bias[z] * 100, label="EKF 4")
ax[1].axvline(60, c="r", ls="--", lw=0.8, label="60 s hedefi")
ax[1].set_xlabel("Zaman [s]"); ax[1].set_ylabel("SOC [%]")
ax[1].set_title("Yakınsama: gerçek %80, EKF başlangıcı %50"); ax[1].legend(); ax[1].grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_ocv_fit_convergence.png"), dpi=130)

# ---------------- 6) Özet ----------------
eq = twin.pack_equivalent()
lines = [
    f"Simülasyon süresi: {t[-1]:.0f} s, dt = {DT} s",
    f"Mesafe: {np.sum(v) * DT / 1000:.2f} km",
    f"Tüketilen enerji: {np.sum(df.v_pack * df.i_pack) * DT / 3.6e6:.3f} kWh",
    f"SOC: {SOC_TRUE0*100:.0f}% -> {df.soc.iloc[-1]*100:.1f}%",
    f"I_pack min/max: {i_pack.min():.1f} / {i_pack.max():.1f} A",
    f"V_pack min/max: {df.v_pack.min():.2f} / {df.v_pack.max():.2f} V",
    f"T_core max: {df.t_core.max():.2f} °C, T_surf max: {df.t_surf.max():.2f} °C",
    f"OCV polinomu R² = {r2:.5f}  katsayılar (yüksek->düşük): {np.round(coef, 4).tolist()}",
    "Paket eşdeğer parametreleri: " + ", ".join(f"{k}={v:.4g}" for k, v in eq.items()),
]
for k, r in results.items():
    lines.append(f"{k}: " + ", ".join(f"{a}={b:.3f}" for a, b in r.items()))
txt = "\n".join(lines)
open(os.path.join(OUT, "summary.txt"), "w").write(txt)
print(txt)
