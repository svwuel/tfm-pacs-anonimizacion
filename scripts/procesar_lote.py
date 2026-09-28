"""Procesa el dataset completo y genera las metricas del proceso.

Requiere haber ejecutado antes preparar_subset.py y reidentificar.py,
que generan los datos de partida en data/raw.
"""

import csv
from collections import defaultdict
from pathlib import Path

from anonimizador import MapeoPacientes, anonimizar_archivo

RAIZ = Path(__file__).resolve().parent.parent / "data"
ENTRADA = RAIZ / "raw"
SALIDA = RAIZ / "anonimizados"
# El registro relaciona identificadores originales y anonimizados.
# Con datos reales debe custodiarse aparte o eliminarse: quien disponga
# de el puede revertir la anonimizacion.
REGISTRO = RAIZ / "registro_anonimizacion.csv"

#Buscamos todos los .dcm dentro de la carpeta de entrada, incluidas subcarpetas.
encontrados = ENTRADA.rglob("*.dcm")

#Nos quedamos solo con los que son archivos de verdad.
solo_ficheros = []
for f in encontrados:
    if f.is_file():
        solo_ficheros.append(f)

#Los ordenamos alfabéticamente por su ruta.
ficheros = sorted(solo_ficheros)

print(f"Ficheros a procesar: {len(ficheros)}\n")

mapeo = MapeoPacientes()
filas = []
errores = []

for ruta in ficheros:
    relativa = ruta.relative_to(ENTRADA)     #paciente1/serie2/img.dcm
    destino = SALIDA / relativa              #.../data/anonimizados/paciente1/serie2/img.dcm
    try:
        info = anonimizar_archivo(ruta, destino, mapeo)
        #Le añadimos al diccionario una entrada más: dónde estaba el archivo.
        info["ruta"] = str(relativa)                        
        filas.append(info)
    except Exception as e:
        nombre_del_error = type(e).__name__     
        descripcion = f"{nombre_del_error}: {e}"
        errores.append((str(relativa), descripcion))

if not filas:
    raise SystemExit("No se ha procesado ningun fichero.")

campos = ["ruta", "archivo", "modalidad", "descripcion", "parte_anatomica",
          "paciente_original", "paciente_anon", "estudio_original",
          "estudio_anon", "serie_original", "serie_anon",
          "tamano_bytes", "segundos"]

#Volcado de resultados al informe CSV.
with open(REGISTRO, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=campos)
    w.writeheader()
    w.writerows(filas)


# --- Resultados -----------------------------------------------------------

n_pacientes, n_estudios = mapeo.resumen()
total_s = sum(f["segundos"] for f in filas)
total_mb = sum(f["tamano_bytes"] for f in filas) / 1_048_576

print(f"Instancias procesadas: {len(filas)}")
print(f"Pacientes:             {n_pacientes}")
print(f"Estudios:              {n_estudios}")
print(f"Errores:               {len(errores)}")
print(f"Tiempo total:          {total_s:.3f} s")
print(f"Volumen procesado:     {total_mb:.1f} MB")

for ruta, err in errores:
    print(f"  [ERROR] {ruta}: {err}")

# Tiempos por modalidad
por_modalidad = defaultdict(list)
for fila in filas:
    por_modalidad[fila["modalidad"]].append(fila)

print(f"\n{'Mod.':<6} {'N':>4} {'Total (s)':>11} {'Media (ms)':>12} "
      f"{'MB':>8} {'MB/s':>8}")
print("-" * 54)
for mod in sorted(por_modalidad):
    g = por_modalidad[mod]
    s = sum(x["segundos"] for x in g)
    mb = sum(x["tamano_bytes"] for x in g) / 1_048_576
    print(f"{mod:<6} {len(g):>4} {s:>11.3f} {s / len(g) * 1000:>12.2f} "
          f"{mb:>8.1f} {mb / s if s else 0:>8.1f}")
print("-" * 54)
print(f"{'TOTAL':<6} {len(filas):>4} {total_s:>11.3f} "
      f"{total_s / len(filas) * 1000:>12.2f} {total_mb:>8.1f} "
      f"{total_mb / total_s:>8.1f}")

# Tiempos por serie
print("\nTiempo por serie:")
por_serie = defaultdict(list)
for fila in filas:
    por_serie[(fila["modalidad"], fila["serie_original"])].append(fila)

for (mod, _), g in sorted(por_serie.items()):
    s = sum(x["segundos"] for x in g)
    desc = g[0]["descripcion"][:34]
    print(f"  {mod:<5} {len(g):>4} inst. {s:>8.3f} s   {desc}")

# Correspondencia de pacientes
print("\nCorrespondencia de pacientes:")
for original, anon in mapeo.tabla_pacientes().items():
    print(f"  {original:<32} -> {anon}")
