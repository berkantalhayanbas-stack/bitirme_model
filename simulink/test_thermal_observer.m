%TEST_THERMAL_OBSERVER  2. hafta: çekirdek sıcaklığı gözlemcisinin testi.
%   Üç senaryo (normal, hot_day, cooling_fault) Simulink'te koşturulur.
%   Simulink bloğundaki EKF (g kestirimli), aynı ölçümler üzerinde çevrimdışı
%   çalıştırılan üç basit yöntemle karşılaştırılır:
%     - T_surf measured  : "çekirdek = yüzey" (en basit BMS)
%     - Open-loop model  : sadece model, nominal Ru, ölçüm düzeltmesi yok
%     - KF (R_u nominal) : ölçüm düzeltmeli ama soğutma sabit varsayılır
%   Kabul ölçütleri:
%     1) cooling_fault'ta T_core kestirim hatası < 1 °C (60 s sonrası, maks.)
%     2) Soğutma arızası Ru_hat > 2 x nominal ile algılanır, normal/hot_day'de yanlış alarm yok
%   Önkoşul: build_bms_model (Thermal_Observer içeren sürüm).
%   Çıktılar İngilizce; şekil sonuclar/ klasörüne, veriler thermal_sonuclari.mat'a.

bms_init;
RU_ALARM = 2 * P.ru;                         % 18 K/W
SC = {'normal', 25, 1; 'hot_day', 40, 1; 'cooling_fault', 35, 4};
methods = {'T_surf measured', 'Open-loop model', 'KF (R_u nominal)', 'EKF (g estimated)'};

nS = size(SC, 1);  nM = numel(methods);
MaxAbs = zeros(nM, nS);  RMSE = zeros(nM, nS);
Th = struct();
for s = 1:nS
    bms_init;  T_amb = SC{s,2};  Ru_factor = SC{s,3};
    fprintf('[%d/%d] %s ...\n', s, nS, SC{s,1});
    out = sim('bms_twin_ekf');
    g = @(n) reshape(out.get(n), [], 1);
    t = out.tout(:);  tc = g('log_tcore');
    im = g('log_im'); vm = g('log_vm'); tm = g('log_tm'); se = g('log_soc_est');

    % --- çevrimdışı karşılaştırma yöntemleri (aynı ölçümler) ---
    est = zeros(numel(t), nM);
    est(:,1) = tm;
    est(:,2) = run_offline(im, vm, se, tm, T_amb, P, true);    % açık çevrim
    est(:,3) = run_offline(im, vm, se, tm, T_amb, P, false);   % KF, g sabit
    est(:,4) = g('log_tc_hat');                                % Simulink bloğu

    after = t > 60;
    for m = 1:nM
        e = est(after, m) - tc(after);
        MaxAbs(m, s) = max(abs(e));
        RMSE(m, s)   = sqrt(mean(e.^2));
    end
    ru = g('log_ru_hat');
    Th.(SC{s,1}) = struct('t', t, 'tc', tc, 'est', est, 'ru', ru, ...
        'ru_true', P.ru * Ru_factor, 'ru_max', max(ru(after)), ...
        't_alarm', first_or_nan(t(ru > RU_ALARM)));
end

% ---------------------------------------------------------------- Tablolar
names = matlab.lang.makeValidName(SC(:,1))';
fprintf('\n=== T_core estimation error after 60 s: max |error| [°C] ===\n');
disp(array2table(round(MaxAbs, 3), 'RowNames', methods, 'VariableNames', names));
fprintf('=== T_core estimation error after 60 s: RMSE [°C] ===\n');
disp(array2table(round(RMSE, 3), 'RowNames', methods, 'VariableNames', names));

fprintf('=== Cooling estimate (R_u nominal %.1f K/W, alarm > %.0f K/W) ===\n', P.ru, RU_ALARM);
for s = 1:nS
    d = Th.(SC{s,1});
    fprintf('%-14s true R_u %5.1f K/W | estimate at end %5.2f | max after 60 s %5.2f | alarm at %s\n', ...
        SC{s,1}, d.ru_true, d.ru(end), d.ru_max, alarm_str(d.t_alarm));
