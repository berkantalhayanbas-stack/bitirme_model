# Tezin anlatımı: ne yaptık, neden yaptık

Bu belge tezin Türkçe "öğretmen notu"dur. Tezin her bölümünü sırayla açıklar: o bölümde ne var, neden öyle yapıldı ve jürinin sorabileceği sorular. Tez metni İngilizce (`main.tex` ve `chapters/`); burası onu anlaman için.

Okuma önerisi: önce bu belgenin bir bölümünü oku, sonra tezdeki aynı bölümü. Anlamadığın bir terim olursa en sondaki küçük sözlüğe bak.

---

## Taslak 2 (kısa sürüm, 22 Kasım): baz makale ve yeni yapı

**Baz makale:** Nejakar vd. 2025, "Cloud-Integrated Digital Twin for Intelligent Battery Monitoring and SOC Prediction" (IEEE TEMSMET, 5 sayfa).
- **Onların sistemi:** ESP32 + sensörler (gerilim bölücü, ACS712, DS18B20, GPS) + Firebase + React panel. SOC için Kalman + RNN hibriti, MAE %2,6. Uyarılar eşik tabanlı: SOC < %20, T > 50 °C.
- **Bizimle ilişkisi:** Aynı üç ayak bizde de var: dijital ikiz, SOC kestirimi, bulut izleme. Bizim ekimiz **kontrol**: BMS yalnız uyarmıyor, akımı kısıp bataryayı koruyor. İkiz de testte gerçek paketin yerini alıyor.
- **Karşılaştırma tablosu** (Tablo 5.3): sayılarımızı onlarınkiyle doğrudan yarıştırmadık, çünkü ölçütler farklı. Onların hatası gerçek 12 V bataryada MAE, bizimki ikizin gerçek SOC'sine göre RMSE. Jüri sorarsa bunu söyle.

**Yeni yapı, makalenin iskeleti:**

| Kısa tez | Ne var | Ayrıntısı aşağıda |
|---|---|---|
| 1 Giriş | sorun, makaleye göre konumumuz, katkılar | Bölüm 1 |
| 2 Arka plan | SOC yöntemleri, termal, dijital ikiz/bulut, HIL | Bölüm 2 |
| 3 Yöntem (A-F) | 4 katman: ikiz / BMS / bulut / panel; veri toplama, EKF, bulut, panel, karar | Bölüm 3, 5, 6, 9 |
| 4 Donanım | tablo + gerçek zaman | Bölüm 3 |
| 5 Sonuçlar | model doğruluğu, SOC tablosu, Monte Carlo, HIL'in bulduğu 3 hata, bulut, panel, makaleyle karşılaştırma | Bölüm 4, 5, 7, 9 |
| 6 Sonuç | | Bölüm 10-11 |

Uzun ilk taslak silinmedi: `tez/arsiv_uzun/`. Bir konuyu detaylandırmak istediğimizde oradan paragraf çekeceğiz. Aşağıdaki bölüm açıklamaları uzun taslağın numaralarına göre; içerik aynı.

---

## Büyük resim (tek paragraf)

Bir elektrikli aracın bataryasını yöneten yazılımı (BMS) sıfırdan yazdık ve gerçek bir otomotiv mikrodenetleyicisinde (STM32) çalıştırdık. Gerçek batarya kullanmak yerine bataryanın bilgisayar modelini ("dijital ikiz") ayrı bir karta (Arduino) koyduk. İki kartı arabalardaki gibi CAN hattıyla bağladık. Böylece BMS'e, gerçek hücrelerde yapılamayacak arızaları (yangına yakın ısınma, kopuk sensör, kesik kablo, donan yazılım) güvenle ve tekrar tekrar yaşattık, ve tepkisini ölçtük.

Tezin vurgusu üç şey:
1. BMS çalışıyor ve iyi ölçüm veriyor.
2. Ucuz bir test düzeneği kurduk.
3. Bu düzenek, bilgisayardaki testlerin kaçırdığı üç tasarım hatasını buldu. Bu sonuncusu tezin en güçlü argümanı.

---

## Bölüm 1: Giriş

**Ne anlatıyor:** Neden BMS gerekli, neden test etmek zor, biz ne yaptık.

