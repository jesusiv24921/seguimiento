"""Sentinel Alerts — análisis funcional y técnico de los motores de alertamiento.

Además de las métricas propias (horas, estado, evolución) esta página conecta
con todo lo demás que ya existe en Seguimiento para este proyecto: bloqueos y
pendientes activos, hallazgos abiertos, conocimiento relacionado, actividades
recientes (con el mismo panel de detalle que usa /actividades), y un acceso
directo al Asistente ya con el contexto de este proyecto puesto.
"""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dcc, html

import charts
from components import (badge_conocimiento_estado, badge_estado, badge_hallazgo_estado, badge_proyecto,
                         chart_card, kpi_card, page_header)
from data_store import apply_all_filters, df_from_store, hallazgos_from_store, knowledge_from_store
from pages.bloqueos import _chip_bloqueado, _chip_vencimiento
from theme import ACCENT

dash.register_page(__name__, path="/sentinel", name="Sentinel Alerts", title="Sentinel Alerts")

PROYECTO = "Sentinel Alerts"
FLUJO_CONCEPTUAL = ["Contrato", "Engine", "Orquestador", "Ejecución", "Evaluación",
                     "Generación de alerta", "Persistencia"]

layout = html.Div(className="page", children=[
    html.Div(className="act-page-header", children=[
        page_header("Sentinel Alerts", "Análisis funcional y técnico de los motores de alertamiento.",
                     period_id="page-header-period"),
        dbc.Button([html.I(className="bi bi-robot"), "Preguntar al Asistente"],
                    id="sen-btn-preguntar-asistente", className="btn-refresh", n_clicks=0),
    ]),

    html.Div([
        kpi_card("sen-kpi-total", "Actividades", "bi bi-list-check"),
        kpi_card("sen-kpi-horas", "Horas invertidas", "bi bi-clock-history"),
        kpi_card("sen-kpi-completadas", "Completadas", "bi bi-check2-circle", tone="tone-good",
                  context_id="sen-kpi-completadas-ctx"),
        kpi_card("sen-kpi-bloqueadas", "Bloqueadas", "bi bi-exclamation-triangle",
                  icon_id="sen-kpi-bloqueadas-icon", tone="tone-good"),
        kpi_card("sen-kpi-pendientes", "Pendientes", "bi bi-flag",
                  icon_id="sen-kpi-pendientes-icon", tone="tone-good"),
        kpi_card("sen-kpi-hallazgos", "Hallazgos abiertos", "bi bi-search",
                  icon_id="sen-kpi-hallazgos-icon", tone="tone-good"),
    ], className="kpi-grid"),

    chart_card([
        html.Div([html.I(className="bi bi-diagram-3"), "Flujo conceptual de una alerta"], className="section-title"),
        html.Div("Contexto de arquitectura — no representa datos de ejecución real, solo el flujo "
                  "conceptual documentado en Sentinel Alertas.", className="section-caption"),
        html.Div([
            html.Div([
                html.Div(step, className="flow-step"),
                html.I(className="bi bi-arrow-right flow-arrow") if i < len(FLUJO_CONCEPTUAL) - 1 else None,
            ], className="flow-step-wrap") for i, step in enumerate(FLUJO_CONCEPTUAL)
        ], className="flow-diagram"),
    ]),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-graph-up-arrow"), "Evolución de horas"], className="section-title"),
            html.Div("Horas invertidas en Sentinel Alerts, semana a semana.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="sen-g-evolucion", config={"displayModeBar": False, "responsive": True})),
        ]), lg=7, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-flag"), "Estado del trabajo"], className="section-title"),
            html.Div("Completado, en progreso, bloqueado.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="sen-g-estado", config={"displayModeBar": False, "responsive": True})),
        ]), lg=5, className="mb-3"),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-search"), "Áreas revisadas"], className="section-title"),
        html.Div("Agrupado por el tema/categoría real de cada actividad — la columna \"motor\" está vacía en "
                  "los datos actuales, así que no se listan motores individuales para no inventar información.",
                  className="section-caption"),
        dcc.Loading(type="circle", children=dcc.Graph(id="sen-g-temas", config={"displayModeBar": False, "responsive": True})),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-clock-history"), "Actividades recientes"], className="section-title"),
        html.Div("Haz clic en cualquiera para ver el detalle completo.", className="section-caption"),
        html.Div(id="sen-actividades-recientes", className="con-reciente-lista"),
    ]),

    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-exclamation-triangle"), "Bloqueos y pendientes activos"],
                      className="section-title"),
            dcc.Link([html.I(className="bi bi-arrow-right"), "Ver todos en Bloqueos y pendientes"],
                      href="/bloqueos", className="btn-refresh btn-sm-card ms-auto"),
        ]),
        html.Div("Ordenados por urgencia — lo mismo que se ve en Bloqueos y pendientes, filtrado a este proyecto.",
                  className="section-caption"),
        html.Div(id="sen-bloqueos-cards", className="hal-cards-grid"),
    ]),

    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-clipboard-data"), "Hallazgos abiertos"], className="section-title"),
            dcc.Link([html.I(className="bi bi-arrow-right"), "Ver todos en Hallazgos"],
                      href="/hallazgos", className="btn-refresh btn-sm-card ms-auto"),
        ]),
        html.Div("Hallazgos de validación abiertos o en revisión para este proyecto.", className="section-caption"),
        html.Div(id="sen-hallazgos-cards", className="hal-cards-grid"),
    ]),

    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-mortarboard"), "Conocimiento relacionado"], className="section-title"),
            dcc.Link([html.I(className="bi bi-arrow-right"), "Ver todo en Conocimiento"],
                      href="/conocimiento", className="btn-refresh btn-sm-card ms-auto"),
        ]),
        html.Div("Soluciones, estudio y notas ya guardadas que mencionan este proyecto.",
                  className="section-caption"),
        html.Div(id="sen-conocimiento-cards", className="hal-cards-grid"),
    ]),
])


