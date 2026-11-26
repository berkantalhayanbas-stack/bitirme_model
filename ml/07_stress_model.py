"""
ADIM 7 — Stres katsayısı S(T, m, dod): hibrit (fizik x ağaç kalıntısı) model, eğit ve aktar
==========================================================================================
06_stress_loco.py'nin kararı (bir-koşulu-dışarıda-bırak RMSE ortalaması: fizik %3,78, saf ağaç %5,23,
hibrit %3,64): fizik modeli (Millner tipi, aging_stress.m) eğilimleri taşır, derinliği 2 olan bir karar ağacı
koşul başına gözlenen log S'nin fizikten sapmasını düzeltir. S_h = S_fizik x exp(ağaç).

Bu adım:
  1. Fizik parametrelerini ve koşul S'lerini TÜM 12 çevrim koşuluyla yeniden uydurur (Expt 4 sürüş çevrimi
     doğrulama için dışarıda, aging_calibration.py ile aynı).
  2. Kalıntı ağacını eğitir, fiziksel eğilim kontrollerini yazdırır.
  3. Üç dile aktarır:
       bms_ecu/bms/common/stress_model.{h,c}  -> STM32 (float32, if-else + üstel terimler)
       twin/stress_model.py                     -> Python ikiz / karar mantığı
       simulink/stress_model.m                  -> MATLAB Function (kod üretimine uygun)
  4. C ve Python'u 10 000 rastgele girdide karşılaştırır (göreli fark < 1e-5).

Çalıştırma:   python 07_stress_model.py      (C kontrolü için gcc; MATLAB'ın MinGW'si de aranır)
"""
import glob
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from sklearn.tree import DecisionTreeRegressor, export_text

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
V = os.path.join(ROOT, "veri")
ECU_COMMON = r"C:\Users\berka\STM32CubeIDE\workspace_2.2.0\bms_ecu\bms\common"

# ------------------------------------------------------------------ veri (06_stress_loco.py ile aynı)
DATA = os.path.join(V, "kirkaldy_ozet")
meta = pd.read_excel(os.path.join(V, "experiment_metadata.xlsx"), sheet_name=None)
rows = []
for _, mt in meta.items():
    for _, r in mt.iterrows():
        f = glob.glob(os.path.join(DATA, r['Expt long name'], 'Summary Data', 'Performance Summary',
                                   f"Expt {r['Expt']} - cell {r['Cell']} (*"))
        if not f:
            continue
        d = pd.read_csv(f[0], index_col=0)
        q0 = d['C/10 Capacity [mA h]'].iloc[0] / 1000
        for _, x in d.iterrows():
            rows.append(dict(expt=str(r['Expt']), cell=r['Cell'], Tset=r['Temp'],
                             T=x['Age set av. temperature [°C]'], days=x['Days of degradation'],
                             efc=x['Charge Throughput [A h]'] / (2 * q0),
                             fade=1 - x['C/10 Capacity [mA h]'] / 1000 / q0))
D = pd.DataFrame(rows)
D['T'] = D['T'].fillna(D.groupby(['expt', 'Tset'])['T'].transform('mean'))
SOCM = {'1': 0.15, '2,2': 0.775, '3': 0.925, '5': 0.5, '4': 0.5}
DOD = {'1': 0.30, '2,2': 0.15, '3': 0.15, '5': 1.0, '4': 1.0}
D['m'] = D.expt.map(SOCM)
D['dod'] = D.expt.map(DOD)
VMEAN = {}
for e, name in D.groupby('expt').cell.first().items():
    long = meta[[k for k in meta if str(meta[k]['Expt'].iloc[0]) == e][0]]['Expt long name'].iloc[0]
    fs = glob.glob(os.path.join(DATA, long, 'Summary Data', 'Ageing Sets Summary', 'Summary per Set', '*.csv'))
    VMEAN[e] = float(np.nanmean([pd.read_csv(f)['Av. Voltage [V]'].mean() for f in fs]))
D['V'] = D.expt.map(VMEAN)
CAL_C1, CAL_C0, CAL_SCALE, CAL_EA, CAL_EXP = 7.543, -23.75, 1e6, 6976.0, 0.75   # Schmalstieg 2014 (literatür)
D['cal'] = np.maximum(0, CAL_C1 * D.V + CAL_C0) * CAL_SCALE * np.exp(-CAL_EA / (D['T'] + 273.15)) \
    * D.days.fillna(0) ** CAL_EXP
