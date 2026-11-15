function [T_valid, I_valid] = sensor_diag(I_meas, T_meas, Diag_on)
%SENSOR_DIAG  Sensör teşhisi (makullük kontrolleri), CAN 0x101 değerleri üzerinde.
%   Sıcaklık: aralık (-30..85 °C), değişim hızı (> 2 °C/örnek) ve donma
%   (5 s boyunca aynı değer) kontrolü. Akım: donma kontrolü.
%   Bayraklar kalıcıdır (latched): geçersiz sensör bu sürüşte tekrar güvenilir sayılmaz.
%   Akım ofset kayması burada değil, SOC EKF'sinin kayma durumunda kestirilir;
%   gerilim sıçramaları EKF'nin inovasyon kapısında reddedilir.
%   Diag_on = 0: teşhis kapalı (karşılaştırma testi için), bayraklar hep 1.
%   Python referansı: twin/sensor_faults.py (SensorDiag)

%#codegen
persistent P D
if isempty(P)
    P = bms_param_struct();
end
if isempty(D)
    D = struct('first', true, 't_prev', 0, 'i_prev', 0, 'n_t', 0, 'n_i', 0, ...
               'tv', true, 'iv', true);
end

if ~D.first
    if T_meas == D.t_prev, D.n_t = D.n_t + 1; else, D.n_t = 0; end
    if I_meas == D.i_prev, D.n_i = D.n_i + 1; else, D.n_i = 0; end
    if abs(T_meas - D.t_prev) > P.diag_T_rate
        D.tv = false;
    end
end
if T_meas < P.diag_T_min || T_meas > P.diag_T_max || D.n_t >= P.diag_n_frozen
    D.tv = false;
end
if D.n_i >= P.diag_n_frozen
    D.iv = false;
end
D.first  = false;
D.t_prev = T_meas;
D.i_prev = I_meas;

T_valid = double(D.tv || Diag_on < 0.5);
I_valid = double(D.iv || Diag_on < 0.5);
end
