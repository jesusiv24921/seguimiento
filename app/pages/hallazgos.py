"""Hallazgos — seguimiento y cierre de hallazgos de validación de Sentinel Alerts.

Fuente de verdad: la pestaña HALLAZGOS de seguimiento.xlsx (data.load_hallazgos).
Cerrar un hallazgo escribe de verdad en el Excel (data.close_hallazgo) — nunca
solo en memoria — y luego recarga store-hallazgos para que KPIs, gráficos y
tabla reflejen el cambio real.
"""
from __future__ import annotations

import datetime as dt

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dash_table, dcc, html

import charts
import data as data_mod
from hallazgos_import import template_csv, validate_hallazgos_csv
import knowledge as km
from components import badge_hallazgo_estado, badge_proyecto, chart_card, kpi_card, page_header
from data_store import hallazgos_from_store, hallazgos_to_store, knowledge_to_store, lookups_from_store
from theme import GRID, HALLAZGO_ESTADO_PILL, INK_MUTED, INK_PRIMARY

dash.register_page(__name__, path="/hallazgos", name="Hallazgos", title="Hallazgos")

layout = html.Div(className="page", children=[
    page_header("Hallazgos",
                 "Seguimiento de hallazgos identificados durante la validación de los motores de Sentinel Alerts."),

    html.Div([
        kpi_card("hal-kpi-total", "Hallazgos totales", "bi bi-clipboard-data", context_id="hal-kpi-total-ctx"),
        kpi_card("hal-kpi-abiertos", "Abiertos", "bi bi-exclamation-circle",
                  icon_id="hal-kpi-abiertos-icon", tone="tone-critical", context_id="hal-kpi-abiertos-ctx"),
        kpi_card("hal-kpi-revision", "En revisión", "bi bi-search", tone="tone-warning",
                  context_id="hal-kpi-revision-ctx"),
        kpi_card("hal-kpi-cerrados", "Cerrados", "bi bi-check2-circle", tone="tone-good",
                  context_id="hal-kpi-cerrados-ctx"),
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
        dbc.Row([
            dbc.Col(html.Div([
                html.Div([html.I(className="bi bi-cpu"), "Motor"], className="filter-label"),
                dcc.Dropdown(id="hal-f-motor", multi=True, placeholder="Todos"),
            ], className="filter-field"), md=2),
            dbc.Col(html.Div([
                html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                dcc.Dropdown(id="hal-f-estado", multi=True, placeholder="Todos"),
            ], className="filter-field"), md=2),
            dbc.Col(html.Div([
                html.Div([html.I(className="bi bi-file-earmark-code"), "Script"], className="filter-label"),
                dcc.Dropdown(id="hal-f-script", multi=True, placeholder="Todos"),
            ], className="filter-field"), md=2),
            dbc.Col(html.Div([
                html.Div([html.I(className="bi bi-code-slash"), "Función"], className="filter-label"),
                dcc.Dropdown(id="hal-f-funcion", multi=True, placeholder="Todas"),
            ], className="filter-field"), md=2),
            dbc.Col(html.Div([
                html.Div([html.I(className="bi bi-search"), "Buscar"], className="filter-label"),
                dbc.Input(id="hal-f-buscar", type="text", debounce=True, placeholder="Buscar en descripción..."),
            ], className="filter-field"), md=3),
            dbc.Col(dbc.Button([html.I(className="bi bi-x-circle"), "Limpiar"], id="hal-btn-limpiar-filtros",
                    className="btn-cal-nav w-100 mt-4"), md=1),
        ], className="g-2"),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-list-ul"), "Detalle de hallazgos"], className="section-title"),
        html.Div("Haz clic en cualquier celda o tarjeta para ver el detalle completo. Selecciona con la "
                  "casilla para cerrar, editar, eliminar o convertir en conocimiento.", className="section-caption"),
        html.Div(className="hal-actions-row", children=[
            dbc.Button([html.I(className="bi bi-check2-circle"), "Cerrar hallazgo"],
                        id="btn-cerrar-hallazgo", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-pencil"), "Editar"],
                        id="btn-editar-hallazgo", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-trash"), "Eliminar"],
                        id="btn-eliminar-hallazgo", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-mortarboard-fill"), "Convertir en conocimiento"],
                        id="btn-convertir-conocimiento-hallazgo", className="btn-refresh", disabled=True),
            html.Div(id="hal-selection-msg", className="hal-selection-msg"),
            dbc.Button([html.I(className="bi bi-upload"), "Importar hallazgos"],
                        id="btn-importar-hallazgos", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-plus-lg"), "Nuevo hallazgo"],
                        id="btn-nuevo-hallazgo", className="btn-refresh ms-auto", n_clicks=0),
        ]),
        html.Div(className="table-desktop-only", children=[
            dash_table.DataTable(
                id="hal-tabla",
                columns=[
                    {"name": "Estado", "id": "Estado"},
                    {"name": "Fecha hallazgo", "id": "fecha_hallazgo_txt"},
                    {"name": "Fecha cierre", "id": "fecha_cierre_txt"},
                    {"name": "Motor", "id": "Motor"},
                    {"name": "Script", "id": "Script"},
                    {"name": "Función", "id": "Función"},
                    {"name": "Descripción", "id": "Descripción"},
                ],
                row_selectable="multi",
                page_size=12,
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
                    + [{"if": {"filter_query": f'{{Estado}} = "{k}"', "column_id": "Estado"},
                        "backgroundColor": v["bg"], "color": v["fg"], "fontWeight": "600"}
                       for k, v in HALLAZGO_ESTADO_PILL.items()]
                ),
                style_cell_conditional=[{"if": {"column_id": "Motor"}, "minWidth": "200px"},
                                         {"if": {"column_id": "Descripción"}, "minWidth": "340px"},
                                         {"if": {"column_id": "Estado"}, "maxWidth": "110px"},
                                         {"if": {"column_id": "fecha_hallazgo_txt"}, "maxWidth": "110px"},
                                         {"if": {"column_id": "fecha_cierre_txt"}, "maxWidth": "110px"}],
            ),
        ]),
        html.Div(id="hal-tabla-cards", className="table-mobile-only"),
    ]),

    dcc.Store(id="store-hallazgo-seleccionado"),
    dcc.Store(id="hal-clicks-baseline"),
    dcc.Store(id="hal-import-preview"),
    dcc.Download(id="hal-download-template"),

    dbc.Modal([
        dbc.ModalHeader([
            dbc.ModalTitle(id="hal-detalle-titulo"),
            dbc.Button(html.I(className="bi bi-x-lg"), id="btn-cerrar-detalle-hallazgo",
                        className="btn-refresh", size="sm", n_clicks=0),
        ], close_button=False, className="hal-detail-header"),
        dbc.ModalBody(id="hal-detalle-body"),
    ], id="modal-detalle-hallazgo", is_open=False, size="lg", scrollable=True, className="hal-detail-modal"),

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
            dbc.Row([
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                                    dcc.Dropdown(id="hal-form-estado", options=data_mod.HALLAZGOS_ESTADOS,
                                                  value="Abierto", clearable=False)],
                                    className="mb-3"), md=6),
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-calendar3"), "Fecha hallazgo"],
                                              className="filter-label"),
                                    dcc.DatePickerSingle(id="hal-form-fecha-hallazgo", display_format="DD/MM/YYYY",
                                                           date=dt.date.today(), className="w-100")],
                                    className="mb-3"), md=6),
            ]),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-nuevo-hallazgo", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Guardar hallazgo"],
                        id="btn-guardar-nuevo-hallazgo", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-nuevo-hallazgo", is_open=False, size="lg", scrollable=True),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle([html.I(className="bi bi-upload me-2"), "Importar hallazgos desde CSV"]),
                        close_button=True),
        dbc.ModalBody([
            html.Div("Carga el archivo, revisa los resultados y selecciona los registros válidos antes de importarlos.",
                     className="section-caption mb-3"),
            html.Div([html.Div("Proyecto de destino", className="filter-label"),
                      dcc.Dropdown(id="hal-import-proyecto", placeholder="Selecciona un proyecto")], className="mb-3"),
            dcc.Upload(id="hal-import-upload", multiple=False, children=html.Div([
                html.I(className="bi bi-file-earmark-arrow-up me-2"), "Seleccionar archivo CSV"
            ]), className="con-upload-zone"),
            html.Div([html.Strong("Formato esperado: "),
                      "Estado | Fecha hallazgo | Fecha cierre | Motor | Script | Función | Descripción"],
                     className="section-caption mt-2"),
            dbc.Button([html.I(className="bi bi-download me-1"), "Descargar plantilla CSV"],
                       id="hal-btn-descargar-plantilla", className="btn-cal-nav btn-sm mt-2", n_clicks=0),
            html.Div(id="hal-import-error", className="mt-3"),
            html.Div(id="hal-import-summary", className="mt-3"),
            html.Div([
                dbc.Button("Seleccionar todos", id="hal-import-select-all", className="btn-cal-nav btn-sm", n_clicks=0),
                dbc.Button("Deseleccionar todos", id="hal-import-select-none", className="btn-cal-nav btn-sm ms-2", n_clicks=0),
            ], id="hal-import-selection-actions", className="mt-2", style={"display": "none"}),
            dash_table.DataTable(
                id="hal-import-table",
                columns=[
                    {"name": "Estado", "id": "estado_importacion"},
                    {"name": "Detalle", "id": "detalle"},
                    {"name": "Estado hallazgo", "id": "Estado"},
                    {"name": "Motor", "id": "Motor"},
                    {"name": "Script", "id": "Script"},
                    {"name": "Función", "id": "Función"},
                    {"name": "Descripción", "id": "Descripción"},
                ],
                row_selectable="multi", page_size=8, style_as_list_view=True,
                style_table={"overflowX": "auto", "marginTop": "12px"},
                style_cell={"fontFamily": "Inter, system-ui, sans-serif", "fontSize": "0.82rem",
                            "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                style_data_conditional=[
                    {"if": {"filter_query": '{estado_importacion} = "Error"'}, "backgroundColor": "#fff2f2"},
                    {"if": {"filter_query": '{estado_importacion} = "Válido"'}, "backgroundColor": "#f3fbf5"},
                ],
            ),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="hal-btn-cancelar-import", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2 me-1"), "Importar seleccionados"],
                       id="hal-btn-importar-seleccionados", className="btn-refresh", n_clicks=0, disabled=True),
        ]),
    ], id="modal-importar-hallazgos", is_open=False, size="xl", scrollable=True),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Confirmar importación"), close_button=True),
        dbc.ModalBody(id="hal-import-confirm-body"),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="hal-btn-cancelar-confirm-import", className="btn-cal-nav", n_clicks=0),
            dbc.Button("Sí, importar", id="hal-btn-confirmar-import", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-confirmar-importacion", is_open=False),

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
            dbc.Row([
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                                    dcc.Dropdown(id="hal-edit-form-estado", options=data_mod.HALLAZGOS_ESTADOS,
                                                  clearable=False)], className="mb-3"), md=4),
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-calendar3"), "Fecha hallazgo"],
                                              className="filter-label"),
                                    dcc.DatePickerSingle(id="hal-edit-form-fecha-hallazgo",
                                                           display_format="DD/MM/YYYY", className="w-100")],
                                    className="mb-3"), md=4),
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-calendar-check"), "Fecha cierre"],
                                              className="filter-label"),
                                    dcc.DatePickerSingle(id="hal-edit-form-fecha-cierre",
                                                           display_format="DD/MM/YYYY", className="w-100")],
                                    className="mb-3"), md=4),
            ]),
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