D = D[D.fade.notna() & D.efc.notna()]
cal = D[(D.expt != '4') & (D.fade <= 0.25) & (D.efc > 0)].copy()
cal['cond'] = cal.expt + '_' + cal.Tset.astype(str)

TR, TMAX, KEXT = 25.0, 42.3, np.log(2) / 10


def S_phys(p, dod, m, T):
    a, z, Kex, Ksoc, Klow, kh, kc, kSi = p
    main = np.exp(Ksoc * (m - 0.5) / 0.25) * np.exp(kh * np.maximum(0, T - TR)) * np.exp(kc * np.maximum(0, TR - T) * m)
    si = Klow * np.exp(-m / 0.1) * np.exp(kSi * (T - TR))
    return np.exp((dod - 1) / Kex) * (main + si) / (1 + Klow * np.exp(-5)) * np.exp(KEXT * np.maximum(0, T - TMAX))


def fit_phys(d):
    res = lambda p: p[0] * (S_phys(p, d.dod.values, d.m.values, d['T'].values) * d.efc.values) ** p[1] \
        + d.cal.values - d.fade.values
    best = None
    for a0 in [0.002, 0.004]:
        for Ks0 in [0.5, 1.5]:
            r = least_squares(res, [a0, 0.57, 0.3, Ks0, 20, 0.01, 0.05, 0.05],
                              bounds=([1e-6, 0.3, 0.02, -5, 0, 0, 0, 0], [1, 1.2, 5, 10, 1000, 0.2, 0.5, 0.3]),
                              x_scale='jac')
            if best is None or r.cost < best.cost:
                best = r
    return best.x


def fit_cond_S(d):
    conds = sorted(d.cond.unique())
    ix = d.cond.map({c: k for k, c in enumerate(conds)}).values

    def res(q):
        return q[0] * (np.exp(q[2:][ix]) * d.efc.values) ** q[1] + d.cal.values - d.fade.values
    q0 = np.r_[0.0035, 0.53, np.zeros(len(conds))]
    r = least_squares(res, q0, bounds=(np.r_[1e-6, 0.3, -6 * np.ones(len(conds))], np.r_[1, 1.2, 6 * np.ones(len(conds))]))
    f = d.groupby('cond')[['T', 'm', 'dod']].mean().loc[conds]
    return r.x[0], r.x[1], conds, r.x[2:], f


# ------------------------------------------------------------------ eğitim (tüm 12 koşul)
p = fit_phys(cal)
a, z, conds, ls, f = fit_cond_S(cal)
X = f[['T', 'm', 'dod']].values
ls_phys = np.log(S_phys(p, f.dod.values, f.m.values, f['T'].values))
FEATS = ["T", "m", "dod"]
tree = DecisionTreeRegressor(max_depth=2, min_samples_leaf=3, random_state=0).fit(X, ls - ls_phys)
t = tree.tree_
print("Physics parameters:", dict(zip(['a', 'z', 'Kex', 'Ksoc', 'Klow', 'kh', 'kc', 'kSi'], np.round(p, 5))))
print(f"Damage law (shared): fade_cyc = a (sum S dEFC)^z, a = {a:.6f}, z = {z:.4f}")
print("Residual tree (log S_obs - log S_phys):")
print(export_text(tree, feature_names=FEATS, decimals=3))


def resid_knots(f, ls, ls_phys):
    """Ağaç yalnız T'ye göre bölüyor (yapraklar = üç sıcaklık grubu). Çevrimiçi kullanımda basamak olmasın diye
    aynı düzeltme grup başına ortalama kalıntının grup ortalama T'si arasında doğrusal ara değeri olarak alınır
    (uçlarda sabit)."""
    g = pd.DataFrame(dict(T=f['T'].values, r=ls - ls_phys, grp=np.round(f['T'].values / 12.5)))
    k = g.groupby('grp')[['T', 'r']].mean().sort_values('T')
    return k['T'].values, k['r'].values


KT, KR = resid_knots(f, ls, ls_phys)
print("Smooth residual knots (T [C] -> log correction):", dict(zip(np.round(KT, 2), np.round(KR, 3))))


def S_hyb(T, m, dod):
    T, m, dod = np.broadcast_arrays(np.asarray(T, float), np.asarray(m, float), np.asarray(dod, float))
    return S_phys(p, dod, m, T) * np.exp(np.interp(T, KT, KR))


