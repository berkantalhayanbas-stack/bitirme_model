"""simulink/twin_reference.csv'yi Python dijital ikiziyle yeniden üretir (aynı akım profili).
battery_model.py parametreleri (ör. OCV tablosu) değişince çalıştırılır; run_and_compare.m
Simulink ikizini buna karşı doğrular. Sütunlar: t, speed_kmh, i_pack (girdi, korunur), soc, v_pack, t_core, t_surf."""
import os
import pandas as pd
from battery_model import PackTwin, CellParams, PackConfig

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, "..", "simulink", "twin_reference.csv")
ref = pd.read_csv(F)
dt = float(ref.t.iloc[1] - ref.t.iloc[0])
twin = PackTwin(CellParams(), PackConfig(), soc0=0.8)
d = pd.DataFrame([twin.step(i, dt) for i in ref.i_pack.values])
old = ref.copy()
for k in ("soc", "v_pack", "t_core", "t_surf"):
    ref[k] = d[k].values
ref.to_csv(F, index=False)
print(f"yazildi {len(ref)} satir; v_pack degisimi max {1e3 * (ref.v_pack - old.v_pack).abs().max():.0f} mV, "
      f"t_core max {(ref.t_core - old.t_core).abs().max():.3f} C")
