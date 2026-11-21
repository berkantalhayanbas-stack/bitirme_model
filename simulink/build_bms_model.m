%BUILD_BMS_MODEL  bms_twin_ekf.slx modelini sıfırdan otomatik kurar.
%   Gerekli: sadece Simulink (ek toolbox yok).
%   Kullanım: bu klasörde  >> build_bms_model
%
%   Yapı:
%     Drive (I_dem) ─> Current_Limiter (I_allow_dis/chg) ─> I_pack ─┬─> Battery_Twin ─> V, SOC, T
%                                                                   └─> + bias + gürültü ─>
%                                                kuantalama (CAN 0x101) ─> EKF ─> SOC_est
%                                                          └──────────> Thermal_Observer ─> Tc_hat, Ru_hat
%   Sensör zinciri: gürültü ─> Fault_Injector (Fault_mode, Fault_t) ─> CAN kuantalaması ─> Sensor_Diag
%   Sensor_Diag bayrakları EKF'ye ve Thermal_Observer'a gider (bozulmuş mod).
%   Rint_Estimator (çevrimiçi direnç) ─> SOH_ML (karar ağacı, ml/04_model_aktar.py çıktısı)
%   Age_Q/Age_R: ikizin gerçek yaşlanması; Bms_Q/Bms_R: BMS'in bildiği (EKF'ye girer).
%   Decision (karar mekanizması) ─> Unit Delay (0.1 s) ─> Current_Limiter: KAPALI ÇEVRİM.
%   CAN_Rx (4. hafta): kuantalanmış ölçümler 0x101/0x102 olarak alınır; CRC + alive counter +
%   zaman aşımı izleyicisi (can_monitor_*.m), kayıpta son değer tutulur, CAN_ok -> Decision.
%   Can_mode/Can_msg/Can_t/Can_dur ile CAN arızası enjekte edilir (0 = yok, sonuçlar eskisiyle aynı).
%   Dec_on = 0 iken Decision sabit I_allow_dis/I_allow_chg verir (eski testlerle birebir aynı).

bms_init;
mdl = 'bms_twin_ekf';
if bdIsLoaded(mdl), close_system(mdl, 0); end
if exist([mdl '.slx'], 'file'), delete([mdl '.slx']); end
new_system(mdl);
open_system(mdl);

set_param(mdl, 'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', ...
    'FixedStep', 'Ts', 'StopTime', 't_stop', 'ReturnWorkspaceOutputs', 'on');

L = @(name) [mdl '/' name];

% ------------------------------------------------------------- Kaynaklar
add_block('simulink/Sources/From Workspace', L('Drive'), ...
    'VariableName', 'drive_ts', 'SampleTime', 'Ts', 'Interpolate', 'off', ...
    'OutputAfterFinalValue', 'Holding final value');
add_block('simulink/Sources/Constant', L('T_amb'),     'Value', 'T_amb');
add_block('simulink/Sources/Constant', L('Ru_factor'), 'Value', 'Ru_factor');
add_block('simulink/Sources/Constant', L('SOC0'),      'Value', 'SOC0');
add_block('simulink/Sources/Constant', L('Weak_on'),   'Value', 'Weak_on');
add_block('simulink/Sources/Constant', L('I_allow_dis'), 'Value', 'I_allow_dis');
add_block('simulink/Sources/Constant', L('I_allow_chg'), 'Value', 'I_allow_chg');
add_block('simulink/Sources/Constant', L('Fault_mode'), 'Value', 'Fault_mode');
add_block('simulink/Sources/Constant', L('Fault_t'),    'Value', 'Fault_t');
add_block('simulink/Sources/Constant', L('Diag_on'),    'Value', 'Diag_on');
add_block('simulink/Sources/Constant', L('Age_Q'),      'Value', 'Age_Q');
add_block('simulink/Sources/Constant', L('Age_R'),      'Value', 'Age_R');
add_block('simulink/Sources/Constant', L('Bms_Q'),      'Value', 'Bms_Q');
add_block('simulink/Sources/Constant', L('Bms_R'),      'Value', 'Bms_R');
add_block('simulink/Sources/Constant', L('Rint_num0'),  'Value', 'Rint_num0');
add_block('simulink/Sources/Constant', L('Rint_den0'),  'Value', 'Rint_den0');
add_block('simulink/Sources/Constant', L('Usage'),      'Value', 'Usage');
add_block('simulink/Sources/Constant', L('Dec_on'),     'Value', 'Dec_on');
add_block('simulink/Sources/Constant', L('Can_mode'),   'Value', 'Can_mode');
add_block('simulink/Sources/Constant', L('Can_msg'),    'Value', 'Can_msg');
add_block('simulink/Sources/Constant', L('Can_t'),      'Value', 'Can_t');
add_block('simulink/Sources/Constant', L('Can_dur'),    'Value', 'Can_dur');