# LOCO: ağaç kalıntısı ile yumuşak kalıntının karşılaştırması (06 ile aynı yöntem)
if "--loco" in sys.argv:
    out = []
    for cnd in sorted(cal.cond.unique()):
        tr, te = cal[cal.cond != cnd], cal[cal.cond == cnd]
        pp = fit_phys(tr)
        aa, zz, cc, ll, ff = fit_cond_S(tr)
        lp = np.log(S_phys(pp, ff.dod.values, ff.m.values, ff['T'].values))
        Sp = S_phys(pp, te.dod.values, te.m.values, te['T'].values)
        hy = DecisionTreeRegressor(max_depth=2, min_samples_leaf=3, random_state=0).fit(ff[['T', 'm', 'dod']].values, ll - lp)
        kt, kr = resid_knots(ff, ll, lp)
        rm = lambda S, A=aa, Z=zz: 100 * np.sqrt(np.mean((A * (S * te.efc.values) ** Z + te.cal.values - te.fade.values) ** 2))
        out.append(dict(cond=cnd, physics=rm(Sp, pp[0], pp[1]), hybrid_tree=rm(Sp * np.exp(hy.predict(te[['T', 'm', 'dod']].mean().values[None, :])[0])),
                        hybrid_smooth=rm(Sp * np.exp(np.interp(te['T'].values, kt, kr)))))
        print(out[-1], flush=True)
    L = pd.DataFrame(out)
    print("LOCO mean RMSE [%]:", L.drop(columns='cond').mean().round(2).to_dict())
    print("LOCO max  RMSE [%]:", L.drop(columns='cond').max().round(2).to_dict())
    L.round(3).to_csv(os.path.join(HERE, "stress_model_loco.csv"), index=False)


f['S_obs'] = np.exp(ls)
f['S_phys'] = np.exp(ls_phys)
f['S_hyb'] = S_hyb(f['T'].values, f.m.values, f.dod.values)
print(f.round(3).to_string())
fit_rmse = 100 * np.sqrt(np.mean((a * (S_hyb(cal['T'].values, cal.m.values, cal.dod.values) * cal.efc.values) ** z
                                   + cal.cal.values - cal.fade.values) ** 2))
print(f"Training RMSE of capacity fade (hybrid, all 12 conditions): {fit_rmse:.2f} %")

# fiziksel eğilim kontrolleri (yazdırılır; tezde tablo)
print("\nTrend checks (S at dod 1 unless noted):")
for m_ in (0.3, 0.5, 0.8):
    print(f"  m {m_}: T 5/10/25/40/50 C ->", np.round(S_hyb([5, 10, 25, 40, 50], m_, 1.0), 3))
print("  25 C, m 0.5: dod 0.1/0.3/0.6/1 ->", np.round(S_hyb(25, 0.5, [0.1, 0.3, 0.6, 1.0]), 3))
print("  25 C, dod 1: m 0.1/0.3/0.5/0.7/0.9 ->", np.round(S_hyb(25, [0.1, 0.3, 0.5, 0.7, 0.9], 1.0), 3))
s_ref = float(S_hyb(25.0, 0.5, 1.0))
print(f"  reference S(25 C, 0.5, 1) = {s_ref:.4f}")

# ------------------------------------------------------------------ kod üretimi
PN = dict(zip(['a', 'z', 'Kex', 'Ksoc', 'Klow', 'kh', 'kc', 'kSi'], p))
NORM = 1.0 + PN['Klow'] * np.exp(-5.0)


def emit_interp(lang):
    """Kalıntı r(T): düğümler arasında doğrusal, uçlarda sabit (np.interp ile aynı)."""
    NL = chr(10)
    seg = [((KR[i + 1] - KR[i]) / (KT[i + 1] - KT[i]), i) for i in range(len(KT) - 1)]
    out = []
    if lang == "c":
        out.append(f"    if (T <= {KT[0]:.7f}f) r = {KR[0]:.7f}f;")
        out += [f"    else if (T <= {KT[i + 1]:.7f}f) r = {KR[i]:.7f}f + {k:.7e}f * (T - {KT[i]:.7f}f);" for k, i in seg]
        out.append(f"    else r = {KR[-1]:.7f}f;")
    elif lang == "py":
        out += [f"    if T <= {KT[0]:.7f}:", f"        r = {KR[0]:.7f}"]
        for k, i in seg:
            out += [f"    elif T <= {KT[i + 1]:.7f}:", f"        r = {KR[i]:.7f} + {k:.7e} * (T - {KT[i]:.7f})"]
        out += ["    else:", f"        r = {KR[-1]:.7f}"]
    else:
        out += [f"if T <= {KT[0]:.7f}", f"    r = {KR[0]:.7f};"]
        for k, i in seg:
            out += [f"elseif T <= {KT[i + 1]:.7f}", f"    r = {KR[i]:.7f} + {k:.7e} * (T - {KT[i]:.7f});"]
        out += ["else", f"    r = {KR[-1]:.7f};", "end"]
    return NL.join(out) + NL


