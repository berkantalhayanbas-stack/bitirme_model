%SCENARIOS  Senaryo kütüphanesi: 6 işletme koşulunu tek komutla koşturur.
%   Kullanım:  >> scenarios
%   Önkoşul:   build_bms_model bir kez çalıştırılmış olmalı (SOC0 girişli sürüm).
%
%   Senaryolar:
%     1 normal          25 °C, normal soğutma, standart çevrim, SOC %80
%     2 hot_day         40 °C ortam
%     3 cooling_fault   35 °C ortam + fan arızası (yüzey-ortam ısıl direnci x4)
%     4 aggressive      akım profili x1.6 (deşarj 87.3 A, rejen -40.7 A: veri sayfası 1.5C / 0.7C)
%     5 deep_discharge  SOC %40'tan başlayıp ~%4'e kadar
%     6 long_charge     SOC %20'den 30 A (0.5C) sabit akımla 1 saat şarj
%
%   Tüm ekran ve grafik çıktıları İngilizcedir (tez dili).
%
%   Çıktılar:
%     - Komut penceresinde özet tablo
%     - ../results/ klasörüne 3 grafik (PNG)
%     - senaryo_sonuclari.mat: tüm zaman serileri (yaşlanma modeli ve ML için)

bms_init;                                   % P, Ts, ref, sensör parametreleri
I_std = ref.i_pack;                         % standart sürüş çevrimi (10 Hz)

sc = [ ...
  senaryo('normal',          'Normal: 25 °C',                     25, 1, 0.80, I_std), ...
  senaryo('hot_day',         'Hot day: 40 °C',                    40, 1, 0.80, I_std), ...
  senaryo('cooling_fault',   'Cooling fault: 35 °C, R_u ×4',      35, 4, 0.80, I_std), ...
  senaryo('aggressive',      'Aggressive driving: current ×1.6', 25, 1, 0.80, min(max(1.6*I_std, -40.7), 87.3)), ...
  senaryo('deep_discharge',  'Deep discharge: from 40% SOC',      25, 1, 0.40, I_std), ...
  senaryo('long_charge',     'Long charge: 0.5C from 20% SOC',    25, 1, 0.20, -30*ones(36000, 1)) ];

N = numel(sc);
R = struct();                               % zaman serileri
ozet = table('Size', [N 8], ...
  'VariableTypes', {'string','double','double','double','double','double','double','double'}, ...
  'VariableNames', {'Scenario','T_core_max_C','T_surf_max_C','V_cell_min_V', ...
                    'SOC_start_pct','SOC_end_pct','EKF_RMSE_pct','Energy_kWh'});

for k = 1:N
    fprintf('[%d/%d] %s ...\n', k, N, sc(k).aciklama);

    % --- Senaryo değişkenlerini base workspace'e yaz (model buradan okur) ---
    T_amb     = sc(k).T_amb;
    Ru_factor = sc(k).Ru;
    SOC0      = sc(k).SOC0;
    t         = (0:numel(sc(k).I)-1)' * Ts;
    drive_ts  = timeseries(sc(k).I, t);
    t_stop    = t(end);

    out = sim('bms_twin_ekf');

    g = @(name) reshape(out.get(name), [], 1);
    d.t       = out.tout(:);
    d.i       = g('log_i');
    d.v_pack  = g('log_vpack');
    d.soc     = g('log_soc');
    d.soc_est = g('log_soc_est');
    d.t_core  = g('log_tcore');
    d.t_surf  = g('log_tsurf');
    d.ocv     = g('log_ocv');
    d.T_amb   = T_amb;  d.Ru = Ru_factor;
    R.(sc(k).ad) = d;

    after = d.t > 60;
    ozet.Scenario(k)       = sc(k).ad;
    ozet.T_core_max_C(k)   = max(d.t_core);
    ozet.T_surf_max_C(k)   = max(d.t_surf);
    ozet.V_cell_min_V(k)   = min(d.v_pack) / P.Ns;
    ozet.SOC_start_pct(k)  = 100 * SOC0;
    ozet.SOC_end_pct(k)    = 100 * d.soc(end);
    ozet.EKF_RMSE_pct(k)   = 100 * sqrt(mean((d.soc_est(after) - d.soc(after)).^2));
    ozet.Energy_kWh(k)     = sum(d.v_pack .* d.i) * Ts / 3.6e6;
end

fprintf('\n=== Scenario summary ===\n');
disp(ozet);
save('senaryo_sonuclari.mat', 'R', 'ozet', 'sc');

% ---------------------------------------------------------------- Grafikler
if ~exist(fullfile('..', 'results'), 'dir'), mkdir(fullfile('..', 'results')); end
renk = lines(N);

f1 = figure('Name', 'Scenarios: core temperature', 'Color', 'w', 'Position', [60 60 900 450]);
hold on; grid on;
for k = 1:N
    d = R.(sc(k).ad);
    plot(d.t/60, d.t_core, 'Color', renk(k,:), 'LineWidth', 1.2, 'DisplayName', sc(k).aciklama);
end
yline(45, 'k--', '45 °C (candidate derating threshold)', 'HandleVisibility', 'off');
xlabel('Time [min]'); ylabel('T_{core} [°C]');
title('Cell core temperature by scenario');
legend('Location', 'eastoutside');
save_fig(f1, 'senaryo_T_core.png');

f2 = figure('Name', 'Scenarios: SOC', 'Color', 'w', 'Position', [80 80 900 450]);
hold on; grid on;
for k = 1:N
    d = R.(sc(k).ad);
    plot(d.t/60, 100*d.soc, 'Color', renk(k,:), 'LineWidth', 1.2, 'DisplayName', sc(k).aciklama);
end
xlabel('Time [min]'); ylabel('SOC [%]');
title('True state of charge by scenario');
legend('Location', 'eastoutside');
save_fig(f2, 'senaryo_SOC.png');

f3 = figure('Name', 'Scenarios: EKF tracking', 'Color', 'w', 'Position', [100 40 1000 700]);
tiledlayout(3, 2, 'TileSpacing', 'compact');
for k = 1:N
    d = R.(sc(k).ad);
    nexttile; hold on; grid on;
    plot(d.t/60, 100*d.soc,     'k', 'LineWidth', 1.2);
    plot(d.t/60, 100*d.soc_est, 'r');
    title(sprintf('%s  (RMSE %.2f%%)', sc(k).aciklama, ozet.EKF_RMSE_pct(k)), 'FontWeight', 'normal');
    ylabel('SOC [%]');
    if k == 1, legend('True', 'EKF', 'Location', 'best'); end
end
xlabel('Time [min]');
save_fig(f3, 'senaryo_EKF.png');

fprintf('Figures saved to ../results/, data saved to senaryo_sonuclari.mat\n');

% ---------------------------------------------------------------- Yerel fonksiyon
function s = senaryo(ad, aciklama, T_amb, Ru, SOC0, I)
    s = struct('ad', ad, 'aciklama', aciklama, 'T_amb', T_amb, 'Ru', Ru, ...
               'SOC0', SOC0, 'I', I(:));
end
