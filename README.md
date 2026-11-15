# Bitirme — Sütun 1: 19S12P Dijital İkiz + EKF Prototipi

## Çalıştırma
```
pip install numpy scipy matplotlib pandas
cd twin && python run_sim.py
```
Çıktılar `results/` klasörüne yazılır.

## Dosyalar
| Dosya | İçerik |
|---|---|
| `twin/battery_model.py` | 2-RC hücre modeli, R0(T,SOC), 2 düğümlü termal model, Bernardi ısısı, 19S12P ölçekleme |
| `twin/drive_cycle.py` | Sentetik çevrim + araç dinamiği (450 kg hafif EV) → paket akımı. Gerçek WLTC CSV için `load_speed_csv()` |
| `twin/sensors.py` | Gürültü, akım sensörü kayması ve CAN 0x101 kuantalaması (0.1 V / 0.1 A / 0.1 °C) |
| `twin/ekf.py` | 3 ve 4 durumlu EKF (SOC, V1, V2, [akım kayması]); R0(T) düzeltmesi T_surf ile yapılıyor |
| `twin/run_sim.py` | Ana senaryo, grafikler, özet |

## İlk sonuçlar (gerçek SOC %80, EKF başlangıcı %50)
Gürültü: σ_V = 0.25 V (paket), σ_I = 0.5 A, akım kayması = +0.5 A, CAN kuantalaması dahil.

| Yöntem | SOC RMSE (tüm) | RMSE (60 s sonrası) | Son kez \|hata\| > %2 |
|---|---|---|---|
| EKF, sabit R0 | %0.84 | %0.82 | 57.8 s |
| EKF, R0(T) | %0.34 | %0.26 | 58.0 s |
| EKF, R0(T) + kayma durumu | %0.31 | %0.22 | 57.8 s |

KPI (RMSE < %1.5 ve 60 s içinde kilitlenme) sağlanıyor.

## Bilinen sınırlamalar / sıradaki işler
- Hücre parametreleri literatür tipik değerleri; kendi OCV + darbe testinle `CellParams` güncellenecek.
- Kayma durumu RMSE'yi az iyileştiriyor ama kaymanın kendisini doğru kestiremiyor (0.5 A yerine ~0.9 A buluyor). Gözlemlenebilirlik zayıf; tezde dürüstçe tartışılmalı.
- Paket en fazla 87 A verebildiğinden araç ~90 km/h üstünde akım sınırında kalıyor (sürenin ~%14'ü).
- 25 °C ortamda T_core en fazla ~31 °C'ye çıkıyor. Derating senaryosu için sıcak ortam / agresif çevrim / soğutma arızası senaryoları eklenecek.
