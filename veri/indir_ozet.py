"""
Kirkaldy et al. (2024) Zenodo veri setinden YALNIZCA 'Summary Data' klasörlerini indirir.
49 GB'lık zip dosyalarının tamamını indirmez; HTTP range istekleriyle zip'in
içinden sadece gerekli küçük CSV dosyalarını çeker (toplam birkaç MB).

Kurulum (bir kez):   pip install remotezip
Çalıştırma:          python indir_ozet.py
Çıktı:               kirkaldy_ozet/ klasörü ve kirkaldy_ozet.zip (bunu Claude'a yükle)
"""
import os
import sys
import shutil
import time
from urllib.parse import quote

try:
    from remotezip import RemoteZip
except ImportError:
    sys.exit("Önce şunu çalıştır:  pip install remotezip")

RECORD = "https://zenodo.org/records/10637534/files/"
ZIPS = [
    "Expt 1 - Si-based Degradation.zip",
    "Expt 2,2 - C-based Degradation 2.zip",
    "Expt 3 - Cathode Degradation and Li-Plating.zip",
    "Expt 4 - Drive Cycle Aging (Control).zip",
    "Expt 5 - Standard Cycle Aging (Control).zip",
]
OUT = "kirkaldy_ozet"
os.makedirs(OUT, exist_ok=True)

toplam = 0
for zname in ZIPS:
    url = RECORD + quote(zname) + "?download=1"
    print(f"\n=== {zname}")
    for deneme in range(3):
        try:
            with RemoteZip(url) as z:
                uyelar = [i for i in z.infolist()
                          if "Summary Data" in i.filename and not i.is_dir()]
                boyut = sum(i.file_size for i in uyelar)
                print(f"  {len(uyelar)} özet dosya bulundu ({boyut/1e6:.2f} MB)")
                for i in uyelar:
                    hedef = os.path.join(OUT, i.filename)
                    os.makedirs(os.path.dirname(hedef), exist_ok=True)
                    with z.open(i) as src, open(hedef, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    toplam += 1
                    print("   +", i.filename)
            break
        except Exception as e:
            print(f"  Hata (deneme {deneme+1}/3): {e}")
            time.sleep(3)
    else:
        print(f"  !!! {zname} indirilemedi. Bu hatayı Claude'a gönder.")

shutil.copy("experiment_metadata.xlsx", OUT) if os.path.exists("experiment_metadata.xlsx") else None
shutil.make_archive("kirkaldy_ozet", "zip", OUT)
print(f"\nBitti: {toplam} dosya. 'kirkaldy_ozet.zip' dosyasını Claude'a yükle.")
