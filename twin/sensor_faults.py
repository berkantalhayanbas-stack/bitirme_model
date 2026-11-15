"""
Sensör arıza kütüphanesi + teşhis (diagnostics).

Arıza modları (t >= t_f anından itibaren):
  0  none
  1  v_spike   : paket gerilim ölçümünde EMI sıçramaları (+8 V, her ~30 s'de bir örnek)
  2  i_frozen  : akım sensörü son değerinde takılı kalır
  3  t_open    : NTC kopuk -> ADC skala sonu, -40.0 °C okunur
  4  t_frozen  : sıcaklık sensörü son değerinde takılı kalır
  5  i_offset  : akım sensöründe +3 A ani ofset kayması

Teşhis (her örnekte, kuantalanmış CAN değerleri üzerinde):
  - aralık kontrolü  : T < -30 °C veya T > 85 °C       -> T geçersiz
  - değişim hızı     : |ΔT| > 2 °C / örnek (0.1 s)      -> T geçersiz
  - donma kontrolü   : 50 örnek (5 s) aynı değer        -> geçersiz
  Arıza bayrağı kalıcıdır (latched): geçersiz bir sensör bu sürüşte tekrar güvenilir sayılmaz.
  V sıçramaları EKF içinde normalize inovasyon kapısıyla (|ν| > 10 σ; 5 örnek üst üste red olursa kapı açılır) reddedilir.
"""
import numpy as np

FAULTS = {0: "none", 1: "v_spike", 2: "i_frozen", 3: "t_open", 4: "t_frozen", 5: "i_offset"}


def inject(v, i, t, mode, t_f, dt=0.1, spike=8.0, spike_period=30.0, i_off=3.0):
    """Gürültülü (henüz kuantalanmamış) ölçümlere arıza ekler."""
    v, i, t = v.copy(), i.copy(), t.copy()
    k0 = int(round(t_f / dt))
    if mode == 1:
        ks = np.arange(k0, len(v), int(round(spike_period / dt)))
        v[ks] += spike
    elif mode == 2:
        i[k0:] = i[k0]
    elif mode == 3:
        t[k0:] = -40.0
    elif mode == 4:
        t[k0:] = t[k0]
    elif mode == 5:
        i[k0:] += i_off
    return v, i, t


class SensorDiag:
    T_MIN, T_MAX, T_RATE, N_FROZEN = -30.0, 85.0, 2.0, 50

    def __init__(self):
        self.t_prev = None
        self.i_prev = None
        self.n_t = 0
        self.n_i = 0
        self.t_valid = True
        self.i_valid = True

    def step(self, i_q, t_q):
        if self.t_prev is not None:
            self.n_t = self.n_t + 1 if t_q == self.t_prev else 0
            self.n_i = self.n_i + 1 if i_q == self.i_prev else 0
            if abs(t_q - self.t_prev) > self.T_RATE:
                self.t_valid = False
        if t_q < self.T_MIN or t_q > self.T_MAX or self.n_t >= self.N_FROZEN:
            self.t_valid = False
        if self.n_i >= self.N_FROZEN:
            self.i_valid = False
        self.t_prev, self.i_prev = t_q, i_q
        return self.t_valid, self.i_valid
