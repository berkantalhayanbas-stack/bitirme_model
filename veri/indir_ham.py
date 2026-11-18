"""Kirkaldy et al. (2024) Zenodo zip'inden seçilen ham/işlenmiş dosyaları (HTTP range) indirir.
Kullanım: python indir_ham.py <zip_no 1-5> <filtre1&filtre2...>   -> kirkaldy_ham/<zip içi yol>
Lisans: CC BY 4.0, doi:10.5281/zenodo.10637534 (atıf gerekli)."""
import os
import shutil
import sys
from urllib.parse import quote
from remotezip import RemoteZip

RECORD = "https://zenodo.org/records/10637534/files/"
ZIPS = ["Expt 1 - Si-based Degradation.zip", "Expt 2,2 - C-based Degradation 2.zip",
        "Expt 3 - Cathode Degradation and Li-Plating.zip", "Expt 4 - Drive Cycle Aging (Control).zip",
        "Expt 5 - Standard Cycle Aging (Control).zip"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "kirkaldy_ham")
no, filtre = int(sys.argv[1]), sys.argv[2].split("&")
with RemoteZip(RECORD + quote(ZIPS[no - 1]) + "?download=1") as z:
    uy = [i for i in z.infolist() if not i.is_dir() and all(f in i.filename for f in filtre)]
    print(f"{len(uy)} dosya, {sum(i.compress_size for i in uy) / 1e6:.1f} MB")
    for i in uy:
        hedef = os.path.join(OUT, i.filename)
        if os.path.exists(hedef) and os.path.getsize(hedef) == i.file_size:
            continue
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        with z.open(i) as src, open(hedef, "wb") as dst:
            shutil.copyfileobj(src, dst)
        print("  +", i.filename)
