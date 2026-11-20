# Bitirme: yapılacaklar ve alınacaklar (2026-11-19)

Hedef: batarya odaklı, gerçek veriyle desteklenmiş, geleceğin araçlarına uygun bir BMS
(dijital ikiz + kendini teşhis eden kestirim + mikrodenetleyicide ML + deterministik güvenlik).
Tez yazımı ~2 Aralık'ta başlar. Öncelik sırası: A (güvenlik) > C (doğrulama) > B (özellik).

## Bugüne kadar (18-19 Kasım)
- Uçtan uca demo 7/7, 5 buton = 5 stres senaryosu, senaryo koşturucu (tools/demo_run.py).
- Kartta bulunan ve düzeltilen iki tasarım hatası: soğutma alarmı titremesi (histerezis 18/15 K/W),
  sıcak yeniden başlatmada sahte soğutma alarmı (açılışta 120 s bekleme).
- Gerçek veri: OCV tablosu Kirkaldy 2024 GITT'ten (gerilim hatası 64,7 -> 17,0 mV), R0 doğrulandı,
  R1/R2 veriyle desteklendi, hücreler arası fark gerçek 40 hücreyle doğrulandı.
- PIL referansları artık yeniden üretilebilir (tools/pil_test/sil_ref.py).

## A. Güvenlik ve algoritma (önce)
1. [x] **Isıl gecikme (3. bulgu), 19 Kasım:** LIMP/SAFE artık ayrıca ölçüme bağlı çekirdek sınırıyla
       (T_ss = T_ölç + Rc/Ru (T_ölç - T_ortam) > 55/60 °C, 1 s). Kart A2: LIMP gerçek çekirdek
       55,5 °C, SAFE 60,4 °C (önce 65,9 / 66,4). S1-S7 değişmedi; U14, S8/S9, PIL S8 eklendi.
       İnovasyon CUSUM'u denendi, benimsenmedi: yalnız hızlı dış ısıyı yakalıyor, iç ısıyı
       gözlemci soğutma değişimi gibi yutuyor, yeniden başlatma sonrası 1/3 tohumda sahte alarm.
   [ ] **Yeni (A1'den):** sıcak + soğutması arızalı pakette yeniden başlatma sonrası ısıl gözlemci
       sapıyor (Tc^ ölçümün 7 °C altına); nedeni büyük olasılıkla SOC EKF'nin 0,5'ten başlaması
       (ısı girdisi OCV(SOC^) - V yanlış). SOC'yi açılışta dinlenme OCV'sinden başlatmayı incele.
2. [x] **Ea, 19 Kasım:** Kirkaldy Expt 5 Set 1 ham .mpr (8 hücre, 15/27/40 °C, ~500 MB, git dışı),
       CV -> 5 A basamağı: R0 (0,05 s) 6,2 ± 0,3, R1 (10 s polarizasyon) 17,5 ± 0,8, R2 (30 s)
       14,3 ± 0,5 kJ/mol (veri/ea_kirkaldy.py). Eski varsayım: yalnız R0'a 20 kJ/mol. Dört modele
       uygulandı, tüm testler geçti. O'Regan 2022 tam metni erişilemedi (özet: kinetik Ea'lar
       ~60 kJ/mol'e kadar, nitel olarak uyumlu); tezde tam metinden sayı alınmalı.
   [x] **Kart:** yeni Ea'lı twin_emu ile butonlar.txt 5/5 PASS (soğutma alarmı 121,8 s; A2 LIMP
       gerçek çekirdek 55,6 °C, SAFE 60,5 °C).
   [x] LM35 (20 Kasım): 38-43 °C okuyordu, sensör değiştirildi -> ~25 °C. Sahte sıcak ortam D3'ü
       hızlandırıyordu: soğuk (25 °C) pakette soğutma alarmı kartta 391 s (Python ~490 s; ısı akışı az,
       R_u geç gözlenir), dün 121 s. butonlar.txt D3 beklemesi 300 -> 700 s.
