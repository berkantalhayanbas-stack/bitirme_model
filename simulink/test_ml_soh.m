%TEST_ML_SOH  ML ile SOH tahmini, uçtan uca (Simulink): yaşlanmış paket demosu.
%   Python karşılığı: ml/05_yaslanmis_hucre.py
%   Dört test hücresi (Kirkaldy verisinden gerçek SOH ve direnç oranı) için:
%     1) 3 öğrenme sürüşü: yaşlanmış ikiz, BMS yeni hücre sanıyor; Rint_Estimator direnç
%        oranını biriktirir (birikimler sürüşten sürüşe taşınır = BMS EEPROM'u)
%     2) SOH_ML bloğu (karar ağacı, ml/04_model_aktar.py) SOH'yi tahmin eder
%     3) değerlendirme sürüşü, aynı gürültüyle üç BMS:
%          New-cell BMS : Bms_Q = Bms_R = 1
%          ML-updated   : Bms_Q = SOH_ML, Bms_R = rr_hat
%          Oracle       : gerçek değerler
%   Not: buradaki ağaç tüm veriyle eğitilmiş (dağıtılan model); bu hücrelerin koşulları
%   eğitimde vardı. Görülmemiş koşuldaki dürüst hata 3. adımdaki çapraz doğrulamadır
%   (RMSE ~%3). Python demosu her hücre için koşulunu dışarıda bırakarak eğitir.
%   Önkoşul: build_bms_model (Rint_Estimator + SOH_ML içeren sürüm).
%   Çıktılar İngilizce; şekil ../results/ klasörüne, veriler ml_soh_sonuclari.mat'a.

bms_init;
% cell, SOH, R ratio, usage = [efc days T_mean SOC_mean DoD]   (ml/dataset.csv)
C = { '3C',   0.950084, 1.055291, [157.297176  58  14.799443 0.925 0.15];
      '2,2B', 0.900183, 1.031073, [779.223299 208  16.975018 0.775 0.15];
      '5G',   0.849871, 1.222894, [553.409337 163  42.776417 0.500 1.00];
      '1B',   0.799444, 1.244982, [791.093767 208  18.701658 0.150 0.30] };
N_LEARN = 3;
nC = size(C, 1);
T = table('Size', [nC 12], 'VariableTypes', [{'string'}, repmat({'double'}, 1, 11)], ...
    'VariableNames', {'Cell','SOH_true','SOH_ML','rr_true','rr_hat','rr_err_1drive_pct', ...
                      'rr_err_pct','Events','RMSE_newcell','RMSE_ML','RMSE_oracle','End_err_ML'});
E = struct();
for c = 1:nC
    soh = C{c,2};  rr = C{c,3};
    num = 0;  den = 0;  rr_drv = zeros(1, N_LEARN);
    for k = 1:N_LEARN                                   % öğrenme sürüşleri
        bms_init;  Age_Q = soh;  Age_R = rr;  Usage = C{c,4};
        Rint_num0 = num;  Rint_den0 = den;
        seed_v = 100 + 3*k;  seed_i = 101 + 3*k;  seed_t = 102 + 3*k;
        fprintf('[%s] learning drive %d/%d ...\n', C{c,1}, k, N_LEARN);
        out = sim('bms_twin_ekf');
        num = lastv(out, 'log_rint_num');  den = lastv(out, 'log_rint_den');
        rr_drv(k) = lastv(out, 'log_rr');
    end
    rr_hat  = rr_drv(end);
    soh_hat = lastv(out, 'log_soh_ml');
    n_ev    = lastv(out, 'log_rint_n');
    % değerlendirme sürüşü
    cfg = {'New-cell BMS', 1, 1; 'ML-updated', soh_hat, rr_hat; 'Oracle', soh, rr};
    for b = 1:3
        bms_init;  Age_Q = soh;  Age_R = rr;  Usage = C{c,4};
        Bms_Q = cfg{b,2};  Bms_R = cfg{b,3};
        seed_v = 200;  seed_i = 201;  seed_t = 202;
        fprintf('[%s] evaluation drive: %s ...\n', C{c,1}, cfg{b,1});
        out = sim('bms_twin_ekf');
        g = @(n) reshape(out.get(n), [], 1);
        ev.t = out.tout(:);  ev.soc = g('log_soc');  ev.est(:, b) = g('log_soc_est');
    end
    after = ev.t > 60;
    err = 100 * (ev.est - ev.soc);
    rm = sqrt(mean(err(after, :).^2));
    T(c, :) = {C{c,1}, 100*soh, 100*soh_hat, rr, rr_hat, 100*(rr_drv(1)/rr - 1), ...
               100*(rr_hat/rr - 1), n_ev, rm(1), rm(2), rm(3), err(end, 2)};
    E.(matlab.lang.makeValidName(['c' C{c,1}])) = ev;
    clear ev
end

fprintf('\n=== ML SOH on aged packs (Simulink) ===\n');
disp(T);
ok1 = all(abs(T.rr_err_pct) < 2);
ok2 = all(T.RMSE_ML <= T.RMSE_newcell);
ok3 = mean(T.RMSE_ML) < 0.5 * mean(T.RMSE_newcell);
fprintf('Acceptance 1 (online resistance within 2 %% after %d drives):   %s\n', N_LEARN, pf(ok1));
fprintf('Acceptance 2 (ML-updated BMS never worse than new-cell BMS):   %s\n', pf(ok2));
fprintf('Acceptance 3 (ML halves the mean SOC RMSE on aged packs):      %s\n', pf(ok3));
save('ml_soh_sonuclari.mat', 'T', 'E', 'C');

% ---------------------------------------------------------------- Şekil: en yaşlı hücre
[~, w] = min(T.SOH_true);
ev = E.(matlab.lang.makeValidName(['c' C{w,1}]));
nm = {'New-cell BMS', 'ML-updated', 'Oracle'};  col = [0.84 0.15 0.16; 0.12 0.47 0.71; 0.17 0.63 0.17];
f = figure('Name', 'ML SOH demo', 'Color', 'w', 'Position', [60 40 1000 720]);
tiledlayout(2, 1, 'TileSpacing', 'compact');
nexttile; hold on; grid on;
plot(ev.t/60, 100*ev.soc, 'k', 'LineWidth', 1.6);
for b = 1:3, plot(ev.t/60, 100*ev.est(:, b), 'Color', col(b,:), 'LineWidth', 1.0); end
ylabel('SOC [%]'); legend([{'True SOC'}, nm], 'Location', 'northeast');
title(sprintf('Aged pack (cell %s: SOH %.1f %%, R x%.2f); ML estimate SOH %.1f %%, R x%.2f', ...
      C{w,1}, T.SOH_true(w), T.rr_true(w), T.SOH_ML(w), T.rr_hat(w)));
nexttile; hold on; grid on;
for b = 1:3, plot(ev.t/60, 100*(ev.est(:, b) - ev.soc), 'Color', col(b,:), 'LineWidth', 1.0); end
ylim([-4 4]); xlabel('Time [min]'); ylabel('SOC error [%]'); legend(nm, 'Location', 'northeast');
save_fig(f, 'ml_aged_pack_soc_simulink.png');

function v = lastv(out, name)
    x = out.get(name);  v = x(end);
end
function s = pf(ok)
    if ok, s = 'PASS'; else, s = 'FAIL'; end
end