def _actividad_row(row) -> html.Button:
    horas_txt = f"{row['horas']:.1f} h" if pd.notna(row["horas"]) else "—"
    return html.Button(className="con-reciente-row", n_clicks=0,
                         id={"type": "sen-actividad-view", "index": row["actividad_id"]}, children=[
        badge_estado(row["estado"]),
        html.Div([
            html.Div(row["actividad"], className="con-reciente-row-title"),
            html.Div(f"{row['tema'] or 'Sin tema'} · {row['fecha_inicio'].strftime('%d/%m/%Y')}",
                      className="con-reciente-row-meta"),
        ]),
        html.Div(horas_txt, className="con-reciente-row-fecha"),
    ])


def _bloqueo_card(row) -> html.Div:
    return html.Div(className="blocker-card", children=[
        html.Div([html.I(className="bi bi-exclamation-octagon-fill"), badge_proyecto(row["proyecto"])],
                  className="blocker-card-head"),
        html.Div(row["tema"] or row["actividad"], className="blocker-card-title"),
        html.Div(f"Problema: {row['resultado'] or 'No especificado en los datos.'}",
                  className="blocker-card-body"),
        html.Div(className="blq-chip-row", children=[_chip_bloqueado(row["fecha_inicio"])]),
    ])


def _pendiente_card(row, chip) -> html.Div:
    return html.Div(className="pending-card", children=[
        html.Div([html.I(className="bi bi-flag-fill"), badge_proyecto(row["proyecto"])],
                  className="blocker-card-head"),
        html.Div(row["actividad"], className="blocker-card-title"),
        html.Div(row["descripcion"] or "Sin descripción.", className="blocker-card-body"),
        html.Div(className="blq-chip-row", children=[chip]),
    ])


def _hallazgo_mini_card(row) -> html.Div:
    return html.Div(className="hal-card", children=[
        html.Div(className="hal-card-head", children=[
            badge_hallazgo_estado(row["Estado"]),
            html.Span(row["Motor"], className="hal-card-motor"),
        ]),
        html.Div(row["Descripción"], className="hal-card-desc"),
        html.Div(className="hal-card-meta-grid", children=[
            html.Div([html.Span("Script", className="hal-card-meta-label"),
                       html.Span(row["Script"], className="hal-card-meta-value")]),
            html.Div([html.Span("Función", className="hal-card-meta-label"),
                       html.Span(row["Función"], className="hal-card-meta-value")]),
        ]),
    ])


def _conocimiento_mini_card(row) -> html.Div:
    return html.Div(className="hal-card", children=[
        html.Div(className="hal-card-head", children=[
            badge_conocimiento_estado(row["estado"]),
            html.Span(row["categoria"], className="hal-card-motor"),
        ]),
        html.Div(row["titulo"], className="hal-card-desc"),
        html.Div(row["descripcion_breve"] or "", className="hal-card-meta-value"),
    ])


