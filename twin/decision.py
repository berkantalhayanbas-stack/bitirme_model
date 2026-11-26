"""
Güvenli karar mekanizması (Hedef 4): 4 durumlu makine + izin verilen akım (I_allow).

Durumlar:  1 NORMAL     tam performans (veri sayfası sınırları)
           2 DERATE     sıcaklık, soğutma alarmı, gerilim payı veya soğuk hücre nedeniyle kısılmış
           3 LIMP-HOME  sensör arızası / aşırı sıcaklık / boş batarya: taban akım (%25), lamba asla sönmez
           4 SAFE-STOP  sert sınır aşıldı: I_allow = 0, kilitlenir, sadece reset ile çıkılır

İzin verilen akım (deşarj ve şarj ayrı, her ikisi de pozitif büyüklük):
  I_allow = rate_limit( min( I_datasheet(T) · (1 - Ψ),  I_SOP ) )   [LIMP-HOME'da ayrıca ≤ taban]
    I_datasheet(T): LG M50T veri sayfasının sıcaklığa bağlı sürekli akım sınırları × Np
    Ψ (stres indeksi, 0..1): bataryaya etki eden bütün kötü koşulların toplam yükü, olasılıksal VEYA
      Ψ = 1 - Π (1 - Ψ_i)   (küçük değerlerde ≈ ΣΨ_i; tek bir Ψ_i = 1 -> Ψ = 1; ayar sabiti yok)
      Ψ_T    çekirdek sıcaklığı (Tc_hat)        45 °C'de başlar (43 -> 55 °C doğrusal), tavan 1.0
      Ψ_C    soğutma alarmı (R_u kestirimi)     alarm açık -> 0.3
      Ψ_Tdot yüzey sıcaklığı artış hızı         süzülmüş dT/dt, 3 -> 10 °C/dk, tavan 0.5
             (A2 bulgusu: gizli ısıda Tc_hat gerçeğin 11 °C gerisinde kaldı; hız erken uyarır)
      Ψ_A    yaşlanma hızı (hibrit model, stress_model.py): çevrim R_cyc = S(T, m, dod)/S_ref · |I|/0,5C,
             takvim R_cal = alpha(OCV(SOC), T)/alpha(OCV(0,5), 25 °C); Ψ = log2(R)/3 (1x -> 0, 8x -> 1),
             Ψ_A = VEYA(Ψ_cyc, Ψ_cal). Takvim terimi 2x'te başlar (2x -> 0, 16x -> 1) ve yalnız gösterge
             (akım kısmak takvim yaşlanmasını yavaşlatmaz). Çevrim terimi şarjı kısar, 0,3C tabanı var
             (sürüşü yaşlanma için kesme)
      Ψ_H    sağlık: kapasite SOH 90 -> 70 % ve EKF R0 ölçeği k_R 1.2 -> 1.3 (büyüğü), gösterge
      Ψ_B    grup dengesizliği: V_max - V_min (|I| < 2 A'da, 10 s süzgeç) 50 -> 150 mV, gösterge
      Deşarj Ψ_P = VEYA(Ψ_T, Ψ_C, Ψ_Tdot); şarj ayrıca (1 - Ψ_A) ile (tabanlı). Panelin "Battery stress"i
      altısının VEYA'sı; baskın kriter (self.dom) en büyük Ψ_i: 0 yok, 1 T, 2 C, 3 Tdot, 4 H, 5 A, 6 B.
      Yalnız Ψ_T 1'e ulaşabilir: durdurmak LIMP/SAFE'in işi. Tasarım: bms_ecu/docs/stress_design.md.
    I_SOP: gerilim payına dayalı güç sınırı (state of power). Hücre gerilimi sınıra yaklaştıkça
           akım kısılır:  I_SOP = |I_şimdi| + k · Np · (V_ölçülen - V_sınır) / R0(T)
                R0(T) = R0 · clip(k_R, 1, 2) · Arrhenius(T): EKF'nin bulduğu direnç artışı SOP'u da kısar.
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

from stress_model import STRESS_S_REF, stress_S, stress_cal_alpha

NORMAL, DERATE, LIMP, SAFE = 1, 2, 3, 4
NAMES = {1: "NORMAL", 2: "DERATE", 3: "LIMP-HOME", 4: "SAFE-STOP"}

# neden bitleri (fault/cause code)
C_THERM, C_COOL, C_SOP_DIS, C_SOP_CHG, C_DS_T, C_SENSOR, C_EMPTY, C_HARD = 1, 2, 4, 8, 16, 32, 64, 128
C_ANOM = 256    # termal anomali (thermal_anomaly.py); 0x201'de cause 8 bit: C_THERM de kurulur
C_TDOT = 512    # sıcaklık artış hızı (Ψ_Tdot > 0); 0x201'de C_THERM de kurulur
C_HEALTH = 1024 # direnç artışı (Ψ_H > 0); 0x201'de 8 bitlik karşılığı yok (yalnız UART telemetrisi)
C_TEVT = 2048   # termal olay: SAFE'te akım yokken yüzey ortamın üstünde ısınıyor (kilitli; 0x201'de karşılığı yok)
C_AGE = 4096    # yaşlanma hızı (Ψ_A > 0): yalnız şarjı kısar, durumu değiştirmez (bilgi; yalnız UART)
C_IMBAL = 8192  # grup dengesizliği (Ψ_B > 0): gösterge (bilgi; yalnız UART)
C_INFO = C_HEALTH | C_AGE | C_IMBAL   # DERATE'e yol açmayan neden bitleri
DOM_NONE, DOM_T, DOM_C, DOM_TDOT, DOM_H, DOM_A, DOM_B = 0, 1, 2, 3, 4, 5, 6
DOM_NAMES = {0: "none", 1: "core temperature", 2: "cooling", 3: "temperature rise rate", 4: "battery health",
             5: "ageing rate", 6: "cell imbalance"}
# OCV tablosu (Kirkaldy 2024 M50T GITT; bms_config.h SOH_OCV_*): Ψ_A'nın takvim terimi için
OCV_S = (0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8,
         0.85, 0.9, 0.95, 0.98, 1.0)
OCV_V = (2.9414, 3.0161, 3.1444, 3.2871, 3.4047, 3.4646, 3.5055, 3.5621, 3.6086, 3.6418, 3.6729, 3.7119,
         3.7594, 3.8136, 3.8737, 3.9207, 3.9641, 4.0162, 4.0619, 4.0873, 4.112, 4.1519, 4.1845)


def or_agg(xs):
    """Olasılıksal VEYA: 1 - Π(1 - x)."""
    r = 1.0
    for x in xs:
        r *= 1.0 - x
    return 1.0 - r


def clip01(x):
    return min(1.0, max(0.0, x))
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
    # Ψ_Tdot: ölçülen yüzey sıcaklığının süzülmüş artış hızı [°C/dk]. T_f = T_ölç'ün 5 s alçak
    # geçireni; hız = 60·ΔT_f/ts, 30 s alçak geçirenden geçer (MC taraması: nominal en çok 2,3 °C/dk,
    # dış ısı ~23 °C/dk)
    td_a_f, td_a_r = 0.02, 1.0 / 300.0   # ts/5 s, ts/30 s (Euler)
    tdot_on, tdot_full, psi_tdot = 3.0, 10.0, 0.5
    # Ψ_H: kapasite SOH'u (soh_*) ve EKF'nin R0 ölçeği k_R (nominal MC: 0,89-1,10); büyüğü
    kr_on, kr_full = 1.2, 1.3
    soh_on, soh_full = 0.90, 0.70
    kr_sop_max = 2.0                 # SOP direnci: R0 · clip(k_R, 1, kr_sop_max)
    # Ψ_A: yaşlanma hızı oranı R (1x -> 0, 8x -> 1, log2), şarj tabanı 0,3C (VARSAYIM; MC ile ayarlanır)
    age_log2_full = 3.0
    age_cal_onset = 2.0             # takvim oranı bunun üstünde sayılır (ılık / yarı dolu park normal)
    age_i_ref = 2.425               # 0,5C [A/hücre]: çevrim referansı (25 °C, m 0,5, dod 1)
    age_floor = 1.455               # 0,3C [A/hücre]: Ψ_A şarjı bunun altına kısmaz
    age_i_min = 2.0                 # [A] yön ölçümü ölü bandı (yarım çevrim kuralı)
    age_a = 0.1 / 60.0              # R_cyc süzgeci (tau 60 s)
    cell_q = 4.85                   # [Ah] birikimli hasar için
    # Ψ_B: grup dengesizliği (yalnız düşük akımda, IR düşümü karışmasın)
    bal_i_max, bal_a = 2.0, 0.01    # [A], süzgeç (tau 10 s)
    imb_on, imb_full = 0.050, 0.150
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
    # termal olay (SAFE'ten sonra, bms_config.h DEC_TE_*): kontaktör açık, |I| < te_i_max, yüzey > ortam ve
    # süzülmüş artış hızı > te_rate, te_n örnek. Isı dengelenmesi (τ ~ 8 s) yanlış alarm vermesin diye
    # anomali kilitli değilse akım te_wait boyunca ~0 kalmış olmalı.
    te_i_max, te_rate, te_wait, te_n = 2.0, 1.0, 900, 10
    bias_max = 8.0          # [A] EKF kayma kestiriminin makullük sınırı. 5 A idi: direnç uyumsuzluğunda
                            # (R1 x1,5, tau2 x0,5; A3) kestirim 5,9 A'ya çıkıp sahte LIMP veriyordu.
                            # Daha küçük gerçek kaymaları EKF telafi ediyor (6 A: SOC hatası <= %2,3)
    # zamanlama ve rampalar
    t_exit_derate, t_exit_limp = 10.0, 10.0
    ramp_up = 10.0                        # A/s; düşüşler anında (güvenlik), artışlar rampalı (sürüş konforu)
    # açılışta sıfır akım kontrolü (A9): kontaktör kapanmadan önce t_zero boyunca I_allow = 0, akım
    # kesin sıfırken ölçülen ortalama = sensör ofseti. |ofset| > zero_max -> sensör arızası (LIMP);
    # değilse EKF kayma durumu bununla başlar (ekf.py). EKF kaymayı sürüşte yavaş ve eksik buluyordu
    # (±8 A hiç, +10 A ~1040 s'de; A3). 3 A = 300 A'lık Hall sensörünün %1'i.
    t_zero = 1.0
    zero_max = 3.0


CAL_REF = stress_cal_alpha(float(np.interp(0.5, OCV_S, OCV_V)), 25.0)   # takvim referansı (25 °C, SOC 0,5)


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
        self.n_zero = 0                # sıfır akım kontrolü: geçerli örnek sayısı
        self.i0_sum = 0.0
        self.i0_ok = True
        self.zero_bad = False
        self.td_on = False             # Ψ_Tdot süzgeci başladı mı
        self.t_f = 0.0
        self.tdot = 0.0                # [°C/dk]
        self.n_i0 = self.n_te = 0      # termal olay: SAFE'te akımsız örnek, koşul süresi
        self.tevt = False              # termal olay (kilitlenir)
        self.psi_i = (0.0,) * 6        # Ψ_T, Ψ_C, Ψ_Tdot, Ψ_H, Ψ_A, Ψ_B (son adım)
        self.psi_s = 0.0               # Ψ: altısının VEYA'sı
        self.psi_p = 0.0               # koruma Ψ_P = VEYA(Ψ_T, Ψ_C, Ψ_Tdot): deşarjı kısar
        # Ψ_A: yarım çevrim izleyici + oranlar
        self.a_dir = 0                 # +1 deşarj, -1 şarj, 0 henüz yok
        self.a_soc_rev = 0.5           # son yön değişimindeki SOC
        self.a_sum = 0.0
        self.a_n = 0
        self.a_swing = 0.0             # tamamlanan son yarım çevrimin derinliği
        self.r_cyc = 0.0               # süzülmüş çevrim hızı oranı
        self.r_cal = 0.0               # takvim hızı oranı
        self.dmg = 0.0                 # birikimli hasar: referans stresli eşdeğer tam çevrim
        self.dv_f = None               # Ψ_B süzgeci [V]
        self.psi_cyc = 0.0             # Ψ_A'nın çevrim payı (şarjı kısan)
        self.dom = DOM_NONE            # baskın kriter

    def _band(self, flag, ratio):
        """Histerezis bandı: oran band_on altına inince bayrak kalkar, band_off üstüne çıkınca iner."""
        if ratio < self.p.band_on:
            return True
        if ratio > self.p.band_off:
            return False
        return flag

    def step(self, I_meas, V_min, V_max, Tc_hat, Ts_hat, Ru_hat, SOC_est, bias_est,
             T_valid=1, I_valid=1, CAN_ok=1, T_meas=None, T_amb=None, T_anom=0, k_R=1.0, soh_c=1.0):
        p = self.p
        cause = 0
        # ---------------------------------------------------- stres indeksi (SAFE'te de hesaplanır:
        # telemetri Ψ'yi her durumda gösterir; I_allow'a etkisi aşağıda)
        if Tc_hat >= p.T_der_on:
            self.therm_on = True
        elif Tc_hat < p.T_der_off:
            self.therm_on = False
        psi_T = float(np.clip((Tc_hat - p.T_der_off) / (p.T_der_full - p.T_der_off), 0, 1)) if self.therm_on else 0.0
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
        if T_meas is not None and T_valid >= 0.5:      # sensör geçersizse süzgeç sıfırdan başlar
            if self.td_on:
                t_prev = self.t_f
                self.t_f += p.td_a_f * (T_meas - self.t_f)
                self.tdot += p.td_a_r * (60.0 * (self.t_f - t_prev) / p.ts - self.tdot)
            else:
                self.td_on, self.t_f, self.tdot = True, T_meas, 0.0
        else:
            self.td_on, self.tdot = False, 0.0
        psi_D = p.psi_tdot * float(np.clip((self.tdot - p.tdot_on) / (p.tdot_full - p.tdot_on), 0, 1))
        blank = self.n_run < n_blank   # açılıştan sonra 120 s: EKF (SOC, k_R) yakınsamadan Ψ_H/Ψ_A/Ψ_B yok
        # Ψ_H: sağlık (gösterge)
        psi_H = 0.0 if blank else max(clip01((p.soh_on - soh_c) / (p.soh_on - p.soh_full)),
                                      clip01((k_R - p.kr_on) / (p.kr_full - p.kr_on)))
        # Ψ_A: yaşlanma hızı. Yarım çevrim: |I| > age_i_min iken yön değişince yeni yarım çevrim başlar;
        # m = yarım çevrimin ortalama SOC'si, dod = şimdiki salınım ile son tam yarım çevrimin büyüğü
        soc = clip01(SOC_est)
        i_abs = abs(I_meas)
        r_inst = 0.0
        if i_abs > p.age_i_min:
            d = 1 if I_meas > 0 else -1
            if d != self.a_dir:
                if self.a_dir != 0:
                    self.a_swing = abs(soc - self.a_soc_rev)
                self.a_dir, self.a_soc_rev, self.a_sum, self.a_n = d, soc, 0.0, 0
            self.a_sum += soc
            self.a_n += 1
            m = self.a_sum / self.a_n
            dod = clip01(max(abs(soc - self.a_soc_rev), self.a_swing))
            s_rel = stress_S(Tc_hat, m, dod) / STRESS_S_REF
            r_inst = s_rel * (i_abs / p.np_) / p.age_i_ref
            self.dmg += s_rel * i_abs * p.ts / (2.0 * p.np_ * p.cell_q * 3600.0)
        self.r_cyc += p.age_a * (r_inst - self.r_cyc)
        v_ocv = float(np.interp(soc, OCV_S, OCV_V))
        self.r_cal = stress_cal_alpha(v_ocv, Tc_hat) / CAL_REF
        psi_cyc = clip01(np.log2(max(self.r_cyc, 1e-9)) / p.age_log2_full)
        psi_cal = clip01(np.log2(max(self.r_cal / p.age_cal_onset, 1e-9)) / p.age_log2_full)
        psi_cyc = 0.0 if blank else psi_cyc
        psi_A = 0.0 if blank else or_agg((psi_cyc, psi_cal))
        self.psi_cyc = psi_cyc
        # Ψ_B: grup dengesizliği (gösterge), yalnız düşük akımda güncellenir
        dv = V_max - V_min
        if i_abs < p.bal_i_max:
            self.dv_f = dv if self.dv_f is None else self.dv_f + p.bal_a * (dv - self.dv_f)
        psi_B = 0.0 if (blank or self.dv_f is None) else clip01((self.dv_f - p.imb_on) / (p.imb_full - p.imb_on))
        self.psi_i = (psi_T, psi_C, psi_D, psi_H, psi_A, psi_B)
        self.psi_p = or_agg(self.psi_i[:3])
        self.psi_s = or_agg(self.psi_i)
        pm = max(self.psi_i)
        self.dom = 1 + self.psi_i.index(pm) if pm > 0 else DOM_NONE
        psi = self.psi_p
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
            self.n_i0 = min(self.n_i0 + 1, p.te_wait) if abs(I_meas) < p.te_i_max else 0
            rising = (CAN_ok >= 0.5 and T_valid >= 0.5 and T_meas is not None and T_meas > T_amb
                      and self.tdot > p.te_rate)
            self.n_te = self.n_te + 1 if rising and self.n_i0 > 0 and (T_anom or self.n_i0 >= p.te_wait) else 0
            if self.n_te >= p.te_n:
                self.tevt = True
            return self.state, 0.0, 0.0, 1.0, C_HARD | (C_TEVT if self.tevt else 0)
        n_zero = round(p.t_zero / p.ts)
        zeroing = self.n_zero < n_zero             # kontaktör açık: akım kesin 0
        if zeroing:                                # geçersiz örnek varsa sonuç yok (I_valid zaten LIMP)
            self.i0_sum += I_meas
            self.i0_ok = self.i0_ok and I_valid >= 0.5
            self.n_zero += 1
            if self.n_zero == n_zero:
                self.zero_bad = self.i0_ok and abs(self.i0_sum / n_zero) > p.zero_max

        # ---------------------------------------------------- veri sayfası sınırları
        i_ds_dis = ds_limit(Ts_hat, p.T_dis, p.I_dis) * p.np_
        i_ds_chg = ds_limit(Ts_hat, p.T_chg, p.I_chg) * p.np_
        r_ds = min(i_ds_dis / self.I_nom_dis, i_ds_chg / self.I_nom_chg)
        self.f_ds = self._band(self.f_ds, r_ds)
        if self.f_ds:
            cause |= C_DS_T

        # ---------------------------------------------------- stres indeksinin neden bitleri
        if psi_T > 0: cause |= C_THERM
        if psi_C > 0: cause |= C_COOL
        if psi_D > 0: cause |= C_TDOT | C_THERM
        if psi_H > 0: cause |= C_HEALTH
        if psi_A > 0: cause |= C_AGE
        if psi_B > 0: cause |= C_IMBAL

        # ---------------------------------------------------- gerilim payı (SOP)
        r0 = p.r0 * min(max(k_R, 1.0), p.kr_sop_max) * np.exp(p.ea / p.rgas * (1 / (Tc_hat + 273.15) - 1 / 298.15))
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
        # şarj: koruma (1 - Ψ_P) ve çevrim yaşlanması (1 - Ψ_cyc); bu pay 0,3C tabanının altına inmez
        f_age = min(1.0, max(1.0 - psi_cyc, p.age_floor * p.np_ / max(i_ds_chg, 1e-6)))
        tgt_chg = max(0.0, min(i_ds_chg * (1 - psi) * f_age, sop_chg))

        # ---------------------------------------------------- LIMP-HOME nedenleri
        sensor_bad = T_valid < 0.5 or I_valid < 0.5 or abs(bias_est) > p.bias_max or self.zero_bad
        if sensor_bad: cause |= C_SENSOR
        if SOC_est < p.soc_empty: cause |= C_EMPTY
        hot_ss = self.n_hl >= n_hard
        if hot_ss: cause |= C_THERM
        if T_anom: cause |= C_ANOM | C_THERM
        limp = sensor_bad or Tc_hat > p.T_limp or hot_ss or SOC_est < p.soc_empty or bool(T_anom)
        if limp:
            # taban akım: Ψ kısıtlamasının yerine geçer ama gerilim payını (SOP) ve
            # veri sayfası sınırını asla aşmaz (boş batarya tabandan önce gelir)
            tgt_dis = min(p.floor_frac * self.I_nom_dis, i_ds_dis, max(sop_dis, 0.0))
            tgt_chg = min(tgt_chg, p.floor_frac * self.I_nom_chg)

        # ---------------------------------------------------- durum + histerezis
        want = LIMP if limp else (DERATE if (cause & ~C_INFO) else NORMAL)   # 1024/4096/8192 bilgi
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
        if zeroing:
            self.i_dis = self.i_chg = 0.0
        psi_out = 1 - self.i_dis / self.I_nom_dis
        return self.state, self.i_dis, self.i_chg, psi_out, cause
