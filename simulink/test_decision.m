%TEST_DECISION  3. hafta: güvenli karar mekanizmasının testi (FMEA test matrisi).
%   A) Birim test vektörleri: twin/test_decision_unit.py'nin ürettiği girdiler (decision_vectors.csv)
%      decision_logic.m'ye verilir; çıktılar Python ile BİREBİR aynı olmalı (12 birim test).
%   B) Kapalı çevrim (Simulink, Dec_on = 1), karar mekanizması yok/var karşılaştırmalı:
%      S1 normal sürüş                            -> yanlış kısıtlama yok
%      S2 40 °C + soğutma arızası + agresif sürüş -> T_core < 55 °C (mekanizmasız aşıyor)
%      S3 %40'tan derin deşarj + zayıf grup       -> V_cell_min >= 2.8 V (mekanizmasız 2.06 V)
%      S4 %80'den 0.7C tam şarj + zayıf grup      -> V_cell_max <= 4.2 V, kendiliğinden CC-CV
%      S5 10 °C'de şarj                           -> veri sayfası 0.3C (17.5 A) sınırı
%      S6 NTC kopması (1200 s)                    -> 0.1 s içinde LIMP-HOME, taban %25
%      S7 5 °C'de sürüş                           -> veri sayfası 0.5C (29.1 A) deşarj sınırı
%   Önkoşul: build_bms_model (Decision bloğu içeren sürüm).
%   Çıktılar İngilizce; şekil sonuclar/decision_closed_loop.png, veriler decision_sonuclari.mat

% ================================================================== A) birim test vektörleri
V = readtable('decision_vectors.csv');
n = height(V);
out = zeros(n, 5);
for k = 1:n
    if V.reset(k), clear decision_logic; end
    [s, a, b, p, c] = decision_logic(V.I_meas(k), V.V_min(k), V.V_max(k), V.Tc_hat(k), V.Ts_hat(k), ...
        V.Ru_hat(k), V.SOC_est(k), V.bias_est(k), V.T_valid(k), V.I_valid(k), V.CAN_ok(k));
    out(k, :) = [s a b p c];
end
clear decision_logic
ref5 = [V.state V.i_dis V.i_chg V.psi V.cause];
d_state = sum(out(:,1) ~= ref5(:,1));
d_cause = sum(out(:,5) ~= ref5(:,5));
d_cur   = max(max(abs(out(:,2:4) - ref5(:,2:4))));
fprintf('=== A) Unit-test vectors: MATLAB decision_logic vs Python decision.py (%d samples, %d tests) ===\n', ...
        n, numel(unique(V.test)));
fprintf('State mismatches: %d   cause mismatches: %d   max |current/psi difference|: %.2e\n', d_state, d_cause, d_cur);
okA = d_state == 0 && d_cause == 0 && d_cur < 1e-9;
fprintf('Acceptance A (MATLAB and Python logic identical): %s\n\n', pf(okA));

% ================================================================== B) kapalı çevrim
bms_init;
I_std = ref.i_pack;
I_agg = min(max(1.6*I_std, -40.7), 87.3);
I_chg = -40.7 * ones(18000, 1);
%      ad              açıklama                           T_amb Ru SOC0 weak fault drive  dec
S = { 'S1_normal',     'Normal drive, 25 °C',              25, 1, 0.80, 0, 0, I_std, [1];
      'S2_thermal',    '40 °C + cooling fault + aggressive', 40, 4, 0.80, 0, 0, I_agg, [0 1];
      'S3_deep',       'Deep discharge + weak group',      25, 1, 0.40, 1, 0, I_std, [0 1];
      'S4_charge',     'Full charge 0.7C + weak group',    25, 1, 0.80, 1, 0, I_chg, [0 1];
      'S5_cold_chg',   'Charge at 10 °C',                  10, 1, 0.30, 0, 0, I_chg, [0 1];
      'S6_ntc_open',   'NTC open circuit at 1200 s',       25, 1, 0.80, 0, 3, I_std, [1];
      'S7_cold_drive', 'Drive at 5 °C',                     5, 1, 0.80, 0, 0, I_std, [1] };
nm = {'NORMAL','DERATE','LIMP','SAFE'};
T = table();
R = struct();
for s = 1:size(S, 1)
    for dec = S{s, 9}
        bms_init;
        T_amb = S{s,3};  Ru_factor = S{s,4};  SOC0 = S{s,5};  Weak_on = S{s,6};
        Fault_mode = S{s,7};  Dec_on = dec;
        t = (0:numel(S{s,8})-1)' * Ts;
        drive_ts = timeseries(S{s,8}, t);  t_stop = t(end);
        fprintf('[%s] %s, decision %s ...\n', S{s,1}, S{s,2}, onoff(dec));
        o = sim('bms_twin_ekf');
        g = @(n) reshape(o.get(n), [], 1);
        d = struct('t', o.tout(:), 'I', g('log_i'), 'tc', g('log_tcore'), 'vmin', g('log_vcellmin'), ...
                   'vmax', g('log_vcellmax'), 'soc', g('log_soc'), 'state', g('log_state'), ...
                   'idis', g('log_iallow_dis'), 'ichg', g('log_iallow_chg'), 'cause', g('log_cause'));
        R.(sprintf('%s_%s', S{s,1}, onoff(dec))) = d;
        row = table(string(S{s,1}), string(onoff(dec)), max(d.tc), min(d.vmin), max(d.vmax), ...
            max(d.I), -min(d.I), 100*mean(d.state==1), 100*mean(d.state==2), 100*mean(d.state==3), ...
            100*mean(d.state==4), sum(diff(d.state) ~= 0), sum(d.I)*Ts/3600, ...
            'VariableNames', {'Scenario','Decision','Tcore_max','Vcell_min','Vcell_max','I_dis_max', ...
            'I_chg_max','pct_NORMAL','pct_DERATE','pct_LIMP','pct_SAFE','Transitions','Ah'});
        T = [T; row]; %#ok<AGROW>
    end