3. [x] **Duyarlılık analizi, 19 Kasım** (twin/sensitivity.py, results/sensitivity.csv/.png): 24
       bozulma x 4 senaryo. Kabul ölçütleri (S2 < 55 °C, S3 >= 2,8 V, S4 <= 4,2 V, yanlış SAFE yok)
       25/25 korunuyor. SOC RMSE (taban %0,29) en çok R0 ±%20 (%0,94 / %2,09), R1, R2 ±%50 (~%1,1-1,7)
       ve OCV ±15 mV (%1,4-1,7); termal parametreler, Ea, kapasite, R_u etkisiz. İki yeni bulgu:
   [x] **A7/A8 düzeltildi (19 Kasım):** EKF'ye R0 ölçeği k_R (5 durum), kayma makullük sınırı 5 -> 8 A;
       T değişim hızı = hızlı süzgeçten (tau 0,3 s) > 2 °C fark, 3 örnek üst üste. Duyarlılık
       analizinde sahte LIMP kalmadı (25/25 durumda %100 NORMAL); R0 x1,2 SOC RMSE %2,09 -> %0,29.
       Python == C (SOC farkı <= 0,0013 puan), MATLAB A + B1-B8 PASS, PIL PASS (bms_step 86 us).
   [x] **LED'ler (kullanıcı, 19 Kasım akşamı):** "LED'ler hep yanıyor, sorun var gibi". O an ECU DERATE,
       kısa far PWM %15,4 (ölçülen de %15,4, 999 Hz), uzun far %0, kontaktör kapalı. Yarın kartta bak:
       %15'te de tam parlak mı görünüyor (algı), PWM gerçekten LED'e ulaşıyor mu (ULN IN1/OUT1, PA8
       TIM1), uzun far hattı, SAFE'te sönüyor mu, kablolama. Gerekirse parlaklık eğrisi (gamma).
       20 Kasım: SAFE'te de yanıyordu (ECU kendi pininde %0 ölçüyordu -> kablolama). LM35 değişimi
       sırasında düzeldi (büyük olasılıkla gevşek kablo). Gama zaten var (seviye^2,5; alt sınır %3,1 PWM).
   [x] **A9 açılış sıfır akım kontrolü (20 Kasım):** ilk 1 s kontaktör açık, I_allow = 0; ölçülen ortalama
       = ofset. EKF b_I bununla başlar (P 0,05 A^2), |ofset| > 3 A -> sensör arızası LIMP (neden 32),
       ofset yine telafi edilir. Tarama (twin/bias_sweep.py, results/bias_sweep.png): tespit süresi
       hiç / 1000-1660 s -> 0,9 s; S1 SOC RMSE ±3 A içinde %0,29-0,30 (önce %0,14-0,83), büyük ofsette
       %0,5 (önce %1,0-2,2). Python == C == MATLAB, U15, PIL girdileri kapalı çevrimden yeniden
       üretildi (tools/pil_test/make_pil_inputs.py; C13 de kapandı), PIL PASS (86 us).
       Sınır: sürüş sırasında sonradan oluşan kaymayı yine yalnız yavaş EKF görür.
   [ ] (eski) **A7 Sahte akım sensörü teşhisi:** direnç uyumsuzluğunda (R0 ±%20, R1 x1,5, τ2 x0,5) EKF farkı
       akım kayması b_I'ya yüklüyor, |b_I| > 5 A -> neden 32 LIMP (S1'in %11-36'sı). Yaşlanmış pakette
       olur. Aday: çevrimiçi direnç kestiricisinin (rr) R0'ı EKF'ye vermesi (uyarlamalı R0) ve/veya
       kayma sınırını ayrı bir doğrulamaya bağlamak.
   [ ] **A8 Sıcaklık değişim hızı teşhisi gürültüye dar:** σ 0,6 °C'de ardışık fark > 2 °C/örnek
       sıçramaları kalıcı "T geçersiz" -> sürüşün tamamı LIMP. Aday: 2 ardışık örnek şartı ya da
       filtrelenmiş hız; gerçek NTC + ADC gürültüsü ölçülünce (B9) eşiği doğrula.
4. [ ] **SOC farkı 0,75-1,0 puan** (kartta): 19 grup / tek ortalama mı, başka bir şey mi, incele.
5. [ ] **Zayıf grup -%5 kapasite:** yeni hücre saçılmasının dışında (-%0,8) -> yaşlanma modeliyle
       "yaşlanmış grup" gerekçesi ya da değeri gerçekçi aralığa çek.
6. [ ] **Sensör gürültüsü kaynakları:** gerçek parça veri sayfaları (Hall akım sensörü, NTC, AFE
       çipi BQ76952/LTC6811) ile karşılaştır; donanım gelince ölç.

## B. Özellikler (geleceğin BMS'i)
7. [ ] **SOH (ML) görünür:** LCD'de "SOH %xx (ML)", demoda mikrodenetleyicide ML.
8. [ ] **Öngörülü uyarı:** ECU ısıl modelini ileri simüle edip "bu yükle N dk sonra kısıtlama".
9. [ ] **Gerçek ısıl düzenek** (alınacaklar 1): güç direnci + NTC + fan; Uno ölçer, 0x101'in T'si
       gerçek sensörden; fanı durdurmak = gerçek soğutma arızası, ECU R_u'yu gerçek fizikten bulur.