@dash.callback(
    Output("hal-f-motor", "value"),
    Output("hal-f-estado", "value"),
    Output("hal-f-script", "value"),
    Output("hal-f-funcion", "value"),
    Output("hal-f-buscar", "value"),
    Input("hal-btn-limpiar-filtros", "n_clicks"),
    prevent_initial_call=True,
)
def limpiar_filtros_hallazgos(_n_clicks):
    return [], [], [], [], ""


def _hallazgo_card(idx: int, row: dict) -> html.Div:
    """Tarjeta con el mismo contenido que una fila de hal-tabla, para pantallas
    angostas/verticales. Tocar el cuerpo abre el detalle (igual que un clic en
    una celda de la tabla); el botón "Seleccionar" escribe directo en
    hal-tabla.selected_rows (con el mismo índice de esta fila), así que
    reutiliza sin duplicar toda la lógica de selección/edición/cierre que ya
    lee ese mismo prop."""
    pill = HALLAZGO_ESTADO_PILL.get(row["Estado"], {"bg": "#eee", "fg": "#333"})
    return html.Div(className="hal-card", children=[
        html.Div(className="hal-card-body-clickable",
                  id={"type": "hal-card-view", "index": idx}, n_clicks=0, children=[
            html.Div(className="hal-card-head", children=[
                html.Span(row["Estado"], className="status-pill",
                           style={"backgroundColor": pill["bg"], "color": pill["fg"]}),
                html.Span(row["Motor"], className="hal-card-motor"),
            ]),
            html.Div(row["Descripción"], className="hal-card-desc"),
            html.Div(className="hal-card-meta-grid", children=[
                html.Div([html.Span("Proyecto", className="hal-card-meta-label"),
                           html.Span(row["Proyecto"], className="hal-card-meta-value")]),
                html.Div([html.Span("Script", className="hal-card-meta-label"),
                           html.Span(row["Script"], className="hal-card-meta-value")]),
                html.Div([html.Span("Función", className="hal-card-meta-label"),
                           html.Span(row["Función"], className="hal-card-meta-value")]),
                html.Div([html.Span("Fecha hallazgo", className="hal-card-meta-label"),
                           html.Span(row["fecha_hallazgo_txt"], className="hal-card-meta-value")]),
                html.Div([html.Span("Fecha cierre", className="hal-card-meta-label"),
                           html.Span(row["fecha_cierre_txt"], className="hal-card-meta-value")]),
            ]),
        ]),
        dbc.Button("Seleccionar", id={"type": "hal-card-select", "index": idx},
                    className="btn-refresh btn-sm-card", size="sm", n_clicks=0),
    ])


