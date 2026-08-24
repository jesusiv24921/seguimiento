"""Actividades — histórico completo, explorable con orden/filtro/exportación."""
from __future__ import annotations

import dash
import pandas as pd
from dash import Input, Output, dash_table, html

from components import chart_card, page_header
from data_store import apply_all_filters, df_from_store
from theme import ESTADO_PILL, GRID, INK_MUTED, INK_PRIMARY, PRIORIDAD_PILL

dash.register_page(__name__, path="/actividades", name="Actividades", title="Actividades")

layout = html.Div(className="page", children=[
    page_header("Actividades", "Registro detallado de actividades desarrolladas.",
                 period_id="page-header-period"),
    chart_card([
        html.Div([html.I(className="bi bi-table"), "Histórico de actividades"], className="section-title"),
        html.Div("Haz clic en una fila para ver el detalle completo. Ordena, filtra por columna o exporta a CSV "
                  "con los controles de la tabla.", className="section-caption"),
        dash_table.DataTable(
            id="act-tabla",
            columns=[
                {"name": "ID", "id": "actividad_id"},
                {"name": "Fecha", "id": "fecha_txt"},
                {"name": "Horario", "id": "horario_txt"},
                {"name": "Duración", "id": "horas_txt"},
                {"name": "Proyecto", "id": "proyecto"},
                {"name": "Actividad", "id": "actividad"},
                {"name": "Tema", "id": "tema"},
                {"name": "Estado", "id": "estado"},
                {"name": "Prioridad", "id": "prioridad"},
            ],
            page_size=15,
            sort_action="native",
            filter_action="native",
            export_format="csv",
            export_headers="display",
            style_as_list_view=True,
            style_table={"overflowX": "auto"},
            style_cell={"fontFamily": "Inter, system-ui, sans-serif", "fontSize": "0.85rem",
                        "padding": "10px 12px", "textAlign": "left", "whiteSpace": "normal",
                        "height": "auto", "border": "none", "cursor": "pointer"},
            style_header={"backgroundColor": "#f7f7f4", "fontWeight": "700", "color": INK_MUTED,
                          "border": "none", "borderBottom": f"1px solid {GRID}"},
            style_data={"borderBottom": f"1px solid {GRID}", "color": INK_PRIMARY},
            style_data_conditional=(
                [{"if": {"row_index": "odd"}, "backgroundColor": "#fbfbf9"}]
                + [{"if": {"filter_query": f'{{estado}} = "{k}"', "column_id": "estado"},
                    "backgroundColor": v["bg"], "color": v["fg"], "fontWeight": "600"} for k, v in ESTADO_PILL.items()]
                + [{"if": {"filter_query": f'{{prioridad}} = "{k}"', "column_id": "prioridad"},
                    "backgroundColor": v["bg"], "color": v["fg"], "fontWeight": "600"} for k, v in PRIORIDAD_PILL.items()]
            ),
            style_cell_conditional=[{"if": {"column_id": "actividad"}, "minWidth": "200px"},
                                     {"if": {"column_id": "tema"}, "minWidth": "180px"},
                                     {"if": {"column_id": "actividad_id"}, "maxWidth": "60px"}],
        ),
    ]),
])


@dash.callback(
    Output("act-tabla", "data"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_actividades(store_json, start_date, end_date):
    df = df_from_store(store_json)
    if df.empty:
        return []

    filtered = apply_all_filters(df, start_date, end_date)

    tabla = filtered.copy()
    tabla["fecha_txt"] = tabla["fecha_inicio"].dt.strftime("%d/%m/%Y")
    tabla["horario_txt"] = tabla["hora_inicio_txt"].fillna("—") + " — " + tabla["hora_fin_txt"].fillna("—")
    tabla["horas_txt"] = tabla["horas"].apply(lambda h: f"{h:.1f} h" if pd.notna(h) else "Sin horas registradas")
    tabla = tabla.sort_values("fecha_inicio", ascending=False)
    tabla["id"] = tabla["actividad_id"]

    cols = ["id", "actividad_id", "fecha_txt", "horario_txt", "horas_txt", "proyecto",
            "actividad", "tema", "estado", "prioridad"]
    return tabla[cols].to_dict("records")


@dash.callback(
    Output("store-selected-activity", "data", allow_duplicate=True),
    Input("act-tabla", "active_cell"),
    prevent_initial_call=True,
)
def select_activity_from_table(active_cell):
    if not active_cell:
        return dash.no_update
    return active_cell.get("row_id")
