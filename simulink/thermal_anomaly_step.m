function [A, flag] = thermal_anomaly_step(A, I_meas, V_meas, SOC_est, T_meas, T_amb, Tc_hat, T_valid, P)
%THERMAL_ANOMALY_STEP  Termal anomali dedektörünün durumsuz bir adımı (açıklanamayan ısı).
%   Gözlemci yalnız Ts'yi ölçer ve ısıyı I^2R + ortamla açıklar; gizli bir kaynak (dış ısı, iç kısa
%   devre başlangıcı) g'yi alt sınıra iter, Tc düşük kalır. "Adyabatik zarf": bilinen ısının üst
%   sınırı (ta_q_k * q + ta_q_off) ve SOĞUTMA YOK (ortam yüzeyden sıcaksa g = ta_g_max) ile Ts'nin
%   çıkabileceği en yüksek değer; iki kaydırmalı pencere ölçümden yeniden başlar. Süzülmüş ölçüm
%   zarfı ta_r_th aşar, ta_n örnek sürerse anomali (kilitlenir).
%   Durum A çağırana aittir (thermal_anomaly_init ile başlar).
%   Python: twin/thermal_anomaly.py, C: bms_algo.c tanom_step (birebir aynı)

%#codegen
if T_valid < 0.5                               % ölçüm dönünce baştan
    A.started = false;  A.n = 0;  flag = A.flag;  return;
end
if ~A.started                                  % ilk adımda iki zarf da başlar
    A.t_f = T_meas;  A.k = 0;  A.started = true;  A.age = [-1 -1];
end
A.t_f = A.t_f + P.ta_alpha * (T_meas - A.t_f);
i = I_meas / P.Np;
q = max(i * (polyval(P.ocv_poly, min(max(SOC_est, 0), 1)) - V_meas / P.Ns), 0) * P.ta_q_k + P.ta_q_off;
r = -1e9;
for j = 1:2
    if A.k == (j - 1) * (P.ta_win / 2) || A.age(j) < 0      % kaydırmalı yeniden başlatma
        A.tc(j) = max(Tc_hat, A.t_f) + P.ta_tc0;  A.ts(j) = A.t_f + P.ta_ts0;  A.age(j) = 0;
    end
    tc = A.tc(j);  ts = A.ts(j);
    if T_amb > ts, g = P.ta_g_max; else, g = 0; end
    A.tc(j) = tc + P.Ts / P.cc * (q + (ts - tc) / P.rc);
    A.ts(j) = ts + P.Ts / P.cs * (g * (T_amb - ts) - (ts - tc) / P.rc);
    A.age(j) = A.age(j) + 1;
    if A.age(j) >= P.ta_age_min, r = max(r, A.t_f - A.ts(j)); end
end
A.k = mod(A.k + 1, P.ta_win);
if r > -1e8
    if r > P.ta_r_th, A.n = A.n + 1; else, A.n = 0; end
    if A.n >= P.ta_n, A.flag = true; end
end
flag = A.flag;
end
