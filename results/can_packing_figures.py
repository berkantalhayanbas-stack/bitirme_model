"""CAN sinyal paketleme figürleri (tez, Haberleşme mimarisi bölümü).

1) can_frame_layout.png : 0x101 ve 0x110 çerçevelerinin 64 bit veri alanı düzeni
   (bms_ecu/bms/common/bms_can.c ile birebir: küçük-uçlu put16, put12x2, finish_hi).
2) can_bus_load.png     : EMU->ECU ölçüm verisinin (25 sinyal, 10 Hz) hat yükü;
   her sinyal ayrı çerçevede / ayrı + E2E / bizim paketli düzenimiz.

Çalıştırma: python results/can_packing_figures.py  (çıktılar results/ içine)
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT = os.path.dirname(os.path.abspath(__file__))
INK, INK2, GRID = "#1f1f1e", "#5f5e58", "#d6d5cf"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
GRAY, DGRAY = "#9a9990", "#5f5e58"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.edgecolor": GRID, "text.color": INK})

# ------------------------------------------------------------ 1) bit düzeni
# segment: (bayt, düşük bit, yüksek bit, renk, etiket)
F101 = [
    (0, 0, 7, BLUE, "V_pack [7:0]"), (1, 0, 7, BLUE, "V_pack [15:8]"),
    (2, 0, 7, ORANGE, "I_pack [7:0]"), (3, 0, 7, ORANGE, "I_pack [15:8]"),
    (4, 0, 7, AQUA, "T_pack [7:0]"), (5, 0, 7, AQUA, "T_pack [15:8]"),
    (6, 0, 3, GRAY, "counter"), (6, 4, 7, "#e9e8e2", "reserved (0)"),
    (7, 0, 7, DGRAY, "CRC-8 SAE J1850"),
]
F110 = [
    (0, 0, 7, BLUE, "V1 [7:0]"),
    (1, 0, 3, BLUE, "V1 [11:8]"), (1, 4, 7, ORANGE, "V2 [3:0]"),
    (2, 0, 7, ORANGE, "V2 [11:4]"),
    (3, 0, 7, AQUA, "V3 [7:0]"),
    (4, 0, 3, AQUA, "V3 [11:8]"), (4, 4, 7, MAGENTA, "V4 [3:0]"),
    (5, 0, 7, MAGENTA, "V4 [11:4]"),
    (6, 0, 3, GRAY, "counter"), (6, 4, 7, YELLOW, "balancing\nfeedback"),
    (7, 0, 7, DGRAY, "CRC-8 SAE J1850"),
]
NOTE101 = ("V 0.1 V (u16)   I 0.1 A (s16)   T 0.1 °C (s16)\n"
           "little-endian (Intel); CRC over ID + bytes 0-6")
NOTE110 = ("4 groups x 12 bit: V = 1.000 V + raw x 1 mV (0xFFF = invalid)\n"
           "0x110-0x114: 19 groups in 5 frames (last slot of 0x114 unused)")


def draw_frame(ax, segs, title, note):
    for b, lo, hi, col, lab in segs:
        # bit 7 solda, bit 0 sağda (DBC görünümü); satır = bayt
        x0, w = 7 - hi, hi - lo + 1
        dark = col in (DGRAY, GRAY)
        ax.add_patch(Rectangle((x0 + 0.04, b + 0.06), w - 0.08, 0.88,
                               facecolor=col, alpha=1.0 if dark else 0.30,
                               edgecolor=col, linewidth=1.2))
        ax.text(x0 + w / 2, b + 0.5, lab, ha="center", va="center",
                fontsize=8 if w > 4 else 7, color="white" if dark else INK)
    ax.set_xlim(0, 8); ax.set_ylim(8, 0)
    ax.set_xticks([i + 0.5 for i in range(8)], [str(7 - i) for i in range(8)])
    ax.set_yticks([i + 0.5 for i in range(8)], [f"byte {i}" for i in range(8)])
    ax.tick_params(length=0, colors=INK2)
    ax.xaxis.set_ticks_position("top"); ax.xaxis.set_label_position("top")
    ax.set_xlabel("bit", color=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold", pad=22)
    ax.text(0, 8.35, note, va="top", fontsize=7.5, color=INK2)


fig, axs = plt.subplots(1, 2, figsize=(10.5, 5.2))
draw_frame(axs[0], F101, "0x101  pack measurement (EMU → ECU, 10 Hz)", NOTE101)
draw_frame(axs[1], F110, "0x110  cell group voltages 1-4 (EMU → ECU, 10 Hz)", NOTE110)
fig.subplots_adjust(left=0.07, right=0.99, top=0.83, bottom=0.15, wspace=0.18)
fig.savefig(os.path.join(OUT, "can_frame_layout.png"), dpi=200)
plt.close(fig)

# ------------------------------------------------------------ 2) hat yükü
# Klasik CAN taban çerçevesi: SOF 1 + ID 11 + RTR 1 + IDE 1 + r0 1 + DLC 4 + veri
# + CRC 15 + CRC ayracı 1 + ACK 2 + EOF 7 + IFS 3 = 47 + 8n bit.
# Bit doldurma yalnız SOF..CRC (34 + 8n bit) üzerinde; en kötü durum floor((34+8n-1)/4).
def frame_bits(n):
    return 47 + 8 * n, (34 + 8 * n - 1) // 4

N_SIG = 3 + 3 + 19          # 0x101 (V, I, T) + 0x102 (Vmin, Vmax, Tamb) + 19 grup
RATE, BUS = 10.0, 500e3     # Hz, bit/s
cases = [
    ("each signal in its own frame\n(2 data bytes, no E2E)", N_SIG, 2),
    ("each signal in its own frame\n+ counter and CRC-8 (4 bytes)", N_SIG, 4),
    ("packed (this work)\n0x101, 0x102, 0x110-0x114", 7, 8),
]
rows = []
for lab, nf, nb in cases:
    base, stuff = frame_bits(nb)
    rows.append((lab, nf, nf * base * RATE, nf * (base + stuff) * RATE))

fig, ax = plt.subplots(figsize=(8.6, 3.4))
for i, (lab, nf, lo, hi) in enumerate(rows):
    y = len(rows) - 1 - i
    col = BLUE if i == 2 else GRAY
    ax.barh(y, lo / 1e3, height=0.52, color=col)
    ax.barh(y, (hi - lo) / 1e3, left=lo / 1e3, height=0.52, color=col, alpha=0.30)
    ax.text(hi / 1e3 + 0.4, y, f"{nf} frames, {lo/1e3:.1f}-{hi/1e3:.1f} kbit/s "
            f"({100*lo/BUS:.1f}-{100*hi/BUS:.1f} % of bus)",
            va="center", fontsize=8.5, color=INK)
ax.set_yticks(range(len(rows)), [r[0] for r in rows][::-1], fontsize=8.5)
ax.set_xlim(0, 46)
ax.set_xlabel("bus load for EMU → ECU measurements, 25 signals at 10 Hz [kbit/s]", color=INK2)
ax.grid(axis="x", color=GRID, linewidth=0.6); ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.tick_params(length=0, colors=INK2)
ax.set_title("Signal packing: same data, 60 % less bus time", loc="left",
             fontsize=10, fontweight="bold")
fig.text(0.30, 0.03, "solid: frame without bit stuffing; light: worst-case stuffing. "
         "Classic CAN overhead 47 bit/frame (SOF..IFS).", fontsize=7.5, color=INK2)
fig.subplots_adjust(left=0.30, right=0.99, top=0.88, bottom=0.30)
fig.savefig(os.path.join(OUT, "can_bus_load.png"), dpi=200)
plt.close(fig)

for lab, nf, lo, hi in rows:
    print(f"{lab.splitlines()[0]:34s} {nf:2d} frames  {lo:7.0f}-{hi:7.0f} bit/s")
