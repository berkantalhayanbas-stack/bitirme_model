function S = aging_stress(dod, m, T, A)
%AGING_STRESS  Çevrim başına stres katsayısı (eşdeğer tam çevrim başına göreli hasar).
%   dod : çevrim derinliği (0-1), m : çevrimin ortalama SOC'si (0-1), T : hücre sıcaklığı [°C]
%   S(1, 0.5, 25 °C) = 1 (referans: 25 °C'de %0-100 tam çevrim)
%
%   Yapı Millner (2010) stres fikrine dayanır: üstel DoD terimi + ortalama SOC terimi,
%   NMC811/SiOx hücre için iki ek: soğukta Li kaplama ve düşük SOC'de Si hasarı.
%   Vektör girişleri destekler; kod üretimine uygundur (ECU'ya taşınabilir).

%#codegen
main = exp(A.Ksoc*(m - 0.5)/0.25) .* exp(A.kh*max(0, T - A.Tr)) ...
       .* exp(A.kc*max(0, A.Tr - T).*m);                  % SEI + soğukta Li kaplama
si   = A.Klow*exp(-m/0.1) .* exp(A.kSi*(T - A.Tr));       % düşük SOC: Si hasarı
ext  = exp(A.k_ext*max(0, T - A.T_data_max));             % veri dışı sıcaklık: Millner kuralı
S    = exp((dod - 1)/A.Kex) .* (main + si) ./ (1 + A.Klow*exp(-5)) .* ext;
end
