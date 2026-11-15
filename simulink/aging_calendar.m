function alpha = aging_calendar(V, T, A)
%AGING_CALENDAR  Takvim yaşlanma hızı katsayısı (Schmalstieg vd. 2014, NMC).
%   fade_cal(t) = alpha * t^0.75,  t [gün]
%   V : dinlenme (OCV) gerilimi [V/hücre], T : hücre sıcaklığı [°C]
%   Yüksek gerilim (yüksek SOC) ve yüksek sıcaklık takvim kaybını hızlandırır.

%#codegen
alpha = max(0, A.cal_c1*V + A.cal_c0) * A.cal_scale .* exp(-A.cal_EaR ./ (T + 273.15));
end
