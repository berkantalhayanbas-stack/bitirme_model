# Araç BMS dosyalarının analizi (OneDrive zip, 11 Kasım 2026)

Kaynak: bataryası alınan elektrikli aracın BMS çalışma klasörü ("BMS ve Batarya Paketleme", 17 dosya, 146 MB).
Amaç: işimize yarayanları bulmak, hataları düzeltmek, projeye neyin alınacağını belirlemek.

## 1. İçerik envanteri
| Dosya | Ne | Durum |
|---|---|---|
| Works/BMS .docx | Entegre seçimi notları + analog dengeleyici açıklaması + 3 görsel (kitap şekli ve 2 LTspice ekranı) | Hatalı eşikler ve formül, aşağıda |
| Works/BMS_balancer.asc | Kitaptaki analog dengeleyicinin LTspice kopyası (4 karşılaştırıcı, MOSFET, 3 optokuplör) | 6 hata, düzeltildi |
| Works/B2.asc | Sadeleştirilmiş 3 karşılaştırıcılı sürüm (LT1011) | Aynı eşik ve besleme hataları |
| Works/BQ76Datasheet.pdf | TI bq76PL455A-Q1, 16 hücre izleme + pasif dengeleme | Referans |
| Product_option.xlsx | AFE seçenekleri: MP2797, MP2796, bq79758-Q1 (18S), NXP MC33775 (14 kanal, ASIL D), BQ76PL455A | Referans |
| Usefull_Link.xlsx | ESP32 ADC sayfası | Kullanılmıyor (STM32 seçildi) |
| Books/ (7 PDF) | Andrea (2010) BMS kitabı, LTC6801/6803, ATmega406, DS2726 veri sayfaları, 3 kitap/tez | Literatür |
| Works/MATHLAB_BMS/BatteryManagementSystem.mlproj | MathWorks resmi BMS referans projesi (2023) | Lisansımızla çalışmaz, referans olarak değerli |
| Passive-cell-Balancing.rar | Pasif dengeleme Simulink modeli (10 batarya, Stateflow) | Çalışmaz; algoritmada hata var |

## 2. Analog dengeleyici devresi (docx + BMS_balancer.asc + B2.asc)
Topoloji: Andrea, *Battery Management Systems for Large Lithium-Ion Battery Packs*, Şekil 5.21. Her seri gruba bir kart: 4 dirençli bölücü (100k / 26,5k / 3,5k / 70k), 1,25 V referans, 4 karşılaştırıcı, dengeleme MOSFET'i (10 Ω 2 W), optokuplörlü BAL / LVL / HVL zinciri.

Kitap değerleriyle eşikler: 1,25 V × 200k / (alt kısım) → **2,50 V, 3,40 V, 3,57 V. Bunlar LiFePO4 için.** LG M50T (NMC, 2,5–4,2 V) için uygun değil.

### Bulunan hatalar
1. **Kimya uyumsuzluğu:** Eşikler LiFePO4'e göre. M50T'de 3,57 V'ta dengeleme başlar, hücre her zaman "aşırı gerilimde" görünür.
2. **docx'teki formül:** "son kademe (charge)·73,5/200" yazıyor, doğrusu 70/200. Eşikler "2,5 / 3,5 / 3,5 V" yazıyor, doğrusu 2,50 / 3,40 / 3,57 V.
3. **Besleme (BMS_balancer.asc):** Hücre yerine **28 V** kaynak var (V1, B+ ile B− arası). Bölücü uçları 14 / 10,3 / 9,8 V olur, bütün karşılaştırıcılar doyuma gider. Devre tek hücre içindir (2,5–4,2 V) ve o hücreyle beslenip ona referanslanmalı. B2.asc'de de referans ayrı bir **10 V** kaynaktan besleniyor; seri pakette her kart kendi hücresinde "yüzer", ayrı besleme olamaz.
4. **Yanlış parça türü:** BMS_balancer.asc'de LT1001 kullanılmış; bu hassas bir op-amp, karşılaştırıcı değil (yavaş toparlanma, açık kollektör çıkışı yok, çift besleme ister). B2.asc'deki LT1011 gerçek bir karşılaştırıcı ama mA mertebesinde akım çekiyor. Hücreden beslenen bir devrede bu sürekli deşarj ve hücreler arası dengesizlik demek. Mikro güç bir karşılaştırıcı gerekir (kitaptaki LP339 veya TLV3012 sınıfı, ikincisinde dahili referans var).
5. **Dengeleme direnci:** BMS_balancer.asc'de R9 = **10 kΩ** → 0,41 mA. 12P grup (58,2 Ah) için %1 SOC'yi dengelemek **1420 saat** sürer, yani pratikte dengeleme yok. Kitaptaki 10 Ω 2 W ile 0,41 A, 1,4 saat.
6. **Histerezis yok:** Gürültü ve yük altında çıkışlar eşikte titreşir. Projedeki bulgu 16 ile aynı ders.
7. **Simülasyon kurgusu:** `.tran` ile sabit DC kaynak kullanılmış, eşikler görülemez. Gerilimi süpüren bir PWL rampası veya `.dc` taraması gerekir.

