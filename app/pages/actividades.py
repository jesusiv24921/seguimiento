"""Actividades — histórico completo, explorable con orden/filtro/exportación."""
from __future__ import annotations

import datetime as dt
import re

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dash_table, dcc, html

import data as data_mod
from components import badge_estado, badge_prioridad, chart_card, kpi_card, page_header
from data_store import apply_all_filters, df_from_store, df_to_store, lookups_from_store
from theme import ESTADO_PILL, GRID, INK_MUTED, INK_PRIMARY, PRIORIDAD_PILL

dash.register_page(__name__, path="/actividades", name="Actividades", title="Actividades")

ESTADOS_FORM = ["Bloqueado", "Completado", "En progreso"]
PRIORIDADES_FORM = ["Alta", "Media", "Baja"]
ESTADOS_FILTRO = ["Completado", "En progreso", "Pendiente", "Bloqueado", "Sin estado"]
PRIORIDADES_FILTRO = ["Alta", "Media", "Baja", "Sin prioridad"]
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
    html.Div(className="act-page-header", children=[
        page_header("Actividades", "Registro detallado de actividades desarrolladas.",
                    period_id="page-header-period"),
        dbc.Button([html.I(className="bi bi-plus-lg"), "Nueva actividad"],
                   id="btn-nueva-actividad", className="btn-refresh", n_clicks=0),
    ]),
    chart_card([
        html.Div([html.I(className="bi bi-sliders"), "Filtros de actividades"], className="section-title"),
        html.Div("El período se aplica desde los filtros globales superiores.", className="section-caption mb-2"),
        dbc.Row([
            dbc.Col(_campo("Proyecto", "bi bi-folder2", dcc.Dropdown(id="act-f-proyecto", multi=True,
                    placeholder="Todos los proyectos")), md=3),
            dbc.Col(_campo("Estado", "bi bi-flag", dcc.Dropdown(id="act-f-estado", options=ESTADOS_FILTRO,
                    multi=True, placeholder="Todos los estados")), md=2),
            dbc.Col(_campo("Prioridad", "bi bi-exclamation-circle", dcc.Dropdown(id="act-f-prioridad",
                    options=PRIORIDADES_FILTRO, multi=True, placeholder="Todas las prioridades")), md=2),
            dbc.Col(_campo("Buscar", "bi bi-search", dbc.Input(id="act-f-buscar", type="text", debounce=True,
                    placeholder="Buscar actividad...")), md=4),
            dbc.Col(dbc.Button([html.I(className="bi bi-x-circle"), "Limpiar"], id="act-btn-limpiar-filtros",
                    className="btn-cal-nav w-100 mt-4"), md=1),
        ], className="g-2"),
    ], className="act-filters-card"),
    html.Div(className="kpi-grid act-kpi-grid", children=[
        kpi_card("act-kpi-total", "Actividades", "bi bi-list-check", context_id="act-kpi-total-ctx"),
        kpi_card("act-kpi-completadas", "Completadas", "bi bi-check2-circle", tone="tone-good", context_id="act-kpi-completadas-ctx"),
        kpi_card("act-kpi-progreso", "En progreso", "bi bi-arrow-repeat", tone="tone-warning", context_id="act-kpi-progreso-ctx"),
        kpi_card("act-kpi-pendientes", "Pendientes", "bi bi-flag", tone="tone-critical", context_id="act-kpi-pendientes-ctx"),
        kpi_card("act-kpi-horas", "Horas registradas", "bi bi-clock-history", context_id="act-kpi-horas-ctx"),
        kpi_card("act-kpi-proyectos", "Proyectos activos", "bi bi-folder2-open", context_id="act-kpi-proyectos-ctx"),
    ]),
    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-table"), "Histórico de actividades"], className="section-title"),
            dbc.Button([html.I(className="bi bi-pencil"), "Editar"],
                        id="btn-editar-actividad", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-trash"), "Eliminar"],
                        id="btn-eliminar-actividad", className="btn-refresh", disabled=True),
            html.Div(id="act-selection-msg", className="hal-selection-msg"),
        ], style={"justifyContent": "space-between", "alignItems": "center"}),
        html.Div("Selecciona una fila con la casilla para editarla o eliminarla, o haz clic en cualquier celda "
                  "para ver el detalle completo. Ordena, filtra por columna o exporta a CSV con los controles "
                  "de la tabla.", className="section-caption"),
        html.Div(className="table-desktop-only", children=[
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
        html.Div(id="act-tabla-cards", className="table-mobile-only"),
    ]),
    nueva_actividad_modal,
    eliminar_actividad_modal,
    act_toast,
    dcc.Store(id="store-actividad-seleccionada"),
    dcc.Store(id="store-actividad-form-mode"),
    dcc.Store(id="act-clicks-baseline"),
])