HDR = (f"AUTO-GENERATED by C:\\bitirme\\ml\\07_stress_model.py, do not edit by hand.\n"
       f"Hybrid cycle-ageing stress factor S(T, m, dod) per equivalent full cycle, LG M50T (Kirkaldy et al. 2024,\n"
       f"12 cycling conditions): physics (Millner-type, aging_stress.m) x exp(r(T)), r = data residual,\n"
       f"piecewise linear between the three temperature groups (the depth-2 residual tree splits only on T).\n"
       f"S(25 C, m 0.5, dod 1) = {s_ref:.4f}. Damage law: fade_cyc = STRESS_A (sum S dEFC)^STRESS_Z.\n"
       f"Calendar fade (Schmalstieg 2014, NMC, literature): max(0, C1 V + C0) SCALE exp(-EA / T_K) days^EXP.")

h = f"""/* stress_model.h -- {HDR.replace(chr(10), chr(10) + ' * ')}
 */
#ifndef STRESS_MODEL_H
#define STRESS_MODEL_H

#define STRESS_A        {a:.7e}f
#define STRESS_Z        {z:.7f}f
#define STRESS_S_REF    {s_ref:.7f}f
#define STRESS_CAL_C1   {CAL_C1:.4f}f
#define STRESS_CAL_C0   {CAL_C0:.4f}f
#define STRESS_CAL_SC   {CAL_SCALE:.1f}f
#define STRESS_CAL_EA   {CAL_EA:.1f}f
#define STRESS_CAL_EXP  {CAL_EXP:.4f}f

/* T: hücre sıcaklığı [°C], m: yarım çevrimin ortalama SOC'si [0-1], dod: yarım çevrimin derinliği [0-1] */
float stress_S(float T, float m, float dod);
/* Takvim yaşlanma katsayısı alpha(V, T) [1/gün^EXP]: V hücre gerilimi [V], T [°C] */
float stress_cal_alpha(float V, float T);

#endif
"""
c = f"""/* stress_model.c -- AUTO-GENERATED by C:\\bitirme\\ml\\07_stress_model.py, do not edit by hand. */
#include <math.h>
#include "stress_model.h"

float stress_S(float T, float m, float dod)
{{
    const float main_ = expf({PN['Ksoc']:.7e}f * (m - 0.5f) / 0.25f)
                      * expf({PN['kh']:.7e}f * fmaxf(0.0f, T - {TR:.1f}f))
                      * expf({PN['kc']:.7e}f * fmaxf(0.0f, {TR:.1f}f - T) * m);
    const float si    = {PN['Klow']:.7e}f * expf(-m / 0.1f) * expf({PN['kSi']:.7e}f * (T - {TR:.1f}f));
    const float phys  = expf((dod - 1.0f) / {PN['Kex']:.7e}f) * (main_ + si) / {NORM:.7e}f
                      * expf({KEXT:.7e}f * fmaxf(0.0f, T - {TMAX:.1f}f));
    float r;
{emit_interp("c")}    return phys * expf(r);
}}

float stress_cal_alpha(float V, float T)
{{
    return fmaxf(0.0f, STRESS_CAL_C1 * V + STRESS_CAL_C0) * STRESS_CAL_SC * expf(-STRESS_CAL_EA / (T + 273.15f));
}}
"""
py = f'''r"""stress_model.py -- {HDR}"""
import math

STRESS_A = {a:.7e}
STRESS_Z = {z:.7f}
STRESS_S_REF = {s_ref:.7f}
CAL_C1, CAL_C0, CAL_SC, CAL_EA, CAL_EXP = {CAL_C1}, {CAL_C0}, {CAL_SCALE}, {CAL_EA}, {CAL_EXP}


def stress_S(T, m, dod):
    main_ = (math.exp({PN['Ksoc']:.7e} * (m - 0.5) / 0.25) * math.exp({PN['kh']:.7e} * max(0.0, T - {TR:.1f}))
             * math.exp({PN['kc']:.7e} * max(0.0, {TR:.1f} - T) * m))
    si = {PN['Klow']:.7e} * math.exp(-m / 0.1) * math.exp({PN['kSi']:.7e} * (T - {TR:.1f}))
    phys = (math.exp((dod - 1.0) / {PN['Kex']:.7e}) * (main_ + si) / {NORM:.7e}
            * math.exp({KEXT:.7e} * max(0.0, T - {TMAX:.1f})))
{emit_interp("py")}    return phys * math.exp(r)


def stress_cal_alpha(V, T):
    return max(0.0, CAL_C1 * V + CAL_C0) * CAL_SC * math.exp(-CAL_EA / (T + 273.15))
'''
mfile = f"""function S = stress_model(T, m, dod)
%STRESS_MODEL  {HDR.replace(chr(10), chr(10) + '%   ')}
%   T [degC], m mean SOC of the half cycle [0-1], dod depth of the half cycle [0-1]

%#codegen
main_ = exp({PN['Ksoc']:.7e} * (m - 0.5) / 0.25) * exp({PN['kh']:.7e} * max(0, T - {TR:.1f})) ...
        * exp({PN['kc']:.7e} * max(0, {TR:.1f} - T) * m);
si = {PN['Klow']:.7e} * exp(-m / 0.1) * exp({PN['kSi']:.7e} * (T - {TR:.1f}));
phys = exp((dod - 1) / {PN['Kex']:.7e}) * (main_ + si) / {NORM:.7e} * exp({KEXT:.7e} * max(0, T - {TMAX:.1f}));
{emit_interp("m")}S = phys * exp(r);
end
"""
open(os.path.join(ECU_COMMON, "stress_model.h"), "w", encoding="utf-8").write(h)
open(os.path.join(ECU_COMMON, "stress_model.c"), "w", encoding="utf-8").write(c)
open(os.path.join(ROOT, "twin", "stress_model.py"), "w", encoding="utf-8").write(py)
open(os.path.join(ROOT, "simulink", "stress_model.m"), "w", encoding="utf-8").write(mfile)
print("\nWritten: bms_ecu/bms/common/stress_model.{h,c}, twin/stress_model.py, simulink/stress_model.m")

