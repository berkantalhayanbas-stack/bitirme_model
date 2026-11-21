"""
Akım sensörü kayması taraması (A9): açılış sıfır akım kontrolü olmadan / ile.

Kontrolsüz ECU kaymayı yalnız sürüşte EKF'nin b_I durumundan, yavaş ve eksik buluyordu (A3).
Kontrollü ECU ilk 1 s kontaktörü açık tutar (akım kesin 0), ölçülen ortalamayı ofset alır:
|ofset| <= 3 A -> EKF b_I bununla başlar; büyüğü -> akım sensörü arızası (LIMP, neden 32).
S1 normal sürüş, aynı gürültü tohumu, kayma -12..+12 A.

Kullanım: python bias_sweep.py   -> results/bias_sweep.csv, results/bias_sweep.png
"""
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")
BIASES = [-12, -10, -8, -6, -4, -3, -2, -1, 0, 1, 2, 3, 4, 6, 8, 10, 12]


def job(args):
    from closed_loop import run
    b, zc = args
    I = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv")).i_pack.values
    d = run(I, noise={"bias": float(b)}, zero_check=zc)
    e = 100 * (d.soc_est - d.soc)[d.t > 60]
    sens = (d.cause.astype(int) & 32) > 0
    return dict(bias=b, zero_check=int(zc), soc_rmse=float(np.sqrt(np.mean(e ** 2))),
                soc_max=float(np.abs(e).max()), t_detect=float(d.t[np.argmax(sens)]) if sens.any() else np.nan,
                bias_est_end=float(np.nan), pct_limp=100 * float(np.mean(d.state == 3)))


def main():
    os.chdir(HERE)
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(job, [(b, z) for z in (False, True) for b in BIASES])))
    df = df.drop(columns="bias_est_end")
    df.to_csv(os.path.join(OUT, "bias_sweep.csv"), index=False)
    print(df.pivot(index="bias", columns="zero_check", values=["soc_rmse", "t_detect"]).round(2).to_string())
    plot(df)


def plot(df):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import thesis_style as ts                       # ortak tez figür stili
    ts.apply()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 3.8))
    for zc, col, lab in ((0, ts.MUTED, "without zero-current check"), (1, ts.BLUE, "with zero-current check (A9)")):
        s = df[df.zero_check == zc].sort_values("bias")
        a1.plot(s.bias, s.soc_rmse, "o-", color=col, label=lab, ms=4)
        det = s.t_detect.fillna(1250.0)
        a2.semilogy(s.bias, det, "o-", color=col, label=lab, ms=4)
        nd = s.t_detect.isna()
        a2.plot(s.bias[nd], det[nd], "x", color=col, ms=7)
    for a in (a1, a2):
        a.axvspan(-3, 3, color=ts.BLUE, alpha=0.07, lw=0)
        a.set_xlabel("current sensor offset [A]")
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    a1.set_ylabel("SOC RMSE in normal drive S1 [% SOC]")
    a1.text(0, a1.get_ylim()[1] * 0.92, "compensated\n|offset| ≤ 3 A", ha="center", va="top", fontsize=8, color=ts.INK2)
    a1.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, 0.8))
    a2.set_ylabel("time to sensor-fault flag [s]")
    a2.axhline(1250, color=ts.MUTED, lw=0.8, ls="--")
    a2.text(12, 1250, "not detected (×)", ha="right", va="bottom", fontsize=8)
    a2.set_ylim(0.5, 2500)
    fig.suptitle("Start-up zero-current check before contactor close", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "bias_sweep.png"), dpi=200)


if __name__ == "__main__":
    import sys
    if "--plot" in sys.argv:
        plot(pd.read_csv(os.path.join(OUT, "bias_sweep.csv")))
    else:
        main()
