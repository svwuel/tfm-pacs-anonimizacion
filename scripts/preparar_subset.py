"""Construye un subconjunto manejable a partir de las descargas del IDC.

Toma 5 cortes centrales de cada serie, salvo las series marcadas como
completas, que se copian integras para poder demostrar la navegacion
por el volumen en OHIF.
"""

import shutil
from collections import defaultdict
from pathlib import Path

import pydicom

RAIZ = Path.home() / "tfm_bioinformatica/proyecto/data"
ORIGEN = RAIZ / "idc"
DESTINO = RAIZ / "subset"

CORTES_POR_SERIE = 5

# Series que se copian completas (por coleccion y modalidad).
# lungct_diagnosis CT: 130 cortes, manejable y util para demostrar
# la navegacion por el volumen en el visor.
COMPLETAS = {("lungct_diagnosis", "CT")}


def clave_orden(ds, ruta):
    """Ordena los cortes dentro de una serie.

    InstanceNumber es lo habitual; si falta, se recurre a la posicion
    espacial y, como ultimo recurso, al nombre del fichero.
    """
    num = getattr(ds, "InstanceNumber", None)
    if num is not None:
        return (0, float(num))
    pos = getattr(ds, "ImagePositionPatient", None)
    if pos is not None and len(pos) == 3:
        return (1, float(pos[2]))
    return (2, ruta.name)


def cortes_centrales(lista, n):
    """Devuelve n elementos del centro de la lista."""
    if len(lista) <= n:
        return lista
    inicio = (len(lista) - n) // 2
    return lista[inicio:inicio + n]


# --- Agrupacion por serie -------------------------------------------------

ficheros = sorted(f for f in ORIGEN.rglob("*.dcm") if f.is_file())
print(f"Ficheros en origen: {len(ficheros)}")

series = defaultdict(list)
for ruta in ficheros:
    ds = pydicom.dcmread(ruta, stop_before_pixels=True)
    coleccion = ruta.relative_to(ORIGEN).parts[0]
    modalidad = str(getattr(ds, "Modality", "?"))
    uid = str(getattr(ds, "SeriesInstanceUID", "?"))
    series[(coleccion, modalidad, uid)].append((clave_orden(ds, ruta), ruta))

# --- Seleccion y copia ----------------------------------------------------

if DESTINO.exists():
    shutil.rmtree(DESTINO)

copiados = 0
print(f"\n{'Coleccion':<32} {'Mod.':<5} {'Origen':>7} {'Copia':>7}")
print("-" * 55)

for (coleccion, modalidad, uid) in sorted(series):
    entradas = sorted(series[(coleccion, modalidad, uid)])
    rutas = [ruta for _, ruta in entradas]

    if (coleccion, modalidad) in COMPLETAS:
        seleccion = rutas
    else:
        seleccion = cortes_centrales(rutas, CORTES_POR_SERIE)

    for ruta in seleccion:
        relativa = ruta.relative_to(ORIGEN)
        salida = DESTINO / relativa
        salida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ruta, salida)
        copiados += 1

    print(f"{coleccion:<32} {modalidad:<5} {len(rutas):>7} {len(seleccion):>7}")

print("-" * 55)
print(f"{'TOTAL':<32} {'':<5} {len(ficheros):>7} {copiados:>7}")
print(f"\nSubconjunto creado en: {DESTINO}")
