"""
Serialización del DataFrame de actividades hacia/desde dcc.Store, y los
filtros compartidos por todas las páginas. Vive separado de theme.py porque
esto es sobre datos, no sobre diseño — cada página importa de aquí para leer
el store-data global sin duplicar el parseo de fechas.
"""
from __future__ import annotations

import io
import json

import pandas as pd

STORE_COLUMNS = [
    "actividad_id", "fecha_inicio", "fecha_fin", "hora_inicio_txt", "hora_fin_txt",
    "inicio_dt", "fin_dt", "horas",
    "proyecto", "tipo_actividad", "categoria", "actividad", "descripcion",
    "tema", "resultado", "estado", "prioridad", "motor", "observaciones",
    "semana_label", "semana_inicio", "mes_label", "dia_semana", "fecha",
    "proyecto_id", "tipo_actividad_id", "categoria_id",
]

DATE_COLS = ["fecha_inicio", "fecha_fin", "inicio_dt", "fin_dt", "semana_inicio", "fecha"]


def df_to_store(df: pd.DataFrame) -> str:
    trimmed = df.copy()
    trimmed["hora_inicio_txt"] = trimmed["hora_inicio"].apply(lambda t: t.strftime("%H:%M") if pd.notna(t) else None)
    trimmed["hora_fin_txt"] = trimmed["hora_fin"].apply(lambda t: t.strftime("%H:%M") if pd.notna(t) else None)
    trimmed = trimmed[STORE_COLUMNS]
    return trimmed.to_json(orient="records", date_format="iso")


def df_from_store(json_str: str | None) -> pd.DataFrame:
    if not json_str:
        return pd.DataFrame(columns=STORE_COLUMNS)
    df = pd.read_json(io.StringIO(json_str), orient="records")
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def issues_to_store(issues: list[dict]) -> str:
    safe = []
    for it in issues:
        row = {}
        for k, v in it.items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                row[k] = None
            elif isinstance(v, (str, int, float, bool)):
                row[k] = v
            else:
                row[k] = str(v)
        safe.append(row)
    return json.dumps(safe)


def filter_date_range(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    out = df
    if start_date:
        out = out[out["fecha_inicio"] >= pd.to_datetime(start_date)]
    if end_date:
        out = out[out["fecha_inicio"] <= pd.to_datetime(end_date) + pd.Timedelta(hours=23, minutes=59)]
    return out


def apply_all_filters(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    """El único filtro global es el rango de fechas — cada página ya se
    encarga de su propio recorte (Sentinel Alerts, New Opps, Transversales)
    o muestra todo (Resumen, Actividades, Calendario, Análisis)."""
    return filter_date_range(df, start_date, end_date)


# --------------------------------------------------------------------------
# HALLAZGOS (sin fechas, así que no comparte STORE_COLUMNS con actividades)
# --------------------------------------------------------------------------
HALLAZGOS_COLUMNS = ["Proyecto", "Motor", "Script", "Función", "Descripción", "Estado"]


def hallazgos_to_store(df: pd.DataFrame) -> str:
    return df[HALLAZGOS_COLUMNS].to_json(orient="records")


def hallazgos_from_store(json_str: str | None) -> pd.DataFrame:
    if not json_str:
        return pd.DataFrame(columns=HALLAZGOS_COLUMNS)
    return pd.read_json(io.StringIO(json_str), orient="records")


# --------------------------------------------------------------------------
# Catálogos (PROYECTOS / TIPOS_ACTIVIDAD / CATEGORIAS) — para llenar los
# dropdowns del formulario "Nueva actividad" con las opciones reales del
# Excel, en vez de tenerlas hardcodeadas en el código.
# --------------------------------------------------------------------------
def lookups_to_store(proyectos: pd.DataFrame, tipos: pd.DataFrame, categorias: pd.DataFrame) -> str:
    payload = {
        "proyectos": proyectos[["proyecto_id", "proyecto"]].to_dict("records"),
        "tipos": tipos[["tipo_actividad_id", "tipo_actividad"]].to_dict("records"),
        "categorias": categorias[["categoria_id", "categoria"]].to_dict("records"),
    }
    return json.dumps(payload)


def lookups_from_store(json_str: str | None) -> dict:
    if not json_str:
        return {"proyectos": [], "tipos": [], "categorias": []}
    return json.loads(json_str)
