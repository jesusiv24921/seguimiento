"""Análisis — cada visual responde una pregunta concreta sobre dónde va el tiempo."""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

import charts
from components import chart_card, page_header
from data_store import apply_all_filters, df_from_store

dash.register_page(__name__, path="/analisis", name="Análisis", title="Análisis")

layout = html.Div(className="page", children=[
    page_header("Análisis", "Distribución del tiempo por proyecto, fecha, categoría y tipo de actividad.",
                 period_id="page-header-period"),

    chart_card([
        html.Div([html.I(className="bi bi-bar-chart"), "Horas por proyecto"], className="section-title"),
        html.Div("¿Dónde se concentran mis horas: Sentinel Alerts, New Opps o transversal?",
                  className="section-caption"),
        dcc.Loading(type="circle", children=dcc.Graph(id="ana-g-proyecto", config={"displayModeBar": False, "responsive": True})),
    ]),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-calendar-week"), "Actividades por día"], className="section-title"),
            html.Div("¿Qué tan seguido registro trabajo?", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="ana-g-act-dia", config={"displayModeBar": False, "responsive": True})),
        ]), lg=6, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-clock-history"), "Horas por día"], className="section-title"),
            html.Div("¿Qué días concentro más tiempo de trabajo?", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="ana-g-horas-dia", config={"displayModeBar": False, "responsive": True})),
        ]), lg=6, className="mb-3"),
    ]),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-tags"), "Actividades por categoría"], className="section-title"),
            html.Div("¿En qué tipo de trabajo temático estoy invirtiendo más actividades?",
                      className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="ana-g-categoria", config={"displayModeBar": False, "responsive": True})),
        ]), lg=6, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-diagram-3"), "Actividades por tipo"], className="section-title"),
            html.Div("¿Cuánto de mi trabajo es análisis vs. reuniones vs. documentación?",
                      className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="ana-g-tipo", config={"displayModeBar": False, "responsive": True})),
        ]), lg=6, className="mb-3"),
    ]),
])


@dash.callback(
    Output("ana-g-proyecto", "figure"),
    Output("ana-g-act-dia", "figure"),
    Output("ana-g-horas-dia", "figure"),
    Output("ana-g-categoria", "figure"),
    Output("ana-g-tipo", "figure"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_analisis(store_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en seguimiento.xlsx")
        return empty, empty, empty, empty, empty

    filtered = apply_all_filters(df, start_date, end_date)

    fig_proyecto = charts.fig_horas_por_proyecto_comparativa(filtered)
    fig_act_dia = charts.fig_actividades_por_dia(filtered)
    fig_horas_dia = charts.fig_horas_por_dia(filtered)
    fig_categoria = charts.fig_barras_actividades(filtered, "categoria", color="#eb6834", top_n=8)
    fig_tipo = charts.fig_barras_actividades(filtered, "tipo_actividad")

    return fig_proyecto, fig_act_dia, fig_horas_dia, fig_categoria, fig_tipo
