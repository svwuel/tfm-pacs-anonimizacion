"""Envio de instancias DICOM a Orthanc mediante STOW-RS (DICOMweb).

Construye manualmente el cuerpo multipart/related que exige el estandar
y lo envia al endpoint /dicom-web/studies del servidor.
"""

import os
import uuid
from pathlib import Path

import requests

ORTHANC = os.environ.get("ORTHANC_URL", "http://localhost:8042")

try:
    AUTH = (os.environ["ORTHANC_USER"], os.environ["ORTHANC_PASSWORD"])
except KeyError:
    raise SystemExit(
        "Faltan las credenciales de Orthanc. Definelas antes de ejecutar:\n"
        "  export ORTHANC_USER=...\n"
        "  export ORTHANC_PASSWORD=..."
    )


def enviar_stow(rutas):
    """Envia una o varias instancias DICOM mediante STOW-RS."""
    frontera = uuid.uuid4().hex
    partes = []

    for ruta in rutas:
        cabecera_texto = f"--{frontera}\r\nContent-Type: application/dicom\r\n\r\n"
        cabecera = cabecera_texto.encode()
        contenido = ruta.read_bytes()
        cierre = b"\r\n"
        partes.append(cabecera + contenido + cierre)
        
    cuerpo = b"".join(partes)
    cuerpo = cuerpo + f"--{frontera}--\r\n".encode()

    cabeceras = {
        "Content-Type": f'multipart/related; type="application/dicom"; boundary={frontera}',
        "Accept": "application/dicom+json",
    }

    r = requests.post(f"{ORTHANC}/dicom-web/studies", data=cuerpo,
                      headers=cabeceras, auth=AUTH, timeout=120)
    r.raise_for_status()
    return r


