function save_fig(fig, filename)
%SAVE_FIG  Şekli sonuclar/ klasörüne 200 dpi PNG olarak kaydeder.
%   Eksen araç çubuklarını (yakınlaştırma/kaydırma simgeleri) gizler,
%   böylece tez şekillerine karışmazlar ve MATLAB uyarı vermez.
%   Kullanım: save_fig(f1, 'senaryo_T_core.png')

if ~exist('sonuclar', 'dir'), mkdir('sonuclar'); end
ax = findall(fig, 'Type', 'axes');
for k = 1:numel(ax)
    ax(k).Toolbar.Visible = 'off';
end
drawnow;
exportgraphics(fig, fullfile('sonuclar', filename), 'Resolution', 200);
end
