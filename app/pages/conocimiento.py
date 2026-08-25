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

    chart_card([
        html.Div([html.I(className="bi bi-book"), "Estoy estudiando"], className="section-title"),
        html.Div("Entradas en estudio o en progreso, con tu avance por concepto.", className="section-caption"),
        html.Div(id="con-estudiando-cards", className="hal-cards-grid"),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-clock-history"), "Conocimiento reciente"], className="section-title"),
        html.Div("Últimas entradas creadas o actualizadas.", className="section-caption"),
        html.Div(id="con-recientes-cards", className="hal-cards-grid"),
    ]),

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
            html.Div([html.Div([html.I(className="bi bi-diagram-3"), "Actividades relacionadas"], className="filter-label"),
                       dcc.Dropdown(id="con-form-actividades", multi=True, placeholder="Ninguna (opcional)")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-flag-fill"), "Objetivo de estudio (opcional)"], className="filter-label"),
                       dbc.Input(id="con-form-objetivo", type="text",
                                  placeholder="p.ej. Poder construir una API completa con FastAPI")],
                       className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-list-check"), "Conceptos y progreso (opcional)"], className="filter-label"),
                       dbc.Textarea(id="con-form-conceptos", style={"height": "70px"},
                                     placeholder="nombre:porcentaje separados por coma, p.ej. "
                                                  "Routing:100, Pydantic:80, Dependency Injection:40")],
                       className="mb-1"),
            html.Div("El progreso general se calcula como el promedio de estos porcentajes.",
                      className="section-caption mb-3"),
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


def _split_csv(valor) -> list[str]:
    """Divide un campo de texto separado por comas en una lista, tolerando
    NaN: cuando una columna de CONOCIMIENTO queda vacía en todas las filas
    del store (p.ej. muy pocas entradas todavía), el viaje por JSON la
    infiere como float64 (NaN) en vez de texto/None, y un simple
    '(valor or "").split(",")' revienta con AttributeError."""
    if not isinstance(valor, str) or not valor.strip():
        return []
    return [v.strip() for v in valor.split(",") if v.strip()]


def _campos_vacios():
    return (None, "", "", "Estudio", "En estudio", "Global", [], "", "", [], "", "")


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


def _con_card_portada(row: dict, mostrar_progreso: bool = False) -> html.Div:
    """Tarjeta para las secciones 'Estoy estudiando' / 'Conocimiento reciente'
    de la portada. A diferencia de _con_card (que selecciona una fila de la
    tabla por posición), el botón aquí navega directo por conocimiento_id —
    estas tarjetas muestran un subconjunto en un orden distinto al de la
    tabla, así que un índice posicional apuntaría a la fila equivocada."""
    pill = CONOCIMIENTO_ESTADO_PILL.get(row["estado"], {"bg": "#eee", "fg": "#333"})
    hijos = [
        html.Div(className="hal-card-head", children=[
            html.Span(row["estado"], className="status-pill",
                       style={"backgroundColor": pill["bg"], "color": pill["fg"]}),
            html.Span(row["categoria"], className="hal-card-motor"),
        ]),
        html.Div(row["titulo"], className="hal-card-desc"),
    ]
    if mostrar_progreso and row.get("progreso") is not None:
        hijos.append(dbc.Progress(value=row["progreso"], label=f"{row['progreso']}%",
                                    className="mb-2", style={"height": "0.6rem"}))
    hijos.append(html.Div(className="hal-card-meta-grid", children=[
        html.Div([html.Span("Proyectos", className="hal-card-meta-label"),
                   html.Span(row["proyectos"] or "—", className="hal-card-meta-value")]),
        html.Div([html.Span("Actualizado", className="hal-card-meta-label"),
                   html.Span(row["fecha_actualizacion_txt"], className="hal-card-meta-value")]),
    ]))
    hijos.append(dbc.Button("Continuar estudiando" if mostrar_progreso else "Ver",
                              id={"type": "con-portada-select", "index": row["conocimiento_id"]},
                              className="btn-refresh btn-sm-card", size="sm", n_clicks=0))
    return html.Div(className="hal-card", children=hijos)


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


