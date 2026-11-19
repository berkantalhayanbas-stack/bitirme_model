"""
Duyarlılık analizi (A3): gerçek batarya modelimizden farklıysa ECU ne kadar yanılır?

İkizin (gerçeğin) parametreleri tek tek bozulur, ECU (EKF, sıcaklık gözlemcisi, karar) nominal
parametrelerle çalışmaya devam eder (closed_loop.run(truth=..., noise=...)). Aynı gürültü tohumu
(seed 7) kullanılır: farklar yalnız parametreden gelir. Aralıklar: ölçülen saçılmanın birkaç
katı (R0 ±%20: Kirkaldy BoL sd %3, en çok +%13; kapasite ±%5: sd %0,44) ve varsayılan
parametrelerde ±%50 (R1, R2, τ2, Rc, R_u), OCV ±15 mV (eski Chen tablosu 10-15 mV farklıydı),
sensör gürültüsü 2 kat, akım kayması 2 A.

Senaryolar (karar açık, test_closed_loop ile aynı):
  S1 normal sürüş         -> SOC hatası (RMSE, en büyük), çekirdek kestirim hatası, yanlış kısıtlama
  S2 40 °C + soğutma x4   -> T_core en çok (< 55 °C kabul)
  S3 derin deşarj + zayıf -> V_min (>= 2,8 V kabul)
  S4 tam şarj + zayıf     -> V_max (<= 4,2 V kabul)
Tüm koşularda yanlış SAFE-STOP aranır.

Kullanım: python sensitivity.py [--plot]   -> results/sensitivity.csv, results/sensitivity.png
"""
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")

CASES = [("baseline", {}, {})]
for k, lo, hi, lab in (("r0", 0.8, 1.2, "R0"), ("r1", 0.5, 1.5, "R1"), ("r2", 0.5, 1.5, "R2"),
                       ("c2", 0.5, 1.5, "tau2 (C2)"), ("capacity_ah", 0.95, 1.05, "capacity"),
                       ("ru", 0.5, 2.0, "R_u"), ("rc", 0.5, 1.5, "R_c"), ("cc", 0.8, 1.2, "C_core")):
    CASES += [(f"{lab} x{lo:g}", {k: lo}, {}), (f"{lab} x{hi:g}", {k: hi}, {})]
CASES += [("OCV -15 mV", {"ocv_off": -0.015}, {}), ("OCV +15 mV", {"ocv_off": 0.015}, {}),
          ("Ea x0.5", {"ea_r0": 0.5, "ea_r1": 0.5, "ea_r2": 0.5}, {}),
          ("Ea x1.5", {"ea_r0": 1.5, "ea_r1": 1.5, "ea_r2": 1.5}, {}),
          ("V noise x2", {}, {"sv": 0.5}), ("I noise x2", {}, {"si": 1.0}),
          ("I bias 2 A", {}, {"bias": 2.0}), ("T noise x2", {}, {"st": 0.6})]


def scenarios():
    ref = pd.read_csv(os.path.join(HERE, "..", "simulink", "twin_reference.csv"))
    I = ref.i_pack.values
    return {"S1": (I, {}),
            "S2": (np.clip(1.6 * I, -40.7, 87.3), dict(T_amb=40, ru_factor=4)),
            "S3": (I, dict(soc0=0.4, weak=True)),
            "S4": (-40.7 * np.ones(18000), dict(soc0=0.8, weak=True))}


def job(args):
    from closed_loop import run
    case, truth, noise, sc = args
    I, kw = scenarios()[sc]
    d = run(I, truth=truth, noise=noise, **kw)
    m = d.t > 60.0
    e = 100 * (d.soc_est - d.soc)[m]
    st = d.state.values
    return dict(case=case, scenario=sc, soc_rmse=float(np.sqrt(np.mean(e ** 2))),
                soc_max=float(np.abs(e).max()), tc_err_max=float(np.abs(d.tc_hat - d.tc)[m].max()),
                tcore_max=float(d.tc.max()), vmin=float(d.vmin.min()), vmax=float(d.vmax.max()),
                pct_normal=100 * float(np.mean(st == 1)), pct_limp=100 * float(np.mean(st == 3)),
                safe=int((st == 4).any()), transitions=int(np.sum(np.diff(st) != 0)),
                ah=float(d.I.sum() * 0.1 / 3600))


