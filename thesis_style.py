"""thesis_style.py -- tez figürleri için ortak matplotlib stili.

Kurallar dataviz yönteminden (doğrulanmış kategorik palet, ince işaretler, silik ızgara,
tek eksen, metin rengi veri renginden ayrı, durum renkleri yalnız durum için).
Ana kopya: C:\\bitirme\\thesis_style.py; bms_ecu/tools/thesis_style.py BİREBİR kopyası
(biri değişirse diğerini de güncelle).

Kullanım:
    import thesis_style as ts
    ts.apply()                      # matplotlib içe aktarıldıktan sonra, çizimden önce
    ax.plot(t, y)                   # renkler sırayla SERIES'ten (C0..C7)
    ts.ref_line(ax, 55, "LIMP 55 °C")
    ts.state_band(ax, t, state)     # NORMAL/DERATE/LIMP/SAFE arka plan şeridi
    ts.save(fig, path)
"""
import matplotlib as mpl
from cycler import cycler

# ------------------------------------------------------------ kategorik palet (sıra sabit)
# Doğrulandı (validate_palette.js, açık mod, beyaz zemin): CVD ΔE >= 9.1, normal ΔE >= 19.6.
# Aqua / sarı / magenta 3:1 altı -> bu serilerde lejant + doğrudan etiket şart.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
MAGENTA, GREEN, VIOLET, RED = "#e87ba4", "#008300", "#6250d6", "#e34948"
SERIES = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED]
# 8'den fazla seri yok: fazlası "Other"a katlanır ya da küçük çoklu grafiğe bölünür.

# ------------------------------------------------------------ mürekkep / zemin
SURFACE = "#ffffff"
INK = "#0b0b0b"        # birincil metin, "gerçek değer" eğrisi
INK2 = "#52514e"       # ikincil metin, eksen etiketleri
MUTED = "#898781"      # eşik çizgileri, ölçüm noktaları, ikincil seri
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
LIGHT = "#e9e8e2"      # boş / ayrılmış alan dolgusu

# ------------------------------------------------------------ durum renkleri (yalnız durum için)
GOOD, WARNING, SERIOUS, CRITICAL = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
STATE_COLOR = {1: GOOD, 2: WARNING, 3: SERIOUS, 4: CRITICAL}
STATE_NAME = {1: "NORMAL", 2: "DERATE", 3: "LIMP-HOME", 4: "SAFE-STOP"}

# ------------------------------------------------------------ sıralı rampa (tek ton, mavi)
SEQ_BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
            "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]


def seq_cmap(name="thesis_blue"):
    """Büyüklük için tek tonlu (açık -> koyu) renk haritası."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(name, SEQ_BLUE)


def apply(font_size=9):
    """rcParams'ı tez stiline ayarla."""
    mpl.rcParams.update({
        "font.family": "DejaVu Sans",          # °, µ, Ψ, Türkçe karakterler her makinede
        "font.size": font_size,
        "axes.titlesize": font_size + 0.5,
        "axes.titleweight": "normal",
        "axes.titlelocation": "left",
        "axes.labelsize": font_size,
        "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.facecolor": SURFACE,
        "axes.prop_cycle": cycler(color=SERIES),
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "xtick.color": AXIS,
        "ytick.color": AXIS,
        "xtick.labelcolor": INK2,
        "ytick.labelcolor": INK2,
        "xtick.labelsize": font_size - 0.5,
        "ytick.labelsize": font_size - 0.5,
        "text.color": INK,
        "lines.linewidth": 1.5,                # ~2 px
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "lines.markersize": 4,
        "patch.linewidth": 0,
        "legend.frameon": False,
        "legend.fontsize": font_size - 1,
        "legend.labelcolor": INK2,
        "legend.handlelength": 1.6,
        "figure.facecolor": SURFACE,
        "figure.dpi": 100,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.facecolor": SURFACE,
    })
    if "thesis_blue" not in mpl.colormaps:
        mpl.colormaps.register(seq_cmap())
    mpl.rcParams["image.cmap"] = "thesis_blue"


def ref_line(ax, y=None, label=None, x=None, color=MUTED, ls="--"):
    """Eşik / sınır çizgisi (silik, ince) + isteğe bağlı kısa etiket."""
    if y is not None:
        ax.axhline(y, color=color, lw=0.8, ls=ls, zorder=1.5)
        if label:
            ax.annotate(label, (1.0, y), xycoords=("axes fraction", "data"), xytext=(-2, 2),
                        textcoords="offset points", ha="right", va="bottom", fontsize=7.5, color=INK2)
    if x is not None:
        ax.axvline(x, color=color, lw=0.8, ls=ls, zorder=1.5)
        if label:
            ax.annotate(label, (x, 1.0), xycoords=("data", "axes fraction"), xytext=(2, -2),
                        textcoords="offset points", ha="left", va="top", fontsize=7.5, color=INK2)


def end_label(ax, x, y, text, dy=0):
    """Serinin sonuna doğrudan etiket (metin rengi mürekkep, seri rengi değil)."""
    ax.annotate(text, (x, y), xytext=(4, dy), textcoords="offset points", va="center",
                fontsize=7.5, color=INK2, annotation_clip=False)


def state_band(ax, t, state, alpha=0.18, legend=True):
    """Karar durumunu (1..4) eksenin arka planına renkli şerit olarak çiz."""
    import numpy as np
    t = np.asarray(t, float)
    s = np.asarray(state)
    seen = set()
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        st = int(s[i]) if s[i] == s[i] else 0
        if st in STATE_COLOR:
            t1 = t[j + 1] if j + 1 < len(t) else t[j]
            ax.axvspan(t[i], t1, color=STATE_COLOR[st], alpha=alpha, lw=0, zorder=0,
                       label=STATE_NAME[st] if (legend and st not in seen) else None)
            seen.add(st)
        i = j + 1


def panel_label(ax, text):
    """(a), (b) ... alt başlık, sola dayalı."""
    ax.set_title(text, loc="left", fontsize=mpl.rcParams["font.size"] + 0.5, color=INK)


def save(fig, path, pdf=False):
    """PNG (200 dpi) kaydet; pdf=True ise yanına aynı adla vektör PDF."""
    import os
    fig.savefig(path)
    if pdf:
        fig.savefig(os.path.splitext(path)[0] + ".pdf")
