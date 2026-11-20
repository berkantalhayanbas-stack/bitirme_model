function [state, I_allow_dis, I_allow_chg, psi, cause] = decision_logic(I_meas, V_min, V_max, Tc_hat, Ts_hat, Ru_hat, SOC_est, bias_est, T_valid, I_valid, CAN_ok, T_meas, T_amb)
%DECISION_LOGIC  Güvenli karar mekanizması (Hedef 4): 4 durumlu makine + izin verilen akım.
%   Durumlar: 1 NORMAL, 2 DERATE, 3 LIMP-HOME, 4 SAFE-STOP (kilitlenir; çıkış: clear decision_logic)
%   Çıkışlar: I_allow_dis / I_allow_chg (pozitif büyüklük, A), psi = 1 - I_allow_dis/I_nom,
%             cause = neden bitleri: 1 sıcaklık, 2 soğutma alarmı, 4 deşarj gerilim payı,
%             8 şarj gerilim payı, 16 veri sayfası sıcaklık sınırı, 32 sensör, 64 boş, 128 sert sınır
%
%   I_allow = rampa( min( I_veri_sayfası(T_surf) * (1 - Ψ),  I_SOP ) )
%     Ψ = max(Ψ_sıcaklık, Ψ_soğutma): 43→55 °C doğrusal (45 °C'de başlar, 43 altında kalkar);
%         soğutma alarmı (R_u > 18 K/W'ta açılır, < 15 K/W'ta kalkar; ilk 120 s yok) 0.3 önleyici kısıtlama
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
persistent P D
if isempty(P)
    P = bms_param_struct();
end
if isempty(D)
    D = struct('state', 1, 'n_ok', 0, 'n_lo', 0, 'n_hi', 0, 'therm_on', false, 'cool_on', false, 'n_run', 0, 'n_hl', 0, 'n_hs', 0, ...
               'f_ds', false, 'f_sop_dis', false, 'f_sop_chg', false, 'i_dis', 0, 'i_chg', 0, ...
               'n_zero', 0, 'i0_sum', 0, 'i0_ok', true, 'zero_bad', false);
end
ts = P.Ts;  np_ = P.Np;
I_nom_dis = max(P.dec_I_dis) * np_;
I_nom_chg = max(P.dec_I_chg) * np_;

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
    state = 4;  I_allow_dis = 0;  I_allow_chg = 0;  psi = 1;  cause = 128;
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

% ---------------------------------------------------- stres indeksi
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
psi_s = max(psi_T, psi_C);

% ---------------------------------------------------- gerilim payı (SOP)
r0 = P.r0 * exp(P.ea_r0 / P.Rgas * (1/(Tc_hat + 273.15) - 1/298.15));
sop_dis = max(I_meas, 0) + P.dec_k_sop * np_ * (V_min - P.dec_v_lim_dis) / r0;
sop_chg = max(-I_meas, 0) + P.dec_k_sop * np_ * (P.dec_v_lim_chg - V_max) / r0;
r_dc = r0 + P.r1 * exp(P.ea_r1 / P.Rgas * (1/(Tc_hat + 273.15) - 1/298.15)) ...
           + P.r2 * exp(P.ea_r2 / P.Rgas * (1/(Tc_hat + 273.15) - 1/298.15));   % R0 + R1 + R2 (T)
ic = I_meas / np_;
qs_dis = np_ * (V_min + max(ic, 0) * r0 - P.dec_v_lim_dis) / r_dc;
qs_chg = np_ * (P.dec_v_lim_chg - (V_max - max(-ic, 0) * r0)) / r_dc;
D.f_sop_dis = band(D.f_sop_dis, qs_dis / max(i_ds_dis, 1e-6), P);
D.f_sop_chg = band(D.f_sop_chg, qs_chg / max(i_ds_chg, 1e-6), P);

tgt_dis = max(0, min(i_ds_dis * (1 - psi_s), sop_dis));
tgt_chg = max(0, min(i_ds_chg * (1 - psi_s), sop_chg));

% ---------------------------------------------------- LIMP-HOME
sensor_bad = T_valid < 0.5 || I_valid < 0.5 || abs(bias_est) > P.dec_bias_max || D.zero_bad;
empty = SOC_est < P.dec_soc_empty;
hot_ss = D.n_hl >= n_hard;
limp = sensor_bad || Tc_hat > P.dec_T_limp || hot_ss || empty;
if limp
    tgt_dis = min([P.dec_floor * I_nom_dis, i_ds_dis, max(sop_dis, 0)]);
    tgt_chg = min(tgt_chg, P.dec_floor * I_nom_chg);
end

cause = 1*(psi_T > 0 || hot_ss) + 2*(psi_C > 0) + 4*D.f_sop_dis + 8*D.f_sop_chg + 16*D.f_ds ...
      + 32*sensor_bad + 64*empty;

% ---------------------------------------------------- durum + histerezis
if limp
    want = 3;
elseif cause > 0
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
