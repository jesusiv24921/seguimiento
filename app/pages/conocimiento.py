"""Centro de Conocimiento — Knowledge Hub: estudio, soluciones, conceptos,
notas, con panel de detalle persistente (no modal) y exploración por tabs.

Mismo patrón que Hallazgos en lo estructural: fuente de verdad la pestaña
CONOCIMIENTO (y CONOCIMIENTO_ARCHIVOS) de seguimiento.xlsx, escritura real
vía knowledge.py, guardas contra el disparo fantasma de callbacks al entrar
a la página (dash/#1513).

Dos mecanismos de selección conviven a propósito:
- Checkbox de la tabla administrativa (con-tabla) -> store-conocimiento-
  seleccionado -> botones Ver/Editar/Eliminar. Para administración.
- Click directo en una tarjeta/fila (Estoy estudiando, Conocimiento
  reciente, Explorar) -> {"type": "con-item-select", "index":
  "seccion:conocimiento_id"} -> abre el panel de detalle directamente, por
  ID (no por posición, para no apuntar a la fila equivocada si el orden
  visible no coincide con el de la tabla). El prefijo de sección evita que
  dos tarjetas terminen con el mismo id de Dash (y por lo tanto el mismo
  atributo `id` en el HTML, inválido) cuando la misma entrada aparece a la
  vez en más de una sección — algo normal con pocas entradas todavía.
  Para navegar/consultar.
"""
from __future__ import annotations

import base64

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dash_table, dcc, html

import data as data_mod
import knowledge as km
from components import badge_conocimiento_estado, chart_card, kpi_card, page_header
from data_store import lookups_from_store
from theme import CONOCIMIENTO_CATEGORIA_ICONO, CONOCIMIENTO_ESTADO_PILL, GRID, INK_MUTED, INK_PRIMARY

dash.register_page(__name__, path="/conocimiento", name="Conocimiento", title="Conocimiento")


