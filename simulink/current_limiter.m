function [I_pack, limited] = current_limiter(I_dem, I_allow_dis, I_allow_chg)
%CURRENT_LIMITER  Sürücü akım talebini BMS'in izin verdiği sınırlarla kırpar.
%   I_dem       : talep edilen paket akımı [A] (pedal / sürüş çevrimi; + deşarj)
%   I_allow_dis : izin verilen en büyük deşarj akımı [A] (>= 0)
%   I_allow_chg : izin verilen en büyük şarj (rejen) akımı [A] (>= 0, büyüklük)
%   I_pack      : bataryaya uygulanan akım [A]
%   limited     : 1 ise talep kırpıldı (sürücüye geri bildirim / gösterge)
%
%   Gerçek araçta bu işi VCU yapar: BMS izin verilen akımı CAN ile yayınlar
%   (0x201), VCU motor sürücüsünün talebini buna göre sınırlar.
%   3. haftada I_allow_* girişleri karar mekanizmasının çıkışına bağlanacak.

%#codegen
I_pack  = min(max(I_dem, -max(I_allow_chg, 0)), max(I_allow_dis, 0));
limited = double(abs(I_pack - I_dem) > 1e-9);
end
