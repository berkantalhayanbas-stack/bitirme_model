function [rr_hat, num, den, n_ev] = rint_estimator(I_meas, V_meas, Tc_hat, SOC_est, I_valid, num0, den0)
%RINT_ESTIMATOR  Çevrimiçi iç direnç kestiricisi (sürüş sırasında, CAN ölçümlerinden).
%   Akım bir örnekte (0.1 s) |ΔI| >= 20 A değişirse: ΔV ≈ -R_pack·ΔI
%   (Kirkaldy verisindeki "0.1 s direnci" tanımı -> ML modeline doğrudan girer).
%   Sıcaklık (gözlemcinin T_core kestirimi) ve SOC (EKF) etkisi 25 °C'ye normalize edilir,
%   en küçük kareler ile birikir:  R25 = Σ(-ΔV·ΔI/f) / Σ(ΔI²), unutma çarpanı λ.
%   num0, den0: önceki sürüşlerden saklanan birikimler (BMS'te EEPROM; test betiği taşır).
%   Çıkış: rr_hat = R25 / R_BoL (ML girdisi), num/den (sürüş sonunda saklanacak), olay sayısı.
%   Python referansı: twin/rint_estimator.py

%#codegen
persistent P S
if isempty(P)
    P = bms_param_struct();
end
if isempty(S)
    S = struct('first', true, 'i_prev', 0, 'v_prev', 0, 'num', num0, 'den', den0, 'n', 0);
end

if ~S.first && I_valid > 0.5
    di = I_meas - S.i_prev;
    dv = V_meas - S.v_prev;
    if abs(di) >= P.rint_di_min && SOC_est > P.rint_soc_min
        f = exp(P.ea_r0 / P.Rgas * (1/(Tc_hat + 273.15) - 1/298.15)) ...
            * (1 + 0.6 * exp(-SOC_est / 0.08));
        k = P.Np / P.Ns;
        r_ev = -dv / di * k / f;
        if r_ev > 0.3 * P.r0 && r_ev < 4 * P.r0          % kaba aykırı olayı at
            S.num = P.rint_lam * S.num + (-dv * di / f) * k;
            S.den = P.rint_lam * S.den + di * di;
            S.n   = S.n + 1;
        end
    end
end
S.first  = false;
S.i_prev = I_meas;
S.v_prev = V_meas;

if S.den > 0
    rr_hat = S.num / S.den / P.r0;
else
    rr_hat = 1.0;
end
num  = S.num;
den  = S.den;
n_ev = S.n;
end
