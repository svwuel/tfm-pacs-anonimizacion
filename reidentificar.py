"""Inyecta datos sinteticos en el subconjunto del IDC.

Las imagenes publicas vienen ya desidentificadas, por lo que no contienen
datos que el modulo pueda eliminar. Este script les reinyecta valores
ficticios en los campos contemplados por la politica de anonimizacion,
generando asi el dataset de partida (data/raw).

Los campos inyectados se corresponden con el subconjunto del Basic
Application Level Confidentiality Profile (DICOM PS 3.15, Anexo E)
implementado en el modulo.
"""

from pathlib import Path

import pydicom
import re
from anonimizador import normalizar_id

RAIZ = Path(__file__).resolve().parent.parent / "data"
ORIGEN = RAIZ / "subset"
DESTINO = RAIZ / "raw"

# --- Datos sinteticos por paciente ---------------------------------------

PACIENTES = [
    ("GARCIA LOPEZ^MARIA",      "19640312", "Calle Mayor 12, Madrid"),
    ("MARTINEZ RUIZ^ANTONIO",   "19580724", "Avenida del Parque 8, Madrid"),
    ("FERNANDEZ SOTO^CARMEN",   "19710105", "Calle del Olivo 45, Sevilla"),
    ("LOPEZ VEGA^JOSE",         "19490918", "Plaza Nueva 3, Valencia"),
    ("SANCHEZ DIAZ^ANA",        "19820226", "Calle Alta 27, Bilbao"),
    ("ROMERO GIL^MANUEL",       "19551130", "Camino Real 19, Zaragoza"),
    ("NAVARRO PEREZ^LUCIA",     "19760614", "Calle Corta 5, Malaga"),
    ("TORRES BLANCO^PEDRO",     "19670803", "Ronda Sur 61, Murcia"),
    ("IGLESIAS MORA^ELENA",     "19900419", "Calle Larga 14, Valladolid"),
    ("CASTRO HERRERA^JAVIER",   "19620207", "Paseo del Rio 30, Granada"),
    ("ORTEGA LUNA^ISABEL",      "19851122", "Calle Nueva 9, Alicante"),
]

MEDICOS_PETICIONARIOS = ["SANZ MOLINA^LUIS", "VIDAL CAMPOS^MARTA"]
MEDICOS_RESPONSABLES  = ["TORRES DIAZ^ELENA", "MORENO SILVA^ANDRES"]

INSTITUCIONES = [
    ("Hospital Universitario de Madrid",  "Avenida de la Salud 100, Madrid"),
    ("Centro Diagnostico del Cáncer",       "Calle los Cedros 22, Barcelona"),
]

def normalizar_id(patient_id):
    """Corrige el PatientID en colecciones donde incluye la proyeccion.

    CBIS-DDSM identifica cada proyeccion como un paciente distinto
    (P_00038_RIGHT_CC), cuando en realidad corresponden al mismo sujeto.
    Se conserva unicamente el identificador del paciente (P_00038).
    """
    pid = str(patient_id)
    m = re.match(r"^(P_\d+)", pid)
    return m.group(1) if m else pid

class AsignadorDatos:
    """Asigna datos sinteticos estables a cada PatientID original."""

    def __init__(self):
        self._pacientes = {}
        self._estudios = {}

    def datos_paciente(self, patient_id_original):
        clave = str(patient_id_original)
        if clave not in self._pacientes:
            i = len(self._pacientes)
            if i >= len(PACIENTES):
                raise IndexError(
                    f"Mas pacientes ({i + 1}) que entradas en PACIENTES "
                    f"({len(PACIENTES)}). Anade mas nombres a la lista."
                )
            nombre, fecha, direccion = PACIENTES[i]
            institucion, dir_inst = INSTITUCIONES[i % len(INSTITUCIONES)]
            self._pacientes[clave] = {
                "nombre": nombre,
                "fecha_nacimiento": fecha,
                "direccion": direccion,
                "institucion": institucion,
                "direccion_institucion": dir_inst,
                "peticionario": MEDICOS_PETICIONARIOS[i % len(MEDICOS_PETICIONARIOS)],
                "responsable": MEDICOS_RESPONSABLES[i % len(MEDICOS_RESPONSABLES)],
            }
        return self._pacientes[clave]

    def numero_acceso(self, study_uid):
        clave = str(study_uid)
        if clave not in self._estudios:
            self._estudios[clave] = f"ACC{len(self._estudios) + 1:06d}"
        return self._estudios[clave]

    def resumen(self):
        return len(self._pacientes), len(self._estudios)


def reidentificar(ruta_entrada, ruta_salida, asignador):
    ds = pydicom.dcmread(ruta_entrada)

    datos = asignador.datos_paciente(normalizar_id(getattr(ds, "PatientID", "SIN_ID")))

    # Identificadores directos del paciente
    ds.PatientName = datos["nombre"]
    ds.PatientBirthDate = datos["fecha_nacimiento"]
    ds.PatientAddress = datos["direccion"]

    # Numero de acceso, unico por estudio
    ds.AccessionNumber = asignador.numero_acceso(
        getattr(ds, "StudyInstanceUID", "SIN_UID")
    )

    # Institucion
    ds.InstitutionName = datos["institucion"]
    ds.InstitutionAddress = datos["direccion_institucion"]

    # Personal sanitario
    ds.ReferringPhysicianName = datos["peticionario"]
    ds.PerformingPhysicianName = datos["responsable"]
    
    # Las imagenes del IDC vienen marcadas como desidentificadas; tras
    # inyectar datos ficticios, esa marca deja de ser cierta.
    ds.PatientIdentityRemoved = "NO"
    if "DeidentificationMethod" in ds:
        del ds.DeidentificationMethod

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(ruta_salida)

    return datos["nombre"]


# --- Proceso --------------------------------------------------------------

ficheros = sorted(f for f in ORIGEN.rglob("*.dcm") if f.is_file())
print(f"Ficheros a procesar: {len(ficheros)}")

asignador = AsignadorDatos()
procesados = 0

for ruta in ficheros:
    relativa = ruta.relative_to(ORIGEN)
    try:
        reidentificar(ruta, DESTINO / relativa, asignador)
        procesados += 1
    except Exception as e:
        print(f"[ERROR] {relativa}: {type(e).__name__}: {e}")

n_pacientes, n_estudios = asignador.resumen()
print(f"\nProcesados:  {procesados}")
print(f"Pacientes:   {n_pacientes}")
print(f"Estudios:    {n_estudios}")
print(f"Destino:     {DESTINO}")

print("\nCorrespondencia asignada:")
for original, datos in asignador._pacientes.items():
    print(f"  {original:<32} -> {datos['nombre']}")