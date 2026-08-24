"""New Opps — seguimiento del proceso de contextualización y desarrollo."""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

import charts
from components import badge_estado, chart_card, kpi_card, page_header, success_state
from data_store import apply_all_filters, df_from_store
from theme import ACCENT

dash.register_page(__name__, path="/new-opps", name="New Opps", title="New Opps")

layout = html.Div(className="page", children=[
    page_header("New Opps", "Seguimiento del proceso de contextualización y desarrollo.",
                 period_id="page-header-period"),

    html.Div([
        kpi_card("nop-kpi-total", "Actividades", "bi bi-list-check"),
        kpi_card("nop-kpi-horas", "Horas invertidas", "bi bi-clock-history"),
        kpi_card("nop-kpi-completadas", "Completadas", "bi bi-check2-circle", tone="tone-good",
                  context_id="nop-kpi-completadas-ctx"),
        kpi_card("nop-kpi-bloqueadas", "Bloqueadas", "bi bi-exclamation-triangle",
                  icon_id="nop-kpi-bloqueadas-icon", tone="tone-good"),
    ], className="kpi-grid"),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-graph-up-arrow"), "Evolución de horas"], className="section-title"),
            html.Div("Horas invertidas en New Opps, semana a semana.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="nop-g-evolucion", config={"displayModeBar": False, "responsive": True})),
        ]), lg=7, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-flag"), "Estado del trabajo"], className="section-title"),
            html.Div("Completado, en progreso, bloqueado.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="nop-g-estado", config={"displayModeBar": False, "responsive": True})),
        ]), lg=5, className="mb-3"),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-diagram-3"), "Tipo de actividad"], className="section-title"),
        html.Div("Reuniones, análisis, soporte y demás — dónde se concentra el trabajo de New Opps.",
                  className="section-caption"),
        dcc.Loading(type="circle", children=dcc.Graph(id="nop-g-tipo", config={"displayModeBar": False, "responsive": True})),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-exclamation-octagon"), "Bloqueos técnicos"], className="section-title"),
        html.Div("Impedimentos técnicos registrados, tal como están en los datos — sin inventar soluciones.",
                  className="section-caption"),
        html.Div(id="nop-bloqueos"),
    ]),
])


@dash.callback(
    Output("nop-kpi-total", "children"),
    Output("nop-kpi-horas", "children"),
    Output("nop-kpi-completadas", "children"), Output("nop-kpi-completadas-ctx", "children"),
    Output("nop-kpi-bloqueadas", "children"), Output("nop-kpi-bloqueadas-icon", "className"),
    Output("nop-g-evolucion", "figure"),
    Output("nop-g-estado", "figure"),
    Output("nop-g-tipo", "figure"),
    Output("nop-bloqueos", "children"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_new_opps(store_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en seguimiento.xlsx")
        return ("0", "0.0 h", "0", "0% del total", "0", "kpi-icon tone-good",
                empty, empty, empty, success_state("Sin datos."))

    base = df[df["proyecto"] == "New Opps"]
    filtered = apply_all_filters(base, start_date, end_date)

    total = len(filtered)
    horas = filtered["horas"].fillna(0).sum()
    completadas = int(filtered["estado"].eq("Completado").sum())
    bloqueadas = int(filtered["estado"].eq("Bloqueado").sum())
    pct_completadas = (completadas / total * 100) if total else 0
    bloqueadas_icon = "kpi-icon tone-good" if bloqueadas == 0 else "kpi-icon tone-critical"

    fig_evolucion = charts.fig_evolucion_semanal(filtered)
    fig_estado = charts.fig_donut_estado(filtered)
    fig_tipo = charts.fig_barras_horas(filtered, "tipo_actividad", color=ACCENT)

    bloqueos_df = filtered[filtered["estado"] == "Bloqueado"]
    if bloqueos_df.empty:
        bloqueos_ui = success_state("No existen bloqueos técnicos registrados en el periodo seleccionado.")
    else:
        cards = []
        for _, r in bloqueos_df.sort_values("fecha_inicio", ascending=False).iterrows():
            cards.append(html.Div(className="blocker-card", children=[
                html.Div([html.I(className="bi bi-exclamation-octagon-fill"), r["tema"] or r["actividad"]],
                          className="blocker-card-head"),
                html.Div(f"Problema: {r['resultado'] or 'No especificado en los datos.'}",
                          className="blocker-card-body"),
                html.Div(f"Observaciones: {r['observaciones'] or 'Sin observaciones registradas.'}",
                          className="blocker-card-body"),
                html.Div(f"Fecha: {r['fecha_inicio'].strftime('%d/%m/%Y')}", className="blocker-card-meta"),
                badge_estado(r["estado"]),
            ]))
        bloqueos_ui = html.Div(cards, className="blocker-list")

    return (str(total), f"{horas:.1f} h", str(completadas), f"{pct_completadas:.0f}% del total",
            str(bloqueadas), bloqueadas_icon, fig_evolucion, fig_estado, fig_tipo, bloqueos_ui)
