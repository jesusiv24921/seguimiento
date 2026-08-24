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
    dbc.ModalHeader(dbc.ModalTitle(html.Span("Nueva actividad", id="act-form-modal-title")), close_button=True),
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

eliminar_actividad_modal = dbc.Modal([
    dbc.ModalHeader(dbc.ModalTitle("¿Eliminar esta actividad?"), close_button=True),
    dbc.ModalBody(id="act-eliminar-modal-body"),
    dbc.ModalFooter([
        dbc.Button("Cancelar", id="btn-cancelar-eliminar-actividad", className="btn-cal-nav", n_clicks=0),
        dbc.Button([html.I(className="bi bi-trash"), "Eliminar definitivamente"],
                    id="btn-confirmar-eliminar-actividad", className="btn-refresh", n_clicks=0),
    ]),
], id="modal-eliminar-actividad", is_open=False)

layout = html.Div(className="page", children=[
    page_header("Actividades", "Registro detallado de actividades desarrolladas.",
                 period_id="page-header-period"),
    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-table"), "Histórico de actividades"], className="section-title"),
            dbc.Button([html.I(className="bi bi-pencil"), "Editar"],
                        id="btn-editar-actividad", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-trash"), "Eliminar"],
                        id="btn-eliminar-actividad", className="btn-refresh", disabled=True),
            html.Div(id="act-selection-msg", className="hal-selection-msg"),
            dbc.Button([html.I(className="bi bi-plus-lg"), "Nueva actividad"],
                        id="btn-nueva-actividad", className="btn-refresh ms-auto", n_clicks=0),
        ], style={"justifyContent": "space-between", "alignItems": "center"}),
        html.Div("Selecciona una fila con la casilla para editarla o eliminarla, o haz clic en cualquier celda "
                  "para ver el detalle completo. Ordena, filtra por columna o exporta a CSV con los controles "
                  "de la tabla.", className="section-caption"),
        dash_table.DataTable(
            id="act-tabla",
            row_selectable="single",
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
    eliminar_actividad_modal,
    act_toast,
    dcc.Store(id="store-actividad-seleccionada"),
    dcc.Store(id="store-actividad-form-mode"),
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


@dash.callback(
    Output("btn-editar-actividad", "disabled"),
    Output("btn-eliminar-actividad", "disabled"),
    Output("act-selection-msg", "children"),
    Output("store-actividad-seleccionada", "data"),
    Input("act-tabla", "selected_rows"),
    State("act-tabla", "data"),
)
def update_actividad_selection(selected_rows, table_data):
    selected_rows = selected_rows or []
    if len(selected_rows) == 0:
        return True, True, "Selecciona una actividad para editar o eliminar.", None
    if len(selected_rows) > 1:
        return True, True, "Selecciona únicamente una actividad para continuar.", None

    idx = selected_rows[0]
    if not table_data or idx >= len(table_data):
        return True, True, "Selecciona una actividad para continuar.", None

    return False, False, "", table_data[idx]["actividad_id"]


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
    Output("modal-nueva-actividad", "is_open", allow_duplicate=True),
    Output("act-form-error", "children", allow_duplicate=True),
    Output("act-form-fecha", "date", allow_duplicate=True),
    Output("act-form-hora-inicio", "value", allow_duplicate=True),
    Output("act-form-hora-fin", "value", allow_duplicate=True),
    Output("act-form-proyecto", "value", allow_duplicate=True),
    Output("act-form-tipo", "value", allow_duplicate=True),
    Output("act-form-categoria", "value", allow_duplicate=True),
    Output("act-form-titulo", "value", allow_duplicate=True),
    Output("act-form-tema", "value", allow_duplicate=True),
    Output("act-form-descripcion", "value", allow_duplicate=True),
    Output("act-form-resultado", "value", allow_duplicate=True),
    Output("act-form-estado", "value", allow_duplicate=True),
    Output("act-form-prioridad", "value", allow_duplicate=True),
    Output("act-form-motor", "value", allow_duplicate=True),
    Output("act-form-observaciones", "value", allow_duplicate=True),
    Output("act-form-modal-title", "children", allow_duplicate=True),
    Output("store-actividad-form-mode", "data", allow_duplicate=True),
    Input("btn-nueva-actividad", "n_clicks"),
    prevent_initial_call=True,
)
def open_nueva_actividad(n_clicks):
    if not n_clicks:
        return (dash.no_update,) * 18
    return (True, None, *_campos_vacios(), "Nueva actividad", None)


