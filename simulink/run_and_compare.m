%RUN_AND_COMPARE  Simulink modelini koşturur, Python referansıyla karşılaştırır.
%   Doğrulama 1: Simulink dijital ikizi == Python dijital ikizi (aynı akım profili)
%   Doğrulama 2: EKF SOC RMSE < %1.5 ve 60 s içinde yakınsama

bms_init;
out = sim('bms_twin_ekf');

n   = min(height(ref), numel(out.get('log_soc')));
t   = ref.t(1:n);
g   = @(name) reshape(out.get(name), [], 1);
cut = @(v) v(1:n);

soc = cut(g('log_soc')); vp = cut(g('log_vpack')); tc = cut(g('log_tcore')); ts = cut(g('log_tsurf'));
soc_est = cut(g('log_soc_est')); bias = cut(g('log_bias')); vm = cut(g('log_vm')); ocv = cut(g('log_ocv'));

% ---------------- Doğrulama 1: Python ile çapraz kontrol ----------------
e_soc = max(abs(soc - ref.soc(1:n))) * 100;
e_v   = max(abs(vp  - ref.v_pack(1:n))) * 1000;
e_tc  = max(abs(tc  - ref.t_core(1:n)));
e_ts  = max(abs(ts  - ref.t_surf(1:n)));
fprintf('\n=== Digital twin cross-validation: Simulink vs Python (max. absolute difference) ===\n');
fprintf('SOC    : %.2e %%\nV_pack : %.2e mV\nT_core : %.2e °C\nT_surf : %.2e °C\n', ...
        e_soc, e_v, e_tc, e_ts);
if e_v < 1, disp('-> PASS: both implementations are equivalent.');
else,       disp('-> WARNING: difference larger than expected, check.'); end

% ---------------- Doğrulama 2: EKF KPI ----------------
err   = soc_est - soc;
after = t > 60;
rmse_all = sqrt(mean(err.^2)) * 100;
rmse_60  = sqrt(mean(err(after).^2)) * 100;
idx      = find(abs(err) > 0.02, 1, 'last');
if isempty(idx), t_conv = 0; else, t_conv = t(idx); end
fprintf('\n=== EKF (true SOC 80%%, initial estimate 50%%) ===\n');
fprintf('RMSE (all)            : %.3f %%\n', rmse_all);
fprintf('RMSE (after 60 s)     : %.3f %%   [target < 1.5]\n', rmse_60);
fprintf('Last |error| > 2%% at : %.1f s     [target < 60]\n', t_conv);
fprintf('Estimated current bias: %.2f A (true 0.50 A)\n', bias(end));

% ---------------- Grafikler (tümü sonuclar/ klasörüne kaydedilir) ----------------
if ~exist('sonuclar', 'dir'), mkdir('sonuclar'); end
fA = figure('Name', 'Digital twin + EKF', 'Color', 'w', 'Position', [80 60 1000 850]);
tiledlayout(4, 1, 'TileSpacing', 'compact');
nexttile; plot(t, ref.i_pack(1:n)); ylabel('I_{pack} [A]'); grid on;
title('19S12P LG 21700 digital twin with EKF (Simulink)');
nexttile; plot(t, vm, 'Color', [0.6 0.75 0.9]); hold on;
plot(t, vp, 'b'); plot(t, ocv, 'k--'); ylabel('V_{pack} [V]'); grid on;
legend('Measured (CAN)', 'True', 'OCV', 'Location', 'southwest');
nexttile; plot(t, soc*100, 'k', 'LineWidth', 1.2); hold on;
plot(t, soc_est*100, 'r'); ylabel('SOC [%]'); grid on;
legend('True', 'EKF');
nexttile; plot(t, tc); hold on; plot(t, ts); ylabel('T [°C]'); xlabel('Time [s]');
legend('T_{core}', 'T_{surf}'); grid on;

fB = figure('Name', 'Python cross-validation', 'Color', 'w');
plot(t, (vp - ref.v_pack(1:n)) * 1000); grid on;
xlabel('Time [s]'); ylabel('V_{Simulink} - V_{Python} [mV]');
title('Cross-validation: Simulink vs Python');

save_fig(fA, 'twin_ekf_overview.png');
save_fig(fB, 'twin_crossvalidation.png');
fprintf('Figures saved to sonuclar/\n');
