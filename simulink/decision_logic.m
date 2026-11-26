function [state, I_allow_dis, I_allow_chg, psi, cause, psi_s, dom, psi_i, tdot, psi_p] = decision_logic(I_meas, V_min, V_max, Tc_hat, Ts_hat, Ru_hat, SOC_est, bias_est, T_valid, I_valid, CAN_ok, T_meas, T_amb, T_anom, k_R, soh_c)
%DECISION_LOGIC  Güvenli karar mekanizması (Hedef 4): 4 durumlu makine + izin verilen akım.
%   Durumlar: 1 NORMAL, 2 DERATE, 3 LIMP-HOME, 4 SAFE-STOP (kilitlenir; çıkış: clear decision_logic)
%   Çıkışlar: I_allow_dis / I_allow_chg (pozitif büyüklük, A), psi = 1 - I_allow_dis/I_nom,
%             cause = neden bitleri: 1 sıcaklık, 2 soğutma alarmı, 4 deşarj gerilim payı,
%             8 şarj gerilim payı, 16 veri sayfası sıcaklık sınırı, 32 sensör, 64 boş, 128 sert sınır,
%             256 termal anomali (thermal_anomaly_step.m; 1 de kurulur: CAN 0x201'de cause 8 bit),
%             2048 termal olay (yalnız SAFE'te: akım yokken yüzey ortamın üstünde ısınıyor; kilitli),
%             512 sıcaklık artış hızı (Ψ_Tdot > 0; 1 de kurulur), 1024 sağlık (Ψ_H > 0),
%             4096 yaşlanma hızı (Ψ_A > 0), 8192 grup dengesizliği (Ψ_B > 0) (1024/4096/8192 bilgi: DERATE değil)
%             psi_s = stres indeksi Ψ = VEYA(Ψ_i), psi_p = koruma Ψ_P = VEYA(Ψ_T, Ψ_C, Ψ_Tdot),
%             dom = baskın kriter (0 yok, 1 T, 2 C, 3 Tdot, 4 H, 5 A, 6 B),
%             psi_i = [Ψ_T Ψ_C Ψ_Tdot Ψ_H Ψ_A Ψ_B], tdot = süzülmüş yüzey sıcaklığı artış hızı [°C/dk]
%   T_anom (isteğe bağlı, varsayılan 0): açıklanamayan ısı -> LIMP-HOME
%   k_R (isteğe bağlı, varsayılan 1): EKF R0 ölçeği -> Ψ_H ve SOP direnci R0·clip(k_R,1,2)
%   soh_c (isteğe bağlı, varsayılan 1): kapasite SOH'u -> Ψ_H
%
%   I_allow_dis = rampa( min( I_veri_sayfası(T_surf) * (1 - Ψ_P),  I_SOP ) )
%   I_allow_chg = rampa( min( I_veri_sayfası(T_surf) * (1 - Ψ_P) * max(1 - Ψ_cyc, 0,3C taban), I_SOP ) )
%     VEYA(x) = 1 - Π(1 - x_i); Ψ_P = VEYA(Ψ_T, Ψ_C, Ψ_Tdot), gösterge Ψ = VEYA(altısı):
%       Ψ_T    43→55 °C doğrusal (45 °C'de başlar, 43 altında kalkar), tavan 1
%       Ψ_C    soğutma alarmı (R_u > 18 K/W'ta açılır, < 15 K/W'ta kalkar; ilk 120 s yok) 0.3
%       Ψ_Tdot ölçülen yüzey T'nin süzülmüş artış hızı 3→10 °C/dk, tavan 0.5
%       Ψ_H    kapasite SOH 90→70 % ve k_R 1.2→1.3 (büyüğü), gösterge
%       Ψ_A    yaşlanma hızı: VEYA(Ψ_cyc, Ψ_cal), Ψ = log2(R)/3; R_cyc = S(T,m,dod)/S_ref · |I|/0,5C
%              (stress_model.m, yarım çevrim kuralı), R_cal = alpha(OCV(SOC),T)/alpha(OCV(0,5),25 °C), 2x'te başlar
%       Ψ_B    V_max - V_min (|I| < 2 A, 10 s süzgeç) 50→150 mV, gösterge
%     I_SOP (hızlı, akımı keser) = |I| + k·Np·(V - V_sınır)/R0(T); gerilim eşiği yerine akım sınırı
%     Durum için yavaş kapasite tahmini: SOP_qs = Np·(V ± |i|R0 - V_sınır)/(R0+R1+R2),
%         < %90 · veri sayfası sınırı -> neden; ≥ %100 -> kalkar (histerezis bandı)
%   LIMP-HOME (sensör arızası, |b_I| > 5 A, T_core > 55 °C, SOC < %3): taban %25, ama gerilim
%     payını ve veri sayfası sınırını asla aşmaz.
%   SAFE-STOP: T_core > 60 °C, V_min < 2.5 V (1 s), V_max > 4.25 V (1 s), CAN kesintisi.
%   Ölçüme bağlı çekirdek sınırı: T_ss = T_meas + Rc/Ru (T_meas - T_amb) > 55 / 60 °C (1 s)
%     -> LIMP-HOME / SAFE-STOP (gözlemcinin göremediği modellenmemiş ısı; sensör geçerliyse).
%   Kısıtlayıcı yöne anında, gevşetici yöne neden 10 s yokken geçilir; düşüşler anında, artışlar
%   en fazla 10 A/s; açılışta I_allow = 0'dan başlar.
%   Python referansı: twin/decision.py (birebir aynı mantık; test_decision.m doğrular)

%#codegen
if nargin < 14, T_anom = 0; end
if nargin < 15, k_R = 1; end
if nargin < 16, soh_c = 1; end
persistent P D
if isempty(P)
    P = bms_param_struct();
end
if isempty(D)
    D = struct('state', 1, 'n_ok', 0, 'n_lo', 0, 'n_hi', 0, 'therm_on', false, 'cool_on', false, 'n_run', 0, 'n_hl', 0, 'n_hs', 0, ...
               'f_ds', false, 'f_sop_dis', false, 'f_sop_chg', false, 'i_dis', 0, 'i_chg', 0, ...
               'n_zero', 0, 'i0_sum', 0, 'i0_ok', true, 'zero_bad', false, ...
               'td_on', false, 't_f', 0, 'tdot', 0, 'n_i0', 0, 'n_te', 0, 'tevt', false, ...
               'a_dir', 0, 'a_soc_rev', 0.5, 'a_sum', 0, 'a_n', 0, 'a_swing', 0, 'r_cyc', 0, 'dmg', 0, ...
               'dv_f', 0, 'dv_on', false);
end
ts = P.Ts;  np_ = P.Np;
I_nom_dis = max(P.dec_I_dis) * np_;
I_nom_chg = max(P.dec_I_chg) * np_;

% ---------------------------------------------------- stres indeksi (SAFE'te de hesaplanır: telemetri)
if Tc_hat >= P.dec_T_der_on
    D.therm_on = true;
elseif Tc_hat < P.dec_T_der_off
    D.therm_on = false;
end
psi_T = 0;
if D.therm_on
    psi_T = min(max((Tc_hat - P.dec_T_der_off) / (P.dec_T_der_full - P.dec_T_der_off), 0), 1);
end
n_blank = round(P.dec_t_cool_blank / ts);
if D.n_run < n_blank, D.n_run = D.n_run + 1; end
if D.n_run < n_blank                    % gözlemci yakınsıyor: alarm yok
    D.cool_on = false;
elseif Ru_hat > P.dec_ru_alarm
    D.cool_on = true;
elseif Ru_hat < P.dec_ru_alarm_off
    D.cool_on = false;
end
psi_C = 0;
if D.cool_on
    psi_C = P.dec_psi_cool;
end
if T_valid >= 0.5                       % sıcaklık artış hızı; sensör geçersizse süzgeç yeniden başlar
    if D.td_on
        t_prev = D.t_f;
        D.t_f = D.t_f + P.dec_td_a_f * (T_meas - D.t_f);
        D.tdot = D.tdot + P.dec_td_a_r * (60 * (D.t_f - t_prev) / ts - D.tdot);
    else
        D.td_on = true;  D.t_f = T_meas;  D.tdot = 0;
    end
else
    D.td_on = false;  D.tdot = 0;
end
psi_D = P.dec_psi_tdot * min(max((D.tdot - P.dec_tdot_on) / (P.dec_tdot_full - P.dec_tdot_on), 0), 1);
blank = D.n_run < n_blank;              % açılıştan sonra 120 s Ψ_H/Ψ_A/Ψ_B yok (EKF yakınsıyor)
psi_H = max(min(max((P.dec_soh_on - soh_c) / (P.dec_soh_on - P.dec_soh_full), 0), 1), ...
            min(max((k_R - P.dec_kr_on) / (P.dec_kr_full - P.dec_kr_on), 0), 1));
if blank, psi_H = 0; end
% Ψ_A: yarım çevrim kuralı (|I| > ölü bant, yön değişince yeni yarım çevrim)
soc = min(max(SOC_est, 0), 1);
i_abs = abs(I_meas);
r_inst = 0;
if i_abs > P.dec_age_i_min
    if I_meas > 0, dr = 1; else, dr = -1; end
    if dr ~= D.a_dir
        if D.a_dir ~= 0, D.a_swing = abs(soc - D.a_soc_rev); end
        D.a_dir = dr;  D.a_soc_rev = soc;  D.a_sum = 0;  D.a_n = 0;
    end
    D.a_sum = D.a_sum + soc;  D.a_n = D.a_n + 1;
    m = D.a_sum / D.a_n;
    dod = min(max(max(abs(soc - D.a_soc_rev), D.a_swing), 0), 1);
    s_rel = stress_model(Tc_hat, m, dod) / P.dec_age_s_ref;
    r_inst = s_rel * (i_abs / np_) / P.dec_age_i_ref;
    D.dmg = D.dmg + s_rel * i_abs * ts / (2 * np_ * P.Q_Ah * 3600);
end
D.r_cyc = D.r_cyc + P.dec_age_a * (r_inst - D.r_cyc);
v_ocv = interp1(P.soc_tab, P.ocv_tab, soc);
alpha = @(v, t) max(0, P.dec_cal_c1 * v + P.dec_cal_c0) * P.dec_cal_sc * exp(-P.dec_cal_ea / (t + 273.15));
r_cal = alpha(v_ocv, Tc_hat) / alpha(interp1(P.soc_tab, P.ocv_tab, 0.5), 25.0);
psi_cyc = min(max(log2(max(D.r_cyc, 1e-9)) / P.dec_age_log2_full, 0), 1);
psi_cal = min(max(log2(max(r_cal / P.dec_age_cal_onset, 1e-9)) / P.dec_age_log2_full, 0), 1);
if blank, psi_cyc = 0; end
psi_A = 1 - (1 - psi_cyc) * (1 - psi_cal);
if blank, psi_A = 0; end
% Ψ_B: yalnız düşük akımda güncellenir
dv = V_max - V_min;
if i_abs < P.dec_bal_i_max
    if D.dv_on, D.dv_f = D.dv_f + P.dec_bal_a * (dv - D.dv_f); else, D.dv_f = dv; D.dv_on = true; end
end
psi_B = 0;
if ~blank && D.dv_on, psi_B = min(max((D.dv_f - P.dec_imb_on) / (P.dec_imb_full - P.dec_imb_on), 0), 1); end
psi_i = [psi_T psi_C psi_D psi_H psi_A psi_B];
psi_p = 1 - prod(1 - psi_i(1:3));
psi_s = 1 - prod(1 - psi_i);
[pm, im] = max(psi_i);                  % ilk en büyük: Python index() ile aynı
dom = 0;
if pm > 0, dom = im; end
tdot = D.tdot;

% ---------------------------------------------------- sert sınırlar (kilitlenir)
% sayaçlar örnek cinsinden (tamsayı): 10 x 0.1 kayan noktada tam 1.0 etmez
n_hard = round(P.dec_t_hard / ts);
if V_min < P.dec_v_safe_lo, D.n_lo = D.n_lo + 1; else, D.n_lo = 0; end
if V_max > P.dec_v_safe_hi, D.n_hi = D.n_hi + 1; else, D.n_hi = 0; end
if T_valid >= 0.5
    t_ss = T_meas + P.dec_k_ss * (T_meas - T_amb);
    if t_ss > P.dec_T_limp, D.n_hl = D.n_hl + 1; else, D.n_hl = 0; end
    if t_ss > P.dec_T_safe, D.n_hs = D.n_hs + 1; else, D.n_hs = 0; end
else
    D.n_hl = 0;  D.n_hs = 0;
end
hard = Tc_hat > P.dec_T_safe || D.n_hs >= n_hard || D.n_lo >= n_hard || D.n_hi >= n_hard || CAN_ok < 0.5;
if hard || D.state == 4
    D.state = 4;  D.i_dis = 0;  D.i_chg = 0;
    % termal olay: akım yokken yüzey ortamın üstünde ısınmayı sürdürüyor (bms_config.h DEC_TE_*)
    if abs(I_meas) < P.dec_te_i_max, D.n_i0 = min(D.n_i0 + 1, P.dec_te_wait); else, D.n_i0 = 0; end
    rising = CAN_ok >= 0.5 && T_valid >= 0.5 && T_meas > T_amb && D.tdot > P.dec_te_rate;
    if rising && D.n_i0 > 0 && (T_anom > 0.5 || D.n_i0 >= P.dec_te_wait), D.n_te = D.n_te + 1; else, D.n_te = 0; end
    if D.n_te >= P.dec_te_n, D.tevt = true; end
    state = 4;  I_allow_dis = 0;  I_allow_chg = 0;  psi = 1;  cause = 128 + 2048 * D.tevt;
    return;
end

% ---------------------------------------------------- açılış sıfır akım kontrolü (A9)
% ilk dec_t_zero s kontaktör açık (I_allow = 0): akım kesin 0, ölçülen ortalama = sensör ofseti
n_zero = round(P.dec_t_zero / ts);
zeroing = D.n_zero < n_zero;
if zeroing
    D.i0_sum = D.i0_sum + I_meas;
    D.i0_ok = D.i0_ok && I_valid >= 0.5;
    D.n_zero = D.n_zero + 1;
    if D.n_zero == n_zero
        D.zero_bad = D.i0_ok && abs(D.i0_sum / n_zero) > P.dec_zero_max;
    end
end

% ---------------------------------------------------- veri sayfası sınırları
i_ds_dis = interp1(P.dec_T_dis, P.dec_I_dis, Ts_hat, 'linear', 0) * np_;
i_ds_chg = interp1(P.dec_T_chg, P.dec_I_chg, Ts_hat, 'linear', 0) * np_;
D.f_ds = band(D.f_ds, min(i_ds_dis / I_nom_dis, i_ds_chg / I_nom_chg), P);

% ---------------------------------------------------- gerilim payı (SOP)
r0 = P.r0 * min(max(k_R, 1), P.dec_kr_sop_max) * exp(P.ea_r0 / P.Rgas * (1/(Tc_hat + 273.15) - 1/298.15));
sop_dis = max(I_meas, 0) + P.dec_k_sop * np_ * (V_min - P.dec_v_lim_dis) / r0;
sop_chg = max(-I_meas, 0) + P.dec_k_sop * np_ * (P.dec_v_lim_chg - V_max) / r0;
r_dc = r0 + P.r1 * exp(P.ea_r1 / P.Rgas * (1/(Tc_hat + 273.15) - 1/298.15)) ...
           + P.r2 * exp(P.ea_r2 / P.Rgas * (1/(Tc_hat + 273.15) - 1/298.15));   % R0 + R1 + R2 (T)
ic = I_meas / np_;
qs_dis = np_ * (V_min + max(ic, 0) * r0 - P.dec_v_lim_dis) / r_dc;
qs_chg = np_ * (P.dec_v_lim_chg - (V_max - max(-ic, 0) * r0)) / r_dc;
D.f_sop_dis = band(D.f_sop_dis, qs_dis / max(i_ds_dis, 1e-6), P);
D.f_sop_chg = band(D.f_sop_chg, qs_chg / max(i_ds_chg, 1e-6), P);

tgt_dis = max(0, min(i_ds_dis * (1 - psi_p), sop_dis));
f_age = min(1, max(1 - psi_cyc, P.dec_age_floor * np_ / max(i_ds_chg, 1e-6)));   % Ψ_cyc payı 0,3C tabanlı
tgt_chg = max(0, min(i_ds_chg * (1 - psi_p) * f_age, sop_chg));

% ---------------------------------------------------- LIMP-HOME
sensor_bad = T_valid < 0.5 || I_valid < 0.5 || abs(bias_est) > P.dec_bias_max || D.zero_bad;
empty = SOC_est < P.dec_soc_empty;
hot_ss = D.n_hl >= n_hard;
limp = sensor_bad || Tc_hat > P.dec_T_limp || hot_ss || empty || T_anom > 0.5;
if limp
    tgt_dis = min([P.dec_floor * I_nom_dis, i_ds_dis, max(sop_dis, 0)]);
    tgt_chg = min(tgt_chg, P.dec_floor * I_nom_chg);
end

cause = 1*(psi_T > 0 || hot_ss || T_anom > 0.5 || psi_D > 0) + 2*(psi_C > 0) + 4*D.f_sop_dis + 8*D.f_sop_chg + 16*D.f_ds ...
      + 32*sensor_bad + 64*empty + 256*(T_anom > 0.5) + 512*(psi_D > 0) + 1024*(psi_H > 0) ...
      + 4096*(psi_A > 0) + 8192*(psi_B > 0);

% ---------------------------------------------------- durum + histerezis
if limp
    want = 3;
elseif cause - bitand(cause, 1024 + 4096 + 8192) > 0   % Ψ_H/Ψ_A/Ψ_B bilgi, DERATE değil
    want = 2;
else
    want = 1;
end
if want > D.state                       % kısıtlayıcı yön: anında
    D.state = want;  D.n_ok = 0;
elseif want < D.state                   % gevşetici yön: bekle
    D.n_ok = D.n_ok + 1;
    if D.state == 3, need = P.dec_t_exit_limp; else, need = P.dec_t_exit_derate; end
    if D.n_ok >= round(need / ts)
        D.state = want;  D.n_ok = 0;
    end
else
    D.n_ok = 0;
end

% ---------------------------------------------------- rampa (düşüş anında, artış ≤ ramp_up)
D.i_dis = ramp(D.i_dis, tgt_dis, P.dec_ramp_up * ts);
D.i_chg = ramp(D.i_chg, tgt_chg, P.dec_ramp_up * ts);
if zeroing
    D.i_dis = 0;  D.i_chg = 0;
end

state = D.state;
I_allow_dis = D.i_dis;
I_allow_chg = D.i_chg;
psi = 1 - D.i_dis / I_nom_dis;
end

% ----------------------------------------------------------------------- yerel fonksiyonlar
function f = band(f, ratio, P)
%BAND  Histerezis bandı: oran < dec_band_on -> true, > dec_band_off -> false, arada değişmez.
if ratio < P.dec_band_on
    f = true;
elseif ratio > P.dec_band_off
    f = false;
end
end

function y = ramp(cur, tgt, step)
if tgt < cur
    y = tgt;
else
    y = min(tgt, cur + step);
end
end