10. [ ] **Gerçek akım ölçümü** (alınacaklar 2): INA226 + küçük yük; bias/gürültü gerçek veride.
11. [ ] **Bağımsız analog koruma** (alınacaklar 3): LM393 ile yazılımdan bağımsız ikinci katman.
12. [ ] **Sürücü uyarısı:** buzzer (DERATE kısa bip, SAFE sürekli).
12b. [ ] **Çok kriterli stres indeksi Ψ (ÖNEMLİ, tez başlığı; 20 Kasım tasarım taslağı, kullanıcı onayı bekliyor):**
       bugün Ψ = max(Ψ_T, Ψ_C). Önerilen ek alt indeksler: Ψ_Ṫ (dT/dt 3→10 °C/dk, tavan 0,5),
       Ψ_I (I²t %70→100, 0,3), Ψ_H (EKF k_R 1,2→1,6, 0,3), Ψ_B (ΔV 30→100 mV düşük akımda, 0,2),
       Ψ_U (σ_SOC %3→8, 0,2). Birleştirme Ψ = min(1, Ψ_max + κ(ΣΨᵢ − Ψ_max)), κ = 0,25; baskın
       kriter raporlanır. Açık: eşikler, κ, 0x201 cause baytı dolu (baskın kriter 0x202 d[6] üst
       4 bit?), k_R SOP direncine de bağlansın mı. Sıra: Python → MATLAB → C → SIL/PIL → MC 1000
       (sahte kısma yok) → kart → figür.

## C. Doğrulama, demo, belge
0. [x] **Kart üstü Monte Carlo (20 Kasım):** APP_MC = 8, 1000 rastgele kapalı çevrim koşusu (600 s, ikiz +
       bms_step aynı STM32'de, 623x gerçek zaman, 16 dk). 1000/1000 PASS; kart == PC hüküm 1000/1000, tüm
       alanlar 991/1000 (kalan 9: SOC hatasının son hanesi). Dış ısıda LIMP gerçek çekirdek 54,1-55,4 °C,
       SAFE 59,2-60,4 °C. results/mc_overview.png, mc_summary.txt. Sıradaki: UART telemetri + gateway.
13. [x] (20 Kasım, A9 ile) PIL girdi senaryolarını (tools/pil_test/data/*_in.csv) yeni OCV'li ikizle yeniden üret.
14. [ ] can_replay testi (mcp2515_bridge) güncel kodla.
15. [ ] FMEA tablosu (tez eki): bugünkü arıza enjeksiyonlarının hepsi sistemli.
16. [ ] Parametre tablosuna "kaynak / ölçüm / varsayım" sütunu (plan/parametre_tablosu.tex).
17. [ ] Demo videosu: 5 buton, karanlık oda, pozlama kilitli, soğutma için ECU önce resetli.
18. [ ] Figürlerin İngilizce son hali; GitHub'a push (onayla).
19. [ ] Tez yazımı (bulgular listesi hazır), sunum 12-14 slayt, jüri provası.

## Alınacaklar
Uno'da boş kalanlar: A0 (pot artık kullanılmıyor), D6-D9, I2C (LCD ile ortak).

| # | Parça | Adet | Ne için | Uno bağlantısı |
|---|---|---|---|---|
| 1 | 10 Ω 10 W alüminyum gövdeli güç direnci | 2 | Isıl düzenek: "hücre" ısı kaynağı | MOSFET üzerinden |
| 1 | 10 kΩ NTC termistör (B3950, epoksi boncuk) | 3 | Gerçek yüzey sıcaklığı (+ yedek) | A0 (10 kΩ bölücüyle) |
| 1 | 5 V fan 40x40 mm | 1 | Soğutma; durdurmak = gerçek soğutma arızası | D6 (transistör/ULN) |
| 1 | Mantık seviyeli MOSFET (IRLZ44N) + 220 Ω + 10 kΩ | 1 | Direnci PWM ile ısıtmak | D9 |
| 1 | 12 V 2 A adaptör | 1 | Direnç gücü (~10 W) | ortak GND |
| 1 | Termal macun / ısıl yapıştırıcı, küçük alüminyum plaka | 1 | NTC'yi dirence sabitlemek, ısıl kütle | — |
| 2 | INA226 modülü (şönt dahil) | 1 | Gerçek akım ve gerilim ölçümü | I2C (A4/A5) |
| 2 | Küçük yük: 5 W direnç ya da ikinci güç direnci | 1 | INA226'dan akım geçirmek | — |
| 3 | LM393 (IC ya da modül) + 10 kΩ trimpot | 2 | Bağımsız analog aşırı sıcaklık koruması | röle hattına |
| 4 | Aktif buzzer 5 V | 1 | Sürücü uyarısı | D7 |
| — | Jumper kablo, küçük breadboard | — | Gevşek 5 V hattı sorununu önlemek için sağlam besleme | — |

Güvenlik: güç direnci 80-100 °C'ye çıkabilir; ahşap/plastik üstüne koyma, el sürme, ilk denemede
PWM'i düşük tut. Gerçek lityum hücre kullanılmıyor (masada risk; Kirkaldy verisi yerini tutuyor).
