"""
Carga y limpieza de datos de seguimiento.xlsx.

Se lee el Excel completo en cada llamada a load_data(), de modo que nuevas
actividades agregadas por el usuario aparecen en la aplicación sin tocar
código. Toda la limpieza (fechas, textos vacíos, valores de estado/prioridad
mal escritos, etc.) vive aquí para que el resto de la app trabaje siempre
sobre datos ya normalizados.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
from pathlib import Path

import holidays as holidays_lib
import openpyxl
import pandas as pd

# En local, el Excel vive junto a este repo (seguimiento/seguimiento.xlsx).
# En Render, SEGUIMIENTO_EXCEL_PATH apunta a un disco persistente (por
# ejemplo /var/data/seguimiento.xlsx) para que los cierres de hallazgos
# sobrevivan a reinicios y redeploys — el filesystem normal de un Web
# Service de Render es efímero y se borra en cada uno de esos eventos.
_BUNDLED_EXCEL_PATH = Path(__file__).resolve().parent.parent / "seguimiento.xlsx"
_env_excel_path = os.environ.get("SEGUIMIENTO_EXCEL_PATH")
EXCEL_PATH = Path(_env_excel_path) if _env_excel_path else _BUNDLED_EXCEL_PATH

if _env_excel_path and not EXCEL_PATH.exists() and _BUNDLED_EXCEL_PATH.exists():
    # Primer arranque con un disco persistente vacío: lo sembramos con la
    # copia incluida en el repo. En arranques posteriores el disco ya tiene
    # el archivo (con los cierres de hallazgos hechos desde el dashboard),
    # así que esta copia no se vuelve a ejecutar y no pisa esos cambios.
    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_BUNDLED_EXCEL_PATH, EXCEL_PATH)

HALLAZGOS_SHEET = "HALLAZGOS"
HALLAZGOS_COLUMNS = ["Proyecto", "Motor", "Script", "Función", "Descripción", "Estado"]
HALLAZGOS_ESTADOS = ["Abierto", "En revisión", "Cerrado"]

ACTIVIDADES_SHEET = "ACTIVIDADES"
ACTIVIDADES_COLUMNS = [
    "actividad_id", "fecha_inicio", "fecha_fin", "hora_inicio", "hora_fin",
    "proyecto_id", "tipo_actividad_id", "categoria_id", "actividad", "descripcion",
    "tema", "resultado", "estado", "prioridad", "motor", "observaciones",
]

_VACIO_RE = re.compile(r"^\s*\(?\s*vac[ií]o\s*\)?\s*$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")

ESTADOS_VALIDOS = {
    "completado": "Completado",
    "en progreso": "En progreso",
    "bloqueado": "Bloqueado",
    "pendiente": "Pendiente",
}
PRIORIDADES_VALIDAS = {"alta": "Alta", "media": "Media", "baja": "Baja"}

ESTADO_ORDEN = ["Completado", "En progreso", "Bloqueado", "Pendiente", "Sin estado"]
PRIORIDAD_ORDEN = ["Alta", "Media", "Baja", "Sin prioridad"]

# Colores de estado (paleta de estado, fija, nunca reutilizada para series).
COLOR_ESTADO = {
    "Completado": "#0ca30c",
    "En progreso": "#fab219",
    "Bloqueado": "#d03b3b",
    "Pendiente": "#898781",
    "Sin estado": "#c3c2b7",
}

# Colores categóricos (paleta validada, orden fijo) para proyecto.
COLOR_PROYECTO = {
    "Sentinel Alerts": "#2a78d6",
    "New Opps": "#eb6834",
    "Transversal": "#1baf7a",
}


def _clean_text(value) -> str | None:
    """Normaliza celdas de texto: NaN y variantes de "(vacío)" -> None."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or _VACIO_RE.match(text):
        return None
    return _WS_RE.sub(" ", text)


def _fix_date_cell(value):
    """Corrige fechas nativas de Excel con día/mes invertidos.

    Excel (localización en-US) interpreta una fecha tecleada en formato
    dd/mm/aaaa como mm/dd/aaaa cuando el "día" tecleado es <=12, guardando
    internamente el valor con día y mes intercambiados. En este archivo eso
    solo puede ocurrir cuando la celda quedó como fecha nativa (si el día
    tecleado es >12, Excel no logra interpretarla como fecha y la deja como
    texto, que se parsea aparte con dayfirst=True). Por eso el intercambio
    solo se aplica cuando el día resultante es <=12: es la única zona donde
    la ambigüedad pudo producirse.
    """
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, str):
        return pd.to_datetime(value, dayfirst=True, errors="coerce")
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        ts = pd.Timestamp(value)
        if ts.day <= 12:
            return ts.replace(month=ts.day, day=ts.month)
        return ts
    return pd.NaT