**Ana fikirler:**
- **BMS üç iş yapar.** Ölçer (gerilim, akım, birkaç sıcaklık), kestirir (şarj durumu SOC, hücre içi sıcaklık, iç direnç) ve karar verir (araç ne kadar akım çekebilir).
- **Kestirim şart, çünkü tehlikeli büyüklükler gizli.** Sensör hücrenin yüzeyine yapışır, ama yaşlanma ve termal kaçak için önemli olan iç (çekirdek) sıcaklıktır. SOC de akım akarken voltmetreden okunamaz.
- **Karar kademeli olmalı.** Sorun olunca hemen kontaktörü açmak, yani bataryayı ayırmak, hareket hâlindeki araçta tehlikelidir. Önce akım azaltılır, sonra "limp-home" (eve kadar sürünme) seviyesine inilir, en son ayrılır.
- **Test zor.** Sanayi bunu laboratuvar HIL düzenekleriyle yapıyor, ama bunlar çok pahalı.

**"Kapsam" neden önemli:** Bizim düzenek "iletişim tabanlı" HIL. İkiz hücre gerilimlerini analog sinyal olarak değil, CAN mesajı olarak gönderiyor. Bu, BMS'in *karar stratejisini* test etmek için yeterli (Haupt 2013 bunu açıkça söylüyor). Ama ölçüm devresini (AFE çipi) test etmez. Bunu dürüstçe söylemek jüri karşısında güç verir.

