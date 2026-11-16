"""
ADIM 5 — Uçtan uca demo: yaşlanmış hücrede ML ile SOH -> daha iyi SOC
=======================================================================
Senaryo: araçtaki hücreler yaşlanmış (kapasite düşük, direnç yüksek) ama BMS bunu
bilmiyor ve hâlâ yeni hücre parametreleriyle çalışıyor. Sorular:
  1. Çevrimiçi direnç kestiricisi sürüş sırasında direnç oranını (rr) bulabiliyor mu?
  2. ML ağacı bu rr ve BMS sayaçlarıyla SOH'yi doğru tahmin ediyor mu?
  3. Tahmin EKF'ye verilince SOC hatası ne kadar düzeliyor?

Dürüstlük kuralı: her test hücresi için ağaç, o hücrenin KULLANIM KOŞULU hiç görülmeden
eğitilir (leave-one-condition-out). Yaşlanmış ikizin kapasitesi ve direnci, o hücrenin
Kirkaldy verisindeki gerçek ölçümlerinden alınır.

Akış (her test hücresi için):
  sürüş 1..3 : yaşlanmış ikiz + gürültülü CAN ölçümleri -> EKF + sıcaklık gözlemcisi
               -> direnç kestiricisi rr'yi biriktirir
  ML         : SOH_hat = ağaç(efc, days, T, m, dod, rr_hat)
  sürüş 4    : üç EKF karşılaştırılır (aynı ölçümler)
                 "new-cell BMS" : nominal kapasite ve direnç
                 "ML-updated"   : Q = SOH_hat·Q0, R0 = rr_hat·R0
                 "oracle"       : gerçek kapasite ve direnç (ulaşılabilecek en iyi)

Çalıştırma:   python 05_yaslanmis_hucre.py     (~1 dk)
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.tree import DecisionTreeRegressor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "twin"))
from battery_model import PackTwin, CellParams, PackConfig     # noqa: E402
from sensors import measure                                     # noqa: E402
from ekf import PackEKF                                         # noqa: E402
from thermal_observer import ThermalEKF                         # noqa: E402
from rint_estimator import RintEstimator                        # noqa: E402
from ortak import load, FIG                                     # noqa: E402

FEATS = ["efc", "days", "T", "m", "dod", "rr"]
MONO = [-1 if f in ("efc", "days", "rr") else 0 for f in FEATS]
DT, N_LEARN = 0.1, 3
ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
I = ref.i_pack.values
t = ref.t.values
c0 = CellParams()
mask = c0.soc_tab >= 0.05
coef = np.polyfit(c0.soc_tab[mask], c0.ocv_tab[mask], 7)

D = load(with_R=True)
# Test hücreleri: farklı koşullardan, SOH ~ 0.95 / 0.90 / 0.85 / 0.80
cases, used = [], set()
for target in (0.95, 0.90, 0.85, 0.80):
    c = D[~D.group.isin(used) & (D.days > 0)].copy()
    row = c.iloc[(c.soh - target).abs().argmin()]
    used.add(row.group)
    cases.append(row)


def pack_eq(q_ah, r_scale):
    k = 19 / 12
    # Varsayım: yaşlanmada tüm dirençler (R0, R1, R2) aynı oranda artar; ikiz de böyle.
    # Sadece R0'ı güncellemek yetmiyor: RC dirençleri eski kalırsa oracle bile %1 hata yapıyor.
    return {"Q_pack_Ah": q_ah * 12, "R0_pack": c0.r0 * r_scale * k, "R1_pack": c0.r1 * r_scale * k,
            "C1_pack": c0.c1 / k, "R2_pack": c0.r2 * r_scale * k,
            "C2_pack": c0.c2 / k}          # kapasitanslar sabit (ikizle aynı)


def drive(cell, seed, ekfs, rint=None):
    """Bir sürüş: ikiz -> ölçüm -> (EKF'ler, gözlemci, direnç kestiricisi)."""
    twin = PackTwin(cell, PackConfig(t_amb=25.0), soc0=0.8)
    d = pd.DataFrame([twin.step(i, DT) for i in I])
    vm, im, tm = measure(d.v_pack.values, d.i_pack.values, d.t_surf.values, seed=seed)
    th = ThermalEKF(c0, 19, 12, coef, DT, t0=tm[0])
    est = {k: np.zeros(len(I)) for k in ekfs}
    for k_ in range(len(I)):
        for name, e in ekfs.items():
            est[name][k_] = e.step(im[k_], vm[k_], tm[k_])[0][0]
        s_ref = est[next(iter(ekfs))][k_]
        xt, _, _ = th.step(im[k_], vm[k_], s_ref, tm[k_], 25.0)
        if rint is not None:
            rint.step(im[k_], vm[k_], xt[0], s_ref)
    return d, est


rows, hist = [], {}
for r in cases:
    cell = CellParams(capacity_ah=c0.capacity_ah * r.soh, r0=c0.r0 * r.rr,
                      r1=c0.r1 * r.rr, r2=c0.r2 * r.rr)
    tr = D[D.group != r.group]
    tree = DecisionTreeRegressor(max_depth=3, min_samples_leaf=10, monotonic_cst=MONO,
                                 random_state=0).fit(tr[FEATS].values, tr.soh.values)
    rint = RintEstimator()
    rr_hist = []
    for k in range(N_LEARN):                       # öğrenme sürüşleri
        drive(cell, 100 + k, {"nominal": PackEKF(pack_eq(c0.capacity_ah, 1.0), coef, 19, DT, soc0=0.5)},
              rint)
        rr_hist.append(rint.rr())
    rr_hat = rint.rr()
    x = r[FEATS].values.astype(float).copy()
    x[-1] = rr_hat
    soh_hat = float(tree.predict(x.reshape(1, -1))[0])
    # değerlendirme sürüşü: üç EKF aynı ölçümlerle
    ekfs = {
        "New-cell BMS": PackEKF(pack_eq(c0.capacity_ah, 1.0), coef, 19, DT, soc0=0.5),
        "ML-updated": PackEKF(pack_eq(c0.capacity_ah * soh_hat, rr_hat), coef, 19, DT, soc0=0.5),
        "Oracle": PackEKF(pack_eq(c0.capacity_ah * r.soh, r.rr), coef, 19, DT, soc0=0.5),
    }
    d, est = drive(cell, 200, ekfs)
    after = t > 60
    row = dict(Cell=r.cell, Condition=r.group, SOH_true=100 * r.soh, rr_true=r.rr,
               rr_hat=rr_hat, rr_err_pct=100 * (rr_hat / r.rr - 1), SOH_ML=100 * soh_hat,
               SOH_err_pts=100 * (soh_hat - r.soh), events=rint.n,
               rr_err_1drive_pct=100 * (rr_hist[0] / r.rr - 1))
    for name, e in est.items():
        err = 100 * (e - d.soc.values)
        row[f"RMSE {name}"] = np.sqrt(np.mean(err[after] ** 2))
        row[f"End err {name}"] = err[-1]
    rows.append(row)
    hist[r.cell] = (d, est, rr_hist)
    print(f"{r.cell:5s} ({r.group:7s}) SOH true {100 * r.soh:5.1f} %  ML {100 * soh_hat:5.1f} %   "
          f"rr true {r.rr:.3f}  est {rr_hat:.3f} ({rint.n} steps)")

R = pd.DataFrame(rows)
pd.set_option("display.width", 220)
print("\n=== Online resistance + ML SOH ===")
print(R[["Cell", "Condition", "SOH_true", "SOH_ML", "SOH_err_pts", "rr_true", "rr_hat",
         "rr_err_pct", "rr_err_1drive_pct", "events"]].round(3).to_string(index=False))
print("\n=== SOC estimation on an aged pack (after 60 s, %) ===")
print(R[["Cell", "SOH_true"] + [c for c in R.columns if c.startswith(("RMSE", "End"))]]
      .round(3).to_string(index=False))
R.to_csv(os.path.join(HERE, "aged_demo_results.csv"), index=False)

# ------------------------------------------------------------------ grafik (en yaşlı hücre)
cell_id = R.iloc[R.SOH_true.argmin()].Cell
d, est, _ = hist[cell_id]
r = R[R.Cell == cell_id].iloc[0]
fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
ax[0].plot(t / 60, 100 * d.soc, "k", lw=1.6, label="True SOC")
for (name, e), c in zip(est.items(), ["C3", "C0", "C2"]):
    ax[0].plot(t / 60, 100 * e, c=c, lw=1, label=name)
ax[0].set_ylabel("SOC [%]"); ax[0].legend(); ax[0].grid(alpha=.3)
ax[0].set_title(f"Aged pack (cell {cell_id}: SOH {r.SOH_true:.1f} %, R ×{r.rr_true:.2f}); "
                f"ML estimate SOH {r.SOH_ML:.1f} %, R ×{r.rr_hat:.2f}")
for (name, e), c in zip(est.items(), ["C3", "C0", "C2"]):
    ax[1].plot(t / 60, 100 * (e - d.soc), c=c, lw=1, label=name)
ax[1].set_ylim(-4, 4); ax[1].set_ylabel("SOC error [%]"); ax[1].set_xlabel("Time [min]")
ax[1].grid(alpha=.3); ax[1].legend()
fig.tight_layout()
fig.savefig(os.path.join(FIG, "ml_aged_pack_soc.png"), dpi=200)
print("\nSaved: ml/aged_demo_results.csv, simulink/sonuclar/ml_aged_pack_soc.png")