@dash.callback(
    Output("con-form-actividades", "options"),
    Input("store-data", "data"),
)
def update_conocimiento_actividad_options(store_json):
    from data_store import df_from_store
    df = df_from_store(store_json)
    if df.empty:
        return []
    tabla = df.sort_values("fecha_inicio", ascending=False)
    return [{"label": f"{r['actividad_id']} — {r['actividad']} ({r['proyecto']})", "value": r["actividad_id"]}
            for _, r in tabla.iterrows()]


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
# Portada: "Estoy estudiando" / "Conocimiento reciente" (independiente de
# los filtros de abajo — siempre muestra el estado real más reciente).
# --------------------------------------------------------------------------
@dash.callback(
    Output("con-estudiando-cards", "children"),
    Output("con-recientes-cards", "children"),
    Input("store-conocimiento", "data"),
)
def update_conocimiento_portada(store_json):
    from data_store import knowledge_from_store
    df = knowledge_from_store(store_json)
    if df.empty:
        return [], []
    df = df.copy()
    df["fecha_actualizacion_txt"] = df["fecha_actualizacion"].dt.strftime("%d/%m/%Y").fillna("—")
    df["progreso"] = df["conceptos"].apply(km.progreso_promedio)

    estudiando = (df[df["estado"].isin(["En estudio", "En progreso"])]
                  .sort_values("fecha_actualizacion", ascending=False).head(6))
    recientes = df.sort_values("fecha_actualizacion", ascending=False).head(6)

    tarjetas_estudiando = [_con_card_portada(row, mostrar_progreso=True) for _, row in estudiando.iterrows()]
    tarjetas_recientes = [_con_card_portada(row, mostrar_progreso=False) for _, row in recientes.iterrows()]
    return tarjetas_estudiando, tarjetas_recientes


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
    Output("con-form-actividades", "value"),
    Output("con-form-objetivo", "value"),
    Output("con-form-conceptos", "value"),
    Output("con-form-modal-title", "children"),
    Input("btn-nuevo-conocimiento", "n_clicks"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_nuevo_conocimiento(n_clicks, baseline):
    umbral = (baseline or {}).get("btn-nuevo-conocimiento", 0)
    if not n_clicks or n_clicks <= umbral:
        return (dash.no_update,) * 15
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
    Output("con-form-actividades", "value", allow_duplicate=True),
    Output("con-form-objetivo", "value", allow_duplicate=True),
    Output("con-form-conceptos", "value", allow_duplicate=True),
    Output("con-form-modal-title", "children", allow_duplicate=True),
    Input("btn-editar-conocimiento", "n_clicks"),
    State("store-conocimiento-seleccionado", "data"),
    State("store-conocimiento", "data"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_editar_conocimiento(n_clicks, conocimiento_id, store_json, baseline):
    from data_store import knowledge_from_store
    vacio = (dash.no_update,) * 15
    umbral = (baseline or {}).get("btn-editar-conocimiento", 0)
    if not n_clicks or n_clicks <= umbral or not conocimiento_id:
        return vacio
    df = knowledge_from_store(store_json)
    fila = df[df["conocimiento_id"] == conocimiento_id]
    if fila.empty:
        return vacio
    r = fila.iloc[0]
    proyectos_list = _split_csv(r["proyectos"])
    actividades_list = _split_csv(r["actividades_relacionadas"])
    etiquetas_txt = r["etiquetas"] if isinstance(r["etiquetas"], str) else ""
    fuente_txt = r["fuente"] if isinstance(r["fuente"], str) else ""
    objetivo_txt = r["objetivo_estudio"] if isinstance(r["objetivo_estudio"], str) else ""
    conceptos_txt = r["conceptos"] if isinstance(r["conceptos"], str) else ""
    return (True, None, r["titulo"], r["descripcion_breve"], r["contenido"], r["categoria"],
            r["estado"], r["ambito"], proyectos_list, etiquetas_txt, fuente_txt,
            actividades_list, objetivo_txt, conceptos_txt,
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
    State("con-form-actividades", "value"),
    State("con-form-objetivo", "value"),
    State("con-form-conceptos", "value"),
    State("con-form-modal-title", "children"),
    prevent_initial_call=True,
)
def guardar_conocimiento(n_clicks, seleccionado_id, titulo, desc_breve, contenido, categoria,
                          estado, ambito, proyectos_list, etiquetas, fuente, actividades_list,
                          objetivo, conceptos, modal_title):
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
    actividades_txt = ", ".join(actividades_list) if actividades_list else None
    es_edicion = modal_title and str(modal_title).startswith("Editar:")

    if es_edicion:
        if not seleccionado_id:
            return error("No hay ninguna entrada seleccionada.")
        ok, msg = km.update_knowledge(
            seleccionado_id, titulo=titulo.strip(), descripcion_breve=(desc_breve or "").strip(),
            contenido=contenido.strip(), categoria=categoria, estado=estado, ambito=ambito,
            proyectos=proyectos_txt, etiquetas=(etiquetas or "").strip() or None,
            fuente=(fuente or "").strip() or None, actividades_relacionadas=actividades_txt,
            objetivo_estudio=(objetivo or "").strip() or None, conceptos=(conceptos or "").strip() or None,
        )
    else:
        ok, msg, _new_id = km.add_knowledge(
            titulo=titulo.strip(), descripcion_breve=(desc_breve or "").strip(), contenido=contenido.strip(),
            categoria=categoria, estado=estado, ambito=ambito, proyectos=proyectos_txt,
            etiquetas=(etiquetas or "").strip() or None, fuente=(fuente or "").strip() or None,
            actividades_relacionadas=actividades_txt, objetivo_estudio=(objetivo or "").strip() or None,
            conceptos=(conceptos or "").strip() or None,
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
    Input({"type": "con-portada-select", "index": ALL}, "n_clicks"),
    State({"type": "con-archivo-subido", "index": ALL}, "filename"),
    State("store-conocimiento-seleccionado", "data"),
    State("con-clicks-baseline", "data"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def abrir_detalle_conocimiento(n_clicks, contents_list, portada_clicks_list, filenames_list,
                                conocimiento_id, baseline, actividades_json):
    umbral = (baseline or {}).get("btn-ver-conocimiento", 0)
    triggered_id = dash.ctx.triggered_id
    es_por_boton = triggered_id == "btn-ver-conocimiento"
    es_por_portada = isinstance(triggered_id, dict) and triggered_id.get("type") == "con-portada-select"
    if es_por_boton and (not n_clicks or n_clicks <= umbral):
        return dash.no_update, dash.no_update, dash.no_update
    if es_por_portada:
        if not portada_clicks_list or not any(portada_clicks_list):
            return dash.no_update, dash.no_update, dash.no_update
        conocimiento_id = triggered_id["index"]
    if not conocimiento_id:
        return dash.no_update, dash.no_update, dash.no_update

    if not es_por_boton and not es_por_portada and contents_list and any(contents_list):
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

    # ---- Estudio: objetivo, progreso y conceptos ----
    bloque_estudio = []
    if isinstance(r["objetivo_estudio"], str) and r["objetivo_estudio"]:
        bloque_estudio.append(html.Div([html.Span("🎯 ", className="me-1"), r["objetivo_estudio"]],
                                          className="section-caption mb-2"))
    conceptos = km.parse_conceptos(r["conceptos"] if isinstance(r["conceptos"], str) else None)
    if conceptos:
        progreso = km.progreso_promedio(r["conceptos"])
        bloque_estudio.append(dbc.Progress(value=progreso, label=f"{progreso}%", className="mb-2"))
        bloque_estudio.append(html.Div(className="d-flex flex-wrap gap-2 mb-3", children=[
            html.Span(f"{c['nombre']} · {c['progreso']}%", className="hal-card-motor")
            for c in conceptos
        ]))

    # ---- Actividades relacionadas (por actividad_id sobre store-data) ----
    ids_actividad = _split_csv(r["actividades_relacionadas"])
    bloque_actividades = html.Div("Ninguna actividad relacionada.", className="section-caption")
    if ids_actividad:
        from data_store import df_from_store
        dfact = df_from_store(actividades_json)
        relacionadas = dfact[dfact["actividad_id"].isin(ids_actividad)] if not dfact.empty else dfact
        if not relacionadas.empty:
            bloque_actividades = html.Div(className="section-caption", children=[
                html.Div([html.I(className="bi bi-diagram-3 me-1"),
                           f"{a['actividad']} ({a['proyecto']}, {a['estado']})"])
                for _, a in relacionadas.iterrows()
            ])

    # ---- Hallazgos relacionados (texto libre: los hallazgos no tienen ID propio) ----
    hallazgos_txt = r["hallazgos_relacionados"] if isinstance(r["hallazgos_relacionados"], str) else ""
    bloque_hallazgos = (html.Div(hallazgos_txt, className="section-caption") if hallazgos_txt else
                          html.Div("Ningún hallazgo relacionado.", className="section-caption"))

    # ---- Conocimiento relacionado: mismas etiquetas o mismo proyecto (sin embeddings) ----
    etiquetas_propias = {e.lower() for e in _split_csv(r["etiquetas"])}
    proyectos_propios = {p.lower() for p in _split_csv(r["proyectos"])}

    def _relacionado(otra) -> bool:
        etq_otra = {e.lower() for e in _split_csv(otra["etiquetas"])}
        proy_otra = {p.lower() for p in _split_csv(otra["proyectos"])}
        return bool(etiquetas_propias & etq_otra) or bool(proyectos_propios & proy_otra)

    otras = df[df["conocimiento_id"] != conocimiento_id]
    relacionadas_kw = [row for _, row in otras.iterrows() if _relacionado(row)][:5] \
        if (etiquetas_propias or proyectos_propios) else []
    bloque_relacionado = html.Div("Sin conocimiento relacionado detectado.", className="section-caption")
    if relacionadas_kw:
        bloque_relacionado = html.Div(className="section-caption", children=[
            html.Div([html.I(className="bi bi-link-45deg me-1"), f"{a['titulo']} ({a['categoria']})"])
            for a in relacionadas_kw
        ])

    body = html.Div([
        html.Div([badge_conocimiento_estado(r["estado"]),
                   html.Span(r["categoria"], className="hal-card-motor ms-2")],
                  className="d-flex align-items-center gap-2 mb-3"),
        html.Div(r["descripcion_breve"] or "", className="section-caption mb-2"),
        *bloque_estudio,
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
        html.Div("Actividades relacionadas", className="section-title"),
        bloque_actividades,
        html.Div("Hallazgos relacionados", className="section-title mt-2"),
        bloque_hallazgos,
        html.Div("Conocimiento relacionado", className="section-title mt-2"),
        bloque_relacionado,
        html.Div("Archivos adjuntos", className="section-title mt-2"),
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