% ------------------------------------------------------------- Akım sınırlayıcı
add_block('simulink/User-Defined Functions/MATLAB Function', L('Current_Limiter'));
cfg = get_param(L('Current_Limiter'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [I_pack, limited] = lim_blk(I_dem, I_allow_dis, I_allow_chg)\n' ...
    '%%#codegen\n' ...
    '[I_pack, limited] = current_limiter(I_dem, I_allow_dis, I_allow_chg);\n' ...
    'end\n']);

% ------------------------------------------------------------- Dijital ikiz
add_block('simulink/User-Defined Functions/MATLAB Function', L('Battery_Twin'));
cfg = get_param(L('Battery_Twin'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [V_pack, SOC, T_core, T_surf, OCV_pack, V_cell_min, SOC_weak, V_cell_max] = twin_blk(I_pack, T_amb, Ru_factor, SOC0, Weak_on, Age_Q, Age_R)\n' ...
    '%%#codegen\n' ...
    '[V_pack, SOC, T_core, T_surf, OCV_pack, V_cell_min, SOC_weak, V_cell_max] = battery_twin(I_pack, T_amb, Ru_factor, SOC0, Weak_on, Age_Q, Age_R);\n' ...
    'end\n']);

% ------------------------------------------------------------- Sensör modeli
add_block('simulink/Sources/Random Number', L('Noise_V'), 'Mean', '0', ...
    'Variance', 'sig_v^2', 'Seed', 'seed_v', 'SampleTime', 'Ts');
add_block('simulink/Sources/Random Number', L('Noise_I'), 'Mean', '0', ...
    'Variance', 'sig_i^2', 'Seed', 'seed_i', 'SampleTime', 'Ts');
add_block('simulink/Sources/Random Number', L('Noise_T'), 'Mean', '0', ...
    'Variance', 'sig_t^2', 'Seed', 'seed_t', 'SampleTime', 'Ts');
add_block('simulink/Sources/Constant', L('Bias_I'), 'Value', 'bias_i');
% hücre gerilimleri (CAN 0x102: en düşük / en yüksek seri grup, 1 mV çözünürlük)
add_block('simulink/Sources/Random Number', L('Noise_Vmin'), 'Mean', '0', ...
    'Variance', 'sig_vc^2', 'Seed', 'seed_vmin', 'SampleTime', 'Ts');
add_block('simulink/Sources/Random Number', L('Noise_Vmax'), 'Mean', '0', ...
    'Variance', 'sig_vc^2', 'Seed', 'seed_vmax', 'SampleTime', 'Ts');
add_block('simulink/Math Operations/Sum', L('Sum_Vmin'), 'Inputs', '++');
add_block('simulink/Math Operations/Sum', L('Sum_Vmax'), 'Inputs', '++');
add_block('simulink/Discontinuities/Quantizer', L('CAN_Q_Vmin'), 'QuantizationInterval', 'lsb_vc');
add_block('simulink/Discontinuities/Quantizer', L('CAN_Q_Vmax'), 'QuantizationInterval', 'lsb_vc');

