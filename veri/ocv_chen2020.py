"""
LG M50 açık devre gerilimi (OCV) - SOC eğrisi, Chen vd. (2020) elektrot OCP uyumlarından.
Chen, Brosa Planella, O'Regan, Gastol, Widanage, Kendrick,
"Development of Experimental Techniques for Parameterization of Multi-scale Lithium-ion
Battery Models", J. Electrochem. Soc. 167 (2020) 080534.
OCP fonksiyonları ve stokiyometri sınırları PyBaMM 'Chen2020' parametre setindeki ile aynıdır.
OCV(SOC) = U_pos(y) - U_neg(x),  x = x0 + SOC (x100 - x0),  y = y0 + SOC (y100 - y0)
"""
import numpy as np
def U_neg(x):   # grafit-SiOx, LG M50
    return (1.9793*np.exp(-39.3631*x) + 0.2482 - 0.0909*np.tanh(29.8538*(x-0.1234))
            - 0.04478*np.tanh(14.9159*(x-0.2769)) - 0.0205*np.tanh(30.4444*(x-0.6103)))
def U_pos(y):   # NMC811, LG M50
    return (-0.8090*y + 4.4875 - 0.0428*np.tanh(18.5138*(y-0.5542))
            - 17.7326*np.tanh(15.7890*(y-0.3117)) + 17.5842*np.tanh(15.9308*(y-0.3120)))
x100, y100 = 29866/33133, 17038/63104          # %100 SOC (PyBaMM Chen2020 başlangıç konsantrasyonları)
def ocv_full(x0, y0, s): return U_pos(y0+s*(y100-y0)) - U_neg(x0+s*(x100-x0))
# %0 SOC stokiyometrileri: OCV = 2.5 V ve lityum dengesi (x100-x0)*Cn = (y0-y100)*Cp ile çöz
# %0 SOC stokiyometrileri: Chen 2020 makale değerleri (OCV(0) = 2.4977 V ile tutarlı)
x0, y0 = 0.0279, 0.9084
if __name__ == '__main__':
    print(f'x: {x0:.4f} -> {x100:.4f}   y: {y0:.4f} -> {y100:.4f}')
    print(f'OCV(0%) = {ocv_full(x0,y0,0):.4f} V, OCV(100%) = {ocv_full(x0,y0,1):.4f} V')
    soc_tab = np.r_[0, 0.02, np.arange(0.05, 0.951, 0.05), 0.98, 1.0].round(2)
    print('soc_tab =', soc_tab.tolist())
    print('ocv_tab =', np.round(ocv_full(x0,y0,soc_tab),4).tolist())
