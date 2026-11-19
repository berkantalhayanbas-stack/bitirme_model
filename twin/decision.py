"""
Güvenli karar mekanizması (Hedef 4): 4 durumlu makine + izin verilen akım (I_allow).

Durumlar:  1 NORMAL     tam performans (veri sayfası sınırları)
           2 DERATE     sıcaklık, soğutma alarmı, gerilim payı veya soğuk hücre nedeniyle kısılmış
           3 LIMP-HOME  sensör arızası / aşırı sıcaklık / boş batarya: taban akım (%25), lamba asla sönmez
           4 SAFE-STOP  sert sınır aşıldı: I_allow = 0, kilitlenir, sadece reset ile çıkılır

İzin verilen akım (deşarj ve şarj ayrı, her ikisi de pozitif büyüklük):
  I_allow = rate_limit( min( I_datasheet(T) · (1 - Ψ),  I_SOP ) )   [LIMP-HOME'da ayrıca ≤ taban]
    I_datasheet(T): LG M50T veri sayfasının sıcaklığa bağlı sürekli akım sınırları × Np
    Ψ (stres indeksi, 0..1) = max(Ψ_sıcaklık, Ψ_soğutma)       çok kriterli, en kötü kriter belirler
    I_SOP: gerilim payına dayalı güç sınırı (state of power). Hücre gerilimi sınıra yaklaştıkça
           akım kısılır:  I_SOP = |I_şimdi| + k · Np · (V_ölçülen - V_sınır) / R0(T)
           Gerilime eşik koymak yerine akımı sınırlamak, yük altı gerilim çukurlarında alarm
           titreşimini ortadan kaldırır (bulgu 16) ve şarjda kendiliğinden CC-CV davranışı verir.
           Bu hızlı sınır akımı keser ama DURUMU belirlemez (her ivmelenmede devreye girip çıkar).
Durum için yavaş kapasite tahmini (quasi-static SOP), akımdan bağımsız:
    OCV_uç ≈ V_min + i_hücre·R0(T)        (IR düşümü geri eklenir)
    SOP_qs = Np · (OCV_uç - V_sınır) / R_dc,   R_dc = R0(T) + R1 + R2   (sürekli akım için)
  SOP_qs < 0.90 · veri sayfası sınırı -> neden aktif; ≥ 1.00 olunca kalkar (histerezis bandı).
  Veri sayfasının sıcaklık sınırı da aynı bantla: < 0.90 · nominal -> neden.
Sert sınırlar (SAFE-STOP): T_core > 60 °C, V_min < 2.5 V (1 s), V_max > 4.25 V (1 s).
Ölçüme bağlı çekirdek sınırı: T_ss = T_ölç + Rc/Ru (T_ölç - T_ortam) > 55 / 60 °C (1 s) de
LIMP-HOME / SAFE-STOP verir (gözlemcinin göremediği, modellenmemiş ısıya karşı).
Histerezis: kısıtlayıcı yöne anında geçilir (güvenlik), gevşetici yöne ancak neden 10 s
boyunca ortadan kalkınca; sıcaklık terimi 45 °C'de başlar, 43 °C altında sıfırlanır;
soğutma alarmı R_u > 18 K/W'ta açılır, 15 K/W altında kalkar; açılıştan sonraki ilk 120 s alarm
yok (gözlemci yakınsaması).
Sensör arızası bayrakları kalıcıdır (sensor_diag), bu yüzden LIMP-HOME o sürüşte sürer.

Python referansı; Simulink karşılığı: simulink/decision_logic.m (birebir aynı mantık).
"""
import numpy as np

NORMAL, DERATE, LIMP, SAFE = 1, 2, 3, 4
NAMES = {1: "NORMAL", 2: "DERATE", 3: "LIMP-HOME", 4: "SAFE-STOP"}

# neden bitleri (fault/cause code)
C_THERM, C_COOL, C_SOP_DIS, C_SOP_CHG, C_DS_T, C_SENSOR, C_EMPTY, C_HARD = 1, 2, 4, 8, 16, 32, 64, 128
# C_DS_T: veri sayfasının sıcaklığa bağlı akım sınırı nominalin altında (soğuk veya çok sıcak hücre)


