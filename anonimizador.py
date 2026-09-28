"""Modulo de anonimizacion de imagenes DICOM.

Implementa un subconjunto pragmatico del Basic Application Level
Confidentiality Profile (DICOM PS 3.15, Anexo E), adaptado a las
necesidades del proyecto.

Acciones aplicadas, siguiendo la clasificacion del propio anexo:
  - Sustitucion por valor ficticio: atributos obligatorios que deben
    conservar un valor valido (tipo 1).
  - Vaciado: atributos obligatorios que admiten valor nulo (tipo 2).
  - Eliminacion: atributos opcionales (tipo 3).
  - Regeneracion determinista: identificadores unicos (UID).

Los datos de pixel no se modifican en ningun momento, por lo que la
compresion original de la imagen se conserva intacta.
"""

import hashlib
import re
import time
from pathlib import Path

import pydicom
from pydicom.uid import generate_uid
from pydicom.datadict import tag_for_keyword

# --- Politica de anonimizacion -------------------------------------------

# Sustitucion por valor fijo
SUSTITUIR_FIJOS = {
    "InstitutionName": "CENTRO_ANONIMIZADO",
}

# Vaciado (el atributo permanece, sin contenido)
VACIAR = [
    "PatientBirthDate",
    "ReferringPhysicianName",
]

# Eliminacion completa del atributo
ELIMINAR = [
    "PatientAddress",
    "InstitutionAddress",
    "ReferringPhysicianAddress",
    "PerformingPhysicianName",
    "PhysiciansOfRecord",
    "NameOfPhysiciansReadingStudy",
    "OperatorsName",
    "InstitutionalDepartmentName",
]

# Identificadores unicos regenerados de forma determinista
UIDS = [
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
]

# Comprobacion de integridad de la politica: una errata en una palabra
# clave dejaria el atributo sin anonimizar sin que pydicom avisase.

# 1. Reunimos en una sola lista todas las palabras clave de la política.
todas_las_claves = []
todas_las_claves = todas_las_claves + list(SUSTITUIR_FIJOS)  # solo los nombres, no los valores
todas_las_claves = todas_las_claves + VACIAR
todas_las_claves = todas_las_claves + ELIMINAR
todas_las_claves = todas_las_claves + UIDS

# 2. Preparamos una lista vacía donde iremos guardando las que estén mal escritas.
erratas = []

# 3. Recorremos las claves una a una.
for clave in todas_las_claves:
    tag = tag_for_keyword(clave)   # devuelve el tag DICOM, o None si no existe

    if tag is None:
        erratas.append(clave)      # no la reconoce el estándar: es una errata

# 4. Si hemos encontrado alguna, paramos el script con un error explicativo.
if erratas:
    raise ValueError(f"Palabras clave no reconocidas: {erratas}")


# --- Utilidades -----------------------------------------------------------

def normalizar_id(patient_id):
    """Corrige identificadores que incluyen informacion de la proyeccion.

    La coleccion CBIS-DDSM identifica cada proyeccion mamografica como un
    paciente distinto (P_00038_RIGHT_CC), cuando corresponden al mismo
    sujeto. Se conserva unicamente el identificador del paciente.
    """
    pid = str(patient_id)
    m = re.match(r"^(P_\d+)", pid)
    return m.group(1) if m else pid


def nuevo_uid(uid_original):
    """Genera un UID nuevo de forma determinista.

    El mismo UID de entrada produce siempre el mismo UID de salida, lo que
    preserva la jerarquia estudio / serie / instancia: los cortes que
    compartian SeriesInstanceUID lo siguen compartiendo tras el proceso.
    La transformacion no es invertible.
    """
    semilla = hashlib.sha256(str(uid_original).encode()).hexdigest()
    return generate_uid(entropy_srcs=[semilla])


class MapeoPacientes:
    """Asigna pseudonimos estables a cada paciente y estudio."""

    def __init__(self):
        self._pacientes = {}
        self._estudios = {}

    def pseudonimo(self, patient_id_original):
        clave = normalizar_id(patient_id_original)
        if clave not in self._pacientes:
            self._pacientes[clave] = f"ANON{len(self._pacientes) + 1:03d}"
        return self._pacientes[clave]

    def numero_acceso(self, study_uid):
        clave = str(study_uid)
        if clave not in self._estudios:
            self._estudios[clave] = f"ANONACC{len(self._estudios) + 1:06d}"
        return self._estudios[clave]

    def tabla_pacientes(self):
        return dict(self._pacientes)

    def resumen(self):
        return len(self._pacientes), len(self._estudios)
    


# --- Anonimizacion --------------------------------------------------------

def anonimizar_dataset(ds, mapeo):
    """Aplica la politica de anonimizacion sobre un dataset en memoria."""

    id_original = getattr(ds, "PatientID", "SIN_ID")   
    seudonimo = mapeo.pseudonimo(id_original)
    
    ds.PatientName = seudonimo
    ds.PatientID = seudonimo

    # 1. Leemos el UID del estudio. Si el archivo no lo tiene, usamos "SIN_UID".
    uid_del_estudio = getattr(ds, "StudyInstanceUID", "SIN_UID")
    # → "1.2.840.113619.2.55.3.604688.9.1234"

    # 2. Se lo pasamos al objeto mapeo, que nos devuelve el número de acceso.
    numero = mapeo.numero_acceso(uid_del_estudio)
    # → "ACC000001"

    # 3. Guardamos ese número en el campo AccessionNumber del archivo.
    ds.AccessionNumber = numero

    for kw, valor in SUSTITUIR_FIJOS.items():
        setattr(ds, kw, valor)

    for kw in VACIAR:
        if kw in ds:
            setattr(ds, kw, "")

    for kw in ELIMINAR:
        if kw in ds:
            delattr(ds, kw)

    for kw in UIDS:
        if kw in ds:
            setattr(ds, kw, nuevo_uid(ds[kw].value))

    # El SOPInstanceUID aparece tambien en la metainformacion del fichero;
    # si ambos no coinciden, el objeto queda internamente incoherente y
    # puede ser rechazado por el servidor PACS.
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = (
        "Subconjunto del perfil basico DICOM PS 3.15 Anexo E - TFM"
    )

    return ds


def anonimizar_archivo(ruta_entrada, ruta_salida, mapeo):
    """Anonimiza un fichero y devuelve los metadatos del proceso."""
    ruta_entrada = Path(ruta_entrada)
    ruta_salida = Path(ruta_salida)
    t0 = time.perf_counter()

    ds = pydicom.dcmread(ruta_entrada)

    modalidad = str(getattr(ds, "Modality", "?"))
    descripcion = str(getattr(ds, "SeriesDescription", ""))
    parte = str(getattr(ds, "BodyPartExamined", ""))
    paciente_original = str(getattr(ds, "PatientID", ""))
    estudio_original = str(getattr(ds, "StudyInstanceUID", ""))
    serie_original = str(getattr(ds, "SeriesInstanceUID", ""))

    anonimizar_dataset(ds, mapeo)

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(ruta_salida)

    return {
        "archivo": ruta_entrada.name,
        "modalidad": modalidad,
        "descripcion": descripcion,
        "parte_anatomica": parte,
        "paciente_original": paciente_original,
        "paciente_anon": str(ds.PatientID),
        "estudio_original": estudio_original,
        "estudio_anon": str(ds.StudyInstanceUID),
        "serie_original": serie_original,
        "serie_anon": str(ds.SeriesInstanceUID),
        "tamano_bytes": ruta_entrada.stat().st_size,
        "segundos": round(time.perf_counter() - t0, 5),
    }