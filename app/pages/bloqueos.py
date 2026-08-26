"""Bloqueos y pendientes — qué está frenado y por qué, sin inventar soluciones.

Los pendientes se muestran SIEMPRE, sin importar el filtro de fecha global:
representan tareas abiertas que hay que hacer, no un evento que ya ocurrió en
una fecha concreta, así que filtrarlos por "fecha_inicio" (su fecha límite)
los hacía desaparecer apenas el rango seleccionado no incluía esa fecha. Un
pendiente solo deja de listarse aquí cuando se cierra explícitamente con el
botón "Cerrar pendiente" (requiere un comentario), lo que lo pasa a estado
Completado con la fecha de cierre real — a partir de ahí es indistinguible de
cualquier otra actividad completada.
"""
from __future__ import annotations

import datetime as dt

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, dcc, html

import data as data_mod
from components import badge_prioridad, badge_proyecto, chart_card, kpi_card, page_header, success_state
from data_store import apply_all_filters, df_from_store, df_to_store, lookups_from_store
from theme import PRIORIDAD_PILL

dash.register_page(__name__, path="/bloqueos", name="Bloqueos y pendientes", title="Bloqueos y pendientes")

PRIORIDADES_FILTRO = [k for k in PRIORIDAD_PILL if k != "Sin prioridad"] + ["Sin prioridad"]

layout = html.Div(className="page", children=[
    page_header("Bloqueos y pendientes",
                 "Qué está frenado, qué tareas quedaron pendientes de actividades anteriores, y por qué.",
                 period_id="page-header-period"),

    html.Div(className="filters-panel", children=[
        html.Div([html.I(className="bi bi-sliders"), "Filtros"], className="filters-panel-title"),
        html.Div(className="filters-grid", children=[
            html.Div([
                html.Div([html.I(className="bi bi-search"), "Buscar"], className="filter-label"),
                dbc.Input(id="blq-f-buscar", type="text", debounce=True,
                           placeholder="Tema, actividad, descripción..."),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-folder2"), "Proyecto"], className="filter-label"),
                dcc.Dropdown(id="blq-f-proyecto", multi=True, placeholder="Todos"),
            ], className="filter-field"),
            html.Div([
                html.Div([html.I(className="bi bi-exclamation-circle"), "Prioridad"], className="filter-label"),
                dcc.Dropdown(id="blq-f-prioridad", options=PRIORIDADES_FILTRO, multi=True, placeholder="Todas"),
            ], className="filter-field"),
        ]),
    ]),

    html.Div([
        kpi_card("blq-kpi-total", "Total bloqueos", "bi bi-exclamation-triangle",
                  icon_id="blq-kpi-total-icon", tone="tone-good"),
        kpi_card("blq-kpi-sentinel", "Sentinel Alerts", "bi bi-shield-check"),
        kpi_card("blq-kpi-newopps", "New Opps", "bi bi-rocket-takeoff"),
        kpi_card("blq-kpi-pendientes", "Pendientes", "bi bi-flag",
                  icon_id="blq-kpi-pendientes-icon", tone="tone-good"),
        kpi_card("blq-kpi-vencidos", "Pendientes vencidos", "bi bi-alarm",
                  icon_id="blq-kpi-vencidos-icon", tone="tone-good"),
    ], className="kpi-grid"),

    chart_card([
        html.Div([html.I(className="bi bi-list-ul"), "Detalle de bloqueos"], className="section-title"),
        html.Div("Ordenados del más antiguo al más reciente — lo que lleva más tiempo frenado aparece primero.",
                  className="section-caption"),
        html.Div(id="blq-lista", className="hal-cards-grid"),
    ]),

    chart_card([
        html.Div([html.I(className="bi bi-flag"), "Pendientes generados desde actividades"], className="section-title"),
        html.Div("Se muestran todos los pendientes abiertos, sin importar el filtro de fecha del periodo — "
                  "ordenados por urgencia, vencidos primero. Un pendiente solo desaparece de aquí cuando se "
                  "cierra con un comentario.", className="section-caption"),
        html.Div(id="blq-lista-pendientes", className="hal-cards-grid"),
    ]),

    dcc.Store(id="store-pendiente-seleccionado"),
    dcc.Store(id="blq-clicks-baseline"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Cerrar pendiente"), close_button=True),
        dbc.ModalBody([
            html.Div(id="pnd-cierre-error"),
            html.Div(id="pnd-cierre-origen", className="section-caption"),
            html.Div([html.Div([html.I(className="bi bi-text-paragraph"), "Comentario de cierre"],
                                  className="filter-label"),
                       dbc.Textarea(id="pnd-cierre-comentario",
                                     placeholder="Qué se hizo / cómo quedó resuelto este pendiente.",
                                     style={"height": "90px"})], className="mb-2"),
            html.Div(id="pnd-cierre-fecha-info", className="section-caption"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancelar", id="btn-cancelar-cierre-pendiente", className="btn-cal-nav", n_clicks=0),
            dbc.Button([html.I(className="bi bi-check2-circle"), "Confirmar cierre"],
                        id="btn-confirmar-cierre-pendiente", className="btn-refresh", n_clicks=0),
        ]),
    ], id="modal-cerrar-pendiente", is_open=False),
])