# --------------------------------------------------------------------------
# KPIs + gráficos + tabla
# --------------------------------------------------------------------------
@dash.callback(
    Output("hal-kpi-total", "children"), Output("hal-kpi-total-ctx", "children"),
    Output("hal-kpi-abiertos", "children"), Output("hal-kpi-abiertos-icon", "className"),
    Output("hal-kpi-abiertos-ctx", "children"),
    Output("hal-kpi-revision", "children"), Output("hal-kpi-revision-ctx", "children"),
    Output("hal-kpi-cerrados", "children"), Output("hal-kpi-cerrados-ctx", "children"),
    Output("hal-kpi-cierre", "children"),
    Output("hal-g-estado", "figure"),
    Output("hal-g-motor", "figure"),
    Output("hal-tabla", "data"),
    Output("hal-tabla-cards", "children"),
    Input("store-hallazgos", "data"),
    Input("hal-f-motor", "value"),
    Input("hal-f-estado", "value"),
    Input("hal-f-script", "value"),
    Input("hal-f-funcion", "value"),
    Input("hal-f-buscar", "value"),
)
def update_hallazgos(store_json, motores, estados, scripts, funciones, buscar):
    df = hallazgos_from_store(store_json)
    if df.empty:
        empty = charts.empty_figure("Sin datos disponibles en la pestaña HALLAZGOS.")
        return ("0", "Sin registros", "0", "kpi-icon tone-good", "0% del total",
                "0", "0% del total", "0", "0% del total", "0.0%", empty, empty, [], [])

    filtered = df
    if motores:
        filtered = filtered[filtered["Motor"].isin(motores)]
    if estados:
        filtered = filtered[filtered["Estado"].isin(estados)]
    if scripts:
        filtered = filtered[filtered["Script"].isin(scripts)]
    if funciones:
        filtered = filtered[filtered["Función"].isin(funciones)]
    if buscar and buscar.strip():
        query = buscar.strip().lower()
        searchable = ["Descripción", "Motor", "Script", "Función", "Proyecto"]
        mask = pd.Series(False, index=filtered.index)
        for col in searchable:
            mask |= filtered[col].fillna("").astype(str).str.lower().str.contains(query, regex=False)
        filtered = filtered[mask]

    total = len(filtered)
    abiertos = int(filtered["Estado"].eq("Abierto").sum())
    revision = int(filtered["Estado"].eq("En revisión").sum())
    cerrados = int(filtered["Estado"].eq("Cerrado").sum())
    pct_cierre = (cerrados / total * 100) if total else 0.0
    abiertos_icon = "kpi-icon tone-good" if abiertos == 0 else "kpi-icon tone-critical"

    def porcentaje(valor):
        return f"{valor / total * 100:.0f}% del total" if total else "0% del total"

    fig_estado = charts.fig_donut_hallazgo_estado(filtered)
    fig_motor = charts.fig_hallazgos_por_motor(filtered)

    tabla = filtered.copy()
    tabla["fecha_hallazgo_txt"] = tabla["Fecha hallazgo"].dt.strftime("%d/%m/%Y").fillna("—")
    tabla["fecha_cierre_txt"] = tabla["Fecha cierre"].dt.strftime("%d/%m/%Y").fillna("—")
    tabla["fecha_hallazgo_iso"] = tabla["Fecha hallazgo"].dt.strftime("%Y-%m-%d")
    tabla["fecha_cierre_iso"] = tabla["Fecha cierre"].dt.strftime("%Y-%m-%d")
    # "id" es una clave reservada de dash_table: permite identificar la fila por
    # active_cell.row_id sin importar el orden visual tras un ordenamiento nativo
    # (los hallazgos no tienen un ID de negocio propio, así que se usa la
    # posición en el DataFrame ya filtrado, estable mientras dure este render).
    tabla["id"] = tabla.index.astype(str)
    tabla_data = tabla[["id", "Estado", "Motor", "Script", "Función", "Descripción", "Proyecto",
                         "fecha_hallazgo_txt", "fecha_cierre_txt",
                         "fecha_hallazgo_iso", "fecha_cierre_iso"]].to_dict("records")
    # to_dict convierte los None de las fechas vacías en NaN (float); DatePickerSingle
    # necesita None literal para mostrarse vacío en vez de una fecha inválida.
    for fila in tabla_data:
        if pd.isna(fila["fecha_hallazgo_iso"]):
            fila["fecha_hallazgo_iso"] = None
        if pd.isna(fila["fecha_cierre_iso"]):
            fila["fecha_cierre_iso"] = None

    cards = [_hallazgo_card(i, fila) for i, fila in enumerate(tabla_data)]

    return (str(total), "Resultado de los filtros",
            str(abiertos), abiertos_icon, porcentaje(abiertos),
            str(revision), porcentaje(revision),
            str(cerrados), porcentaje(cerrados),
            f"{pct_cierre:.1f}%", fig_estado, fig_motor, tabla_data, cards)


