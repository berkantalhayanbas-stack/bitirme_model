%TEST_WEEK1_EXTRAS  1. haftanın iki ek özelliğini test eder (kabul ölçütleriyle).
%   A) Akım sınırlayıcı: I_allow_dis düşünce paket akımı da düşmeli (ve ısınma azalmalı).
%   B) Zayıf hücre: derin deşarjda zayıf seri grup 2.8 V sınırına ortalamadan önce ulaşmalı.
%   Önkoşul: build_bms_model (Current_Limiter ve Weak_on içeren sürüm).
%   Tüm ekran ve grafik çıktıları İngilizcedir; şekiller sonuclar/ klasörüne.

bms_init;
V_LIM = P.v_min;                              % tasarım alt sınırı 2.8 V

% ======================================================= A) Current limiter
cases_A = [P.i_max_dis*P.Np, 45];             % 87.3 A (veri sayfası) ve 45 A (derating)
A = struct();
for k = 1:2
    bms_init;  I_allow_dis = cases_A(k);
    out = sim('bms_twin_ekf');
    g = @(n) reshape(out.get(n), [], 1);
    A(k).t = out.tout(:); A(k).idem = g('log_idem'); A(k).i = g('log_i');
    A(k).tc = g('log_tcore'); A(k).soc = g('log_soc'); A(k).lim = g('log_limited');
end
fprintf('\n=== A) Current limiter (normal scenario) ===\n');
fprintf('%-22s %12s %12s %14s %12s\n', 'I_allow_dis [A]', 'max I [A]', 'T_core max', 'time limited', 'SOC end');
for k = 1:2
    fprintf('%-22.1f %12.2f %10.2f °C %12.1f %% %10.2f %%\n', cases_A(k), max(A(k).i), max(A(k).tc), ...
            100*mean(A(k).lim), 100*A(k).soc(end));
end
okA = max(A(2).i) <= cases_A(2) + 1e-6 && max(A(2).tc) < max(A(1).tc);
fprintf('Acceptance (pack current follows I_allow and heating is reduced): %s\n', pf(okA));

fA = figure('Name', 'Current limiter test', 'Color', 'w', 'Position', [60 60 950 600]);
tiledlayout(2, 1, 'TileSpacing', 'compact');
nexttile; z = A(1).t <= 600;
plot(A(1).t(z), A(1).idem(z), 'Color', [0.6 0.6 0.6], 'LineWidth', 1.0); hold on; grid on;
plot(A(2).t(z), A(2).i(z), 'r', 'LineWidth', 1.2);
yline(cases_A(2), 'r--', sprintf('I_{allow,dis} = %.0f A', cases_A(2)), 'HandleVisibility', 'off');
ylabel('Pack current [A]'); legend('Driver demand', 'Applied (limited)', 'Location', 'southeast');
title('Current limiter: BMS-allowed current caps the driver demand (first 10 min)');
nexttile; hold on; grid on;
plot(A(1).t/60, A(1).tc, 'k', 'LineWidth', 1.2); plot(A(2).t/60, A(2).tc, 'r', 'LineWidth', 1.2);
xlabel('Time [min]'); ylabel('T_{core} [°C]');
legend(sprintf('I_{allow,dis} = %.1f A', cases_A(1)), sprintf('I_{allow,dis} = %.0f A', cases_A(2)), 'Location', 'southeast');
title('Effect of current limiting on cell core temperature');
save_fig(fA, 'limiter_test.png');

% ======================================================= B) Weak cell
B = struct();
for k = 1:2
    bms_init;  SOC0 = 0.40;  Weak_on = k - 1;
    out = sim('bms_twin_ekf');
    g = @(n) reshape(out.get(n), [], 1);
    B(k).t = out.tout(:); B(k).vmin = g('log_vcellmin'); B(k).vavg = g('log_vpack')/P.Ns;
    B(k).socw = g('log_socweak'); B(k).soc = g('log_soc');
end
t_cross = @(t, v) first_or_nan(t(v < V_LIM));
t_avg  = t_cross(B(1).t, B(1).vmin);          % tüm gruplar özdeş
t_weak = t_cross(B(2).t, B(2).vmin);          % zayıf grup
fprintf('\n=== B) Weak series group (deep discharge from 40%% SOC) ===\n');
fprintf('Weak group: capacity x%.2f, resistances x%.2f\n', P.weak_cap, P.weak_r);
fprintf('First time below %.1f V  - identical cells: %7.0f s\n', V_LIM, t_avg);
fprintf('First time below %.1f V  - with weak group: %7.0f s  (%.0f s earlier)\n', V_LIM, t_weak, t_avg - t_weak);
fprintf('Minimum group voltage - identical: %.3f V, weak: %.3f V\n', min(B(1).vmin), min(B(2).vmin));
fprintf('SOC at end - average cell: %.1f %%, weak group: %.1f %%\n', 100*B(2).soc(end), 100*B(2).socw(end));
okB = t_weak < t_avg;
fprintf('Acceptance (weak group reaches V_min before the average): %s\n', pf(okB));

fB = figure('Name', 'Weak cell test', 'Color', 'w', 'Position', [80 80 950 450]);
hold on; grid on;
plot(B(1).t/60, B(1).vmin, 'k', 'LineWidth', 1.2);
plot(B(2).t/60, B(2).vavg, 'Color', [0.3 0.45 0.7], 'LineWidth', 1.0);
plot(B(2).t/60, B(2).vmin, 'r', 'LineWidth', 1.2);
yline(V_LIM, 'k--', sprintf('Design limit %.1f V', V_LIM), 'HandleVisibility', 'off');
xlabel('Time [min]'); ylabel('Cell (series group) voltage [V]');
legend('All groups identical', 'Average group (with weak group present)', 'Weak group (-10% capacity, +20% resistance)', ...
       'Location', 'southwest');
title('Deep discharge from 40% SOC: the weak series group limits the pack');
save_fig(fB, 'weak_cell_test.png');

% ---------------------------------------------------------------- yerel fonksiyonlar
function s = pf(ok)
    if ok, s = 'PASS'; else, s = 'FAIL'; end
end
function v = first_or_nan(x)
    if isempty(x), v = NaN; else, v = x(1); end
end