def _chip(texto: str, tono: str) -> html.Span:
    return html.Span(texto, className=f"blq-chip blq-chip-{tono}")


def _chip_bloqueado(fecha_inicio) -> html.Span:
    dias = (dt.date.today() - fecha_inicio.date()).days
    if dias <= 0:
        return _chip("Bloqueado hoy", "warning")
    texto = f"Bloqueado hace {dias} día{'s' if dias != 1 else ''}"
    return _chip(texto, "critical" if dias >= 5 else "warning")


def _chip_vencimiento(fecha_limite) -> tuple[html.Span, int]:
    dias = (fecha_limite.date() - dt.date.today()).days
    if dias < 0:
        return _chip(f"Vencido hace {abs(dias)} día{'s' if abs(dias) != 1 else ''}", "critical"), dias
    if dias == 0:
        return _chip("Vence hoy", "warning"), dias
    if dias <= 3:
        return _chip(f"Vence en {dias} día{'s' if dias != 1 else ''}", "warning"), dias
    return _chip(f"Vence en {dias} días", "neutral"), dias


def _filtrar_comunes(df, proyectos, prioridades, buscar):
    if proyectos:
        df = df[df["proyecto"].isin(proyectos)]
    if prioridades:
        df = df[df["prioridad"].isin(prioridades)]
    if buscar:
        q = buscar.strip().lower()
        df = df[
            df["tema"].fillna("").str.lower().str.contains(q, regex=False)
            | df["actividad"].fillna("").str.lower().str.contains(q, regex=False)
            | df["descripcion"].fillna("").str.lower().str.contains(q, regex=False)
            | df["resultado"].fillna("").str.lower().str.contains(q, regex=False)
        ]
    return df


@dash.callback(
    Output("blq-f-proyecto", "options"),
    Input("store-lookups", "data"),
)
def update_bloqueos_proyecto_options(lookups_json):
    lookups = lookups_from_store(lookups_json)
    return [{"label": r["proyecto"], "value": r["proyecto"]} for r in lookups["proyectos"]]


