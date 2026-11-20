%TEST_CAN_MONITOR  4. hafta: CAN alım izleyicisi (E2E: CRC + alive counter + zaman aşımı) testi.
%   A) Birim test vektörleri: twin/test_can_monitor.py'nin ürettiği olay dizisi (can_monitor_vectors.csv,
%      STM32 zaman çizelgesi: alım 100 ms'de bir, değerlendirme 10 ms'de bir) can_monitor_*.m'ye verilir;
%      çıktılar Python ile BİREBİR aynı olmalı (aynı vektörler STM32 bms_can.c ile de birebir aynıdır).
%   B) Kapalı çevrim (Simulink, Dec_on = 1, 120 s sürüş, arıza 60 s'de; son geçerli mesaj 59.9 s):
%      C0 arıza yok                     -> CAN_ok hep 1, SAFE yok
%      C1 0x101 0.3 s kayıp             -> fault, SAFE yok
%      C2 0x101 0.4 s kayıp             -> dönüş çerçevesi reddedilir (sayaç farkı 5 > 3) -> SAFE 60.4 s
%      C3 0x101 0.5 s kayıp             -> SAFE 60.4 s (son geçerliden 500 ms)
%      C4 0x102 CRC bozuk               -> SAFE 60.4 s
%      C5 0x101 donmuş alive counter    -> SAFE 60.5 s (60.0 s'deki çerçevenin sayacı zaten doğru)
%      C6 açılıştan itibaren mesaj yok  -> SAFE 2.0 s (açılış süresi)
%      Hepsinde SAFE kalıcı, I_allow = 0. Beklenen anlar Python closed_loop.py ile aynı.
%   Önkoşul: build_bms_model (CAN_Rx bloğu içeren sürüm).
%   Çıktılar İngilizce; şekil ../results/can_monitor.png

% ================================================================== A) birim test vektörleri
V = readtable('can_monitor_vectors.csv');
n = height(V);
out = zeros(n, 8);
for k = 1:n
    if V.reset(k), mon = can_monitor_init(0); end
    ok = false;
    if V.op(k) == 1
        [mon, ok] = can_monitor_rx(mon, V.now_ms(k), V.crc_ok(k) > 0, V.counter(k));
    else
        mon = can_monitor_tick(mon, V.now_ms(k));
    end
    out(k, :) = [ok mon.fault mon.safe mon.n_ok mon.n_crc_err mon.n_cnt_err mon.n_lost V.test(k)];
end
ref8 = [V.ok V.fault V.safe V.n_ok V.n_crc_err V.n_cnt_err V.n_lost V.test];
d_ev = sum(any(out ~= ref8, 2));
fprintf('=== A) Unit-test vectors: MATLAB can_monitor_*.m vs Python can_monitor.py (%d events, %d tests) ===\n', ...
        n, numel(unique(V.test)));
fprintf('Mismatched events: %d\n', d_ev);
okA = d_ev == 0;
fprintf('Acceptance A (MATLAB and Python monitor identical): %s\n\n', pf(okA));

% ================================================================== B) kapalı çevrim
%      ad     açıklama                                Can_mode Can_msg Can_t Can_dur  beklenen SAFE [s]
S = { 'C0', 'No CAN fault',                           0, 3, 60, Inf,  NaN;
      'C1', '0x101 lost for 0.3 s',                   1, 1, 60, 0.3,  NaN;
      'C2', '0x101 lost for 0.4 s (return rejected)', 1, 1, 60, 0.4,  60.4;
      'C3', '0x101 lost for 0.5 s',                   1, 1, 60, 0.5,  60.4;
      'C4', '0x102 CRC corrupted',                    2, 2, 60, Inf,  60.4;
      'C5', '0x101 frozen alive counter',             3, 1, 60, Inf,  60.5;
      'C6', 'No frames from power-up',                1, 3,  0, Inf,  2.0 };
