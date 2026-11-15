function [Tc_hat, Ts_hat, Ru_hat] = thermal_observer(I_meas, V_meas, SOC_est, T_meas, T_amb, T_valid)
%THERMAL_OBSERVER  Simulink MATLAB Function bloğu: çekirdek sıcaklığı gözlemcisi.
%   Girdiler CAN 0x101 çözünürlüğünde (V 0.1 V, I 0.1 A, T 0.1 °C);
%   SOC_est, SOC EKF'sinden gelir (iki gözlemci zincir halinde).
%   Çıkışlar: kestirilen çekirdek ve yüzey sıcaklığı, kestirilen Ru [K/W].
%   Ru_hat nominalin (9 K/W) belirgin üstüne çıkarsa soğutma bozulmuştur:
%   3. haftadaki karar mekanizması bunu girdi olarak kullanacak.
%   T_valid = 0 (sensör teşhisi): ölçüm düzeltmesi yapılmaz, gözlemci son
%   öğrendiği soğutma değeriyle sadece modelle devam eder (bozulmuş mod).

%#codegen
persistent P x Pk
if isempty(P)
    P = bms_param_struct();
end
if isempty(x)
    x = [T_meas; T_meas; 1 / P.ru];         % ilk ölçümle başlat
end
if isempty(Pk)
    Pk = diag(P.th_P0);
end

[x, Pk] = thermal_obs_step(x, Pk, I_meas, V_meas, SOC_est, T_meas, T_amb, P, true, T_valid > 0.5);

Tc_hat = x(1);
Ts_hat = x(2);
Ru_hat = 1 / x(3);
end