@dash.callback(
    Output("blq-kpi-total", "children"), Output("blq-kpi-total-icon", "className"),
    Output("blq-kpi-sentinel", "children"),
    Output("blq-kpi-newopps", "children"),
    Output("blq-kpi-pendientes", "children"), Output("blq-kpi-pendientes-icon", "className"),
    Output("blq-kpi-vencidos", "children"), Output("blq-kpi-vencidos-icon", "className"),
    Output("blq-lista", "children"),
    Output("blq-lista-pendientes", "children"),
    Input("store-data", "data"),
    Input("f-fechas", "start_date"),
    Input("f-fechas", "end_date"),
    Input("blq-f-proyecto", "value"),
    Input("blq-f-prioridad", "value"),
    Input("blq-f-buscar", "value"),
)
def update_bloqueos(store_json, start_date, end_date, proyectos, prioridades, buscar):
    df = df_from_store(store_json)
    if df.empty:
        vacio = success_state("Sin datos disponibles.")
        return ("0", "kpi-icon tone-good", "0", "0", "0", "kpi-icon tone-good",
                "0", "kpi-icon tone-good", vacio, vacio)

    bloqueados = apply_all_filters(df[df["estado"] == "Bloqueado"], start_date, end_date)
    bloqueados = _filtrar_comunes(bloqueados, proyectos, prioridades, buscar)
    # Los pendientes NO se filtran por fecha: deben verse siempre hasta que se cierren.
    pendientes = _filtrar_comunes(df[df["estado"] == "Pendiente"], proyectos, prioridades, buscar)

    total = len(bloqueados)
    n_sentinel = int(bloqueados["proyecto"].eq("Sentinel Alerts").sum())
    n_newopps = int(bloqueados["proyecto"].eq("New Opps").sum())
    icon_tone = "kpi-icon tone-good" if total == 0 else "kpi-icon tone-critical"

    n_pendientes = len(pendientes)
    pendientes_icon_tone = "kpi-icon tone-good" if n_pendientes == 0 else "kpi-icon tone-warning"

    n_vencidos = int((pendientes["fecha_inicio"].dt.date < dt.date.today()).sum()) if not pendientes.empty else 0
    vencidos_icon_tone = "kpi-icon tone-good" if n_vencidos == 0 else "kpi-icon tone-critical"

    if bloqueados.empty:
        lista = success_state("No existen actividades bloqueadas con estos filtros.")
    else:
        cards = []
        # Lo que lleva más tiempo bloqueado es lo más urgente: se ordena por
        # fecha ascendente (el bloqueo más antiguo primero), no por el más
        # reciente.
        for _, r in bloqueados.sort_values("fecha_inicio", ascending=True).iterrows():
            cards.append(html.Div(className="blocker-card", children=[
                html.Div([html.I(className="bi bi-exclamation-octagon-fill"), badge_proyecto(r["proyecto"])],
                          className="blocker-card-head"),
                html.Div(r["tema"] or r["actividad"], className="blocker-card-title"),
                html.Div(f"Problema: {r['resultado'] or 'No especificado en los datos.'}",
                          className="blocker-card-body"),
                html.Div(className="blq-chip-row", children=[
                    _chip_bloqueado(r["fecha_inicio"]), badge_prioridad(r["prioridad"]),
                ]),
                html.Div(f"Desde el {r['fecha_inicio'].strftime('%d/%m/%Y')}", className="blocker-card-meta"),
            ]))
        lista = cards

    if pendientes.empty:
        lista_pendientes = success_state("No hay pendientes abiertos con estos filtros.")
    else:
        cards_p = []
        filas_con_urgencia = []
        for _, r in pendientes.iterrows():
            chip, dias = _chip_vencimiento(r["fecha_inicio"])
            filas_con_urgencia.append((dias, r, chip))
        filas_con_urgencia.sort(key=lambda t: t[0])  # vencidos (negativos) primero, luego más próximos

        for dias, r, chip in filas_con_urgencia:
            cards_p.append(html.Div(className="pending-card", children=[
                html.Div([html.I(className="bi bi-flag-fill"), badge_proyecto(r["proyecto"])],
                          className="blocker-card-head"),
                html.Div(r["actividad"], className="blocker-card-title"),
                html.Div(r["descripcion"] or "Sin descripción.", className="blocker-card-body"),
                html.Div(className="blq-chip-row", children=[chip, badge_prioridad(r["prioridad"])]),
                html.Div(f"Fecha límite: {r['fecha_inicio'].strftime('%d/%m/%Y')}", className="blocker-card-meta"),
                html.Div(r["observaciones"], className="blocker-card-meta") if r["observaciones"] else None,
                html.Div(className="pending-card-actions", children=[
                    dbc.Button([html.I(className="bi bi-check2-circle"), "Cerrar pendiente"],
                                id={"type": "btn-cerrar-pendiente", "index": r["actividad_id"]},
                                className="btn-refresh", size="sm", n_clicks=0),
                ]),
            ]))
        lista_pendientes = cards_p

    return (str(total), icon_tone, str(n_sentinel), str(n_newopps),
            str(n_pendientes), pendientes_icon_tone, str(n_vencidos), vencidos_icon_tone,
            lista, lista_pendientes)


# --------------------------------------------------------------------------
# Reinicia la línea base de clics al entrar a la página (mismo patrón que
# Hallazgos/Actividades: evita que un clic de una visita anterior en la
# misma sesión reabra el modal de cierre solo).
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-cerrar-pendiente", "is_open", allow_duplicate=True),
    Output("blq-clicks-baseline", "data"),
    Input("url", "pathname"),
    State("btn-confirmar-cierre-pendiente", "n_clicks"),
    prevent_initial_call=True,
)
def resetear_al_entrar(pathname, n_confirmar):
    if pathname != "/bloqueos":
        return dash.no_update, dash.no_update
    return False, {"btn-confirmar-cierre-pendiente": n_confirmar or 0}