add_block('simulink/Math Operations/Sum', L('Sum_V'), 'Inputs', '++');
add_block('simulink/Math Operations/Sum', L('Sum_I'), 'Inputs', '+++');
add_block('simulink/Math Operations/Sum', L('Sum_T'), 'Inputs', '++');

add_block('simulink/User-Defined Functions/MATLAB Function', L('Fault_Injector'));
cfg = get_param(L('Fault_Injector'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [V_out, I_out, T_out] = fault_blk(V_in, I_in, T_in, Fault_mode, Fault_t)\n' ...
    '%%#codegen\n' ...
    '[V_out, I_out, T_out] = fault_injector(V_in, I_in, T_in, Fault_mode, Fault_t);\n' ...
    'end\n']);

add_block('simulink/Discontinuities/Quantizer', L('CAN_Q_V'), 'QuantizationInterval', 'lsb_v');
add_block('simulink/Discontinuities/Quantizer', L('CAN_Q_I'), 'QuantizationInterval', 'lsb_i');
add_block('simulink/Discontinuities/Quantizer', L('CAN_Q_T'), 'QuantizationInterval', 'lsb_t');

% ------------------------------------------------------------- CAN alımı (ECU tarafı)
add_block('simulink/User-Defined Functions/MATLAB Function', L('CAN_Rx'));
cfg = get_param(L('CAN_Rx'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [V, I, T, V_min, V_max, CAN_ok, can_fault] = canrx_blk(V_in, I_in, T_in, Vmin_in, Vmax_in, Can_mode, Can_msg, Can_t, Can_dur)\n' ...
    '%%#codegen\n' ...
    '[V, I, T, V_min, V_max, CAN_ok, can_fault] = can_rx(V_in, I_in, T_in, Vmin_in, Vmax_in, Can_mode, Can_msg, Can_t, Can_dur);\n' ...
    'end\n']);

% ------------------------------------------------------------- Sensör teşhisi
add_block('simulink/User-Defined Functions/MATLAB Function', L('Sensor_Diag'));
cfg = get_param(L('Sensor_Diag'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [T_valid, I_valid] = diag_blk(I_meas, T_meas, Diag_on)\n' ...
    '%%#codegen\n' ...
    '[T_valid, I_valid] = sensor_diag(I_meas, T_meas, Diag_on);\n' ...
    'end\n']);
add_block('simulink/Discrete/Unit Delay', L('Delay_Ts'), 'InitialCondition', 'T_amb', 'SampleTime', 'Ts');

% ------------------------------------------------------------- EKF
add_block('simulink/User-Defined Functions/MATLAB Function', L('EKF'));
cfg = get_param(L('EKF'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [SOC_est, bias_est, innov, rejected] = ekf_blk(I_meas, V_meas, T_meas, T_valid, Ts_hat_prev, Gate_on, Q_scale, R_scale, Zero_on)\n' ...
    '%%#codegen\n' ...
    '[SOC_est, bias_est, innov, rejected] = ekf_soc(I_meas, V_meas, T_meas, T_valid, Ts_hat_prev, Gate_on, Q_scale, R_scale, Zero_on);\n' ...
    'end\n']);

% ------------------------------------------------------------- Çekirdek sıcaklığı gözlemcisi
add_block('simulink/User-Defined Functions/MATLAB Function', L('Thermal_Observer'));
cfg = get_param(L('Thermal_Observer'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [Tc_hat, Ts_hat, Ru_hat, T_anom] = thobs_blk(I_meas, V_meas, SOC_est, T_meas, T_amb, T_valid)\n' ...
    '%%#codegen\n' ...
    '[Tc_hat, Ts_hat, Ru_hat, T_anom] = thermal_observer(I_meas, V_meas, SOC_est, T_meas, T_amb, T_valid);\n' ...
    'end\n']);

