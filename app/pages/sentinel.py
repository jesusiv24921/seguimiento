"""Sentinel Alerts — análisis funcional y técnico de los motores de alertamiento."""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

import charts
from components import chart_card, kpi_card, page_header
from data_store import apply_all_filters, df_from_store
from theme import ACCENT

dash.register_page(__name__, path="/sentinel", name="Sentinel Alerts", title="Sentinel Alerts")

FLUJO_CONCEPTUAL = ["Contrato", "Engine", "Orquestador", "Ejecución", "Evaluación",
                     "Generación de alerta", "Persistencia"]

layout = html.Div(className="page", children=[
    page_header("Sentinel Alerts", "Análisis funcional y técnico de los motores de alertamiento.",
                 period_id="page-header-period"),

    html.Div([
        kpi_card("sen-kpi-total", "Actividades", "bi bi-list-check"),
        kpi_card("sen-kpi-horas", "Horas invertidas", "bi bi-clock-history"),
        kpi_card("sen-kpi-completadas", "Completadas", "bi bi-check2-circle", tone="tone-good",
                  context_id="sen-kpi-completadas-ctx"),
        kpi_card("sen-kpi-bloqueadas", "Bloqueadas", "bi bi-exclamation-triangle",
                  icon_id="sen-kpi-bloqueadas-icon", tone="tone-good"),
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
])


@dash.callback(
    Output("sen-kpi-total", "children"),
    Output("sen-kpi-horas", "children"),
    Output("sen-kpi-completadas", "children"), Output("sen-kpi-completadas-ctx", "children"),
    Output("sen-kpi-bloqueadas", "children"), Output("sen-kpi-bloqueadas-icon", "className"),
    Output("sen-g-evolucion", "figure"),
    Output("sen-g-estado", "figure"),
    Output("sen-g-temas", "figure"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_sentinel(store_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en seguimiento.xlsx")
        return "0", "0.0 h", "0", "0% del total", "0", "kpi-icon tone-good", empty, empty, empty

    base = df[df["proyecto"] == "Sentinel Alerts"]
    filtered = apply_all_filters(base, start_date, end_date)

    total = len(filtered)
    horas = filtered["horas"].fillna(0).sum()
    completadas = int(filtered["estado"].eq("Completado").sum())
    bloqueadas = int(filtered["estado"].eq("Bloqueado").sum())
    pct_completadas = (completadas / total * 100) if total else 0
    bloqueadas_icon = "kpi-icon tone-good" if bloqueadas == 0 else "kpi-icon tone-critical"

    fig_evolucion = charts.fig_evolucion_semanal(filtered)
    fig_estado = charts.fig_donut_estado(filtered)
    fig_temas = charts.fig_barras_horas(filtered, "tema", color=ACCENT, top_n=8)

    return (str(total), f"{horas:.1f} h", str(completadas), f"{pct_completadas:.0f}% del total",
            str(bloqueadas), bloqueadas_icon, fig_evolucion, fig_estado, fig_temas)
