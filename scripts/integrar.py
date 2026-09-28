"""Carga el conjunto anonimizado en el servidor PACS mediante STOW-RS."""

import os
import time
from collections import defaultdict
from pathlib import Path

import pydicom
import requests

from enviar_orthanc import enviar_stow

ORTHANC = os.environ.get("ORTHANC_URL", "http://localhost:8042")
try:
    AUTH = (os.environ["ORTHANC_USER"], os.environ["ORTHANC_PASSWORD"])
except KeyError:
    raise SystemExit(
        "Faltan las credenciales de Orthanc. Definelas antes de ejecutar:\n"
        "  export ORTHANC_USER=...\n"
        "  export ORTHANC_PASSWORD=..."
    )
RAIZ = Path(__file__).resolve().parent.parent / "data" / "anonimizados"

encontrados = RAIZ.rglob("*.dcm")

solo_ficheros = []
for f in encontrados:
    if f.is_file():
        solo_ficheros.append(f)

ficheros = sorted(solo_ficheros)       
print(f"Instancias a enviar: {len(ficheros)}")

# Se agrupa por serie: STOW-RS admite varias instancias por peticion,
# lo que reduce la sobrecarga frente al envio individual.
series = defaultdict(list)
for ruta in ficheros:
    ds = pydicom.dcmread(ruta, stop_before_pixels=True)
    series[str(ds.SeriesInstanceUID)].append(ruta)

print(f"Series: {len(series)}\n")

enviadas = 0
fallidas = []
t0 = time.perf_counter()

for uid, rutas in series.items():
    try:
        r = enviar_stow(rutas)
        enviadas += len(rutas)
        print(f"  {len(rutas):>4} inst. -> {r.status_code}")
    except Exception as e:
        fallidas.append((uid, f"{type(e).__name__}: {e}"))
        print(f"  [ERROR] {uid[:20]}...: {type(e).__name__}")

transcurrido = time.perf_counter() - t0

print(f"\nInstancias enviadas: {enviadas}/{len(ficheros)}")
print(f"Series fallidas:     {len(fallidas)}")
print(f"Tiempo total:        {transcurrido:.2f} s")

# /statistics refleja todo el contenido del servidor, no solo este envio.
# Los recuentos coinciden con el dataset si el PACS estaba vacio.
est = requests.get(f"{ORTHANC}/statistics", auth=AUTH, timeout=10).json()
print(f"\nContenido del servidor:")
print(f"  Pacientes:  {est['CountPatients']}")
print(f"  Estudios:   {est['CountStudies']}")
print(f"  Series:     {est['CountSeries']}")
print(f"  Instancias: {est['CountInstances']}")
