# Makine öğrenmesi: gerçek veriyle SOH tahmini

**Soru:** BMS, aracın içinde, hücrenin şu anki kapasitesini (SOH) bilebilir mi?
**Veri:** Kirkaldy vd. (2024), 40 adet LG M50T hücre, 15 farklı kullanım koşulu, 511 ölçüm noktası.
**Hedef:** STM32'ye sığan (birkaç if-else) bir model. Tahmin EKF'ye girecek ve yaşlanmış hücrede SOC hatasını düzeltecek.

## Kurulum (bir kez)
Komut satırında (Windows: `cmd`, MATLAB değil), bu klasördeyken:
```
pip install numpy pandas scipy scikit-learn matplotlib openpyxl
```

## Adımlar
Sırayla çalıştır, her birinin çıktısını oku. Grafikler `simulink/sonuclar/` klasörüne kaydedilir.

| Adım | Komut | Öğreneceğin kavram |
|---|---|---|
| 1 | `python 01_veri_hazirla.py` | Veriye bakmak, özellik (X) ve hedef (y), aykırı değer |
| 2 | `python 02_ilk_model.py` | Eğitim/test ayrımı, doğrusal regresyon, karar ağacı, aşırı öğrenme |
| 3 | `python 03_dogru_test.py` | Çapraz doğrulama, veri sızıntısı, model ve özellik karşılaştırması |
| 4 | `python 04_model_aktar.py` | Son model, fizik kısıtları, otomatik C/MATLAB kodu üretimi ve doğrulaması |
| 5 | `python 05_yaslanmis_hucre.py` | Uçtan uca demo: çevrimiçi direnç -> ML SOH -> EKF, yaşlanmış pakette |

`dataset.csv` hazır olarak geliyor. 1. adım `../veri/kirkaldy_ozet/` klasörünü bulamazsa doğrudan 2. adımdan başlayabilirsin.

## Her adımda neye bakmalı?
**Adım 1:** Sağdaki grafikte direnç arttıkça SOH düşüyor. Çıktıdaki korelasyona bak: tek bir hatalı direnç ölçümü (hücre 5A, normalin 6 katı) bütün verideki korelasyonu −0,84'ten −0,29'a düşürüyordu. Modelden önce veriye bakmanın sebebi bu.

**Adım 2:** Karar ağacının kurallarını oku. Ağacın ilk sorusu "direnç oranı 1,072'den büyük mü?" oluyor; model en bilgilendirici özelliği kendisi buluyor. Derinlik tablosunda eğitim hatası sıfıra iniyor ama test hatası inmiyor: model ezberliyor.

**Adım 3:** Projenin en önemli dersi burada.
- Rastgele testte derin ağaç (8) iyi görünüyor.
- Koşul bazlı testte, yani model hiç görmediği bir kullanım tarzıyla karşılaşınca, en iyi derinlik 3 çıkıyor ve derin ağaç belirgin şekilde kötüleşiyor.
- Rastgele test iyimser, çünkü aynı hücrenin komşu ölçümleri ve aynı koşuldaki kardeş hücreler hem eğitimde hem testte bulunuyor. Buna veri sızıntısı denir.

**Adım 4:** Ağacın kurallarını tekrar oku. Kısıtsız ağaç "direnç düşükse SOH düşük" gibi saçma bir kural öğrenmişti (tek bir noktayı ezberleyerek). Fizik kısıtıyla (SOH direnç/çevrim/gün arttıkça artamaz) ve yaprak başına en az 10 ölçüm şartıyla bütün kurallar anlamlı oluyor, doğruluk aynı kalıyor. Üretilen C kodu Python ile 10 000 girdide birebir aynı (fark < 1e-6).

**Adım 5:** Araçta direnç laboratuvardaki gibi ölçülemez; BMS onu sürüşteki ani akım değişimlerinden (≥ 20 A / 0,1 s) kendisi kestirir (`twin/rint_estimator.py`). Bir sürüşte ~%3, üç sürüşte < %1 hata. Grafikte kırmızı çizgiye bak: yeni hücre sanan BMS'in hatası asıl dirençten geliyor; yaşlı hücrenin büyük gerilim düşümünü "SOC düşük" diye yorumluyor.

## Dosyalar
- `ortak.py`: veri yükleme ve fizik tabanlı yaşlanma modeli (karşılaştırma için, her testte yeniden kalibre edilir)
- `dataset.csv`: 1. adımın çıktısı
- `cv_results.csv`: 3. adımın sonuç tablosu
- `soh_tree.c/.h`: STM32 için otomatik üretilen model (Simulink karşılığı: `simulink/soh_tree.m`)
- `aged_demo_results.csv`: 5. adımın sonuç tablosu
