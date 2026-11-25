"""Ön analiz: Kirkaldy yaşlanma verisinde koşul stres katsayısı S(T, m, dod) için fizik (Millner) ve ML
modellerinin bir-koşulu-dışarıda-bırak (LOCO) karşılaştırması. Veri hazırlığı aging_calibration.py ile aynı."""
import glob, os, sys
import numpy as np, pandas as pd
from scipy.optimize import least_squares
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import GradientBoostingRegressor

V = r"C:\bitirme\veri"
DATA = os.path.join(V, "kirkaldy_ozet")
meta = pd.read_excel(os.path.join(V, "experiment_metadata.xlsx"), sheet_name=None)
rows = []
for _, m in meta.items():
    for _, r in m.iterrows():
        f = glob.glob(os.path.join(DATA, r['Expt long name'], 'Summary Data', 'Performance Summary',
                                   f"Expt {r['Expt']} - cell {r['Cell']} (*"))
        if not f: continue
        d = pd.read_csv(f[0], index_col=0)
        q0 = d['C/10 Capacity [mA h]'].iloc[0] / 1000
        for _, x in d.iterrows():
            rows.append(dict(expt=str(r['Expt']), cell=r['Cell'], Tset=r['Temp'],
                             T=x['Age set av. temperature [°C]'], days=x['Days of degradation'],
                             efc=x['Charge Throughput [A h]'] / (2*q0),
                             fade=1 - x['C/10 Capacity [mA h]']/1000/q0))
D = pd.DataFrame(rows)
D['T'] = D['T'].fillna(D.groupby(['expt', 'Tset'])['T'].transform('mean'))
SOCM = {'1': 0.15, '2,2': 0.775, '3': 0.925, '5': 0.5, '4': 0.5}
DOD = {'1': 0.30, '2,2': 0.15, '3': 0.15, '5': 1.0, '4': 1.0}
D['m'] = D.expt.map(SOCM); D['dod'] = D.expt.map(DOD)
VMEAN = {}
for e, name in D.groupby('expt').cell.first().items():
    long = meta[[k for k in meta if str(meta[k]['Expt'].iloc[0]) == e][0]]['Expt long name'].iloc[0]
    fs = glob.glob(os.path.join(DATA, long, 'Summary Data', 'Ageing Sets Summary', 'Summary per Set', '*.csv'))
    VMEAN[e] = float(np.nanmean([pd.read_csv(f)['Av. Voltage [V]'].mean() for f in fs]))
D['V'] = D.expt.map(VMEAN)
D['cal'] = np.maximum(0, 7.543*D.V - 23.75)*1e6*np.exp(-6976/(D['T'] + 273.15))*D.days.fillna(0)**0.75
D = D[D.fade.notna() & D.efc.notna()]
cal = D[(D.expt != '4') & (D.fade <= 0.25) & (D.efc > 0)].copy()
cal['cond'] = cal.expt + '_' + cal.Tset.astype(str)

Tr, TMAX, KEXT = 25.0, 42.3, np.log(2)/10
def S_phys(p, dod, m, T):
    a, z, Kex, Ksoc, Klow, kh, kc, kSi = p
    main = np.exp(Ksoc*(m-0.5)/0.25)*np.exp(kh*np.maximum(0, T-Tr))*np.exp(kc*np.maximum(0, Tr-T)*m)
    si = Klow*np.exp(-m/0.1)*np.exp(kSi*(T-Tr))
    return np.exp((dod-1)/Kex)*(main+si)/(1+Klow*np.exp(-5))*np.exp(KEXT*np.maximum(0, T-TMAX))
def fit_phys(d):
    res = lambda p: p[0]*(S_phys(p, d.dod.values, d.m.values, d['T'].values)*d.efc.values)**p[1] + d.cal.values - d.fade.values
    best = None
    for a0 in [0.002, 0.004]:
        for Ks0 in [0.5, 1.5]:
            r = least_squares(res, [a0, 0.57, 0.3, Ks0, 20, 0.01, 0.05, 0.05],
                              bounds=([1e-6, 0.3, 0.02, -5, 0, 0, 0, 0], [1, 1.2, 5, 10, 1000, 0.2, 0.5, 0.3]), x_scale='jac')
            if best is None or r.cost < best.cost: best = r
    return best.x