class DecisionParams:
    ns, np_, ts = 19, 12, 0.1
    r0, ea, rgas = 0.0264, 6200.0, 8.314     # Ea: R0 ohmik kısım (Kirkaldy 2024)
    # veri sayfası (hücre başı, A) — sürekli akım, LG INR21700 M50T
    # Bölge sınırlarında basamak yerine 2 °C'lik doğrusal geçiş (durum titreşmesin); geçiş
    # her zaman kısıtlı tarafta: sınır sıcaklığın kendisi (ör. 25 °C şarj) üst bölgeye dahil.
    T_dis = (-20, -18, 8, 10, 53, 55);  I_dis = (0, 2.425, 2.425, 7.275, 7.275, 0)   # 0.5C / 1.5C
    T_chg = (0, 2, 23, 25, 43, 45);     I_chg = (0, 1.455, 1.455, 3.395, 3.395, 0)   # 0.3C / 0.7C
    # stres indeksi
    T_der_on, T_der_off, T_der_full = 45.0, 43.0, 55.0
    psi_cool = 0.3
    ru_alarm = 18.0
    ru_alarm_off = 15.0     # histerezis: R_u kestirimi eşik çevresinde yakınsarken alarm titriyordu (HIL)
    t_cool_blank = 120.0    # açılıştan sonra soğutma alarmı yok: gözlemci sıcak/yüklü pakette başlarsa
                            # R_u kestirimi geçici olarak > 30 K/W (HIL'de bulundu, U13)
    # gerilim payı (SOP)
    v_lim_dis, v_lim_chg, k_sop = 2.90, 4.18, 0.3
    r1, r2 = 0.0093, 0.012         # R1, R2 [Ohm/hücre] (sürekli akımda kutuplaşma), 25 °C
    ea_r1, ea_r2 = 17500.0, 14300.0   # RC dallarının Ea'sı (Kirkaldy 2024)
    band_on, band_off = 0.90, 1.00   # neden < %90'da başlar, ancak %100'e dönünce kalkar
    # LIMP-HOME ve sert sınırlar
    floor_frac = 0.25
    T_limp, T_safe = 55.0, 60.0
    # ölçüme bağlı çekirdek sınırı (A1, HIL 3. bulgu): kararlı halde Tc - Ts = Rc/Ru (Ts - Ta);
    # ısının kaynağından bağımsız. Gözlemci modellenmemiş ısıyı (dış kaynak, iç kısa devre
    # başlangıcı) göremediği için LIMP/SAFE ayrıca T_ss = Tm + k_ss (Tm - Ta) ile verilir (1 s süre
    # filtresi, gürültü). Nominal Ru: soğutma arızasında (Ru büyür) sınır tutucu kalır.
    k_ss = 1.8 / 9.0                      # Rc / Ru_nom
    soc_empty = 0.03
    v_safe_lo, v_safe_hi, t_hard = 2.50, 4.25, 1.0
    bias_max = 5.0
    # zamanlama ve rampalar
    t_exit_derate, t_exit_limp = 10.0, 10.0
    ramp_up = 10.0                        # A/s; düşüşler anında (güvenlik), artışlar rampalı (sürüş konforu)


def ds_limit(T, Tb, Ib):
    """Veri sayfası akım sınırı [A/hücre]: parçalı doğrusal tablo (bölge dışında 0)."""
    return float(np.interp(T, Tb, Ib, left=0.0, right=0.0))


