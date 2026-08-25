"""
Piezas de UI reutilizables. Cada página compone su layout a partir de estas
funciones en vez de reconstruir cards/badges/headers a mano, para que todas
las páginas se vean parte de la misma aplicación (misma tipografía, mismos
colores, mismo sistema de tarjetas).
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from theme import CONOCIMIENTO_ESTADO_PILL, ESTADO_PILL, HALLAZGO_ESTADO_PILL, PRIORIDAD_PILL, PROYECTO_PILL


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------
def _pill(text: str, pill_dict: dict, fallback_key: str) -> html.Span:
    style = pill_dict.get(text, pill_dict[fallback_key])
    return html.Span(text, className="status-pill",
                       style={"backgroundColor": style["bg"], "color": style["fg"]})


def badge_estado(valor: str) -> html.Span:
    return _pill(valor, ESTADO_PILL, "Sin estado")


def badge_prioridad(valor: str) -> html.Span:
    return _pill(valor, PRIORIDAD_PILL, "Sin prioridad")


def badge_proyecto(valor: str) -> html.Span:
    return _pill(valor, PROYECTO_PILL, "Transversal")


def badge_hallazgo_estado(valor: str) -> html.Span:
    return _pill(valor, HALLAZGO_ESTADO_PILL, "Sin estado")


def badge_conocimiento_estado(valor: str) -> html.Span:
    return _pill(valor, CONOCIMIENTO_ESTADO_PILL, "Sin estado")


# --------------------------------------------------------------------------
# KPI card
# --------------------------------------------------------------------------
def kpi_card(value_id: str, label: str, icon: str, icon_id: str | None = None,
             tone: str = "", delta_id: str | None = None,
             context_id: str | None = None) -> dbc.Card:
    """Tarjeta KPI: icono + valor + etiqueta + (contexto secundario XOR delta
    de tendencia). `context_id` es para "85% del total"; `delta_id` es para
    el chip de tendencia con flecha (↑/↓) usado en KPIs semanales."""
    icon_classes = f"kpi-icon {tone}".strip()
    icon_el = html.Div(html.I(className=icon), className=icon_classes, id=icon_id) if icon_id \
        else html.Div(html.I(className=icon), className=icon_classes)
    extra = None
    if delta_id:
        extra = html.Div(id=delta_id, className="kpi-delta flat")
    elif context_id:
        extra = html.Div(id=context_id, className="kpi-context")
    return dbc.Card(
        html.Div(className="d-flex align-items-start gap-3", children=[
            icon_el,
            html.Div(className="kpi-body", children=[
                html.Div("—", id=value_id, className="kpi-value"),
                html.Div(label, className="kpi-label"),
                extra,
            ]),
        ]),
        className="kpi-card",
    )


# --------------------------------------------------------------------------
# Headers y contenedores
# --------------------------------------------------------------------------
def page_header(title: str, subtitle: str, period_id: str | None = None) -> html.Div:
    right = html.Div(id=period_id, className="page-header-period") if period_id else None
    return html.Div(className="page-header", children=[
        html.Div([
            html.Div(title, className="page-header-title"),
            html.Div(subtitle, className="page-header-subtitle"),
        ]),
        right,
    ])


def section_header(title: str, icon: str, caption: str | None = None) -> html.Div:
    children = [html.Div([html.I(className=icon), title], className="section-title")]
    if caption:
        children.append(html.Div(caption, className="section-caption"))
    return html.Div(children)


def chart_card(children, className: str = "") -> html.Div:
    return html.Div(children, className=f"chart-card {className}".strip())


def empty_state(message: str, icon: str = "bi-inbox", tone: str = "") -> html.Div:
    """Panel para reemplazar gráficos/listas vacías con un mensaje claro en
    vez de dejar un hueco en blanco (spec: nunca mostrar espacios sin
    explicación)."""
    return html.Div(className=f"empty-state {tone}".strip(), children=[
        html.I(className=f"bi {icon}"),
        html.Div(message),
    ])


def success_state(message: str) -> html.Div:
    return html.Div(className="empty-state tone-good", children=[
        html.I(className="bi bi-check-circle"),
        html.Div(message),
    ])