def fit_cond_S(d):
    """Paylaşılan a, z + koşul başına serbest log S (veriden 'gözlenen' stres katsayısı)."""
    conds = sorted(d.cond.unique()); ix = d.cond.map({c: k for k, c in enumerate(conds)}).values
    def res(q):
        a, z, ls = q[0], q[1], q[2:]
        return a*(np.exp(ls[ix])*d.efc.values)**z + d.cal.values - d.fade.values
    q0 = np.r_[0.0035, 0.53, np.zeros(len(conds))]
    r = least_squares(res, q0, bounds=(np.r_[1e-6, 0.3, -6*np.ones(len(conds))], np.r_[1, 1.2, 6*np.ones(len(conds))]))
    a, z = r.x[0], r.x[1]
    f = d.groupby('cond')[['T', 'm', 'dod']].mean().loc[conds]
    return a, z, conds, r.x[2:], f

def rmse_pred(a, z, S, g):
    return 100*np.sqrt(np.mean((a*(S*g.efc.values)**z + g.cal.values - g.fade.values)**2))

out = []
for c in sorted(cal.cond.unique()):
    tr, te = cal[cal.cond != c], cal[cal.cond == c]
    # fizik
    p = fit_phys(tr)
    r_phys = rmse_pred(p[0], p[1], S_phys(p, te.dod.values, te.m.values, te['T'].values), te)
    # ML: eğitim koşullarının log S'si -> özelliklerden
    a, z, conds, ls, f = fit_cond_S(tr)
    X, Xt = f[['T', 'm', 'dod']].values, te[['T', 'm', 'dod']].mean().values[None, :]
    tree = DecisionTreeRegressor(max_depth=3, min_samples_leaf=2, random_state=0).fit(X, ls)
    gbm = GradientBoostingRegressor(n_estimators=60, max_depth=2, learning_rate=0.1, random_state=0).fit(X, ls)
    r_tree = rmse_pred(a, z, np.exp(tree.predict(Xt)[0]), te)
    r_gbm = rmse_pred(a, z, np.exp(gbm.predict(Xt)[0]), te)
    # hibrit: fizik S x exp(ağaç kalıntısı); kalıntı = log S_gözlenen - log S_fizik (eğitim koşullarında)
    ls_phys = np.log(S_phys(p, f.dod.values, f.m.values, f['T'].values))
    hyb = DecisionTreeRegressor(max_depth=2, min_samples_leaf=3, random_state=0).fit(X, ls - ls_phys)
    S_h = S_phys(p, te.dod.values, te.m.values, te['T'].values)*np.exp(hyb.predict(Xt)[0])
    r_hyb = rmse_pred(a, z, S_h, te)
    out.append(dict(cond=c, T=round(te['T'].mean(), 1), m=te.m.iloc[0], dod=te.dod.iloc[0],
                    physics=r_phys, tree=r_tree, gbm=r_gbm, hybrid=r_hyb))
    print(out[-1], flush=True)
R = pd.DataFrame(out)
print(R.round(2).to_string(index=False))
print("mean RMSE [%]:", R[['physics', 'tree', 'gbm', 'hybrid']].mean().round(2).to_dict())
print("max  RMSE [%]:", R[['physics', 'tree', 'gbm', 'hybrid']].max().round(2).to_dict())
# tüm veriyle koşul S'leri (25 °C, m 0,5, dod 1 = referansa göre)
a, z, conds, ls, f = fit_cond_S(cal)
f['S_obs'] = np.exp(ls); p = fit_phys(cal); f['S_phys'] = S_phys(p, f.dod.values, f.m.values, f['T'].values)
print(f.round(3).to_string())
R.to_csv(os.path.join(os.path.dirname(__file__), "stress_loco.csv"), index=False)
