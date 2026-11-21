%BMS_INIT  Simülasyon girdilerini base workspace'e yükler.
%   build_bms_model.m bunu otomatik çağırır.

P  = bms_param_struct();
Ts = P.Ts;

% Sürüş çevrimi: Python dijital ikizinin kullandığı akım profili (10 Hz)
ref      = readtable('twin_reference.csv');
drive_ts = timeseries(ref.i_pack, ref.t, 'Name', 'I_pack');
t_stop   = ref.t(end);

% Senaryo ayarları (modeli yeniden kurmadan değiştirilebilir)
T_amb     = 25;   % ortam sıcaklığı [°C]
Ru_factor = 1;    % 1 = normal soğutma, >1 = soğutma arızası
SOC0      = P.soc0; % gerçek başlangıç SOC'si
Weak_on   = 0;      % 1: bir seri grup zayıf (kapasite -%10, direnç +%20)

% BMS'in izin verdiği akımlar (3. haftada karar mekanizması belirleyecek)
I_allow_dis = P.i_max_dis * P.Np;   % 87.3 A (veri sayfası 1.5C)
I_allow_chg = P.i_max_chg * P.Np;   % 40.7 A (veri sayfası 0.7C)

% Sensör arıza enjeksiyonu (0 = arıza yok; 1..5: fault_injector.m)
Fault_mode = 0;
Fault_t    = 1200;  % arıza anı [s]
Diag_on    = 1;     % 1: sensör teşhisi ve EKF inovasyon kapısı açık

% Yaşlanma: ikizin gerçek durumu (Age_*) ve BMS'in bildiği (Bms_*); yeni hücre = 1.
% Yalnız SOH biliniyorsa direnç oranı veriden: Age_R = 1 + P.age_beta * (1 - Age_Q)
Age_Q = 1;  Age_R = 1;
Bms_Q = 1;  Bms_R = 1;
% Çevrimiçi direnç kestiricisi: önceki sürüşlerden saklanan birikimler (0 = hiç sürüş yok)
Rint_num0 = 0;  Rint_den0 = 0;
% BMS ömür sayaçları: [eşdeğer tam çevrim, gün, ort. sıcaklık °C, ort. SOC, tipik DoD]
Usage = [0 0 25 0.5 1];
% Gürültü tohumları (farklı sürüşler için değiştirilebilir)
seed_v = 11;  seed_i = 22;  seed_t = 33;

% Karar mekanizması: 0 = kapalı (sabit I_allow; eski testler birebir aynı kalır), 1 = kapalı çevrim
Dec_on = 0;
% CAN alımı (can_rx.m): CAN_ok artık izleyiciden gelir. Arıza enjeksiyonu (0 = yok):
%   Can_mode 1 çerçeve kaybı, 2 CRC bozuk, 3 donmuş alive counter;  Can_msg 1 = 0x101, 2 = 0x102, 3 = ikisi
Can_mode = 0;  Can_msg = 3;  Can_t = 600;  Can_dur = Inf;   % Can_t başlangıç [s], Can_dur süre [s]
% Hücre gerilimi ölçümü (CAN 0x102: en düşük/en yüksek seri grup)
sig_vc = 0.005;  lsb_vc = 0.001;  seed_vmin = 44;  seed_vmax = 55;

% Sensör gürültü parametreleri (Random Number blokları kullanır)
sig_v = P.sig_v;  sig_i = P.sig_i;  sig_t = P.sig_t;  bias_i = P.bias_i;
lsb_v = P.lsb_v;  lsb_i = P.lsb_i;  lsb_t = P.lsb_t;