end
fprintf('\n=== B) Closed-loop scenarios ===\n');
disp(T);

% ---------------------------------------------------------------- kabul (FMEA test matrisi)
q = @(sc, dc) T(T.Scenario == sc & T.Decision == dc, :);
r6 = R.S6_ntc_open_on;  k6 = find(r6.state == 3, 1);
on = T(T.Decision == "on", :);
chk = { ...
 'B1 normal drive: no false derating',            q("S1_normal","on").pct_NORMAL >= 99 && q("S1_normal","on").Transitions <= 1;
 'B2 thermal: T_core > 55 °C without, < 55 with', q("S2_thermal","off").Tcore_max > 55 && q("S2_thermal","on").Tcore_max < 55;
 'B3 deep discharge: V_min >= 2.8 V with',        q("S3_deep","off").Vcell_min < 2.5 && q("S3_deep","on").Vcell_min >= 2.8;
 'B4 full charge: V_max <= 4.2 V with',           q("S4_charge","off").Vcell_max > 4.25 && q("S4_charge","on").Vcell_max <= 4.2;
 'B5 cold charge limited to 0.3C (17.46 A)',      q("S5_cold_chg","on").I_chg_max <= 17.46 + 0.01;
 'B6 NTC open -> LIMP-HOME within 0.1 s',          ~isempty(k6) && r6.t(k6) - 1200 <= 0.1 + 1e-9;
 'B7 cold drive limited to 0.5C (29.1 A)',        q("S7_cold_drive","on").I_dis_max <= 29.1 + 0.01;
 'B8 no SAFE-STOP in any scenario (no false trip)', all(on.pct_SAFE == 0) };
fprintf('\n=== Acceptance (FMEA test matrix) ===\n');
fprintf('%-52s %s\n', 'A  MATLAB and Python decision logic identical', pf(okA));
for i = 1:size(chk, 1)
    fprintf('%-52s %s\n', chk{i,1}, pf(chk{i,2}));
end
if ~isempty(k6)
    fprintf('(S6: LIMP-HOME at t = %.1f s, I_allow afterwards %.2f A)\n', r6.t(k6), r6.idis(k6+2));
end
save('decision_sonuclari.mat', 'T', 'R', 'S');

% ---------------------------------------------------------------- Şekil
f = figure('Name', 'Decision mechanism', 'Color', 'w', 'Position', [40 40 1150 760]);
tiledlayout(2, 2, 'TileSpacing', 'compact');
a = R.S2_thermal_off;  b = R.S2_thermal_on;
nexttile; hold on; grid on;
plot(a.t/60, a.tc, 'r', 'LineWidth', 1.2);  plot(b.t/60, b.tc, 'b', 'LineWidth', 1.2);
yline(55, 'k--', '55 °C', 'HandleVisibility', 'off');
ylabel('T_{core} [°C]');  xlabel('Time [min]');
legend('Without decision mechanism', 'With decision mechanism', 'Location', 'northwest');
title('(a) 40 °C, cooling fault, aggressive driving');
a = R.S3_deep_off;  b = R.S3_deep_on;
nexttile; hold on; grid on;
plot(a.t/60, a.vmin, 'r', 'LineWidth', 1.0);  plot(b.t/60, b.vmin, 'b', 'LineWidth', 1.0);
yline(2.8, 'k--', '2.8 V design limit', 'HandleVisibility', 'off');
yline(2.5, 'k:', '2.5 V datasheet cut-off', 'HandleVisibility', 'off');
ylim([1.9 3.8]);  ylabel('Weak-group voltage V_{cell,min} [V]');  xlabel('Time [min]');
legend('Without', 'With (current limited by voltage headroom)', 'Location', 'southwest');
title('(b) Deep discharge with a weak series group');
a = R.S4_charge_off;  b = R.S4_charge_on;
nexttile; hold on; grid on;
yyaxis left;  plot(a.t/60, a.vmax, 'r-', 'LineWidth', 1.0);  plot(b.t/60, b.vmax, 'b-', 'LineWidth', 1.2);
yline(4.2, 'k--', '4.2 V', 'HandleVisibility', 'off');  ylabel('V_{cell,max} [V]');
yyaxis right; plot(b.t/60, -b.I, '-', 'Color', [0.3 0.6 0.3], 'LineWidth', 1.0);  ylabel('Charge current, with [A]');
xlabel('Time [min]');
legend('V_{max} without', 'V_{max} with', 'Charge current with', 'Location', 'southeast');
title('(c) Full charge: constant-current / constant-voltage emerges');
b = R.S6_ntc_open_on;
nexttile; hold on; grid on;
yyaxis left;  plot(b.t/60, b.idis, 'b', 'LineWidth', 1.2);  plot(b.t/60, b.I, '-', 'Color', [0.7 0.7 0.7]);
ylabel('Current [A]');
yyaxis right; stairs(b.t/60, b.state, 'r', 'LineWidth', 1.2);  ylim([0.5 4.5]);
yticks(1:4);  yticklabels(nm);
xlabel('Time [min]');
legend('I_{allow,dis}', 'Pack current', 'State', 'Location', 'west');
title('(d) NTC open circuit at 20 min: LIMP-HOME, 25 % floor');
save_fig(f, 'decision_closed_loop.png');

function s = onoff(x)
    if x, s = 'on'; else, s = 'off'; end
end
function s = pf(ok)
    if ok, s = 'PASS'; else, s = 'FAIL'; end
end
