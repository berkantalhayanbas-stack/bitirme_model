"""2-RC parametrelerinin Kirkaldy et al. (2024) GITT verisinden uydurulması (LG M50T, BoL).

Veri: Zenodo 10.5281/zenodo.10637534 (CC BY 4.0), Expt 5, hücre A-H, RPT0,
      '25-pulse GITT 0.5C discharge' (indir_ham.py ile kirkaldy_ham/ altına).
Yöntem: her darbe (0,5C deşarj, süre Tp) bittikten sonraki dinlenme eğrisi
      V(t) = V_inf - a1 exp(-t/tau1) - a2 exp(-t/tau2)
      tau1, tau2 ızgara aramasıyla, (V_inf, a1, a2) doğrusal en küçük kareyle; sonra
      R_k = a_k / (I (1 - exp(-Tp/tau_k)))   (darbe boyunca dolan RC gerilimi)
      R0 = akım kesildiği andaki gerilim sıçraması / I.
Çıktı: SOC'ye göre tablo ve modeldeki %52 SOC değerleriyle karşılaştırma.
"""
import glob
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(HERE, "kirkaldy_ham", "**", "*RPT0 - 25-pulse GITT*.csv"), recursive=True))
TAU1 = np.geomspace(1, 60, 40)
TAU2 = np.geomspace(60, 3000, 40)


def fit_relax(t, v):
    best = None
    for t1 in TAU1:
        e1 = np.exp(-t / t1)
        for t2 in TAU2:
            A = np.column_stack([np.ones_like(t), -e1, -np.exp(-t / t2)])
            c, *_ = np.linalg.lstsq(A, v, rcond=None)
            r = np.sum((A @ c - v) ** 2)
            if c[1] > 0 and c[2] > 0 and (best is None or r < best[0]):
                best = (r, t1, t2, c)
    return best


TP1 = np.geomspace(0.5, 120, 45)
TP2 = np.geomspace(30, 3000, 45)


def fit_pulse(t, v):
    """Darbe sırasında (0,1 s örnekleme): V = c0 - c1 t - a1 (1-e^-t/t1) - a2 (1-e^-t/t2),
    c1 t = darbe boyunca OCV düşüşü (SOC değişimi, ~%4), t2 > 3 t1."""
    best = None
    for t1 in TP1:
        f1 = 1 - np.exp(-t / t1)
        for t2 in TP2:
            if t2 < 3 * t1:
                continue
            A = np.column_stack([np.ones_like(t), -t, -f1, -(1 - np.exp(-t / t2))])
            c, *_ = np.linalg.lstsq(A, v, rcond=None)
            r = np.sum((A @ c - v) ** 2)
            if c[2] > 0 and c[3] > 0 and (best is None or r < best[0]):
                best = (r, t1, t2, c)
    return best


rows = []
for f in files:
    cell = os.path.basename(f).split(" - ")[1]
    d = pd.read_csv(f)
    t, v, i = d["Time (s)"].values, d["Voltage (V)"].values, d["Current (mA)"].values / 1000.0
    T = d["Temperature (degC)"].values
    q = d["Charge (mA.h)"].values / 1000.0
    on = np.abs(i) > 0.05
    starts = np.flatnonzero(on[1:] & ~on[:-1]) + 1
    ends = np.flatnonzero(~on[1:] & on[:-1]) + 1
    q_tot = np.abs(q).max()
    for s in starts:
        e = ends[ends > s]
        if not len(e):
            continue
        e = e[0]
        nxt = starts[starts > e]
        stop = nxt[0] if len(nxt) else len(t)
        I = np.abs(np.median(i[s:e]))
        Tp = t[e - 1] - t[s]
        tr, vr = t[e:stop] - t[e], v[e:stop]
        if len(tr) < 20 or tr[-1] < 600:
            continue
        r0 = (vr[0] - v[e - 1]) / I
        fit = fit_relax(tr, vr)
        if fit is None:
            continue
        _, t1, t2, c = fit
        R1 = c[1] / (I * (1 - np.exp(-Tp / t1)))
        R2 = c[2] / (I * (1 - np.exp(-Tp / t2)))
        soc = 1 - abs(q[e]) / q_tot
        # darbe uydurması: ilk örnek (akım açıldığı an) hariç, t = 0 darbe başı
        tp, vp = t[s + 1:e] - t[s], v[s + 1:e]
        pf = fit_pulse(tp, vp)
        r0p = (v[s - 1] - v[s + 1]) / I if s > 0 else np.nan          # ilk 0,1 s örneğinde sıçrama
        p1, p2 = (pf[3][2] / I, pf[3][3] / I) if pf else (np.nan, np.nan)
        rows.append(dict(cell=cell, soc=soc, I=I, Tp=Tp, R0=r0 * 1e3, R1=R1 * 1e3, tau1=t1, R2=R2 * 1e3, tau2=t2,
                         pR0=r0p * 1e3, pR1=p1 * 1e3, ptau1=pf[1] if pf else np.nan, pR2=p2 * 1e3,
                         ptau2=pf[2] if pf else np.nan,
                         T=np.mean(T[s:stop]), dt_pulse=np.median(np.diff(t[s:e])), dt_rest=np.median(np.diff(tr[:50]))))

D = pd.DataFrame(rows)
print(f"{len(files)} hücre, {len(D)} darbe; darbe akımı {D.I.median():.2f} A, süre {D.Tp.median():.0f} s, "
      f"örnekleme darbe {D.dt_pulse.median():.2f} s / dinlenme {D.dt_rest.median():.2f} s, T {D['T'].median():.1f} C")
D["soc_bin"] = (D.soc * 20).round() / 20
tab = D.groupby("soc_bin")[["R0", "R1", "tau1", "R2", "tau2", "pR0", "pR1", "ptau1", "pR2", "ptau2"]].median()
print(tab.round(2).to_string())
mid = D[(D.soc > 0.42) & (D.soc < 0.62)]
print("\n40-60 % SOC (medyan, hucreler arasi IQR); R*: dinlenme uydurmasi, pR*: darbe uydurmasi (0,1 s):")
for k in ["R0", "R1", "tau1", "R2", "tau2", "pR0", "pR1", "ptau1", "pR2", "ptau2"]:
    print(f"  {k:5s} {mid[k].median():8.2f}  [{mid[k].quantile(.25):.2f} .. {mid[k].quantile(.75):.2f}]")
print("Model (bms_config.h): R0 26.4 mOhm, R1 9.3 mOhm tau1 10 s, R2 12 mOhm tau2 180 s")
m = mid.median(numeric_only=True)
r10 = lambda R1, t1, R2, t2: R1 * (1 - np.exp(-10 / t1)) + R2 * (1 - np.exp(-10 / t2))
print(f"R(10 s) - R(0.1 s) [Kirkaldy: 6.54 mOhm]: model {r10(9.3, 10, 12, 180):.2f}, "
      f"dinlenme uyd. {r10(m.R1, m.tau1, m.R2, m.tau2):.2f}, darbe uyd. {r10(m.pR1, m.ptau1, m.pR2, m.ptau2):.2f}")
D.to_csv(os.path.join(HERE, "gitt_fit_sonuc.csv"), index=False)