### Simülasyonun yakaladığı ek tasarım hatası
Üç karşılaştırıcı tek bölücüyü paylaşınca histerezis geri beslemeleri birbirini etkiliyor. BAL açılınca OV eşiği 4,21 V'tan **4,17 V'a** kayıyor (ngspice). Çözüm: OV'ye (güvenlik işlevi) **ayrı bölücü**. Güvenlik işlevinin diğer işlevlerden bağımsız olması ilkesiyle de uyumlu.

### Düzeltilmiş tasarım (donanim/m50t_cell_monitor.cir, ngspice ile doğrulandı)
| İşlev | Bölücü (E96, %0,1) | Simülasyon: yükselen / düşen [V] |
|---|---|---|
| UV ("hücre iyi") | Bölücü 1: 226k – 57,6k – 124k (UV ucu) | 2,820 / **2,799** |
| BAL (dengeleme açık) | Bölücü 1 (BAL ucu) | **4,101** / 4,062 |
| OV (aşırı gerilim arızası) | Bölücü 2: 267k – 113k | **4,214** / 4,176 |

- Histerezis: her uçta 27 MΩ pozitif geri besleme, 20–40 mV.
- OV bilerek 4,21 V: tam şarjda (CV sonu 4,20 V) yanlış alarm vermez, veri sayfası koruması 4,25 V'un altında kalır.
- Dengeleme akımı 10 Ω ile 0,45 A. Bölücülerin toplam çekişi ~21 µA.
- **Tolerans (Monte Carlo):** %1 dirençle OV eşiği ±75 mV oynuyor; devrelerin %3,9'unda 4,25 V'un üstüne kayıyor. %0,1 direnç ve %0,2 referansla ±24 mV, 4,25 V aşımı yok. Sonuç: analog çözüm hassas direnç olmadan güvenli değil. AFE entegreleri (ör. LTC6811 < 1,2 mV toplam hata) bu yüzden tercih ediliyor.
- Grafik: results/analog_monitor_m50t.png

## 3. Entegre seçimleri (docx + Product_option.xlsx)
| Parça | Durum (üretici sayfası) | Not |
|---|---|---|
| LTC6803-1 | NOT RECOMMENDED FOR NEW DESIGNS | Halefi LTC6811 (12 hücre, isoSPI, < 1,2 mV hata) |
| LTC6801 | NOT RECOMMENDED FOR NEW DESIGNS | Bağımsız arıza izleyici (ikincil koruma kavramı değerli) |
| DS2726 | Üretimi durdurulmuş (ADI) | 5–10 hücre koruyucu |
| ATmega406 | Üretimde, ama 4 hücre, 1 MHz 8 bit | 19S için uygun değil |
| bq76PL455A-Q1 | (veri sayfası klasörde) | 16 hücre; 19S için 2 adet |
| bq79758-Q1 | 18S | 19S için yine 2 adet |
| MC33775 | 14 kanal, ASIL D | 19S için 2 adet; fonksiyonel güvenlik için en güçlü aday |
19S için hangi aileden olursa olsun **2 AFE + papatya zinciri (daisy chain)** gerekiyor. Tezde "donanım gerçekleme / gelecek çalışma" bölümünde kullanılabilir.

