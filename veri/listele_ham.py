"""Kirkaldy et al. (2024) Zenodo zip'lerinin içeriğini (ham veri klasörleri, boyutlar) listeler; indirmez.
Kullanım: python listele_ham.py [zip_no 1-5] [dosya adı filtresi]
Filtresiz: klasör özetleri; filtreli: eşleşen dosyalar."""
import collections
import sys
from urllib.parse import quote
from remotezip import RemoteZip

RECORD = "https://zenodo.org/records/10637534/files/"
ZIPS = ["Expt 1 - Si-based Degradation.zip", "Expt 2,2 - C-based Degradation 2.zip",
        "Expt 3 - Cathode Degradation and Li-Plating.zip", "Expt 4 - Drive Cycle Aging (Control).zip",
        "Expt 5 - Standard Cycle Aging (Control).zip"]
no = int(sys.argv[1]) if len(sys.argv) > 1 else 5
filtre = sys.argv[2] if len(sys.argv) > 2 else None
with RemoteZip(RECORD + quote(ZIPS[no - 1]) + "?download=1") as z:
    uy = [i for i in z.infolist() if not i.is_dir() and "Summary Data" not in i.filename]
    if filtre is None:
        g = collections.OrderedDict()
        for i in uy:
            k = "/".join(i.filename.split("/")[1:-1])
            n, s = g.get(k, (0, 0))
            g[k] = (n + 1, s + i.compress_size)
        for k, (n, s) in g.items():
            print(f"{n:5d} dosya {s / 1e6:9.1f} MB  {k}")
    else:
        for i in uy:
            if all(f in i.filename for f in filtre.split("&")):
                print(f"{i.compress_size / 1e6:9.1f} MB  {i.filename}")
