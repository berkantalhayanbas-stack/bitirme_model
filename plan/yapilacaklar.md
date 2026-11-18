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
1. [ ] **Isıl gecikme (3. bulgu):** aşırı ısınmada kestirim gerçeğin 11 °C gerisinde, SAFE gerçek
       çekirdek 66 °C'de geldi. (a) LIMP/SAFE için max(Tc_hat, ölçülen T); (b) inovasyon tabanlı
       "açıklanamayan ısı" anomali bayrağı -> önleyici LIMP. C + Python + MATLAB + testler + kart.
2. [ ] **Ea:** galvani paketi + Kirkaldy ham .mpr (10/25/40 °C, ~170 MB) -> akım basamaklarından
       R(T) -> Ea uydurma; O'Regan 2022 ile karşılaştırma.
3. [ ] **Duyarlılık analizi:** R_u, sensör gürültüsü, grup farkı, R2/τ2 ±%50 -> SOC hatası ve
       kararlar ne kadar değişiyor (tez tablosu).
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

## C. Doğrulama, demo, belge
13. [ ] PIL girdi senaryolarını (tools/pil_test/data/*_in.csv) yeni OCV'li ikizle yeniden üret.
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
