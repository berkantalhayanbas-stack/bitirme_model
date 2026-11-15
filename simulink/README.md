# Simulink: 19S12P Dijital İkiz + EKF (R2025b, sadece Simulink gerekli)

## Kurulum (3 komut)
Bu klasörü MATLAB'da "Current Folder" yap, sonra:
```matlab
build_bms_model      % bms_twin_ekf.slx modelini otomatik kurar ve kaydeder
run_and_compare      % simülasyonu koşturur, Python ile karşılaştırır, grafik çizer
```

## Dosyalar
| Dosya | Görev |
|---|---|
| `bms_param_struct.m` | Tüm parametreler (hücre, termal, OCV, EKF, sensör). **Değiştirmen gereken tek dosya.** |
| `battery_twin.m` | Dijital ikiz adım fonksiyonu (2-RC + 2 düğüm termal + Bernardi). MATLAB Function bloğu bunu çağırır. |
| `ekf_soc.m` | 4 durumlu EKF (SOC, V1, V2, akım kayması), R0(T) düzeltmeli. |
| `bms_init.m` | Sürüş çevrimini ve senaryo değişkenlerini workspace'e yükler. |
| `build_bms_model.m` | Modeli bloklarıyla ve bağlantılarıyla sıfırdan kurar. |
| `current_limiter.m` | Sürücü talebini BMS'in izin verdiği akımla kırpar (3. haftada karar mekanizmasına bağlanacak). |
| `test_week1_extras.m` | Sınırlayıcı ve zayıf hücre kabul testleri. |
| `scenarios.m` | 6 senaryoluk kütüphane: normal, sıcak gün, fan arızası, agresif, derin deşarj, uzun şarj. |
| `run_and_compare.m` | Simülasyon, Python çapraz doğrulaması, EKF KPI raporu, grafikler. |
| `twin_reference.csv` | Python dijital ikizinin çıktısı (10 Hz, 24 940 satır). |

