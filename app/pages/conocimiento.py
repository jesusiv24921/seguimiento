"""Centro de Conocimiento — estudio, soluciones, conceptos, notas.

Mismo patrón que Hallazgos: fuente de verdad la pestaña CONOCIMIENTO (y
CONOCIMIENTO_ARCHIVOS) de seguimiento.xlsx, escritura real vía knowledge.py,
selección de fila reutilizada por Editar/Eliminar, vista de tarjetas en
pantallas angostas, y guardas contra el disparo fantasma de callbacks al
entrar a la página (dash/#1513).
"""
from __future__ import annotations

import base64

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, dash_table, dcc, html

import data as data_mod
import knowledge as km
from components import badge_conocimiento_estado, chart_card, kpi_card, page_header
from data_store import lookups_from_store
from theme import CONOCIMIENTO_ESTADO_PILL, GRID, INK_MUTED, INK_PRIMARY

dash.register_page(__name__, path="/conocimiento", name="Conocimiento", title="Conocimiento")

layout = html.Div(className="page", children=[
    page_header("Centro de Conocimiento",
                 "Estudio, soluciones, errores y aprendizajes, conceptos, procedimientos, ideas, "
                 "referencias y notas — tuyo, buscable, y conectado con tus proyectos."),

    html.Div([
        kpi_card("con-kpi-total", "Entradas totales", "bi bi-journal-bookmark"),
        kpi_card("con-kpi-estudio", "En estudio", "bi bi-book", tone="tone-warning"),
        kpi_card("con-kpi-aplicado", "Aprendido / Aplicado", "bi bi-check2-circle", tone="tone-good"),
        kpi_card("con-kpi-global", "De ámbito global", "bi bi-globe"),
    ], className="kpi-grid"),

    html.Div(className="filters-panel", children=[
        html.Div([html.I(className="bi bi-sliders"), "Filtros de conocimiento"], className="filters-panel-title"),
        html.Div(className="filters-grid", children=[
            html.Div([
                html.Div([html.I(className="bi bi-search"), "Buscar"], className="filter-label"),
                dbc.Input(id="con-f-query", type="text", placeholder="Título, contenido, etiquetas..."),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-tags"), "Categoría"], className="filter-label"),
                dcc.Dropdown(id="con-f-categoria", options=km.CATEGORIAS, multi=True, placeholder="Todas"),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                dcc.Dropdown(id="con-f-estado", options=km.ESTADOS, multi=True, placeholder="Todos"),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-folder2"), "Proyecto"], className="filter-label"),
                dcc.Dropdown(id="con-f-proyecto", multi=True, placeholder="Todos"),
            ], className="filter-field"),
        ]),
    ]),

    chart_card([
        html.Div(className="hal-actions-row", children=[
            html.Div([html.I(className="bi bi-list-ul"), "Entradas de conocimiento"], className="section-title"),
            dbc.Button([html.I(className="bi bi-eye"), "Ver detalle"],
                        id="btn-ver-conocimiento", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-pencil"), "Editar"],
                        id="btn-editar-conocimiento", className="btn-refresh", disabled=True),
            dbc.Button([html.I(className="bi bi-trash"), "Eliminar"],
                        id="btn-eliminar-conocimiento", className="btn-refresh", disabled=True),
            html.Div(id="con-selection-msg", className="hal-selection-msg"),
            dbc.Button([html.I(className="bi bi-plus-lg"), "Nuevo conocimiento"],
                        id="btn-nuevo-conocimiento", className="btn-refresh ms-auto", n_clicks=0),
        ]),
        html.Div("Selecciona una entrada con la casilla para ver el detalle, editarla o eliminarla.",
                  className="section-caption"),
        html.Div(className="table-desktop-only", children=[
            dash_table.DataTable(
                id="con-tabla",
                columns=[
                    {"name": "Título", "id": "titulo"},
                    {"name": "Categoría", "id": "categoria"},
                    {"name": "Estado", "id": "estado"},
                    {"name": "Ámbito", "id": "ambito"},
                    {"name": "Proyectos", "id": "proyectos"},
                    {"name": "Actualizado", "id": "fecha_actualizacion_txt"},
                ],
                row_selectable="single",
                page_size=12,
                sort_action="native",
                filter_action="native",
                export_format="csv",
                export_headers="display",
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
                    + [{"if": {"filter_query": f'{{estado}} = "{k}"', "column_id": "estado"},
                        "backgroundColor": v["bg"], "color": v["fg"], "fontWeight": "600"}
                       for k, v in CONOCIMIENTO_ESTADO_PILL.items()]
                ),
                style_cell_conditional=[{"if": {"column_id": "titulo"}, "minWidth": "220px"},
                                         {"if": {"column_id": "estado"}, "maxWidth": "130px"}],
            ),
        ]),
        html.Div(id="con-tabla-cards", className="table-mobile-only"),
    ]),

    dcc.Store(id="store-conocimiento-seleccionado"),
    dcc.Store(id="con-clicks-baseline"),

    # ---- Alta / edición ----
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(html.Span("Nuevo conocimiento", id="con-form-modal-title")), close_button=True),
        dbc.ModalBody([
            html.Div(id="con-form-error"),
            html.Div([html.Div([html.I(className="bi bi-card-text"), "Título"], className="filter-label"),
                       dbc.Input(id="con-form-titulo", type="text", placeholder="p.ej. FastAPI")], className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-text-paragraph"), "Descripción breve"], className="filter-label"),
                       dbc.Input(id="con-form-descripcion-breve", type="text",
                                  placeholder="Una línea que resuma la entrada")], className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-journal-text"), "Contenido"], className="filter-label"),
                       dbc.Textarea(id="con-form-contenido", placeholder="Markdown libre: conceptos, código, notas...",
                                     style={"height": "160px"})], className="mb-3"),
            dbc.Row([
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-tags"), "Categoría"], className="filter-label"),
                                    dcc.Dropdown(id="con-form-categoria", options=km.CATEGORIAS,
                                                  value="Estudio", clearable=False)], className="mb-3"), md=4),
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-flag"), "Estado"], className="filter-label"),
                                    dcc.Dropdown(id="con-form-estado", options=km.ESTADOS,
                                                  value="En estudio", clearable=False)], className="mb-3"), md=4),
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-globe"), "Ámbito"], className="filter-label"),
                                    dcc.Dropdown(id="con-form-ambito", options=km.AMBITOS,
                                                  value="Global", clearable=False)], className="mb-3"), md=4),
            ]),
            html.Div([html.Div([html.I(className="bi bi-folder2"), "Proyectos relacionados"], className="filter-label"),
                       dcc.Dropdown(id="con-form-proyectos", multi=True, placeholder="Ninguno (opcional)")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-tag"), "Etiquetas"], className="filter-label"),
                       dbc.Input(id="con-form-etiquetas", type="text", placeholder="separadas por coma")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-link-45deg"), "Fuente (opcional)"], className="filter-label"),
                       dbc.Input(id="con-form-fuente", type="text", placeholder="URL o referencia")],
                       className="mb-3"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-conocimiento", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Guardar"],
                        id="btn-guardar-conocimiento", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-conocimiento", is_open=False, size="lg", scrollable=True),

    # ---- Detalle + acciones IA + archivos ----
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle(html.Span("Detalle", id="con-detalle-titulo")), close_button=True),
        dbc.ModalBody(id="con-detalle-body"),
    ], id="modal-detalle-conocimiento", is_open=False, size="lg", scrollable=True),

    # ---- Eliminar ----
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("¿Eliminar esta entrada?"), close_button=True),
        dbc.ModalBody(id="con-eliminar-modal-body"),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-eliminar-conocimiento", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-trash"), "Eliminar definitivamente"],
                        id="btn-confirmar-eliminar-conocimiento", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-eliminar-conocimiento", is_open=False),

    dbc.Toast(
        id="con-toast", header="Conocimiento", is_open=False, dismissable=True, duration=6000,
        style={"position": "fixed", "top": 20, "right": 20, "zIndex": 999, "minWidth": "320px"},
    ),
])


