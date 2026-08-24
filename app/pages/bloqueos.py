"""Bloqueos y pendientes — qué está frenado y por qué, sin inventar soluciones."""
from __future__ import annotations

import dash
from dash import Input, Output, html

from components import badge_proyecto, chart_card, kpi_card, page_header, success_state
from data_store import apply_all_filters, df_from_store

dash.register_page(__name__, path="/bloqueos", name="Bloqueos y pendientes", title="Bloqueos y pendientes")

layout = html.Div(className="page", children=[
    page_header("Bloqueos y pendientes", "Qué está frenado, en qué proyecto y por qué.",
                 period_id="page-header-period"),

    html.Div([
        kpi_card("blq-kpi-total", "Total bloqueos", "bi bi-exclamation-triangle",
                  icon_id="blq-kpi-total-icon", tone="tone-good"),
        kpi_card("blq-kpi-sentinel", "Sentinel Alerts", "bi bi-shield-check"),
        kpi_card("blq-kpi-newopps", "New Opps", "bi bi-rocket-takeoff"),
    ], className="kpi-grid"),

    chart_card([
        html.Div([html.I(className="bi bi-list-ul"), "Detalle de bloqueos"], className="section-title"),
        html.Div(id="blq-lista"),
    ]),
])


@dash.callback(
    Output("blq-kpi-total", "children"), Output("blq-kpi-total-icon", "className"),
    Output("blq-kpi-sentinel", "children"),
    Output("blq-kpi-newopps", "children"),
    Output("blq-lista", "children"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_bloqueos(store_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        return "0", "kpi-icon tone-good", "0", "0", success_state("Sin datos disponibles.")

    bloqueados = df[df["estado"] == "Bloqueado"]
    filtered = apply_all_filters(bloqueados, start_date, end_date)

    total = len(filtered)
    n_sentinel = int(filtered["proyecto"].eq("Sentinel Alerts").sum())
    n_newopps = int(filtered["proyecto"].eq("New Opps").sum())
    icon_tone = "kpi-icon tone-good" if total == 0 else "kpi-icon tone-critical"

    if filtered.empty:
        lista = success_state("No existen actividades bloqueadas en el periodo seleccionado.")
    else:
        cards = []
        for _, r in filtered.sort_values("fecha_inicio", ascending=False).iterrows():
            cards.append(html.Div(className="blocker-card", children=[
                html.Div([html.I(className="bi bi-exclamation-octagon-fill"), badge_proyecto(r["proyecto"])],
                          className="blocker-card-head"),
                html.Div(r["tema"] or r["actividad"], className="blocker-card-title"),
                html.Div(f"Problema: {r['resultado'] or 'No especificado en los datos.'}",
                          className="blocker-card-body"),
                html.Div(f"Fecha: {r['fecha_inicio'].strftime('%d/%m/%Y')}", className="blocker-card-meta"),
            ]))
        lista = html.Div(cards, className="blocker-list")

    return str(total), icon_tone, str(n_sentinel), str(n_newopps), lista
