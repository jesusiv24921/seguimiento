"""
Asistente IA de Seguimiento — capa delgada sobre la Responses API de OpenAI.

Solo se importa/ejecuta desde callbacks server-side de Dash. OPENAI_API_KEY
nunca se envía al cliente, nunca se guarda en el Excel ni en un dcc.Store.

Las "tools" que el modelo puede invocar son envoltorios delgados sobre
funciones que ya existen en data.py/knowledge.py — el asistente consulta datos
reales del Excel, nunca inventa cifras ni hechos.

El historial de conversaciones se guarda como un archivo JSON por
conversación en conversaciones/ (mismo disco donde vive seguimiento.xlsx) —
no se introduce ninguna base de datos nueva para esto.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

from openai import OpenAI

import data as data_mod
import knowledge as knowledge_mod

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# gpt-5.6-luna: variante económica de la familia GPT-5.6 (verificado ago-2026
# en la documentación oficial de OpenAI). Cambiar aquí solo el valor por
# defecto — el usuario puede sobreescribirlo con la variable de entorno
# OPENAI_MODEL sin tocar código.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
MAX_TOOL_TURNS = 6
_REQUEST_TIMEOUT = 30.0

CONVERSACIONES_DIR = data_mod.EXCEL_PATH.parent / "conversaciones"

SYSTEM_PROMPT = (
    "Eres el asistente personal dentro de Seguimiento, la aplicación de "
    "seguimiento de trabajo, proyectos y conocimiento de este usuario. "
    "Seguimiento es un proyecto independiente que el usuario construyó para "
    "su propio uso — no confundirlo con 'Sentinel', que es solo uno de los "
    "proyectos de trabajo que él registra dentro de Seguimiento. "
    "Usa siempre las herramientas disponibles para consultar datos reales "
    "(horas, pendientes, bloqueos, actividades, entradas de conocimiento) en "
    "vez de inventar cifras o hechos. Si no tienes una herramienta para algo, "
    "dilo explícitamente en vez de adivinar. Responde en español, de forma "
    "clara y concisa. Cuando el usuario pida un mapa conceptual, respóndelo "
    "como un bloque de código ```mermaid ... ``` con sintaxis válida de "
    "Mermaid (graph TD u otra), sin explicaciones adicionales dentro del bloque."
)


def is_configured() -> bool:
    return bool(OPENAI_API_KEY)


# --------------------------------------------------------------------------
# Herramientas (function calling) — envoltorios sobre data.py / knowledge.py
# --------------------------------------------------------------------------
def _tool_get_projects(**_kwargs) -> dict:
    df = data_mod.load_data()["proyectos"]
    return {"proyectos": df["proyecto"].dropna().tolist()}


def _tool_get_activities(proyecto: str | None = None, dias: int | None = None, **_kwargs) -> dict:
    df = data_mod.load_data()["actividades"]
    if proyecto:
        df = df[df["proyecto"] == proyecto]
    if dias:
        limite = dt.date.today() - dt.timedelta(days=int(dias))
        df = df[df["fecha_inicio"].dt.date >= limite]
    df = df.sort_values("fecha_inicio", ascending=False).head(30)
    registros = df[["actividad_id", "fecha_inicio", "proyecto", "actividad", "estado", "horas"]].copy()
    registros["fecha_inicio"] = registros["fecha_inicio"].dt.strftime("%Y-%m-%d")
    return {"actividades": registros.to_dict("records")}


def _tool_get_hours_by_project(proyecto: str | None = None, dias: int | None = None, **_kwargs) -> dict:
    df = data_mod.load_data()["actividades"]
    if proyecto:
        df = df[df["proyecto"] == proyecto]
    if dias:
        limite = dt.date.today() - dt.timedelta(days=int(dias))
        df = df[df["fecha_inicio"].dt.date >= limite]
    resumen = df.groupby("proyecto")["horas"].sum().round(1).to_dict()
    return {"horas_por_proyecto": resumen, "total_actividades": int(len(df))}


def _tool_get_pending_tasks(proyecto: str | None = None, **_kwargs) -> dict:
    df = data_mod.load_data()["actividades"]
    df = df[df["estado"] == "Pendiente"]
    if proyecto:
        df = df[df["proyecto"] == proyecto]
    registros = df[["actividad_id", "actividad", "proyecto", "fecha_inicio", "prioridad"]].copy()
    registros["fecha_inicio"] = registros["fecha_inicio"].dt.strftime("%Y-%m-%d")
    return {"pendientes": registros.to_dict("records")}


def _tool_get_blockers(proyecto: str | None = None, **_kwargs) -> dict:
    df = data_mod.load_data()["actividades"]
    df = df[df["estado"] == "Bloqueado"]
    if proyecto:
        df = df[df["proyecto"] == proyecto]
    registros = df[["actividad_id", "actividad", "proyecto", "resultado", "fecha_inicio"]].copy()
    registros["fecha_inicio"] = registros["fecha_inicio"].dt.strftime("%Y-%m-%d")
    return {"bloqueos": registros.to_dict("records")}


def _tool_search_knowledge(query: str | None = None, categoria: str | None = None,
                            proyecto: str | None = None, etiqueta: str | None = None,
                            **_kwargs) -> dict:
    df = knowledge_mod.search_knowledge(query=query, categoria=categoria, proyecto=proyecto, etiqueta=etiqueta)
    if df.empty:
        return {"resultados": []}
    cols = ["conocimiento_id", "titulo", "descripcion_breve", "categoria", "estado", "ambito", "proyectos", "etiquetas"]
    return {"resultados": df[cols].to_dict("records")}


def _tool_get_knowledge(conocimiento_id: str, **_kwargs) -> dict:
    df = knowledge_mod.load_knowledge()
    fila = df[df["conocimiento_id"] == conocimiento_id]
    if fila.empty:
        return {"error": "No se encontró esa entrada de conocimiento."}
    registro = fila.iloc[0].to_dict()
    for k, v in registro.items():
        if hasattr(v, "isoformat"):
            registro[k] = v.isoformat()
    return registro


TOOLS = [
    {"type": "function", "name": "get_projects",
     "description": "Obtiene la lista de proyectos reales registrados en Seguimiento.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"type": "function", "name": "get_activities",
     "description": "Obtiene actividades recientes, opcionalmente filtradas por proyecto y por los últimos N días.",
     "parameters": {"type": "object", "properties": {
         "proyecto": {"type": "string", "description": "Nombre exacto del proyecto (opcional)."},
         "dias": {"type": "integer", "description": "Solo actividades de los últimos N días (opcional)."},
     }, "required": []}},
    {"type": "function", "name": "get_hours_by_project",
     "description": "Obtiene las horas totales dedicadas por proyecto, opcionalmente filtradas por proyecto y por los últimos N días.",
     "parameters": {"type": "object", "properties": {
         "proyecto": {"type": "string", "description": "Nombre exacto del proyecto (opcional)."},
         "dias": {"type": "integer", "description": "Solo actividades de los últimos N días (opcional)."},
     }, "required": []}},
    {"type": "function", "name": "get_pending_tasks",
     "description": "Obtiene las tareas pendientes (estado Pendiente), opcionalmente filtradas por proyecto.",
     "parameters": {"type": "object", "properties": {
         "proyecto": {"type": "string", "description": "Nombre exacto del proyecto (opcional)."},
     }, "required": []}},
    {"type": "function", "name": "get_blockers",
     "description": "Obtiene los bloqueos activos (estado Bloqueado), opcionalmente filtrados por proyecto.",
     "parameters": {"type": "object", "properties": {
         "proyecto": {"type": "string", "description": "Nombre exacto del proyecto (opcional)."},
     }, "required": []}},
    {"type": "function", "name": "search_knowledge",
     "description": "Busca entradas del Centro de Conocimiento por texto y/o filtros (categoría, proyecto, etiqueta).",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Texto a buscar en título/descripción/contenido/etiquetas."},
         "categoria": {"type": "string", "description": "Estudio, Soluciones, Errores y aprendizajes, Conceptos, Procedimientos, Ideas, Referencias o Notas."},
         "proyecto": {"type": "string", "description": "Nombre del proyecto relacionado."},
         "etiqueta": {"type": "string", "description": "Una etiqueta."},
     }, "required": []}},
    {"type": "function", "name": "get_knowledge",
     "description": "Obtiene el contenido completo de una entrada de conocimiento por su ID (ej. K003).",
     "parameters": {"type": "object", "properties": {
         "conocimiento_id": {"type": "string", "description": "ID de la entrada, ej. K003."},
     }, "required": ["conocimiento_id"]}},
]

TOOL_FUNCTIONS = {
    "get_projects": _tool_get_projects,
    "get_activities": _tool_get_activities,
    "get_hours_by_project": _tool_get_hours_by_project,
    "get_pending_tasks": _tool_get_pending_tasks,
    "get_blockers": _tool_get_blockers,
    "search_knowledge": _tool_search_knowledge,
    "get_knowledge": _tool_get_knowledge,
}


# --------------------------------------------------------------------------
# Historial de conversaciones (JSON en disco, un archivo por conversación)
# --------------------------------------------------------------------------
def _ensure_conversaciones_dir() -> None:
    CONVERSACIONES_DIR.mkdir(parents=True, exist_ok=True)


def _conversacion_path(conversacion_id: str) -> Path:
    safe_id = re.sub(r"[^\w-]", "_", conversacion_id)
    return CONVERSACIONES_DIR / f"{safe_id}.json"


def _cargar_conversacion(conversacion_id: str) -> dict:
    path = _conversacion_path(conversacion_id)
    if not path.exists():
        return {"conversacion_id": conversacion_id, "titulo": None,
                "fecha_creacion": None, "mensajes": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"conversacion_id": conversacion_id, "titulo": None,
                "fecha_creacion": None, "mensajes": []}


def _guardar_conversacion(conversacion_id: str, historial: dict) -> None:
    _ensure_conversaciones_dir()
    path = _conversacion_path(conversacion_id)
    path.write_text(json.dumps(historial, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def nueva_conversacion_id() -> str:
    return dt.datetime.now().strftime("C%Y%m%d%H%M%S")


def listar_conversaciones() -> list[dict]:
    """Metadatos de todas las conversaciones guardadas, más recientes primero."""
    _ensure_conversaciones_dir()
    resultado = []
    for path in CONVERSACIONES_DIR.glob("*.json"):
        try:
            data_conv = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        mensajes = data_conv.get("mensajes", [])
        titulo = data_conv.get("titulo") or (
            mensajes[0]["contenido"][:60] if mensajes else "Conversación vacía")
        resultado.append({
            "conversacion_id": data_conv.get("conversacion_id", path.stem),
            "titulo": titulo,
            "fecha_creacion": data_conv.get("fecha_creacion") or "",
            "n_mensajes": len(mensajes),
        })
    resultado.sort(key=lambda r: r["fecha_creacion"], reverse=True)
    return resultado


def obtener_conversacion(conversacion_id: str) -> dict:
    return _cargar_conversacion(conversacion_id)


# --------------------------------------------------------------------------
# Envío de mensajes (bucle de tool-calling sobre la Responses API)
# --------------------------------------------------------------------------
def enviar_mensaje(conversacion_id: str, mensaje_usuario: str,
                    contexto_extra: str | None = None) -> tuple[bool, str]:
    """Envía un mensaje del usuario, resuelve las herramientas que el modelo
    pida, guarda ambos mensajes en el JSON de la conversación, y devuelve
    (ok, texto_de_respuesta_o_error). contexto_extra es para prompts armados
    desde una entrada de conocimiento (ej. "Explícame esto: <contenido>")."""
    if not is_configured():
        return False, ("El asistente no está activado todavía: falta configurar "
                        "OPENAI_API_KEY en las variables de entorno.")

    historial = _cargar_conversacion(conversacion_id)
    mensajes_previos = historial.get("mensajes", [])

    input_items: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in mensajes_previos[-20:]:
        input_items.append({"role": m["rol"], "content": m["contenido"]})
    contenido_usuario = f"{mensaje_usuario}\n\n{contexto_extra}" if contexto_extra else mensaje_usuario
    input_items.append({"role": "user", "content": contenido_usuario})

    client = OpenAI(api_key=OPENAI_API_KEY, timeout=_REQUEST_TIMEOUT)

    texto = None
    try:
        for _ in range(MAX_TOOL_TURNS):
            response = client.responses.create(model=OPENAI_MODEL, input=input_items, tools=TOOLS)
            input_items += [item.model_dump() for item in response.output]
            llamadas = [item for item in response.output if item.type == "function_call"]
            if not llamadas:
                texto = response.output_text
                break
            for llamada in llamadas:
                fn = TOOL_FUNCTIONS.get(llamada.name)
                try:
                    args = json.loads(llamada.arguments or "{}")
                    resultado = fn(**args) if fn else {"error": f"Herramienta desconocida: {llamada.name}"}
                except Exception as exc:  # nunca dejar caer el bucle por un error de una tool
                    resultado = {"error": str(exc)}
                input_items.append({
                    "type": "function_call_output",
                    "call_id": llamada.call_id,
                    "output": json.dumps(resultado, ensure_ascii=False, default=str),
                })
        if texto is None:
            return False, "El asistente no pudo completar la respuesta (demasiadas herramientas encadenadas)."
    except Exception as exc:
        return False, f"No fue posible conectar con OpenAI: {exc}"

    ahora = dt.datetime.now().isoformat()
    mensajes_previos.append({"rol": "user", "contenido": mensaje_usuario, "fecha_hora": ahora})
    mensajes_previos.append({"rol": "assistant", "contenido": texto, "fecha_hora": ahora})
    historial["mensajes"] = mensajes_previos
    if not historial.get("titulo"):
        historial["titulo"] = mensaje_usuario[:60]
    if not historial.get("fecha_creacion"):
        historial["fecha_creacion"] = ahora
    historial["conversacion_id"] = conversacion_id
    _guardar_conversacion(conversacion_id, historial)

    return True, texto