def _campos_vacios():
    return (None, "", "", "", "Estudio", "En estudio", "Global", [], "", "")


def _con_card(idx: int, row: dict) -> html.Div:
    pill = CONOCIMIENTO_ESTADO_PILL.get(row["estado"], {"bg": "#eee", "fg": "#333"})
    return html.Div(className="hal-card", children=[
        html.Div(className="hal-card-head", children=[
            html.Span(row["estado"], className="status-pill",
                       style={"backgroundColor": pill["bg"], "color": pill["fg"]}),
            html.Span(row["categoria"], className="hal-card-motor"),
        ]),
        html.Div(row["titulo"], className="hal-card-desc"),
        html.Div(className="hal-card-meta-grid", children=[
            html.Div([html.Span("Ámbito", className="hal-card-meta-label"),
                       html.Span(row["ambito"], className="hal-card-meta-value")]),
            html.Div([html.Span("Proyectos", className="hal-card-meta-label"),
                       html.Span(row["proyectos"] or "—", className="hal-card-meta-value")]),
            html.Div([html.Span("Actualizado", className="hal-card-meta-label"),
                       html.Span(row["fecha_actualizacion_txt"], className="hal-card-meta-value")]),
        ]),
        dbc.Button("Seleccionar", id={"type": "con-card-select", "index": idx},
                    className="btn-refresh btn-sm-card", size="sm", n_clicks=0),
    ])


