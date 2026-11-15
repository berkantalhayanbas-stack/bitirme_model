%PREFILTER_DESIGN  Koruma eşikleri için alçak geçiren ön filtrenin tasarımı (designfilt).
%   Hafif betik: simülasyon koşturmaz, sadece filtre tasarlar ve çizer.
%   Seçim (twin/prefilter_study.py çalışmasından):
%     - EKF girdisi: FİLTRE YOK. Her ön filtre SOC RMSE'yi kötüleştirdi (%0,227 -> %0,26-0,27);
%       Kalman filtresi zaten modele dayalı optimal süzgeç, ikinci süzgeç gecikme ekliyor.
%     - Eşik tabanlı korumalar (sıcaklık, gerilim): 2. derece Butterworth, kesim 0,5 Hz.
%       Aşırı sıcaklık eşiğinde alarm bölgesine giriş sayısı 159 -> 4, gecikme 0,45 s
%       (ısıl zaman sabitleri dakikalar mertebesinde: ihmal edilebilir).
%   Simülasyon 10 Hz, STM32 döngüsü 100 Hz: iki örnekleme için de tasarlanır; gecikme saniye
%   cinsinden aynıdır (kesim frekansı belirler, örnekleme değil).
%   Çıktılar İngilizce; şekil sonuclar/prefilter_design.png

fc = 0.5;                                   % kesim frekansı [Hz]
fsList = [10 100];                          % simülasyon ve STM32
col = lines(2);
f = figure('Name', 'Prefilter design', 'Color', 'w', 'Position', [80 80 1000 420]);
tiledlayout(1, 2, 'TileSpacing', 'compact');
ax1 = nexttile; hold on; grid on;
ax2 = nexttile; hold on; grid on;
fprintf('=== 2nd-order Butterworth low-pass, fc = %.1f Hz (designfilt) ===\n', fc);
for k = 1:2
    fs = fsList(k);
    d = designfilt('lowpassiir', 'FilterOrder', 2, 'HalfPowerFrequency', fc, ...
                   'SampleRate', fs, 'DesignMethod', 'butter');
    [b, a] = tf(d);
    [h, w] = freqz(d, 4096, fs);
    [gd, wg] = grpdelay(d, 4096, fs);
    fprintf('fs = %3d Hz: b = [%.8f %.8f %.8f], a = [%.8f %.8f %.8f], DC group delay = %.0f ms\n', ...
            fs, b, a, 1000 * gd(1) / fs);
    plot(ax1, w, 20*log10(abs(h)), 'Color', col(k,:), 'LineWidth', 1.3, ...
         'DisplayName', sprintf('f_s = %d Hz', fs));
    plot(ax2, wg, 1000 * gd / fs, 'Color', col(k,:), 'LineWidth', 1.3, ...
         'DisplayName', sprintf('f_s = %d Hz', fs));
end
fprintf('Python reference (scipy.signal.butter, fs = 10 Hz): b = [0.02008337 0.04016673 0.02008337],\n');
fprintf('                                                    a = [1 -1.56101808 0.64135154]\n');
set(ax1, 'XScale', 'log');  xlim(ax1, [0.01 5]);  ylim(ax1, [-60 5]);
xline(ax1, fc, 'k:', 'f_c', 'HandleVisibility', 'off');
xlabel(ax1, 'Frequency [Hz]');  ylabel(ax1, 'Magnitude [dB]');  legend(ax1, 'Location', 'southwest');
title(ax1, 'Magnitude response');
set(ax2, 'XScale', 'log');  xlim(ax2, [0.01 5]);
xlabel(ax2, 'Frequency [Hz]');  ylabel(ax2, 'Group delay [ms]');  legend(ax2, 'Location', 'northwest');
title(ax2, 'Group delay (≈450 ms at low frequency for both sampling rates)');
save_fig(f, 'prefilter_design.png');
