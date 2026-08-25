"""
Sistema de diseño compartido: colores, tokens de texto y helpers de formato
usados por components.py, charts.py y todas las páginas. Centralizar esto
evita que cada página reinvente su propia paleta o formato de fecha.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

import data as data_mod

# --------------------------------------------------------------------------
# Paleta (paleta categórica y de estado validadas — ver skill dataviz)
# --------------------------------------------------------------------------
CAT_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

COLOR_PROYECTO = dict(data_mod.COLOR_PROYECTO)
COLOR_ESTADO = dict(data_mod.COLOR_ESTADO)

INK_PRIMARY = "#14140f"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8880"
GRID = "#ece9e2"
SURFACE = "#ffffff"
ACCENT = "#2a6fd6"

ESTADO_PILL = {
    "Completado":  {"bg": "rgba(12, 163, 12, 0.12)",  "fg": "#0a6b0a"},
    "En progreso": {"bg": "rgba(201, 133, 0, 0.14)",  "fg": "#8a5a00"},
    "Bloqueado":   {"bg": "rgba(208, 59, 59, 0.12)",  "fg": "#a52323"},
    "Pendiente":   {"bg": "rgba(137, 135, 129, 0.14)", "fg": "#6b6a63"},
    "Sin estado":  {"bg": "rgba(137, 135, 129, 0.14)", "fg": "#6b6a63"},
}
PRIORIDAD_PILL = {
    "Alta":           {"bg": "rgba(208, 59, 59, 0.10)", "fg": "#a52323"},
    "Media":          {"bg": "rgba(201, 133, 0, 0.10)", "fg": "#8a5a00"},
    "Baja":           {"bg": "rgba(12, 163, 12, 0.10)", "fg": "#0a6b0a"},
    "Sin prioridad":  {"bg": "rgba(137, 135, 129, 0.10)", "fg": "#6b6a63"},
}
PROYECTO_PILL = {
    "Sentinel Alerts": {"bg": "rgba(42, 120, 214, 0.12)", "fg": "#1a56a8"},
    "New Opps":        {"bg": "rgba(122, 74, 196, 0.12)", "fg": "#6a3ba8"},
    "Transversal":     {"bg": "rgba(137, 135, 129, 0.14)", "fg": "#6b6a63"},
}
HALLAZGO_ESTADO_PILL = {
    "Abierto":     {"bg": "rgba(208, 59, 59, 0.12)",  "fg": "#a52323"},
    "En revisión": {"bg": "rgba(201, 133, 0, 0.14)",  "fg": "#8a5a00"},
    "Cerrado":     {"bg": "rgba(12, 163, 12, 0.12)",  "fg": "#0a6b0a"},
    "Sin estado":  {"bg": "rgba(137, 135, 129, 0.14)", "fg": "#6b6a63"},
}
HALLAZGO_ESTADO_COLOR = {
    "Abierto": "#d03b3b", "En revisión": "#c98500", "Cerrado": "#0ca30c",
}
# New Opps usa púrpura en la paleta corporativa pedida por el usuario; el
# gráfico categórico (_color_map) sigue usando la paleta validada de la
# skill dataviz (naranja) para mantener el contraste CVD-safe en gráficos.
COLOR_PROYECTO_BRAND = {**COLOR_PROYECTO, "New Opps": "#7a4ac4"}

CONOCIMIENTO_ESTADO_PILL = {
    "En estudio":           {"bg": "rgba(201, 133, 0, 0.14)",  "fg": "#8a5a00"},
    "En progreso":          {"bg": "rgba(42, 111, 214, 0.12)", "fg": "#1a56a8"},
    "Aprendido":            {"bg": "rgba(12, 163, 12, 0.12)",  "fg": "#0a6b0a"},
    "Aplicado":             {"bg": "rgba(12, 163, 12, 0.12)",  "fg": "#0a6b0a"},
    "Pendiente de revisar": {"bg": "rgba(208, 59, 59, 0.10)",  "fg": "#a52323"},
    "Archivado":            {"bg": "rgba(137, 135, 129, 0.14)", "fg": "#6b6a63"},
    "Sin estado":           {"bg": "rgba(137, 135, 129, 0.14)", "fg": "#6b6a63"},
}
CONOCIMIENTO_CATEGORIA_ICONO = {
    "Estudio": "bi-book", "Soluciones": "bi-tools", "Errores y aprendizajes": "bi-bug",
    "Conceptos": "bi-journal-text", "Procedimientos": "bi-list-check",
    "Ideas": "bi-lightbulb", "Referencias": "bi-link-45deg", "Notas": "bi-sticky",
}

MESES_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def fmt_fecha_es(d: dt.date) -> str:
    return f"{d.day} de {MESES_ES[d.month]} de {d.year}"


def fmt_periodo_corto(d: dt.date) -> str:
    return f"{d.day:02d} {MESES_ES[d.month][:3].upper()}"


def fmt_rango_periodo(start, end) -> str:
    """'03 AGO — 23 AGO' para el header de cada página. Si no hay filtro de
    fecha explícito, cae a None (el caller decide el texto por defecto)."""
    if not start or not end:
        return None
    s = pd.Timestamp(start).date()
    e = pd.Timestamp(end).date()
    return f"{fmt_periodo_corto(s)} — {fmt_periodo_corto(e)}"


def color_map(categories: list[str], preferred: dict[str, str]) -> dict[str, str]:
    """Asigna colores categóricos: respeta los colores preferidos conocidos
    y asigna los siguientes slots de la paleta, en orden, a categorías
    nuevas (p.ej. si se agrega un proyecto nuevo en el Excel)."""
    colors: dict[str, str] = {}
    used = set(preferred.values())
    free_slots = [c for c in CAT_PALETTE if c not in used]
    for cat in categories:
        if cat in preferred:
            colors[cat] = preferred[cat]
        else:
            colors[cat] = free_slots.pop(0) if free_slots else INK_MUTED
    return colors