# --------------------------------------------------------------------------
# Opciones de filtros / formularios (catálogo real de proyectos)
# --------------------------------------------------------------------------
@dash.callback(
    Output("con-f-proyecto", "options"),
    Output("con-form-proyectos", "options"),
    Input("store-lookups", "data"),
)
def update_conocimiento_proyecto_options(lookups_json):
    lookups = lookups_from_store(lookups_json)
    opts = [{"label": r["proyecto"], "value": r["proyecto"]} for r in lookups["proyectos"]]
    return opts, opts


# --------------------------------------------------------------------------
# KPIs + tabla + tarjetas
# --------------------------------------------------------------------------
@dash.callback(
    Output("con-kpi-total", "children"),
    Output("con-kpi-estudio", "children"),
    Output("con-kpi-aplicado", "children"),
    Output("con-kpi-global", "children"),
    Output("con-tabla", "data"),
    Output("con-tabla-cards", "children"),
    Input("store-conocimiento", "data"),
    Input("con-f-query", "value"),
    Input("con-f-categoria", "value"),
    Input("con-f-estado", "value"),
    Input("con-f-proyecto", "value"),
)
def update_conocimiento(store_json, query, categorias, estados, proyectos):
    from data_store import knowledge_from_store
    df = knowledge_from_store(store_json)
    if df.empty:
        return "0", "0", "0", "0", [], []

    filtered = df
    if query:
        q = query.strip().lower()
        filtered = filtered[
            filtered["titulo"].fillna("").str.lower().str.contains(q, regex=False)
            | filtered["descripcion_breve"].fillna("").str.lower().str.contains(q, regex=False)
            | filtered["contenido"].fillna("").str.lower().str.contains(q, regex=False)
            | filtered["etiquetas"].fillna("").str.lower().str.contains(q, regex=False)
        ]
    if categorias:
        filtered = filtered[filtered["categoria"].isin(categorias)]
    if estados:
        filtered = filtered[filtered["estado"].isin(estados)]
    if proyectos:
        filtered = filtered[filtered["proyectos"].fillna("").apply(
            lambda p: any(pr.strip() in [x.strip() for x in p.split(",")] for pr in proyectos))]

    total = len(filtered)
    en_estudio = int(filtered["estado"].eq("En estudio").sum())
    aplicado = int(filtered["estado"].isin(["Aprendido", "Aplicado"]).sum())
    global_n = int(filtered["ambito"].eq("Global").sum())

    tabla = filtered.copy()
    tabla["fecha_actualizacion_txt"] = tabla["fecha_actualizacion"].dt.strftime("%d/%m/%Y").fillna("—")
    tabla = tabla.sort_values("fecha_actualizacion", ascending=False)
    cols = ["conocimiento_id", "titulo", "categoria", "estado", "ambito", "proyectos",
            "fecha_actualizacion_txt"]
    tabla_data = tabla[cols].to_dict("records")
    cards = [_con_card(i, fila) for i, fila in enumerate(tabla_data)]

    return str(total), str(en_estudio), str(aplicado), str(global_n), tabla_data, cards


