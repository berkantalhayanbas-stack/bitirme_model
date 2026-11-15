%AGING_MODEL  Kalibre yaşlanma modelini senaryo kütüphanesine uygular.
%   Önkoşul: scenarios.m çalıştırılmış olmalı (senaryo_sonuclari.mat).
%   Gerekli toolbox: Signal Processing Toolbox (rainflow).
%
%   Yöntem (her senaryo bir "günlük kullanım" olarak):
%     1. Sürüş SOC izi + başlangıç SOC'sine 0.3C ile geri şarj (ortam sıcaklığında)
%     2. rainflow ile SOC izi çevrimlere ayrılır: sayı, derinlik (DoD), ortalama SOC
%     3. Her çevrimin sıcaklığı: o çevrim süresince ortalama yüzey sıcaklığı
%        (kalibrasyon verisi yüzey sıcaklığıyla ölçüldüğü için T_surf kullanılır)
%     4. Stres ağırlıklı EFC:  E = sum( sayı * DoD * S(DoD, SOC_ort, T) )
%     5. Takvim: araç günün geri kalanında başlangıç SOC'sinde, ortam sıcaklığında park eder
%     6. N gün sonra kayıp: fade = a*(N*E)^z + alpha(V_park, T_amb)*N^0.75 ; ömür sonu (%20)
%
%   Tüm ekran ve grafik çıktıları İngilizcedir (tez dili); şekiller sonuclar/ klasörüne.

load('senaryo_sonuclari.mat', 'R', 'sc');
A        = aging_params();
Pb       = bms_param_struct();
Q_cell   = 4.85;            % Ah (Kirkaldy C/10 BoL ortalaması)
trip_km  = 28.68;           % standart sürüş çevrimi mesafesi [km]
ds       = 10;              % 10 Hz -> 1 Hz (rainflow için yeterli)
N        = numel(sc);

res = table('Size', [N 10], ...
  'VariableTypes', {'string','double','double','double','double','double','double','double','double','double'}, ...
  'VariableNames', {'Scenario','EFC_per_day','Mean_cycle_stress','Cycle_fade_1yr_pct', ...
                    'Calendar_fade_1yr_pct','Total_fade_1yr_pct','Rel_to_normal', ...
                    'Years_to_EOL','km_to_EOL','V_park'});
fadefun = cell(N, 1);

for k = 1:N
    d   = R.(sc(k).ad);
    soc = d.soc(1:ds:end);   T = d.t_surf(1:ds:end);
    soc0 = sc(k).SOC0;

    % --- günlük kullanım: başlangıç SOC'sine 0.3C ile geri dön (şarj ortam sıcaklığında)
    if ~strcmp(sc(k).ad, 'long_charge') && soc(end) < soc0
        n_ch = ceil((soc0 - soc(end)) / (0.3/3600));          % 1 s adımlarla
        soc  = [soc; linspace(soc(end), soc0, n_ch)'];
        T    = [T;   d.T_amb*ones(n_ch, 1)];
    end

    % --- rainflow: [sayı, aralık, ortalama, başlangıç, bitiş]
    c   = rainflow(soc);
    cnt = c(:,1); dod = c(:,2); mu = c(:,3);
    i1  = max(1, round(c(:,4))); i2 = min(numel(T), max(i1, round(c(:,5))));
    Tc  = arrayfun(@(a, b) mean(T(a:b)), i1, i2);

    S   = aging_stress(dod, mu, Tc, A);
    efc = sum(cnt .* dod);
    E   = sum(cnt .* dod .* S);

    % --- takvim: park SOC'si = günün sonundaki SOC, park sıcaklığı = ortam
    V_park = interp1(Pb.soc_tab, Pb.ocv_tab, min(max(soc(end), 0), 1));
    alpha  = aging_calendar(V_park, d.T_amb, A);
    f      = @(days) A.a*(E*days).^A.z + alpha*days.^A.cal_exp;
    days_eol = fzero(@(x) f(x) - A.fade_eol, [1 1e6]);

    res.Scenario(k)              = sc(k).ad;
    res.EFC_per_day(k)           = efc;
    res.Mean_cycle_stress(k)     = E / efc;
    res.Cycle_fade_1yr_pct(k)    = 100 * A.a * (365*E)^A.z;
    res.Calendar_fade_1yr_pct(k) = 100 * alpha * 365^A.cal_exp;
    res.Total_fade_1yr_pct(k)    = 100 * f(365);
    res.Years_to_EOL(k)          = days_eol / 365;
    res.km_to_EOL(k)             = days_eol * trip_km;
    res.V_park(k)                = V_park;
    fadefun{k} = f;
end
res.Rel_to_normal = res.Total_fade_1yr_pct / res.Total_fade_1yr_pct(1);
res.km_to_EOL(strcmp(res.Scenario, 'long_charge')) = NaN;

fprintf('\n=== Aging assessment per scenario (one run per day + parking, EOL = 20%% fade) ===\n');
disp(res);
fprintf(['Note: temperatures above %.1f °C exceed the calibration data; the Millner rule ' ...
         '(x2 per 10 K) is applied there as a conservative extrapolation.\n'], A.T_data_max);
save('aging_sonuclari.mat', 'res', 'A');

% ---------------------------------------------------------------- grafikler
if ~exist('sonuclar', 'dir'), mkdir('sonuclar'); end
lbl = string({sc.aciklama});

f1 = figure('Name', 'Aging: relative rate', 'Color', 'w', 'Position', [60 60 900 420]);
b = barh([res.Cycle_fade_1yr_pct res.Calendar_fade_1yr_pct], 'stacked');
b(1).FaceColor = [0.30 0.45 0.70]; b(2).FaceColor = [0.85 0.55 0.25];
set(gca, 'YTick', 1:N, 'YTickLabel', lbl, 'YDir', 'reverse'); grid on;
for k = 1:N
    text(res.Total_fade_1yr_pct(k), k, sprintf('  %.1f%% (%.2f×)', res.Total_fade_1yr_pct(k), res.Rel_to_normal(k)), ...
         'VerticalAlignment', 'middle');
end
xlabel('Capacity fade after one year [%]'); legend('Cycle aging', 'Calendar aging (parking)', 'Location', 'southeast');
title('First-year capacity fade per scenario (cycle: calibrated on LG M50T data; calendar: Schmalstieg 2014)');
save_fig(f1, 'aging_relative_rate.png');

f2 = figure('Name', 'Aging: projected fade', 'Color', 'w', 'Position', [80 80 900 450]);
hold on; grid on; yrs = linspace(0, 10, 300); renk = lines(N);
for k = 1:N
    plot(yrs, 100*fadefun{k}(365*yrs), 'Color', renk(k,:), 'LineWidth', 1.4, 'DisplayName', lbl(k));
end
yline(100*A.fade_eol, 'k--', 'End of life (20% fade)', 'HandleVisibility', 'off');
xlabel('Years (one scenario run per day)'); ylabel('Capacity fade [%]'); ylim([0 40]);
title('Projected capacity fade if each scenario is repeated daily (incl. parking)');
legend('Location', 'eastoutside');
save_fig(f2, 'aging_projected_fade.png');
fprintf('Figures saved to sonuclar/, results saved to aging_sonuclari.mat\n');
