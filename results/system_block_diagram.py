"""Sistem blok diyagramı (tez, Donanım/HIL düzeneği bölümü).

system_block_diagram.png / .pdf : masa üstü HIL düzeneği.
  Sol  : tesis = dijital ikiz EMU düğümü (Arduino Uno + MCP2515 + TJA1050, girişler, LCD)
  Orta : CAN 500 kbit/s hattı ve mantıksal mesaj akışı (bms_ecu/bms/common/bms_can.h)
  Sağ  : kontrolcü = BMS ECU (NUCLEO-G431RB) ve çıkışlar (farlar ULN2003 üzerinden, röle = ana kontaktör)
  Üst  : PC araçları (COM10 = Uno, COM9 + SWD = ST-LINK)
Pin ve mesaj bilgileri bms_ecu/CLAUDE.md ile aynı; biri değişirse burayı da güncelle.

Çalıştırma: python results/system_block_diagram.py  (çıktılar results/ içine)
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import thesis_style as ts                       # ortak tez figür stili
ts.apply()
plt.rcParams["axes.grid"] = False                 # diyagram: ızgara yalnız istenen eksende
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.dirname(os.path.abspath(__file__))
INK, INK2, GRID = ts.INK, ts.INK2, ts.GRID
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = ts.BLUE, ts.ORANGE, ts.AQUA, ts.YELLOW, ts.MAGENTA
GRAY = ts.MUTED

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
                     "text.color": INK})

fig, ax = plt.subplots(figsize=(14, 9.2))
ax.set_xlim(0, 140)
ax.set_ylim(0, 92)
ax.axis("off")


# ------------------------------------------------------------ yardımcılar
def group(x, y, w, h, col, title):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.5",
                                facecolor=col, alpha=0.06, edgecolor=col, linewidth=1.4,
                                linestyle=(0, (5, 3))))
    ax.text(x + 1.2, y + h - 1.2, title, ha="left", va="top", fontsize=9.5,
            fontweight="bold", color=col)


def box(x, y, w, h, col, title, lines=(), strong=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
                                facecolor=col, alpha=0.30 if strong else 0.13,
                                edgecolor=col, linewidth=1.3))
    if lines:
        ax.text(x + w / 2, y + h - 1.0, title, ha="center", va="top",
                fontsize=8.5, fontweight="bold")
        ax.text(x + w / 2, y + h - 3.6, "\n".join(lines), ha="center", va="top",
                fontsize=7.3, color=INK2, linespacing=1.35)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=8, fontweight="bold", linespacing=1.3)


def arrow(p0, p1, col=INK2, both=False, ls="-", lw=1.2, label=None, lpos=0.5,
          loff=(0, 0.8), lha="center", lsize=7, cs="arc3"):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="<|-|>" if both else "-|>",
                                 mutation_scale=9, color=col, linewidth=lw,
                                 linestyle=ls, connectionstyle=cs,
                                 shrinkA=0, shrinkB=0))
    if label:
        mx = p0[0] + (p1[0] - p0[0]) * lpos + loff[0]
        my = p0[1] + (p1[1] - p0[1]) * lpos + loff[1]
        ax.text(mx, my, label, ha=lha, va="bottom", fontsize=lsize, color=col)


# ------------------------------------------------------------ PC (üst)
box(24, 84, 92, 6.5, GRAY,
    "PC (Python araçları)",
    ["demo_run.py (senaryolar)  ·  can_replay.py (kayıt oynatma)  ·  "
     "live_panel.py (canlı panel)  ·  fw_build.py (derle + yükle)"])

# ------------------------------------------------------------ tesis (sol)
group(1, 10, 47, 68, ORANGE, "TESİS: dijital ikiz EMU düğümü")
box(3, 58, 14, 7, YELLOW, "LM35 (A1)\nortam sıcaklığı")
box(3, 48, 14, 7, YELLOW, "Pedal potu (A0)\nsürücü isteği")
box(3, 38, 14, 7, YELLOW, "5 buton\nstres senaryoları")
box(3, 28, 14, 7, YELLOW, "I2C LCD 16x2\n(A4/A5)")
box(20, 30, 26, 41, ORANGE, "Arduino Uno",
    ["twin_emu (10 Hz)", "",
     "2-RC hücre modeli", "x 19 grup (saçılma,", "zayıf grup 7)", "",
     "2 düğümlü termal model", "",
     "araç modeli +", "sürüş çevrimi", "",
     "akımı 0x201 I_allow", "ile kırpar", "",
     "0x210 maskesiyle", "10 Ω dengeleme"], strong=True)
box(20, 20.5, 26, 6, ORANGE, "MCP2515 CAN denetleyici (SPI)")
box(20, 12.5, 26, 5.5, ORANGE, "TJA1050 alıcı-verici (5 V)")

arrow((17, 61.5), (20, 61.5))
arrow((17, 51.5), (20, 51.5))
arrow((17, 41.5), (20, 41.5))
arrow((20, 31.5), (17, 31.5))
arrow((33, 30), (33, 26.5), both=True, label="SPI", loff=(0.8, -0.6), lha="left")
arrow((33, 20.5), (33, 18), both=True)

# ------------------------------------------------------------ kontrolcü (sağ)
group(74, 10, 41, 68, BLUE, "KONTROLCÜ: BMS ECU")
box(76, 30, 22, 41, BLUE, "NUCLEO-G431RB",
    ["STM32G431, Cortex-M4F", "170 MHz, FPU (float32)", "",
     "bms_step (Ts = 0,1 s)", "",
     "SOC EKF [SOC V1 V2 b_I]", "",
     "sıcaklık gözlemcisi", "[Tc Ts g]", "",
     "sensör teşhisi", "",
     "çevrimiçi direnç kestirici", "",
     "karar: NORMAL / DERATE", "/ LIMP / SAFE", "",
     "pasif dengeleme"], strong=True)
box(76, 20.5, 22, 6, BLUE, "FDCAN1 (PA11/PA12, AF9)")
box(76, 12.5, 22, 5.5, BLUE, "TJA1050 alıcı-verici (5 V)")
arrow((87, 30), (87, 26.5), both=True)
arrow((87, 20.5), (87, 18), both=True)

box(100, 64, 13, 7, GRAY, "ST-LINK\nSWD + VCP")
box(100, 54, 13, 7.5, MAGENTA, "Güvenlik\nIWDG ~100 ms\nflash CRC, reset")
box(100, 46, 13, 5.5, AQUA, "CORDIC\nexp / log")
box(100, 38, 13, 5.5, AQUA, "Lojik analizör\nTIM6 + DMA1")
box(100, 28, 13, 7.5, BLUE, "Çıkış katı\nTIM1 PWM 1 kHz\nPA8/PA9, PB5")
arrow((98, 31.5), (100, 31.5))
arrow((100, 67.5), (98, 67.5), both=True, label="COM9", loff=(-0.1, 0.4), lsize=6.5)

# ------------------------------------------------------------ çıkışlar
group(117, 22, 22, 50, YELLOW, "ÇIKIŞLAR")
box(119, 50, 18, 13, YELLOW, "ULN2003 + LED",
    ["kısa far PA8 (D7)", "uzun far PA9 (D8)", "parlaklık = I_allow"])
box(119, 26, 18, 16, YELLOW, "Röle modülü",
    ["PB5 (D4), açık-akaçlı", "düşükte tetiklenen", "= ana kontaktör",
     "(SAFE → açar)"])
ax.plot([113, 115, 115], [34, 34, 56.5], color=INK2, linewidth=1.2)
arrow((115, 56.5), (119, 56.5))
ax.text(115.5, 45, "PWM", ha="left", va="center", fontsize=6.5, color=INK2, rotation=90)
arrow((113, 30), (119, 33), label="K", lpos=0.55, loff=(0, -2.5), lsize=6.5)

# ------------------------------------------------------------ CAN hattı
ax.plot([10, 112], [7.2, 7.2], color=INK, linewidth=2.0)
ax.plot([10, 112], [5.0, 5.0], color=INK, linewidth=2.0, linestyle=(0, (6, 2)))
ax.text(9, 7.2, "CANH", ha="right", va="center", fontsize=7.5)
ax.text(9, 5.0, "CANL", ha="right", va="center", fontsize=7.5)
ax.text(61, 2.0, "CAN 2.0 (klasik), 500 kbit/s  ·  ölçülen hat yükü %1,6",
        ha="center", va="center", fontsize=8, fontweight="bold")
for x in (33, 87):
    ax.plot([x - 1, x - 1], [12.5, 7.2], color=INK, linewidth=1.2)
    ax.plot([x + 1, x + 1], [12.5, 5.0], color=INK, linewidth=1.2, linestyle=(0, (3, 1.5)))

# ------------------------------------------------------------ mantıksal mesaj akışı
ax.text(61, 73, "mantıksal veri akışı (CAN üzerinden)", ha="center", va="center",
        fontsize=7.5, style="italic", color=INK2)
arrow((46, 64), (76, 64), col=ORANGE, lw=1.6)
ax.text(61, 64.8, "EMU → ECU", ha="center", va="bottom", fontsize=8,
        fontweight="bold", color=ORANGE)
ax.text(61, 63.0, "0x101  V, I, T paket (10 Hz)\n0x102  V_min, V_max, T_ortam\n"
        "0x110–0x114  19 grup gerilimi\n(4 x 12 bit, 1 mV) + dengeleme geri bildirimi\n0x301  PC komutu / hata enjeksiyonu",
        ha="center", va="top", fontsize=7, color=INK2, linespacing=1.35)
arrow((76, 44), (46, 44), col=BLUE, lw=1.6)
ax.text(61, 44.8, "ECU → EMU", ha="center", va="bottom", fontsize=8,
        fontweight="bold", color=BLUE)
ax.text(61, 43.0, "0x201  I_allow deşarj / şarj, durum, sebep\n0x202  SOC, Tc kestirimi, SOH, ψ\n"
        "0x210  19 bit dengeleme maskesi",
        ha="center", va="top", fontsize=7, color=INK2, linespacing=1.35)
ax.text(61, 31, "her çerçevede E2E koruma:\n4 bit sayaç + CRC-8 SAE J1850\n"
        "(ölçüm kaybı 500 ms → SAFE)", ha="center", va="center", fontsize=7,
        color=INK2, linespacing=1.35,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor=GRID))

# ------------------------------------------------------------ PC bağlantıları
arrow((33, 84), (33, 71), both=True, label="USB seri COM10\n(komut, R satırı)",
      lpos=0.5, loff=(1.0, 3.2), lha="left", lsize=6.5)
arrow((106.5, 84), (106.5, 71), both=True, label="USB (SWD yükleme/reset,\nCOM9 telemetri)",
      lpos=0.5, loff=(-1.0, 3.2), lha="right", lsize=6.5)

fig.tight_layout()
for ext in ("png", "pdf"):
    fig.savefig(os.path.join(OUT, f"system_block_diagram.{ext}"), dpi=200,
                bbox_inches="tight")
print("written:", os.path.join(OUT, "system_block_diagram.png"))