# --------------------------------------------------------------------------
# Selección (tabla + tarjetas comparten el mismo prop con la tabla)
# --------------------------------------------------------------------------
@dash.callback(
    Output("con-tabla", "selected_rows", allow_duplicate=True),
    Input({"type": "con-card-select", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def seleccionar_conocimiento_desde_card(n_clicks_list):
    if not n_clicks_list or not any(n_clicks_list):
        return dash.no_update
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update
    return [triggered["index"]]


@dash.callback(
    Output("btn-ver-conocimiento", "disabled"),
    Output("btn-editar-conocimiento", "disabled"),
    Output("btn-eliminar-conocimiento", "disabled"),
    Output("con-selection-msg", "children"),
    Output("store-conocimiento-seleccionado", "data"),
    Input("con-tabla", "selected_rows"),
    State("con-tabla", "data"),
)
def update_conocimiento_selection(selected_rows, table_data):
    selected_rows = selected_rows or []
    if len(selected_rows) != 1:
        msg = "Selecciona una entrada para continuar." if len(selected_rows) == 0 \
            else "Selecciona únicamente una entrada."
        return True, True, True, msg, None
    idx = selected_rows[0]
    if not table_data or idx >= len(table_data):
        return True, True, True, "Selecciona una entrada para continuar.", None
    return False, False, False, "", table_data[idx]["conocimiento_id"]


# --------------------------------------------------------------------------
# Reset al entrar a la página (evita callbacks fantasma de dash/#1513)
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-conocimiento", "is_open", allow_duplicate=True),
    Output("modal-detalle-conocimiento", "is_open", allow_duplicate=True),
    Output("modal-eliminar-conocimiento", "is_open", allow_duplicate=True),
    Output("con-form-error", "children", allow_duplicate=True),
    Output("con-tabla", "selected_rows", allow_duplicate=True),
    Output("con-clicks-baseline", "data"),
    Input("url", "pathname"),
    State("btn-nuevo-conocimiento", "n_clicks"),
    State("btn-editar-conocimiento", "n_clicks"),
    State("btn-eliminar-conocimiento", "n_clicks"),
    State("btn-ver-conocimiento", "n_clicks"),
    prevent_initial_call=True,
)
def cerrar_modales_al_entrar(pathname, n_nuevo, n_editar, n_eliminar, n_ver):
    if pathname != "/conocimiento":
        return (dash.no_update,) * 6
    baseline = {
        "btn-nuevo-conocimiento": n_nuevo or 0, "btn-editar-conocimiento": n_editar or 0,
        "btn-eliminar-conocimiento": n_eliminar or 0, "btn-ver-conocimiento": n_ver or 0,
    }
    return False, False, False, None, [], baseline


# --------------------------------------------------------------------------
# Nuevo / editar: abrir, cancelar, guardar
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-conocimiento", "is_open"),
    Output("con-form-error", "children"),
    Output("con-form-titulo", "value"),
    Output("con-form-descripcion-breve", "value"),
    Output("con-form-contenido", "value"),
    Output("con-form-categoria", "value"),
    Output("con-form-estado", "value"),
    Output("con-form-ambito", "value"),
    Output("con-form-proyectos", "value"),
    Output("con-form-etiquetas", "value"),
    Output("con-form-fuente", "value"),
    Output("con-form-modal-title", "children"),
    Input("btn-nuevo-conocimiento", "n_clicks"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_nuevo_conocimiento(n_clicks, baseline):
    umbral = (baseline or {}).get("btn-nuevo-conocimiento", 0)
    if not n_clicks or n_clicks <= umbral:
        return (dash.no_update,) * 12
    return (True, None, *_campos_vacios(), "Nuevo conocimiento")


@dash.callback(
    Output("modal-conocimiento", "is_open", allow_duplicate=True),
    Output("con-form-error", "children", allow_duplicate=True),
    Output("con-form-titulo", "value", allow_duplicate=True),
    Output("con-form-descripcion-breve", "value", allow_duplicate=True),
    Output("con-form-contenido", "value", allow_duplicate=True),
    Output("con-form-categoria", "value", allow_duplicate=True),
    Output("con-form-estado", "value", allow_duplicate=True),
    Output("con-form-ambito", "value", allow_duplicate=True),
    Output("con-form-proyectos", "value", allow_duplicate=True),
    Output("con-form-etiquetas", "value", allow_duplicate=True),
    Output("con-form-fuente", "value", allow_duplicate=True),
    Output("con-form-modal-title", "children", allow_duplicate=True),
    Input("btn-editar-conocimiento", "n_clicks"),
    State("store-conocimiento-seleccionado", "data"),
    State("store-conocimiento", "data"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_editar_conocimiento(n_clicks, conocimiento_id, store_json, baseline):
    from data_store import knowledge_from_store
    vacio = (dash.no_update,) * 12
    umbral = (baseline or {}).get("btn-editar-conocimiento", 0)
    if not n_clicks or n_clicks <= umbral or not conocimiento_id:
        return vacio
    df = knowledge_from_store(store_json)
    fila = df[df["conocimiento_id"] == conocimiento_id]
    if fila.empty:
        return vacio
    r = fila.iloc[0]
    proyectos_list = [p.strip() for p in (r["proyectos"] or "").split(",") if p.strip()]
    return (True, None, r["titulo"], r["descripcion_breve"], r["contenido"], r["categoria"],
            r["estado"], r["ambito"], proyectos_list, r["etiquetas"] or "", r["fuente"] or "",
            f"Editar: {r['titulo']}")


@dash.callback(
    Output("modal-conocimiento", "is_open", allow_duplicate=True),
    Input("btn-cancelar-conocimiento", "n_clicks"),
    prevent_initial_call=True,
)
def cancelar_conocimiento(_n_clicks):
    return False


@dash.callback(
    Output("store-conocimiento", "data", allow_duplicate=True),
    Output("modal-conocimiento", "is_open", allow_duplicate=True),
    Output("con-form-error", "children", allow_duplicate=True),
    Output("con-toast", "children", allow_duplicate=True),
    Output("con-toast", "icon", allow_duplicate=True),
    Output("con-toast", "is_open", allow_duplicate=True),
    Input("btn-guardar-conocimiento", "n_clicks"),
    State("store-conocimiento-seleccionado", "data"),
    State("con-form-titulo", "value"),
    State("con-form-descripcion-breve", "value"),
    State("con-form-contenido", "value"),
    State("con-form-categoria", "value"),
    State("con-form-estado", "value"),
    State("con-form-ambito", "value"),
    State("con-form-proyectos", "value"),
    State("con-form-etiquetas", "value"),
    State("con-form-fuente", "value"),
    State("con-form-modal-title", "children"),
    prevent_initial_call=True,
)
def guardar_conocimiento(n_clicks, seleccionado_id, titulo, desc_breve, contenido, categoria,
                          estado, ambito, proyectos_list, etiquetas, fuente, modal_title):
    from data_store import knowledge_to_store
    if not n_clicks:
        return (dash.no_update,) * 6

    def error(msg):
        return (dash.no_update, True, html.Div(msg, className="section-caption", style={"color": "#a52323"}),
                dash.no_update, dash.no_update, dash.no_update)

    if not titulo or not titulo.strip():
        return error("Escribe un título.")
    if not contenido or not contenido.strip():
        return error("Escribe el contenido.")

    proyectos_txt = ", ".join(proyectos_list) if proyectos_list else None
    es_edicion = modal_title and str(modal_title).startswith("Editar:")

    if es_edicion:
        if not seleccionado_id:
            return error("No hay ninguna entrada seleccionada.")
        ok, msg = km.update_knowledge(
            seleccionado_id, titulo=titulo.strip(), descripcion_breve=(desc_breve or "").strip(),
            contenido=contenido.strip(), categoria=categoria, estado=estado, ambito=ambito,
            proyectos=proyectos_txt, etiquetas=(etiquetas or "").strip() or None,
            fuente=(fuente or "").strip() or None,
        )
    else:
        ok, msg, _new_id = km.add_knowledge(
            titulo=titulo.strip(), descripcion_breve=(desc_breve or "").strip(), contenido=contenido.strip(),
            categoria=categoria, estado=estado, ambito=ambito, proyectos=proyectos_txt,
            etiquetas=(etiquetas or "").strip() or None, fuente=(fuente or "").strip() or None,
        )
    if not ok:
        return error(msg)

    nuevo_df = km.load_knowledge()
    return knowledge_to_store(nuevo_df), False, None, f"✓ {msg}", "success", True


# --------------------------------------------------------------------------
# Eliminar
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-eliminar-conocimiento", "is_open"),
    Output("con-eliminar-modal-body", "children"),
    Input("btn-eliminar-conocimiento", "n_clicks"),
    State("store-conocimiento-seleccionado", "data"),
    State("store-conocimiento", "data"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_eliminar_conocimiento(n_clicks, conocimiento_id, store_json, baseline):
    from data_store import knowledge_from_store
    umbral = (baseline or {}).get("btn-eliminar-conocimiento", 0)
    if not n_clicks or n_clicks <= umbral or not conocimiento_id:
        return dash.no_update, dash.no_update
    df = knowledge_from_store(store_json)
    fila = df[df["conocimiento_id"] == conocimiento_id]
    if fila.empty:
        return dash.no_update, dash.no_update
    r = fila.iloc[0]
    body = html.Div([
        html.P("Esta acción eliminará la entrada (y sus archivos adjuntos) de forma permanente. "
                "No se puede deshacer.", className="section-caption", style={"color": "#a52323"}),
        html.Div([html.Div("Título", className="modal-field-label"),
                   html.Div(r["titulo"], className="modal-field-value")], className="modal-field"),
    ])
    return True, body


@dash.callback(
    Output("modal-eliminar-conocimiento", "is_open", allow_duplicate=True),
    Input("btn-cancelar-eliminar-conocimiento", "n_clicks"),
    prevent_initial_call=True,
)
def cancelar_eliminar_conocimiento(_n_clicks):
    return False


@dash.callback(
    Output("store-conocimiento", "data", allow_duplicate=True),
    Output("modal-eliminar-conocimiento", "is_open", allow_duplicate=True),
    Output("con-toast", "children", allow_duplicate=True),
    Output("con-toast", "icon", allow_duplicate=True),
    Output("con-toast", "is_open", allow_duplicate=True),
    Input("btn-confirmar-eliminar-conocimiento", "n_clicks"),
    State("store-conocimiento-seleccionado", "data"),
    prevent_initial_call=True,
)
def confirmar_eliminar_conocimiento(n_clicks, conocimiento_id):
    from data_store import knowledge_to_store
    if not n_clicks:
        return (dash.no_update,) * 5
    if not conocimiento_id:
        return dash.no_update, False, "No hay ninguna entrada seleccionada.", "danger", True
    ok, msg = km.delete_knowledge(conocimiento_id)
    if ok:
        nuevo_df = km.load_knowledge()
        return knowledge_to_store(nuevo_df), False, f"✓ {msg}", "success", True
    return dash.no_update, False, msg, "danger", True


# --------------------------------------------------------------------------
# Detalle: contenido, archivos, subir archivo, acciones de IA
# --------------------------------------------------------------------------
def _accion_ia_boton(label: str, icon: str, prompt_tipo: str) -> dbc.Button:
    return dbc.Button([html.I(className=icon), label], size="sm", className="btn-refresh btn-sm-card",
                        id={"type": "con-accion-ia", "index": prompt_tipo}, n_clicks=0)


@dash.callback(
    Output("modal-detalle-conocimiento", "is_open"),
    Output("con-detalle-titulo", "children"),
    Output("con-detalle-body", "children"),
    Input("btn-ver-conocimiento", "n_clicks"),
    Input({"type": "con-archivo-subido", "index": ALL}, "contents"),
    State({"type": "con-archivo-subido", "index": ALL}, "filename"),
    State("store-conocimiento-seleccionado", "data"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_detalle_conocimiento(n_clicks, contents_list, filenames_list, conocimiento_id, baseline):
    umbral = (baseline or {}).get("btn-ver-conocimiento", 0)
    triggered_id = dash.ctx.triggered_id
    es_por_boton = triggered_id == "btn-ver-conocimiento"
    if es_por_boton and (not n_clicks or n_clicks <= umbral):
        return dash.no_update, dash.no_update, dash.no_update
    if not conocimiento_id:
        return dash.no_update, dash.no_update, dash.no_update

    if not es_por_boton and contents_list and any(contents_list):
        idx = [i for i, c in enumerate(contents_list) if c][-1]
        contenido_b64 = contents_list[idx]
        filename = filenames_list[idx]
        _header, encoded = contenido_b64.split(",", 1)
        raw = base64.b64decode(encoded)
        km.add_knowledge_file(conocimiento_id, filename, raw)

    df = km.load_knowledge()
    fila = df[df["conocimiento_id"] == conocimiento_id]
    if fila.empty:
        return dash.no_update, dash.no_update, dash.no_update
    r = fila.iloc[0]

    dfa = km.load_knowledge_files()
    archivos = dfa[dfa["conocimiento_id"] == conocimiento_id]
    lista_archivos = html.Div(className="section-caption", children=[
        html.Div([html.I(className="bi bi-paperclip me-1"), a["nombre_archivo"]])
        for _, a in archivos.iterrows()
    ]) if not archivos.empty else html.Div("Sin archivos adjuntos.", className="section-caption")

    body = html.Div([
        html.Div([badge_conocimiento_estado(r["estado"]),
                   html.Span(r["categoria"], className="hal-card-motor ms-2")],
                  className="d-flex align-items-center gap-2 mb-3"),
        html.Div(r["descripcion_breve"] or "", className="section-caption mb-2"),
        dcc.Markdown(r["contenido"] or "", className="mb-3"),
        html.Div(className="d-flex flex-wrap gap-2 mb-3", children=[
            _accion_ia_boton("Explicarme", "bi bi-mortarboard", "explicar"),
            _accion_ia_boton("Resumir", "bi bi-card-list", "resumir"),
            _accion_ia_boton("Hacerme preguntas", "bi bi-question-circle", "preguntas"),
            _accion_ia_boton("Crear ejercicios", "bi bi-pencil-square", "ejercicios"),
            _accion_ia_boton("Mapa conceptual", "bi bi-diagram-3", "mapa"),
            _accion_ia_boton("Ejemplo de código", "bi bi-code-slash", "codigo"),
            _accion_ia_boton("Qué estudiar después", "bi bi-signpost", "siguiente"),
        ]),
        html.Div("Archivos adjuntos", className="section-title"),
        lista_archivos,
        dcc.Upload(id={"type": "con-archivo-subido", "index": conocimiento_id},
                    children=html.Div(["Arrastra un archivo o ", html.A("selecciónalo")]),
                    className="con-upload-zone", multiple=False),
    ])
    return True, r["titulo"], body


# --------------------------------------------------------------------------
# Botones de acción IA: arman el prompt y navegan al Asistente con el
# contenido pre-cargado (el usuario revisa y envía — nunca se llama a OpenAI
# automáticamente, para no gastar tokens sin que el usuario lo pida).
# --------------------------------------------------------------------------
_PROMPTS_IA = {
    "explicar": "Explícame esto como si estuviera empezando a aprenderlo:",
    "resumir": "Hazme un resumen breve de esto:",
    "preguntas": "Hazme 10 preguntas para evaluar si entendí esto:",
    "ejercicios": "Créame ejercicios prácticos sobre esto:",
    "mapa": "Hazme un mapa conceptual (Mermaid) de esto:",
    "codigo": "Dame un ejemplo de código sobre esto:",
    "siguiente": "Según esto que ya sé, ¿qué debería estudiar después?",
}


@dash.callback(
    Output("store-prompt-pendiente", "data"),
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": "con-accion-ia", "index": ALL}, "n_clicks"),
    State("store-conocimiento-seleccionado", "data"),
    State("con-detalle-titulo", "children"),
    prevent_initial_call=True,
)
def usar_accion_ia(n_clicks_list, conocimiento_id, titulo):
    if not n_clicks_list or not any(n_clicks_list) or not conocimiento_id:
        return dash.no_update, dash.no_update
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update
    prefijo = _PROMPTS_IA.get(triggered["index"], "Ayúdame con esto:")

    df = km.load_knowledge()
    fila = df[df["conocimiento_id"] == conocimiento_id]
    contenido = fila.iloc[0]["contenido"] if not fila.empty else ""
    prompt = f"{prefijo}\n\n**{titulo}**\n\n{contenido}"
    return prompt, "/asistente"
