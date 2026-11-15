function [mon, ok] = can_monitor_rx(mon, now_ms, crc_ok, counter)
%CAN_MONITOR_RX  Alınan bir çerçeveyi değerlendirir; ok = 1 ise veri kullanılabilir.
%   CRC hatası            -> reddedilir (n_crc_err)
%   sayaç farkı 0         -> donmuş sayaç / tekrar, reddedilir (n_cnt_err)
%   sayaç farkı 2..3      -> arada kayıp çerçeve var ama kabul (n_lost += fark - 1)
%   sayaç farkı > 3       -> dizi hatası, reddedilir; sayaç yeniden eşitlenir (n_cnt_err)
%   Kabul edilen çerçeve zaman aşımı sayacını sıfırlar (last_ok_ms = now_ms).
%   Sonuç (100 ms periyot, bilinçli seçim): 3 ardışık kayıptan sonra dönüş çerçevesi reddedilir
%   ama SAFE olmaz (yaş 497 ms); 4 ve üstü kayıpta dönüş çerçevesi de reddedildiği için 500 ms
%   dolar -> SAFE. Yani pratikte 4 ardışık kayıp SAFE-STOP'a götürür (AUTOSAR E2E "wrong sequence").
%   C karşılığı: can_monitor_rx (bms_can.c).

%#codegen
P = bms_param_struct();
ok = false;
if ~crc_ok
    mon.n_crc_err = mon.n_crc_err + 1;
    return;
end
if mon.have_counter
    delta = mod(counter - mon.last_counter, P.can_counter_mod);
    mon.last_counter = counter;
    if delta == 0 || delta > P.can_max_delta
        mon.n_cnt_err = mon.n_cnt_err + 1;
        return;
    end
    mon.n_lost = mon.n_lost + delta - 1;
else
    mon.have_counter = true;
    mon.last_counter = counter;
end
mon.n_ok = mon.n_ok + 1;
mon.last_ok_ms = now_ms;
ok = true;
end
