function [SOC_est, bias_est, innov, rejected] = ekf_soc(I_meas, V_meas, T_meas, T_valid, Ts_hat_prev, Gate_on, Q_scale, R_scale)
%EKF_SOC  Paket seviyesi 5 durumlu Genişletilmiş Kalman Filtresi.
%   x = [SOC; V1; V2; b_I; k_R]   (b_I: akım sensörü kayması, k_R: gerçek R0 / nominal R0)
%   k_R olmadan R0 uyumsuzluğu (yaşlanma) b_I'ya yükleniyor, sahte sensör arızası veriyordu (A7).
%   Girdiler CAN 0x101 çözünürlüğünde: V 0.1 V, I 0.1 A, T 0.1 °C.
%   R0(T) düzeltmesi ölçülen yüzey sıcaklığıyla yapılır; sıcaklık sensörü
%   geçersizse (T_valid = 0) gözlemcinin bir önceki yüzey kestirimi kullanılır.
%   Normalize inovasyon kapısı: |ν| > ekf_gate·sqrt(S) olan ölçüm (EMI sıçraması)
%   reddedilir; ekf_n_rej örnek üst üste red olursa kapı açılır (model yanlış demektir).
%   Gate_on = 0: kapı kapalı (teşhissiz karşılaştırma testi için).
%   Q_scale, R_scale: BMS'in bildiği yaşlanma (ML SOH tahmini ve direnç oranı); yeni hücre = 1.
%
%   STM32'ye taşınırken bu fonksiyon doğrudan C'ye çevrilecek (4x4 float).
%   Not (kod üretimi): her kalıcı değişken kendi isempty kontrolüyle başlatılır.

%#codegen
persistent P x Pk n_rej
if isempty(P)
    P = bms_param_struct();
end
if isempty(x)
    x = [P.soc0_ekf; 0; 0; 0; 1];
end
if isempty(Pk)
    Pk = diag(P.ekf_P0);
end
if isempty(n_rej)
    n_rej = 0;
end

% ---- Paket eşdeğer parametreleri (sabit, her adımda ucuz) ----
dt  = P.Ts;
k   = P.Ns / P.Np;
R0r = R_scale * P.r0 * k;  R1 = R_scale * P.r1 * k;  C1 = P.c1 / k;
R2  = R_scale * P.r2 * k;  C2 = P.c2 / k;
Qah = Q_scale * P.Q_Ah * P.Np;
Qn  = diag(P.ekf_Q);

% ---- R0(T): Arrhenius, ölçülen T_surf ile (sensör geçersizse gözlemci kestirimi) ----
if T_valid > 0.5
    T_use = T_meas;
else
    T_use = Ts_hat_prev;
end
R0 = R0r * exp(P.ea_r0 / P.Rgas * (1/(T_use + 273.15) - 1/298.15));
R1 = R1 * exp(P.ea_r1 / P.Rgas * (1/(T_use + 273.15) - 1/298.15));   % RC dalları (Kirkaldy 2024)
R2 = R2 * exp(P.ea_r2 / P.Rgas * (1/(T_use + 273.15) - 1/298.15));
a1 = exp(-dt / (R1 * C1));
a2 = exp(-dt / (R2 * C2));

kr = x(5);
i  = I_meas - x(4);
kc = dt / (3600 * Qah);

% ---- Tahmin (a priori) ----
xp    = x;
xp(1) = x(1) - kc * i;
xp(2) = a1 * x(2) + R1 * (1 - a1) * i;
xp(3) = a2 * x(3) + R2 * (1 - a2) * i;

A = [1  0  0   kc         0;
     0  a1 0  -R1*(1-a1)  0;
     0  0  a2 -R2*(1-a2)  0;
     0  0  0   1          0;
     0  0  0   0          1];
Pp = A * Pk * A' + Qn;

% ---- Düzeltme (a posteriori) ----
s     = min(max(xp(1), 0), 1);
ocv   = P.Ns * polyval(P.ocv_poly,  s);
docv  = P.Ns * polyval(P.docv_poly, s);
y_hat = ocv - kr * R0 * i - xp(2) - xp(3);
C     = [docv, -1, -1, kr * R0, -R0 * i];

S     = C * Pp * C' + P.ekf_R;
K     = Pp * C' / S;
innov = V_meas - y_hat;

% ---- İnovasyon kapısı ----
rej = Gate_on > 0.5 && abs(innov) > P.ekf_gate * sqrt(S) && n_rej < P.ekf_n_rej;
if rej
    n_rej = n_rej + 1;
    x  = xp;                                    % ölçümü yok say, sadece tahmin
    Pk = Pp;
else
    n_rej = 0;
    x     = xp + K * innov;
    x(5)  = min(max(x(5), P.ekf_kr_min), P.ekf_kr_max);
    IKC   = eye(5) - K * C;
    Pk    = IKC * Pp * IKC' + P.ekf_R * (K * K');   % Joseph formu
end
rejected = double(rej);

SOC_est  = x(1);
bias_est = x(4);
end
