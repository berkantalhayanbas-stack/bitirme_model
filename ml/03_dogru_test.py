"""
ADIM 3 — Dürüst test: veri sızıntısı (data leakage) ve model karşılaştırması
============================================================================
Kavramlar:
  - Çapraz doğrulama (cross-validation): veriyi parçalara ayır; her seferinde bir
    parçayı test, kalanını eğitim yap; tüm parçalar bir kez test olunca hataları topla.
  - Veri sızıntısı: test verisi eğitim verisine "akraba" ise model ezberle başarılı görünür.
    Bizim veride akrabalık iki katmanlı:
      * aynı hücrenin komşu ölçümleri (gün 100 ve gün 130 neredeyse aynı)
      * aynı koşuldaki kardeş hücreler (aynı deney, aynı sıcaklık)
  - Üç test yöntemi, kolaydan zora:
      1) Random 5-fold          : satırlar rastgele (sızıntı var)
      2) Leave-one-cell-out     : bir hücre tamamen dışarıda (40 katman)
      3) Leave-one-condition-out: bir KOŞUL (deney x sıcaklık) tamamen dışarıda (15 katman)
    Araçtaki gerçek soru 3'e en yakın: "Modelin hiç görmediği bir kullanım tarzında ne olur?"

Bölüm A: aynı karar ağacını üç yöntemle test et, derinlik seçimine etkisini gör.
Bölüm B: dürüst testle (2 ve 3) modelleri ve özellik setlerini karşılaştır:
  - Physics model : 1. haftanın yaşlanma modeli, her katmanda yeniden kalibre
  - Usage only    : sadece BMS sayaçları (efc, days, T, m, dod)
  - R only        : sadece direnç oranı (tek özellik!)
  - Usage + R     : hepsi
  - Hybrid        : fizik modeli + ağaç (ağaç, fizik modelinin HATASINI öğrenir)
Bölüm C: fizik bilgisiyle kısıtlanmış ağaç (physics-informed constraints):
  - min_samples_leaf: her yaprak en az N ölçüme dayanmalı (tek noktayı ezberlemesin)
  - monotonic_cst   : SOH; direnç, çevrim ve gün arttıkça ARTAMAZ (fizik bunu söyler)

Çalıştırma:   python 03_dogru_test.py      (fizik modeli 55 kez kalibre edilir: ~2 dk)
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import KFold, LeaveOneGroupOut, cross_val_predict
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import GradientBoostingRegressor
from ortak import load, physics_fit, physics_predict, FIG, HERE

D = load(with_R=True)
y = D.soh.values
USAGE = ["efc", "days", "T", "m", "dod"]
rmse = lambda p: 100 * np.sqrt(np.mean((p - y) ** 2))
maxe = lambda p: 100 * np.max(np.abs(p - y))

SPLITS = {
    "Random 5-fold": (KFold(5, shuffle=True, random_state=0), None),
    "Leave-one-cell-out": (LeaveOneGroupOut(), D.cell),
    "Leave-one-condition-out": (LeaveOneGroupOut(), D.group),
}

# ================================================================== A) sızıntı
print("=== A) Same decision tree, three ways of testing: SOH RMSE [%] ===")
depths = range(1, 11)
A = {k: [] for k in SPLITS}
for d in depths:
    for k, (cv, g) in SPLITS.items():
        p = cross_val_predict(DecisionTreeRegressor(max_depth=d, random_state=0),
                              D[USAGE + ["rr"]].values, y, cv=cv, groups=g)
        A[k].append(rmse(p))
print(" depth " + "".join(f"{k:>26s}" for k in SPLITS))
for i, d in enumerate(depths):
    print(f" {d:5d} " + "".join(f"{A[k][i]:26.2f}" for k in SPLITS))
for k in SPLITS:
    print(f"{k:24s}: best depth {depths[int(np.argmin(A[k]))]}, "
          f"depth-8 tree looks {'fine' if A[k][7] < min(A[k]) * 1.1 else 'WORSE'} "
          f"({A[k][7]:.2f} % vs best {min(A[k]):.2f} %)")
DEPTH = depths[int(np.argmin(A["Leave-one-condition-out"]))]
print(f"-> Depth chosen with the honest test: {DEPTH}")

fig, ax = plt.subplots(figsize=(7.5, 4.3))
for k, mk in zip(SPLITS, "o^s"):
    ax.plot(depths, A[k], mk + "-", label=k)
ax.axvline(DEPTH, c="k", ls=":", lw=1)
ax.set_xlabel("Tree depth"); ax.set_ylabel("Cross-validated SOH RMSE [%]")
ax.set_title("Data leakage: only the condition-wise test penalises deep trees")
ax.grid(alpha=.3); ax.legend()
fig.tight_layout(); fig.savefig(os.path.join(FIG, "ml_cv_leakage.png"), dpi=200)

# ================================================================== B) karşılaştırma
MODELS = {
    "Linear": LinearRegression,
    f"Tree (depth {DEPTH})": lambda: DecisionTreeRegressor(max_depth=DEPTH, random_state=0),
    "Gradient boosting": lambda: GradientBoostingRegressor(n_estimators=150, max_depth=2,
                                                           learning_rate=.05, random_state=0),
}
FEATSETS = {"Usage only": USAGE, "R only": ["rr"], "Usage + R": USAGE + ["rr"]}

rows = []
for split in ["Leave-one-cell-out", "Leave-one-condition-out"]:
    cv, groups = SPLITS[split]
    folds = list(cv.split(D, y, groups))
    print(f"\n=== B) {split} ({len(folds)} folds) ===")
    # fizik modeli: her katmanda sadece eğitim verisiyle kalibre
    phys = np.zeros(len(y)); phys_tr = []
    for i, (tr, te) in enumerate(folds):
        p = physics_fit(D.iloc[tr])
        phys[te] = physics_predict(p, D.iloc[te])
        phys_tr.append(physics_predict(p, D.iloc[tr]))
        print(f"\r  physics model calibrated {i + 1}/{len(folds)}", end="")
    print()
    rows.append(dict(Split=split, Model="Physics model", Features="Usage (physics)",
                     RMSE=rmse(phys), MaxErr=maxe(phys)))
    for mn, mk in MODELS.items():
        for fn, feats in FEATSETS.items():
            p = cross_val_predict(mk(), D[feats].values, y, cv=folds)
            rows.append(dict(Split=split, Model=mn, Features=fn, RMSE=rmse(p), MaxErr=maxe(p)))
    # hibrit: ağaç fizik modelinin artığını (hata) öğrenir
    hyb = np.zeros(len(y))
    for (tr, te), ptr in zip(folds, phys_tr):
        t = DecisionTreeRegressor(max_depth=DEPTH, random_state=0)
        t.fit(D.iloc[tr][USAGE + ["rr"]].values, y[tr] - ptr)
        hyb[te] = phys[te] + t.predict(D.iloc[te][USAGE + ["rr"]].values)
    rows.append(dict(Split=split, Model=f"Hybrid: physics + tree", Features="Usage + R",
                     RMSE=rmse(hyb), MaxErr=maxe(hyb)))

R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "cv_results.csv"), index=False)
pd.set_option("display.width", 160)
for split in R.Split.unique():
    print(f"\n--- {split}: SOH error [%] ---")
    print(R[R.Split == split].drop(columns="Split").round(2).to_string(index=False))

# ------------------------------------------------------------------ grafik
sub = R[R.Split == "Leave-one-condition-out"].reset_index(drop=True)
lab = [f"{m}\n{f}" if not m.startswith(("Physics", "Hybrid")) else m.replace(": ", ":\n")
       for m, f in zip(sub.Model, sub.Features)]
col = ["0.4" if m.startswith("Physics") else ("C3" if m.startswith("Hybrid") else
       {"Usage only": "C0", "R only": "C1", "Usage + R": "C2"}[f]) for m, f in zip(sub.Model, sub.Features)]
fig, ax = plt.subplots(figsize=(12, 4.6))
ax.bar(range(len(sub)), sub.RMSE, color=col)
for i, v in enumerate(sub.RMSE):
    ax.text(i, v + .05, f"{v:.2f}", ha="center", fontsize=8)
ax.set_xticks(range(len(sub))); ax.set_xticklabels(lab, fontsize=7.5)
ax.set_ylabel("SOH RMSE [%]")
ax.set_title("SOH estimation on unseen operating conditions (leave-one-condition-out, 15 folds)\n"
             "grey: physics model, blue: usage counters, orange: resistance only, green: both, red: hybrid",
             fontsize=10)
ax.grid(axis="y", alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "ml_model_comparison.png"), dpi=200)
# ================================================================== C) fizik kısıtları
print("\n=== C) Physics-informed constraints, leave-one-condition-out SOH RMSE [%] ===")
MONO = [-1 if f in ("efc", "days", "rr") else 0 for f in USAGE + ["rr"]]
cv, groups = SPLITS["Leave-one-condition-out"]
print(" depth   unconstrained   min 10 per leaf   min 10 per leaf + monotonic")
for d in (3, 4, 5):
    r = []
    for msl, mc in ((1, None), (10, None), (10, MONO)):
        p = cross_val_predict(DecisionTreeRegressor(max_depth=d, min_samples_leaf=msl,
                              monotonic_cst=mc, random_state=0),
                              D[USAGE + ["rr"]].values, y, cv=cv, groups=groups)
        r.append(rmse(p))
    print(f" {d:5d}   {r[0]:13.2f}   {r[1]:15.2f}   {r[2]:27.2f}")
print("Accuracy is about the same; the constrained tree cannot learn physically impossible rules")
print("(e.g. 'lower resistance -> lower SOH') and does not degrade as quickly with depth.")
print("-> Final model for step 4: depth 3, min 10 samples per leaf, monotonic in efc, days, rr.")

print("\nSaved: ml/cv_results.csv, simulink/sonuclar/ml_cv_leakage.png, ml_model_comparison.png")