% ------------------------------------------------------------- Direnç kestiricisi + ML SOH
add_block('simulink/User-Defined Functions/MATLAB Function', L('Rint_Estimator'));
cfg = get_param(L('Rint_Estimator'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [rr_hat, num, den, n_ev] = rint_blk(I_meas, V_meas, Tc_hat, SOC_est, I_valid, num0, den0)\n' ...
    '%%#codegen\n' ...
    '[rr_hat, num, den, n_ev] = rint_estimator(I_meas, V_meas, Tc_hat, SOC_est, I_valid, num0, den0);\n' ...
    'end\n']);
add_block('simulink/User-Defined Functions/MATLAB Function', L('SOH_ML'));
cfg = get_param(L('SOH_ML'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function SOH_hat = soh_blk(Usage, rr_hat)\n' ...
    '%%#codegen\n' ...
    '%% Usage = [efc days T_mean SOC_mean DoD]: BMS lifetime counters (EEPROM in HIL)\n' ...
    'SOH_hat = soh_tree(Usage(1), Usage(2), Usage(3), Usage(4), Usage(5), rr_hat);\n' ...
    'end\n']);

% ------------------------------------------------------------- Karar mekanizması (kapalı çevrim)
add_block('simulink/User-Defined Functions/MATLAB Function', L('Decision'));
cfg = get_param(L('Decision'), 'MATLABFunctionConfiguration');
cfg.FunctionScript = sprintf([ ...
    'function [state, I_allow_dis, I_allow_chg, psi, cause] = dec_blk(I_meas, V_min, V_max, Tc_hat, Ts_hat, Ru_hat, SOC_est, bias_est, T_valid, I_valid, CAN_ok, T_meas, T_amb, Dec_on, I_fix_dis, I_fix_chg, T_anom)\n' ...
    '%%#codegen\n' ...
    'if Dec_on > 0.5\n' ...
    '    [state, I_allow_dis, I_allow_chg, psi, cause] = decision_logic(I_meas, V_min, V_max, Tc_hat, Ts_hat, Ru_hat, SOC_est, bias_est, T_valid, I_valid, CAN_ok, T_meas, T_amb, T_anom);\n' ...
    'else\n' ...
    '    state = 1; I_allow_dis = I_fix_dis; I_allow_chg = I_fix_chg; psi = 0; cause = 0;\n' ...
    'end\n' ...
    'end\n']);
add_block('simulink/Discrete/Unit Delay', L('Delay_Idis'), 'InitialCondition', 'I_allow_dis*(1-Dec_on)', 'SampleTime', 'Ts');
add_block('simulink/Discrete/Unit Delay', L('Delay_Ichg'), 'InitialCondition', 'I_allow_chg*(1-Dec_on)', 'SampleTime', 'Ts');

% ------------------------------------------------------------- Kayıt + scope
logs = {'log_i','log_vpack','log_soc','log_tcore','log_tsurf','log_ocv', ...
        'log_vm','log_im','log_tm','log_soc_est','log_bias','log_innov', ...
        'log_idem','log_limited','log_vcellmin','log_socweak', ...
        'log_tc_hat','log_ts_hat','log_ru_hat','log_tvalid','log_ivalid','log_rej', ...
        'log_rr','log_rint_num','log_rint_den','log_rint_n','log_soh_ml', ...
        'log_vcellmax','log_vmin_m','log_vmax_m','log_state','log_iallow_dis','log_iallow_chg', ...
        'log_psi','log_cause','log_can_ok','log_can_fault'};
for k = 1:numel(logs)
    add_block('simulink/Sinks/To Workspace', L(logs{k}), ...
        'VariableName', logs{k}, 'SaveFormat', 'Array', 'SampleTime', '-1');
end
add_block('simulink/Sinks/Scope', L('Scope_SOC'),  'NumInputPorts', '2');
add_block('simulink/Sinks/Scope', L('Scope_Temp'), 'NumInputPorts', '3');

% ------------------------------------------------------------- Bağlantılar
c = @(a, b) add_line(mdl, a, b, 'autorouting', 'smart');