class Decision:
    def __init__(self, p=None):
        self.p = p or DecisionParams()
        self.state = NORMAL
        # sayaçlar örnek cinsinden (tamsayı): 10 x 0.1 kayan noktada tam 1.0 etmez
        self.n_ok = 0              # gevşetme yönündeki bekleme sayacı
        self.n_lo = 0
        self.n_hi = 0
        self.therm_on = False
        self.cool_on = False
        self.n_run = 0             # açılıştan beri örnek
        self.n_hl = self.n_hs = 0  # ölçüme bağlı çekirdek sınırı: LIMP / SAFE süre sayaçları
        self.f_ds = self.f_sop_dis = self.f_sop_chg = False
        p = self.p
        self.I_nom_dis = max(p.I_dis) * p.np_          # 87.3 A
        self.I_nom_chg = max(p.I_chg) * p.np_          # 40.7 A
        self.i_dis = 0.0               # açılış: sıfırdan rampayla (öz-denetim sonrası, ~9 s)
        self.i_chg = 0.0

    def _band(self, flag, ratio):
        """Histerezis bandı: oran band_on altına inince bayrak kalkar, band_off üstüne çıkınca iner."""
        if ratio < self.p.band_on:
            return True
        if ratio > self.p.band_off:
            return False
        return flag

    def step(self, I_meas, V_min, V_max, Tc_hat, Ts_hat, Ru_hat, SOC_est, bias_est,
             T_valid=1, I_valid=1, CAN_ok=1, T_meas=None, T_amb=None):
        p = self.p
        cause = 0
        # ---------------------------------------------------- sert sınırlar (kilitlenir)
        n_hard = round(p.t_hard / p.ts)
        self.n_lo = self.n_lo + 1 if V_min < p.v_safe_lo else 0
        self.n_hi = self.n_hi + 1 if V_max > p.v_safe_hi else 0
        if T_meas is not None and T_valid >= 0.5:
            t_ss = T_meas + p.k_ss * (T_meas - T_amb)
            self.n_hl = self.n_hl + 1 if t_ss > p.T_limp else 0
            self.n_hs = self.n_hs + 1 if t_ss > p.T_safe else 0
        else:
            self.n_hl = self.n_hs = 0
        hard = (Tc_hat > p.T_safe or self.n_hs >= n_hard or self.n_lo >= n_hard or self.n_hi >= n_hard
                or CAN_ok < 0.5)
        if hard or self.state == SAFE:
            self.state = SAFE
            self.i_dis = self.i_chg = 0.0
            return self.state, 0.0, 0.0, 1.0, C_HARD

        # ---------------------------------------------------- veri sayfası sınırları
        i_ds_dis = ds_limit(Ts_hat, p.T_dis, p.I_dis) * p.np_
        i_ds_chg = ds_limit(Ts_hat, p.T_chg, p.I_chg) * p.np_
        r_ds = min(i_ds_dis / self.I_nom_dis, i_ds_chg / self.I_nom_chg)
        self.f_ds = self._band(self.f_ds, r_ds)
        if self.f_ds:
            cause |= C_DS_T

        # ---------------------------------------------------- stres indeksi
        if Tc_hat >= p.T_der_on:
            self.therm_on = True
        elif Tc_hat < p.T_der_off:
            self.therm_on = False
        psi_T = np.clip((Tc_hat - p.T_der_off) / (p.T_der_full - p.T_der_off), 0, 1) if self.therm_on else 0.0
        n_blank = round(p.t_cool_blank / p.ts)
        if self.n_run < n_blank:
            self.n_run += 1
        if self.n_run < n_blank:
            self.cool_on = False
        elif Ru_hat > p.ru_alarm:
            self.cool_on = True
        elif Ru_hat < p.ru_alarm_off:
            self.cool_on = False
        psi_C = p.psi_cool if self.cool_on else 0.0
        if psi_T > 0: cause |= C_THERM
        if psi_C > 0: cause |= C_COOL
        psi = max(psi_T, psi_C)

        # ---------------------------------------------------- gerilim payı (SOP)
        r0 = p.r0 * np.exp(p.ea / p.rgas * (1 / (Tc_hat + 273.15) - 1 / 298.15))
        i_dis_now, i_chg_now = max(I_meas, 0.0), max(-I_meas, 0.0)
        sop_dis = i_dis_now + p.k_sop * p.np_ * (V_min - p.v_lim_dis) / r0
        sop_chg = i_chg_now + p.k_sop * p.np_ * (p.v_lim_chg - V_max) / r0
        # yavaş kapasite tahmini (durum için)
        r_dc = (r0 + p.r1 * np.exp(p.ea_r1 / p.rgas * (1 / (Tc_hat + 273.15) - 1 / 298.15))
                + p.r2 * np.exp(p.ea_r2 / p.rgas * (1 / (Tc_hat + 273.15) - 1 / 298.15)))
        ic = I_meas / p.np_
        qs_dis = p.np_ * (V_min + max(ic, 0.0) * r0 - p.v_lim_dis) / r_dc
        qs_chg = p.np_ * (p.v_lim_chg - (V_max - max(-ic, 0.0) * r0)) / r_dc
        self.f_sop_dis = self._band(self.f_sop_dis, qs_dis / max(i_ds_dis, 1e-6))
        self.f_sop_chg = self._band(self.f_sop_chg, qs_chg / max(i_ds_chg, 1e-6))
        if self.f_sop_dis: cause |= C_SOP_DIS
        if self.f_sop_chg: cause |= C_SOP_CHG

        tgt_dis = max(0.0, min(i_ds_dis * (1 - psi), sop_dis))
        tgt_chg = max(0.0, min(i_ds_chg * (1 - psi), sop_chg))

        # ---------------------------------------------------- LIMP-HOME nedenleri
        sensor_bad = T_valid < 0.5 or I_valid < 0.5 or abs(bias_est) > p.bias_max
        if sensor_bad: cause |= C_SENSOR
        if SOC_est < p.soc_empty: cause |= C_EMPTY
        hot_ss = self.n_hl >= n_hard
        if hot_ss: cause |= C_THERM
        limp = sensor_bad or Tc_hat > p.T_limp or hot_ss or SOC_est < p.soc_empty
        if limp:
            # taban akım: Ψ kısıtlamasının yerine geçer ama gerilim payını (SOP) ve
            # veri sayfası sınırını asla aşmaz (boş batarya tabandan önce gelir)
            tgt_dis = min(p.floor_frac * self.I_nom_dis, i_ds_dis, max(sop_dis, 0.0))
            tgt_chg = min(tgt_chg, p.floor_frac * self.I_nom_chg)

        # ---------------------------------------------------- durum + histerezis
        want = LIMP if limp else (DERATE if cause else NORMAL)
        if want > self.state:                    # kısıtlayıcı yön: anında
            self.state, self.n_ok = want, 0
        elif want < self.state:                  # gevşetici yön: bekle
            self.n_ok += 1
            need = p.t_exit_limp if self.state == LIMP else p.t_exit_derate
            if self.n_ok >= round(need / p.ts):
                self.state, self.n_ok = want, 0
        else:
            self.n_ok = 0

        # ---------------------------------------------------- rampa sınırlayıcı
        def ramp(cur, tgt):
            return tgt if tgt < cur else min(tgt, cur + p.ramp_up * p.ts)
        self.i_dis = ramp(self.i_dis, tgt_dis)
        self.i_chg = ramp(self.i_chg, tgt_chg)
        psi_out = 1 - self.i_dis / self.I_nom_dis
        return self.state, self.i_dis, self.i_chg, psi_out, cause
