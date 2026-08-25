"""
Asistente IA de Seguimiento — capa delgada sobre la Responses API de OpenAI,
con un router determinístico que responde localmente siempre que sea posible.

Solo se importa/ejecuta desde callbacks server-side de Dash. OPENAI_API_KEY
nunca se envía al cliente, nunca se guarda en el Excel ni en un dcc.Store.

Principio de diseño (pedido explícito del usuario): "consultar primero los
datos y conocimientos locales de Seguimiento; usar OpenAI únicamente cuando
aporte valor real". Por eso enviar_mensaje() intenta responder con
_clasificar_consulta() (regex/keywords, sin IA, cero costo) ANTES de
considerar siquiera llamar a OpenAI. El router nunca usa IA para decidir si
debe usar IA — es lógica determinística pura.

El historial de conversaciones se guarda como un archivo JSON por
conversación en conversaciones/ (mismo disco donde vive seguimiento.xlsx).
El consumo de IA se registra en ai_usage.jsonl (log de solo-anexar, una
línea por evento — evita reabrir/regrabar el Excel completo en cada mensaje).
La caché de respuestas de IA vive en cache_ia.json. Ninguno de los tres
introduce una base de datos nueva: son archivos en el mismo disco.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from openai import OpenAI

import data as data_mod
import knowledge as knowledge_mod

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# gpt-5.6-luna: variante económica de la familia GPT-5.6 (verificado ago-2026
# en la documentación oficial de OpenAI) — modelo por defecto para tareas
# simples (explicar/resumir/ejercicios). gpt-5.6-terra: variante intermedia,
# solo para consultas que el router detecte como análisis complejo. Ninguno
# de los dos queda fijo en el código: ambos son sobreescribibles por
# variable de entorno sin tocar nada.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
OPENAI_REASONING_MODEL = os.environ.get("OPENAI_REASONING_MODEL", "gpt-5.6-terra")
MAX_TOOL_TURNS = 6
_REQUEST_TIMEOUT = 30.0

AI_MAX_OUTPUT_TOKENS = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "800"))
AI_MONTHLY_BUDGET_USD = float(os.environ.get("AI_MONTHLY_BUDGET_USD", "5.0"))
AI_DAILY_REQUEST_LIMIT = int(os.environ.get("AI_DAILY_REQUEST_LIMIT", "50"))

CONVERSACIONES_DIR = data_mod.EXCEL_PATH.parent / "conversaciones"
USAGE_LOG_PATH = data_mod.EXCEL_PATH.parent / "ai_usage.jsonl"
CACHE_PATH = data_mod.EXCEL_PATH.parent / "cache_ia.json"

# Precios oficiales por 1M de tokens, verificados ago-2026. Sobreescribibles
# sin tocar código vía AI_PRICING_CONFIG_JSON (los precios de OpenAI cambian
# con el tiempo — estos son el valor por defecto, no una promesa de precio).
_DEFAULT_PRICING = {
    "gpt-5.6-luna":  {"input": 0.20, "cached_input": 0.02, "output": 1.20},
    "gpt-5.6-terra": {"input": 2.00, "cached_input": 0.20, "output": 12.00},
    "gpt-5.6-sol":   {"input": 4.00, "cached_input": 0.40, "output": 20.00},
}
try:
    _pricing_override = json.loads(os.environ.get("AI_PRICING_CONFIG_JSON", "{}"))
except json.JSONDecodeError:
    _pricing_override = {}
AI_PRICING_CONFIG = {**_DEFAULT_PRICING, **_pricing_override}

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
# Herramientas (function calling) — envoltorios sobre data.py / knowledge.py.
# El router local (más abajo) llama estas mismas funciones directamente en
# Python, sin pasar por OpenAI, para las consultas que no necesitan IA.
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
# Router determinístico: intenta responder SIN OpenAI. Nunca usa IA para
# decidir — solo regex/keywords sobre las mismas funciones-herramienta de
# arriba. Si ningún patrón matchea con confianza, devuelve None y el
# llamador cae al flujo de OpenAI (nunca se fuerza una respuesta local
# dudosa por ahorrar costo).
# --------------------------------------------------------------------------
def _extraer_proyecto(texto: str) -> str | None:
    proyectos = data_mod.load_data()["proyectos"]["proyecto"].dropna().tolist()
    t = texto.lower()
    for p in proyectos:
        if p.lower() in t:
            return p
    if "transversal" in t:
        return "Transversal"
    return None


def _extraer_dias(texto: str) -> int | None:
    t = texto.lower()
    if "hoy" in t:
        return 1
    if "esta semana" in t:
        return 7
    if "este mes" in t:
        return 30
    return None


def _ventana_txt(dias: int | None) -> str:
    return {1: " hoy", 7: " esta semana", 30: " este mes"}.get(dias, "")


def _resp_horas(texto: str) -> tuple[str, str]:
    proyecto = _extraer_proyecto(texto)
    dias = _extraer_dias(texto)
    r = _tool_get_hours_by_project(proyecto=proyecto, dias=dias)
    horas = r["horas_por_proyecto"]
    ventana = _ventana_txt(dias)
    if proyecto:
        total = horas.get(proyecto, 0.0)
        return f"Has registrado {total:.1f} horas en {proyecto}{ventana}.", "local"
    if not horas:
        return f"No encontré actividades con horas registradas{ventana}.", "local"
    partes = "; ".join(f"{p}: {h:.1f} h" for p, h in horas.items())
    return f"Horas registradas{ventana}: {partes}.", "local"


def _resp_pendientes(texto: str) -> tuple[str, str]:
    proyecto = _extraer_proyecto(texto)
    items = _tool_get_pending_tasks(proyecto=proyecto)["pendientes"]
    extra = f" en {proyecto}" if proyecto else ""
    if not items:
        return f"No tienes actividades pendientes{extra}.", "local"
    lineas = "\n".join(f"- **{i['actividad']}** ({i['proyecto']}, {i['fecha_inicio']}, "
                        f"prioridad {i['prioridad']})" for i in items)
    return f"Tienes {len(items)} pendiente(s){extra}:\n\n{lineas}", "local"


def _resp_bloqueos(texto: str) -> tuple[str, str]:
    proyecto = _extraer_proyecto(texto)
    items = _tool_get_blockers(proyecto=proyecto)["bloqueos"]
    extra = f" en {proyecto}" if proyecto else ""
    if not items:
        return f"No tienes bloqueos activos{extra}.", "local"
    lineas = "\n".join(f"- **{i['actividad']}** ({i['proyecto']}, {i['fecha_inicio']}): {i['resultado']}"
                        for i in items)
    return f"Tienes {len(items)} bloqueo(s){extra}:\n\n{lineas}", "local"


def _resp_proyectos(_texto: str) -> tuple[str, str]:
    proyectos = _tool_get_projects()["proyectos"]
    return f"Tus proyectos registrados son: {', '.join(proyectos)}.", "local"


def _resp_actividades_recientes(texto: str) -> tuple[str, str]:
    items = _tool_get_activities(dias=_extraer_dias(texto) or 14)["actividades"][:5]
    if not items:
        return "No encontré actividades recientes.", "local"
    lineas = "\n".join(f"- **{i['actividad']}** ({i['proyecto']}, {i['fecha_inicio']}, {i['estado']})"
                        for i in items)
    return f"Tus actividades más recientes:\n\n{lineas}", "local"


def _resp_conteo_actividades(texto: str) -> tuple[str, str]:
    proyecto = _extraer_proyecto(texto)
    dias = _extraer_dias(texto)
    df = data_mod.load_data()["actividades"]
    if proyecto:
        df = df[df["proyecto"] == proyecto]
    if dias:
        limite = dt.date.today() - dt.timedelta(days=dias)
        df = df[df["fecha_inicio"].dt.date >= limite]
    completadas = int(df["estado"].eq("Completado").sum())
    extra = f" en {proyecto}" if proyecto else ""
    return (f"Tienes {len(df)} actividad(es) registradas{extra}{_ventana_txt(dias)}, "
            f"de las cuales {completadas} están completadas."), "local"


def _resp_conocimiento(tema: str) -> tuple[str, str] | None:
    items = _tool_search_knowledge(query=tema)["resultados"]
    if not items:
        return None  # sin resultados locales: puede que valga la pena preguntarle a la IA
    lineas = "\n".join(f"- **{i['titulo']}** ({i['categoria']}, {i['estado']}): {i['descripcion_breve']}"
                        for i in items[:8])
    return f'Esto es lo que tienes guardado sobre "{tema}":\n\n{lineas}', "conocimiento"


def _generar_mermaid_estructurado(contenido: str) -> str | None:
    """Convierte encabezados/listas Markdown en un árbol Mermaid
    determinístico. Devuelve None si el contenido no tiene suficiente
    estructura — en ese caso sí vale la pena que la IA interprete las
    relaciones conceptuales de un texto en prosa."""
    nodos: list[tuple[int, str]] = []
    for linea in contenido.splitlines():
        if not linea.strip():
            continue
        m = re.match(r"^(#{1,4})\s+(.+)", linea)
        if m:
            nodos.append((len(m.group(1)), m.group(2).strip()))
            continue
        m2 = re.match(r"^\s*[-*]\s+(.+)", linea)
        if m2 and nodos:
            nodos.append((nodos[-1][0] + 1, m2.group(1).strip()))

    if len(nodos) < 3:
        return None

    mermaid = ["graph TD"]
    pila: list[tuple[int, str]] = []
    for i, (nivel, texto) in enumerate(nodos):
        nid = f"n{i}"
        texto_limpio = re.sub(r'["\n]', " ", texto)[:60]
        mermaid.append(f'    {nid}["{texto_limpio}"]')
        while pila and pila[-1][0] >= nivel:
            pila.pop()
        if pila:
            mermaid.append(f"    {pila[-1][1]} --> {nid}")
        pila.append((nivel, nid))
    return "\n".join(mermaid)


_PATRON_MAPA_TITULO_CONTENIDO = re.compile(r"\*\*(.+?)\*\*\n\n(.+)", re.DOTALL)


def _resp_mapa(texto: str) -> tuple[str, str] | None:
    m = _PATRON_MAPA_TITULO_CONTENIDO.search(texto)
    if not m:
        return None
    titulo, contenido = m.group(1), m.group(2)
    mermaid = _generar_mermaid_estructurado(contenido)
    if not mermaid:
        return None
    respuesta = (f"Mapa conceptual de **{titulo}** (generado directo de la estructura "
                  f"guardada, sin usar IA):\n\n```mermaid\n{mermaid}\n```")
    return respuesta, "local"


_PATRON_CONOCIMIENTO = re.compile(
    r"qu[eé] tengo (?:estudiado|guardado|aprendido)(?:\s+sobre|\s+de)?\s+(.+?)[\?\.]?$",
    re.IGNORECASE,
)
_PATRON_MAPA = re.compile(r"mapa\s+conceptual", re.IGNORECASE)
_PATRON_HORAS = re.compile(r"cu[aá]ntas?\s+horas|horas\s+(dedi|traba|registr)", re.IGNORECASE)
_PATRON_PENDIENTES = re.compile(r"pendient", re.IGNORECASE)
_PATRON_BLOQUEOS = re.compile(r"bloque", re.IGNORECASE)
_PATRON_PROYECTOS = re.compile(r"qu[eé]\s+proyectos|proyectos\s+activ", re.IGNORECASE)
_PATRON_RECIENTES = re.compile(r"actividad(es)?\s+(m[aá]s\s+)?recient", re.IGNORECASE)
_PATRON_CONTEO_ACTIVIDADES = re.compile(r"cu[aá]ntas?\s+actividades", re.IGNORECASE)


def _clasificar_consulta(texto: str) -> tuple[str, str] | None:
    t = texto.strip()

    m_mapa = _PATRON_MAPA.search(t)
    if m_mapa:
        resultado = _resp_mapa(t)
        if resultado:
            return resultado
        # sin estructura suficiente -> cae a OpenAI (return None más abajo)

    m_con = _PATRON_CONOCIMIENTO.search(t)
    if m_con:
        resultado = _resp_conocimiento(m_con.group(1).strip())
        if resultado:
            return resultado

    if _PATRON_HORAS.search(t):
        return _resp_horas(t)
    if _PATRON_PENDIENTES.search(t):
        return _resp_pendientes(t)
    if _PATRON_BLOQUEOS.search(t):
        return _resp_bloqueos(t)
    if _PATRON_PROYECTOS.search(t):
        return _resp_proyectos(t)
    if _PATRON_RECIENTES.search(t):
        return _resp_actividades_recientes(t)
    if _PATRON_CONTEO_ACTIVIDADES.search(t):
        return _resp_conteo_actividades(t)

    return None


# --------------------------------------------------------------------------
# Selección de modelo por tipo de tarea
# --------------------------------------------------------------------------
_PATRON_ANALISIS_COMPLEJO = re.compile(
    r"analiza|compara|relaciona.*proyecto|propon(me)?\s+soluc", re.IGNORECASE,
)


def _elegir_modelo(texto: str) -> str:
    if _PATRON_ANALISIS_COMPLEJO.search(texto):
        return OPENAI_REASONING_MODEL
    return OPENAI_MODEL


# --------------------------------------------------------------------------
# Consumo, presupuesto y caché — archivos aparte, nunca tocan el Excel
# --------------------------------------------------------------------------
def _estimar_costo(modelo: str | None, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    precios = AI_PRICING_CONFIG.get(modelo or "")
    if not precios:
        return 0.0
    no_cacheados = max(input_tokens - cached_tokens, 0)
    costo = (
        no_cacheados / 1_000_000 * precios["input"]
        + cached_tokens / 1_000_000 * precios.get("cached_input", precios["input"])
        + output_tokens / 1_000_000 * precios["output"]
    )
    return round(costo, 6)


def _registrar_uso(tipo: str, modelo: str | None, input_tokens: int, output_tokens: int,
                    costo: float, duracion_ms: float, exito: bool) -> None:
    evento = {
        "fecha": dt.datetime.now().isoformat(), "tipo": tipo, "modelo": modelo,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "costo_estimado_usd": costo, "duracion_ms": round(duracion_ms), "exito": exito,
    }
    try:
        USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except OSError:
        pass  # el registro de consumo nunca debe romper una respuesta real


def _leer_eventos_mes(anio_mes: str | None = None) -> list[dict]:
    anio_mes = anio_mes or dt.date.today().strftime("%Y-%m")
    if not USAGE_LOG_PATH.exists():
        return []
    eventos = []
    try:
        with open(USAGE_LOG_PATH, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    ev = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if ev.get("fecha", "").startswith(anio_mes):
                    eventos.append(ev)
    except OSError:
        pass
    return eventos


def resumen_consumo_mes() -> dict:
    """Consumo ESTIMADO por la app este mes — nunca el saldo real de la
    cuenta de OpenAI (esta integración no tiene ni debe tener acceso a eso)."""
    eventos = _leer_eventos_mes()
    eventos_ia = [e for e in eventos if e.get("tipo") in ("ia", "ia_cache")]
    costo_total = round(sum(e.get("costo_estimado_usd", 0.0) for e in eventos_ia), 4)
    tokens_total = sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in eventos_ia)
    porcentaje = round((costo_total / AI_MONTHLY_BUDGET_USD * 100) if AI_MONTHLY_BUDGET_USD else 0, 1)
    return {
        "consultas_ia": len(eventos_ia),
        "consultas_locales": len([e for e in eventos if e.get("tipo") in ("local", "conocimiento")]),
        "tokens_totales": tokens_total,
        "costo_estimado_usd": costo_total,
        "presupuesto_usd": AI_MONTHLY_BUDGET_USD,
        "porcentaje_usado": porcentaje,
    }


def _presupuesto_excedido() -> bool:
    if AI_MONTHLY_BUDGET_USD <= 0:
        return False
    return resumen_consumo_mes()["costo_estimado_usd"] >= AI_MONTHLY_BUDGET_USD


def _limite_diario_alcanzado() -> bool:
    if AI_DAILY_REQUEST_LIMIT <= 0:
        return False
    hoy = dt.date.today().strftime("%Y-%m-%d")
    eventos_hoy = [e for e in _leer_eventos_mes() if e.get("fecha", "").startswith(hoy)
                   and e.get("tipo") in ("ia", "ia_cache")]
    return len(eventos_hoy) >= AI_DAILY_REQUEST_LIMIT


def _cache_key(tipo: str, contenido: str) -> str:
    return hashlib.sha256(f"{tipo}:{contenido}".encode("utf-8")).hexdigest()


def _cache_get(tipo: str, contenido: str) -> str | None:
    if not CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    entrada = cache.get(_cache_key(tipo, contenido))
    return entrada["respuesta"] if entrada else None


def _cache_set(tipo: str, contenido: str, respuesta: str, modelo: str) -> None:
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        cache = {}
    cache[_cache_key(tipo, contenido)] = {
        "respuesta": respuesta, "modelo": modelo, "fecha": dt.datetime.now().isoformat(),
    }
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


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


def _guardar_intercambio(conversacion_id: str, mensaje_usuario: str, respuesta: str, fuente: str) -> None:
    historial = _cargar_conversacion(conversacion_id)
    mensajes_previos = historial.get("mensajes", [])
    ahora = dt.datetime.now().isoformat()
    mensajes_previos.append({"rol": "user", "contenido": mensaje_usuario, "fecha_hora": ahora})
    mensajes_previos.append({"rol": "assistant", "contenido": respuesta, "fecha_hora": ahora, "fuente": fuente})
    historial["mensajes"] = mensajes_previos
    if not historial.get("titulo"):
        historial["titulo"] = mensaje_usuario[:60]
    if not historial.get("fecha_creacion"):
        historial["fecha_creacion"] = ahora
    historial["conversacion_id"] = conversacion_id
    _guardar_conversacion(conversacion_id, historial)


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
# Llamada real a OpenAI (bucle de tool-calling sobre la Responses API) —
# solo se llega aquí cuando el router determinístico no pudo responder.
# --------------------------------------------------------------------------
def _responder_con_openai(mensajes_previos: list[dict], contenido_usuario: str) -> tuple[bool, str, str, dict]:
    """Devuelve (ok, texto_o_error, modelo_usado, uso_tokens). No guarda nada
    — el llamador decide qué hacer con el resultado."""
    modelo = _elegir_modelo(contenido_usuario)
    input_items: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in mensajes_previos[-20:]:
        input_items.append({"role": m["rol"], "content": m["contenido"]})
    input_items.append({"role": "user", "content": contenido_usuario})

    client = OpenAI(api_key=OPENAI_API_KEY, timeout=_REQUEST_TIMEOUT)
    texto = None
    uso = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    try:
        for _ in range(MAX_TOOL_TURNS):
            response = client.responses.create(
                model=modelo, input=input_items, tools=TOOLS, max_output_tokens=AI_MAX_OUTPUT_TOKENS,
            )
            if response.usage:
                uso["input_tokens"] += response.usage.input_tokens
                uso["output_tokens"] += response.usage.output_tokens
                uso["cached_tokens"] += response.usage.input_tokens_details.cached_tokens
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
            return False, "El asistente no pudo completar la respuesta (demasiadas herramientas encadenadas).", modelo, uso
    except Exception as exc:
        return False, f"No fue posible conectar con OpenAI: {exc}", modelo, uso

    return True, texto, modelo, uso


# --------------------------------------------------------------------------
# Punto de entrada público — router primero, OpenAI solo si hace falta.
# --------------------------------------------------------------------------
def enviar_mensaje(conversacion_id: str, mensaje_usuario: str,
                    contexto_extra: str | None = None) -> tuple[bool, str, str]:
    """Devuelve (ok, texto_de_respuesta_o_error, fuente). fuente es "local",
    "conocimiento", "ia", "ia_cache" o "sistema" (config/presupuesto/error).
    contexto_extra es para prompts armados desde una entrada de conocimiento
    (ej. el botón "Explicarme" de /conocimiento)."""
    if not is_configured():
        return False, ("El asistente no está activado todavía: falta configurar "
                        "OPENAI_API_KEY en las variables de entorno."), "sistema"

    contenido_usuario = f"{mensaje_usuario}\n\n{contexto_extra}" if contexto_extra else mensaje_usuario
    t_inicio = dt.datetime.now()

    ruta_local = _clasificar_consulta(contenido_usuario)
    if ruta_local:
        texto, fuente = ruta_local
        duracion_ms = (dt.datetime.now() - t_inicio).total_seconds() * 1000
        _registrar_uso(fuente, None, 0, 0, 0.0, duracion_ms, True)
        _guardar_intercambio(conversacion_id, mensaje_usuario, texto, fuente)
        return True, texto, fuente

    if _presupuesto_excedido():
        texto = (f"⚠️ Se alcanzó el presupuesto configurado para IA este mes "
                  f"(${AI_MONTHLY_BUDGET_USD:.2f}). Las funciones que no requieren IA "
                  "siguen disponibles con normalidad.")
        _registrar_uso("bloqueado", None, 0, 0, 0.0, 0, False)
        _guardar_intercambio(conversacion_id, mensaje_usuario, texto, "sistema")
        return False, texto, "sistema"

    if _limite_diario_alcanzado():
        texto = "Se alcanzó el límite diario de consultas a IA configurado. Vuelve a intentarlo mañana."
        _registrar_uso("bloqueado", None, 0, 0, 0.0, 0, False)
        _guardar_intercambio(conversacion_id, mensaje_usuario, texto, "sistema")
        return False, texto, "sistema"

    cacheado = _cache_get("mensaje", contenido_usuario)
    if cacheado:
        duracion_ms = (dt.datetime.now() - t_inicio).total_seconds() * 1000
        _registrar_uso("ia_cache", None, 0, 0, 0.0, duracion_ms, True)
        _guardar_intercambio(conversacion_id, mensaje_usuario, cacheado, "ia_cache")
        return True, cacheado, "ia_cache"

    historial = _cargar_conversacion(conversacion_id)
    ok, texto, modelo, uso = _responder_con_openai(historial.get("mensajes", []), contenido_usuario)
    duracion_ms = (dt.datetime.now() - t_inicio).total_seconds() * 1000

    if not ok:
        _registrar_uso("ia", modelo, uso["input_tokens"], uso["output_tokens"], 0.0, duracion_ms, False)
        return False, texto, "sistema"

    costo = _estimar_costo(modelo, uso["input_tokens"], uso["output_tokens"], uso["cached_tokens"])
    _registrar_uso("ia", modelo, uso["input_tokens"], uso["output_tokens"], costo, duracion_ms, True)
    _cache_set("mensaje", contenido_usuario, texto, modelo)
    _guardar_intercambio(conversacion_id, mensaje_usuario, texto, "ia")
    return True, texto, "ia"
