"""Actividades — histórico completo, explorable con orden/filtro/exportación."""
from __future__ import annotations

import datetime as dt
import re

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, dash_table, dcc, html

import data as data_mod
from components import chart_card, page_header
from data_store import apply_all_filters, df_from_store, df_to_store, lookups_from_store
from theme import ESTADO_PILL, GRID, INK_MUTED, INK_PRIMARY, PRIORIDAD_PILL

dash.register_page(__name__, path="/actividades", name="Actividades", title="Actividades")

ESTADOS_FORM = ["Bloqueado", "Completado", "En progreso"]
PRIORIDADES_FORM = ["Alta", "Media", "Baja"]
_HORA_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _campo(label: str, icon: str, component) -> html.Div:
    return html.Div([
        html.Div([html.I(className=icon), label], className="filter-label"),
        component,
    ], className="mb-3")


nueva_actividad_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("Nueva actividad"), close_button=True),
    dbc.ModalBody([
        html.Div(id="act-form-error"),
        dbc.Row([
            dbc.Col(_campo("Fecha", "bi bi-calendar3",
                            dcc.DatePickerSingle(id="act-form-fecha", display_format="DD/MM/YYYY",
                                                   date=dt.date.today(), className="w-100")), md=4),
            dbc.Col(_campo("Hora inicio (HH:MM)", "bi bi-clock",
                            dbc.Input(id="act-form-hora-inicio", type="text", placeholder="09:00")), md=4),
            dbc.Col(_campo("Hora fin (HH:MM)", "bi bi-clock",
                            dbc.Input(id="act-form-hora-fin", type="text", placeholder="10:30")), md=4),
        ]),
        dbc.Row([
            dbc.Col(_campo("Proyecto", "bi bi-folder2",
                            dcc.Dropdown(id="act-form-proyecto", placeholder="Transversal (sin proyecto)")), md=4),
            dbc.Col(_campo("Tipo de actividad", "bi bi-diagram-3",
                            dcc.Dropdown(id="act-form-tipo", placeholder="Selecciona un tipo")), md=4),
            dbc.Col(_campo("Categoría", "bi bi-tags",
                            dcc.Dropdown(id="act-form-categoria", placeholder="Sin categoría")), md=4),
        ]),
        _campo("Actividad", "bi bi-card-text", dbc.Input(id="act-form-titulo", type="text",
                placeholder="Título breve de la actividad")),
        _campo("Tema", "bi bi-bookmark", dbc.Input(id="act-form-tema", type="text", placeholder="Tema")),
        _campo("Descripción", "bi bi-text-paragraph",
                dbc.Textarea(id="act-form-descripcion", placeholder="Qué se hizo y por qué.", style={"height": "80px"})),
        _campo("Resultado", "bi bi-check2-square",
                dbc.Textarea(id="act-form-resultado", placeholder="Qué se obtuvo.", style={"height": "70px"})),
        dbc.Row([
            dbc.Col(_campo("Estado", "bi bi-flag",
                            dcc.Dropdown(id="act-form-estado", options=ESTADOS_FORM, value="Completado",
                                          clearable=False)), md=6),
            dbc.Col(_campo("Prioridad", "bi bi-exclamation-circle",
                            dcc.Dropdown(id="act-form-prioridad", options=PRIORIDADES_FORM, value="Media",
                                          clearable=False)), md=6),
        ]),
        _campo("Motor (opcional)", "bi bi-cpu", dbc.Input(id="act-form-motor", type="text", placeholder="")),
        _campo("Observaciones (opcional)", "bi bi-chat-left-text",
                dbc.Textarea(id="act-form-observaciones", style={"height": "60px"})),
    ]),
    dbc.ModalFooter([
        dbc.Button("Cancelar", id="btn-cancelar-actividad", className="btn-cal-nav", n_clicks=0),
        dbc.Button([html.I(className="bi bi-check2"), "Guardar actividad"],
                    id="btn-guardar-actividad", className="btn-refresh", n_clicks=0),
    ]),
], id="modal-nueva-actividad", is_open=False, size="lg", scrollable=True)

act_toast = dbc.Toast(
    id="act-toast", header="Actividades", is_open=False, dismissable=True, duration=6000,
    style={"position": "fixed", "top": 20, "right": 20, "zIndex": 999, "minWidth": "320px"},
)

layout = html.Div(className="page", children=[
    page_header("Actividades", "Registro detallado de actividades desarrolladas.",
                 period_id="page-header-period"),
    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-table"), "Histórico de actividades"], className="section-title"),
            dbc.Button([html.I(className="bi bi-plus-lg"), "Nueva actividad"],
                        id="btn-nueva-actividad", className="btn-refresh ms-auto", n_clicks=0),
        ], style={"justifyContent": "space-between", "alignItems": "center"}),
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
    nueva_actividad_modal,
    act_toast,
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