c('Drive/1',           'Current_Limiter/1');
c('Delay_Idis/1',      'Current_Limiter/2');
c('Delay_Ichg/1',      'Current_Limiter/3');
c('Current_Limiter/1', 'Battery_Twin/1');
c('Weak_on/1',         'Battery_Twin/5');
c('T_amb/1',     'Battery_Twin/2');
c('Ru_factor/1', 'Battery_Twin/3');
c('SOC0/1',      'Battery_Twin/4');
c('Age_Q/1',     'Battery_Twin/6');
c('Age_R/1',     'Battery_Twin/7');

c('Battery_Twin/1', 'Sum_V/1');   c('Noise_V/1', 'Sum_V/2');
c('Current_Limiter/1', 'Sum_I/1');   c('Bias_I/1',  'Sum_I/2');  c('Noise_I/1', 'Sum_I/3');
c('Battery_Twin/4', 'Sum_T/1');   c('Noise_T/1', 'Sum_T/2');

c('Sum_V/1', 'Fault_Injector/1');  c('Sum_I/1', 'Fault_Injector/2');  c('Sum_T/1', 'Fault_Injector/3');
c('Fault_mode/1', 'Fault_Injector/4');  c('Fault_t/1', 'Fault_Injector/5');
c('Fault_Injector/1', 'CAN_Q_V/1');  c('Fault_Injector/2', 'CAN_Q_I/1');  c('Fault_Injector/3', 'CAN_Q_T/1');
c('CAN_Rx/2', 'Sensor_Diag/1');  c('CAN_Rx/3', 'Sensor_Diag/2');
c('CAN_Rx/2', 'EKF/1');    c('CAN_Rx/1', 'EKF/2');    c('CAN_Rx/3', 'EKF/3');
c('Diag_on/1', 'Sensor_Diag/3');
c('Sensor_Diag/1', 'EKF/4');  c('Delay_Ts/1', 'EKF/5');  c('Diag_on/1', 'EKF/6');
c('Bms_Q/1', 'EKF/7');  c('Bms_R/1', 'EKF/8');
c('CAN_Rx/2', 'Rint_Estimator/1');  c('CAN_Rx/1', 'Rint_Estimator/2');
c('Thermal_Observer/1', 'Rint_Estimator/3');  c('EKF/1', 'Rint_Estimator/4');
c('Sensor_Diag/2', 'Rint_Estimator/5');
c('Rint_num0/1', 'Rint_Estimator/6');  c('Rint_den0/1', 'Rint_Estimator/7');
c('Usage/1', 'SOH_ML/1');  c('Rint_Estimator/1', 'SOH_ML/2');
c('Rint_Estimator/1', 'log_rr/1');  c('Rint_Estimator/2', 'log_rint_num/1');
c('Rint_Estimator/3', 'log_rint_den/1');  c('Rint_Estimator/4', 'log_rint_n/1');
c('SOH_ML/1', 'log_soh_ml/1');
% hücre gerilimi ölçümleri
c('Battery_Twin/6', 'Sum_Vmin/1');  c('Noise_Vmin/1', 'Sum_Vmin/2');  c('Sum_Vmin/1', 'CAN_Q_Vmin/1');
c('Battery_Twin/8', 'Sum_Vmax/1');  c('Noise_Vmax/1', 'Sum_Vmax/2');  c('Sum_Vmax/1', 'CAN_Q_Vmax/1');
c('Battery_Twin/8', 'log_vcellmax/1');
c('CAN_Rx/4', 'log_vmin_m/1');  c('CAN_Rx/5', 'log_vmax_m/1');
% CAN alımı: kuantalanmış ölçümler (EMU'nun gönderdiği) -> CAN_Rx -> BMS algoritmaları
c('CAN_Q_V/1', 'CAN_Rx/1');  c('CAN_Q_I/1', 'CAN_Rx/2');  c('CAN_Q_T/1', 'CAN_Rx/3');
c('CAN_Q_Vmin/1', 'CAN_Rx/4');  c('CAN_Q_Vmax/1', 'CAN_Rx/5');
c('Can_mode/1', 'CAN_Rx/6');  c('Can_msg/1', 'CAN_Rx/7');  c('Can_t/1', 'CAN_Rx/8');  c('Can_dur/1', 'CAN_Rx/9');
c('CAN_Rx/6', 'log_can_ok/1');  c('CAN_Rx/7', 'log_can_fault/1');
% karar mekanizması girişleri
c('CAN_Rx/2',           'Decision/1');
c('CAN_Rx/4',           'Decision/2');
c('CAN_Rx/5',           'Decision/3');
c('Thermal_Observer/1', 'Decision/4');
c('Thermal_Observer/2', 'Decision/5');
c('Thermal_Observer/3', 'Decision/6');
c('Thermal_Observer/4', 'Decision/17');      % termal anomali (açıklanamayan ısı)
c('EKF/1',              'Decision/7');
c('EKF/2',              'Decision/8');
c('Sensor_Diag/1',      'Decision/9');
c('Sensor_Diag/2',      'Decision/10');
c('CAN_Rx/6',           'Decision/11');
c('CAN_Rx/3',           'Decision/12');
c('T_amb/1',            'Decision/13');
c('Dec_on/1',           'Decision/14');
c('Dec_on/1',           'EKF/9');           % A9: sıfır akım kalibrasyonu yalnız karar döngüdeyken (kontaktör açık)
c('I_allow_dis/1',      'Decision/15');
c('I_allow_chg/1',      'Decision/16');
c('Decision/2', 'Delay_Idis/1');  c('Decision/3', 'Delay_Ichg/1');
c('Decision/1', 'log_state/1');   c('Decision/2', 'log_iallow_dis/1');
c('Decision/3', 'log_iallow_chg/1');  c('Decision/4', 'log_psi/1');  c('Decision/5', 'log_cause/1');
c('Sensor_Diag/1', 'log_tvalid/1');  c('Sensor_Diag/2', 'log_ivalid/1');  c('EKF/4', 'log_rej/1');

c('Current_Limiter/1', 'log_i/1');
c('Drive/1',           'log_idem/1');
c('Current_Limiter/2', 'log_limited/1');
c('Battery_Twin/6',    'log_vcellmin/1');
c('Battery_Twin/7',    'log_socweak/1');
c('Battery_Twin/1', 'log_vpack/1');
c('Battery_Twin/2', 'log_soc/1');
c('Battery_Twin/3', 'log_tcore/1');
c('Battery_Twin/4', 'log_tsurf/1');
c('Battery_Twin/5', 'log_ocv/1');
c('CAN_Rx/1', 'log_vm/1');  c('CAN_Rx/2', 'log_im/1');  c('CAN_Rx/3', 'log_tm/1');
c('EKF/1', 'log_soc_est/1'); c('EKF/2', 'log_bias/1');    c('EKF/3', 'log_innov/1');

c('CAN_Rx/2', 'Thermal_Observer/1');  c('CAN_Rx/1', 'Thermal_Observer/2');
c('EKF/1',     'Thermal_Observer/3');  c('CAN_Rx/3', 'Thermal_Observer/4');
c('T_amb/1',   'Thermal_Observer/5');  c('Sensor_Diag/1', 'Thermal_Observer/6');
c('Thermal_Observer/2', 'Delay_Ts/1');
c('Thermal_Observer/1', 'log_tc_hat/1');
c('Thermal_Observer/2', 'log_ts_hat/1');
c('Thermal_Observer/3', 'log_ru_hat/1');
c('Thermal_Observer/1', 'Scope_Temp/3');

c('Battery_Twin/2', 'Scope_SOC/1');  c('EKF/1', 'Scope_SOC/2');
c('Battery_Twin/3', 'Scope_Temp/1'); c('Battery_Twin/4', 'Scope_Temp/2');

Simulink.BlockDiagram.arrangeSystem(mdl);
save_system(mdl);
fprintf('Model hazir: %s.slx  ->  simdi: run_and_compare\n', mdl);
