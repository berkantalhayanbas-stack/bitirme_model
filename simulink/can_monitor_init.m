function mon = can_monitor_init(now_ms)
%CAN_MONITOR_INIT  Bir periyodik CAN mesajı için alım izleyicisi (E2E: CRC + alive counter + zaman aşımı).
%   STM32 karşılığı: bms_ecu/bms/common/bms_can.c  can_monitor_init / _rx / _tick (birebir aynı mantık).
%   Python referansı: twin/can_monitor.py (CanMonitor).  Zaman tamsayı ms.
%   now_ms: izleyicinin başlatıldığı an; ilk geçerli mesaja kadar açılış süresi (P.can_t_first_ms)
%   bu andan sayılır.

%#codegen
mon = struct('last_ok_ms', now_ms, 'last_counter', 0, 'have_counter', false, ...
             'fault', false, 'safe', false, ...
             'n_ok', 0, 'n_crc_err', 0, 'n_cnt_err', 0, 'n_lost', 0);
end