## 4. MathWorks BMS referans projesi (.mlproj)
- **Gerektirdiği ürünler:** Stateflow, Simscape, Simscape Electrical, Simulink Design Optimization, Control System Toolbox, Embedded Coder vb. Elimizdeki lisansla (MATLAB, Simulink, Signal Processing, DSP, Communications) açılamaz. **Referans olarak kullanılacak.**
- **Bizde olmayan, alınabilecek fikirler:**
  1. İşletim modları: Standby / Driving / Charging + Fault.
  2. Kontaktör ve ön şarj sırası: ön şarj, yük geriliminin %95'ine ulaşınca biter, zaman aşımı 1 s, kontaktör bekleme 200 ms.
  3. Arıza tablosu yapısı: her arıza için ID, eşik, TimeToFail, TimeToPass, Sticky (kalıcı). Bizde bu davranışlar var (süre filtreleri, kalıcı bayraklar) ama tablo olarak yazılı değil; FMEA belgesi için bu yapı kullanılabilir.
  4. Dengeleme parametreleri: hedef fark 10 mV, açma bekleme 60 s, kapama bekleme 20 s; sürüşte kapalı, şarjda ve beklemede açık.
  5. Şarj yönetimi: CV eşiği 4,1 V, en yüksek hücre 4,15 V.
- **Bizimle tutarlı olanlar:** hücre arıza sınırları OV 4,25 V / UV 2,5 V (bizde de aynı), sıcaklık −15 / 55 °C.

## 5. Pasif dengeleme modeli (.rar)
- Specialized Power Systems (Simscape Electrical) + Stateflow → elimizdeki lisansla çalışmaz. 10 adet genel Li-ion batarya (7,2 V, 5,4 Ah), biri %96 SOC'de.
- **Algoritmada (Cmpr fonksiyonu) hata var:**
  1. Sıralanmış listedeki konum `i` ile en düşük hücrenin orijinal indeksi `index` karşılaştırılıyor (farklı indeks uzayları).
  2. İkinci en düşük hücre en düşüğe eşit olunca `break` ile döngüden çıkılıyor; diğer yüksek hücreler hiç dengelenmiyor.
  3. Ölü bant yok: %0,0001'lik farkta bile anahtar açılıp kapanıyor.
  4. Gerçek BMS hücre başına SOC ölçmez; dengeleme gerilimle yapılır.
- Düzeltilmiş mantık: hücre gerilimi `V_i − V_min > 10 mV` olanlar dengelenir, `< 5 mV` olunca kapanır (histerezis); sadece şarjda/beklemede; en düşük hücre asla dengelenmez.

## 6. Projeye önerilen eklemeler (öncelik sırasıyla)
1. **Bağımsız donanım koruması (HIL demosu, ucuz, güçlü):** Düzeltilmiş OV/UV devresinin bir kanalı breadboard'da. Arduino'nun PWM + RC çıkışı, emüle edilen V_cell_min/max'ı (2,5–4,2 V, ölçekleme gerekmez) verir. Karşılaştırıcı çıkışı, STM32'den bağımsız olarak lamba MOSFET'inin kapısını keser. "Yazılım kısar, donanım keser" iki katmanlı güvenlik (defense in depth), Hedef 4'ü güçlendirir. Parça: LM393/LM339 + referans (TL431 varsa) + dirençler.
2. **İşletim modları ve ön şarj (4. hafta, firmware):** Karar mekanizmasına Standby/Drive/Charge modları ve ön şarj zaman aşımı arızası; demoda LED ile kontaktör.
3. **Arıza tablosu (FMEA belgesi):** Mevcut kurallarımızı ID / eşik / TimeToFail / TimeToPass / Sticky tablosunda yazmak.
4. **Pasif dengeleme (isteğe bağlı):** İkizdeki zayıf grup + gerilim tabanlı dengeleme algoritması. Kapasite farkını düzeltemeyeceğini (sadece SOC'yi hizalar) göstermek tez için öğretici.
5. **Tez literatürü:** Andrea (2010) ve MathWorks projesi referans; AFE karşılaştırması "gerçek araçta donanım" bölümüne.
