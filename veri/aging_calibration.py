"""
Yaşlanma modeli kalibrasyonu: Kirkaldy vd. (2024) LG M50T açık verisi.
Model (Millner 2010 stres yapısı, NMC811/SiOx için uyarlanmış):

  fade = a * (sum_i S_i * dEFC_i) ** z
  S(DoD, m, T) = exp((DoD-1)/Kex) * [ main + si ] / norm
      main = exp(Ksoc*(m-0.5)/0.25) * exp(kh*max(0,T-Tr)) * exp(kc*max(0,Tr-T)*m)
      si   = Klow * exp(-m/0.1) * exp(kSi*(T-Tr))
      norm = 1 + Klow*exp(-5)     (S(1, 0.5, Tr) = 1)
  Veri aralığı dışı (T > 42.3 °C, en sıcak test hücresi): S *= exp(ln2/10 * (T - 42.3))
      (Millner 2010 Tfact; kalibre EDİLMEMİŞ, muhafazakâr ekstrapolasyon)
  Takvim kaybı (Schmalstieg vd. 2014, NMC; literatürden, kalibre EDİLMEMİŞ):
      fade_cal = alpha(V, T) * t_gün^0.75,  alpha = (7.543 V - 23.75)e6 * exp(-6976 / T_K)
  Toplam: fade = fade_cyc + fade_cal. Test süresindeki takvim kaybı fit sırasında düşülür
  (çift sayımı önlemek için); böylece çevrim parametreleri yalnız çevrim etkisini temsil eder.
  Kalibrasyon: Expt 1, 2, 3, 5 (sabit SoC pencereleri, 3 sıcaklık)
  Doğrulama:   Expt 4 (WLTP tabanlı sürüş çevrimi, kalibrasyonda kullanılmadı)

Kullanım:  pip install pandas scipy matplotlib openpyxl
           python aging_calibration.py
Girdi:     kirkaldy_ozet/ (indir_ozet.py çıktısı) ve experiment_metadata.xlsx
Çıktı:     aging_params.json, ../results/aging_*.png
"""
import os, glob, json
import numpy as np, pandas as pd
from scipy.optimize import least_squares
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import thesis_style as ts                       # ortak tez figür stili
ts.apply()
from rainflow import rainflow

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'kirkaldy_ozet')
FIG  = os.path.join(HERE, '..', 'results'); os.makedirs(FIG, exist_ok=True)
META = os.path.join(HERE, 'experiment_metadata.xlsx')
REF  = os.path.join(HERE, '..', 'simulink', 'twin_reference.csv')

# ------------------------------------------------------------------ veri
meta = pd.read_excel(META, sheet_name=None)
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
DOD  = {'1': 0.30, '2,2': 0.15,  '3': 0.15,  '5': 1.0, '4': 1.0}
LABEL = {'1': '0–30% SoC', '2,2': '70–85% SoC', '3': '85–100% SoC', '5': '0–100% SoC (CC)', '4': '0–100% SoC (drive cycle)'}
D['m'] = D.expt.map(SOCM); D['dod'] = D.expt.map(DOD)
# Her deneyin ortalama hücre gerilimi (takvim terimi için), Ageing Sets Summary'den
VMEAN = {}
for e, name in D.groupby('expt').cell.first().items():
    long = meta[[k for k in meta if str(meta[k]['Expt'].iloc[0]) == e][0]]['Expt long name'].iloc[0]
    fs = glob.glob(os.path.join(DATA, long, 'Summary Data', 'Ageing Sets Summary', 'Summary per Set', '*.csv'))
    VMEAN[e] = float(np.nanmean([pd.read_csv(f)['Av. Voltage [V]'].mean() for f in fs]))
D['V'] = D.expt.map(VMEAN)
def alpha_cal(V, T): return np.maximum(0, 7.543*V - 23.75)*1e6*np.exp(-6976/(T + 273.15))
D['cal'] = alpha_cal(D.V, D['T'])*D.days.fillna(0)**0.75
D = D[D.fade.notna() & D.efc.notna()]
FADE_MAX = 0.25        # diz (knee) sonrası ani düşüşler model kapsamı dışında
cal = D[(D.expt != '4') & (D.fade <= FADE_MAX)]