# --------------------------------------------------------------------------
# Abrir el modal de cierre para un pendiente específico (botón dinámico,
# uno por tarjeta, identificado por su actividad_id).
# --------------------------------------------------------------------------
@dash.callback(
    Output("modal-cerrar-pendiente", "is_open"),
    Output("store-pendiente-seleccionado", "data"),
    Output("pnd-cierre-error", "children"),
    Output("pnd-cierre-origen", "children"),
    Output("pnd-cierre-comentario", "value"),
    Output("pnd-cierre-fecha-info", "children"),
    Input({"type": "btn-cerrar-pendiente", "index": ALL}, "n_clicks"),
    State("store-data", "data"),
    prevent_initial_call=True,
)
def abrir_cerrar_pendiente(n_clicks_list, store_json):
    if not n_clicks_list or not any(n_clicks_list):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    triggered = dash.ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    actividad_id = triggered["index"]
    df = df_from_store(store_json)
    fila = df[df["actividad_id"] == actividad_id]
    if fila.empty:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    r = fila.iloc[0]

    origen = f'Pendiente: "{r["actividad"]}" ({r["proyecto"]}) · Fecha límite: {r["fecha_inicio"].strftime("%d/%m/%Y")}'
    fecha_info = f'Se cerrará con fecha de hoy, {dt.date.today().strftime("%d/%m/%Y")}.'
    return True, actividad_id, None, origen, "", fecha_info


@dash.callback(
    Output("modal-cerrar-pendiente", "is_open", allow_duplicate=True),
    Input("btn-cancelar-cierre-pendiente", "n_clicks"),
    prevent_initial_call=True,
)
def cancelar_cierre_pendiente(_n_clicks):
    return False


@dash.callback(
    Output("store-data", "data", allow_duplicate=True),
    Output("modal-cerrar-pendiente", "is_open", allow_duplicate=True),
    Output("pnd-cierre-error", "children", allow_duplicate=True),
    Input("btn-confirmar-cierre-pendiente", "n_clicks"),
    State("store-pendiente-seleccionado", "data"),
    State("store-data", "data"),
    State("pnd-cierre-comentario", "value"),
    State("blq-clicks-baseline", "data"),
    prevent_initial_call=True,
)
def confirmar_cierre_pendiente(n_clicks, actividad_id, store_json, comentario, baseline):
    umbral = (baseline or {}).get("btn-confirmar-cierre-pendiente", 0)

    def error(msg):
        return dash.no_update, True, html.Div(msg, className="section-caption", style={"color": "#a52323"})

    if not n_clicks or n_clicks <= umbral:
        return dash.no_update, dash.no_update, dash.no_update
    if not actividad_id:
        return error("No hay ningún pendiente seleccionado.")
    if not comentario or not comentario.strip():
        return error("Escribe un comentario de cierre.")

    df = df_from_store(store_json)
    fila = df[df["actividad_id"] == actividad_id]
    if fila.empty:
        return error("No se encontró el pendiente seleccionado (los datos pudieron cambiar).")
    r = fila.iloc[0]

    def _clean(v):
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    ok, msg = data_mod.update_actividad(
        actividad_id=actividad_id,
        fecha_inicio=r["fecha_inicio"].date(), fecha_fin=dt.date.today(),
        hora_inicio=r["inicio_dt"].time() if pd.notna(r["inicio_dt"]) else dt.time(0, 0),
        hora_fin=r["fin_dt"].time() if pd.notna(r["fin_dt"]) else dt.time(0, 0),
        proyecto_id=_clean(r.get("proyecto_id")), tipo_actividad_id=_clean(r.get("tipo_actividad_id")),
        categoria_id=_clean(r.get("categoria_id")), actividad=r["actividad"], descripcion=r["descripcion"],
        tema=r["tema"], resultado=comentario.strip(), estado="Completado", prioridad=r["prioridad"],
        motor=_clean(r.get("motor")), observaciones=_clean(r.get("observaciones")),
    )
    if not ok:
        return error(msg)

    nuevo_df = data_mod.load_data()["actividades"]
    return df_to_store(nuevo_df), False, None