@dash.callback(
    Output("modal-nueva-actividad", "is_open", allow_duplicate=True),
    Output("act-form-error", "children", allow_duplicate=True),
    Output("act-form-fecha", "date", allow_duplicate=True),
    Output("act-form-hora-inicio", "value", allow_duplicate=True),
    Output("act-form-hora-fin", "value", allow_duplicate=True),
    Output("act-form-proyecto", "value", allow_duplicate=True),
    Output("act-form-tipo", "value", allow_duplicate=True),
    Output("act-form-categoria", "value", allow_duplicate=True),
    Output("act-form-titulo", "value", allow_duplicate=True),
    Output("act-form-tema", "value", allow_duplicate=True),
    Output("act-form-descripcion", "value", allow_duplicate=True),
    Output("act-form-resultado", "value", allow_duplicate=True),
    Output("act-form-estado", "value", allow_duplicate=True),
    Output("act-form-prioridad", "value", allow_duplicate=True),
    Output("act-form-motor", "value", allow_duplicate=True),
    Output("act-form-observaciones", "value", allow_duplicate=True),
    Output("act-form-modal-title", "children", allow_duplicate=True),
    Output("store-actividad-form-mode", "data", allow_duplicate=True),
    Input("btn-editar-actividad", "n_clicks"),
    State("store-actividad-seleccionada", "data"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def open_editar_actividad(n_clicks, actividad_id, store_json):
    vacio = (dash.no_update,) * 18
    if not n_clicks or not actividad_id:
        return vacio

    df = df_from_store(store_json)
    fila = df[df["actividad_id"] == actividad_id]
    if fila.empty:
        return vacio
    r = fila.iloc[0]

    def _s(v):
        return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    campos = (
        r["fecha_inicio"].date().isoformat(), _s(r["hora_inicio_txt"]), _s(r["hora_fin_txt"]),
        _s(r.get("proyecto_id")) or None, _s(r.get("tipo_actividad_id")) or None, _s(r.get("categoria_id")) or None,
        _s(r["actividad"]), _s(r["tema"]), _s(r["descripcion"]), _s(r["resultado"]),
        r["estado"] if r["estado"] in ESTADOS_FORM else "Completado",
        r["prioridad"] if r["prioridad"] in PRIORIDADES_FORM else "Media",
        _s(r.get("motor")), _s(r.get("observaciones")),
    )
    return (True, None, *campos, f"Editar actividad {actividad_id}", actividad_id)


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
    Output("act-toast", "children", allow_duplicate=True),
    Output("act-toast", "icon", allow_duplicate=True),
    Output("act-toast", "is_open", allow_duplicate=True),
    Input("btn-guardar-actividad", "n_clicks"),
    State("store-actividad-form-mode", "data"),
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
def guardar_nueva_actividad(_n_clicks, modo_edicion, fecha, hora_inicio_txt, hora_fin_txt, proyecto_id, tipo_id,
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

    kwargs = dict(
        fecha_inicio=dt.date.fromisoformat(fecha), hora_inicio=h_ini, hora_fin=h_fin,
        proyecto_id=proyecto_id, tipo_actividad_id=tipo_id, categoria_id=categoria_id,
        actividad=titulo.strip(), descripcion=descripcion.strip(), tema=tema.strip(),
        resultado=resultado.strip(), estado=estado, prioridad=prioridad,
        motor=(motor or "").strip() or None, observaciones=(observaciones or "").strip() or None,
    )
    if modo_edicion:
        ok, msg = data_mod.update_actividad(actividad_id=modo_edicion, **kwargs)
    else:
        ok, msg = data_mod.add_actividad(**kwargs)
    if not ok:
        return error(msg)

    nuevo_df = data_mod.load_data()["actividades"]
    return df_to_store(nuevo_df), False, None, f"✓ {msg}", "success", True


# --------------------------------------------------------------------------
# Eliminar actividad: abrir confirmación / cancelar / confirmar
# --------------------------------------------------------------------------
def _campo_modal(label: str, value: str) -> html.Div:
    return html.Div([
        html.Div(label, className="modal-field-label"),
        html.Div(value, className="modal-field-value"),
    ], className="modal-field")


@dash.callback(
    Output("modal-eliminar-actividad", "is_open"),
    Output("act-eliminar-modal-body", "children"),
    Input("btn-eliminar-actividad", "n_clicks"),
    State("store-actividad-seleccionada", "data"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def open_eliminar_actividad(n_clicks, actividad_id, store_json):
    if not n_clicks or not actividad_id:
        return dash.no_update, dash.no_update
    df = df_from_store(store_json)
    fila = df[df["actividad_id"] == actividad_id]
    if fila.empty:
        return dash.no_update, dash.no_update
    r = fila.iloc[0]
    body = html.Div([
        html.P("Esta acción eliminará la actividad de forma permanente del archivo Excel y no se puede deshacer.",
                className="section-caption", style={"color": "#a52323"}),
        _campo_modal("ID", actividad_id),
        _campo_modal("Actividad", r["actividad"]),
        _campo_modal("Fecha", r["fecha_inicio"].strftime("%d/%m/%Y")),
        _campo_modal("Proyecto", r["proyecto"]),
        _campo_modal("Estado", r["estado"]),
    ])
    return True, body


@dash.callback(
    Output("modal-eliminar-actividad", "is_open", allow_duplicate=True),
    Input("btn-cancelar-eliminar-actividad", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_eliminar_actividad(_n_clicks):
    return False


@dash.callback(
    Output("store-data", "data", allow_duplicate=True),
    Output("modal-eliminar-actividad", "is_open", allow_duplicate=True),
    Output("act-toast", "children", allow_duplicate=True),
    Output("act-toast", "icon", allow_duplicate=True),
    Output("act-toast", "is_open", allow_duplicate=True),
    Input("btn-confirmar-eliminar-actividad", "n_clicks"),
    State("store-actividad-seleccionada", "data"),
    prevent_initial_call=True,
)
def confirmar_eliminar_actividad(_n_clicks, actividad_id):
    if not actividad_id:
        return dash.no_update, False, "No hay ninguna actividad seleccionada.", "danger", True

    ok, msg = data_mod.delete_actividad(actividad_id)
    if ok:
        nuevo_df = data_mod.load_data()["actividades"]
        return df_to_store(nuevo_df), False, f"✓ {msg}", "success", True
    return dash.no_update, False, msg, "danger", True


# --------------------------------------------------------------------------
# Asegura que ningún formulario quede abierto al entrar a la página. Los
# modales solo deben abrirse por un clic explícito en sus botones; esto
# cierra cualquier estado de "abierto" que el navegador pudiera arrastrar
# de una visita anterior a esta misma página en la sesión.
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-nueva-actividad", "is_open", allow_duplicate=True),
    Output("modal-eliminar-actividad", "is_open", allow_duplicate=True),
    Input("url", "pathname"),
    prevent_initial_call=True,
)
def cerrar_modales_al_entrar(pathname):
    if pathname != "/actividades":
        return dash.no_update, dash.no_update
    return False, False