def _combine(date_val, time_val):
    if pd.isna(date_val) or pd.isna(time_val):
        return pd.NaT
    return pd.Timestamp.combine(date_val.date(), time_val)


def load_data(path: Path | str | None = None) -> dict:
    """Lee y limpia seguimiento.xlsx. Devuelve un dict con el DataFrame
    principal, los catálogos y la lista de incidencias de calidad de datos
    detectadas durante la limpieza."""
    path = Path(path) if path is not None else EXCEL_PATH

    proyectos = pd.read_excel(path, sheet_name="PROYECTOS")
    tipos = pd.read_excel(path, sheet_name="TIPOS_ACTIVIDAD")
    categorias = pd.read_excel(path, sheet_name="CATEGORIAS")
    df = pd.read_excel(path, sheet_name="ACTIVIDADES", usecols="A:P")

    text_cols = [
        "proyecto_id", "tipo_actividad_id", "categoria_id", "actividad",
        "descripcion", "tema", "resultado", "estado", "prioridad", "motor",
        "observaciones",
    ]
    for col in text_cols:
        df[col] = df[col].map(_clean_text)

    df["fecha_inicio"] = df["fecha_inicio"].map(_fix_date_cell)
    df["fecha_fin"] = df["fecha_fin"].map(_fix_date_cell)

    issues: list[dict] = []

    # --- Corrección de desplazamiento de columnas estado/prioridad/motor ---
    # Patrón detectado: si estado y prioridad no coinciden con ningún valor
    # válido pero el valor de "motor" sí es una prioridad válida, es casi
    # seguro que el usuario escribió "<estado> <prioridad>" corrido una
    # celda a la derecha (p.ej. estado="En", prioridad="progreso",
    # motor="Alta" en vez de estado="En progreso", prioridad="Alta").
    # Nota: se accede con df.at[idx, col] en vez de iterar sobre las Series
    # de iterrows(), porque iterrows() reconstruye cada fila como una única
    # Series y, si la fila mezcla columnas float (p.ej. "horas") con
    # columnas de texto, pandas puede "upcastear" esa fila y convertir los
    # None de texto en NaN silenciosamente.
    for idx in df.index:
        estado_raw = df.at[idx, "estado"]
        prioridad_raw = df.at[idx, "prioridad"]
        motor_raw = df.at[idx, "motor"]
        estado_ok = not pd.isna(estado_raw) and estado_raw.lower() in ESTADOS_VALIDOS
        prioridad_ok = not pd.isna(prioridad_raw) and prioridad_raw.lower() in PRIORIDADES_VALIDAS
        motor_es_prioridad = not pd.isna(motor_raw) and motor_raw.lower() in PRIORIDADES_VALIDAS
        if not estado_ok and not prioridad_ok and motor_es_prioridad:
            estado_part = "" if pd.isna(estado_raw) else estado_raw
            prioridad_part = "" if pd.isna(prioridad_raw) else prioridad_raw
            combined = f"{estado_part} {prioridad_part}".strip().lower()
            fixed_estado = ESTADOS_VALIDOS.get(combined)
            if fixed_estado:
                issues.append({
                    "actividad_id": df.at[idx, "actividad_id"],
                    "campo": "estado / prioridad / motor",
                    "problema": "Valores corridos una columna a la derecha",
                    "valor_original": f"estado={estado_raw!r}, prioridad={prioridad_raw!r}, motor={motor_raw!r}",
                    "valor_corregido": f"estado={fixed_estado!r}, prioridad={PRIORIDADES_VALIDAS[motor_raw.lower()]!r}, motor=(vacío)",
                })
                df.at[idx, "estado"] = fixed_estado
                df.at[idx, "prioridad"] = PRIORIDADES_VALIDAS[motor_raw.lower()]
                df.at[idx, "motor"] = None

    # --- Normalización de estado / prioridad ---
    def _norm_estado(v):
        if pd.isna(v):
            return "Sin estado"
        norm = ESTADOS_VALIDOS.get(v.lower())
        if norm is None:
            issues.append({
                "actividad_id": None, "campo": "estado",
                "problema": "Valor no reconocido, se agrupó como 'Sin estado'",
                "valor_original": v, "valor_corregido": "Sin estado",
            })
            return "Sin estado"
        return norm

    def _norm_prioridad(v):
        if pd.isna(v):
            return "Sin prioridad"
        norm = PRIORIDADES_VALIDAS.get(v.lower())
        if norm is None:
            issues.append({
                "actividad_id": None, "campo": "prioridad",
                "problema": "Valor no reconocido, se agrupó como 'Sin prioridad'",
                "valor_original": v, "valor_corregido": "Sin prioridad",
            })
            return "Sin prioridad"
        return norm

    df["estado"] = df["estado"].map(_norm_estado)
    df["prioridad"] = df["prioridad"].map(_norm_prioridad)

    # --- Fechas/horas faltantes o inconsistentes ---
    for idx in df.index:
        if pd.isna(df.at[idx, "fecha_inicio"]):
            issues.append({
                "actividad_id": df.at[idx, "actividad_id"], "campo": "fecha_inicio",
                "problema": "Fecha de inicio ilegible o vacía", "valor_original": None,
                "valor_corregido": None,
            })

    df["inicio_dt"] = [
        _combine(d, t) for d, t in zip(df["fecha_inicio"], df["hora_inicio"])
    ]
    df["fin_dt"] = [
        _combine(d, t) for d, t in zip(df["fecha_fin"], df["hora_fin"])
    ]
    df["horas"] = (df["fin_dt"] - df["inicio_dt"]).dt.total_seconds() / 3600

    for idx in df.index:
        horas_val = df.at[idx, "horas"]
        if pd.isna(horas_val):
            issues.append({
                "actividad_id": df.at[idx, "actividad_id"], "campo": "horas",
                "problema": "No se pudo calcular la duración (fecha/hora incompleta)",
                "valor_original": None, "valor_corregido": None,
            })
        elif horas_val < 0:
            issues.append({
                "actividad_id": df.at[idx, "actividad_id"], "campo": "horas",
                "problema": "Hora de fin anterior a la hora de inicio",
                "valor_original": horas_val, "valor_corregido": None,
            })

    # --- Catálogos ---
    proy_map = dict(zip(proyectos["proyecto_id"], proyectos["proyecto"]))
    tipo_map = dict(zip(tipos["tipo_actividad_id"], tipos["tipo_actividad"]))
    cat_map = dict(zip(categorias["categoria_id"], categorias["categoria"]))

    df["proyecto"] = df["proyecto_id"].map(proy_map).fillna("Transversal")
    df["tipo_actividad"] = df["tipo_actividad_id"].map(tipo_map).fillna("Sin tipo")
    df["categoria"] = df["categoria_id"].map(cat_map).fillna("Sin categoría")

    for idx in df.index:
        proyecto_id_val = df.at[idx, "proyecto_id"]
        tipo_id_val = df.at[idx, "tipo_actividad_id"]
        categoria_id_val = df.at[idx, "categoria_id"]
        actividad_id_val = df.at[idx, "actividad_id"]
        if not pd.isna(proyecto_id_val) and proyecto_id_val not in proy_map:
            issues.append({
                "actividad_id": actividad_id_val, "campo": "proyecto_id",
                "problema": "proyecto_id no existe en el catálogo PROYECTOS",
                "valor_original": proyecto_id_val, "valor_corregido": None,
            })
        if not pd.isna(tipo_id_val) and tipo_id_val not in tipo_map:
            issues.append({
                "actividad_id": actividad_id_val, "campo": "tipo_actividad_id",
                "problema": "tipo_actividad_id no existe en el catálogo TIPOS_ACTIVIDAD",
                "valor_original": tipo_id_val, "valor_corregido": None,
            })
        if not pd.isna(categoria_id_val) and categoria_id_val not in cat_map:
            issues.append({
                "actividad_id": actividad_id_val, "campo": "categoria_id",
                "problema": "categoria_id no existe en el catálogo CATEGORIAS",
                "valor_original": categoria_id_val, "valor_corregido": None,
            })

    # --- Campos derivados para agregación temporal ---
    df["fecha"] = df["fecha_inicio"].dt.normalize()
    iso = df["fecha_inicio"].dt.isocalendar()
    df["anio_iso"] = iso["year"]
    df["semana_iso"] = iso["week"]
    df["semana_label"] = df["anio_iso"].astype("Int64").astype(str) + "-W" + df["semana_iso"].astype("Int64").astype(str).str.zfill(2)
    df["semana_inicio"] = (df["fecha_inicio"] - pd.to_timedelta(df["fecha_inicio"].dt.weekday, unit="D")).dt.normalize()
    df["mes_label"] = df["fecha_inicio"].dt.strftime("%Y-%m")
    df["dia_semana"] = df["fecha_inicio"].dt.day_name(locale=None)

    df = df.sort_values(["fecha_inicio", "hora_inicio"]).reset_index(drop=True)

    return {
        "actividades": df,
        "proyectos": proyectos,
        "tipos": tipos,
        "categorias": categorias,
        "issues": issues,
    }


