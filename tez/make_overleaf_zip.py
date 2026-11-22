"""Overleaf için tek zip: main.tex, chapters/, references.bib ve tezde kullanılan figürler (figures/ altına).

Overleaf'te ../results/ yolu yok; graphicspath önce figures/ klasörüne bakar.
Kullanım: python make_overleaf_zip.py   -> ../results/../tez/build/tez_overleaf.zip
Overleaf: New Project > Upload Project > zip'i seç; Menu > Compiler: pdfLaTeX.
"""
import glob
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
OUT = os.path.join(HERE, "build", "tez_overleaf.zip")

tex_files = ["main.tex"] + sorted(glob.glob(os.path.join(HERE, "chapters", "*.tex")))
tex = "".join(open(os.path.join(HERE, f), encoding="utf-8").read() for f in tex_files)
names = sorted(set(re.findall(r"\\fig\{([^}#]+)\}", tex)) | set(re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}#]+)\}", tex)))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
missing = []
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for f in tex_files:
        z.write(os.path.join(HERE, f), os.path.relpath(os.path.join(HERE, f), HERE))
    z.write(os.path.join(HERE, "references.bib"), "references.bib")
    for n in names:
        src = next((os.path.join(RES, n + e) for e in (".pdf", ".png", ".jpg") if os.path.exists(os.path.join(RES, n + e))), None)
        if src:
            z.write(src, "figures/" + os.path.basename(src))
        else:
            missing.append(n)
print(f"{OUT}: {len(tex_files)} tex, {len(names) - len(missing)} figures")
if missing:
    print("missing figures:", missing)
