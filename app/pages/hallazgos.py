"""Hallazgos — seguimiento y cierre de hallazgos de validación de Sentinel Alerts.

Fuente de verdad: la pestaña HALLAZGOS de seguimiento.xlsx (data.load_hallazgos).
Cerrar un hallazgo escribe de verdad en el Excel (data.close_hallazgo) — nunca
solo en memoria — y luego recarga store-hallazgos para que KPIs, gráficos y
tabla reflejen el cambio real.
"""
from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dash_table, dcc, html

import charts
import data as data_mod
from components import chart_card, kpi_card, page_header
from data_store import hallazgos_from_store, hallazgos_to_store, lookups_from_store
from theme import GRID, HALLAZGO_ESTADO_PILL, INK_MUTED, INK_PRIMARY

dash.register_page(__name__, path="/hallazgos", name="Hallazgos", title="Hallazgos")

layout = html.Div(className="page", children=[
    page_header("Hallazgos",
                 "Seguimiento de hallazgos identificados durante la validación de los motores de Sentinel Alerts."),

    html.Div([
        kpi_card("hal-kpi-total", "Hallazgos totales", "bi bi-clipboard-data"),
        kpi_card("hal-kpi-abiertos", "Abiertos", "bi bi-exclamation-circle",
                  icon_id="hal-kpi-abiertos-icon", tone="tone-critical"),
        kpi_card("hal-kpi-revision", "En revisión", "bi bi-search", tone="tone-warning"),
        kpi_card("hal-kpi-cerrados", "Cerrados", "bi bi-check2-circle", tone="tone-good"),
        kpi_card("hal-kpi-cierre", "% Cierre", "bi bi-graph-up-arrow"),
    ], className="kpi-grid"),

    dbc.Row([
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-pie-chart"), "Estado de los hallazgos"], className="section-title"),
            html.Div("Abiertos, en revisión y cerrados.", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="hal-g-estado", config={"displayModeBar": False, "responsive": True})),
        ]), lg=5, className="mb-3"),
        dbc.Col(chart_card([
            html.Div([html.I(className="bi bi-bar-chart"), "Hallazgos por motor"], className="section-title"),
            html.Div("¿Dónde se concentran los principales hallazgos técnicos?", className="section-caption"),
            dcc.Loading(type="circle", children=dcc.Graph(id="hal-g-motor", config={"displayModeBar": False, "responsive": True})),
        ]), lg=7, className="mb-3"),
    ]),

    html.Div(className="filters-panel", children=[
        html.Div([html.I(className="bi bi-sliders"), "Filtros de hallazgos"], className="filters-panel-title"),
        html.Div(className="filters-grid", children=[
            html.Div([
                html.Div([html.I(className="bi bi-cpu"), "Motor"], className="filter-label"),
                dcc.Dropdown(id="hal-f-motor", multi=True, placeholder="Todos"),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                dcc.Dropdown(id="hal-f-estado", multi=True, placeholder="Todos"),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-file-earmark-code"), "Script"], className="filter-label"),
                dcc.Dropdown(id="hal-f-script", multi=True, placeholder="Todos"),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-code-slash"), "Función"], className="filter-label"),
                dcc.Dropdown(id="hal-f-funcion", multi=True, placeholder="Todas"),
            ], className="filter-field"),
        ]),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-list-ul"), "Detalle de hallazgos"], className="section-title"),
        html.Div("Selecciona un hallazgo en la tabla y presiona \"Cerrar hallazgo\" para actualizarlo "
                  "directamente en el Excel.", className="section-caption"),
        html.Div(className="hal-actions-row", children=[
            dbc.Button([html.I(className="bi bi-check2-circle"), "Cerrar hallazgo"],
                        id="btn-cerrar-hallazgo", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-pencil"), "Editar"],
                        id="btn-editar-hallazgo", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-trash"), "Eliminar"],
                        id="btn-eliminar-hallazgo", className="btn-refresh", disabled=True),
            html.Div(id="hal-selection-msg", className="hal-selection-msg"),
            dbc.Button([html.I(className="bi bi-plus-lg"), "Nuevo hallazgo"],
                        id="btn-nuevo-hallazgo", className="btn-refresh ms-auto", n_clicks=0),
        ]),
        dash_table.DataTable(
            id="hal-tabla",
            columns=[
                {"name": "Estado", "id": "Estado"},
                {"name": "Motor", "id": "Motor"},
                {"name": "Script", "id": "Script"},
                {"name": "Función", "id": "Función"},
                {"name": "Descripción", "id": "Descripción"},
            ],
            row_selectable="multi",
            page_size=12,
            sort_action="native",
            filter_action="native",
            style_as_list_view=True,
            style_table={"overflowX": "auto"},
            style_cell={"fontFamily": "Inter, system-ui, sans-serif", "fontSize": "0.85rem",
                        "padding": "10px 12px", "textAlign": "left", "whiteSpace": "normal",
                        "height": "auto", "border": "none"},
            style_header={"backgroundColor": "#f7f7f4", "fontWeight": "700", "color": INK_MUTED,
                          "border": "none", "borderBottom": f"1px solid {GRID}"},
            style_data={"borderBottom": f"1px solid {GRID}", "color": INK_PRIMARY},
            style_data_conditional=(
                [{"if": {"row_index": "odd"}, "backgroundColor": "#fbfbf9"}]
                + [{"if": {"filter_query": f'{{Estado}} = "{k}"', "column_id": "Estado"},
                    "backgroundColor": v["bg"], "color": v["fg"], "fontWeight": "600"}
                   for k, v in HALLAZGO_ESTADO_PILL.items()]
            ),
            style_cell_conditional=[{"if": {"column_id": "Motor"}, "minWidth": "200px"},
                                     {"if": {"column_id": "Descripción"}, "minWidth": "340px"},
                                     {"if": {"column_id": "Estado"}, "maxWidth": "110px"}],
        ),
    ]),

    dcc.Store(id="store-hallazgo-seleccionado"),
    dcc.Store(id="hal-clicks-baseline"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("¿Desea cerrar este hallazgo?"), close_button=True),
        dbc.ModalBody(id="hal-modal-body"),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-cierre", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Confirmar cierre"],
                        id="btn-confirmar-cierre", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-cerrar-hallazgo", is_open=False),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Nuevo hallazgo"), close_button=True),
        dbc.ModalBody([
            html.Div(id="hal-form-error"),
            html.Div([html.Div([html.I(className="bi bi-folder2"), "Proyecto"], className="filter-label"),
                       dcc.Dropdown(id="hal-form-proyecto", placeholder="Selecciona un proyecto")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-cpu"), "Motor"], className="filter-label"),
                       dbc.Input(id="hal-form-motor", type="text", placeholder="Nombre del motor/engine")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-file-earmark-code"), "Script"], className="filter-label"),
                       dbc.Input(id="hal-form-script", type="text", placeholder="p.ej. engine.py")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-code-slash"), "Función"], className="filter-label"),
                       dbc.Input(id="hal-form-funcion", type="text", placeholder="p.ej. evaluate_rules()")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-text-paragraph"), "Descripción"], className="filter-label"),
                       dbc.Textarea(id="hal-form-descripcion", placeholder="Descripción del hallazgo.",
                                     style={"height": "90px"})],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                       dcc.Dropdown(id="hal-form-estado", options=data_mod.HALLAZGOS_ESTADOS,
                                     value="Abierto", clearable=False)],
                       className="mb-3"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-nuevo-hallazgo", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Guardar hallazgo"],
                        id="btn-guardar-nuevo-hallazgo", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-nuevo-hallazgo", is_open=False, size="lg", scrollable=True),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Editar hallazgo"), close_button=True),
        dbc.ModalBody([
            html.Div(id="hal-edit-form-error"),
            html.Div([html.Div([html.I(className="bi bi-folder2"), "Proyecto"], className="filter-label"),
                       dcc.Dropdown(id="hal-edit-form-proyecto", placeholder="Selecciona un proyecto")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-cpu"), "Motor"], className="filter-label"),
                       dbc.Input(id="hal-edit-form-motor", type="text")], className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-file-earmark-code"), "Script"], className="filter-label"),
                       dbc.Input(id="hal-edit-form-script", type="text")], className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-code-slash"), "Función"], className="filter-label"),
                       dbc.Input(id="hal-edit-form-funcion", type="text")], className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-text-paragraph"), "Descripción"], className="filter-label"),
                       dbc.Textarea(id="hal-edit-form-descripcion", style={"height": "90px"})], className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                       dcc.Dropdown(id="hal-edit-form-estado", options=data_mod.HALLAZGOS_ESTADOS,
                                     clearable=False)], className="mb-3"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-editar-hallazgo", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Guardar cambios"],
                        id="btn-guardar-editar-hallazgo", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-editar-hallazgo", is_open=False, size="lg", scrollable=True),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("¿Eliminar este hallazgo?"), close_button=True),
        dbc.ModalBody(id="hal-eliminar-modal-body"),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-eliminar-hallazgo", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-trash"), "Eliminar definitivamente"],
                        id="btn-confirmar-eliminar-hallazgo", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-eliminar-hallazgo", is_open=False),

    dbc.Toast(
        id="hal-toast", header="Hallazgos", is_open=False, dismissable=True, duration=6000,
        style={"position": "fixed", "top": 20, "right": 20, "zIndex": 999, "minWidth": "320px"},
    ),
])


