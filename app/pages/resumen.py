"""Resumen ejecutivo — responde '¿qué he hecho y cómo ha evolucionado mi trabajo?'."""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, dcc, html

import charts
import data as data_mod
from components import badge_estado, badge_proyecto, chart_card, empty_state, kpi_card, page_header, success_state
from data_store import apply_all_filters, df_from_store

dash.register_page(__name__, path="/", name="Resumen ejecutivo", title="Resumen ejecutivo")

layout = html.Div(className="page", children=[
    page_header("Resumen ejecutivo", "Actividades y evolución del trabajo desde tu ingreso",
                 period_id="page-header-period"),

    html.Div([
        kpi_card("res-kpi-total", "Actividades", "bi bi-list-check", context_id="res-kpi-total-ctx"),
        kpi_card("res-kpi-horas", "Horas registradas", "bi bi-clock-history", context_id="res-kpi-horas-ctx"),
        kpi_card("res-kpi-completadas", "Completadas", "bi bi-check2-circle", tone="tone-good",
                  context_id="res-kpi-completadas-ctx"),
        kpi_card("res-kpi-progreso", "En progreso", "bi bi-arrow-repeat", context_id="res-kpi-progreso-ctx"),
        kpi_card("res-kpi-bloqueadas", "Bloqueadas", "bi bi-exclamation-triangle",
                  icon_id="res-kpi-bloqueadas-icon", tone="tone-good", context_id="res-kpi-bloqueadas-ctx"),
        kpi_card("res-kpi-proyectos", "Proyectos activos", "bi bi-folder2", context_id="res-kpi-proyectos-ctx"),
    ], className="kpi-grid"),

    html.Div([
        html.Span(id="res-stat-semana", className="header-stat"),
        html.Span(id="res-stat-dias-habiles", className="header-stat"),
    ], className="header-stats-row"),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-pie-chart"), "Distribución del trabajo"], className="section-title"),
            html.Div("Dónde se concentran las horas registradas.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="res-g-proyecto", config={"displayModeBar": False, "responsive": True})),
        ]), lg=5, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-graph-up-arrow"), "Evolución temporal"], className="section-title"),
            html.Div("Horas invertidas cada semana, por proyecto.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="res-g-evolucion", config={"displayModeBar": False, "responsive": True})),
        ]), lg=7, className="mb-3"),
    ]),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-flag"), "Estado de las actividades"], className="section-title"),
            html.Div("Completado, en progreso y bloqueado.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="res-g-estado", config={"displayModeBar": False, "responsive": True})),
        ]), lg=5, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-exclamation-triangle"), "Bloqueos y pendientes"],
                      className="section-title"),
            html.Div("Actividades bloqueadas en el periodo seleccionado.", className="section-caption"),
            html.Div(id="res-bloqueos"),
        ]), lg=7, className="mb-3"),
    ]),
])


@dash.callback(
    Output("res-kpi-total", "children"), Output("res-kpi-total-ctx", "children"),
    Output("res-kpi-horas", "children"), Output("res-kpi-horas-ctx", "children"),
    Output("res-kpi-completadas", "children"), Output("res-kpi-completadas-ctx", "children"),
    Output("res-kpi-progreso", "children"), Output("res-kpi-progreso-ctx", "children"),
    Output("res-kpi-bloqueadas", "children"), Output("res-kpi-bloqueadas-ctx", "children"),
    Output("res-kpi-bloqueadas-icon", "className"),
    Output("res-kpi-proyectos", "children"), Output("res-kpi-proyectos-ctx", "children"),
    Output("res-stat-semana", "children"),
    Output("res-stat-dias-habiles", "children"),
    Output("res-g-proyecto", "figure"),
    Output("res-g-evolucion", "figure"),
    Output("res-g-estado", "figure"),
    Output("res-bloqueos", "children"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_resumen(store_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en seguimiento.xlsx")
        return ("0", "Total registradas", "0.0 h", "Según horarios registrados",
                "0", "0.0% del total", "0", "Actividades en curso", "0", "Sin bloqueos",
                "kpi-icon tone-good", "0", "Con actividad en el periodo", "", "",
                empty, empty, empty, empty_state("Sin datos disponibles."))

    filtered = apply_all_filters(df, start_date, end_date)

    total = len(filtered)
    horas = filtered["horas"].fillna(0).sum()
    completadas = int(filtered["estado"].eq("Completado").sum())
    progreso = int(filtered["estado"].eq("En progreso").sum())
    bloqueadas = int(filtered["estado"].eq("Bloqueado").sum())
    proyectos_activos = filtered.loc[filtered["proyecto"] != "Transversal", "proyecto"].nunique()

    pct_completadas = (completadas / total * 100) if total else 0.0
    bloqueadas_icon = "kpi-icon tone-good" if bloqueadas == 0 else "kpi-icon tone-critical"
    bloqueadas_ctx = "Sin bloqueos" if bloqueadas == 0 else "Requieren atención"

    hoy = pd.Timestamp.now().normalize()
    inicio_semana = hoy - pd.Timedelta(days=hoy.weekday())
    fin_semana = inicio_semana + pd.Timedelta(days=6)
    horas_semana = df.loc[(df["fecha_inicio"] >= inicio_semana) & (df["fecha_inicio"] <= fin_semana),
                            "horas"].fillna(0).sum()
    stat_semana = [html.I(className="bi bi-calendar-week"), f" {horas_semana:.1f} h esta semana"]

    fecha_ingreso = df["fecha_inicio"].min().date()
    n_dias, _ = data_mod.business_days_worked(fecha_ingreso, pd.Timestamp.now().date())
    stat_dias = [html.I(className="bi bi-briefcase"), f" {n_dias} días hábiles desde el ingreso"]

    fig_proyecto = charts.fig_donut_proyecto(filtered)
    fig_evolucion = charts.fig_evolucion_semanal(filtered)
    fig_estado = charts.fig_donut_estado(filtered)

    bloqueos_df = filtered[filtered["estado"] == "Bloqueado"]
    if bloqueos_df.empty:
        bloqueos_ui = success_state("No existen actividades bloqueadas en el periodo seleccionado.")
    else:
        cards = []
        for _, r in bloqueos_df.sort_values("fecha_inicio", ascending=False).iterrows():
            cards.append(html.Div(className="blocker-card", children=[
                html.Div([html.I(className="bi bi-exclamation-octagon-fill"), badge_proyecto(r["proyecto"])],
                          className="blocker-card-head"),
                html.Div(r["tema"] or r["actividad"], className="blocker-card-title"),
                html.Div(r["resultado"] or "Sin descripción de resultado.", className="blocker-card-body"),
                badge_estado(r["estado"]),
            ]))
        bloqueos_ui = html.Div(cards, className="blocker-list")

    return (str(total), "Total registradas", f"{horas:.1f} h", "Según horarios registrados",
            str(completadas), f"{pct_completadas:.1f}% del total", str(progreso), "Actividades en curso",
            str(bloqueadas), bloqueadas_ctx, bloqueadas_icon,
            str(proyectos_activos), "Con actividad en el periodo",
            stat_semana, stat_dias,
            fig_proyecto, fig_evolucion, fig_estado, bloqueos_ui)
