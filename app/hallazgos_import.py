"""Validación y preparación de archivos CSV para importar hallazgos."""
from __future__ import annotations

import base64
import binascii
import csv
import io
import unicodedata
from datetime import datetime


CSV_COLUMNS = [
    "Estado",
    "Fecha hallazgo",
    "Fecha cierre",
    "Motor",
    "Script",
    "Función",
    "Descripción",
]
ESTADOS = {"abierto": "Abierto", "en revision": "En revisión", "cerrado": "Cerrado"}
EMPTY_CLOSING_DATES = {"", "-", "—", "–"}


def template_csv() -> str:
    """Devuelve la plantilla oficial, incluyendo BOM para Excel en español."""
    return "\ufeff" + ",".join(CSV_COLUMNS) + "\n"


def _normalized(value: object) -> str:
    text = "" if value is None else " ".join(str(value).split())
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(char)
    )


def _decode_upload(contents: str) -> str:
    if not contents or "," not in contents:
        raise ValueError("No fue posible leer el archivo seleccionado.")
    raw = base64.b64decode(contents.split(",", 1)[1])
    if not raw.strip():
        raise ValueError("El archivo CSV está vacío.")
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("El archivo no tiene una codificación compatible.")


def _parse_date(value: str, required: bool) -> tuple[str | None, str | None]:
    value = value.strip()
    if not value and required:
        return None, "La fecha hallazgo es obligatoria."
    if not value:
        return None, None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat(), None
    except ValueError:
        return None, "Usa fechas con formato DD/MM/YYYY."


def _existing_keys(existing_rows, project: str) -> set[tuple[str, str, str, str]]:
    return {
        (_normalized(row.get("Motor")), _normalized(row.get("Script")),
         _normalized(row.get("Función")), _normalized(row.get("Descripción")))
        for row in existing_rows
        if _normalized(row.get("Proyecto")) == _normalized(project)
    }


def validate_hallazgos_csv(contents: str, filename: str | None, existing_rows, project: str) -> dict:
    """Valida un CSV y devuelve filas preparadas para la vista previa.

    La llave Motor+Script+Función+Descripción normalizada se compara contra el
    proyecto seleccionado. Una coincidencia exacta se bloquea para preservar la
    unicidad que exige la persistencia actual; coincidencias aproximadas quedan
    marcadas como advertencia cuando corresponda.
    """
    if not filename or not filename.lower().endswith(".csv"):
        return {"error": "Selecciona un archivo con extensión .csv.", "rows": []}
    if not project:
        return {"error": "Selecciona el proyecto de destino antes de cargar el archivo.", "rows": []}
    try:
        text = _decode_upload(contents)
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames
        if not headers:
            return {"error": "El archivo no contiene encabezados.", "rows": []}
        headers = [header.strip() for header in headers]
        missing = [column for column in CSV_COLUMNS if column not in headers]
        extra = [column for column in headers if column not in CSV_COLUMNS]
        if missing or extra or len(headers) != len(CSV_COLUMNS):
            details = []
            if missing:
                details.append("Columnas faltantes: " + ", ".join(missing) + ".")
            if extra:
                details.append("Columnas no esperadas: " + ", ".join(extra) + ".")
            return {"error": "No se puede importar el archivo. " + " ".join(details), "rows": []}

        existing_keys = _existing_keys(existing_rows or [], project)
        seen_keys = set()
        rows = []
        for line_number, raw in enumerate(reader, start=2):
            values = {column: (raw.get(column) or "").strip() for column in CSV_COLUMNS}
            if not any(values.values()):
                continue
            errors = []
            estado = ESTADOS.get(_normalized(values["Estado"]))
            if not estado:
                errors.append("Estado inválido. Usa Abierto, En revisión o Cerrado.")
            fecha_hallazgo, date_error = _parse_date(values["Fecha hallazgo"], required=True)
            if date_error:
                errors.append(date_error)
            fecha_cierre_raw = values["Fecha cierre"]
            fecha_cierre, close_error = _parse_date(
                "" if fecha_cierre_raw in EMPTY_CLOSING_DATES else fecha_cierre_raw, required=False
            )
            if close_error:
                errors.append("Fecha cierre: " + close_error)
            for column in ("Motor", "Script", "Función", "Descripción"):
                if not values[column]:
                    errors.append(f"{column} es obligatorio.")

            key = tuple(_normalized(values[column]) for column in ("Motor", "Script", "Función", "Descripción"))
            duplicate = key in existing_keys or key in seen_keys
            if duplicate and not errors:
                errors.append("Ya existe un hallazgo idéntico en este proyecto.")
            seen_keys.add(key)
            valid = not errors
            rows.append({
                "linea": line_number,
                "Estado": estado or values["Estado"],
                "Fecha hallazgo": fecha_hallazgo,
                "Fecha cierre": fecha_cierre,
                "Motor": values["Motor"],
                "Script": values["Script"],
                "Función": values["Función"],
                "Descripción": values["Descripción"],
                "estado_importacion": "Válido" if valid else "Error",
                "detalle": "Posible duplicado" if duplicate and valid else " ".join(errors),
                "valido": valid,
                "duplicado": duplicate,
            })
        if not rows:
            return {"error": "El archivo no contiene registros para importar.", "rows": []}
        return {"error": None, "rows": rows}
    except (ValueError, binascii.Error, csv.Error) as exc:
        return {"error": str(exc), "rows": []}
