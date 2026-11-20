%TEST_SENSOR_FAULTS  2. hafta: sensör arıza kütüphanesi ve teşhis testi.
%   Arıza anı Fault_t = 1200 s. Her arıza, teşhis kapalı (Diag_on = 0) ve
%   açık (Diag_on = 1) olarak koşturulur ve karşılaştırılır.
%     1 v_spike  (normal)        : EMI sıçramaları, EKF inovasyon kapısı
%     2 i_frozen (normal)        : takılı akım sensörü
%     3 t_open   (cooling_fault) : kopuk NTC (-40 °C)
%     4 t_frozen (cooling_fault) : takılı sıcaklık sensörü
%     5 i_offset (normal)        : +3 A akım ofseti (EKF kayma durumu yakalamalı)
%   Ayrıca 6 normal senaryoda (arıza yok) yanlış alarm olmadığı kontrol edilir.
%   Önkoşul: build_bms_model (Fault_Injector + Sensor_Diag içeren sürüm).
%   Çıktılar İngilizce; şekil ../results/ klasörüne, veriler fault_sonuclari.mat'a.

bms_init;
I_std = ref.i_pack;
names = {'none', 'v_spike', 'i_frozen', 't_open', 't_frozen', 'i_offset'};
cases = {1, 'normal', 25, 1;  2, 'normal', 25, 1;  3, 'cooling_fault', 35, 4; ...
         4, 'cooling_fault', 35, 4;  5, 'normal', 25, 1};

nC = size(cases, 1);
T = table('Size', [2*nC 9], 'VariableTypes', ...
    {'string','string','string','double','double','double','double','double','double'}, ...
    'VariableNames', {'Fault','Scenario','Diagnostics','SOC_err_max_pct','SOC_err_end_pct', ...
                      'Tcore_err_max_C','Detect_delay_s','V_rejected','Bias_end_A'});
F = struct();
r = 0;
for c = 1:nC
    for dg = [0 1]
        r = r + 1;
        bms_init;  Fault_mode = cases{c,1};  T_amb = cases{c,3};  Ru_factor = cases{c,4};
        Diag_on = dg;
        fprintf('[%d/%d] %s, diagnostics %s ...\n', r, 2*nC, names{Fault_mode+1}, onoff(dg));
        d = run_once();
        post = d.t >= Fault_t;
        e_soc = 100 * abs(d.soc_est - d.soc);
        e_tc  = abs(d.tc_hat - d.tc);
        flag  = (d.tv < 0.5) | (d.iv < 0.5);
        T.Fault(r) = names{Fault_mode+1};  T.Scenario(r) = cases{c,2};  T.Diagnostics(r) = onoff(dg);
        T.SOC_err_max_pct(r) = max(e_soc(post));
        T.SOC_err_end_pct(r) = e_soc(end);
        T.Tcore_err_max_C(r) = max(e_tc(post));
        if dg && any(flag), T.Detect_delay_s(r) = d.t(find(flag, 1)) - Fault_t;
        else, T.Detect_delay_s(r) = NaN; end
        T.V_rejected(r) = sum(d.rej);
        T.Bias_end_A(r) = d.bias(end);
        F.(sprintf('%s_%s', names{Fault_mode+1}, onoff(dg))) = d;
    end
end
fprintf('\n=== Sensor faults injected at t = %d s ===\n', Fault_t);
disp(T);

% ---------------------------------------------------------------- yanlış alarm
SC = {'normal', 25, 1, 0.80, I_std;  'hot_day', 40, 1, 0.80, I_std; ...
      'cooling_fault', 35, 4, 0.80, I_std; ...
      'aggressive', 25, 1, 0.80, min(max(1.6*I_std, -40.7), 87.3); ...
      'deep_discharge', 25, 1, 0.40, I_std;  'long_charge', 25, 1, 0.20, -30*ones(36000,1)};
fprintf('=== False-alarm check (no fault, diagnostics on) ===\n');
fa_ok = true;
for s = 1:size(SC, 1)
    bms_init;  T_amb = SC{s,2};  Ru_factor = SC{s,3};  SOC0 = SC{s,4};
    t = (0:numel(SC{s,5})-1)' * Ts;  drive_ts = timeseries(SC{s,5}, t);  t_stop = t(end);
    d = run_once();
    nT = sum(d.tv < 0.5);  nI = sum(d.iv < 0.5);  nV = sum(d.rej);
    fprintf('%-15s T invalid: %5d   I invalid: %5d   V rejected: %3d\n', SC{s,1}, nT, nI, nV);
    fa_ok = fa_ok && nT == 0 && nI == 0 && nV == 0;
