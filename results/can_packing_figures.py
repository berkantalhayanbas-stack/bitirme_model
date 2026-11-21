"""CAN sinyal paketleme figürleri (tez, Haberleşme mimarisi bölümü).

1) can_frame_layout.png : 0x101 ve 0x110 çerçevelerinin 64 bit veri alanı düzeni
   (bms_ecu/bms/common/bms_can.c ile birebir: küçük-uçlu put16, put12x2, finish_hi).
2) can_bus_load.png     : EMU->ECU ölçüm verisinin (25 sinyal, 10 Hz) hat yükü;
   her sinyal ayrı çerçevede / ayrı + E2E / bizim paketli düzenimiz.

Çalıştırma: python results/can_packing_figures.py  (çıktılar results/ içine)
"""
import csv
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import thesis_style as ts                       # ortak tez figür stili
ts.apply()
plt.rcParams["axes.grid"] = False                 # diyagram: ızgara yalnız istenen eksende
from matplotlib.patches import Rectangle

OUT = os.path.dirname(os.path.abspath(__file__))
BMS_ECU_TOOLS = r"C:\Users\berka\STM32CubeIDE\workspace_2.2.0\bms_ecu\tools"
INK, INK2, GRID = ts.INK, ts.INK2, ts.GRID
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = ts.BLUE, ts.ORANGE, ts.AQUA, ts.YELLOW, ts.MAGENTA
GRAY, DGRAY = ts.MUTED, ts.INK2