end

ok1 = MaxAbs(4, 3) < 1.0;
ok2 = ~isnan(Th.cooling_fault.t_alarm) && Th.normal.ru_max < RU_ALARM && Th.hot_day.ru_max < RU_ALARM;
fprintf('\nAcceptance 1 (cooling fault, max |T_core error| < 1 °C): %s (%.3f °C)\n', pf(ok1), MaxAbs(4,3));
fprintf('Acceptance 2 (fault detected, no false alarm):          %s\n', pf(ok2));
save('thermal_sonuclari.mat', 'Th', 'MaxAbs', 'RMSE', 'methods', 'SC');

% ---------------------------------------------------------------- Şekil
d = Th.cooling_fault;  c = lines(4);
f = figure('Name', 'Thermal observer', 'Color', 'w', 'Position', [60 40 1000 820]);
tiledlayout(3, 1, 'TileSpacing', 'compact');
nexttile; hold on; grid on;
plot(d.t/60, d.est(:,1), 'Color', [c(1,:) 0.35], 'LineWidth', 0.5);
for m = 2:4, plot(d.t/60, d.est(:,m), 'Color', c(m,:), 'LineWidth', 1.1); end
plot(d.t/60, d.tc, 'k', 'LineWidth', 1.6);
ylabel('Temperature [°C]'); legend([methods, {'True T_{core}'}], 'Location', 'northwest');
title('Cooling fault (35 °C ambient, R_u ×4): core temperature estimation');
nexttile; hold on; grid on;
plot(d.t/60, d.est(:,1) - d.tc, 'Color', [c(1,:) 0.35], 'LineWidth', 0.5);
for m = 2:4, plot(d.t/60, d.est(:,m) - d.tc, 'Color', c(m,:), 'LineWidth', 1.1); end
yline([-1 1], 'r:', 'HandleVisibility', 'off');
ylim([-6 3]); ylabel('T_{core} error [°C]');
title('Estimation error (dotted: ±1 °C target)');
nexttile; hold on; grid on;
plot(d.t/60, d.ru, 'LineWidth', 1.2);
yline(d.ru_true, 'k--', 'True R_u');  yline(P.ru, 'g:', 'Nominal R_u');
yline(RU_ALARM, 'r--', 'Alarm threshold');
if ~isnan(d.t_alarm), xline(d.t_alarm/60, 'r:', sprintf('Detected at %.0f s', d.t_alarm)); end
xlabel('Time [min]'); ylabel('Estimated R_u [K/W]');
title('Online estimate of the surface-to-ambient thermal resistance');
save_fig(f, 'thermal_observer_cooling_fault.png');

% ---------------------------------------------------------------- yerel fonksiyonlar
function tc = run_offline(im, vm, se, tm, T_amb, P, open_loop)
    % open_loop = true : ölçüm düzeltmesi yok (R çok büyük -> K ~ 0)
    % open_loop = false: g sabit doğrusal KF
    if open_loop
        P.th_R = 1e12;  x = [T_amb; T_amb; 1/P.ru];
    else
        x = [tm(1); tm(1); 1/P.ru];
    end
    Pk = diag([P.th_P0(1:2) 0]);
    tc = zeros(size(im));
    for k = 1:numel(im)
        [x, Pk] = thermal_obs_step(x, Pk, im(k), vm(k), se(k), tm(k), T_amb, P, false, true);
        tc(k) = x(1);
    end
end
function s = alarm_str(t)
    if isnan(t), s = 'none'; else, s = sprintf('%.0f s', t); end
end
function s = pf(ok)
    if ok, s = 'PASS'; else, s = 'FAIL'; end
end
function v = first_or_nan(x)
    if isempty(x), v = NaN; else, v = x(1); end
end
