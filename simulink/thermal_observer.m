function [Tc_hat, Ts_hat, Ru_hat, T_anom] = thermal_observer(I_meas, V_meas, SOC_est, T_meas, T_amb, T_valid)
%THERMAL_OBSERVER  Simulink MATLAB Function bloğu: çekirdek sıcaklığı gözlemcisi.
%   Girdiler CAN 0x101 çözünürlüğünde (V 0.1 V, I 0.1 A, T 0.1 °C);
%   SOC_est, SOC EKF'sinden gelir (iki gözlemci zincir halinde).
%   Çıkışlar: kestirilen çekirdek ve yüzey sıcaklığı, kestirilen Ru [K/W].
%   Ru_hat nominalin (9 K/W) belirgin üstüne çıkarsa soğutma bozulmuştur:
%   3. haftadaki karar mekanizması bunu girdi olarak kullanacak.
%   T_valid = 0 (sensör teşhisi): ölçüm düzeltmesi yapılmaz, gözlemci son
%   öğrendiği soğutma değeriyle sadece modelle devam eder (bozulmuş mod).
%   T_anom: termal anomali (thermal_anomaly_step.m, açıklanamayan ısı; kilitlenir). Anomalide g
%   donar ve Tc ölçüme bağlı kararlı hal sınırının altına inmez (C: bms_step ile aynı sıra).

%#codegen
persistent P x Pk A
if isempty(P)
    P = bms_param_struct();
end
if isempty(x)
    x = [T_meas; T_meas; 1 / P.ru];         % ilk ölçümle başlat
end
if isempty(Pk)
    Pk = diag(P.th_P0);
end
if isempty(A)
    A = thermal_anomaly_init();
end

g_prev = x(3);
[x, Pk] = thermal_obs_step(x, Pk, I_meas, V_meas, SOC_est, T_meas, T_amb, P, true, T_valid > 0.5);
[A, anom] = thermal_anomaly_step(A, I_meas, V_meas, SOC_est, T_meas, T_amb, x(1), T_valid, P);
if anom
    x(3) = g_prev;
    if T_valid > 0.5, x(1) = max(x(1), T_meas + P.dec_k_ss * (T_meas - T_amb)); end
end
T_anom = double(anom);

Tc_hat = x(1);
Ts_hat = x(2);
Ru_hat = 1 / x(3);
end
