"""
ADIM 2 — İlk model: eğitim/test ayrımı ve aşırı öğrenme (overfitting)
======================================================================
Kavramlar:
  - Eğitim verisi (train): modelin öğrendiği veri.
  - Test verisi (test)   : modelin HİÇ görmediği veri. Başarı sadece burada ölçülür.
  - RMSE: hataların karesinin ortalamasının kökü (büyük hataları daha çok cezalandırır).
  - MAE : mutlak hataların ortalaması.
  - Karar ağacı (decision tree): "rr > 1.12 mi? evet -> sol, hayır -> sağ" gibi
    soru dizisi. STM32'ye gömmek için ideal: sadece if-else, çarpma bile yok.
  - Derinlik (depth): ardışık soru sayısı. Derinlik arttıkça eğitim hatası hep düşer,
    ama test hatası bir noktadan sonra ARTAR: model veriyi ezberlemeye başlamıştır.

Bu adımda bilerek basit (ve biraz saf) bir yöntem kullanıyoruz: satırları rastgele
%80 eğitim / %20 test olarak ayırıyoruz. 3. adımda bunun neden yanıltıcı olduğunu göreceğiz.

Çalıştırma:   python 02_ilk_model.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor, export_text
from sklearn.metrics import mean_squared_error, mean_absolute_error

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "..", "results")
os.makedirs(FIG, exist_ok=True)

D = pd.read_csv(os.path.join(HERE, "dataset.csv"))
D = D[D.in_scope & D.has_R]                     # 252 satır
FEATS = ["efc", "days", "T", "m", "dod", "rr"]
X, y = D[FEATS].values, D.soh.values

# ------------------------------------------------------------------ 1) rastgele ayır
# random_state: aynı "rastgele" ayrımı her çalıştırmada tekrar üretir (tekrarlanabilirlik)
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=0)
print(f"Train: {len(y_tr)} rows, test: {len(y_te)} rows (random split)\n")


def report(name, model):
    model.fit(X_tr, y_tr)                       # öğren
    p_tr, p_te = model.predict(X_tr), model.predict(X_te)   # tahmin et
    rmse = lambda a, b: 100 * np.sqrt(mean_squared_error(a, b))
    print(f"{name:28s} train RMSE {rmse(y_tr, p_tr):5.2f} %   test RMSE {rmse(y_te, p_te):5.2f} %   "
          f"test MAE {100 * mean_absolute_error(y_te, p_te):5.2f} %")
    return model


# ------------------------------------------------------------------ 2) iki model
print("=== First models (SOH error in percentage points) ===")
lin = report("Linear regression", LinearRegression())
tree = report("Decision tree (depth 3)", DecisionTreeRegressor(max_depth=3, random_state=0))

print("\nLinear model: SOH = b0 + b1*efc + b2*days + ...")
print(f"  b0 = {lin.intercept_:.4f}")
for f, b in zip(FEATS, lin.coef_):
    print(f"  {f:5s} {b:+.5f}")

print("\nDecision tree (depth 3), as if-else rules (value = predicted SOH):")
print(export_text(tree, feature_names=FEATS, decimals=3))

# ------------------------------------------------------------------ 3) derinlik taraması
depths = range(1, 13)
tr_err, te_err = [], []
for d in depths:
    t = DecisionTreeRegressor(max_depth=d, random_state=0).fit(X_tr, y_tr)
    tr_err.append(100 * np.sqrt(mean_squared_error(y_tr, t.predict(X_tr))))
    te_err.append(100 * np.sqrt(mean_squared_error(y_te, t.predict(X_te))))
print("=== Depth sweep (decision tree) ===")
print(" depth  train RMSE  test RMSE  leaves")
for d, a, b in zip(depths, tr_err, te_err):
    n = DecisionTreeRegressor(max_depth=d, random_state=0).fit(X_tr, y_tr).get_n_leaves()
    print(f" {d:5d}  {a:9.2f}  {b:9.2f}  {n:6d}")
best = depths[int(np.argmin(te_err))]
print(f"Training error goes to ~0 (memorisation), but test error stops improving after "
      f"depth ~3 and only jumps around (lowest here at depth {best}).")
print("Question for step 3: is this random test set really 'unseen'? Neighbouring check-ups "
      "of the same cell, and sister cells under the same condition, are split across train and test.")

fig, ax = plt.subplots(figsize=(7, 4.2))
ax.plot(depths, tr_err, "o-", label="Training error")
ax.plot(depths, te_err, "s-", label="Test error (unseen data)")
ax.axvline(best, c="k", ls=":", lw=1)
ax.set_xlabel("Tree depth (number of consecutive if-else questions)")
ax.set_ylabel("SOH RMSE [%]")
ax.set_title("Training error keeps falling, test error does not (random split)")
ax.grid(alpha=.3); ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(FIG, "ml_depth_sweep.png"), dpi=200)
print("Saved: results/ml_depth_sweep.png")