@dash.callback(
    Output("sen-kpi-total", "children"),
    Output("sen-kpi-horas", "children"),
    Output("sen-kpi-completadas", "children"), Output("sen-kpi-completadas-ctx", "children"),
    Output("sen-kpi-bloqueadas", "children"), Output("sen-kpi-bloqueadas-icon", "className"),
    Output("sen-kpi-pendientes", "children"), Output("sen-kpi-pendientes-icon", "className"),
    Output("sen-kpi-hallazgos", "children"), Output("sen-kpi-hallazgos-icon", "className"),
    Output("sen-g-evolucion", "figure"),
    Output("sen-g-estado", "figure"),
    Output("sen-g-temas", "figure"),
    Output("sen-actividades-recientes", "children"),
    Output("sen-bloqueos-cards", "children"),
    Output("sen-hallazgos-cards", "children"),
    Output("sen-conocimiento-cards", "children"),
    Input("store-data", "data"),
    Input("store-hallazgos", "data"),
    Input("store-conocimiento", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_sentinel(store_json, hallazgos_json, conocimiento_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en seguimiento.xlsx")
        vacio = html.Div("Sin datos disponibles.", className="section-caption")
        return ("0", "0.0 h", "0", "0% del total", "0", "kpi-icon tone-good",
                "0", "kpi-icon tone-good", "0", "kpi-icon tone-good",
                empty, empty, empty, vacio, vacio, vacio, vacio)

    base = df[df["proyecto"] == PROYECTO]
    filtered = apply_all_filters(base, start_date, end_date)

    total = len(filtered)
    horas = filtered["horas"].fillna(0).sum()
    completadas = int(filtered["estado"].eq("Completado").sum())
    bloqueadas_df = filtered[filtered["estado"] == "Bloqueado"]
    bloqueadas = len(bloqueadas_df)
    pct_completadas = (completadas / total * 100) if total else 0
    bloqueadas_icon = "kpi-icon tone-good" if bloqueadas == 0 else "kpi-icon tone-critical"

    # Los pendientes, igual que en /bloqueos, se muestran siempre sin importar
    # el filtro de fecha global — son tareas abiertas, no un evento pasado.
    pendientes_df = base[base["estado"] == "Pendiente"]
    n_pendientes = len(pendientes_df)
    pendientes_icon = "kpi-icon tone-good" if n_pendientes == 0 else "kpi-icon tone-warning"

    fig_evolucion = charts.fig_evolucion_semanal(filtered)
    fig_estado = charts.fig_donut_estado(filtered)
    fig_temas = charts.fig_barras_horas(filtered, "tema", color=ACCENT, top_n=8)

    recientes = base.sort_values("fecha_inicio", ascending=False).head(6)
    lista_recientes = [_actividad_row(r) for _, r in recientes.iterrows()] or [
        html.Div("Sin actividades registradas todavía.", className="section-caption")]

    bloqueo_cards = [_bloqueo_card(r) for _, r in bloqueadas_df.sort_values("fecha_inicio").iterrows()]
    filas_urgencia = []
    for _, r in pendientes_df.iterrows():
        chip, dias = _chip_vencimiento(r["fecha_inicio"])
        filas_urgencia.append((dias, r, chip))
    filas_urgencia.sort(key=lambda t: t[0])
    pendiente_cards = [_pendiente_card(r, chip) for _, r, chip in filas_urgencia]
    bloqueos_pendientes_cards = bloqueo_cards + pendiente_cards
    if not bloqueos_pendientes_cards:
        bloqueos_pendientes_cards = [html.Div("Sin bloqueos ni pendientes activos para este proyecto.",
                                                 className="section-caption")]

    dfh = hallazgos_from_store(hallazgos_json)
    n_hallazgos_abiertos = 0
    hallazgos_cards = [html.Div("Sin datos de hallazgos disponibles.", className="section-caption")]
    if not dfh.empty:
        hal_proyecto = dfh[dfh["Proyecto"] == PROYECTO]
        hal_abiertos = hal_proyecto[hal_proyecto["Estado"].isin(["Abierto", "En revisión"])]
        n_hallazgos_abiertos = len(hal_abiertos)
        hallazgos_cards = [_hallazgo_mini_card(r) for _, r in hal_abiertos.iterrows()] or [
            html.Div("Sin hallazgos abiertos para este proyecto.", className="section-caption")]
    hallazgos_icon = "kpi-icon tone-good" if n_hallazgos_abiertos == 0 else "kpi-icon tone-critical"

    dfc = knowledge_from_store(conocimiento_json)
    conocimiento_cards = [html.Div("Sin conocimiento registrado todavía.", className="section-caption")]
    if not dfc.empty:
        con_proyecto = dfc[dfc["proyectos"].fillna("").str.contains(PROYECTO, regex=False)]
        con_proyecto = con_proyecto.sort_values("fecha_actualizacion", ascending=False).head(6)
        if not con_proyecto.empty:
            conocimiento_cards = [_conocimiento_mini_card(r) for _, r in con_proyecto.iterrows()]

    return (str(total), f"{horas:.1f} h", str(completadas), f"{pct_completadas:.0f}% del total",
            str(bloqueadas), bloqueadas_icon, str(n_pendientes), pendientes_icon,
            str(n_hallazgos_abiertos), hallazgos_icon,
            fig_evolucion, fig_estado, fig_temas,
            lista_recientes, bloqueos_pendientes_cards, hallazgos_cards, conocimiento_cards)


@dash.callback(
    Output("store-selected-activity", "data", allow_duplicate=True),
    Input({"type": "sen-actividad-view", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def ver_actividad_desde_sentinel(n_clicks_list):
    if not n_clicks_list or not any(n_clicks_list):
        return dash.no_update
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update
    return triggered["index"]


@dash.callback(
    Output("store-prompt-pendiente", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("sen-btn-preguntar-asistente", "n_clicks"),
    prevent_initial_call=True,
)
def preguntar_asistente_sentinel(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    payload = {"prompt": "¿Qué está pasando con Sentinel Alerts?", "proyecto_contexto": PROYECTO}
    return payload, "/asistente"