# --------------------------------------------------------------------------
# Opciones de filtros
# --------------------------------------------------------------------------
@dash.callback(
    Output("hal-f-motor", "options"),
    Output("hal-f-estado", "options"),
    Output("hal-f-script", "options"),
    Output("hal-f-funcion", "options"),
    Input("store-hallazgos", "data"),
)
def update_hallazgos_filter_options(store_json):
    df = hallazgos_from_store(store_json)
    if df.empty:
        return [], [], [], []

    def opts(col):
        return [{"label": v, "value": v} for v in sorted(df[col].dropna().unique())]

    return opts("Motor"), opts("Estado"), opts("Script"), opts("Función")


# --------------------------------------------------------------------------
# KPIs + gráficos + tabla
# --------------------------------------------------------------------------
@dash.callback(
    Output("hal-kpi-total", "children"),
    Output("hal-kpi-abiertos", "children"), Output("hal-kpi-abiertos-icon", "className"),
    Output("hal-kpi-revision", "children"),
    Output("hal-kpi-cerrados", "children"),
    Output("hal-kpi-cierre", "children"),
    Output("hal-g-estado", "figure"),
    Output("hal-g-motor", "figure"),
    Output("hal-tabla", "data"),
    Input("store-hallazgos", "data"),
    Input("hal-f-motor", "value"),
    Input("hal-f-estado", "value"),
    Input("hal-f-script", "value"),
    Input("hal-f-funcion", "value"),
)
def update_hallazgos(store_json, motores, estados, scripts, funciones):
    df = hallazgos_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en la pestaña HALLAZGOS.")
        return "0", "0", "kpi-icon tone-good", "0", "0", "0.0%", empty, empty, []

    filtered = df
    if motores:
        filtered = filtered[filtered["Motor"].isin(motores)]
    if estados:
        filtered = filtered[filtered["Estado"].isin(estados)]
    if scripts:
        filtered = filtered[filtered["Script"].isin(scripts)]
    if funciones:
        filtered = filtered[filtered["Función"].isin(funciones)]

    total = len(filtered)
    abiertos = int(filtered["Estado"].eq("Abierto").sum())
    revision = int(filtered["Estado"].eq("En revisión").sum())
    cerrados = int(filtered["Estado"].eq("Cerrado").sum())
    pct_cierre = (cerrados / total * 100) if total else 0.0
    abiertos_icon = "kpi-icon tone-good" if abiertos == 0 else "kpi-icon tone-critical"

    fig_estado = charts.fig_donut_hallazgo_estado(filtered)
    fig_motor = charts.fig_hallazgos_por_motor(filtered)

    tabla_data = filtered[["Estado", "Motor", "Script", "Función", "Descripción", "Proyecto"]].to_dict("records")

    return (str(total), str(abiertos), abiertos_icon, str(revision), str(cerrados),
            f"{pct_cierre:.1f}%", fig_estado, fig_motor, tabla_data)