def main():
    os.chdir(HERE)
    jobs = [(c, t, n, s) for c, t, n in CASES for s in ("S1", "S2", "S3", "S4")]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        rows = list(ex.map(job, jobs))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "sensitivity.csv"), index=False)
    w = df.pivot(index="case", columns="scenario")
    t = pd.DataFrame({
        "S1 SOC RMSE %": w["soc_rmse"]["S1"], "S1 SOC max %": w["soc_max"]["S1"],
        "S1 Tc err max": w["tc_err_max"]["S1"], "S1 %NORMAL": w["pct_normal"]["S1"],
        "S2 Tcore max": w["tcore_max"]["S2"], "S3 Vmin": w["vmin"]["S3"], "S4 Vmax": w["vmax"]["S4"],
        "any SAFE": w["safe"].max(axis=1)}).reindex([c for c, _, _ in CASES])
    pd.set_option("display.width", 200)
    print(t.round(3).to_string())
    ok = (t["S2 Tcore max"] < 55) & (t["S3 Vmin"] >= 2.8) & (t["S4 Vmax"] <= 4.2) & (t["any SAFE"] == 0)
    print(f"\nacceptance kept (S2 < 55 °C, S3 >= 2.8 V, S4 <= 4.2 V, no SAFE): {int(ok.sum())}/{len(ok)}")
    print("failed:", list(t.index[~ok]))
    plot(df)


def plot(df):
    """Tornado: S1 SOC RMSE, her bozulma için; sahte LIMP (sensör nedeni) olanlar işaretli."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s1 = df[df.scenario == "S1"].set_index("case").reindex([c for c, _, _ in CASES])
    base = s1.loc["baseline", "soc_rmse"]
    s1 = s1.drop("baseline")
    fig, ax = plt.subplots(figsize=(7.4, 6.2))
    y = np.arange(len(s1))[::-1]
    sensor = s1.index.str.contains("noise|bias")
    col = np.where(s1.pct_limp > 1, "#eb6834", np.where(sensor, "#9a9990", "#2a78d6"))
    ax.barh(y, s1.soc_rmse, color=col, height=0.62)
    ax.axvline(base, color="#1f1f1e", lw=1, ls="--")
    ax.text(base, len(s1) - 0.3, f" baseline {base:.2f} %", fontsize=8, va="bottom")
    for yi, (c, r) in zip(y, s1.iterrows()):
        txt = f"{r.soc_rmse:.2f}"
        if r.pct_limp > 1:
            txt += f"  false LIMP {r.pct_limp:.0f} % of drive"
        ax.text(r.soc_rmse + 0.03, yi, txt, va="center", fontsize=7.5)
    ax.set_yticks(y, s1.index, fontsize=8)
    ax.set_xlim(0, 3.4)
    ax.set_xlabel("SOC estimation RMSE in normal drive S1 [% SOC]  (ECU keeps nominal parameters)")
    ax.set_title("Sensitivity: plant parameter / sensor mismatch vs ECU", loc="left", fontsize=10,
                 fontweight="bold")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#2a78d6", label="plant parameter"), Patch(color="#9a9990", label="sensor"),
                       Patch(color="#eb6834", label="false sensor-fault LIMP (cause 32)")],
              frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="x", color="#d6d5cf", lw=0.6); ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "sensitivity.png"), dpi=200)


if __name__ == "__main__":
    import sys
    if "--plot" in sys.argv:        # yalnız figür, kayıtlı sonuçlardan
        plot(pd.read_csv(os.path.join(OUT, "sensitivity.csv")))
    else:
        main()
