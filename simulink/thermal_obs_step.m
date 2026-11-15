function [x, Pk, q, innov] = thermal_obs_step(x, Pk, I_meas, V_meas, SOC_est, T_meas, T_amb, P, est_g, meas_ok)
%THERMAL_OBS_STEP  Çekirdek sıcaklığı gözlemcisinin durumsuz bir adımı.
%   x = [Tc; Ts; g]  (g = 1/Ru, yüzey-ortam ısıl iletkenliği [W/K])
%   Durum (x, Pk) çağırana aittir: Simulink bloğu (thermal_observer.m)
%   kalıcı değişkende tutar, test betiği döngüde taşır. STM32'ye de bu
%   haliyle (3x3 float) çevrilecek.
%
%   est_g = true : 3 durumlu EKF, soğutma iletkenliği de kestirilir (önerilen)
%   est_g = false: g nominalde sabit, 2 durumlu doğrusal KF (karşılaştırma)
%
%   meas_ok = false: sensör geçersiz, sadece tahmin adımı (bozulmuş mod)
%   Python referansı: twin/thermal_observer.py (birebir aynı denklemler)

%#codegen
dt = P.Ts;  cc = P.cc;  cs = P.cs;  rc = P.rc;

% ---- Isı girdisi: Bernardi, ölçülen V ve EKF SOC'si ile ----
i   = I_meas / P.Np;
ocv = polyval(P.ocv_poly, min(max(SOC_est, 0), 1));
q   = i * (ocv - V_meas / P.Ns);

tc = x(1);  ts = x(2);  g = x(3);

% ---- Tahmin ----
xp = [tc + dt/cc * (q + (ts - tc)/rc);
      ts + dt/cs * (g*(T_amb - ts) - (ts - tc)/rc);
      g];
A = [1 - dt/(cc*rc),  dt/(cc*rc),              0;
     dt/(cs*rc),      1 - dt/cs*(g + 1/rc),    dt/cs*(T_amb - ts);
     0,               0,                       1];
Qn = diag(P.th_Q);
if ~est_g
    A(2,3) = 0;  Qn(3,3) = 0;
end
Pp = A * Pk * A' + Qn;

if ~meas_ok
    x = xp;  Pk = Pp;  innov = 0;
    return;
end

% ---- Düzeltme: y = Ts (NTC) ----
C     = [0 1 0];
S     = Pp(2,2) + P.th_R;
K     = Pp(:,2) / S;
innov = T_meas - xp(2);
x     = xp + K * innov;
x(3)  = max(x(3), P.th_g_min);
IKC   = eye(3) - K * C;
Pk    = IKC * Pp * IKC' + P.th_R * (K * K');   % Joseph formu
end