# --------------------------------------------------------------------------
# Selección de un único hallazgo (habilita/deshabilita el botón de cierre)
# --------------------------------------------------------------------------
@dash.callback(
    Output("btn-cerrar-hallazgo", "disabled"),
    Output("btn-editar-hallazgo", "disabled"),
    Output("btn-eliminar-hallazgo", "disabled"),
    Output("hal-selection-msg", "children"),
    Output("store-hallazgo-seleccionado", "data"),
    Input("hal-tabla", "selected_rows"),
    State("hal-tabla", "data"),
)
def update_hallazgo_selection(selected_rows, table_data):
    selected_rows = selected_rows or []
    if len(selected_rows) == 0:
        return True, True, True, "Selecciona un hallazgo para continuar.", None
    if len(selected_rows) > 1:
        return True, True, True, "Selecciona únicamente un hallazgo para continuar.", None

    idx = selected_rows[0]
    if not table_data or idx >= len(table_data):
        return True, True, True, "Selecciona un hallazgo para continuar.", None

    row = table_data[idx]
    seleccionado = {
        "proyecto": row.get("Proyecto", "Sentinel Alerts"),
        "motor": row["Motor"], "script": row["Script"], "funcion": row["Función"],
        "descripcion": row["Descripción"], "estado_actual": row["Estado"],
    }
    if row["Estado"] == "Cerrado":
        return True, False, False, "Este hallazgo ya está cerrado.", seleccionado
    return False, False, False, "", seleccionado