def _actividad_card(idx: int, row: dict) -> html.Div:
    """Tarjeta con el mismo contenido que una fila de act-tabla, para pantallas
    angostas/verticales. Tocar el cuerpo abre el detalle (igual que hacer clic
    en una celda de la tabla); el botón "Seleccionar" escribe en
    act-tabla.selected_rows para editar/eliminar, igual que la casilla de la
    tabla — así no se duplica ninguna lógica de selección."""
    return html.Div(className="hal-card", children=[
        html.Div(className="hal-card-body-clickable",
                  id={"type": "act-card-view", "index": idx}, n_clicks=0, children=[
            html.Div(className="hal-card-head", children=[
                badge_estado(row["estado"]), badge_prioridad(row["prioridad"]),
            ]),
            html.Div(row["actividad"], className="hal-card-desc"),
            html.Div(className="hal-card-meta-grid", children=[
                html.Div([html.Span("ID", className="hal-card-meta-label"),
                           html.Span(row["actividad_id"], className="hal-card-meta-value")]),
                html.Div([html.Span("Fecha", className="hal-card-meta-label"),
                           html.Span(row["fecha_txt"], className="hal-card-meta-value")]),
                html.Div([html.Span("Horario", className="hal-card-meta-label"),
                           html.Span(row["horario_txt"], className="hal-card-meta-value")]),
                html.Div([html.Span("Proyecto", className="hal-card-meta-label"),
                           html.Span(row["proyecto"], className="hal-card-meta-value")]),
                html.Div([html.Span("Tema", className="hal-card-meta-label"),
                           html.Span(row["tema"], className="hal-card-meta-value")]),
            ]),
        ]),
        dbc.Button("Seleccionar", id={"type": "act-card-select", "index": idx},
                    className="btn-refresh btn-sm-card", size="sm", n_clicks=0),
    ])


@dash.callback(
    Output("act-f-proyecto", "options"),
    Input("store-data", "data"),
)
def update_activity_filter_options(store_json):
    df = df_from_store(store_json)
    if df.empty:
        return []
    return [{"label": proyecto, "value": proyecto}
            for proyecto in sorted(df["proyecto"].dropna().unique())]


@dash.callback(
    Output("act-f-proyecto", "value"),
    Output("act-f-estado", "value"),
    Output("act-f-prioridad", "value"),
    Output("act-f-buscar", "value"),
    Input("act-btn-limpiar-filtros", "n_clicks"),
    prevent_initial_call=True,
)
def clear_activity_filters(_n_clicks):
    return [], [], [], ""


