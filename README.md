# Anonimización de imágenes DICOM y despliegue de un PACS con Docker

Código del Trabajo Fin de Máster *Desarrollo de un sistema de anonimización de imágenes DICOM y despliegue de un PACS mediante Docker para la integración de imágenes médicas* (Máster Universitario en Bioinformática, Universidad Europea de Madrid).

- **Autor:** Samuel Libert Sánchez Cabrera
- **Tutor:** Adrián Galiana Borderá

El proyecto tiene tres partes: una infraestructura PACS desplegada con Docker Compose (Orthanc, PostgreSQL y el visor OHIF), un módulo de anonimización de cabeceras DICOM escrito en Python y un flujo que envía las imágenes anonimizadas al servidor mediante STOW-RS (DICOMweb).

## Estructura del repositorio

```
.
├── docker/
│   ├── docker-compose.yml     # Orthanc + PostgreSQL + plugins DICOMweb y OHIF
│   └── .env.example           # Plantilla de credenciales y puertos
├── scripts/
│   ├── preparar_subset.py     # Selecciona un subconjunto de las descargas del IDC
│   ├── reidentificar.py       # Inyecta datos ficticios de paciente
│   ├── anonimizador.py        # Módulo de anonimización (política y funciones)
│   ├── procesar_lote.py       # Anonimiza el dataset completo y genera métricas
│   ├── enviar_orthanc.py      # Envío de instancias por STOW-RS
│   └── integrar.py            # Carga el dataset anonimizado en Orthanc
├── .gitignore
└── README.md
```

La carpeta `data/` no se incluye en el repositorio, porque contiene las imágenes. Los scripts la esperan en la raíz del proyecto, al mismo nivel que `scripts/`.

## Requisitos

- Docker Desktop (o Docker Engine con Docker Compose)
- Python 3 con las librerías `pydicom` y `requests`

## 1. Levantar la infraestructura

```bash
cd docker
cp .env.example .env
```

Edita `.env` y cambia las credenciales de ejemplo. El archivo tiene que estar en la misma carpeta que `docker-compose.yml`; si no, Compose deja las variables vacías sin avisar. Conviene no usar caracteres especiales como la ñ en las contraseñas.

```bash
docker compose up -d
```

Una vez arrancado, Orthanc está disponible en `http://localhost:8042` (o en el puerto definido en `ORTHANC_HTTP_PORT`) y el visor OHIF en `http://localhost:8042/ohif/`.

Las credenciales de PostgreSQL se fijan la primera vez que se crea el volumen. Si se cambian después en `.env`, hay que recrearlo con `docker compose down -v`, lo que borra también los estudios almacenados.

## 2. Preparar el entorno de Python

Desde la raíz del proyecto:

```bash
python3 -m venv venv
source venv/bin/activate
pip install pydicom requests
```

## 3. Datos de partida

El trabajo usa imágenes públicas del [Imaging Data Commons (IDC)](https://portal.imaging.datacommons.cancer.gov/) de varias modalidades (TC, RM, RX, MG, PET). Las descargas deben colocarse en `data/idc/`, con una subcarpeta por colección:

```
data/idc/<coleccion>/.../*.dcm
```

`preparar_subset.py` contiene identificadores de series concretas de la descarga original del TFM. Si se usan otras imágenes, hay que ajustar las constantes del principio del script.

## 4. Flujo de trabajo

Los scripts se ejecutan desde la raíz del proyecto y en este orden:

```bash
python scripts/preparar_subset.py    # data/idc    -> data/subset
python scripts/reidentificar.py      # data/subset -> data/raw
python scripts/procesar_lote.py      # data/raw    -> data/anonimizados
```

Las imágenes del IDC ya vienen desidentificadas, así que `reidentificar.py` les inyecta datos ficticios (nombre, fecha de nacimiento, dirección, médicos, institución y número de acceso) para disponer de algo que anonimizar.

Para cargar el resultado en Orthanc, exporta las credenciales en la terminal con los mismos valores que en `.env`. Python no lee ese archivo:

```bash
export ORTHANC_USER=...
export ORTHANC_PASSWORD=...
python scripts/integrar.py
```

Si el servidor no está en `http://localhost:8042`, define también `ORTHANC_URL`. Es recomendable exportar estas variables en una terminal distinta de la que se usa para Docker Compose, porque las variables del entorno tienen prioridad sobre el `.env` al lanzar los contenedores.

## Política de anonimización

El módulo implementa un subconjunto del *Basic Application Level Confidentiality Profile* (DICOM PS 3.15, Anexo E):

| Acción | Atributos |
|---|---|
| Sustitución por pseudónimo | `PatientName`, `PatientID`, `AccessionNumber` |
| Sustitución por valor fijo | `InstitutionName` |
| Vaciado | `PatientBirthDate`, `ReferringPhysicianName` |
| Eliminación | Direcciones de paciente, institución y médico, resto de personal sanitario, departamento |
| Regeneración determinista | `StudyInstanceUID`, `SeriesInstanceUID`, `SOPInstanceUID` |

Cada paciente recibe siempre el mismo pseudónimo y los UIDs se regeneran a partir de un hash SHA-256, de modo que los cortes de una misma serie y las series de un mismo estudio se mantienen agrupados en el PACS. Los datos de píxel no se modifican.

## Limitaciones

- No detecta ni elimina texto impreso sobre los píxeles de la imagen (habitual en ecografías).
- `procesar_lote.py` genera `data/registro_anonimizacion.csv`, que relaciona los identificadores originales con los anonimizados. Con datos reales, ese archivo permite revertir el proceso y debe custodiarse aparte o eliminarse.
- Es un desarrollo académico y no está validado para uso clínico.