T = table();
R = struct();
for s = 1:size(S, 1)
    bms_init;
    Dec_on = 1;
    Can_mode = S{s,3};  Can_msg = S{s,4};  Can_t = S{s,5};  Can_dur = S{s,6};
    I = ref.i_pack(1:1200);
    t = (0:numel(I)-1)' * Ts;
    drive_ts = timeseries(I, t);  t_stop = t(end);
    fprintf('[%s] %s ...\n', S{s,1}, S{s,2});
    o = sim('bms_twin_ekf');
    g = @(nm) reshape(o.get(nm), [], 1);
    d = struct('t', o.tout(:), 'I', g('log_i'), 'state', g('log_state'), 'idis', g('log_iallow_dis'), ...
               'ichg', g('log_iallow_chg'), 'can_ok', g('log_can_ok'), 'can_fault', g('log_can_fault'), ...
               'im', g('log_im'));
    R.(S{s,1}) = d;
    k = find(d.state == 4, 1);
    if isempty(k), t_safe = NaN; else, t_safe = d.t(k); end
    exp_t = S{s,7};
    if isnan(exp_t)
        ok = isnan(t_safe) && all(d.can_ok == 1);
        if Can_mode > 0, ok = ok && max(d.can_fault) > 0; end
    else
        ok = abs(t_safe - exp_t) < 1e-6 && all(d.state(k:end) == 4) && all(d.idis(k:end) == 0) ...
             && all(d.ichg(k:end) == 0) && d.can_ok(k) == 0;
    end
    row = table(string(S{s,1}), string(S{s,2}), exp_t, t_safe, max(d.can_fault), min(d.can_ok), ...
        string(pf(ok)), 'VariableNames', {'Case','Description','Expected_SAFE_s','SAFE_s','Fault_flags', ...
        'CAN_ok_min','Result'});
    T = [T; row]; %#ok<AGROW>
end
fprintf('\n=== B) Closed-loop CAN fault cases (Simulink) ===\n');
disp(T);
okB = all(T.Result == "PASS");
fprintf('Acceptance A (MATLAB and Python monitor identical):     %s\n', pf(okA));
fprintf('Acceptance B (SAFE-STOP exactly as STM32/Python, latched): %s\n', pf(okB));
save('can_monitor_sonuclari.mat', 'T', 'R', 'S');

% ---------------------------------------------------------------- Şekil
f = figure('Name', 'CAN monitor', 'Color', 'w', 'Position', [40 40 1150 520]);
tiledlayout(1, 2, 'TileSpacing', 'compact');
nexttile; hold on; grid on;
a = R.C1;  b = R.C3;
yyaxis left;
plot(a.t, a.idis, 'b-', 'LineWidth', 1.2);  plot(b.t, b.idis, 'r-', 'LineWidth', 1.2);
ylabel('I_{allow,dis} [A]');
yyaxis right;
stairs(a.t, a.can_fault > 0, 'b:', 'LineWidth', 1.0);  stairs(b.t, 1 - b.can_ok, 'r:', 'LineWidth', 1.0);
ylim([-0.1 1.5]);  ylabel('Flag');
xlim([58 63]);  xlabel('Time [s]');
legend('0.3 s loss: I_{allow}', '0.5 s loss: I_{allow}', '0.3 s loss: timeout fault', '0.5 s loss: CAN\_ok = 0', ...
       'Location', 'southwest');
title('(a) 0x101 frame loss at 60 s: fault vs SAFE-STOP');
nexttile; hold on; grid on;
c = R.C6;
yyaxis left;  plot(c.t, c.idis, 'b-', 'LineWidth', 1.2);  ylabel('I_{allow,dis} [A]');
yyaxis right; stairs(c.t, c.state, 'r-', 'LineWidth', 1.2);  ylim([0.5 4.5]);
yticks(1:4);  yticklabels({'NORMAL','DERATE','LIMP','SAFE'});
xlim([0 5]);  xlabel('Time [s]');
legend('I_{allow,dis}', 'State', 'Location', 'east');
title('(b) No measurements from power-up: SAFE-STOP at 2 s');
save_fig(f, 'can_monitor.png');

function s = pf(ok)
    if ok, s = 'PASS'; else, s = 'FAIL'; end
end