def colombia_holidays(year_start: int, year_end: int) -> dict[dt.date, str]:
    """Festivos colombianos entre year_start y year_end (ambos inclusive),
    incluyendo los corrimientos al lunes siguiente de la Ley Emiliani."""
    years = range(year_start, year_end + 1)
    co = holidays_lib.country_holidays("CO", years=years)
    return dict(co.items())


def business_days_worked(start_date: dt.date, end_date: dt.date) -> tuple[int, list[tuple[dt.date, str]]]:
    """Cuenta días hábiles (lunes a viernes, sin festivos colombianos) entre
    start_date y end_date, ambos inclusive.

    Devuelve (n_dias_habiles, festivos_excluidos), donde festivos_excluidos
    es la lista de (fecha, nombre) de los festivos que cayeron en día hábil
    dentro del rango y por eso no se contaron.
    """
    if end_date < start_date:
        return 0, []
    dias_habiles = {d.date() for d in pd.bdate_range(start_date, end_date)}
    festivos = colombia_holidays(start_date.year, end_date.year)
    festivos_en_rango = sorted(d for d in festivos if d in dias_habiles)
    n_dias = len(dias_habiles) - len(festivos_en_rango)
    return n_dias, [(d, festivos[d]) for d in festivos_en_rango]


def load_hallazgos(path: Path | str | None = None) -> pd.DataFrame:
    """Lee la pestaña HALLAZGOS tal cual está en el Excel — sin inventar,
    corregir ni reclasificar nada; solo recorta espacios en blanco accidentales
    para que los filtros por valor exacto (Motor, Estado, etc.) funcionen bien."""
    path = path if path is not None else EXCEL_PATH
    df = pd.read_excel(path, sheet_name=HALLAZGOS_SHEET, usecols=HALLAZGOS_COLUMNS)
    for col in HALLAZGOS_COLUMNS:
        df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
    return df.reset_index(drop=True)