# ------------------------------------------------------------------ eşdeğerlik: sklearn / Python / C
sys.path.insert(0, os.path.join(ROOT, "twin"))
import importlib
import stress_model as SM
importlib.reload(SM)
rng = np.random.default_rng(1)
Q = np.column_stack([rng.uniform(-10, 60, 10000), rng.uniform(0, 1, 10000), rng.uniform(0, 1, 10000)])
ref = S_hyb(Q[:, 0], Q[:, 1], Q[:, 2])
pyv = np.array([SM.stress_S(*q) for q in Q])
print(f"Python vs sklearn: max rel diff {np.max(np.abs(pyv / ref - 1)):.2e}")
gcc = shutil.which("gcc") or next(iter(glob.glob(
    r"C:\ProgramData\MATLAB\SupportPackages\*\3P.instrset\mingw_w64.instrset\bin\gcc.exe")), None)
if gcc is None:
    print("gcc not found: C check skipped.")
else:
    tmp = os.path.join(HERE, "_ctest")
    os.makedirs(tmp, exist_ok=True)
    Q32 = Q.astype(np.float32)
    np.savetxt(os.path.join(tmp, "s_in.txt"), Q32, fmt="%.9g")
    open(os.path.join(tmp, "s_main.c"), "w").write(
        '#include <stdio.h>\n#include "stress_model.h"\nint main(void){float x[3];'
        'while(scanf("%f %f %f",x,x+1,x+2)==3) printf("%.9g\\n", stress_S(x[0],x[1],x[2])); return 0;}\n')
    exe = os.path.join(tmp, "s.exe")
    env = dict(os.environ, PATH=os.path.dirname(gcc) + os.pathsep + os.environ["PATH"])
    subprocess.run([gcc, "-O2", "-I", ECU_COMMON, os.path.join(tmp, "s_main.c"),
                    os.path.join(ECU_COMMON, "stress_model.c"), "-lm", "-o", exe], check=True, env=env)
    out = subprocess.run([exe], stdin=open(os.path.join(tmp, "s_in.txt")), capture_output=True, text=True,
                         check=True, env=env).stdout
    cv = np.array([float(x) for x in out.split()])
    ref32 = S_hyb(Q32[:, 0].astype(float), Q32[:, 1].astype(float), Q32[:, 2].astype(float))
    d = np.max(np.abs(cv / ref32 - 1))
    print(f"C (float32) vs sklearn: max rel diff {d:.2e} over {len(cv)} inputs -> {'PASS' if d < 1e-5 else 'FAIL'}")
    shutil.rmtree(tmp, ignore_errors=True)
f.round(4).to_csv(os.path.join(HERE, "stress_model_conditions.csv"))