@dash.callback(
    Output("act-kpi-total", "children"),
    Output("act-kpi-total-ctx", "children"),
    Output("act-kpi-completadas", "children"),
    Output("act-kpi-completadas-ctx", "children"),
    Output("act-kpi-progreso", "children"),
    Output("act-kpi-progreso-ctx", "children"),
    Output("act-kpi-pendientes", "children"),
    Output("act-kpi-pendientes-ctx", "children"),
    Output("act-kpi-horas", "children"),
    Output("act-kpi-horas-ctx", "children"),
    Output("act-kpi-proyectos", "children"),
    Output("act-kpi-proyectos-ctx", "children"),
    Output("act-tabla", "data"),
    Output("act-tabla-cards", "children"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
    Input("act-f-proyecto", "value"),
    Input("act-f-estado", "value"),
    Input("act-f-prioridad", "value"),
    Input("act-f-buscar", "value"),
)
def update_actividades(store_json, start_date, end_date, proyectos, estados, prioridades, buscar):
    df = df_from_store(store_json)
    if df.empty:
        return "0", "Sin registros", "0", "0%", "0", "0%", "0", "0%", "0.0 h", "Sin horas", "0", "Sin proyectos", [], []

    filtered = apply_all_filters(df, start_date, end_date)
    if proyectos:
        filtered = filtered[filtered["proyecto"].isin(proyectos)]
    if estados:
        filtered = filtered[filtered["estado"].isin(estados)]
    if prioridades:
        filtered = filtered[filtered["prioridad"].isin(prioridades)]
    if buscar and buscar.strip():
        query = buscar.strip().lower()
        searchable = ["actividad", "tema", "descripcion", "resultado", "proyecto"]
        mask = pd.Series(False, index=filtered.index)
        for col in searchable:
            mask |= filtered[col].fillna("").astype(str).str.lower().str.contains(query, regex=False)
        filtered = filtered[mask]

    total = len(filtered)
    completadas = int(filtered["estado"].eq("Completado").sum())
    progreso = int(filtered["estado"].eq("En progreso").sum())
    pendientes = int(filtered["estado"].eq("Pendiente").sum())
    horas = float(filtered["horas"].dropna().sum())
    dias_con_registro = max(int(filtered["fecha_inicio"].nunique()), 1)
    proyectos_activos = int(filtered["proyecto"].dropna().nunique())

    def porcentaje(valor):
        return f"{valor / total * 100:.0f}% del período" if total else "0% del período"

    tabla = filtered.copy()
    tabla["fecha_txt"] = tabla["fecha_inicio"].dt.strftime("%d/%m/%Y")
    tabla["horario_txt"] = tabla["hora_inicio_txt"].fillna("—") + " — " + tabla["hora_fin_txt"].fillna("—")
    tabla["horas_txt"] = tabla["horas"].apply(lambda h: f"{h:.1f} h" if pd.notna(h) else "Sin horas registradas")
    tabla = tabla.sort_values("fecha_inicio", ascending=False)
    tabla["id"] = tabla["actividad_id"]

    cols = ["id", "actividad_id", "fecha_txt", "horario_txt", "horas_txt", "proyecto",
            "actividad", "tema", "estado", "prioridad"]
    tabla_data = tabla[cols].to_dict("records")
    cards = [_actividad_card(i, fila) for i, fila in enumerate(tabla_data)]
    return (str(total), "Resultado de los filtros", str(completadas), porcentaje(completadas),
            str(progreso), porcentaje(progreso), str(pendientes), porcentaje(pendientes),
            f"{horas:.1f} h", f"Promedio {horas / dias_con_registro:.1f} h/día" if total else "Sin horas",
            str(proyectos_activos), "En el período filtrado", tabla_data, cards)


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
# Vista móvil (tarjetas): tocar el cuerpo abre el detalle, igual que un clic
# en la tabla; el botón "Seleccionar" marca la fila en act-tabla.selected_rows
# para poder editarla/eliminarla — ambos reutilizan la lógica ya existente.
# --------------------------------------------------------------------------
@dash.callback(
    Output("store-selected-activity", "data", allow_duplicate=True),
    Input({"type": "act-card-view", "index": ALL}, "n_clicks"),
    State("act-tabla", "data"),
    prevent_initial_call=True,
)
def ver_detalle_actividad_desde_card(n_clicks_list, table_data):
    if not n_clicks_list or not any(n_clicks_list):
        return dash.no_update
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update
    idx = triggered["index"]
    if not table_data or idx >= len(table_data):
        return dash.no_update
    return table_data[idx]["actividad_id"]


@dash.callback(
    Output("act-tabla", "selected_rows", allow_duplicate=True),
    Input({"type": "act-card-select", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def seleccionar_actividad_desde_card(n_clicks_list):
    if not n_clicks_list or not any(n_clicks_list):
        return dash.no_update
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update
    return [triggered["index"]]


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
    State("act-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_nueva_actividad(n_clicks, baseline):
    umbral = (baseline or {}).get("btn-nueva-actividad", 0)
    if not n_clicks or n_clicks <= umbral:
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
    State("act-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_editar_actividad(n_clicks, actividad_id, store_json, baseline):
    vacio = (dash.no_update,) * 18
    umbral = (baseline or {}).get("btn-editar-actividad", 0)
    if not n_clicks or n_clicks <= umbral or not actividad_id:
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
def guardar_nueva_actividad(n_clicks, modo_edicion, fecha, hora_inicio_txt, hora_fin_txt, proyecto_id, tipo_id,
                             categoria_id, titulo, tema, descripcion, resultado, estado, prioridad,
                             motor, observaciones):
    if not n_clicks:
        # Dash puede invocar callbacks con prevent_initial_call=True al entrar a una
        # página en apps multi-página (github.com/plotly/dash/issues/1513); sin esta
        # guarda, esa invocación fantasma con campos vacíos cae en la primera
        # validación de error() y esta, para dejar corregir el formulario, pone
        # is_open=True — abriendo el modal solo, con un error, sin que nadie lo pida.
        return (dash.no_update,) * 6

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
    State("act-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def open_eliminar_actividad(n_clicks, actividad_id, store_json, baseline):
    umbral = (baseline or {}).get("btn-eliminar-actividad", 0)
    if not n_clicks or n_clicks <= umbral or not actividad_id:
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
def confirmar_eliminar_actividad(n_clicks, actividad_id):
    if not n_clicks:
        return (dash.no_update,) * 5
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
    Output("act-form-error", "children", allow_duplicate=True),
    Output("act-tabla", "selected_rows", allow_duplicate=True),
    Output("act-clicks-baseline", "data"),
    Input("url", "pathname"),
    State("btn-nueva-actividad", "n_clicks"),
    State("btn-editar-actividad", "n_clicks"),
    State("btn-eliminar-actividad", "n_clicks"),
    prevent_initial_call=True,
)
def cerrar_modales_al_entrar(pathname, n_nueva, n_editar, n_eliminar):
    if pathname != "/actividades":
        return (dash.no_update,) * 5
    baseline = {
        "btn-nueva-actividad": n_nueva or 0,
        "btn-editar-actividad": n_editar or 0,
        "btn-eliminar-actividad": n_eliminar or 0,
    }
    return False, False, None, [], baseline
