"""
Sensör hata modeli + CAN 0x101 kuantalaması.

EKF'ye giden veri, gerçekte CAN üzerinden gelecek olan veriyle aynı
çözünürlükte olmalı: V_term 0.1 V, I 0.1 A, T_surf 0.1 °C.
"""
import numpy as np


def measure(true_v, true_i, true_ts, sigma_v=0.25, sigma_i=0.5,
            bias_i=0.5, sigma_t=0.3, seed=7):
    rng = np.random.default_rng(seed)
    n = len(true_v)
    v = true_v + sigma_v * rng.standard_normal(n)
    i = true_i + bias_i + sigma_i * rng.standard_normal(n)
    ts = true_ts + sigma_t * rng.standard_normal(n)
    # CAN DBC kuantalaması
    q = lambda x, lsb: np.round(x / lsb) * lsb
    return q(v, 0.1), q(i, 0.1), q(ts, 0.1)


def noisy(true_v, true_i, true_ts, sigma_v=0.25, sigma_i=0.5,
          bias_i=0.5, sigma_t=0.3, seed=7):
    """measure() ile aynı gürültü, kuantalama yok (arıza enjeksiyonu için)."""
    rng = np.random.default_rng(seed)
    n = len(true_v)
    v = true_v + sigma_v * rng.standard_normal(n)
    i = true_i + bias_i + sigma_i * rng.standard_normal(n)
    ts = true_ts + sigma_t * rng.standard_normal(n)
    return v, i, ts


def can_q(x, lsb=0.1):
    return np.round(x / lsb) * lsb
