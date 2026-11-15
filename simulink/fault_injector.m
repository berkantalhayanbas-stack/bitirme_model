function [V_out, I_out, T_out] = fault_injector(V_in, I_in, T_in, Fault_mode, Fault_t)
%FAULT_INJECTOR  Sensör arıza kütüphanesi (test amaçlı arıza enjeksiyonu).
%   Gürültülü ama henüz kuantalanmamış ölçümlere, t >= Fault_t anından
%   itibaren seçilen arızayı ekler. Fault_mode:
%     0 none      : arıza yok (normal çalışma)
%     1 v_spike   : paket geriliminde EMI sıçraması (+8 V, her 30 s'de bir örnek)
%     2 i_frozen  : akım sensörü son değerinde takılı kalır
%     3 t_open    : NTC kopuk, -40.0 °C okunur (ADC skala sonu)
%     4 t_frozen  : sıcaklık sensörü son değerinde takılı kalır
%     5 i_offset  : akım sensöründe +3 A ani ofset kayması
%   Python referansı: twin/sensor_faults.py (inject)

%#codegen
persistent P k I_hold T_hold
if isempty(P)
    P = bms_param_struct();
end
if isempty(k)
    k = 0;
end
if isempty(I_hold)
    I_hold = 0;
end
if isempty(T_hold)
    T_hold = 0;
end

k0 = round(Fault_t / P.Ts);
V_out = V_in;  I_out = I_in;  T_out = T_in;

if k == k0                       % arıza anındaki değerler (donma için)
    I_hold = I_in;
    T_hold = T_in;
end

if k >= k0
    switch round(Fault_mode)
        case 1
            if mod(k - k0, P.fault_period) == 0
                V_out = V_in + P.fault_spike;
            end
        case 2
            I_out = I_hold;
        case 3
            T_out = -40;
        case 4
            T_out = T_hold;
        case 5
            I_out = I_in + P.fault_i_off;
        otherwise
            % 0: arıza yok
    end
end
k = k + 1;
end