## Beklenen çıktı
- Simulink vs Python farkı: V_pack için mV'un çok altında olmalı. Aynı denklemler, aynı ayrıklaştırma.
- EKF: RMSE yaklaşık %0.2-0.4 (gürültü tohumları Python'dan farklı olduğu için birebir aynı çıkmaz), yakınsama 60 s civarı.

## Senaryo kütüphanesi (1. hafta)
```matlab
build_bms_model    % SOC0 girişi eklendi; bir kez yeniden kurulmalı
scenarios          % 6 senaryo, özet tablo, sonuclar/*.png, senaryo_sonuclari.mat
```

## Akım sınırlayıcı ve zayıf hücre (1. hafta ekleri)
```matlab
build_bms_model       % Current_Limiter bloğu ve Weak_on girişi eklendi
test_week1_extras     % A) sınırlayıcı testi, B) zayıf hücre testi; PASS/FAIL raporu
```
Workspace değişkenleri (bms_init varsayılanları): `I_allow_dis = 87.3`, `I_allow_chg = 40.7`, `Weak_on = 0`.

## Çekirdek sıcaklığı gözlemcisi (2. hafta)
```matlab
build_bms_model         % Thermal_Observer bloğu eklendi
test_thermal_observer   % 3 senaryo, 4 yöntem karşılaştırması, soğutma arızası algılama
```
`thermal_obs_step.m` durumsuz çekirdek (C'ye çevrilecek), `thermal_observer.m` blok sarmalayıcısı.

## Sensör arıza kütüphanesi ve teşhis (2. hafta)
```matlab
build_bms_model         % Fault_Injector, Sensor_Diag, EKF inovasyon kapısı eklendi
test_sensor_faults      % 5 arıza x teşhis kapalı/açık + 6 senaryoda yanlış alarm kontrolü
```
Workspace değişkenleri: `Fault_mode` (0 yok, 1 v_spike, 2 i_frozen, 3 t_open, 4 t_frozen, 5 i_offset),
`Fault_t = 1200` s, `Diag_on = 1`.

## ML ile SOH tahmini (2. hafta)
```matlab
build_bms_model     % Rint_Estimator, SOH_ML blokları; ikize ve EKF'ye yaşlanma girişleri eklendi
test_ml_soh         % 4 yaşlanmış hücre x (3 öğrenme + 3 değerlendirme sürüşü) = 24 simülasyon
```
`soh_tree.m` elle düzenlenmez; `ml/04_model_aktar.py` üretir. Workspace değişkenleri:
`Age_Q, Age_R` (ikizin gerçek yaşlanması), `Bms_Q, Bms_R` (BMS'in bildiği), `Rint_num0, Rint_den0`
(önceki sürüşlerin birikimi), `Usage` (BMS ömür sayaçları), `seed_v, seed_i, seed_t`.

## Karar mekanizması (3. hafta)
```matlab
build_bms_model     % Decision bloğu + Unit Delay -> Current_Limiter (kapalı çevrim); V_cell_max ölçümü
run_and_compare     % Dec_on = 0 varsayılan: sonuçlar eskisiyle birebir aynı olmalı
test_decision       % A) 6250 birim test vektörü (Python ile birebir) + B) 7 senaryo, 11 simülasyon
```
`decision_logic.m` mantığın kendisi; `decision_vectors.csv` Python'un (`twin/test_decision_unit.py`)
ürettiği test girdileri ve beklenen çıktılar. Workspace: `Dec_on` (0/1), `sig_vc`, `lsb_vc`,
`seed_vmin`, `seed_vmax`. Tek senaryoda açmak için: `bms_init; Dec_on = 1; out = sim('bms_twin_ekf');`

## CAN alım izleyicisi (4. hafta)
```matlab
build_bms_model     % CAN_Rx bloğu: kuantalanmış ölçümler -> 0x101/0x102 alımı -> BMS; CAN_ok sabiti kalktı
test_can_monitor    % A) 3119 olaylık birim test vektörü (Python ile birebir) + B) 7 kapalı çevrim CAN arızası
```
`can_monitor_init/_rx/_tick.m` STM32'deki `bms_can.c` izleyicisinin birebir karşılığı (CRC, 4 bitlik
alive counter, zaman aşımı: 250 ms fault, 500 ms SAFE kalıcı, açılışta 2 s). `can_rx.m` ECU alım katmanı:
kabul edilmeyen mesajda ölçüm son geçerli değerde tutulur, `CAN_ok` -> Decision. Python: `twin/can_monitor.py`,
vektörler `twin/test_can_monitor.py` ile üretilir (`can_monitor_vectors.csv`).
Workspace: `Can_mode` (0 yok, 1 çerçeve kaybı, 2 CRC bozuk, 3 donmuş sayaç), `Can_msg` (1 = 0x101,
2 = 0x102, 3 = ikisi), `Can_t` başlangıç [s], `Can_dur` süre [s] (`Inf` = sona kadar).
`Can_mode = 0` (varsayılan) iken sonuçlar eski `CAN_ok = 1` modeliyle birebir aynıdır.
Etkin tolerans (sayaç kuralı MAX_DELTA = 3 ile birlikte, bilinçli seçim): 1-3 ardışık kayıp yalnız
fault; 4 ve üstünde dönüş çerçevesi de sıra hatası olarak reddedildiği için 500 ms dolar -> SAFE-STOP.
Örnek: `bms_init; Dec_on = 1; Can_mode = 1; Can_msg = 1; Can_t = 600; Can_dur = 0.5; out = sim('bms_twin_ekf');`

## Tek senaryo denemesi (modeli yeniden kurmadan)
```matlab
bms_init; T_amb = 35; Ru_factor = 4;   % sıcak gün + fan arızası
out = sim('bms_twin_ekf');
```
Not: `run_and_compare` başta `bms_init` çağırdığı için senaryo değişkenlerini sıfırlar. Senaryo denemelerinde `sim` komutunu doğrudan kullan.

## Tasarım notları
- Bloklar ince sarmalayıcı; asıl kod `.m` dosyalarında. Hem okunur hem de sonra Embedded Coder ile ya da elle C'ye taşınması kolay.
- EKF'ye giden ölçümler CAN 0x101 çözünürlüğünde kuantalanıyor (0.1 V / 0.1 A / 0.1 °C). HIL'e geçince hiçbir şey değişmeyecek.
- Dijital ikiz OCV için tablo kullanıyor, EKF ise polinom kullanıyor. Bu bilinçli bir model uyumsuzluğu: kestiriciyi kendi modelinden üretilmiş veriyle test etmenin ("inverse crime") yarattığı yapay iyimserliği önler.
