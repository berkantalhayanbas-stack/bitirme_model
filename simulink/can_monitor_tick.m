function mon = can_monitor_tick(mon, now_ms)
%CAN_MONITOR_TICK  Zaman aşımı değerlendirmesi (STM32'de 10 ms'de bir, modelde her adımda).
%   Açılış: henüz hiç geçerli mesaj yokken eşik P.can_t_first_ms (AUTOSAR "first timeout");
%           CRC'si bozuk çerçeveler bu süreyi uzatmaz.
%   Sonra : son geçerli mesajdan beri >= P.can_t_fault_ms -> fault (kendiliğinden kalkar),
%           >= P.can_t_safe_ms -> safe (KALICI; çıkış yalnız yeniden başlatma ile).
%   C karşılığı: can_monitor_tick (bms_can.c).

%#codegen
P = bms_param_struct();
age = now_ms - mon.last_ok_ms;
if ~mon.have_counter
    if age >= P.can_t_first_ms
        mon.fault = true;
        mon.safe  = true;
    end
    return;
end
mon.fault = age >= P.can_t_fault_ms;
if age >= P.can_t_safe_ms
    mon.safe = true;
end
end