# ------------------------------------------------------------------ model
Tr = 25.0
T_DATA_MAX = 42.3                 # kalibrasyon verisindeki en yüksek ortalama hücre sıcaklığı
K_EXT = np.log(2)/10              # Millner (2010): 10 K'de iki kat
NAMES = ['a', 'z', 'Kex', 'Ksoc', 'Klow', 'kh', 'kc', 'kSi']
def S_fun(p, dod, m, T):
    a, z, Kex, Ksoc, Klow, kh, kc, kSi = p
    main = np.exp(Ksoc*(m-0.5)/0.25) * np.exp(kh*np.maximum(0, T-Tr)) * np.exp(kc*np.maximum(0, Tr-T)*m)
    si   = Klow*np.exp(-m/0.1) * np.exp(kSi*(T-Tr))
    ext  = np.exp(K_EXT*np.maximum(0, T-T_DATA_MAX))
    return np.exp((dod-1)/Kex) * (main+si) / (1+Klow*np.exp(-5)) * ext
def fade_fun(p, S, efc): return p[0]*(S*efc)**p[1]
def res(p, d): return fade_fun(p, S_fun(p, d.dod.values, d.m.values, d['T'].values), d.efc.values) + d.cal.values - d.fade.values

best = None
for a0 in [0.002, 0.004, 0.008]:
    for Ks0 in [0.5, 1.5]:
        r = least_squares(res, [a0, 0.57, 0.3, Ks0, 20, 0.01, 0.05, 0.05], args=(cal,),
                          bounds=([1e-6, 0.3, 0.02, -5, 0, 0, 0, 0], [1, 1.2, 5, 10, 1000, 0.2, 0.5, 0.3]),
                          x_scale='jac')
        if best is None or r.cost < best.cost: best = r
p = best.x
P = dict(zip(NAMES, p.tolist())); P['Tr'] = Tr; P['fade_max_fit'] = FADE_MAX
P['T_data_max'] = T_DATA_MAX; P['k_ext'] = K_EXT
P['cal_c1'] = 7.543; P['cal_c0'] = -23.75; P['cal_scale'] = 1e6; P['cal_Ea_over_R'] = 6976.0; P['cal_exp'] = 0.75
P['V_mean_expt'] = VMEAN
P['rmse_cal_pct'] = 100*np.sqrt(np.mean(best.fun**2))

# ------------------------------------------------------------------ doğrulama (Expt 4)
ref = pd.read_csv(REF); i_cell = ref.i_pack.values/12; dt = 0.1; Q = 4.85
soc = [1.0]; s = 1.0
while s > 0.02:
    for i in i_cell:
        s -= i*dt/3600/Q; soc.append(s)
        if s <= 0.02: break
soc = np.r_[soc, np.linspace(s, 1.0, int((1-s)/0.3*3600/dt))][::10]
cyc = np.array(rainflow(soc)); rng, mean, cnt = cyc[:, 0], cyc[:, 1], cyc[:, 2]; w = cnt*rng
val = D[D.expt == '4'].copy(); vrows = []
for T, g in val.groupby('Tset'):
    Tm = g['T'].mean()
    S_eff = np.sum(w*S_fun(p, rng, mean, Tm))/w.sum(); S_cc = S_fun(p, 1.0, 0.5, Tm)
    val.loc[g.index, 'pred'] = fade_fun(p, S_eff, g.efc) + g.cal; val.loc[g.index, 'pred_cc'] = fade_fun(p, S_cc, g.efc) + g.cal
for T, g in val.groupby('Tset'):
    ok = g.fade <= FADE_MAX
    vrows.append(dict(T_set=int(T), T_cell=round(g['T'].mean(), 1),
                      rmse_rainflow_pct=round(100*np.sqrt(np.mean((g.pred-g.fade)[ok]**2)), 2),
                      rmse_as_single_cycle_pct=round(100*np.sqrt(np.mean((g.pred_cc-g.fade)[ok]**2)), 2)))
P['validation_expt4'] = vrows
json.dump(P, open(os.path.join(HERE, 'aging_params.json'), 'w'), indent=1)

print('Fitted parameters:'); [print(f'  {k:5s} = {P[k]:.4g}') for k in NAMES]
print(f"Calibration RMSE (expts 1, 2, 3, 5): {P['rmse_cal_pct']:.2f} %")
for e, g in cal.groupby('expt'): print(f'  {LABEL[e]:22s}: {100*np.sqrt(np.mean(res(p, g)**2)):.2f} %')
print('Validation on held-out drive-cycle experiment (expt 4):'); print(pd.DataFrame(vrows).to_string(index=False))