def _campo_modal(label: str, value: str) -> html.Div:
    return html.Div([
        html.Div(label, className="modal-field-label"),
        html.Div(value, className="modal-field-value"),
    ], className="modal-field")


# --------------------------------------------------------------------------
# Abrir / cancelar / confirmar el cierre
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-cerrar-hallazgo", "is_open"),
    Output("hal-modal-body", "children"),
    Input("btn-cerrar-hallazgo", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    State("hal-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_confirm_modal(n_clicks, seleccionado, baseline):
    umbral = (baseline or {}).get("btn-cerrar-hallazgo", 0)
    if not n_clicks or n_clicks <= umbral or not seleccionado:
        return dash.no_update, dash.no_update
    body = html.Div([
        html.P("Esta acción cambiará el estado del hallazgo a Cerrado y actualizará el archivo Excel.",
                className="section-caption"),
        _campo_modal("Motor", seleccionado["motor"]),
        _campo_modal("Script", seleccionado["script"]),
        _campo_modal("Función", seleccionado["funcion"]),
        _campo_modal("Estado actual", seleccionado["estado_actual"]),
    ])
    return True, body


@dash.callback(
    Output("modal-cerrar-hallazgo", "is_open", allow_duplicate=True),
    Input("btn-cancelar-cierre", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_close(_n_clicks):
    return False


@dash.callback(
    Output("store-hallazgos", "data", allow_duplicate=True),
    Output("modal-cerrar-hallazgo", "is_open", allow_duplicate=True),
    Output("hal-toast", "children", allow_duplicate=True),
    Output("hal-toast", "icon", allow_duplicate=True),
    Output("hal-toast", "is_open", allow_duplicate=True),
    Input("btn-confirmar-cierre", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    prevent_initial_call=True,
)
def confirm_close(_n_clicks, seleccionado):
    if not seleccionado:
        return dash.no_update, False, "No hay ningún hallazgo seleccionado.", "danger", True

    ok, msg = data_mod.close_hallazgo(**seleccionado)
    if ok:
        nuevo_df = data_mod.load_hallazgos()
        return hallazgos_to_store(nuevo_df), False, f"✓ {msg}", "success", True
    return dash.no_update, False, msg, "danger", True


# --------------------------------------------------------------------------
# Opciones de Proyecto para los formularios de alta/edición (catálogo real)
# --------------------------------------------------------------------------
@dash.callback(
    Output("hal-form-proyecto", "options"),
    Output("hal-edit-form-proyecto", "options"),
    Input("store-lookups", "data"),
)
def update_hallazgo_form_proyecto_options(lookups_json):
    lookups = lookups_from_store(lookups_json)
    opts = [{"label": r["proyecto"], "value": r["proyecto"]} for r in lookups["proyectos"]]
    return opts, opts


# --------------------------------------------------------------------------
# Nuevo hallazgo: abrir / cancelar / guardar
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-nuevo-hallazgo", "is_open"),
    Output("hal-form-error", "children"),
    Output("hal-form-proyecto", "value"),
    Output("hal-form-motor", "value"),
    Output("hal-form-script", "value"),
    Output("hal-form-funcion", "value"),
    Output("hal-form-descripcion", "value"),
    Output("hal-form-estado", "value"),
    Input("btn-nuevo-hallazgo", "n_clicks"),
    State("hal-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_nuevo_hallazgo(n_clicks, baseline):
    umbral = (baseline or {}).get("btn-nuevo-hallazgo", 0)
    if not n_clicks or n_clicks <= umbral:
        return (dash.no_update,) * 8
    return True, None, None, "", "", "", "", "Abierto"


@dash.callback(
    Output("modal-nuevo-hallazgo", "is_open", allow_duplicate=True),
    Input("btn-cancelar-nuevo-hallazgo", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_nuevo_hallazgo(_n_clicks):
    return False


@dash.callback(
    Output("store-hallazgos", "data", allow_duplicate=True),
    Output("modal-nuevo-hallazgo", "is_open", allow_duplicate=True),
    Output("hal-form-error", "children", allow_duplicate=True),
    Output("hal-toast", "children", allow_duplicate=True),
    Output("hal-toast", "icon", allow_duplicate=True),
    Output("hal-toast", "is_open", allow_duplicate=True),
    Input("btn-guardar-nuevo-hallazgo", "n_clicks"),
    State("hal-form-proyecto", "value"),
    State("hal-form-motor", "value"),
    State("hal-form-script", "value"),
    State("hal-form-funcion", "value"),
    State("hal-form-descripcion", "value"),
    State("hal-form-estado", "value"),
    prevent_initial_call=True,
)
def guardar_nuevo_hallazgo(_n_clicks, proyecto, motor, script, funcion, descripcion, estado):
    def error(msg):
        return (dash.no_update, True, html.Div(msg, className="section-caption", style={"color": "#a52323"}),
                dash.no_update, dash.no_update, dash.no_update)

    if not proyecto:
        return error("Selecciona un proyecto.")
    if not motor or not motor.strip():
        return error("Escribe el nombre del motor.")
    if not script or not script.strip():
        return error("Escribe el nombre del script.")
    if not funcion or not funcion.strip():
        return error("Escribe el nombre de la función.")
    if not descripcion or not descripcion.strip():
        return error("Escribe una descripción del hallazgo.")
    if not estado:
        return error("Selecciona un estado.")

    ok, msg = data_mod.add_hallazgo(
        proyecto=proyecto, motor=motor.strip(), script=script.strip(),
        funcion=funcion.strip(), descripcion=descripcion.strip(), estado=estado,
    )
    if not ok:
        return error(msg)

    nuevo_df = data_mod.load_hallazgos()
    return hallazgos_to_store(nuevo_df), False, None, f"✓ {msg}", "success", True


# --------------------------------------------------------------------------
# Editar hallazgo: abrir (prellenado) / cancelar / guardar
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-editar-hallazgo", "is_open"),
    Output("hal-edit-form-error", "children"),
    Output("hal-edit-form-proyecto", "value"),
    Output("hal-edit-form-motor", "value"),
    Output("hal-edit-form-script", "value"),
    Output("hal-edit-form-funcion", "value"),
    Output("hal-edit-form-descripcion", "value"),
    Output("hal-edit-form-estado", "value"),
    Input("btn-editar-hallazgo", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    State("hal-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_editar_hallazgo(n_clicks, seleccionado, baseline):
    umbral = (baseline or {}).get("btn-editar-hallazgo", 0)
    if not n_clicks or n_clicks <= umbral or not seleccionado:
        return (dash.no_update,) * 8
    return (True, None, seleccionado["proyecto"], seleccionado["motor"], seleccionado["script"],
            seleccionado["funcion"], seleccionado["descripcion"], seleccionado["estado_actual"])


@dash.callback(
    Output("modal-editar-hallazgo", "is_open", allow_duplicate=True),
    Input("btn-cancelar-editar-hallazgo", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_editar_hallazgo(_n_clicks):
    return False


@dash.callback(
    Output("store-hallazgos", "data", allow_duplicate=True),
    Output("modal-editar-hallazgo", "is_open", allow_duplicate=True),
    Output("hal-edit-form-error", "children", allow_duplicate=True),
    Output("hal-toast", "children", allow_duplicate=True),
    Output("hal-toast", "icon", allow_duplicate=True),
    Output("hal-toast", "is_open", allow_duplicate=True),
    Input("btn-guardar-editar-hallazgo", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    State("hal-edit-form-proyecto", "value"),
    State("hal-edit-form-motor", "value"),
    State("hal-edit-form-script", "value"),
    State("hal-edit-form-funcion", "value"),
    State("hal-edit-form-descripcion", "value"),
    State("hal-edit-form-estado", "value"),
    prevent_initial_call=True,
)
def guardar_editar_hallazgo(_n_clicks, seleccionado, proyecto, motor, script, funcion, descripcion, estado):
    def error(msg):
        return (dash.no_update, True, html.Div(msg, className="section-caption", style={"color": "#a52323"}),
                dash.no_update, dash.no_update, dash.no_update)

    if not seleccionado:
        return error("No hay ningún hallazgo seleccionado.")
    if not proyecto:
        return error("Selecciona un proyecto.")
    if not motor or not motor.strip():
        return error("Escribe el nombre del motor.")
    if not script or not script.strip():
        return error("Escribe el nombre del script.")
    if not funcion or not funcion.strip():
        return error("Escribe el nombre de la función.")
    if not descripcion or not descripcion.strip():
        return error("Escribe una descripción del hallazgo.")
    if not estado:
        return error("Selecciona un estado.")

    ok, msg = data_mod.edit_hallazgo(
        **seleccionado, nuevo_proyecto=proyecto, nuevo_motor=motor.strip(), nuevo_script=script.strip(),
        nuevo_funcion=funcion.strip(), nueva_descripcion=descripcion.strip(), nuevo_estado=estado,
    )
    if not ok:
        return error(msg)

    nuevo_df = data_mod.load_hallazgos()
    return hallazgos_to_store(nuevo_df), False, None, f"✓ {msg}", "success", True


# --------------------------------------------------------------------------
# Eliminar hallazgo: abrir confirmación / cancelar / confirmar
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-eliminar-hallazgo", "is_open"),
    Output("hal-eliminar-modal-body", "children"),
    Input("btn-eliminar-hallazgo", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    State("hal-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_eliminar_hallazgo(n_clicks, seleccionado, baseline):
    umbral = (baseline or {}).get("btn-eliminar-hallazgo", 0)
    if not n_clicks or n_clicks <= umbral or not seleccionado:
        return dash.no_update, dash.no_update
    body = html.Div([
        html.P("Esta acción eliminará el hallazgo de forma permanente del archivo Excel y no se puede deshacer.",
                className="section-caption", style={"color": "#a52323"}),
        _campo_modal("Motor", seleccionado["motor"]),
        _campo_modal("Script", seleccionado["script"]),
        _campo_modal("Función", seleccionado["funcion"]),
        _campo_modal("Descripción", seleccionado["descripcion"]),
        _campo_modal("Estado", seleccionado["estado_actual"]),
    ])
    return True, body


@dash.callback(
    Output("modal-eliminar-hallazgo", "is_open", allow_duplicate=True),
    Input("btn-cancelar-eliminar-hallazgo", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_eliminar_hallazgo(_n_clicks):
    return False


@dash.callback(
    Output("store-hallazgos", "data", allow_duplicate=True),
    Output("modal-eliminar-hallazgo", "is_open", allow_duplicate=True),
    Output("hal-toast", "children", allow_duplicate=True),
    Output("hal-toast", "icon", allow_duplicate=True),
    Output("hal-toast", "is_open", allow_duplicate=True),
    Input("btn-confirmar-eliminar-hallazgo", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    prevent_initial_call=True,
)
def confirmar_eliminar_hallazgo(_n_clicks, seleccionado):
    if not seleccionado:
        return dash.no_update, False, "No hay ningún hallazgo seleccionado.", "danger", True

    ok, msg = data_mod.delete_hallazgo(**seleccionado)
    if ok:
        nuevo_df = data_mod.load_hallazgos()
        return hallazgos_to_store(nuevo_df), False, f"✓ {msg}", "success", True
    return dash.no_update, False, msg, "danger", True


# --------------------------------------------------------------------------
# Asegura que ningún formulario quede abierto al entrar a la página. Los
# modales solo deben abrirse por un clic explícito en sus botones; esto
# cierra cualquier estado de "abierto" que el navegador pudiera arrastrar
# de una visita anterior a esta misma página en la sesión.
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-nuevo-hallazgo", "is_open", allow_duplicate=True),
    Output("modal-editar-hallazgo", "is_open", allow_duplicate=True),
    Output("modal-eliminar-hallazgo", "is_open", allow_duplicate=True),
    Output("modal-cerrar-hallazgo", "is_open", allow_duplicate=True),
    Output("hal-form-error", "children", allow_duplicate=True),
    Output("hal-edit-form-error", "children", allow_duplicate=True),
    Output("hal-tabla", "selected_rows"),
    Output("hal-clicks-baseline", "data"),
    Input("url", "pathname"),
    State("btn-nuevo-hallazgo", "n_clicks"),
    State("btn-editar-hallazgo", "n_clicks"),
    State("btn-eliminar-hallazgo", "n_clicks"),
    State("btn-cerrar-hallazgo", "n_clicks"),
    prevent_initial_call=True,
)
def cerrar_modales_al_entrar(pathname, n_nuevo, n_editar, n_eliminar, n_cerrar):
    if pathname != "/hallazgos":
        return (dash.no_update,) * 8
    baseline = {
        "btn-nuevo-hallazgo": n_nuevo or 0,
        "btn-editar-hallazgo": n_editar or 0,
        "btn-eliminar-hallazgo": n_eliminar or 0,
        "btn-cerrar-hallazgo": n_cerrar or 0,
    }
    return False, False, False, False, None, None, [], baseline
