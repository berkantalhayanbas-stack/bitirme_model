function [V_pack, SOC, T_core, T_surf, OCV_pack, V_cell_min, SOC_weak, V_cell_max] = battery_twin(I_pack, T_amb, Ru_factor, SOC0, Weak_on, Age_Q, Age_R)
%BATTERY_TWIN  19S12P elektro-termal dijital ikiz, bir ayrık zaman adımı.
%   MATLAB Function bloğunun içeriği. Her Ts'de bir kez çağrılır.
%   I_pack    : paket akımı [A] (+ deşarj, - şarj)
%   T_amb     : ortam sıcaklığı [°C]
%   Ru_factor : soğutma arızası çarpanı (1 = normal, 4 = fan arızası vb.)
%   SOC0      : başlangıç SOC'si (yalnızca ilk adımda okunur)
%   Weak_on   : 1 ise 19 seri gruptan biri "zayıf" (kapasite x P.weak_cap,
%               dirençler x P.weak_r); 0 ise tüm gruplar özdeş
%
%   Age_Q     : yaşlanma, kapasite oranı (1 = yeni hücre; ML demosu için gerçek SOH)
%   Age_R     : yaşlanma, direnç oranı (R0, R1, R2 aynı oranda; kapasitanslar sabit)
%
%   Çıkışlar: V_pack, ortalama hücre SOC'si, sıcaklıklar, OCV_pack,
%             en düşük seri grup gerilimi (V_cell_min) ve zayıf grubun SOC'si.
%
%   Elektriksel: 2-RC Thevenin (ZOH ile kesin ayrıklaştırma)
%   Termal     : 2 düğümlü çekirdek-yüzey modeli (açık Euler; ortalama hücre)
%   Isı        : Bernardi tersinmez kısım, q = i*(OCV - V)
%   Not (kod üretimi): kalıcı değişkenler kendi isempty kontrolleriyle başlatılır.

%#codegen
persistent P S
if isempty(P)
    P = bms_param_struct();
end
if isempty(S)
    S = struct('soc', SOC0, 'v1', 0, 'v2', 0, 'tc', T_amb, 'ts', T_amb, ...
               'soc_w', SOC0, 'v1_w', 0, 'v2_w', 0);
end

dt = P.Ts;
i  = I_pack / P.Np;                                     % hücre akımı (seri gruplarda aynı)

% ---- Ortak sıcaklık etkisi ----
f_T = exp(P.ea_r0 / P.Rgas * (1/(S.tc + 273.15) - 1/298.15));
a1  = exp(-dt / (Age_R * P.r1 * P.c1));
a2  = exp(-dt / (Age_R * P.r2 * P.c2));

% ---- Ortalama (normal) hücre ----
ocv  = interp1(P.soc_tab, P.ocv_tab, min(max(S.soc, 0), 1), 'linear');
r0   = Age_R * P.r0 * f_T * (1 + 0.6 * exp(-S.soc / 0.08));
S.v1 = a1 * S.v1 + Age_R * P.r1 * (1 - a1) * i;
S.v2 = a2 * S.v2 + Age_R * P.r2 * (1 - a2) * i;
v_cell = ocv - r0 * i - S.v1 - S.v2;

% ---- Zayıf seri grup (aynı zaman sabitleri, ölçeklenmiş dirençler) ----
kr     = P.weak_r * Age_R;
ocv_w  = interp1(P.soc_tab, P.ocv_tab, min(max(S.soc_w, 0), 1), 'linear');
r0_w   = kr * P.r0 * f_T * (1 + 0.6 * exp(-S.soc_w / 0.08));
S.v1_w = a1 * S.v1_w + kr * P.r1 * (1 - a1) * i;
S.v2_w = a2 * S.v2_w + kr * P.r2 * (1 - a2) * i;
v_weak = ocv_w - r0_w * i - S.v1_w - S.v2_w;

% ---- Termal (ortalama hücre) ----
q   = i * (ocv - v_cell);
ru  = P.ru * Ru_factor;
dtc = (q + (S.ts - S.tc) / P.rc) / P.cc;
dts = ((T_amb - S.ts) / ru - (S.ts - S.tc) / P.rc) / P.cs;
S.tc = S.tc + dtc * dt;
S.ts = S.ts + dts * dt;

% ---- Coulomb sayımı ----
S.soc   = S.soc   - i * dt / (3600 * P.Q_Ah * Age_Q);
S.soc_w = S.soc_w - i * dt / (3600 * P.Q_Ah * Age_Q * P.weak_cap);

% ---- Çıkışlar ----
w          = double(Weak_on > 0.5);
V_pack     = P.Ns * v_cell + w * (v_weak - v_cell);
SOC        = S.soc;
T_core     = S.tc;
T_surf     = S.ts;
OCV_pack   = P.Ns * ocv + w * (ocv_w - ocv);
V_cell_min = v_cell + w * min(0, v_weak - v_cell);
V_cell_max = v_cell + w * max(0, v_weak - v_cell);   % şarjda zayıf grup en yüksek
SOC_weak   = S.soc + w * (S.soc_w - S.soc);
end
