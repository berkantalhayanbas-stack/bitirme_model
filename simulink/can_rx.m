function [V, I, T, V_min, V_max, CAN_ok, can_fault] = can_rx(V_in, I_in, T_in, Vmin_in, Vmax_in, Can_mode, Can_msg, Can_t, Can_dur)
%CAN_RX  ECU'nun CAN alım katmanı (4. hafta): EMU ölçümleri -> izleyici -> BMS algoritmaları.
%   0x101 = V, I, T      0x102 = V_min, V_max (+ T_amb; modelde T_amb doğrudan sabit)
%   Her adımda (Ts = 0.1 s = EMU periyodu) iki mesaj da gönderilir; alive counter adım başına 1 artar.
%   İzleyici: can_monitor_init / _rx / _tick (STM32: bms_can.c, Python: twin/can_monitor.py).
%   Kabul edilmeyen (kayıp, CRC'si bozuk, sayacı hatalı) mesajda o mesajın ölçümleri son geçerli
%   değerde tutulur (sıfır dereceli tutucu, STM32 app_ecu.c ile aynı). CAN_ok = iki izleyiciden
%   hiçbiri SAFE değil -> decision_logic (SAFE-STOP, kalıcı).
%
%   Arıza enjeksiyonu (bms_init: Can_mode, Can_msg, Can_t, Can_dur):
%     Can_mode 0 yok, 1 çerçeve kaybı (kablo kopması / bus-off), 2 CRC bozuk, 3 donmuş alive counter
%     Can_msg  bit maskesi: 1 = 0x101, 2 = 0x102, 3 = ikisi
%     Can_t    başlangıç [s], Can_dur süre [s] (Inf = sona kadar)
%   Çıkış can_fault: bit0 0x101, bit1 0x102 zaman aşımı arızası (>= 250 ms, kendiliğinden kalkar).
%
%   Not: STM32 izleyicisi 10 ms'de bir değerlendirir, model adım başına (100 ms). SAFE anı
%   (son geçerli mesajdan 500 ms sonra) aynıdır; fault bayrağı modelde en geç 50 ms sonra kalkar.
%   Not: ECU ilk geçerli ölçüm çiftinden önce bms_step koşmaz; model koşar (tutulan değer ilk örnek).

%#codegen
persistent M1 M2 k hold
P = bms_param_struct();
if isempty(k)
    k = 0;
    M1 = can_monitor_init(0);
    M2 = can_monitor_init(0);
    hold = [V_in I_in T_in Vmin_in Vmax_in];
end
now_ms = round(k * P.Ts * 1000);
t0_ms  = round(Can_t * 1000);
active = Can_mode > 0 && now_ms >= t0_ms && now_ms < t0_ms + Can_dur * 1000;
cnt    = mod(k, P.can_counter_mod);
cnt_frozen = mod(round(Can_t / P.Ts), P.can_counter_mod);

% ---- 0x101: V, I, T
hit = active && bitand(uint8(Can_msg), uint8(1)) > 0;
if ~(hit && Can_mode == 1)
    c = cnt;
    if hit && Can_mode == 3, c = cnt_frozen; end
    [M1, ok] = can_monitor_rx(M1, now_ms, ~(hit && Can_mode == 2), c);
    if ok, hold(1:3) = [V_in I_in T_in]; end
end
% ---- 0x102: V_min, V_max
hit = active && bitand(uint8(Can_msg), uint8(2)) > 0;
if ~(hit && Can_mode == 1)
    c = cnt;
    if hit && Can_mode == 3, c = cnt_frozen; end
    [M2, ok] = can_monitor_rx(M2, now_ms, ~(hit && Can_mode == 2), c);
    if ok, hold(4:5) = [Vmin_in Vmax_in]; end
end
M1 = can_monitor_tick(M1, now_ms);
M2 = can_monitor_tick(M2, now_ms);
k = k + 1;

V = hold(1);  I = hold(2);  T = hold(3);  V_min = hold(4);  V_max = hold(5);
CAN_ok    = double(~(M1.safe || M2.safe));
can_fault = double(M1.fault) + 2 * double(M2.fault);
end
