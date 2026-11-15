function A = aging_params()
%AGING_PARAMS  Kalibre edilmiş yaşlanma modeli parametreleri (çevrim + takvim).
%   Çevrim terimi: Kirkaldy vd. (2024) LG M50T açık verisiyle en küçük kareler
%   (J. Power Sources 603, 234185; Zenodo 10.5281/zenodo.10637534).
%   Takvim terimi: Schmalstieg vd. (2014), J. Power Sources 257, 325-334 (NMC; kalibre edilmedi).
%   Kalibrasyon RMSE (deney 1, 2, 3, 5): 2.52 %
%   Doğrulama (deney 4, sürüş çevrimi, kalibrasyonda kullanılmadı): 10 C: 4.68 %, 25 C: 0.80 %, 40 C: 1.69 %
%   Bu dosya veri/aging_calibration.py ile üretildi; elle değiştirme.

%#codegen
% --- Çevrim yaşlanması: fade_cyc = a * (sum S*dEFC)^z
A.a     = 0.00353113;
A.z     = 0.531521;   % ~0.5: SEI difüzyon sınırlı (sqrt benzeri)
A.Kex   = 0.428569;   % DoD üstel katsayısı (Millner Kex; LFP için 0.717)
A.Ksoc  = 0.0520326;   % ortalama SOC katsayısı (yüksek SOC etkisi takvim teriminde)
A.Klow  = 56.492;   % düşük SOC (Si) hasar ağırlığı
A.kh    = 5.72592e-24;   % sıcak taraf (veri aralığında ~0)
A.kc    = 0.29655;   % soğuk taraf (Li kaplama), SOC ile ağırlıklı [1/K]
A.kSi   = 0.0222006;   % Si hasarının sıcaklık duyarlılığı [1/K]
A.Tr    = 25;   % referans sıcaklık [°C]
A.T_data_max = 42.3;   % kalibrasyondaki en sıcak hücre [°C]
A.k_ext = 0.0693147;   % bunun üstünde Millner kuralı (ekstrapolasyon)
% --- Takvim yaşlanması: fade_cal = alpha(V,T) * t_gün^0.75
%     alpha = (c1*V + c0) * scale * exp(-EaR / T_K)
A.cal_c1 = 7.543;  A.cal_c0 = -23.75;  A.cal_scale = 1e+06;
A.cal_EaR = 6976.0;  A.cal_exp = 0.75;
A.fade_eol = 0.20;   % ömür sonu: %20 kapasite kaybı
end