def close_hallazgo(proyecto: str, motor: str, script: str, funcion: str, descripcion: str,
                    estado_actual: str, path: Path | str | None = None) -> tuple[bool, str]:
    """Cambia el Estado de un hallazgo a 'Cerrado' directamente en el Excel.

    El registro se identifica por la combinación completa Proyecto+Motor+
    Script+Función+Descripción (nunca solo por Motor, que puede repetirse).
    Antes de escribir se verifica que el Estado en el archivo siga siendo el
    mismo que el usuario vio en el dashboard, para no pisar un cambio hecho
    por otra persona mientras tanto. Nunca borra la fila ni toca otras
    columnas u otras pestañas.
    """
    path = path if path is not None else EXCEL_PATH
    try:
        wb = openpyxl.load_workbook(path)
    except PermissionError:
        return False, ("No fue posible actualizar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    except FileNotFoundError:
        return False, "No se encontró el archivo seguimiento.xlsx."

    if HALLAZGOS_SHEET not in wb.sheetnames:
        return False, "No se encontró la pestaña HALLAZGOS en el archivo."

    ws = wb[HALLAZGOS_SHEET]
    headers = [cell.value for cell in ws[1]]
    try:
        col_idx = {name: headers.index(name) + 1 for name in HALLAZGOS_COLUMNS}
    except ValueError:
        return False, "La estructura de columnas de HALLAZGOS cambió y no se pudo actualizar de forma segura."

    def _norm(v) -> str:
        return "" if v is None else str(v).strip()

    objetivo = (_norm(proyecto), _norm(motor), _norm(script), _norm(funcion), _norm(descripcion))
    filas_encontradas = []
    for r in range(2, ws.max_row + 1):
        clave = tuple(_norm(ws.cell(row=r, column=col_idx[c]).value)
                       for c in ["Proyecto", "Motor", "Script", "Función", "Descripción"])
        if clave == objetivo:
            filas_encontradas.append(r)

    if not filas_encontradas:
        return False, "No se encontró el hallazgo seleccionado en el archivo (los datos pudieron cambiar)."
    if len(filas_encontradas) > 1:
        return False, ("Existe más de un hallazgo idéntico en el archivo; no es posible identificar "
                        "cuál cerrar de forma segura. Revisa el Excel manualmente.")

    fila = filas_encontradas[0]
    estado_cell = ws.cell(row=fila, column=col_idx["Estado"])
    if _norm(estado_cell.value) != _norm(estado_actual):
        return False, ("El estado de este hallazgo cambió desde que se cargó la página. "
                        "Actualiza los datos e inténtalo de nuevo.")

    estado_cell.value = "Cerrado"
    try:
        wb.save(path)
    except PermissionError:
        return False, ("No fue posible actualizar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    return True, "Hallazgo cerrado correctamente."


def add_hallazgo(proyecto: str, motor: str, script: str, funcion: str, descripcion: str,
                  estado: str, path: Path | str | None = None) -> tuple[bool, str]:
    """Agrega una fila nueva al final de HALLAZGOS. Rechaza el alta si ya
    existe un hallazgo idéntico (misma combinación Proyecto+Motor+Script+
    Función+Descripción), porque close_hallazgo() identifica los registros
    por esa combinación y dos filas iguales lo volverían ambiguo."""
    path = path if path is not None else EXCEL_PATH

    def _norm(v) -> str:
        return "" if v is None else str(v).strip()

    try:
        wb = openpyxl.load_workbook(path)
    except PermissionError:
        return False, ("No fue posible agregar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    except FileNotFoundError:
        return False, "No se encontró el archivo seguimiento.xlsx."

    if HALLAZGOS_SHEET not in wb.sheetnames:
        return False, "No se encontró la pestaña HALLAZGOS en el archivo."

    ws = wb[HALLAZGOS_SHEET]
    headers = [cell.value for cell in ws[1]]
    try:
        col_idx = {name: headers.index(name) + 1 for name in HALLAZGOS_COLUMNS}
    except ValueError:
        return False, "La estructura de columnas de HALLAZGOS cambió y no se pudo actualizar de forma segura."

    objetivo = (_norm(proyecto), _norm(motor), _norm(script), _norm(funcion), _norm(descripcion))
    for r in range(2, ws.max_row + 1):
        clave = tuple(_norm(ws.cell(row=r, column=col_idx[c]).value)
                       for c in ["Proyecto", "Motor", "Script", "Función", "Descripción"])
        if clave == objetivo:
            return False, "Ya existe un hallazgo idéntico (mismo proyecto, motor, script, función y descripción)."

    fila = ws.max_row + 1
    valores = {"Proyecto": proyecto, "Motor": motor, "Script": script, "Función": funcion,
               "Descripción": descripcion, "Estado": estado}
    for nombre, valor in valores.items():
        ws.cell(row=fila, column=col_idx[nombre]).value = valor

    try:
        wb.save(path)
    except PermissionError:
        return False, ("No fue posible agregar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    return True, "Hallazgo agregado correctamente."


def edit_hallazgo(proyecto: str, motor: str, script: str, funcion: str, descripcion: str, estado_actual: str,
                   nuevo_proyecto: str, nuevo_motor: str, nuevo_script: str, nuevo_funcion: str,
                   nueva_descripcion: str, nuevo_estado: str,
                   path: Path | str | None = None) -> tuple[bool, str]:
    """Modifica un hallazgo existente (cualquier columna). El registro original
    se identifica por la combinación completa Proyecto+Motor+Script+Función+
    Descripción+Estado tal como estaba cuando se cargó el dashboard, para no
    pisar un cambio hecho por otra persona mientras tanto. Si la nueva
    combinación Proyecto+Motor+Script+Función+Descripción coincide con la de
    otro hallazgo existente, se rechaza para no crear una ambigüedad que
    después impida cerrar/editar/borrar cualquiera de los dos."""
    path = path if path is not None else EXCEL_PATH

    def _norm(v) -> str:
        return "" if v is None else str(v).strip()

    try:
        wb = openpyxl.load_workbook(path)
    except PermissionError:
        return False, ("No fue posible actualizar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    except FileNotFoundError:
        return False, "No se encontró el archivo seguimiento.xlsx."

    if HALLAZGOS_SHEET not in wb.sheetnames:
        return False, "No se encontró la pestaña HALLAZGOS en el archivo."

    ws = wb[HALLAZGOS_SHEET]
    headers = [cell.value for cell in ws[1]]
    try:
        col_idx = {name: headers.index(name) + 1 for name in HALLAZGOS_COLUMNS}
    except ValueError:
        return False, "La estructura de columnas de HALLAZGOS cambió y no se pudo actualizar de forma segura."

    objetivo = (_norm(proyecto), _norm(motor), _norm(script), _norm(funcion), _norm(descripcion))
    nuevo_key = (_norm(nuevo_proyecto), _norm(nuevo_motor), _norm(nuevo_script),
                 _norm(nuevo_funcion), _norm(nueva_descripcion))

    filas_encontradas = []
    filas_conflicto = []
    for r in range(2, ws.max_row + 1):
        clave = tuple(_norm(ws.cell(row=r, column=col_idx[c]).value)
                       for c in ["Proyecto", "Motor", "Script", "Función", "Descripción"])
        if clave == objetivo:
            filas_encontradas.append(r)
        elif clave == nuevo_key:
            filas_conflicto.append(r)

    if not filas_encontradas:
        return False, "No se encontró el hallazgo seleccionado en el archivo (los datos pudieron cambiar)."
    if len(filas_encontradas) > 1:
        return False, ("Existe más de un hallazgo idéntico en el archivo; no es posible identificar "
                        "cuál editar de forma segura. Revisa el Excel manualmente.")
    if filas_conflicto:
        return False, "Ya existe otro hallazgo con esa misma combinación de proyecto, motor, script, función y descripción."

    fila = filas_encontradas[0]
    estado_cell = ws.cell(row=fila, column=col_idx["Estado"])
    if _norm(estado_cell.value) != _norm(estado_actual):
        return False, ("Este hallazgo cambió desde que se cargó la página. Actualiza los datos e inténtalo de nuevo.")

    valores = {"Proyecto": nuevo_proyecto, "Motor": nuevo_motor, "Script": nuevo_script,
               "Función": nuevo_funcion, "Descripción": nueva_descripcion, "Estado": nuevo_estado}
    for nombre, valor in valores.items():
        ws.cell(row=fila, column=col_idx[nombre]).value = valor

    try:
        wb.save(path)
    except PermissionError:
        return False, ("No fue posible actualizar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    return True, "Hallazgo actualizado correctamente."


def delete_hallazgo(proyecto: str, motor: str, script: str, funcion: str, descripcion: str,
                     estado_actual: str, path: Path | str | None = None) -> tuple[bool, str]:
    """Elimina permanentemente la fila de un hallazgo en HALLAZGOS. Se
    identifica por la combinación completa Proyecto+Motor+Script+Función+
    Descripción+Estado vista en el dashboard, igual que close_hallazgo, para
    evitar borrar la fila equivocada o una fila que cambió mientras tanto.
    Esta acción no se puede deshacer desde la aplicación."""
    path = path if path is not None else EXCEL_PATH

    def _norm(v) -> str:
        return "" if v is None else str(v).strip()

    try:
        wb = openpyxl.load_workbook(path)
    except PermissionError:
        return False, ("No fue posible eliminar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    except FileNotFoundError:
        return False, "No se encontró el archivo seguimiento.xlsx."

    if HALLAZGOS_SHEET not in wb.sheetnames:
        return False, "No se encontró la pestaña HALLAZGOS en el archivo."

    ws = wb[HALLAZGOS_SHEET]
    headers = [cell.value for cell in ws[1]]
    try:
        col_idx = {name: headers.index(name) + 1 for name in HALLAZGOS_COLUMNS}
    except ValueError:
        return False, "La estructura de columnas de HALLAZGOS cambió y no se pudo actualizar de forma segura."

    objetivo = (_norm(proyecto), _norm(motor), _norm(script), _norm(funcion), _norm(descripcion))
    filas_encontradas = []
    for r in range(2, ws.max_row + 1):
        clave = tuple(_norm(ws.cell(row=r, column=col_idx[c]).value)
                       for c in ["Proyecto", "Motor", "Script", "Función", "Descripción"])
        if clave == objetivo:
            filas_encontradas.append(r)

    if not filas_encontradas:
        return False, "No se encontró el hallazgo seleccionado en el archivo (los datos pudieron cambiar)."
    if len(filas_encontradas) > 1:
        return False, ("Existe más de un hallazgo idéntico en el archivo; no es posible identificar "
                        "cuál eliminar de forma segura. Revisa el Excel manualmente.")

    fila = filas_encontradas[0]
    estado_cell = ws.cell(row=fila, column=col_idx["Estado"])
    if _norm(estado_cell.value) != _norm(estado_actual):
        return False, ("Este hallazgo cambió desde que se cargó la página. Actualiza los datos e inténtalo de nuevo.")

    ws.delete_rows(fila, 1)

    try:
        wb.save(path)
    except PermissionError:
        return False, ("No fue posible eliminar el hallazgo. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    return True, "Hallazgo eliminado correctamente."


def next_actividad_id(path: Path | str | None = None) -> str:
    """Siguiente ID secuencial tipo 'A035' a partir del mayor existente."""
    path = path if path is not None else EXCEL_PATH
    ids = pd.read_excel(path, sheet_name=ACTIVIDADES_SHEET, usecols="A")["actividad_id"].dropna().astype(str)
    nums = [int(m.group()) for i in ids if (m := re.search(r"\d+", i))]
    return f"A{(max(nums) + 1) if nums else 1:03d}"


def add_actividad(fecha_inicio: dt.date, hora_inicio: dt.time, hora_fin: dt.time,
                   proyecto_id: str | None, tipo_actividad_id: str, categoria_id: str | None,
                   actividad: str, descripcion: str, tema: str, resultado: str,
                   estado: str, prioridad: str, motor: str | None = None,
                   observaciones: str | None = None, fecha_fin: dt.date | None = None,
                   path: Path | str | None = None) -> tuple[bool, str]:
    """Agrega una fila nueva al final de ACTIVIDADES. No modifica ni borra
    ninguna fila existente. fecha_fin, si no se da, se asume igual a
    fecha_inicio (así están prácticamente todas las actividades existentes:
    son de un solo día)."""
    path = path if path is not None else EXCEL_PATH
    fecha_fin = fecha_fin or fecha_inicio

    try:
        wb = openpyxl.load_workbook(path)
    except PermissionError:
        return False, ("No fue posible agregar la actividad. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    except FileNotFoundError:
        return False, "No se encontró el archivo seguimiento.xlsx."

    if ACTIVIDADES_SHEET not in wb.sheetnames:
        return False, "No se encontró la pestaña ACTIVIDADES en el archivo."

    ws = wb[ACTIVIDADES_SHEET]
    headers = [cell.value for cell in ws[1]]
    try:
        col_idx = {name: headers.index(name) + 1 for name in ACTIVIDADES_COLUMNS}
    except ValueError:
        return False, "La estructura de columnas de ACTIVIDADES cambió y no se pudo actualizar de forma segura."

    ids_existentes = [str(ws.cell(row=r, column=col_idx["actividad_id"]).value or "")
                       for r in range(2, ws.max_row + 1)]
    nums = [int(m.group()) for i in ids_existentes if (m := re.search(r"\d+", i))]
    new_id = f"A{(max(nums) + 1) if nums else 1:03d}"

    fila = ws.max_row + 1
    valores = {
        "actividad_id": new_id, "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
        "hora_inicio": hora_inicio, "hora_fin": hora_fin,
        "proyecto_id": proyecto_id or None, "tipo_actividad_id": tipo_actividad_id,
        "categoria_id": categoria_id or None, "actividad": actividad, "descripcion": descripcion,
        "tema": tema, "resultado": resultado, "estado": estado, "prioridad": prioridad,
        "motor": motor or None, "observaciones": observaciones or None,
    }
    for nombre, valor in valores.items():
        celda = ws.cell(row=fila, column=col_idx[nombre])
        celda.value = valor
        if nombre in ("fecha_inicio", "fecha_fin"):
            celda.number_format = "DD/MM/YYYY"
        elif nombre in ("hora_inicio", "hora_fin"):
            celda.number_format = "HH:MM"

    try:
        wb.save(path)
    except PermissionError:
        return False, ("No fue posible agregar la actividad. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    return True, f"Actividad {new_id} agregada correctamente."


def update_actividad(actividad_id: str, fecha_inicio: dt.date, hora_inicio: dt.time, hora_fin: dt.time,
                      proyecto_id: str | None, tipo_actividad_id: str, categoria_id: str | None,
                      actividad: str, descripcion: str, tema: str, resultado: str,
                      estado: str, prioridad: str, motor: str | None = None,
                      observaciones: str | None = None, fecha_fin: dt.date | None = None,
                      path: Path | str | None = None) -> tuple[bool, str]:
    """Sobrescribe los campos editables de una actividad existente,
    identificada por su actividad_id (único, nunca cambia). No borra la fila
    ni afecta otras actividades."""
    path = path if path is not None else EXCEL_PATH
    fecha_fin = fecha_fin or fecha_inicio

    try:
        wb = openpyxl.load_workbook(path)
    except PermissionError:
        return False, ("No fue posible actualizar la actividad. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    except FileNotFoundError:
        return False, "No se encontró el archivo seguimiento.xlsx."

    if ACTIVIDADES_SHEET not in wb.sheetnames:
        return False, "No se encontró la pestaña ACTIVIDADES en el archivo."

    ws = wb[ACTIVIDADES_SHEET]
    headers = [cell.value for cell in ws[1]]
    try:
        col_idx = {name: headers.index(name) + 1 for name in ACTIVIDADES_COLUMNS}
    except ValueError:
        return False, "La estructura de columnas de ACTIVIDADES cambió y no se pudo actualizar de forma segura."

    filas_encontradas = [r for r in range(2, ws.max_row + 1)
                          if str(ws.cell(row=r, column=col_idx["actividad_id"]).value or "") == str(actividad_id)]
    if not filas_encontradas:
        return False, "No se encontró la actividad seleccionada en el archivo (los datos pudieron cambiar)."
    if len(filas_encontradas) > 1:
        return False, "Existe más de una fila con el mismo ID; no es posible actualizar de forma segura."

    fila = filas_encontradas[0]
    valores = {
        "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
        "hora_inicio": hora_inicio, "hora_fin": hora_fin,
        "proyecto_id": proyecto_id or None, "tipo_actividad_id": tipo_actividad_id,
        "categoria_id": categoria_id or None, "actividad": actividad, "descripcion": descripcion,
        "tema": tema, "resultado": resultado, "estado": estado, "prioridad": prioridad,
        "motor": motor or None, "observaciones": observaciones or None,
    }
    for nombre, valor in valores.items():
        celda = ws.cell(row=fila, column=col_idx[nombre])
        celda.value = valor
        if nombre in ("fecha_inicio", "fecha_fin"):
            celda.number_format = "DD/MM/YYYY"
        elif nombre in ("hora_inicio", "hora_fin"):
            celda.number_format = "HH:MM"

    try:
        wb.save(path)
    except PermissionError:
        return False, ("No fue posible actualizar la actividad. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    return True, f"Actividad {actividad_id} actualizada correctamente."


def delete_actividad(actividad_id: str, path: Path | str | None = None) -> tuple[bool, str]:
    """Elimina permanentemente la fila de una actividad en ACTIVIDADES,
    identificada por su actividad_id. Esta acción no se puede deshacer desde
    la aplicación."""
    path = path if path is not None else EXCEL_PATH

    try:
        wb = openpyxl.load_workbook(path)
    except PermissionError:
        return False, ("No fue posible eliminar la actividad. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    except FileNotFoundError:
        return False, "No se encontró el archivo seguimiento.xlsx."

    if ACTIVIDADES_SHEET not in wb.sheetnames:
        return False, "No se encontró la pestaña ACTIVIDADES en el archivo."

    ws = wb[ACTIVIDADES_SHEET]
    headers = [cell.value for cell in ws[1]]
    try:
        col_idx = {name: headers.index(name) + 1 for name in ACTIVIDADES_COLUMNS}
    except ValueError:
        return False, "La estructura de columnas de ACTIVIDADES cambió y no se pudo actualizar de forma segura."

    filas_encontradas = [r for r in range(2, ws.max_row + 1)
                          if str(ws.cell(row=r, column=col_idx["actividad_id"]).value or "") == str(actividad_id)]
    if not filas_encontradas:
        return False, "No se encontró la actividad seleccionada en el archivo (los datos pudieron cambiar)."
    if len(filas_encontradas) > 1:
        return False, "Existe más de una fila con el mismo ID; no es posible eliminar de forma segura."

    ws.delete_rows(filas_encontradas[0], 1)

    try:
        wb.save(path)
    except PermissionError:
        return False, ("No fue posible eliminar la actividad. Verifique que el archivo Excel "
                        "no esté abierto o bloqueado por otro usuario.")
    return True, f"Actividad {actividad_id} eliminada correctamente."