# ------------------------------------------------------------------ şekiller (İngilizce)
col = {10: ts.BLUE, 25: ts.ORANGE, 40: ts.RED}
fig, ax = plt.subplots(1, 4, figsize=(15, 3.8), sharey=True)
for k, e in enumerate(['1', '2,2', '3', '5']):
    g = D[D.expt == e]
    for (c, T), h in g.groupby(['cell', 'Tset']):
        ax[k].plot(h.efc, 100*h.fade, 'o', c=col[T], ms=3, alpha=0.6)
    for T, h in g.groupby('Tset'):
        x = np.linspace(0, h.efc.max(), 100)
        days = np.interp(x, h.sort_values('efc').efc, h.sort_values('efc').days.fillna(0))
        ax[k].plot(x, 100*(fade_fun(p, S_fun(p, DOD[e], SOCM[e], h['T'].mean()), x)
                           + alpha_cal(VMEAN[e], h['T'].mean())*days**0.75), '-', c=col[T], lw=2,
                   label=f'{T} °C set ({h["T"].mean():.0f} °C cell)')
    ax[k].set_title(LABEL[e]); ax[k].set_xlabel('Equivalent full cycles'); ax[k].grid(alpha=0.3); ax[k].set_ylim(0, 35)
ax[0].set_ylabel('Capacity fade [%]'); ax[0].legend(fontsize=8)
fig.suptitle(f"Aging model (cycle + calendar) calibrated on LG M50T data (Kirkaldy et al., 2024): markers = data, lines = model, RMSE {P['rmse_cal_pct']:.2f}%")
fig.tight_layout(); fig.savefig(os.path.join(FIG, 'aging_calibration.png'), dpi=200)

fig, ax = plt.subplots(figsize=(6.5, 4.2))
for (c, T), h in val.groupby(['cell', 'Tset']):
    ax.plot(h.efc, 100*h.fade, 'o', c=col[T], ms=3, alpha=0.6)
for T, h in val.groupby('Tset'):
    Tm = h['T'].mean(); x = np.linspace(0, h.efc.max(), 100)
    S_eff = np.sum(w*S_fun(p, rng, mean, Tm))/w.sum()
    hs = h.sort_values('efc'); days = np.interp(x, hs.efc, hs.days.fillna(0)); cl = alpha_cal(VMEAN['4'], Tm)*days**0.75
    ax.plot(x, 100*(fade_fun(p, S_eff, x) + cl), '-', c=col[T], lw=2, label=f'{T} °C: model with rainflow')
    ax.plot(x, 100*(fade_fun(p, S_fun(p, 1.0, 0.5, Tm), x) + cl), ':', c=col[T], lw=1.5)
ax.set_xlabel('Equivalent full cycles'); ax.set_ylabel('Capacity fade [%]'); ax.set_ylim(0, 35); ax.grid(alpha=0.3)
ax.set_title('Validation on held-out drive-cycle data\n(solid: rainflow-based prediction, dotted: treated as one full cycle)', fontsize=10)
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(os.path.join(FIG, 'aging_validation.png'), dpi=200)

fig, ax = plt.subplots(1, 2, figsize=(11, 4))
mm = np.linspace(0.05, 0.95, 200)
for dod, ls in [(1.0, '-'), (0.5, '--'), (0.15, ':')]:
    ax[0].semilogy(mm, S_fun(p, dod, mm, 28.0), ls, c='k', label=f'DoD = {dod:.2f}')
ax[0].set_xlabel('Mean SOC of cycle'); ax[0].set_ylabel('Stress factor S (per EFC)'); ax[0].grid(alpha=0.3, which='both')
ax[0].set_title('Stress vs mean SOC at 28 °C'); ax[0].legend()
TT = np.linspace(10, 50, 200)
ax[1].axvspan(T_DATA_MAX, 50, color=ts.LIGHT, lw=0, zorder=0)
ax[1].text(T_DATA_MAX+0.5, 0.25, 'extrapolation\n(Millner rule)', fontsize=8, va='bottom')
for m_, c_ in [(0.15, ts.VIOLET), (0.5, ts.BLUE), (0.775, ts.AQUA), (0.925, ts.RED)]:
    ax[1].plot(TT, S_fun(p, 1.0 if m_ == 0.5 else (0.3 if m_ == 0.15 else 0.15), m_, TT), c=c_,
               label=f'mean SOC {m_:.2f}')
ax[1].set_xlabel('Cell temperature [°C]'); ax[1].set_ylabel('Stress factor S'); ax[1].grid(alpha=0.3)
ax[1].set_title('Stress vs temperature (tested windows)'); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(os.path.join(FIG, 'aging_stress_map.png'), dpi=200)
print('Figures saved to', os.path.abspath(FIG))
