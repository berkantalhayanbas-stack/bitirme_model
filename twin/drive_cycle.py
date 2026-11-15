"""
Hafif elektrikli araç (L7e / hafif şehir aracı sınıfı) için sentetik
sürüş çevrimi ve hız -> paket akımı dönüşümü.

4.2 kWh'lik paket binek otomobil için çok küçük olduğundan, araç modeli
~600 kg'lık hafif bir araç olarak seçildi. Gerçek WLTC Class-3 hız
profili (UNECE GTR-15) CSV olarak elde edildiğinde load_speed_csv() ile
doğrudan bu modele beslenebilir.
"""
import numpy as np


def synthetic_cycle(dt=0.1, repeats=3, seed=1):
    """Şehir içi + banliyö + kısa hızlı yol segmentlerinden oluşan profil [m/s]."""
    rng = np.random.default_rng(seed)
    # (hedef hız km/h, hızlanma süresi s, sabit süre s, yavaşlama s, bekleme s)
    base = [
        (30, 10, 20, 7, 10), (50, 14, 40, 9, 15), (40, 11, 25, 7, 8),
        (70, 22, 60, 12, 12), (50, 13, 30, 8, 10), (90, 32, 80, 16, 20),
        (35, 9, 15, 6, 12), (60, 18, 45, 10, 15),
    ]
    v = [0.0] * int(10 / dt)
    for _ in range(repeats):
        for vt, ta, tc, td, tw in base:
            vt = vt * (1 + 0.1 * rng.standard_normal()) / 3.6
            v += list(np.linspace(0, vt, int(ta / dt)))
            cruise = vt + 0.4 * np.sin(np.arange(int(tc / dt)) * dt * 0.5)
            v += list(cruise)
            v += list(np.linspace(vt, 0, int(td / dt)))
            v += [0.0] * int(tw / dt)
    v = np.clip(np.array(v), 0, None)
    t = np.arange(len(v)) * dt
    return t, v


def speed_to_current(v, dt, v_pack_nom=69.0, i_max=87.3, i_regen_max=-30.0,
                     mass=450.0, crr=0.011, cda=0.45, rho=1.2,
                     eta_drive=0.88, eta_regen=0.60, p_aux=250.0):
    """Boyuna araç dinamiği -> elektriksel güç -> paket akımı [A]."""
    a = np.gradient(v, dt)
    f = mass * a + mass * 9.81 * crr * (v > 0.1) + 0.5 * rho * cda * v ** 2
    p_wheel = f * v
    p_elec = np.where(p_wheel >= 0, p_wheel / eta_drive, p_wheel * eta_regen)
    p_elec = p_elec + p_aux
    i = p_elec / v_pack_nom
    return np.clip(i, i_regen_max, i_max)


def load_speed_csv(path, dt=0.1):
    """2 sütunlu (t[s], v[km/h]) CSV'yi dt örnekleme ile m/s'ye çevirir."""
    d = np.loadtxt(path, delimiter=",", skiprows=1)
    t = np.arange(0, d[-1, 0], dt)
    return t, np.interp(t, d[:, 0], d[:, 1]) / 3.6
