"""
Sentinel Dash | Seguimiento de Proyectos — shell de la aplicación.

App Dash multi-página (dash.register_page) que usa seguimiento.xlsx como
única fuente de datos. Este archivo es el "shell": sidebar de navegación,
header, filtros globales (compartidos por todas las páginas vía dcc.Store),
carga de datos y el modal de detalle de actividad. Cada página vive en
pages/ y solo se preocupa de su propio contenido.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

import dash
import dash_auth
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dcc, html
from flask import request

import ai_assistant
import data as data_mod
import knowledge as km
import personal_auth
from components import badge_conocimiento_estado, badge_estado, badge_prioridad
from data_store import (df_from_store, df_to_store, hallazgos_to_store, issues_to_store,
                         knowledge_to_store, lookups_to_store)
from theme import MESES_ES, fmt_rango_periodo

# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
FONT_AND_ICONS_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  window.mermaid = mermaid;
  mermaid.initialize({ startOnLoad: false, theme: "neutral" });
</script>
"""

app = dash.Dash(
    __name__, use_pages=True, pages_folder="pages",
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="Seguimiento de Proyectos",
    suppress_callback_exceptions=True,
)
server = app.server
app.index_string = app.index_string.replace("</head>", FONT_AND_ICONS_HEAD + "</head>")

# Usuario/clave vienen de variables de entorno (nunca hardcodeados: el repo
# de GitHub es público). En local, si no están configuradas, la app queda
# sin login para facilitar el desarrollo — en Render sí se configuran.
_auth_user = os.environ.get("SEGUIMIENTO_AUTH_USER")
_auth_password = os.environ.get("SEGUIMIENTO_AUTH_PASSWORD")
if _auth_user and _auth_password:
    server.secret_key = os.environ.get("SEGUIMIENTO_SECRET_KEY", os.urandom(24).hex())
    dash_auth.BasicAuth(app, {_auth_user: _auth_password})

personal_auth.install(server)