# --------------------------------------------------------------------------
# Botón "Seleccionar" de una tarjeta (vista móvil): escribe en
# hal-tabla.selected_rows, así que dispara update_hallazgo_selection de
# abajo exactamente igual que marcar la casilla de la tabla.
# --------------------------------------------------------------------------
@dash.callback(
    Output("hal-tabla", "selected_rows", allow_duplicate=True),
    Input({"type": "hal-card-select", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def seleccionar_hallazgo_desde_card(n_clicks_list):
    if not n_clicks_list or not any(n_clicks_list):
        return dash.no_update
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update
    return [triggered["index"]]


# --------------------------------------------------------------------------
# Selección de un único hallazgo (habilita/deshabilita el botón de cierre)
# --------------------------------------------------------------------------
@dash.callback(
    Output("btn-cerrar-hallazgo", "disabled"),
    Output("btn-editar-hallazgo", "disabled"),
    Output("btn-eliminar-hallazgo", "disabled"),
    Output("btn-convertir-conocimiento-hallazgo", "disabled"),
    Output("hal-selection-msg", "children"),
    Output("store-hallazgo-seleccionado", "data"),
    Input("hal-tabla", "selected_rows"),
    State("hal-tabla", "data"),
)
def update_hallazgo_selection(selected_rows, table_data):
    selected_rows = selected_rows or []
    if len(selected_rows) == 0:
        return True, True, True, True, "Selecciona un hallazgo para continuar.", None
    if len(selected_rows) > 1:
        return True, True, True, True, "Selecciona únicamente un hallazgo para continuar.", None

    idx = selected_rows[0]
    if not table_data or idx >= len(table_data):
        return True, True, True, True, "Selecciona un hallazgo para continuar.", None

    row = table_data[idx]
    seleccionado = {
        "proyecto": row.get("Proyecto", "Sentinel Alerts"),
        "motor": row["Motor"], "script": row["Script"], "funcion": row["Función"],
        "descripcion": row["Descripción"], "estado_actual": row["Estado"],
        "fecha_hallazgo": row.get("fecha_hallazgo_iso"), "fecha_cierre": row.get("fecha_cierre_iso"),
    }
    if row["Estado"] == "Cerrado":
        return True, False, False, False, "Este hallazgo ya está cerrado.", seleccionado
    return False, False, False, False, "", seleccionado


def _campo_modal(label: str, value: str) -> html.Div:
    return html.Div([
        html.Div(label, className="modal-field-label"),
        html.Div(value, className="modal-field-value"),
    ], className="modal-field")


# --------------------------------------------------------------------------
# Panel de detalle (drawer lateral, mismo patrón que el detalle de
# Actividades en app.py): clic en una celda de la tabla o en el cuerpo de
# una tarjeta abre una vista de solo lectura, independiente de la selección
# por casilla que usan Cerrar/Editar/Eliminar/Convertir en conocimiento.
# --------------------------------------------------------------------------
def _construir_detalle_hallazgo(fila: dict) -> html.Div:
    descriptor_prefix = f"{fila['Motor']} / {fila['Script']} / {fila['Función']}"
    conocimientos = km.load_knowledge()
    relacionados = conocimientos[
        conocimientos["hallazgos_relacionados"].fillna("").astype(str).str.contains(descriptor_prefix, regex=False)
    ]
    bloque_conocimiento = html.Div(className="hal-detail-related", children=[
        html.Div([html.Span(k["conocimiento_id"], className="hal-card-motor"),
                   html.Div(k["titulo"], className="fw-semibold")])
        for _, k in relacionados.iterrows()
    ]) if not relacionados.empty else html.Div("No hay conocimiento relacionado registrado.",
                                                  className="section-caption")

    return html.Div(className="hal-detail-body", children=[
        html.Div([badge_hallazgo_estado(fila["Estado"]), badge_proyecto(fila["Proyecto"])],
                  className="d-flex gap-2 mb-3"),
        html.Div("Información", className="section-title"),
        html.Div(className="hal-detail-fields", children=[
            _campo_modal("Motor", fila["Motor"]),
            _campo_modal("Script", fila["Script"]),
            _campo_modal("Función", fila["Función"]),
            _campo_modal("Proyecto", fila["Proyecto"]),
            _campo_modal("Fecha hallazgo", fila["fecha_hallazgo_txt"]),
            _campo_modal("Fecha cierre", fila["fecha_cierre_txt"]),
        ]),
        html.Div("Descripción", className="section-title mt-3"),
        html.Div(fila["Descripción"] or "No registrada.", className="hal-detail-text"),
        html.Div("Conocimiento relacionado", className="section-title mt-3"),
        bloque_conocimiento,
    ])


@dash.callback(
    Output("modal-detalle-hallazgo", "is_open"),
    Output("hal-detalle-titulo", "children"),
    Output("hal-detalle-body", "children"),
    Input("hal-tabla", "active_cell"),
    Input({"type": "hal-card-view", "index": ALL}, "n_clicks"),
    State("hal-tabla", "data"),
    prevent_initial_call=True,
)
def abrir_detalle_hallazgo(active_cell, n_clicks_list, table_data):
    triggered_id = dash.ctx.triggered_id
    fila = None

    if triggered_id == "hal-tabla":
        if not active_cell:
            return dash.no_update, dash.no_update, dash.no_update
        row_id = active_cell.get("row_id")
        fila = next((d for d in (table_data or []) if str(d.get("id")) == str(row_id)), None)
    elif isinstance(triggered_id, dict) and triggered_id.get("type") == "hal-card-view":
        if not n_clicks_list or not any(n_clicks_list):
            return dash.no_update, dash.no_update, dash.no_update
        idx = triggered_id["index"]
        if not table_data or idx >= len(table_data):
            return dash.no_update, dash.no_update, dash.no_update
        fila = table_data[idx]

    if not fila:
        return dash.no_update, dash.no_update, dash.no_update

    titulo = [html.I(className="bi bi-search me-2"), f"{fila['Motor']} — {fila['Script']}"]
    return True, titulo, _construir_detalle_hallazgo(fila)


@dash.callback(
    Output("modal-detalle-hallazgo", "is_open", allow_duplicate=True),
    Input("btn-cerrar-detalle-hallazgo", "n_clicks"),
    prevent_initial_call=True,
)
def cerrar_detalle_hallazgo(_n_clicks):
    return False


_IDENTIDAD_KEYS = ["proyecto", "motor", "script", "funcion", "descripcion", "estado_actual"]


def _identidad(seleccionado: dict) -> dict:
    """store-hallazgo-seleccionado trae, además de la clave de identidad que
    usan close/delete_hallazgo, las fechas actuales (para prellenar el
    formulario de edición). Esta función se queda solo con la clave de
    identidad, para poder seguir usando **kwargs sin pasar argumentos que
    close_hallazgo/delete_hallazgo no esperan."""
    return {k: seleccionado[k] for k in _IDENTIDAD_KEYS}


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
def confirm_close(n_clicks, seleccionado):
    if not n_clicks:
        return (dash.no_update,) * 5
    if not seleccionado:
        return dash.no_update, False, "No hay ningún hallazgo seleccionado.", "danger", True

    ok, msg = data_mod.close_hallazgo(**_identidad(seleccionado))
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
    Output("hal-import-proyecto", "options"),
    Input("store-lookups", "data"),
)
def update_hallazgo_form_proyecto_options(lookups_json):
    lookups = lookups_from_store(lookups_json)
    opts = [{"label": r["proyecto"], "value": r["proyecto"]} for r in lookups["proyectos"]]
    return opts, opts, opts


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
    Output("hal-form-fecha-hallazgo", "date"),
    Input("btn-nuevo-hallazgo", "n_clicks"),
    State("hal-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_nuevo_hallazgo(n_clicks, baseline):
    umbral = (baseline or {}).get("btn-nuevo-hallazgo", 0)
    if not n_clicks or n_clicks <= umbral:
        return (dash.no_update,) * 9
    return True, None, None, "", "", "", "", "Abierto", dt.date.today()


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
    State("hal-form-fecha-hallazgo", "date"),
    prevent_initial_call=True,
)
def guardar_nuevo_hallazgo(n_clicks, proyecto, motor, script, funcion, descripcion, estado, fecha_hallazgo):
    if not n_clicks:
        # Ver comentario equivalente en actividades.py: dash/#1513 puede invocar este
        # callback al entrar a la página con campos vacíos, y sin esta guarda su
        # error() dejaría is_open=True, abriendo el modal solo.
        return (dash.no_update,) * 6

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
        fecha_hallazgo=dt.date.fromisoformat(fecha_hallazgo) if fecha_hallazgo else None,
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
    Output("hal-edit-form-fecha-hallazgo", "date"),
    Output("hal-edit-form-fecha-cierre", "date"),
    Input("btn-editar-hallazgo", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    State("hal-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_editar_hallazgo(n_clicks, seleccionado, baseline):
    umbral = (baseline or {}).get("btn-editar-hallazgo", 0)
    if not n_clicks or n_clicks <= umbral or not seleccionado:
        return (dash.no_update,) * 10
    return (True, None, seleccionado["proyecto"], seleccionado["motor"], seleccionado["script"],
            seleccionado["funcion"], seleccionado["descripcion"], seleccionado["estado_actual"],
            seleccionado.get("fecha_hallazgo"), seleccionado.get("fecha_cierre"))


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
    State("hal-edit-form-fecha-hallazgo", "date"),
    State("hal-edit-form-fecha-cierre", "date"),
    prevent_initial_call=True,
)
def guardar_editar_hallazgo(n_clicks, seleccionado, proyecto, motor, script, funcion, descripcion, estado,
                             fecha_hallazgo, fecha_cierre):
    if not n_clicks:
        return (dash.no_update,) * 6

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
        **_identidad(seleccionado), nuevo_proyecto=proyecto, nuevo_motor=motor.strip(), nuevo_script=script.strip(),
        nuevo_funcion=funcion.strip(), nueva_descripcion=descripcion.strip(), nuevo_estado=estado,
        nueva_fecha_hallazgo=dt.date.fromisoformat(fecha_hallazgo) if fecha_hallazgo else None,
        nueva_fecha_cierre=dt.date.fromisoformat(fecha_cierre) if fecha_cierre else None,
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
def confirmar_eliminar_hallazgo(n_clicks, seleccionado):
    if not n_clicks:
        return (dash.no_update,) * 5
    if not seleccionado:
        return dash.no_update, False, "No hay ningún hallazgo seleccionado.", "danger", True

    ok, msg = data_mod.delete_hallazgo(**_identidad(seleccionado))
    if ok:
        nuevo_df = data_mod.load_hallazgos()
        return hallazgos_to_store(nuevo_df), False, f"✓ {msg}", "success", True
    return dash.no_update, False, msg, "danger", True


# --------------------------------------------------------------------------
# Convertir en conocimiento: crea una entrada preliminar directo desde el
# hallazgo seleccionado (mismo patrón que app.py:convertir_actividad_en_
# conocimiento para actividades) — el usuario la termina de editar en
# /conocimiento. Los hallazgos no tienen un ID propio (se identifican por
# la clave compuesta motor/script/función/descripción), así que
# 'hallazgos_relacionados' se guarda como un descriptor de texto, no un ID.
# --------------------------------------------------------------------------
@dash.callback(
    Output("store-conocimiento", "data", allow_duplicate=True),
    Output("hal-toast", "children", allow_duplicate=True),
    Output("hal-toast", "icon", allow_duplicate=True),
    Output("hal-toast", "is_open", allow_duplicate=True),
    Input("btn-convertir-conocimiento-hallazgo", "n_clicks"),
    State("store-hallazgo-seleccionado", "data"),
    prevent_initial_call=True,
)
def convertir_hallazgo_en_conocimiento(n_clicks, seleccionado):
    if not n_clicks:
        return (dash.no_update,) * 4
    if not seleccionado:
        return dash.no_update, "No hay ningún hallazgo seleccionado.", "danger", True

    descriptor = (f"{seleccionado['motor']} / {seleccionado['script']} / "
                   f"{seleccionado['funcion']}: {seleccionado['descripcion']}")
    contenido = f"**Descripción del hallazgo:** {seleccionado['descripcion']}"

    ok, msg, _new_id = km.add_knowledge(
        titulo=f"{seleccionado['motor']}: {seleccionado['descripcion'][:80]}",
        descripcion_breve=f"Script {seleccionado['script']}, función {seleccionado['funcion']}",
        contenido=contenido, categoria="Errores y aprendizajes", estado="Pendiente de revisar",
        ambito="Proyecto", proyectos=seleccionado["proyecto"], etiquetas=None, fuente=None,
        hallazgos_relacionados=descriptor,
    )
    if not ok:
        return dash.no_update, msg, "danger", True

    nuevo_df = km.load_knowledge()
    return (knowledge_to_store(nuevo_df), f"✓ {msg} Puedes terminar de editarla en Conocimiento.",
            "success", True)


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
    Output("modal-detalle-hallazgo", "is_open", allow_duplicate=True),
    Output("hal-form-error", "children", allow_duplicate=True),
    Output("hal-edit-form-error", "children", allow_duplicate=True),
    Output("hal-tabla", "selected_rows", allow_duplicate=True),
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
        return (dash.no_update,) * 9
    baseline = {
        "btn-nuevo-hallazgo": n_nuevo or 0,
        "btn-editar-hallazgo": n_editar or 0,
        "btn-eliminar-hallazgo": n_eliminar or 0,
        "btn-cerrar-hallazgo": n_cerrar or 0,
    }
    return False, False, False, False, False, None, None, [], baseline


# --------------------------------------------------------------------------
# Importación CSV: vista previa y persistencia mediante data.add_hallazgo
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-importar-hallazgos", "is_open"),
    Input("btn-importar-hallazgos", "n_clicks"),
    prevent_initial_call=True,
)
def abrir_importacion_hallazgos(n_clicks):
    return bool(n_clicks)


@dash.callback(
    Output("modal-importar-hallazgos", "is_open", allow_duplicate=True),
    Input("hal-btn-cancelar-import", "n_clicks"),
    prevent_initial_call=True,
)
def cancelar_importacion_hallazgos(_n_clicks):
    return False


@dash.callback(
    Output("hal-download-template", "data"),
    Input("hal-btn-descargar-plantilla", "n_clicks"),
    prevent_initial_call=True,
)
def descargar_plantilla_hallazgos(_n_clicks):
    return dict(content=template_csv(), filename="plantilla_hallazgos_sentinel.csv", type="text/csv")


@dash.callback(
    Output("hal-import-preview", "data"),
    Output("hal-import-error", "children"),
    Output("hal-import-summary", "children"),
    Output("hal-import-table", "data"),
    Output("hal-import-table", "selected_rows"),
    Output("hal-import-selection-actions", "style"),
    Input("hal-import-upload", "contents"),
    State("hal-import-upload", "filename"),
    State("hal-import-proyecto", "value"),
    State("store-hallazgos", "data"),
    prevent_initial_call=True,
)
def previsualizar_importacion_hallazgos(contents, filename, proyecto, store_json):
    if not contents:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    resultado = validate_hallazgos_csv(
        contents, filename, hallazgos_from_store(store_json).to_dict("records"), proyecto
    )
    if resultado["error"]:
        error = dbc.Alert(resultado["error"], color="danger", className="mb-0")
        return [], error, None, [], [], {"display": "none"}

    rows = resultado["rows"]
    validos = sum(row["valido"] for row in rows)
    duplicados = sum(row["duplicado"] for row in rows)
    errores = len(rows) - validos
    summary = dbc.Alert([
        html.Strong(f"Archivo: {filename}. "),
        f"{len(rows)} registros encontrados · ",
        html.Span(f"✓ {validos} válidos", className="me-2"),
        html.Span(f"⚠ {duplicados} posibles duplicados", className="me-2"),
        html.Span(f"✕ {errores} con error"),
    ], color="light", className="mb-0")
    selected = [index for index, row in enumerate(rows) if row["valido"]]
    return rows, None, summary, rows, selected, {"display": "block"}


@dash.callback(
    Output("hal-import-table", "selected_rows", allow_duplicate=True),
    Input("hal-import-select-all", "n_clicks"),
    Input("hal-import-select-none", "n_clicks"),
    State("hal-import-preview", "data"),
    prevent_initial_call=True,
)
def seleccionar_registros_importacion(_select_all, _select_none, rows):
    if dash.ctx.triggered_id == "hal-import-select-none":
        return []
    return [index for index, row in enumerate(rows or []) if row.get("valido")]


@dash.callback(
    Output("hal-btn-importar-seleccionados", "disabled"),
    Input("hal-import-table", "selected_rows"),
    State("hal-import-preview", "data"),
)
def habilitar_importacion_hallazgos(selected_rows, rows):
    return not any((rows or [])[index].get("valido") for index in (selected_rows or []) if index < len(rows or []))


@dash.callback(
    Output("modal-confirmar-importacion", "is_open"),
    Output("hal-import-confirm-body", "children"),
    Input("hal-btn-importar-seleccionados", "n_clicks"),
    State("hal-import-table", "selected_rows"),
    State("hal-import-preview", "data"),
    prevent_initial_call=True,
)
def confirmar_importacion_hallazgos(n_clicks, selected_rows, rows):
    seleccionados = [rows[index] for index in (selected_rows or []) if index < len(rows or []) and rows[index].get("valido")]
    if not n_clicks or not seleccionados:
        return False, dash.no_update
    return True, f"Se importarán {len(seleccionados)} hallazgos al proyecto seleccionado. ¿Deseas continuar?"


@dash.callback(
    Output("modal-confirmar-importacion", "is_open", allow_duplicate=True),
    Input("hal-btn-cancelar-confirm-import", "n_clicks"),
    prevent_initial_call=True,
)
def cancelar_confirmacion_importacion(_n_clicks):
    return False


@dash.callback(
    Output("store-hallazgos", "data", allow_duplicate=True),
    Output("modal-importar-hallazgos", "is_open", allow_duplicate=True),
    Output("modal-confirmar-importacion", "is_open", allow_duplicate=True),
    Output("hal-toast", "children", allow_duplicate=True),
    Output("hal-toast", "icon", allow_duplicate=True),
    Output("hal-toast", "is_open", allow_duplicate=True),
    Input("hal-btn-confirmar-import", "n_clicks"),
    State("hal-import-proyecto", "value"),
    State("hal-import-table", "selected_rows"),
    State("hal-import-preview", "data"),
    prevent_initial_call=True,
)
def importar_hallazgos_csv(n_clicks, proyecto, selected_rows, rows):
    if not n_clicks:
        return (dash.no_update,) * 6
    seleccionados = [rows[index] for index in (selected_rows or []) if index < len(rows or []) and rows[index].get("valido")]
    if not proyecto or not seleccionados:
        return dash.no_update, True, False, "No hay registros válidos seleccionados para importar.", "danger", True

    importados, errores = 0, []
    for row in seleccionados:
        try:
            ok, message = data_mod.add_hallazgo(
                proyecto=proyecto, motor=row["Motor"], script=row["Script"], funcion=row["Función"],
                descripcion=row["Descripción"], estado=row["Estado"],
                fecha_hallazgo=dt.date.fromisoformat(row["Fecha hallazgo"]),
                fecha_cierre=dt.date.fromisoformat(row["Fecha cierre"]) if row["Fecha cierre"] else None,
            )
        except (TypeError, ValueError):
            ok, message = False, f"Fila {row['linea']}: no fue posible procesar las fechas."
        if ok:
            importados += 1
        else:
            errores.append(f"Fila {row['linea']}: {message}")

    nuevo_store = hallazgos_to_store(data_mod.load_hallazgos()) if importados else dash.no_update
    if errores:
        message = f"{importados} hallazgos importados. {len(errores)} registro(s) no pudieron ser procesados: " + " ".join(errores[:3])
        icon = "warning" if importados else "danger"
    else:
        message, icon = f"✓ {importados} hallazgos importados correctamente.", "success"
    return nuevo_store, False, False, message, icon, True
