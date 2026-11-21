function A = thermal_anomaly_init()
%THERMAL_ANOMALY_INIT  Termal anomali dedektörü durumu (thermal_anomaly_step.m).
%#codegen
A = struct('tc', [0 0], 'ts', [0 0], 'age', [0 0], 'k', 0, 'n', 0, 't_f', 0, ...
           'started', false, 'flag', false);
end