@server.after_request
def _no_cache_dash_internals(response):
    """El navegador cachea agresivamente index.html y las rutas internas de
    Dash (_dash-dependencies, _dash-layout, _dash-update-component). Durante
    desarrollo eso hace que, tras reiniciar el servidor, una pestaña ya
    abierta siga usando un grafo de callbacks viejo y muestre errores que
    ya no existen en el servidor. Forzamos "no-cache" para que un refresh
    normal siempre traiga la versión actual."""
    if request.path == "/" or request.path.startswith("/_dash"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

NAV_ITEMS = [
    ("/personal", "Personal", "bi-wallet2"),
    ("/", "Resumen ejecutivo", "bi-house"),
    ("/actividades", "Actividades", "bi-list-check"),
    ("/calendario", "Calendario", "bi-calendar3"),
    ("/bloqueos", "Bloqueos y pendientes", "bi-exclamation-triangle"),
    ("/transversales", "Reuniones y Transversales", "bi-people"),
    ("/hallazgos", "Hallazgos", "bi-clipboard2-check"),
    ("/sentinel", "Sentinel Alerts", "bi-shield-check"),
    ("/new-opps", "New Opps", "bi-rocket-takeoff"),
    ("/analisis", "Análisis", "bi-bar-chart"),
    ("/conocimiento", "Conocimiento", "bi-mortarboard"),
    ("/asistente", "Asistente", "bi-robot"),
]


def _nav_link(path: str, label: str, icon: str) -> dcc.Link:
    return dcc.Link(
        [html.I(className=f"bi {icon}"), html.Span(label)],
        href=path, id={"type": "navlink", "path": path}, className="nav-link-item",
    )


sidebar = html.Div(className="sidebar", children=[
    html.Div(className="sidebar-brand", children=[
        html.Div("SEGUIMIENTO", className="sidebar-brand-line1"),
        html.Div("DE PROYECTOS", className="sidebar-brand-line2"),
    ]),
    html.Hr(className="sidebar-divider"),
    html.Nav([_nav_link(path, label, icon) for path, label, icon in NAV_ITEMS], className="sidebar-nav"),
    html.Div(className="sidebar-footer", children=[
        html.Hr(className="sidebar-divider"),
        html.Div(id="sidebar-updated", className="sidebar-updated"),
    ]),
])

filters_panel = html.Div(className="filters-panel", children=[
    html.Div([html.I(className="bi bi-sliders"), "Filtros de análisis"], className="filters-panel-title"),
    html.Div(className="filters-grid", children=[
        html.Div([
            html.Div([html.I(className="bi bi-calendar3"), "Periodo"], className="filter-label"),
            dcc.DatePickerRange(id="f-fechas", display_format="DD/MM/YYYY", className="w-100", persistence=True, persistence_type="session"),
            html.Div(id="f-fechas-dias-habiles", className="dias-habiles-badge"),
        ], className="filter-field"),
        html.Div([
            html.Div(" ", className="filter-label"),
            dbc.Button([html.I(className="bi bi-x-circle"), "Limpiar filtro"],
                        id="btn-clear-filters", className="btn-clear-filters"),
        ], className="filter-field"),
    ]),
])

app.layout = html.Div(className="app-shell", children=[
    dcc.Location(id="url"),
    dcc.Store(id="store-data"),
    dcc.Store(id="store-issues"),
    dcc.Store(id="store-hallazgos"),
    dcc.Store(id="store-lookups"),
    dcc.Store(id="store-selected-activity"),
    dcc.Store(id="store-conocimiento"),
    dcc.Store(id="store-prompt-pendiente"),
    dcc.Interval(id="interval-refresh", interval=5 * 60 * 1000, n_intervals=0),

    sidebar,

    html.Div(className="content-area", children=[
        html.Div(className="topbar", children=[
            dbc.Button([html.I(className="bi bi-arrow-clockwise"), "Actualizar datos"],
                        id="btn-refresh", className="btn-refresh"),
            html.Div(id="last-update-text", className="last-update"),
        ]),
        filters_panel,
        dash.page_container,
    ]),

    dbc.Modal([
    dbc.ModalHeader([
        dbc.ModalTitle(id="modal-actividad-title"),
        dbc.Button(html.I(className="bi bi-x-lg"), id="btn-cerrar-detalle-actividad",
                   className="btn-refresh", size="sm", n_clicks=0),
    ], close_button=False, className="activity-detail-header"),
        dbc.ModalBody(id="modal-actividad-body"),
        dbc.ModalFooter([
            dbc.Button([html.I(className="bi bi-flag-fill"), "Generar pendiente desde esta actividad"],
                        id="btn-generar-pendiente", className="btn-refresh", n_clicks=0),
            dbc.Button([html.I(className="bi bi-mortarboard-fill"), "Convertir en conocimiento"],
                        id="btn-convertir-conocimiento", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-actividad", is_open=False, size="lg", scrollable=True,
       className="activity-detail-modal"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Nuevo pendiente"), close_button=True),
        dbc.ModalBody([
            html.Div(id="pnd-form-error"),
            html.Div(id="pnd-form-origen", className="section-caption"),
            html.Div([html.Div([html.I(className="bi bi-card-text"), "Título del pendiente"], className="filter-label"),
                       dbc.Input(id="pnd-form-titulo", type="text",
                                  placeholder="p.ej. Realizar presentación")], className="mb-3"),
            html.Div([html.Div([html.I(className="bi bi-text-paragraph"), "Qué hay que hacer"], className="filter-label"),
                       dbc.Textarea(id="pnd-form-descripcion",
                                     placeholder="Detalle del pendiente que quedó de la actividad.",
                                     style={"height": "80px"})], className="mb-3"),
            dbc.Row([
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-exclamation-circle"), "Prioridad"],
                                              className="filter-label"),
                                    dcc.Dropdown(id="pnd-form-prioridad", options=["Alta", "Media", "Baja"],
                                                  value="Media", clearable=False)], className="mb-3"), md=6),
                dbc.Col(html.Div([html.Div([html.I(className="bi bi-calendar-event"), "Fecha límite (opcional)"],
                                              className="filter-label"),
                                    dcc.DatePickerSingle(id="pnd-form-fecha-limite", display_format="DD/MM/YYYY",
                                                           className="w-100")], className="mb-3"), md=6),
            ]),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-pendiente", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2"), "Guardar pendiente"],
                        id="btn-guardar-pendiente", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-nuevo-pendiente", is_open=False, size="lg", scrollable=True),

    dbc.Toast(
        id="shell-toast", header="Seguimiento de Proyectos", is_open=False, dismissable=True, duration=6000,
        style={"position": "fixed", "top": 20, "right": 20, "zIndex": 999, "minWidth": "320px"},
    ),
])


# --------------------------------------------------------------------------
# Carga de datos (botón + refresco periódico)
# --------------------------------------------------------------------------
@app.callback(
    Output("store-data", "data", allow_duplicate=True),
    Output("store-issues", "data"),
    Output("store-hallazgos", "data", allow_duplicate=True),
    Output("store-lookups", "data"),
    Output("store-conocimiento", "data", allow_duplicate=True),
    Output("last-update-text", "children"),
    Output("sidebar-updated", "children"),
    Input("btn-refresh", "n_clicks"),
    Input("interval-refresh", "n_intervals"),
    prevent_initial_call="initial_duplicate",
)
def refresh_data(_n_clicks, _n_intervals):
    loaded = data_mod.load_data()
    df = loaded["actividades"]
    hallazgos_df = data_mod.load_hallazgos()
    knowledge_df = km.load_knowledge()
    stamp_text = datetime.now().strftime("%d/%m/%Y %H:%M")
    topbar_stamp = [html.I(className="bi bi-record-circle-fill"), f"Datos al {stamp_text}"]
    sidebar_stamp = [html.Div("ACTUALIZADO", className="sidebar-updated-label"), stamp_text]
    lookups_json = lookups_to_store(loaded["proyectos"], loaded["tipos"], loaded["categorias"])
    return (df_to_store(df), issues_to_store(loaded["issues"]), hallazgos_to_store(hallazgos_df),
            lookups_json, knowledge_to_store(knowledge_df), topbar_stamp, sidebar_stamp)


# --------------------------------------------------------------------------
# Resaltado del link activo en el sidebar
# --------------------------------------------------------------------------
@app.callback(
    Output({"type": "navlink", "path": ALL}, "className"),
    Input("url", "pathname"),
)
def highlight_active_nav(pathname):
    paths = [path for path, _, _ in NAV_ITEMS]
    return ["nav-link-item active" if p == pathname else "nav-link-item" for p in paths]


# --------------------------------------------------------------------------
# Rango de fechas disponible (refleja el contenido actual del Excel)
# --------------------------------------------------------------------------
@app.callback(
    Output("f-fechas", "min_date_allowed"),
    Output("f-fechas", "max_date_allowed"),
    Input("store-data", "data"),
)
def update_filter_options(store_json):
    df = df_from_store(store_json)
    if df.empty:
        today = date.today()
        return today, today
    return df["fecha_inicio"].min().date(), df["fecha_inicio"].max().date()


# --------------------------------------------------------------------------
# Badge de periodo del header (id compartido por las 8 páginas). Vive en un
# único callback aquí, en vez de en cada página, porque Dash no permite que
# callbacks con la misma "firma" de Inputs targeteen el mismo Output aunque
# tengan allow_duplicate=True (varias páginas comparten exactamente los
# mismos filtros como Input, lo que generaba "Duplicate callback outputs").
# --------------------------------------------------------------------------
@app.callback(
    Output("page-header-period", "children"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_page_header_period(store_json, start_date, end_date):
    df = df_from_store(store_json)

    if not start_date or not end_date:
        total = len(df) if not df.empty else 0
        return f"Todo el periodo · {total} actividades"

    s = pd.Timestamp(start_date).date()
    e = pd.Timestamp(end_date).date()
    count = 0
    if not df.empty:
        fechas = df["fecha_inicio"].dt.date
        count = int(((fechas >= s) & (fechas <= e)).sum())

    hoy = date.today()
    inicio_semana_actual = hoy - timedelta(days=hoy.weekday())
    fin_semana_actual = inicio_semana_actual + timedelta(days=6)
    mes_fin = (pd.Timestamp(s) + pd.offsets.MonthEnd(0)).date()

    if s == inicio_semana_actual and e == fin_semana_actual:
        label = "Esta semana"
    elif s.day == 1 and e == mes_fin and s.year == e.year and s.month == e.month:
        label = f"{MESES_ES[s.month].capitalize()} {s.year}"
    else:
        label = fmt_rango_periodo(start_date, end_date)

    return f"{label} · {count} actividades"


# --------------------------------------------------------------------------
# Limpiar el filtro de fecha
# --------------------------------------------------------------------------
@app.callback(
    Output("f-fechas", "start_date"),
    Output("f-fechas", "end_date"),
    Input("btn-clear-filters", "n_clicks"),
    prevent_initial_call=True,
)
def clear_filters(_btn_clicks):
    return None, None


# --------------------------------------------------------------------------
# Contador de días hábiles (Colombia) del rango de fechas seleccionado
# --------------------------------------------------------------------------
@app.callback(
    Output("f-fechas-dias-habiles", "children"),
    Output("f-fechas-dias-habiles", "className"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
)
def update_dias_habiles_filtro(start_date, end_date):
    if not start_date or not end_date:
        children = [html.I(className="bi bi-calendar-check"),
                    html.Span("Selecciona fecha inicial y final para calcular los días hábiles")]
        return children, "dias-habiles-badge dias-habiles-badge-idle"

    s = pd.Timestamp(start_date).date()
    e = pd.Timestamp(end_date).date()
    if e < s:
        children = [html.I(className="bi bi-exclamation-triangle"),
                    html.Span("La fecha final debe ser posterior a la inicial")]
        return children, "dias-habiles-badge dias-habiles-badge-warning"

    n_dias, _festivos = data_mod.business_days_worked(s, e)
    etiqueta = "día hábil" if n_dias == 1 else "días hábiles"
    children = [html.I(className="bi bi-calendar-check"),
                html.Span([html.B(str(n_dias)), f" {etiqueta} entre el "
                            f"{s.strftime('%d/%m/%Y')} y el {e.strftime('%d/%m/%Y')}"])]
    return children, "dias-habiles-badge"


# --------------------------------------------------------------------------
# Modal de detalle de actividad (fuente única: store-selected-activity)
# --------------------------------------------------------------------------
def _modal_field(label: str, value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    return html.Div([
        html.Div(label, className="modal-field-label"),
        html.Div(text, className="modal-field-value"),
    ], className="modal-field")


@app.callback(
    Output("modal-actividad", "is_open"),
    Output("modal-actividad-title", "children"),
    Output("modal-actividad-body", "children"),
    Input("store-selected-activity", "data"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def open_activity_modal(actividad_id, store_json):
    if not actividad_id:
        return dash.no_update, dash.no_update, dash.no_update

    df = df_from_store(store_json)
    row = df[df["actividad_id"] == actividad_id]
    if row.empty:
        return dash.no_update, dash.no_update, dash.no_update
    r = row.iloc[0]

    horas_r = 0.0 if pd.isna(r["horas"]) else r["horas"]
    horario = f"{r['hora_inicio_txt'] or '—'} — {r['hora_fin_txt'] or '—'}"

    conocimientos = km.load_knowledge()
    relacionados = conocimientos[
        conocimientos["actividades_relacionadas"].fillna("").astype(str).str.split(",").apply(
            lambda ids: actividad_id in [item.strip() for item in ids]
        )
    ]
    conocimiento_relacionado = (
        html.Div(className="activity-detail-related", children=[
            html.Div([html.Span(k["conocimiento_id"], className="hal-card-motor"),
                      html.Div(k["titulo"], className="fw-semibold"),
                      badge_conocimiento_estado(k["estado"])])
            for _, k in relacionados.iterrows()
        ]) if not relacionados.empty else html.Div("No hay conocimiento relacionado registrado.",
                                                   className="section-caption"))

    title = [html.I(className="bi bi-journal-text me-2"), f"{actividad_id} — {r['actividad']}"]
    body = html.Div(className="activity-detail-body", children=[
        html.Div([badge_estado(r["estado"]), badge_prioridad(r["prioridad"])],
                 className="d-flex gap-2 mb-3"),
        html.Div("Información", className="section-title"),
        html.Div(className="activity-detail-fields", children=[
            _modal_field("Fecha", r["fecha_inicio"].strftime("%d/%m/%Y")),
            _modal_field("Horario", horario),
            _modal_field("Duración", f"{horas_r:.1f} horas"),
            _modal_field("Proyecto", r["proyecto"]),
            _modal_field("Tema", r["tema"]),
            _modal_field("Prioridad", r["prioridad"]),
            _modal_field("Estado", r["estado"]),
        ]),
        html.Div("Descripción", className="section-title mt-3"),
        html.Div(_modal_field("", r["descripcion"]) or "No registrada.", className="activity-detail-text"),
        html.Div("Resultado", className="section-title mt-3"),
        html.Div(_modal_field("", r["resultado"]) or "No se ha registrado un resultado.", className="activity-detail-text"),
        html.Div("Conocimiento relacionado", className="section-title mt-3"),
        conocimiento_relacionado,
        html.Div("Observaciones", className="section-title mt-3"),
        html.Div(_modal_field("", r["observaciones"]) or "No registradas.", className="activity-detail-text"),
    ])
    return True, title, body


@app.callback(
    Output("modal-actividad", "is_open", allow_duplicate=True),
    Input("btn-cerrar-detalle-actividad", "n_clicks"),
    prevent_initial_call=True,
)
def close_activity_detail(n_clicks):
    """Cierra el panel lateral de actividad después de un clic explícito."""
    return False if n_clicks else dash.no_update


# --------------------------------------------------------------------------
# Generar pendiente a partir de una actividad (desde el modal de detalle,
# disponible sin importar en qué página se abrió: Calendario, Actividades...)
# --------------------------------------------------------------------------
@app.callback(
    Output("modal-nuevo-pendiente", "is_open"),
    Output("modal-actividad", "is_open", allow_duplicate=True),
    Output("pnd-form-error", "children"),
    Output("pnd-form-origen", "children"),
    Output("pnd-form-titulo", "value"),
    Output("pnd-form-descripcion", "value"),
    Output("pnd-form-prioridad", "value"),
    Output("pnd-form-fecha-limite", "date"),
    Input("btn-generar-pendiente", "n_clicks"),
    State("store-selected-activity", "data"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def open_generar_pendiente(n_clicks, actividad_id, store_json):
    vacio = (dash.no_update,) * 8
    if not n_clicks or not actividad_id:
        return vacio

    df = df_from_store(store_json)
    row = df[df["actividad_id"] == actividad_id]
    if row.empty:
        return vacio
    r = row.iloc[0]

    origen = [
        html.I(className="bi bi-arrow-return-right me-1"),
        f'Se generará a partir de "{r["actividad"]}" ({r["proyecto"]}, '
        f'{r["fecha_inicio"].strftime("%d/%m/%Y")}).',
    ]
    return True, False, None, origen, None, None, "Media", None


@app.callback(
    Output("modal-nuevo-pendiente", "is_open", allow_duplicate=True),
    Input("btn-cancelar-pendiente", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_generar_pendiente(_n_clicks):
    return False


@app.callback(
    Output("store-data", "data", allow_duplicate=True),
    Output("modal-nuevo-pendiente", "is_open", allow_duplicate=True),
    Output("pnd-form-error", "children", allow_duplicate=True),
    Output("shell-toast", "children", allow_duplicate=True),
    Output("shell-toast", "icon", allow_duplicate=True),
    Output("shell-toast", "is_open", allow_duplicate=True),
    Input("btn-guardar-pendiente", "n_clicks"),
    State("store-selected-activity", "data"),
    State("store-data", "data"),
    State("pnd-form-titulo", "value"),
    State("pnd-form-descripcion", "value"),
    State("pnd-form-prioridad", "value"),
    State("pnd-form-fecha-limite", "date"),
    prevent_initial_call=True,
)
def guardar_pendiente(n_clicks, actividad_id, store_json, titulo, descripcion, prioridad, fecha_limite):
    if not n_clicks:
        return (dash.no_update,) * 6

    def error(msg):
        return (dash.no_update, True, html.Div(msg, className="section-caption", style={"color": "#a52323"}),
                dash.no_update, dash.no_update, dash.no_update)

    if not actividad_id:
        return error("No hay ninguna actividad de origen seleccionada.")
    if not titulo or not titulo.strip():
        return error("Escribe un título para el pendiente.")
    if not descripcion or not descripcion.strip():
        return error("Describe qué hay que hacer.")

    df = df_from_store(store_json)
    row = df[df["actividad_id"] == actividad_id]
    if row.empty:
        return error("No se encontró la actividad de origen (los datos pudieron cambiar).")
    r = row.iloc[0]

    def _clean(v):
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    fecha_pendiente = date.fromisoformat(fecha_limite) if fecha_limite else date.today()
    origen_txt = (f'Pendiente generado desde la actividad {actividad_id} '
                  f'("{r["actividad"]}", {r["fecha_inicio"].strftime("%d/%m/%Y")}).')

    ok, msg = data_mod.add_actividad(
        fecha_inicio=fecha_pendiente, hora_inicio=time(0, 0), hora_fin=time(0, 0),
        proyecto_id=_clean(r.get("proyecto_id")), tipo_actividad_id=_clean(r.get("tipo_actividad_id")),
        categoria_id=_clean(r.get("categoria_id")), actividad=titulo.strip(), descripcion=descripcion.strip(),
        tema=_clean(r["tema"]) or "Pendiente", resultado="Pendiente por completar",
        estado="Pendiente", prioridad=prioridad or "Media", motor=_clean(r.get("motor")),
        observaciones=origen_txt, fecha_fin=fecha_pendiente,
    )
    if not ok:
        return error(msg)

    nuevo_df = data_mod.load_data()["actividades"]
    return df_to_store(nuevo_df), False, None, "✓ Pendiente creado a partir de la actividad seleccionada.", "success", True


# --------------------------------------------------------------------------
# Convertir en conocimiento: crea una entrada preliminar directo desde el
# detalle de actividad (sin modal intermedio, igual que pide la sección 18
# del pedido original) — el usuario la termina de editar en /conocimiento.
# --------------------------------------------------------------------------
@app.callback(
    Output("store-conocimiento", "data", allow_duplicate=True),
    Output("shell-toast", "children", allow_duplicate=True),
    Output("shell-toast", "icon", allow_duplicate=True),
    Output("shell-toast", "is_open", allow_duplicate=True),
    Input("btn-convertir-conocimiento", "n_clicks"),
    State("store-selected-activity", "data"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def convertir_actividad_en_conocimiento(n_clicks, actividad_id, store_json):
    if not n_clicks:
        return (dash.no_update,) * 4
    if not actividad_id:
        return dash.no_update, "No hay ninguna actividad seleccionada.", "danger", True

    df = df_from_store(store_json)
    row = df[df["actividad_id"] == actividad_id]
    if row.empty:
        return dash.no_update, "No se encontró la actividad de origen (los datos pudieron cambiar).", "danger", True
    r = row.iloc[0]

    partes = []
    if r["descripcion"]:
        partes.append(f"**Descripción:** {r['descripcion']}")
    if r["resultado"]:
        partes.append(f"**Resultado:** {r['resultado']}")
    if r["observaciones"]:
        partes.append(f"**Observaciones:** {r['observaciones']}")
    contenido = "\n\n".join(partes) or "(completar)"

    ok, msg, _new_id = km.add_knowledge(
        titulo=r["actividad"], descripcion_breve=r["tema"] or "", contenido=contenido,
        categoria="Soluciones", estado="Pendiente de revisar", ambito="Proyecto",
        proyectos=r["proyecto"], etiquetas=None, fuente=None,
        actividades_relacionadas=actividad_id,
    )
    if not ok:
        return dash.no_update, msg, "danger", True

    nuevo_df = km.load_knowledge()
    return (knowledge_to_store(nuevo_df), f"✓ {msg} Puedes terminar de editarla en Conocimiento.",
            "success", True)


if __name__ == "__main__":
    app.run(debug=True, port=8060, use_reloader=False)