# ------------------------------------------------------------ 1) bit düzeni
# segment: (bayt, düşük bit, yüksek bit, renk, etiket)
F101 = [
    (0, 0, 7, BLUE, "V_pack [7:0]"), (1, 0, 7, BLUE, "V_pack [15:8]"),
    (2, 0, 7, ORANGE, "I_pack [7:0]"), (3, 0, 7, ORANGE, "I_pack [15:8]"),
    (4, 0, 7, AQUA, "T_pack [7:0]"), (5, 0, 7, AQUA, "T_pack [15:8]"),
    (6, 0, 3, GRAY, "counter"), (6, 4, 7, ts.LIGHT, "reserved (0)"),
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

fig, ax = plt.subplots(figsize=(8.6, 4.0))
for i, (lab, nf, lo, hi) in enumerate(rows):
    y = len(rows) - 1 - i
    col = BLUE if i == 2 else GRAY
    ax.barh(y, lo / 1e3, height=0.52, color=col)
    ax.barh(y, (hi - lo) / 1e3, left=lo / 1e3, height=0.52, color=col, alpha=0.30)
    ax.text(hi / 1e3 + 0.4, y, f"{nf} frames, {lo/1e3:.1f}-{hi/1e3:.1f} kbit/s "
            f"({100*lo/BUS:.1f}-{100*hi/BUS:.1f} % of bus)",
            va="center", fontsize=8.5, color=INK)
# Ölçülen nokta: STM32 lojik analizörüyle (bms_ecu tools/la_stats.py) yakalanan gerçek çerçeveler,
# kimlik başına ortalama ham bit (doldurma + IFS dahil) x 10 Hz.
with open(os.path.join(OUT, "can_la_stats.csv")) as fh:
    la = list(csv.DictReader(fh))
ids = sorted({r["id"] for r in la})
meas = sum(np.mean([int(r["bits"]) for r in la if r["id"] == i]) for i in ids) * RATE
mean_stuff = np.mean([int(r["stuff"]) for r in la])
ax.plot(meas / 1e3, 0, marker="D", ms=8, color=INK, mec="white", mew=1.5, zorder=5)
ax.annotate(f"measured on the bus: {meas/1e3:.2f} kbit/s\n({len(la)} frames, {len(ids)} IDs, "
            f"mean {mean_stuff:.1f} stuff bits/frame)",
            xy=(meas / 1e3, 0), xytext=(meas / 1e3, -0.62), ha="center", va="top",
            fontsize=8, color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.set_ylim(-1.25, len(rows) - 0.5)
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
fig.subplots_adjust(left=0.30, right=0.99, top=0.90, bottom=0.20)
fig.savefig(os.path.join(OUT, "can_bus_load.png"), dpi=200)
plt.close(fig)

for lab, nf, lo, hi in rows:
    print(f"{lab.splitlines()[0]:34s} {nf:2d} frames  {lo:7.0f}-{hi:7.0f} bit/s")
print(f"measured (logic analyzer)          {len(ids)} IDs     {meas:7.0f} bit/s, "
      f"{len(la)} frames, mean stuff {mean_stuff:.2f}")

# ------------------------------------------------------------ 3) lojik analizör: gerçek 0x110
# Ham örnekler STM32'nin kendi lojik analizöründen (APP_LA, PA11, 4,25 MS/s); çözüm bms_ecu
# tools/la_view.py ile aynı (o modül yüklenir). Veri baytları figür 1'deki düzene göre çözülür.
sys.path.insert(0, BMS_ECU_TOOLS)
import la_view  # noqa: E402

z = np.load(os.path.join(OUT, "can_la_raw_0x110.npy"))
rate, x = int(z[0]), z[1:].astype(np.uint8)
bits, t_bits, frames, spb = la_view.decode(rate, x)
f = frames[0]
tb_us, _ = la_view.bit_time([f], t_bits, bits, spb, rate)
t_us = np.array(f["t_bits"]) / rate * 1e6
lv = np.array([int(bits[k]) for k in f["raw_idx"]])
fld = f["field"]
t_end = t_us[-1] + 2.0

FIELD_COL = {"SOF": BLUE, "ID": BLUE, "RTR": "#c3c2b7", "IDE": "#c3c2b7", "r0": "#c3c2b7",
             "DLC": "#c3c2b7", "DATA": AQUA, "CRC": ORANGE, "CRC del": ts.LIGHT,
             "ACK": MAGENTA, "ACK del": ts.LIGHT, "EOF": ts.LIGHT}
fig, ax = plt.subplots(figsize=(10.5, 4.2))
# alan şeritleri (doldurma bitleri bulunduğu alana katılır, ayrıca işaretlenir)
eff = []
for k, nm in enumerate(fld):
    eff.append(eff[-1] if nm == "stuff" else nm)
seg_start = 0
for k in range(1, len(eff) + 1):
    if k == len(eff) or eff[k] != eff[seg_start]:
        nm = eff[seg_start]
        x0, x1 = t_us[seg_start], (t_us[k] if k < len(eff) else t_end)
        ax.axvspan(x0, x1, ymin=0.08, ymax=0.62, color=FIELD_COL[nm], alpha=0.18, lw=0)
        if nm in ("ID", "DLC", "DATA", "CRC", "ACK", "EOF"):
            ax.text((x0 + x1) / 2, 1.42, nm if nm != "ID" else "ID 0x110", ha="center",
                    fontsize=8, color=INK2)
        seg_start = k
ax.step(np.append(t_us, t_end), np.append(lv, lv[-1]), where="post", color=INK, lw=1.1)
st = [t for t, nm in zip(t_us, fld) if nm == "stuff"]
ax.plot(np.array(st) + 1.0, [-0.28] * len(st), "^", color=ORANGE, ms=6,
        label=f"stuff bits ({len(st)})")
# veri baytları: sınırlar + değerler
d_idx = [k for k, nm in enumerate(fld) if nm == "DATA"]
for b in range(8):
    k0 = d_idx[8 * b]
    k1 = d_idx[8 * b + 7]
    x0, x1 = t_us[k0], t_us[k1] + 2.0
    ax.axvline(x0, ymin=0.08, ymax=0.62, color="white", lw=1.5)
    ax.text((x0 + x1) / 2, 1.18, f"b{b}\n{f['data'][b]:02X}", ha="center", fontsize=7.5, color=INK)
d = f["data"]
v = [d[0] | (d[1] & 0x0F) << 8, d[1] >> 4 | d[2] << 4, d[3] | (d[4] & 0x0F) << 8, d[4] >> 4 | d[5] << 4]
txt = ("decoded: " + ", ".join(f"V{j+1} = {1.0 + 0.001 * r:.3f} V" for j, r in enumerate(v))
       + f", counter {d[6] & 0x0F}, CRC-8 0x{d[7]:02X}  |  CRC-15 0x{f['crc_rx']:04X} OK, ACK, "
       f"{f['n_bits'] + 3} bits incl. IFS, bit time {tb_us:.3f} µs")
fig.text(0.09, 0.04, txt, fontsize=8, color=INK)
ax.set_ylim(-0.45, 1.75)
ax.set_yticks([0, 1], ["dominant", "recessive"])
ax.set_xlim(-2, t_end + 2)
ax.set_xlabel("time from SOF [µs]", color=INK2)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.tick_params(length=0, colors=INK2)
ax.legend(loc="upper right", frameon=False, fontsize=8, bbox_to_anchor=(1.0, 1.12))
ax.set_title("Real frame 0x110 on PA11, captured by the STM32 itself (TIM6 + DMA, 4.25 MS/s)",
             loc="left", fontsize=10, fontweight="bold", pad=18)
fig.subplots_adjust(left=0.09, right=0.99, top=0.86, bottom=0.24)
fig.savefig(os.path.join(OUT, "can_la_frame_0x110.png"), dpi=200)
plt.close(fig)
print("0x110:", " ".join(f"{1.0 + 0.001 * r:.3f}" for r in v), f"bit time {tb_us:.4f} us")