# --------------------------------------------------------------------------
# Opciones de los dropdowns del formulario (Proyecto / Tipo / Categoría),
# tomadas de los catálogos reales del Excel — así si se agrega un tipo o
# categoría nueva en PROYECTOS/TIPOS_ACTIVIDAD/CATEGORIAS, aparece sola.
# --------------------------------------------------------------------------
@dash.callback(
    Output("act-form-proyecto", "options"),
    Output("act-form-tipo", "options"),
    Output("act-form-categoria", "options"),
    Input("store-lookups", "data"),
)
def update_form_options(lookups_json):
    lookups = lookups_from_store(lookups_json)
    proyectos = [{"label": r["proyecto"], "value": r["proyecto_id"]} for r in lookups["proyectos"]]
    tipos = [{"label": r["tipo_actividad"], "value": r["tipo_actividad_id"]} for r in lookups["tipos"]]
    categorias = [{"label": r["categoria"], "value": r["categoria_id"]} for r in lookups["categorias"]]
    return proyectos, tipos, categorias


def _campos_vacios():
    return (dt.date.today(), "", "", None, None, None, "", "", "", "",
            "Completado", "Media", "", "")


@dash.callback(
    Output("modal-nueva-actividad", "is_open"),
    Output("act-form-error", "children"),
    Output("act-form-fecha", "date"),
    Output("act-form-hora-inicio", "value"),
    Output("act-form-hora-fin", "value"),
    Output("act-form-proyecto", "value"),
    Output("act-form-tipo", "value"),
    Output("act-form-categoria", "value"),
    Output("act-form-titulo", "value"),
    Output("act-form-tema", "value"),
    Output("act-form-descripcion", "value"),
    Output("act-form-resultado", "value"),
    Output("act-form-estado", "value"),
    Output("act-form-prioridad", "value"),
    Output("act-form-motor", "value"),
    Output("act-form-observaciones", "value"),
    Input("btn-nueva-actividad", "n_clicks"),
    prevent_initial_call=True,
)
def open_nueva_actividad(_n_clicks):
    return (True, None, *_campos_vacios())


@dash.callback(
    Output("modal-nueva-actividad", "is_open", allow_duplicate=True),
    Input("btn-cancelar-actividad", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_nueva_actividad(_n_clicks):
    return False


@dash.callback(
    Output("store-data", "data", allow_duplicate=True),
    Output("modal-nueva-actividad", "is_open", allow_duplicate=True),
    Output("act-form-error", "children", allow_duplicate=True),
    Output("act-toast", "children"),
    Output("act-toast", "icon"),
    Output("act-toast", "is_open"),
    Input("btn-guardar-actividad", "n_clicks"),
    State("act-form-fecha", "date"),
    State("act-form-hora-inicio", "value"),
    State("act-form-hora-fin", "value"),
    State("act-form-proyecto", "value"),
    State("act-form-tipo", "value"),
    State("act-form-categoria", "value"),
    State("act-form-titulo", "value"),
    State("act-form-tema", "value"),
    State("act-form-descripcion", "value"),
    State("act-form-resultado", "value"),
    State("act-form-estado", "value"),
    State("act-form-prioridad", "value"),
    State("act-form-motor", "value"),
    State("act-form-observaciones", "value"),
    prevent_initial_call=True,
)
def guardar_nueva_actividad(_n_clicks, fecha, hora_inicio_txt, hora_fin_txt, proyecto_id, tipo_id,
                             categoria_id, titulo, tema, descripcion, resultado, estado, prioridad,
                             motor, observaciones):
    def error(msg):
        return (dash.no_update, True, html.Div(msg, className="section-caption", style={"color": "#a52323"}),
                dash.no_update, dash.no_update, dash.no_update)

    if not fecha:
        return error("Selecciona una fecha.")
    if not hora_inicio_txt or not _HORA_RE.match(hora_inicio_txt.strip()):
        return error("La hora de inicio debe tener formato HH:MM (ej. 09:00).")
    if not hora_fin_txt or not _HORA_RE.match(hora_fin_txt.strip()):
        return error("La hora de fin debe tener formato HH:MM (ej. 10:30).")

    h_ini = dt.datetime.strptime(hora_inicio_txt.strip(), "%H:%M").time()
    h_fin = dt.datetime.strptime(hora_fin_txt.strip(), "%H:%M").time()
    if h_fin <= h_ini:
        return error("La hora de fin debe ser posterior a la hora de inicio.")
    if not tipo_id:
        return error("Selecciona un tipo de actividad.")
    if not titulo or not titulo.strip():
        return error("Escribe un título para la actividad.")
    if not tema or not tema.strip():
        return error("Escribe el tema.")
    if not descripcion or not descripcion.strip():
        return error("Escribe una descripción.")
    if not resultado or not resultado.strip():
        return error("Escribe el resultado.")
    if not estado or not prioridad:
        return error("Selecciona estado y prioridad.")

    ok, msg = data_mod.add_actividad(
        fecha_inicio=dt.date.fromisoformat(fecha), hora_inicio=h_ini, hora_fin=h_fin,
        proyecto_id=proyecto_id, tipo_actividad_id=tipo_id, categoria_id=categoria_id,
        actividad=titulo.strip(), descripcion=descripcion.strip(), tema=tema.strip(),
        resultado=resultado.strip(), estado=estado, prioridad=prioridad,
        motor=(motor or "").strip() or None, observaciones=(observaciones or "").strip() or None,
    )
    if not ok:
        return error(msg)

    nuevo_df = data_mod.load_data()["actividades"]
    return df_to_store(nuevo_df), False, None, f"✓ {msg}", "success", True