end

% ---------------------------------------------------------------- kabul
row = @(f, dg) find(T.Fault == f & T.Diagnostics == dg);
ok1 = T.V_rejected(row('v_spike','on')) == 44;
ok2 = T.Tcore_err_max_C(row('t_open','on')) < 1 && T.SOC_err_max_pct(row('t_open','on')) < 1;
ok3 = T.Tcore_err_max_C(row('t_frozen','on')) < 1;
ok4 = abs(T.Bias_end_A(row('i_offset','on')) - 3.5) < 0.3;
ok5 = T.Detect_delay_s(row('i_frozen','on')) <= 5.1;
fprintf('\nAcceptance 1 (all 44 voltage spikes rejected):              %s\n', pf(ok1));
fprintf('Acceptance 2 (open NTC: T_core err < 1 °C, SOC err < 1%%):   %s\n', pf(ok2));
fprintf('Acceptance 3 (frozen NTC: T_core err < 1 °C):                %s\n', pf(ok3));
fprintf('Acceptance 4 (3 A offset tracked by EKF bias state):         %s\n', pf(ok4));
fprintf('Acceptance 5 (frozen current detected within 5 s):           %s\n', pf(ok5));
fprintf('Acceptance 6 (no false alarm in 6 fault-free scenarios):     %s\n', pf(fa_ok));
save('fault_sonuclari.mat', 'T', 'F');

% ---------------------------------------------------------------- Şekil: kopuk NTC
a = F.t_open_off;  b = F.t_open_on;  m = a.t/60;
f = figure('Name', 'Open NTC', 'Color', 'w', 'Position', [60 40 1000 720]);
tiledlayout(2, 1, 'TileSpacing', 'compact');
nexttile; hold on; grid on;
plot(m, a.tm, 'Color', [0.7 0.7 0.7], 'LineWidth', 0.6);
plot(m, a.tc_hat, 'r', 'LineWidth', 1.2);
plot(m, b.tc_hat, 'b', 'LineWidth', 1.2);
plot(m, a.tc, 'k--', 'LineWidth', 1.4);
xline(Fault_t/60, 'k:', 'NTC open circuit', 'HandleVisibility', 'off');
ylim([-45 55]); ylabel('Temperature [°C]');
legend('Measured T_{surf} (CAN)', 'T_{core} estimate, no diagnostics', ...
       'T_{core} estimate, with diagnostics', 'True T_{core}', 'Location', 'southwest');
title('Open NTC during a cooling fault (35 °C, R_u ×4)');
nexttile; hold on; grid on;
plot(m, 100*(a.soc_est - a.soc), 'r', 'LineWidth', 1.2);
plot(m, 100*(b.soc_est - b.soc), 'b', 'LineWidth', 1.2);
xline(Fault_t/60, 'k:', 'HandleVisibility', 'off');
xlabel('Time [min]'); ylabel('SOC error [%]');
legend('No diagnostics (R_0 corrected with -40 °C)', 'With diagnostics (observer temperature)', ...
       'Location', 'northwest');
title('Effect on SOC estimation');
save_fig(f, 'sensor_fault_open_ntc.png');

% ---------------------------------------------------------------- yerel fonksiyonlar
function d = run_once()
    out = evalin('base', 'sim(''bms_twin_ekf'')');
    g = @(n) reshape(out.get(n), [], 1);
    d.t = out.tout(:);        d.soc = g('log_soc');     d.soc_est = g('log_soc_est');
    d.tc = g('log_tcore');    d.tc_hat = g('log_tc_hat'); d.tm = g('log_tm');
    d.tv = g('log_tvalid');   d.iv = g('log_ivalid');   d.rej = g('log_rej');
    d.bias = g('log_bias');
end
function s = onoff(x)
    if x, s = 'on'; else, s = 'off'; end
end
function s = pf(ok)
    if ok, s = 'PASS'; else, s = 'FAIL'; end
end
