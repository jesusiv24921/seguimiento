"""Reuniones y Transversales — el trabajo que no fue desarrollo técnico directo."""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, dcc, html

import charts
from components import badge_proyecto, chart_card, kpi_card, page_header
from data_store import apply_all_filters, df_from_store

dash.register_page(__name__, path="/transversales", name="Reuniones y Transversales", title="Reuniones y Transversales")

layout = html.Div(className="page", children=[
    page_header("Reuniones y Transversales",
                 "Inducción, capacitaciones, reuniones y configuración de herramientas — "
                 "el trabajo que sostiene el desarrollo técnico pero no es desarrollo técnico en sí.",
                 period_id="page-header-period"),

    html.Div([
        kpi_card("trv-kpi-total", "Actividades", "bi bi-list-check"),
        kpi_card("trv-kpi-horas", "Horas invertidas", "bi bi-clock-history"),
        kpi_card("trv-kpi-reuniones", "Reuniones", "bi bi-people", context_id="trv-kpi-reuniones-ctx"),
    ], className="kpi-grid"),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-bar-chart-steps"), "Por tipo de actividad"],
                      className="section-title"),
            html.Div("Capacitación, reunión, soporte y demás — agrupado por el campo real "
                      "tipo_actividad del Excel.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="trv-g-tipo", config={"displayModeBar": False})),
        ]), lg=6, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-graph-up-arrow"), "Evolución en el tiempo"], className="section-title"),
            html.Div("Horas invertidas cada semana en actividades transversales y reuniones.",
                      className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="trv-g-evolucion", config={"displayModeBar": False})),
        ]), lg=6, className="mb-3"),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-list-ul"), "Detalle"], className="section-title"),
        html.Div(id="trv-lista"),
    ]),
])


@dash.callback(
    Output("trv-kpi-total", "children"),
    Output("trv-kpi-horas", "children"),
    Output("trv-kpi-reuniones", "children"), Output("trv-kpi-reuniones-ctx", "children"),
    Output("trv-g-tipo", "figure"),
    Output("trv-g-evolucion", "figure"),
    Output("trv-lista", "children"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_transversales(store_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en seguimiento.xlsx")
        return "0", "0.0 h", "0", "", empty, empty, html.Div()

    base = df[(df["proyecto"] == "Transversal") | (df["tipo_actividad"] == "Reunión")]
    filtered = apply_all_filters(base, start_date, end_date)

    total = len(filtered)
    horas = filtered["horas"].fillna(0).sum()
    reuniones = int(filtered["tipo_actividad"].eq("Reunión").sum())
    reuniones_ctx = "Del total de actividades" if total else ""

    fig_tipo = charts.fig_barras_actividades(filtered, "tipo_actividad")
    fig_evolucion = charts.fig_evolucion_semanal(filtered)

    if filtered.empty:
        lista = html.Div("No hay actividades transversales para los filtros seleccionados.",
                           className="section-caption")
    else:
        rows = []
        for _, r in filtered.sort_values("fecha_inicio", ascending=False).iterrows():
            horas_r = 0.0 if pd.isna(r["horas"]) else r["horas"]
            rows.append(html.Div(className="cal-detail-row", children=[
                html.Div(className="cal-detail-body", children=[
                    html.Div(r["actividad"], className="cal-detail-title"),
                    html.Div(f"{r['fecha_inicio'].strftime('%d/%m/%Y')} · {r['tipo_actividad']} · {horas_r:.1f} h",
                              className="cal-detail-meta"),
                ]),
                badge_proyecto(r["proyecto"]),
            ]))
        lista = html.Div(rows, className="cal-detail-list")

    return str(total), f"{horas:.1f} h", str(reuniones), reuniones_ctx, fig_tipo, fig_evolucion, lista