**Jüri sorabilir:** "Neden gerçek batarya kullanmadınız?"
**Cevap:** Test etmek istediğimiz arızaların çoğu gerçek hücrede tehlikeli ya da tekrarlanamaz (60 °C'ye ısınma, dış ısı, kesik kablo). Model ölçülmüş verilerle (Kirkaldy 2024) ayarlandı, yani hayalî değil.

---

## Bölüm 2: Arka plan ve literatür

**Ne anlatıyor:** Hücrenin nasıl davrandığını, kestirim yöntemlerini ve literatürdeki HIL çalışmalarını.

**Kavramlar (bunları iyi bilmelisin):**
- **OCV (açık devre gerilimi):** Dinlenmiş hücrenin gerilimi; SOC'nin bir fonksiyonu. NMC hücrede ortası düz olduğu için orada küçük gerilim hatası büyük SOC hatası demek.
- **Eşdeğer devre modeli (ECM):** Hücreyi bir direnç (R0, anlık düşüş) ve iki RC kolu (yavaş polarizasyon) olarak düşünürüz. Neden iki RC? Bir tanesi kısa (saniyeler), diğeri uzun (dakikalar) etkileri temsil ediyor. Gerçekte daha fazla zaman sabiti var; iki RC bir uzlaşma.
- **Arrhenius:** Sıcaklık arttıkça direnç düşer. Ne kadar düştüğünü aktivasyon enerjisi (Ea) belirler.
- **İki düğümlü termal model:** Çekirdek ve yüzey, arada iletim direnci (Rc), yüzeyden havaya taşınım direnci (Ru). Biz yalnız yüzeyi ölçebiliyoruz.
- **Kalman filtresi:** Modelin tahminiyle ölçümü, ikisinin belirsizliğine göre ağırlıklandırıp birleştirir. EKF, doğrusal olmayan modeli her adımda doğrusallaştırır.
- **SOP (izin verilen akım):** Hiçbir hücreyi gerilim sınırının dışına itmeyecek en büyük akım.

**Literatürü dört gruba ayırdık (Bölüm 2.4):** gerçek batarya + PC'de algoritma; pahalı laboratuvar HIL'i (ticari BMS kara kutu); ayrıntılı model + basit BMS; yalnız ölçüm yapan prototipler.

**Bizim boşluğumuz:** İçini bildiğimiz (beyaz kutu) kendi BMS'imiz + ucuz ikiz + ölçülmüş arıza tespit süreleri. Bu üçlüyü birleştiren çalışma yok.

**Jüri sorabilir:** "Neden EKF? Neden UKF ya da yapay sinir ağı değil?"
**Cevap:**
- EKF sanayide yaygın ve mikrodenetleyicide ucuz: bir adım < 0,1 ms.
- Zhao 2017 birinci dereceden EKF'nin en zayıf seçenek olduğunu gösteriyor. Bunu biliyoruz ve gelecek çalışmaya yazdık.
- Doğruluğumuz (%0,28) iş için yeterli.

---

## Bölüm 3: Sistem tasarımı

**Ne anlatıyor:** Donanım, paket, ikiz, CAN mesajları, yazılım yapısı.

**Neden iki ayrı kart?** HIL'in özü bu. BMS, modelin iç değişkenlerine "bakamaz"; yalnız CAN çerçevelerini görür, gerçek bir BMS'in hücre izleme kartından gördüğü gibi. İkisi aynı kartta olsaydı kandırmak kolay olurdu.

**Her parçanın nedeni:** Tablo 3.1'de. En önemlileri:
- **Röle = ana kontaktör.** Son koruma katmanı. Akım sınırlama ancak inverter itaat ederse işe yarar, bu yüzden SAFE durumunda bataryanın fiziksel olarak ayrılması gerekir.
- Röle "fail-safe" bağlı: BMS takılırsa ya da elektrik kesilirse kendiliğinden bırakır.

**Paket:** 19 seri × 12 paralel hücre, 58,2 Ah, ~4 kWh. Deşarj sınırı 87,3 A, şarj sınırı 40,7 A (veri sayfasından).

**Parametre tablosu (Tablo 3.2) neden önemli:** Hangi değerin ölçülmüş, hangisinin varsayılmış olduğunu açıkça gösteriyor. Dürüstlük puanı.

**CAN tasarımı, üç neden (ezberle):**
1. **Verim:** Her CAN çerçevesinin ~47 bitlik sabit yükü var. 19 grubu 19 ayrı çerçeve yerine 5 çerçevede gönderdik.
2. **Tutarlılık:** Akım, gerilim ve sıcaklık aynı çerçevede, yani aynı anın değerleri. Ayrı gelselerdi geciken bir çerçeve yeni akımı eski gerilimle eşleştirir ve filtre bunu "direnç değişti" diye yorumlardı.
3. **Koruma maliyeti:** Sayaç + CRC (1,5 bayt) çerçeve başına bir kez ödenir.

**E2E koruma:** Her çerçevede 4 bitlik sayaç ve CRC-8 var; CRC ID'yi de kapsıyor. 500 ms geçerli ölçüm gelmezse SAFE.

**Ölçülen bus yükü:** %1,61. Mikrodenetleyicinin kendi zamanlayıcısı ve DMA'sıyla lojik analizör yaptık, CAN analizörü almadan.

**Gerçek zaman dersi:** Bloklayan UART raporu (30 ms) CAN alım kuyruğunu (3 çerçeve) taşırdı. Kesmeli yazıya geçtik. Gömülü sistemlerde "bir işin süresi" başka bir işi bozabilir; güzel bir anlatım konusu.

---

## Bölüm 4: Modelin tanılanması

**Ne anlatıyor:** İkizin gerçek hücre gibi davranması için parametreleri gerçek veriden nasıl çıkardık.

**Veri:** Kirkaldy 2024, 40 adet LG M50T hücrenin ömür boyu ölçümleri, açık veri.

**4.1 OCV:** İlk modelde kardeş hücrenin (M50, Chen 2020) eğrisini kullanıyorduk. GITT verisinden yeni tablo çıkardık:
- **GITT nedir:** Hücreye kısa akım darbesi verilir, sonra uzun süre dinlendirilir. Dinlenme sonundaki gerilim ≈ OCV.
- **Çapraz doğrulama:** Tabloyu A-D hücrelerinden kurduk, *tabloyu kurmayan* E-H hücrelerinde test ettik. Hata 64,7 mV → 17,0 mV (3,8 kat iyi).
- Bu "çapraz doğrulama" fikri önemli: modeli kurduğun veriyle test edersen kendini kandırırsın.

**4.2 RC kolları:** Hangi bölgeye uydurursan farklı sayı çıkıyor, ama hata < 2 mV değişiyor. Yani RC seçimi sonucu belirlemiyor; asıl hata OCV ve histerezisten.

**4.3 Aktivasyon enerjisi:**
- Ohmik direnç sıcaklığa az duyarlı (6,2 kJ/mol), polarizasyon çok duyarlı (14-28 kJ/mol).
- Eski varsayımımız (20 kJ/mol yalnız R0'a) 40 °C'de %30, 5 °C'de %40 hatalıydı.

**4.4 Yaşlanma:**
- 40 hücre, 224 ölçümde direnç artışı = 1,31 × kapasite kaybı.
- Ömür sonunda (SOH %80) direnç %26 fazla.
- Bu ilişki iki işe yarıyor: ikizi tek parametreyle (SOH) yaşlandırmak, ve direnç tabanlı eşikleri "SOH yüzde kaç" diye anlamlandırmak.

**4.5:** Modelin dört kopyası (Python, Simulink, C ikiz, Monte Carlo) birebir aynı sonucu veriyor. Bu sayede "kart ile PC aynı hükmü verdi" iddiası anlamlı.

**Jüri sorabilir:** "Parametrelerin bir kısmı varsayım, sonuçlarına nasıl güveniyoruz?"
**Cevap:** Duyarlılık analizi (Bölüm 5.2). Parametreleri tek tek bozduk; güvenlik ölçütleri 25 durumun 25'inde korundu. Bulduğumuz hatalar da yapısal hatalardı, parametreye bağlı değildi.

---

## Bölüm 5: Kestirim algoritmaları

Bu bölüm tezin teknik kalbi.

**5.1 SOC EKF:** Durum vektörü [SOC, V1, V2, b_I, k_R].
- **V1, V2:** RC kollarının gerilimleri (ölçülemez, kestirilir).
- **b_I (akım sensörü ofseti):** Coulomb sayımı sabit bir ofseti zamanla büyüyen SOC hatasına çevirir. Filtre ofseti de kestirirse bunu düzeltir.
- **k_R (direnç ölçeği):** Duyarlılık analizinde k_R olmadan filtrenin direnç hatasını b_I'ya yüklediğini ve yaşlanmış pakette sahte "sensör arızası" verdiğini gördük. Bu yüzden eklendi.
- **İnovasyon kapısı:** Ölçüm beklenenden 10σ uzaksa reddedilir (EMI sıçraması). 5 ardışık red olursa kapı açılır, çünkü o zaman hatalı olan ölçüm değil modeldir.
- **Açılış sıfır akım kontrolü:** Filtre ofseti çok yavaş görüyordu (±8 A hiç fark edilmiyordu). Sanayideki çözümü uyguladık: kontaktör açıkken akım kesin 0, yani ölçülen ortalama = ofset. Tespit süresi 1000+ s'den 0,9 s'ye indi.
- **İlginç ders:** Arızayı bildirip ofseti düzeltmezsek SOC kontrol hiç yokmuş gibi kötüleşiyordu.
- **Açılışta k_R dondurma:** Kartta bulduğumuz hata. Yeniden başlatmadan hemen sonra şarj başlarsa k_R 2,0'a fırlıyordu. Çünkü filtre SOC'yi %50'den başlatıyor; SOC oturmadan gerilim farkını "direnç arttı" sanıyordu. İlk 120 s k_R'yi dondurduk.

**Sonuç:** SOC hatası %0,277 RMSE. Tablo 5.1'de karşılaştırma var:
- Yalnız OCV'ye bakmak %17 hata verir.
- Yalnız Coulomb sayımı %0,86 hata verir.
- Sabit dirençli EKF sıcak günde %2,5 hata verir.
- Sıcaklık ve ofset bilgisi ekledikçe hata düşüyor; tablonun anlattığı hikâye bu.

**5.3 Çekirdek sıcaklık gözlemcisi:**
- İkinci bir EKF, durum [Tc, Ts, g]; g = 1/Ru, yani soğutmanın iletkenliği.
- g kestirildiği için BMS **soğutmanın bozulduğunu kendi başına fark edebiliyor**: Ru > 18 K/W olunca alarm.
- **Sınırlama:** Ru yalnız ısı akarken gözlenebilir. Paket yeterince ısınmazsa soğutma arızası görünmez (Monte Carlo'da %48 yakalandı). Bu bir hata değil, fiziğin sınırı; tezde dürüstçe yazıldı.

**5.4 Modelde olmayan ısı:** Bu bölüm tezin en ilginç hikâyesi.
- **Sorun:** Gözlemci yalnız akımdan hesaplanabilen ısıyı biliyor. Dışarıdan ısıtınca (yangın, iç kısa devre başlangıcı) yüzeyin ısınmasını "soğutma kötüleşti" diye açıkladı. Çekirdek tahmini 26 °C'de kaldı, oysa gerçek çekirdek 55 °C idi.
- **Çözüm 1 (ölçüme bağlı sınır):** Durağan hâlde çekirdek ile yüzey arasındaki fark, ısının kaynağından bağımsız olarak Rc/Ru × (yüzey − ortam). Bu sınır ölçümden hesaplanır, gözlemciye güvenmez.
- **Çözüm 2 (termal anomali dedektörü, "adyabatik zarf"):** Şu soruyu sorar: "Hiç soğutma olmasa bile, bildiğim ısı yüzeyi bu kadar hızlı ısıtabilir miydi?" Cevap hayırsa açıklanamayan bir ısı var demektir. Bu durumda LIMP'e geçilir.
- **Sonuç:** Medyan 8 s'de tespit. Çekirdek tahmin hatası −52 °C'den −5 °C'ye indi.
- **Negatif sonuç da değerli:** İlk denenen CUSUM yöntemi işe yaramadı ve neden işe yaramadığı tezde anlatıldı. Jüri bunu sever.

**5.5 Sensör teşhisi:** Aralık, donma ve hız kontrolleri. Ön filtreleme denendi ama reddedildi: filtre gecikme ekliyor, histerezis aynı işi gecikmesiz yapıyor.

**5.6 Makine öğrenmesiyle SOH:**
- Kirkaldy verisiyle eğitilmiş 3 derinlikli karar ağacı, C koduna aktarıldı.
- Hücre dışarıda bırakma doğrulamasında %2,57 hata. Gradient boosting daha iyi (%1,93), ama ağaç mikrodenetleyiciye sığdığı için seçildi.
- **Sınırlama:** Kartta SOH hep ~%100 görünüyor. Kullanım sayaçları saklanmıyor ve direnç kestiricisinin ihtiyaç duyduğu büyük akım basamakları test çevriminde yok.

**Jüri sorabilir:** "Gözlemci çekirdek sıcaklığı yanlış tahmin ediyorsa, BMS'e nasıl güvenelim?"
**Cevap:** Güvenlik tek bir tahmine dayanmıyor; katmanlı. Ölçüme bağlı sınır ve anomali dedektörü gözlemciden bağımsız çalışıyor. Bunu kart testinde ölçtük: SAFE, gerçek çekirdek 60 °C'deyken geldi.

---

## Bölüm 6: Karar katmanı ve stres indeksi

**Dört durum:** NORMAL → DERATE (akım azalt) → LIMP-HOME (%25) → SAFE-STOP (0 A, kontaktör açık, kilitli).

**Kurallar:**
- Kötüleşme anında olur, iyileşme 10 s bekler. Böylece durum titremez (histerezis).
- İzin verilen akım saniyede en çok 10 A artar; araç ani sıçrama görmez.
- **Neden bitleri:** Her kararın nedeni de gönderiliyor (sıcaklık, soğutma, gerilim payı, sensör...). Açıklanabilirlik; "BMS neden kıstı?" sorusunun cevabı.

**Gerilim payı (SOP):** En zayıf grubu 2,90 V'a indirecek akımı hesaplar. Direnci sıcaklıkla ve k_R ile ölçekler; yaşlanmış paket kendiliğinden daha erken kısılır.

**Stres indeksi Ψ:**
- **Formül:** Ψ = en büyük kriter + 0,25 × (diğerlerinin toplamı). İki orta uyarı birlikte tek birinden fazla kısar, ama en güçlü uyarıyı fazla aşmaz.
- **Akım kısan kriterler:** çekirdek sıcaklığı, soğutma alarmı, sıcaklık artış hızı.
- **Ψ_H (direnç artışı) yalnız gösterge.** Yeniden başlatmadan hemen sonra yanlış tetiklenebildiği için akım kısmaktan çıkarıldı. Yaşlanmış paketi zaten SOP kısıyor.
- **Diğer aday kriterler** (SOC belirsizliği, I²t, grup gerilim farkı) veriyle değerlendirildi ve reddedildi: ya hiç eşiğe yaklaşmıyorlardı, ya da normalde de arıza seviyesine çıkıyorlardı. "Neden eklemedik" sorusunun veriye dayalı cevabı var.

**Dengeleme:** Yüksek gruplar 10 Ω dirençle boşaltılır. Gösterimde 500 kat hızlandırdık; gerçekte %1 SOC farkı ~1,4 saatte kapanıyor. Bunu açıkça yazmak önemli. Dengeleme SOC'yi eşitler, kapasite farkını gidermez.

**Termal olay:** Araç kapalıyken (SAFE) paket ısınmaya devam ederse "aracı terk edin" uyarısı. Kapanıştan hemen sonraki doğal ısı dengelenmesini yanlış alarm saymamak için 90 s bekleme var.

---

## Bölüm 7: Doğrulama

**Doğrulama zinciri, beş seviye:**

| Seviye | Ne test edilir |
|---|---|
| MIL | Python/Simulink'te model; 20 birim testi ve 8 kabul senaryosu |
| SIL | C kodu PC'de; Python ve MATLAB ile birebir aynı |
| PIL | Aynı veri karta UART'tan gider; kart aynı sonucu verir; adım < 92 µs |
| CAN replay | Kayıtlı veri gerçek CAN hattından oynatılır |
| HIL | Gerçek düzenek |

Her seviye bir öncekinin göremediği şeyi yakalar.

**Monte Carlo (en güçlü sayısal sonuç):**
- İkiz ve BMS aynı STM32'de, gerçek zamanı beklemeden çalışıyor.
- 1000 rastgele koşu: sıcaklık, SOC, sürüş sertliği, hücre farkları, rastgele zamanda tek bir arıza.
- **1000/1000 geçti.**
- **Kart ile PC aynı tohumla aynı hükmü verdi, 1000/1000.** Bu, gömülü kodun PC'deki kodla aynı davrandığının kanıtı.
- 605 kat gerçek zamandan hızlı; 1000 koşu 16,5 dakika.

**Tezgâh buton testleri:** Her buton bir *neden* enjekte ediyor, ECU'ya senaryoyu söylemiyor. ECU doğru moda kendi başına varıyor. Süreler Tablo 7.2'de.

**HIL'in bulduğu üç hata (Tablo 7.3) — tezin en önemli argümanı:**
1. **Soğutma alarmı titriyordu.** Histerezis eksikti. Bilgisayar testlerinde kestirim eşiği yavaşça geçen bir durum hiç oluşmamıştı.
2. **Sıcak paket yeniden başlatılınca sahte soğutma alarmı veriyordu.** Hiçbir offline test "sıcak ve yüklü paket üzerinde ECU'yu yeniden başlat" senaryosunu içermiyordu.
3. **Dış ısıda çekirdek tahmini gerçeğin çok gerisinde kalıyordu.** Offline testlerde ısı hep modelin bildiği ısıydı.

Ortak nokta: bu hatalar parametreye bağlı değil, yapısal. Ucuz bir ikiz bile onları bulmaya yetti.

---

## Bölüm 8: Güvenlik analizi

13 tehlike, her biri için tespit mekanizması, eşik, tepki ve **ölçülmüş süre**. Bu tablo FMEA tarzında; tam bir ISO 26262 süreci değil (HARA ve ASIL yok). Bunu açıkça söylemek doğru olandır; jüri "ISO 26262'ye uygun mu?" diye sorarsa cevap "mekanizma düzeyinde evet, süreç düzeyinde hayır".

Kapsanmayanlar da yazılı: kısa devre (100 ms döngü çok yavaş), hat direnci arızası, inverterin akım sınırına uymaması.

---

## Bölüm 9: Uzaktan izleme

**Zincir:** ECU → seri port → PC'deki gateway → HTTPS → PHP sunucu → web paneli.

**Neden "yalnız izleme":** İnternet kopabilir. Güvenlik kararları ECU'da kalmalı (Li 2020). Bulut bağlantısı saldırı yüzeyi açar (Naseri 2023); bu yüzden API anahtarı ve tekrar gönderim koruması var.

**Ölçüm:**
- 30 dakikada 18 046 satır, kayıp 0.
- Gidiş-dönüş medyan 102 ms.
- Uçtan uca gecikmenin büyük kısmı 1 s'lik toplama süresinden; bilinçli bir tasarım seçimi.

**İki ölçüm dersi:**
1. PC saati sunucuyla senkron değildi. Bu yüzden tek yön gecikme ölçülemez; yalnız tek saatle ölçülenler raporlandı.
2. İki serbest çalışan saat (ECU ve PC) birbirinden ~500 ppm kayıyor. Titreşim ölçerken bu kaymayı çıkarmak gerekiyor.

---

## Bölüm 10-11: Tartışma, sınırlamalar, sonuç

**Tartışmanın ana fikri:** Bizim düzenek laboratuvar düzeneklerinden çok ucuz ve elektriksel olarak daha az gerçekçi. Ama BMS beyaz kutu olduğu için tahminleri gerçekle karşılaştırabiliyoruz; tespit sürelerini ve *neden geciktiğini* görebiliyoruz.

**Sınırlamalar listesi:** Bunu iyi bil. Jüri bir eksik sorduğunda "evet, bunu biliyoruz, Bölüm 10.3'te yazılı" demek çok güçlü bir cevap.

**Kapanış cümlesi (sunumda da kullan):** "Çalışan bir BMS, onu güvenle test eden ucuz bir platform ve ikisinin neden birlikte gerektiğini kendi verisiyle gösteren bir tez."

---

## Taslakta yapılacaklar (TODO listesi)

Tez metninde turuncu `[TODO: ...]` notları var (13 tane). En önemlileri:
- Üniversite, bölüm, danışman ve tarih bilgileri (kapak).
- Türkçe özetin son hâli.
- Blok diyagramı İngilizce etiketlerle yeniden çizilmeli.
- Dengeleme figürü.
- Tezgâh senaryo grafiklerinin tez stilinde yeniden çizilmesi.
- Ekler: CAN çerçeve tablosu, sabitler tablosu.
- Veri sayfası ve standart sürümlerinin kontrolü (`references.md`).

Üniversitenin bir tez şablonu varsa (kapak, kenar boşlukları, Türkçe/İngilizce zorunluluğu) metni ona taşırız; içerik aynı kalır.

---

## Derleme

- **Overleaf:** `python make_overleaf_zip.py` → `build/tez_overleaf.zip` → Overleaf'te New Project > Upload Project. Derleyici: pdfLaTeX.
- Bilgisayarda (MiKTeX, `tez/` klasöründe; figürler `../results/` klasöründen okunur, PDF `build/main.pdf`):
  1. `pdflatex -output-directory=build main.tex`
  2. `cd build` ve `set BIBINPUTS=..` (Git Bash'te `BIBINPUTS=.. bibtex main`), sonra `bibtex main`
  3. `cd ..` ve `pdflatex -output-directory=build main.tex` komutunu iki kez daha çalıştır.
  Kaynakça değişmediyse yalnız 3. adım yeter.

---

## Küçük sözlük

| Terim | Anlamı |
|---|---|
| SOC | Şarj durumu (%). Bataryada ne kadar enerji kaldığı. |
| SOH | Sağlık durumu. Kalan kapasitenin yeni hâline oranı (%80 = ömür sonu). |
| OCV | Açık devre gerilimi; dinlenmiş hücrenin gerilimi. |
| ECM | Eşdeğer devre modeli; hücreyi direnç ve kapasitörlerle temsil etmek. |
| EKF | Genişletilmiş Kalman filtresi. |
| RMSE | Karesel ortalama hata; tipik hata büyüklüğü. |
| HIL | Donanım-döngüde test; gerçek denetleyici + benzetilmiş sistem. |
| MIL / SIL / PIL | Model / yazılım / işlemci-döngüde test. |
| SOP | İzin verilen güç/akım. |
| CAN | Araçlardaki iki telli haberleşme hattı. |
| CRC | Mesajın bozulup bozulmadığını anlamaya yarayan sağlama değeri. |
| E2E | Uçtan uca koruma (sayaç + CRC). |
| IWDG | Bağımsız bekçi köpeği; yazılım donarsa kartı sıfırlar. |
| GITT | Darbe + dinlenme ile yapılan hücre ölçüm yöntemi. |
| Histerezis | Açma ve kapama eşiklerinin farklı olması; titremeyi önler. |
| Monte Carlo | Rastgele çok sayıda senaryo koşup istatistik çıkarma. |
