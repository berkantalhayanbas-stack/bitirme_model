function P = bms_param_struct()
%BMS_PARAM_STRUCT  19S12P LG 21700 dijital ikiz + EKF parametreleri.
%   Tüm MATLAB Function blokları parametreleri buradan okur
%   (kod üretimiyle uyumlu, workspace bağımlılığı yok).
%   Python referansı: twin/battery_model.py ile birebir aynı değerler.
%   Kaynaklar (ayrıntı: plan/parametre_tablosu.tex):
%     veri sayfası: LG INR21700 M50T (Rev 0, 2018-07-16); R0, R1: Kirkaldy vd. (2024) BoL;
%     OCV: Kirkaldy vd. (2024) GITT (veri/ocv_gitt.py; önceki Chen vd. 2020)

%#codegen
P.Ts    = 0.1;          % örnekleme zamanı [s] (STM32'de 10 ms'ye inecek)

% ---- Paket yapısı ----
P.Ns    = 19;
P.Np    = 12;

% ---- Hücre (LG INR21700 M50T, başlangıç değerleri; etiket doğrulandı) ----
P.Q_Ah  = 4.85;         % hücre kapasitesi [Ah] (veri sayfası min.; Kirkaldy C/10: 4.857)
P.v_max = 4.20;         % veri sayfası şarj sonu gerilimi
P.v_min = 2.80;         % tasarım alt sınırı (veri sayfası 2.5 V)
P.i_max_dis = 7.275;    % sürekli deşarj [A/hücre] (1.5C, 25-55 °C)
P.i_max_chg = 3.395;    % maks. şarj [A/hücre] (0.7C, 25-45 °C; 0-25 °C'de 0.3C)
% Veri sayfası sıcaklığa bağlı sürekli akım sınırları (3. hafta karar mekanizması kullanacak):
%   şarj  : 0-25 °C 0.3C (1.455 A), 25-45 °C 0.7C (3.395 A), diğer: yasak
%   deşarj: -20-10 °C 0.5C (2.425 A), 10-25 °C 3.0C (14.55 A, yeni revizyon), 25-55 °C 1.5C (7.275 A)
P.lim_T_chg   = [0 25 45];          % [°C] şarj bölge sınırları
P.lim_I_chg   = [1.455 3.395];      % [A/hücre]
P.lim_T_dis   = [-20 10 25 55];     % [°C] deşarj bölge sınırları
P.lim_I_dis   = [2.425 7.275 7.275];% [A/hücre] 10-25 °C'de muhafazakâr olarak 1.5C kullanıldı
P.r0    = 0.0264;       % [Ohm] Kirkaldy R(0.1 s), %52 SOC, 25 °C
P.r1    = 0.0093;  P.c1 = 1075;     % R(10 s)-R(0.1 s) = 6.54 mOhm kısıtından; tau1 = 10 s
P.r2    = 0.012;   P.c2 = 15000;    % tau2 = 180 s
% Arrhenius aktivasyon enerjileri [J/mol]: Kirkaldy 2024 Expt 5 ham döngü verisi, 8 hücre 15-40 °C,
% 5 A basamağı (veri/ea_kirkaldy.py): R0 = 0.05 s ohmik, R1 / R2 = 10 s / 30 s polarizasyonu
P.ea_r0 = 6200;  P.ea_r1 = 17500;  P.ea_r2 = 14300;
P.Rgas  = 8.314;

% ---- Zayıf seri grup (Weak_on = 1 iken; 1 / 19 grup) ----
% Yaşlanma: direnç oranı = 1 + age_beta (1 - SOH) (Kirkaldy 40 hücre, veri/age_resistance.py;
% bms_ecu TW_AGE_BETA, twin/battery_model.py AGE_BETA ile aynı). bms_init: Age_R = 1 + P.age_beta*(1 - Age_Q)
P.age_beta = 1.31;
P.weak_cap = 0.90;      % kapasite oranı (%10 düşük)
P.weak_r   = 1.20;      % direnç oranı (%20 yüksek)

% ---- Termal (2 düğüm: çekirdek-yüzey) ----
P.cc    = 64;           % [J/K] (toplam 69 J/K: 69 g x ~1000 J/(kg K))
P.cs    = 5;            % [J/K]
P.rc    = 1.8;          % [K/W]
ru_nom  = 9.0;          % yerel değişken: aşağıda gözlemci ayarında da kullanılıyor
P.ru    = ru_nom;       % [K/W]

% ---- Çekirdek sıcaklığı gözlemcisi (x = [Tc Ts g], g = 1/Ru) ----
P.th_P0    = [1.0 0.1 (1/ru_nom)^2];  % g için ±%100 başlangıç belirsizliği
P.th_Q     = [1e-4 1e-4 1e-9];        % g rastgele yürüyüşü: yavaş değişen soğutma
P.th_R     = 0.3^2 + 0.1^2/12;        % NTC gürültüsü + CAN kuantalaması [°C^2]
P.th_g_min = 0.2 / ru_nom;            % fiziksel alt sınır (g > 0)

% ---- Termal anomali dedektörü (açıklanamayan ısı; thermal_anomaly_step.m, C: bms_config.h TA_*) ----
P.ta_win     = 1200;     % 120 s kaydırmalı pencere [örnek]
P.ta_age_min = 100;      % zarf en az 10 s yaşlı [örnek]
P.ta_r_th    = 1.5;      % [°C] süzülmüş ölçüm - adyabatik zarf
P.ta_n       = 10;       % 1 s
P.ta_alpha   = 0.1;      % ölçüm süzgeci (~1 s)
P.ta_q_k     = 1.5;      % bilinen ısı payı
P.ta_q_off   = 0.2;      % [W/hücre]
P.ta_tc0     = 1.0;      % [°C] zarf başlangıç payları
P.ta_ts0     = 0.5;
P.ta_g_max   = 4 / ru_nom;   % ortam yüzeyden sıcaksa en güçlü ısıtma

% ---- OCV-SOC tablosu: Kirkaldy vd. (2024) LG M50T GITT dinlenme sonu gerilimleri (BoL, 25 °C; veri/ocv_gitt.py, hücre A-D, E-H'de doğrulandı) ----
P.soc_tab = [0 0.02 0.05 0.10 0.15 0.20 0.25 0.30 0.35 0.40 0.45 0.50 ...
             0.55 0.60 0.65 0.70 0.75 0.80 0.85 0.90 0.95 0.98 1.00];
P.ocv_tab = [2.9414 3.0161 3.1444 3.2871 3.4047 3.4646 3.5055 3.5621 3.6086 3.6418 3.6729 3.7119 ...
             3.7594 3.8136 3.8737 3.9207 3.9641 4.0162 4.0619 4.0873 4.1120 4.1519 4.1845];

% ---- OCV polinomu (EKF kullanır; 7. derece, SOC >= 0.05, tabloya en büyük hata 11,6 mV) ----
% (Kod üretimi kuralı: yapı okunduktan sonra yeni alan eklenemez,
%  bu yüzden türev önce yerel değişkenle hesaplanır.)
ocv_poly    = [60.3790948991, -208.990896881, 295.06003585, -224.987541467, ...
               104.426799217, -30.805913718, 6.20417948038, 2.89779228523];
P.ocv_poly  = ocv_poly;
P.docv_poly = ocv_poly(1:7) .* [7 6 5 4 3 2 1]; % analitik türev

% ---- Başlangıç koşulları ----
P.soc0      = 0.80;     % gerçek SOC
P.soc0_ekf  = 0.50;     % EKF'ye bilerek yanlış başlangıç

% ---- EKF ayarları (x = [SOC V1 V2 b_I]) ----
P.ekf_P0 = [0.1 0.01 0.01 1.0 0.01];   % son durum k_R (R0 ölçeği): ±%10 başlangıç belirsizliği
P.ekf_Q  = [1e-10 1e-6 1e-6 1e-8 1e-8];
P.ekf_kr_min = 0.5;  P.ekf_kr_max = 2.0;
P.ekf_kr_freeze = 120;  % [s] açılışta k_R kazancı 0 (SOC yakınsıyor; kart buton testi 2026-11-21)
P.ekf_p_b0 = 0.05;     % [A^2] sıfır akım kalibrasyonu sonrası kayma belirsizliği
P.ekf_R  = 0.25^2;      % paket gerilim ölçüm varyansı [V^2]
P.ekf_gate  = 10;       % normalize inovasyon kapısı [sigma] (EMI sıçramalarını reddeder)
P.ekf_n_rej = 5;        % 5 örnek üst üste red -> model yanlış, kapı açılır

% ---- Sensör teşhisi (CAN 0x101 değerleri üzerinde) ----
P.diag_T_min    = -30;  % [°C] altı: kopuk NTC (ADC skala sonu)
P.diag_T_max    = 85;   % [°C] üstü: kısa devre NTC
P.diag_T_rate   = 2.0;  % [°C] ölçümün hızlı süzgeçten farkı (3 örnek üst üste) -> imkânsız değişim
P.diag_T_alpha  = 0.28; % 1 - exp(-0.1 / 0.3 s)
P.diag_n_rate   = 3;
P.diag_n_frozen = 50;   % 50 örnek (5 s) aynı değer -> donmuş sensör

% ---- Çevrimiçi direnç kestiricisi (ML SOH modelinin girdisi) ----
P.rint_di_min  = 20;    % [A] olay eşiği: 0.1 s'de en az 20 A akım basamağı
P.rint_soc_min = 0.2;   % düşük SOC'de direnç hızla değişir, olay sayılmaz
P.rint_lam     = 0.999; % unutma çarpanı (~1000 olay hafıza = birkaç sürüş)

% ---- Karar mekanizması (decision_logic.m; Python: twin/decision.py) ----
% Veri sayfası sürekli akım sınırları [A/hücre], 2 °C'lik geçişlerle (sınır sıcaklığı üst bölgede)
P.dec_T_dis = [-20 -18 8 10 53 55];   P.dec_I_dis = [0 2.425 2.425 7.275 7.275 0];   % 0.5C / 1.5C
P.dec_T_chg = [0 2 23 25 43 45];      P.dec_I_chg = [0 1.455 1.455 3.395 3.395 0];   % 0.3C / 0.7C
P.dec_T_der_on   = 45;    % [°C] sıcaklık kısıtlaması başlar (T_core kestirimi)
P.dec_T_der_off  = 43;    % [°C] altına inince kalkar (histerezis); Ψ 43->55 °C doğrusal
P.dec_T_der_full = 55;
P.dec_psi_cool   = 0.3;   % soğutma alarmında önleyici kısıtlama
% çok kriterli stres indeksi: Ψ = min(1, Ψ_max + κ (ΣΨ_i - Ψ_max)), Ψ_i = [T C Tdot H]
P.dec_td_a_f     = 0.02;      % Ψ_Tdot: ölçülen yüzey T'nin 5 s alçak geçireni (ts/5)
P.dec_td_a_r     = 1/300;     %   artış hızının 30 s alçak geçireni (ts/30)
P.dec_tdot_on    = 3;     % [°C/dk] Ψ_Tdot başlar (nominal MC en çok 2,3 °C/dk)
P.dec_tdot_full  = 10;    % [°C/dk] tavana ulaşır
P.dec_psi_tdot   = 0.5;   % Ψ_Tdot tavanı
P.dec_kr_on      = 1.2;   % Ψ_H: EKF R0 ölçeği k_R (nominal MC 0,89-1,10)
P.dec_kr_full    = 1.3;   % SOH ~%80 (ömür sonu; veri/age_resistance.py, EKF +%3-4)
P.dec_soh_on     = 0.90;  % Ψ_H: kapasite SOH 90 -> 70 % (k_R ile büyüğü; gösterge)
P.dec_soh_full   = 0.70;
P.dec_kr_sop_max = 2.0;   % SOP direnci R0 · clip(k_R, 1, 2) · Arrhenius(T)
% Ψ toplama: olasılıksal VEYA, Ψ = 1 - Π(1 - Ψ_i) (ayar sabiti yok; eski κ kaldırıldı)
% Ψ_A yaşlanma hızı (stress_model.m, twin/decision.py ile aynı): log2(R)/3, takvim 2x'te başlar
P.dec_age_log2_full = 3.0;
P.dec_age_cal_onset = 2.0;
P.dec_age_i_ref     = 2.425;   % 0,5C [A/hücre]
P.dec_age_floor     = 1.455;   % 0,3C [A/hücre] şarj tabanı
P.dec_age_i_min     = 2.0;     % [A] yön ölü bandı
P.dec_age_a         = 0.1 / 60.0;
P.dec_age_s_ref     = 3.3563718;   % S(25 °C, 0,5, 1) (ml/07_stress_model.py)
P.dec_cal_c1 = 7.543;  P.dec_cal_c0 = -23.75;  P.dec_cal_sc = 1e6;  P.dec_cal_ea = 6976.0;   % Schmalstieg 2014
% Ψ_B grup dengesizliği (gösterge)
P.dec_bal_i_max = 2.0;  P.dec_bal_a = 0.01;  P.dec_imb_on = 0.050;  P.dec_imb_full = 0.150;
P.dec_ru_alarm   = 18;    % [K/W] 2 x nominal R_u
P.dec_ru_alarm_off = 15;  % [K/W] altına inince kalkar (histerezis)
P.dec_t_cool_blank = 120; % [s] açılıştan sonra soğutma alarmı yok (gözlemci yakınsaması)
P.dec_v_lim_dis  = 2.90;  % [V] gerilim payı sınırları (SOP), tasarım sınırı 2.8 V'un üstünde
P.dec_v_lim_chg  = 4.18;
P.dec_k_sop      = 0.3;   % SOP geri besleme kazancı
P.dec_band_on    = 0.90;  % kapasite/veri sayfası oranı < 0.90 -> neden; >= 1.00 -> kalkar
P.dec_band_off   = 1.00;
P.dec_floor      = 0.25;  % LIMP-HOME taban akımı (nominalin %25'i, lamba asla sönmez)
P.dec_T_limp     = 55;    % [°C]
P.dec_T_safe     = 60;    % [°C] SAFE-STOP
P.dec_k_ss       = 1.8 / 9;   % Rc / Ru_nom: ölçüme bağlı çekirdek sınırı T_ss = Tm + k (Tm - Ta)
P.dec_soc_empty  = 0.03;
P.dec_v_safe_lo  = 2.50;  % [V] veri sayfası kesme gerilimi, 1 s süre filtresi
P.dec_v_safe_hi  = 4.25;  % [V] veri sayfası aşırı gerilim koruması
P.dec_t_hard     = 1.0;   % [s]
P.dec_te_i_max   = 2.0;   % [A] termal olay (SAFE'ten sonra): akım yok sayılır
P.dec_te_rate    = 1.0;   % [°C/dk] süzülmüş yüzey artış hızı
P.dec_te_wait    = 900;   % [örnek] anomalisiz yolda ısı dengelenmesi beklemesi (90 s)
P.dec_te_n       = 10;    % [örnek] 1 s
P.dec_bias_max   = 8.0;   % [A] akım kayması makullük sınırı (5 A: direnç uyumsuzluğunda sahte LIMP, A3)
P.dec_t_exit_derate = 10; % [s] gevşetici yönde bekleme
P.dec_t_exit_limp   = 10;
P.dec_ramp_up    = 10;    % [A/s] I_allow artış hızı; düşüşler anında
P.dec_t_zero     = 1.0;   % [s] açılış sıfır akım kontrolü (A9): kontaktör açık, I_allow = 0
P.dec_zero_max   = 3.0;   % [A] |ofset| üstü: akım sensörü arızası (LIMP); altı: EKF kayması başlar

% ---- Arıza enjeksiyonu (test) ----
P.fault_spike   = 8.0;  % [V] EMI sıçraması
P.fault_period  = 300;  % [örnek] sıçrama aralığı (30 s)
P.fault_i_off   = 3.0;  % [A] akım ofset kayması

% ---- Sensör hata modeli (CAN 0x101 kuantalaması dahil) ----
P.sig_v  = 0.25;   P.sig_i = 0.5;   P.bias_i = 0.5;   P.sig_t = 0.3;
P.lsb_v  = 0.1;    P.lsb_i = 0.1;   P.lsb_t  = 0.1;

% ---- CAN alım izleyicisi (can_monitor_*.m; STM32: bms_can.h, Python: twin/can_monitor.py) ----
P.can_t_fault_ms  = 250;   % 2 periyot kaçırıldı -> arıza bayrağı (kendiliğinden kalkar)
P.can_t_safe_ms   = 500;   % 5 periyot -> CAN_ok = 0 -> SAFE-STOP (kalıcı)
P.can_t_first_ms  = 2000;  % açılış: ilk geçerli mesaj için süre (AUTOSAR "first timeout")
P.can_max_delta   = 3;     % alive counter farkı 2..3: kayıp çerçeve ama kabul; > 3: dizi hatası
P.can_counter_mod = 16;    % 4 bitlik alive counter
end