# ==========================================================================
# Layout
# ==========================================================================
layout = html.Div(className="page", children=[
    page_header("🧠 Centro de Conocimiento",
                 "Tu memoria técnica y de aprendizaje conectada con tus proyectos."),

    html.Div(className="con-header-actions mb-3", children=[
        dbc.Input(id="con-f-query", type="text", placeholder="Buscar conocimiento...",
                    className="con-header-search"),
        dbc.Button([html.I(className="bi bi-upload"), "Importar"],
                    id="btn-importar-conocimiento", className="btn-refresh", n_clicks=0),
        dbc.Button([html.I(className="bi bi-plus-lg"), "Nuevo conocimiento"],
                    id="btn-nuevo-conocimiento", className="btn-refresh", n_clicks=0),
    ]),

    html.Div(className="con-layout-grid", children=[
        html.Div(className="con-layout-main", children=[

            html.Div([
                kpi_card("con-kpi-total", "Conocimientos", "bi bi-journal-bookmark"),
                kpi_card("con-kpi-estudio", "En estudio", "bi bi-book", tone="tone-warning"),
                kpi_card("con-kpi-aplicado", "Aplicados", "bi bi-check2-circle", tone="tone-good"),
                kpi_card("con-kpi-soluciones", "Soluciones", "bi bi-tools"),
                kpi_card("con-kpi-revisar", "Por revisar", "bi bi-flag", tone="tone-critical"),
            ], className="kpi-grid"),

            chart_card([
                html.Div([html.I(className="bi bi-book"), "Estoy estudiando"], className="section-title"),
                html.Div("Conocimientos en estudio o en progreso, con tu avance por concepto.",
                          className="section-caption"),
                html.Div(id="con-estudiando-cards", className="hal-cards-grid"),
            ]),

            chart_card([
                html.Div([html.I(className="bi bi-clock-history"), "Conocimiento reciente"], className="section-title"),
                html.Div("Últimas entradas creadas o actualizadas.", className="section-caption"),
                html.Div(id="con-recientes-lista", className="con-reciente-lista"),
            ]),

            html.Div(className="filters-panel", children=[
                html.Div([html.I(className="bi bi-sliders"), "Filtros avanzados"], className="filters-panel-title"),
                html.Div(className="filters-grid", children=[
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
                html.Div([html.I(className="bi bi-compass"), "Explorar conocimiento"], className="section-title"),
                html.Div("Navega por categoría, o cambia a tabla para administrar (editar/eliminar).",
                          className="section-caption"),
                html.Div(className="con-explorar-toolbar", children=[
                    dbc.Tabs(id="con-explorar-tabs", active_tab="todo", children=[
                        dbc.Tab(label="Todo", tab_id="todo"),
                        *[dbc.Tab(label=cat, tab_id=cat) for cat in km.CATEGORIAS],
                    ]),
                    html.Div(className="d-flex gap-1", children=[
                        dbc.Button([html.I(className="bi bi-grid-3x3-gap"), "Tarjetas"],
                                    id="con-btn-vista-tarjetas", className="btn-refresh", size="sm", n_clicks=0),
                        dbc.Button([html.I(className="bi bi-table"), "Tabla"],
                                    id="con-btn-vista-tabla", className="btn-refresh active", size="sm", n_clicks=0),
                    ]),
                ]),

                html.Div(id="con-explorar-cards-wrap", style={"display": "none"}, children=[
                    html.Div(id="con-explorar-cards", className="hal-cards-grid"),
                ]),

                html.Div(id="con-explorar-tabla-wrap", style={"display": "block"}, children=[
                    html.Div(className="hal-actions-row", children=[
                        dbc.Button([html.I(className="bi bi-eye"), "Ver detalle"],
                                    id="btn-ver-conocimiento", className="btn-refresh", disabled=True),
                        dbc.Button([html.I(className="bi bi-pencil"), "Editar"],
                                    id="btn-editar-conocimiento", className="btn-refresh", disabled=True),
                        dbc.Button([html.I(className="bi bi-trash"), "Eliminar"],
                                    id="btn-eliminar-conocimiento", className="btn-refresh", disabled=True),
                        html.Div(id="con-selection-msg", className="hal-selection-msg"),
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
            ]),
        ]),

        dbc.Modal([
            dbc.ModalHeader([
                dbc.ModalTitle(id="con-detalle-title"),
                dbc.Button(html.I(className="bi bi-x-lg"), id="btn-cerrar-detalle-conocimiento",
                           className="btn-refresh", size="sm", n_clicks=0),
            ], close_button=False, className="activity-detail-header"),
            dbc.ModalBody(id="con-detalle-body"),
        ], id="modal-detalle-conocimiento", is_open=False, scrollable=True, backdrop=False,
           className="knowledge-detail-modal",
           dialog_style={"position": "fixed", "top": 0, "right": 0, "bottom": 0,
                         "width": "min(100vw, 1100px)", "maxWidth": "none", "height": "100vh", "margin": 0},
           content_style={"height": "100vh", "borderRadius": 0}),
    ]),

    dcc.Store(id="store-conocimiento-seleccionado"),
    dcc.Store(id="con-clicks-baseline"),
    dcc.Store(id="con-importar-archivo"),

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
            html.Div([html.Div([html.I(className="bi bi-lightbulb"), "Lección aprendida (opcional)"], className="filter-label"),
                       dbc.Textarea(id="con-form-leccion", style={"height": "70px"},
                                     placeholder="La idea clave que te quieres llevar de esto")],
                       className="mb-3"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-conocimiento", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Guardar"],
                        id="btn-guardar-conocimiento", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-conocimiento", is_open=False, size="lg", scrollable=True),

    # ---- Importar ----
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Importar conocimiento"), close_button=True),
        dbc.ModalBody([
            html.Div("Sube un archivo .md o .txt — su contenido se convierte en una entrada nueva "
                      "y el archivo original queda adjunto como referencia.", className="section-caption mb-2"),
            dcc.Upload(id="con-importar-upload", accept=".md,.txt",
                        children=html.Div(["Arrastra un archivo o ", html.A("selecciónalo")]),
                        className="con-upload-zone mb-3", multiple=False),
            html.Div(id="con-importar-preview", className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-card-text"), "Título"], className="filter-label"),
                       dbc.Input(id="con-importar-titulo", type="text", placeholder="Título de la entrada")],
                       className="mb-3"),
            dbc.Row([
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-tags"), "Categoría"], className="filter-label"),
                                    dcc.Dropdown(id="con-importar-categoria", options=km.CATEGORIAS,
                                                  value="Notas", clearable=False)], className="mb-3"), md=6),
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-tag"), "Etiquetas"], className="filter-label"),
                                    dbc.Input(id="con-importar-etiquetas", type="text",
                                               placeholder="separadas por coma")], className="mb-3"), md=6),
            ]),
            html.Div([html.Div([html.I(className="bi bi-folder2"), "Proyectos relacionados"], className="filter-label"),
                       dcc.Dropdown(id="con-importar-proyectos", multi=True, placeholder="Ninguno (opcional)")],
                       className="mb-3"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-importar", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Importar"],
                        id="con-btn-confirmar-importar", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-importar-conocimiento", is_open=False, size="lg", scrollable=True),

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


# ==========================================================================
# Helpers
# ==========================================================================
def _split_csv(valor) -> list[str]:
    """Divide un campo de texto separado por comas en una lista, tolerando
    NaN: cuando una columna de CONOCIMIENTO queda vacía en todas las filas
    del store (p.ej. muy pocas entradas todavía), el viaje por JSON la
    infiere como float64 (NaN) en vez de texto/None, y un simple
    '(valor or "").split(",")' revienta con AttributeError."""
    if not isinstance(valor, str) or not valor.strip():
        return []
    return [v.strip() for v in valor.split(",") if v.strip()]


def _texto_o_vacio(valor) -> str:
    return valor if isinstance(valor, str) else ""


def _campos_vacios():
    return (None, "", "", "Estudio", "En estudio", "Global", [], "", "", [], "", "", "")


def _fecha_relativa(fecha) -> str:
    if pd.isna(fecha):
        return "—"
    dias = (pd.Timestamp.now().normalize() - fecha.normalize()).days
    if dias == 0:
        return "Hoy"
    if dias == 1:
        return "Ayer"
    return fecha.strftime("%d/%m/%Y")


def _con_card_admin(idx: int, row: dict) -> html.Div:
    """Tarjeta de administración (fallback móvil de con-tabla): selecciona
    por POSICIÓN en la tabla filtrada, para habilitar Editar/Eliminar —
    a propósito distinta del click-directo-por-ID usado en Estoy estudiando/
    Reciente/Explorar."""
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


def _con_card(row: dict, mostrar_progreso: bool = False, mostrar_etiquetas: bool = False,
              seccion: str = "explorar") -> html.Div:
    """Tarjeta clickeable por conocimiento_id (Estoy estudiando / Explorar).
    Usada para navegar directo al panel de detalle.

    `seccion` se antepone al index del id: si la misma entrada aparece a la
    vez en varias secciones de la página (p.ej. está en "Conocimiento
    reciente" Y en "Explorar" al mismo tiempo, algo normal con pocas
    entradas), dos elementos con el MISMO id de Dash terminan siendo dos
    elementos HTML con el mismo atributo `id` — inválido, y el navegador
    solo reacciona de forma fiable a uno de los dos. Prefijar por sección
    garantiza que cada botón tenga un id realmente único en la página."""
    pill = CONOCIMIENTO_ESTADO_PILL.get(row["estado"], {"bg": "#eee", "fg": "#333"})
    icono = CONOCIMIENTO_CATEGORIA_ICONO.get(row["categoria"], "bi-journal-text")
    hijos = [
        html.Div(className="hal-card-head", children=[
            html.Span(row["estado"], className="status-pill",
                       style={"backgroundColor": pill["bg"], "color": pill["fg"]}),
            html.Span([html.I(className=f"bi {icono} me-1"), row["categoria"]], className="hal-card-motor"),
        ]),
        html.Div(row["titulo"], className="hal-card-desc"),
    ]
    if mostrar_etiquetas:
        etiquetas = _split_csv(row.get("etiquetas"))
        if etiquetas:
            hijos.append(html.Div(className="d-flex flex-wrap gap-1 mb-2", children=[
                html.Span(e, className="hal-card-motor") for e in etiquetas[:4]
            ]))
    if mostrar_progreso and row.get("progreso") is not None:
        conceptos = km.parse_conceptos(row.get("conceptos"))
        comprendidos = sum(1 for c in conceptos if c["progreso"] >= 70)
        hijos.append(dbc.Progress(value=row["progreso"], label=f"{row['progreso']}%",
                                    className="mb-1", style={"height": "0.6rem"}))
        if conceptos:
            hijos.append(html.Div(f"{comprendidos} de {len(conceptos)} conceptos",
                                    className="hal-card-meta-value mb-2"))
    hijos.append(html.Div(className="hal-card-meta-grid", children=[
        html.Div([html.Span("Proyectos", className="hal-card-meta-label"),
                   html.Span(row.get("proyectos") or "—", className="hal-card-meta-value")]),
        html.Div([html.Span(("Último estudio" if mostrar_progreso else "Actualizado"),
                              className="hal-card-meta-label"),
                   html.Span(_fecha_relativa(row["fecha_actualizacion"]), className="hal-card-meta-value")]),
    ]))
    hijos.append(dbc.Button("Continuar estudiando" if mostrar_progreso else "Ver",
                              id={"type": "con-item-select", "index": f"{seccion}:{row['conocimiento_id']}"},
                              className="btn-refresh btn-sm-card", size="sm", n_clicks=0))
    return html.Div(className="hal-card", children=hijos)


def _con_reciente_row(row: dict) -> html.Div:
    pill = CONOCIMIENTO_ESTADO_PILL.get(row["estado"], {"bg": "#eee", "fg": "#333"})
    return html.Button(className="con-reciente-row", n_clicks=0,
                         id={"type": "con-item-select", "index": f"reciente:{row['conocimiento_id']}"}, children=[
        html.Span(row["estado"], className="status-pill",
                   style={"backgroundColor": pill["bg"], "color": pill["fg"]}),
        html.Div([
            html.Div(row["titulo"], className="con-reciente-row-title"),
            html.Div(f"{row['categoria']} · {row.get('proyectos') or 'Global'}",
                      className="con-reciente-row-meta"),
        ]),
        html.Div(row["fecha_actualizacion_txt"], className="con-reciente-row-fecha"),
    ])


def _estado_vacio_detalle() -> html.Div:
    return html.Div(className="empty-state", children=[
        html.I(className="bi bi-journal-text"),
        html.Div("Selecciona una entrada para ver el detalle."),
    ])


# ==========================================================================
# Opciones de filtros / formularios (catálogo real de proyectos/actividades)
# ==========================================================================
@dash.callback(
    Output("con-f-proyecto", "options"),
    Output("con-form-proyectos", "options"),
    Output("con-importar-proyectos", "options"),
    Input("store-lookups", "data"),
)
def update_conocimiento_proyecto_options(lookups_json):
    lookups = lookups_from_store(lookups_json)
    opts = [{"label": r["proyecto"], "value": r["proyecto"]} for r in lookups["proyectos"]]
    return opts, opts, opts


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


# ==========================================================================
# KPIs + tabla admin + tarjetas admin + tarjetas Explorar
# ==========================================================================
@dash.callback(
    Output("con-kpi-total", "children"),
    Output("con-kpi-estudio", "children"),
    Output("con-kpi-aplicado", "children"),
    Output("con-kpi-soluciones", "children"),
    Output("con-kpi-revisar", "children"),
    Output("con-tabla", "data"),
    Output("con-tabla-cards", "children"),
    Output("con-explorar-cards", "children"),
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
        return "0", "0", "0", "0", "0", [], [], []

    total_global = len(df)
    en_estudio_global = int(df["estado"].isin(["En estudio", "En progreso"]).sum())
    aplicado_global = int(df["estado"].isin(["Aprendido", "Aplicado"]).sum())
    soluciones_global = int(df["categoria"].eq("Soluciones").sum())
    revisar_global = int(df["estado"].eq("Pendiente de revisar").sum())

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

    tabla = filtered.copy()
    tabla["fecha_actualizacion_txt"] = tabla["fecha_actualizacion"].dt.strftime("%d/%m/%Y").fillna("—")
    tabla = tabla.sort_values("fecha_actualizacion", ascending=False)
    cols = ["conocimiento_id", "titulo", "categoria", "estado", "ambito", "proyectos",
            "fecha_actualizacion_txt"]
    tabla_data = tabla[cols].to_dict("records")
    admin_cards = [_con_card_admin(i, fila) for i, fila in enumerate(tabla_data)]

    explorar_cards = [_con_card(row, mostrar_etiquetas=True, seccion="explorar") for _, row in tabla.iterrows()]

    return (str(total_global), str(en_estudio_global), str(aplicado_global), str(soluciones_global),
            str(revisar_global), tabla_data, admin_cards, explorar_cards)


@dash.callback(
    Output("con-f-categoria", "value", allow_duplicate=True),
    Input("con-explorar-tabs", "active_tab"),
    prevent_initial_call=True,
)
def aplicar_tab_categoria(tab):
    if not tab or tab == "todo":
        return []
    return [tab]


@dash.callback(
    Output("con-explorar-cards-wrap", "style"),
    Output("con-explorar-tabla-wrap", "style"),
    Output("con-btn-vista-tarjetas", "className"),
    Output("con-btn-vista-tabla", "className"),
    Input("con-btn-vista-tarjetas", "n_clicks"),
    Input("con-btn-vista-tabla", "n_clicks"),
    prevent_initial_call=True,
)
def cambiar_vista_explorar(_n_tarjetas, _n_tabla):
    if dash.ctx.triggered_id == "con-btn-vista-tabla":
        return {"display": "none"}, {"display": "block"}, "btn-refresh", "btn-refresh active"
    return {"display": "block"}, {"display": "none"}, "btn-refresh active", "btn-refresh"


# ==========================================================================
# Portada: "Estoy estudiando" / "Conocimiento reciente"
# ==========================================================================
@dash.callback(
    Output("con-estudiando-cards", "children"),
    Output("con-recientes-lista", "children"),
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

    tarjetas_estudiando = [_con_card(row, mostrar_progreso=True, seccion="estudiando") for _, row in estudiando.iterrows()]
    filas_recientes = [_con_reciente_row(row) for _, row in recientes.iterrows()]
    return tarjetas_estudiando, filas_recientes


# ==========================================================================
# Selección admin (checkbox de la tabla) — sin cambios de comportamiento
# ==========================================================================
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


# ==========================================================================
# Reset al entrar a la página (evita callbacks fantasma de dash/#1513)
# ==========================================================================
@dash.callback(
    Output("modal-conocimiento", "is_open", allow_duplicate=True),
    Output("modal-importar-conocimiento", "is_open", allow_duplicate=True),
    Output("modal-eliminar-conocimiento", "is_open", allow_duplicate=True),
    Output("con-form-error", "children", allow_duplicate=True),
    Output("con-tabla", "selected_rows", allow_duplicate=True),
    Output("con-clicks-baseline", "data"),
    Input("url", "pathname"),
    State("btn-nuevo-conocimiento", "n_clicks"),
    State("btn-editar-conocimiento", "n_clicks"),
    State("btn-eliminar-conocimiento", "n_clicks"),
    State("btn-ver-conocimiento", "n_clicks"),
    State("btn-importar-conocimiento", "n_clicks"),
    prevent_initial_call=True,
)
def cerrar_modales_al_entrar(pathname, n_nuevo, n_editar, n_eliminar, n_ver, n_importar):
    if pathname != "/conocimiento":
        return (dash.no_update,) * 6
    baseline = {
        "btn-nuevo-conocimiento": n_nuevo or 0, "btn-editar-conocimiento": n_editar or 0,
        "btn-eliminar-conocimiento": n_eliminar or 0, "btn-ver-conocimiento": n_ver or 0,
        "btn-importar-conocimiento": n_importar or 0,
    }
    # El panel de detalle ya nace vacío en el layout. No se actualiza desde
    # este callback para que su respuesta tardía no borre una selección que
    # el usuario acaba de abrir.
    return False, False, False, None, [], baseline


# ==========================================================================
# Nuevo / editar: abrir, cancelar, guardar
# ==========================================================================
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
    Output("con-form-leccion", "value"),
    Output("con-form-modal-title", "children"),
    Input("btn-nuevo-conocimiento", "n_clicks"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_nuevo_conocimiento(n_clicks, baseline):
    umbral = (baseline or {}).get("btn-nuevo-conocimiento", 0)
    if not n_clicks or n_clicks <= umbral:
        return (dash.no_update,) * 16
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
    Output("con-form-leccion", "value", allow_duplicate=True),
    Output("con-form-modal-title", "children", allow_duplicate=True),
    Input("btn-editar-conocimiento", "n_clicks"),
    State("store-conocimiento-seleccionado", "data"),
    State("store-conocimiento", "data"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_editar_conocimiento(n_clicks, conocimiento_id, store_json, baseline):
    from data_store import knowledge_from_store
    vacio = (dash.no_update,) * 16
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
    return (True, None, r["titulo"], r["descripcion_breve"], r["contenido"], r["categoria"],
            r["estado"], r["ambito"], proyectos_list, _texto_o_vacio(r["etiquetas"]),
            _texto_o_vacio(r["fuente"]), actividades_list, _texto_o_vacio(r["objetivo_estudio"]),
            _texto_o_vacio(r["conceptos"]), _texto_o_vacio(r["leccion_aprendida"]),
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
    State("con-form-leccion", "value"),
    State("con-form-modal-title", "children"),
    prevent_initial_call=True,
)
def guardar_conocimiento(n_clicks, seleccionado_id, titulo, desc_breve, contenido, categoria,
                          estado, ambito, proyectos_list, etiquetas, fuente, actividades_list,
                          objetivo, conceptos, leccion, modal_title):
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

    kwargs = dict(
        titulo=titulo.strip(), descripcion_breve=(desc_breve or "").strip(), contenido=contenido.strip(),
        categoria=categoria, estado=estado, ambito=ambito, proyectos=proyectos_txt,
        etiquetas=(etiquetas or "").strip() or None, fuente=(fuente or "").strip() or None,
        actividades_relacionadas=actividades_txt, objetivo_estudio=(objetivo or "").strip() or None,
        conceptos=(conceptos or "").strip() or None, leccion_aprendida=(leccion or "").strip() or None,
    )

    if es_edicion:
        if not seleccionado_id:
            return error("No hay ninguna entrada seleccionada.")
        ok, msg = km.update_knowledge(seleccionado_id, **kwargs)
    else:
        ok, msg, _new_id = km.add_knowledge(**kwargs)
    if not ok:
        return error(msg)

    nuevo_df = km.load_knowledge()
    return knowledge_to_store(nuevo_df), False, None, f"✓ {msg}", "success", True


# ==========================================================================
# Importar: abrir/cancelar, procesar archivo, confirmar
# ==========================================================================
@dash.callback(
    Output("modal-importar-conocimiento", "is_open"),
    Output("con-importar-archivo", "data"),
    Output("con-importar-preview", "children"),
    Output("con-importar-titulo", "value"),
    Output("con-importar-categoria", "value"),
    Output("con-importar-proyectos", "value"),
    Output("con-importar-etiquetas", "value"),
    Input("btn-importar-conocimiento", "n_clicks"),
    State("con-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def abrir_importar_conocimiento(n_clicks, baseline):
    umbral = (baseline or {}).get("btn-importar-conocimiento", 0)
    if not n_clicks or n_clicks <= umbral:
        return (dash.no_update,) * 7
    return True, None, None, "", "Notas", [], ""


@dash.callback(
    Output("modal-importar-conocimiento", "is_open", allow_duplicate=True),
    Input("btn-cancelar-importar", "n_clicks"),
    prevent_initial_call=True,
)
def cancelar_importar(_n_clicks):
    return False


@dash.callback(
    Output("con-importar-archivo", "data", allow_duplicate=True),
    Output("con-importar-preview", "children", allow_duplicate=True),
    Output("con-importar-titulo", "value", allow_duplicate=True),
    Input("con-importar-upload", "contents"),
    State("con-importar-upload", "filename"),
    prevent_initial_call=True,
)
def procesar_archivo_importar(contents, filename):
    if not contents:
        return dash.no_update, dash.no_update, dash.no_update
    try:
        _header, encoded = contents.split(",", 1)
        raw = base64.b64decode(encoded)
        texto = raw.decode("utf-8", errors="replace")
    except Exception:
        return (None, html.Div("No se pudo leer ese archivo. Debe ser .md o .txt en texto plano.",
                                  className="section-caption", style={"color": "#a52323"}), dash.no_update)
    titulo_sugerido = filename.rsplit(".", 1)[0] if filename else "Importado"
    recorte = texto if len(texto) <= 3000 else texto[:3000] + "\n\n*(vista previa recortada)*"
    preview = html.Div([
        html.Div(f"📄 {filename}", className="section-caption mb-2"),
        dcc.Markdown(recorte),
    ])
    return {"filename": filename, "contents": contents, "texto": texto}, preview, titulo_sugerido


@dash.callback(
    Output("store-conocimiento", "data", allow_duplicate=True),
    Output("modal-importar-conocimiento", "is_open", allow_duplicate=True),
    Output("con-toast", "children", allow_duplicate=True),
    Output("con-toast", "icon", allow_duplicate=True),
    Output("con-toast", "is_open", allow_duplicate=True),
    Input("con-btn-confirmar-importar", "n_clicks"),
    State("con-importar-archivo", "data"),
    State("con-importar-titulo", "value"),
    State("con-importar-categoria", "value"),
    State("con-importar-proyectos", "value"),
    State("con-importar-etiquetas", "value"),
    prevent_initial_call=True,
)
def confirmar_importar(n_clicks, archivo, titulo, categoria, proyectos_list, etiquetas):
    from data_store import knowledge_to_store
    if not n_clicks:
        return (dash.no_update,) * 5
    if not archivo or not archivo.get("texto"):
        return dash.no_update, dash.no_update, "Primero selecciona un archivo .md o .txt.", "danger", True
    if not titulo or not titulo.strip():
        return dash.no_update, dash.no_update, "Escribe un título.", "danger", True

    proyectos_txt = ", ".join(proyectos_list) if proyectos_list else None
    ok, msg, new_id = km.add_knowledge(
        titulo=titulo.strip(), descripcion_breve=f"Importado desde {archivo['filename']}",
        contenido=archivo["texto"], categoria=categoria or "Notas", estado="Pendiente de revisar",
        ambito="Proyecto" if proyectos_txt else "Global", proyectos=proyectos_txt,
        etiquetas=(etiquetas or "").strip() or None,
    )
    if not ok:
        return dash.no_update, dash.no_update, msg, "danger", True

    _header, encoded = archivo["contents"].split(",", 1)
    raw = base64.b64decode(encoded)
    km.add_knowledge_file(new_id, archivo["filename"], raw)

    nuevo_df = km.load_knowledge()
    return knowledge_to_store(nuevo_df), False, f"✓ {msg}", "success", True


# ==========================================================================
# Eliminar
# ==========================================================================
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


# ==========================================================================
# Detalle: panel persistente con pestañas, acciones de IA, archivos
# ==========================================================================
def _accion_ia_boton(label: str, icon: str, prompt_tipo: str) -> dbc.Button:
    return dbc.Button([html.I(className=icon), label], size="sm", className="btn-refresh btn-sm-card",
                        id={"type": "con-accion-ia", "index": prompt_tipo}, n_clicks=0)


def _construir_detalle(conocimiento_id: str, actividades_json) -> html.Div:
    df = km.load_knowledge()
    fila = df[df["conocimiento_id"] == conocimiento_id]
    if fila.empty:
        return _estado_vacio_detalle()
    r = fila.iloc[0]
    descripcion_txt = _texto_o_vacio(r["descripcion_breve"])
    contenido_txt = _texto_o_vacio(r["contenido"])
    objetivo_txt = _texto_o_vacio(r["objetivo_estudio"])
    proyectos_txt = _texto_o_vacio(r["proyectos"]) or "Ninguno"

    dfa = km.load_knowledge_files()
    archivos = dfa[dfa["conocimiento_id"] == conocimiento_id]
    lista_archivos = html.Div(className="section-caption", children=[
        html.Div([html.I(className="bi bi-paperclip me-1"), a["nombre_archivo"]])
        for _, a in archivos.iterrows()
    ]) if not archivos.empty else html.Div("Sin archivos adjuntos.", className="section-caption")

    etiquetas = _split_csv(r["etiquetas"])

    # ---- Resumen ----
    leccion_txt = _texto_o_vacio(r["leccion_aprendida"])
    tab_resumen = [
        html.Div([badge_conocimiento_estado(r["estado"]),
                   html.Span(r["categoria"], className="hal-card-motor ms-2")],
                  className="d-flex align-items-center gap-2 mb-2"),
        html.Div([html.Span(e, className="hal-card-motor") for e in etiquetas],
                  className="con-detalle-etiquetas") if etiquetas else None,
        html.Div(descripcion_txt, className="section-caption mb-3"),
    ]
    if leccion_txt:
        tab_resumen.append(html.Div(className="con-leccion-box", children=[
            html.I(className="bi bi-lightbulb-fill"),
            html.Div([
                html.Div("Lección aprendida", className="con-leccion-box-titulo"),
                html.Div(leccion_txt, className="con-leccion-box-texto"),
            ]),
        ]))

    # ---- Contenido ----
    tab_contenido = [
        dcc.Markdown(contenido_txt or "_Sin contenido registrado todavía._", className="mb-3"),
        html.Div("🤖 Acciones IA", className="section-title"),
        html.Div(className="d-flex flex-wrap gap-2 mb-2", children=[
            _accion_ia_boton("Explicarme", "bi bi-mortarboard", "explicar"),
            _accion_ia_boton("Resumir", "bi bi-card-list", "resumir"),
            _accion_ia_boton("Hacerme preguntas", "bi bi-question-circle", "preguntas"),
            _accion_ia_boton("Crear ejercicios", "bi bi-pencil-square", "ejercicios"),
            _accion_ia_boton("Mapa conceptual", "bi bi-diagram-3", "mapa"),
            _accion_ia_boton("Ejemplo de código", "bi bi-code-slash", "codigo"),
            _accion_ia_boton("Qué estudiar después", "bi bi-signpost", "siguiente"),
        ]),
    ]

    # ---- Conceptos ----
    conceptos = km.parse_conceptos(r["conceptos"])
    tab_conceptos = []
    if objetivo_txt:
        tab_conceptos.append(html.Div([html.Span("🎯 ", className="me-1"), objetivo_txt],
                                        className="section-caption mb-2"))
    if conceptos:
        progreso = km.progreso_promedio(r["conceptos"])
        tab_conceptos.append(dbc.Progress(value=progreso, label=f"{progreso}%", className="mb-2"))
        tab_conceptos.append(html.Div(className="d-flex flex-wrap gap-2", children=[
            html.Span(f"{c['nombre']} · {c['progreso']}%", className="hal-card-motor")
            for c in conceptos
        ]))
    else:
        tab_conceptos.append(html.Div("Sin conceptos registrados todavía.", className="section-caption"))

    # ---- Relaciones ----
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

    hallazgos_txt = _texto_o_vacio(r["hallazgos_relacionados"])
    bloque_hallazgos = (html.Div(hallazgos_txt, className="section-caption") if hallazgos_txt else
                          html.Div("Ningún hallazgo relacionado.", className="section-caption"))

    etiquetas_propias = {e.lower() for e in etiquetas}
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

    tab_relaciones = dbc.Row([
        dbc.Col([html.Div("Proyectos", className="section-title"),
                  html.Div(proyectos_txt, className="section-caption")], md=6, className="mb-3"),
        dbc.Col([html.Div("Actividades relacionadas", className="section-title"),
                  bloque_actividades], md=6, className="mb-3"),
        dbc.Col([html.Div("Hallazgos relacionados", className="section-title"),
                  bloque_hallazgos], md=6, className="mb-3"),
        dbc.Col([html.Div("Conocimiento relacionado", className="section-title"),
                  bloque_relacionado], md=6, className="mb-3"),
    ])

    # ---- Archivos ----
    tab_archivos = [
        lista_archivos,
        dcc.Upload(id={"type": "con-archivo-subido", "index": conocimiento_id},
                    children=html.Div(["Arrastra un archivo o ", html.A("selecciónalo")]),
                    className="con-upload-zone mt-2", multiple=False),
    ]

    # ---- Historial (honesto: solo lo que realmente se guarda) ----
    tab_historial = html.Div([
        html.Div([html.Span("Creado: ", className="hal-card-meta-label"),
                   html.Span(r["fecha_creacion"].strftime("%d/%m/%Y") if pd.notna(r["fecha_creacion"]) else "—")],
                  className="mb-2"),
        html.Div([html.Span("Última actualización: ", className="hal-card-meta-label"),
                   html.Span(r["fecha_actualizacion"].strftime("%d/%m/%Y") if pd.notna(r["fecha_actualizacion"]) else "—")]),
        html.Div("El registro de cambios detallado por campo no está disponible todavía.",
                  className="section-caption mt-2"),
    ])

    return html.Div([
        html.Div(className="con-detalle-secciones", children=[
            html.Div(tab_resumen, className="con-detalle-seccion"),
            html.Div([html.Div("Contenido", className="section-title"), *tab_contenido],
                     className="con-detalle-seccion"),
            html.Div([html.Div("Conceptos", className="section-title"), *tab_conceptos],
                     className="con-detalle-seccion"),
            html.Div([html.Div("Relaciones", className="section-title"), tab_relaciones],
                     className="con-detalle-seccion"),
            html.Div([html.Div("Archivos", className="section-title"), *tab_archivos],
                     className="con-detalle-seccion"),
            html.Div([html.Div("Historial", className="section-title"), tab_historial],
                     className="con-detalle-seccion"),
        ]),
    ])


@dash.callback(
    Output("modal-detalle-conocimiento", "is_open"),
    Output("con-detalle-title", "children"),
    Output("con-detalle-body", "children"),
    Output("store-conocimiento-seleccionado", "data", allow_duplicate=True),
    Input("btn-ver-conocimiento", "n_clicks"),
    Input("con-tabla", "active_cell"),
    Input({"type": "con-item-select", "index": ALL}, "n_clicks"),
    Input({"type": "con-archivo-subido", "index": ALL}, "contents"),
    State("con-tabla", "data"),
    State({"type": "con-archivo-subido", "index": ALL}, "filename"),
    State("store-conocimiento-seleccionado", "data"),
    State("con-clicks-baseline", "data"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def abrir_detalle_conocimiento(n_clicks, active_cell, item_clicks_list, contents_list, table_data, filenames_list,
                                conocimiento_id, baseline, actividades_json):
    umbral = (baseline or {}).get("btn-ver-conocimiento", 0)
    triggered_id = dash.ctx.triggered_id

    es_por_boton = triggered_id == "btn-ver-conocimiento"
    es_por_tabla = triggered_id == "con-tabla"
    es_por_item = isinstance(triggered_id, dict) and triggered_id.get("type") == "con-item-select"
    es_por_archivo = isinstance(triggered_id, dict) and triggered_id.get("type") == "con-archivo-subido"

    if es_por_boton and (not n_clicks or n_clicks <= umbral):
        return (dash.no_update,) * 4
    if es_por_item:
        if not item_clicks_list or not any(item_clicks_list):
            return (dash.no_update,) * 4
        # El index viene como "seccion:conocimiento_id" (ver _con_card /
        # _con_reciente_row) para que el mismo id nunca se repita si una
        # misma entrada aparece a la vez en varias secciones de la página.
        conocimiento_id = triggered_id["index"].split(":", 1)[-1]
    if es_por_tabla:
        idx = (active_cell or {}).get("row")
        if idx is None or not table_data or idx >= len(table_data):
            return (dash.no_update,) * 4
        conocimiento_id = table_data[idx]["conocimiento_id"]
    if not conocimiento_id:
        return (dash.no_update,) * 4

    if es_por_archivo and contents_list and any(contents_list):
        idx = [i for i, c in enumerate(contents_list) if c][-1]
        contenido_b64 = contents_list[idx]
        filename = filenames_list[idx]
        _header, encoded = contenido_b64.split(",", 1)
        raw = base64.b64decode(encoded)
        km.add_knowledge_file(conocimiento_id, filename, raw)

    # Se fija store-conocimiento-seleccionado al ID mostrado (no solo al
    # seleccionado por checkbox) para que "Acciones IA" siempre opere sobre
    # la entrada que el usuario está viendo, sin importar cómo llegó a ella
    # (tarjeta clickeada directamente o fila de la tabla administrativa).
    conocimiento = km.load_knowledge()
    fila = conocimiento[conocimiento["conocimiento_id"] == conocimiento_id]
    titulo = fila.iloc[0].get("titulo", "Detalle de conocimiento") if not fila.empty else "Detalle de conocimiento"
    return (True, titulo, _construir_detalle(conocimiento_id, actividades_json), conocimiento_id)


@dash.callback(
    Output("modal-detalle-conocimiento", "is_open", allow_duplicate=True),
    Input("btn-cerrar-detalle-conocimiento", "n_clicks"),
    prevent_initial_call=True,
)
def cerrar_detalle_conocimiento(n_clicks):
    """Cierra un panel únicamente después de un clic real en su botón."""
    # Dash puede disparar el callback cuando el botón se inserta dinámicamente
    # con n_clicks=0. Ese evento inicial no debe cerrar el detalle recién
    # abierto.
    return False if n_clicks else dash.no_update


# --------------------------------------------------------------------------
# Botones de acción IA: arman el prompt (+ contexto de proyecto) y navegan
# al Asistente con el contenido pre-cargado (el usuario revisa y envía —
# nunca se llama a OpenAI automáticamente, para no gastar tokens sin que el
# usuario lo pida).
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
    prevent_initial_call=True,
)
def usar_accion_ia(n_clicks_list, conocimiento_id):
    if not n_clicks_list or not any(n_clicks_list):
        return dash.no_update, dash.no_update
    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update

    df = km.load_knowledge()
    fila = df[df["conocimiento_id"] == conocimiento_id] if conocimiento_id else df.iloc[0:0]
    if fila.empty:
        return dash.no_update, dash.no_update
    r = fila.iloc[0]

    prefijo = _PROMPTS_IA.get(triggered["index"], "Ayúdame con esto:")
    prompt = f"{prefijo}\n\n**{r['titulo']}**\n\n{r['contenido'] or ''}"
    proyectos = _split_csv(r["proyectos"])
    payload = {"prompt": prompt, "proyecto_contexto": proyectos[0] if proyectos else None}
    return payload, "/asistente"
